#!/usr/bin/env python3
"""
run_gap_pipeline_v5.py — V5 终极重构：路径驱动 + LLM + 约束收束 + 全量统计指标

V5 完整设计原则
══════════════
  ① 拓扑即等级（V3/V4 保留）
       L2A: ego→A→B  (主车起始)
       L2B: A→B→C   (物体起始, 全部非 ego)   ← V5 重定义
  ② LLM 语义感知（每个 L2 cell 必须调用 LLM）
       LLM 生成上下文 Cypher，返回 B 的全量属性 + 中间节点的干扰项兄弟
  ③ 统一约束收束（L2A 与 L2B 结构对称）
       gap_target = 路径终点 (B/C)
       candidates = 中间节点 (A/B) 的其他邻居（干扰项）
       CumulativeConstraintChain.tighten() 找最小约束组合
  ④ 物理足迹核验 — 满足 footprint_nodes = 3 才计入 ΔL2
  ⑤ Logic_Verification (Step 5d.5) — Neo4j 验证 n=1

V5 CSV 七项必填指标
════════════════════
  Path_Structure   : 完整 ID 链 (ego→car1→car2)
  Topology_Level   : L2A / L2B
  Template_ID      : 对应模板库编号
  Constraint_Trace : 收束推演全程 (Path→type(F,14)→dir8(S,1))
  Token_Prompt     : 真实 LLM prompt token 数
  Token_Completion : 真实 LLM completion token 数
  Logic_Verification: Step 5d.5 的 Neo4j 验证结果 (n=1 ✅ / n=X ❌)
  Footprint_Nodes  : 该题实际覆盖的所有节点 ID

debug log: output/pipeline_debug.log
"""
from __future__ import annotations

import argparse, csv, json, logging, sys, time, uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_gap_pipeline_v5")

# ── Debug log setup ───────────────────────────────────────────────────────────
_debug_log_path: Optional[Path] = None

def _dlog(msg: str) -> None:
    """Write one line to pipeline_debug.log."""
    if _debug_log_path:
        with _debug_log_path.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")


# =============================================================================
# Timing
# =============================================================================

@contextmanager
def _measure() -> Generator[list, None, None]:
    buf: list = [0.0]
    t0 = time.perf_counter()
    yield buf
    buf[0] = (time.perf_counter() - t0) * 1_000


# =============================================================================
# Helpers: Constraint_Trace + Logic_Verification
# =============================================================================

def _format_constraint_trace(trace_log: list, method_used: str) -> str:
    """
    Format: "Path→type(F,61)→status(F,61)→dir8(S,1)"
    'Path' = the chain constraint itself (first level of uniqueness).
    """
    parts = ["Path"]
    for item in trace_log:
        flag = "S" if item["success"] else "F"
        n    = item.get("remaining_n", "?")
        parts.append(f"{item['method']}({flag},{n})")
    if not trace_log and method_used:
        parts.append(f"{method_used}(S,1)")
    return "→".join(parts)


def _build_l2_verify_cypher(
    n1_id: str, n2_id: str, n3_id: str,
    method_used: str,
    tighten_value: Dict,
    ctx: Dict,
) -> str:
    """
    Build a Neo4j Cypher that counts how many nodes satisfy the L2 path +
    attribute constraints. Should return n=1 for a uniquely-locked result.

    Works for both L2A (n1_id='ego') and L2B (n1_id=any non-ego).
    """
    conditions: List[str] = []
    parts = set(method_used.split("+"))

    if "type" in parts or method_used in ("type_filter", "type_status_anchor"):
        v = tighten_value.get("type") or ctx.get("n3_type", "")
        if v: conditions.append(f"c.type = '{v}'")

    if "status" in parts or method_used in ("status_anchor", "type_status_anchor"):
        v = tighten_value.get("status") or ctx.get("n3_status", "")
        if v: conditions.append(f"coalesce(c.status,'') = '{v}'")

    if "dir8" in parts or method_used in ("dir8_refine", "dir8"):
        v = tighten_value.get("dir8") or ctx.get("r2_dir8", "")
        if v: conditions.append(f"r2.direction_8 = '{v}'")

    if "dist_ord" in parts or method_used in ("dist_order", "ordinal_by_distance"):
        order = tighten_value.get("dist_ord") or tighten_value.get("order", "closest")
        order_sql = "ASC" if order == "closest" else "DESC"
        where = " AND ".join(conditions) if conditions else "true"
        return (
            f"MATCH (a:Object {{unique_id:'{n1_id}'}})-[:RELATES_TO]->(b:Object {{unique_id:'{n2_id}'}})"
            f"-[r2:RELATES_TO]->(c:Object)\n"
            f"WHERE {where}\n"
            f"RETURN count(c) AS n, collect(c.unique_id) AS ids\n"
            f"ORDER BY r2.distance {order_sql} LIMIT 3"
        )

    where = " AND ".join(conditions) if conditions else "true"
    return (
        f"MATCH (a:Object {{unique_id:'{n1_id}'}})-[:RELATES_TO]->(b:Object {{unique_id:'{n2_id}'}})"
        f"-[r2:RELATES_TO]->(c:Object)\n"
        f"WHERE {where}\n"
        f"RETURN count(c) AS n, collect(c.unique_id) AS ids"
    )


def _run_verify(driver, vcypher: str, tgt_id: str) -> str:
    """Run verify Cypher, return 'n=1 ✅' or 'n=X ❌' string."""
    try:
        with driver.session() as sess:
            rec = sess.run(vcypher).single()
        if rec:
            n   = rec.get("n", 0)
            ids = list(rec.get("ids", []))
            ok  = (n == 1 and tgt_id in ids)
            return f"n={n} {'✅' if ok else '❌'} ids={ids[:3]}"
        return "n=0 ❌ (no result)"
    except Exception as exc:
        return f"ERR: {exc}"


# =============================================================================
# Question rendering
# =============================================================================

def _render_l2_question(
    topology: str,
    ctx: Dict,
    method_used: str,
    tighten_value: Dict,
) -> str:
    """
    Generate the chain question for both L2A and L2B.

    L2A template:
      "What [constraint] {n3_type} is to the {r2_dir8} of the {n2_type}
       that is to the {r1_dir4} of ego?"

    L2B template:
      "What [constraint] {n3_type} is to the {r2_dir8} of the {n2_type}
       that is to the {r1_dir8} of {n1_type} {n1_id}?"

    Both explicitly name the chain: {start} → {middle} → {end}.
    """
    n1_id   = ctx.get("n1_id",  "ego")
    n1_type = ctx.get("n1_type", "ego")
    n2_type = ctx.get("n2_type", "vehicle")
    n3_type = ctx.get("n3_type", "object")
    r1_dir  = ctx.get("r1_dir4") or ctx.get("r1_dir8") or "front"
    r2_dir  = ctx.get("r2_dir8") or ctx.get("r2_dir4") or "front"

    # Build constraint qualifier from tighten result
    parts = method_used.split("+")
    qualifiers: List[str] = []
    if tighten_value.get("status") or ("status" in parts):
        v = tighten_value.get("status") or ctx.get("n3_status", "")
        if v: qualifiers.append(v)
    if tighten_value.get("dist") or ("dist_ord" in parts):
        v = tighten_value.get("dist") or tighten_value.get("dist_ord", "")
        if v: qualifiers.append(v)
    qualifiers.append(n3_type)
    constraint_str = " ".join(qualifiers)

    if topology == "L2A":
        # Anchor: start = ego
        return (
            f"What {constraint_str} is to the {r2_dir} of the {n2_type} "
            f"that is to the {r1_dir} of ego?"
        )
    else:
        # Object chain: start = n1 (non-ego)
        n1_label = (n1_id if n1_id.lower().startswith(n1_type.lower())
                    else f"{n1_type} {n1_id}")
        return (
            f"What {constraint_str} is to the {r2_dir} of the {n2_type} "
            f"that is to the {r1_dir} of {n1_label}?"
        )


# =============================================================================
# Per-cell processing (unified for L2A and L2B)
# =============================================================================

def _process_l2_cell(
    cell:       Dict[str, Any],
    topology:   str,           # "L2A" or "L2B"
    llm_client,
    driver,
    chain,                     # CumulativeConstraintChain instance
    scene_name: str,
    frame_idx:  int,
) -> Tuple[List[Dict], Dict]:
    """
    Unified processing for both L2A (ego→A→B) and L2B (A→B→C).
    Returns (qa_list, cell_timing_dict).

    Steps:
      5a  LLM → context Cypher (with interference siblings)
      5b  Neo4j → execute context Cypher
      5d  ConstraintChain.tighten(n3 vs n2's siblings)
      5d.5 Neo4j → Logic_Verification
      5e  Generate chain QA + footprint guard
    """
    path   = cell.get("path_pattern", "?")
    n1, n2, n3 = cell.get("n1_id",""), cell.get("n2_id",""), cell.get("n3_id","")

    t = {
        "path": path, "topology": topology,
        "llm_ms": 0.0, "llm_used": False,
        "token_prompt": 0, "token_completion": 0,
        "neo4j_ms": 0.0, "verify_ms": 0.0, "constraint_ms": 0.0,
        "n_siblings": 0,
        "method_used": "", "is_unique": False, "footprint_ok": False,
        "constraint_trace": "", "logic_verification": "",
        "n_qa": 0,
    }

    _dlog(f"\n{'='*70}")
    _dlog(f"  [{topology}] {path}")
    _dlog(f"  n1={n1}  n2={n2}  n3={n3}")

    # ── Step 5a: LLM context Cypher ──────────────────────────────────────────
    with _measure() as out:
        try:
            if topology == "L2A":
                cypher = llm_client.generate_l2a_context_cypher(cell)
            else:
                cypher = llm_client.generate_l2b_obj_context_cypher(cell)
            t["llm_used"]         = True
            t["token_prompt"]     = llm_client.last_token_usage.get("prompt_tokens", 0)
            t["token_completion"] = llm_client.last_token_usage.get("completion_tokens", 0)
        except Exception as exc:
            logger.warning("[%s] Step5a LLM failed (%s), fallback", topology, exc)
            from gap_pipeline.llm_client import LLMClient as _LC
            cypher = (_LC.build_l2a_fallback_cypher(cell) if topology == "L2A"
                      else _LC.build_l2b_obj_fallback_cypher(cell))
    t["llm_ms"] = out[0]
    _dlog(f"[Step 5a] LLM={t['llm_used']} {t['llm_ms']:.0f}ms  "
          f"prompt={t['token_prompt']} compl={t['token_completion']}")
    _dlog(f"  Cypher (first 200 chars):\n    {cypher[:200].replace(chr(10),' ')}")

    # ── Step 5b: Execute context Cypher ──────────────────────────────────────
    with _measure() as out:
        with driver.session() as sess:
            rec = sess.run(cypher).single()
    t["neo4j_ms"] = out[0]
    if rec is None:
        _dlog(f"[Step 5b] No result! Skipping.")
        return [], t
    ctx = dict(rec)
    sib_ids = ctx.get("sibling_ids", []) or []
    t["n_siblings"] = len(sib_ids)
    _dlog(f"[Step 5b] Neo4j {t['neo4j_ms']:.0f}ms  "
          f"n2={ctx.get('n2_id','?')}({ctx.get('n2_type','?')})  "
          f"n3={ctx.get('n3_id','?')}({ctx.get('n3_type','?')}/{ctx.get('n3_status','?')})  "
          f"siblings={t['n_siblings']}")
    if sib_ids:
        _dlog(f"  Interference siblings: {sib_ids[:10]}{'...' if len(sib_ids)>10 else ''}")

    # ── Step 5d: ConstraintChain.tighten(n3 vs n2's siblings) ────────────────
    candidates = []
    sib_types    = ctx.get("sibling_types",    []) or []
    sib_statuses = ctx.get("sibling_statuses", []) or []
    for i, sid in enumerate(sib_ids):
        if not sid: continue
        candidates.append({
            "id":         sid,
            "tgt_type":   sib_types[i]    if i < len(sib_types)    else "",
            "tgt_status": sib_statuses[i] if i < len(sib_statuses) else "",
            "dir8": "", "dist_level": "", "actual_dist": None, "ego_dir8": "",
        })

    gap_target = {
        "id":         ctx.get("n3_id", n3),
        "tgt_type":   ctx.get("n3_type", ""),
        "tgt_status": ctx.get("n3_status", ""),
        "dir8":       ctx.get("r2_dir8", ""),
        "dist_level": ctx.get("r2_dist", ""),
        "actual_dist": ctx.get("r2_actual_dist"),
        "ego_dir8":   "",
    }
    tvars = {
        "src_id": n1, "src_type": ctx.get("n1_type",""),  "src_status": "",
        "tgt_id": n3, "tgt_type": ctx.get("n3_type",""),  "tgt_status": ctx.get("n3_status",""),
        "dir4": ctx.get("r2_dir4",""), "dir8": ctx.get("r2_dir8",""),
        "dist_level": ctx.get("r2_dist",""),
        "anc_id": n2, "anc_type": ctx.get("n2_type",""),
        "beyond_id": "", "beyond_type": "",
    }
    with _measure() as out:
        tighten = chain.tighten(
            gap_target=gap_target, candidates=candidates, tvars=tvars, ctx={},
        )
    t["constraint_ms"] = out[0]
    t["method_used"]   = tighten.method_used
    t["is_unique"]     = tighten.is_unique
    t["constraint_trace"] = _format_constraint_trace(
        tighten.trace_log, tighten.method_used
    )

    _dlog(f"[Step 5d] ConstraintChain {t['constraint_ms']:.2f}ms  "
          f"method={tighten.method_used}  unique={tighten.is_unique}")
    for item in tighten.trace_log:
        flag = "✅" if item["success"] else "  "
        _dlog(f"    {flag} Try {item['method']:30s} → remaining={item.get('remaining_n','?')}")
    _dlog(f"  Constraint_Trace: {t['constraint_trace']}")

    # ── Step 5d.5: Logic_Verification ───────────────────────────────────────
    vcypher = _build_l2_verify_cypher(
        n1_id=n1, n2_id=n2, n3_id=n3,
        method_used=tighten.method_used,
        tighten_value=tighten.value,
        ctx=ctx,
    )
    with _measure() as out:
        verify_result = _run_verify(driver, vcypher, n3)
    t["verify_ms"] = out[0]
    t["logic_verification"] = verify_result
    _dlog(f"[Step 5d.5] Logic_Verification {t['verify_ms']:.0f}ms: {verify_result}")
    _dlog(f"  Verify Cypher: {vcypher.replace(chr(10), ' ')[:200]}")

    # ── Step 5e: Generate chain QA + footprint guard ─────────────────────────
    question = _render_l2_question(topology, ctx, tighten.method_used, tighten.value)
    answer   = ctx.get("n3_id", n3)

    # Footprint guard: question must mention both middle (n2) and end (n3) types
    n2_type_lower = (ctx.get("n2_type") or "").lower()
    n3_type_lower = (ctx.get("n3_type") or "").lower()
    q_lower = question.lower()
    fp_ok = (n2_type_lower in q_lower) and (n3_type_lower in q_lower)
    t["footprint_ok"] = fp_ok

    footprint_str  = f"{n1}|{n2}|{n3}"  # always 3 nodes
    template_id    = f"{topology}:{tighten.method_used}"

    _dlog(f"[Step 5e] Question: {question}")
    _dlog(f"  Answer: {answer}  footprint_ok={fp_ok}")
    _dlog(f"  Template_ID: {template_id}")

    qa = {
        "question_id":       str(uuid.uuid4())[:8],
        "scene_name":        scene_name,
        "frame_idx":         frame_idx,
        # ── V5 七项指标 ────────────────────────────────────────────────
        "Path_Structure":    path,
        "Topology_Level":    topology,
        "Template_ID":       template_id,
        "Constraint_Trace":  t["constraint_trace"],
        "Token_Prompt":      t["token_prompt"],
        "Token_Completion":  t["token_completion"],
        "Logic_Verification": verify_result,
        "Footprint_Nodes":   footprint_str,
        # ── 其他字段 ───────────────────────────────────────────────────
        "question_type":     "l2a_chain" if topology == "L2A" else "l2b_chain",
        "difficulty":        "hard",
        "question":          question,
        "answer":            answer,
        "answer_type":       "open",
        "reference_objects": [n1, n2],
        "target_objects":    [n3],
        "source":            "L2_chain_v5",
        "topology_level":    topology,
        "path_pattern":      path,
        "footprint_nodes":   [n1, n2, n3],
        "n_interference_siblings": t["n_siblings"],
        "is_unique":         tighten.is_unique,
        "llm_used":          t["llm_used"],
    }
    t["n_qa"] = 1

    if not fp_ok:
        qa["topology_level"] = f"{topology}_degraded"  # don't count as L2
        _dlog("  ⚠ Footprint guard FAILED — degraded (won't count as L2)")

    _dlog(f"{'='*70}")
    return [qa], t


# =============================================================================
# CSV writer (V5 schema)
# =============================================================================

_V5_CSV_FIELDS = [
    "question_id", "scene_name", "frame_idx",
    # 7 mandatory V5 indicators
    "Path_Structure", "Topology_Level", "Template_ID",
    "Constraint_Trace", "Token_Prompt", "Token_Completion",
    "Logic_Verification", "Footprint_Nodes",
    # Extra
    "is_unique", "n_interference_siblings", "llm_used",
    "question", "answer",
]

def _write_v5_csv(qa_pairs: List[Dict], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=_V5_CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(qa_pairs)
    logger.info("V5 CSV written: %d rows → %s", len(qa_pairs), out_path)


# =============================================================================
# Main pipeline
# =============================================================================

def run_v5_pipeline(
    neo4j_uri:   str,
    neo4j_user:  str,
    neo4j_password: str,
    l2a_cells:   int = 25,
    l2b_cells:   int = 25,
    scene_name:  str = "",
    frame_idx:   int = 0,
    output_path: Optional[str] = None,
    csv_path:    Optional[str] = None,
    debug_log:   Optional[str] = None,
) -> Dict[str, Any]:
    global _debug_log_path
    from neo4j import GraphDatabase  # type: ignore[import]
    from gap_pipeline.coverage_tracker import CoverageTracker
    from gap_pipeline.llm_client import LLMClient
    from gap_pipeline.constraint_methods import CumulativeConstraintChain

    # Debug log setup
    if debug_log:
        _debug_log_path = Path(debug_log)
        _debug_log_path.parent.mkdir(parents=True, exist_ok=True)
        _debug_log_path.write_text(
            f"=== V5 Pipeline Debug Log — {time.strftime('%Y-%m-%dT%H:%M:%S')} ===\n"
            f"scene={scene_name}  frame={frame_idx}  L2A={l2a_cells}  L2B={l2b_cells}\n\n",
            encoding="utf-8",
        )

    t_start = time.perf_counter()
    llm    = LLMClient()
    chain  = CumulativeConstraintChain()
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        # ── Init CoverageTracker ──────────────────────────────────────────────
        tracker = CoverageTracker()
        with driver.session() as sess:
            tracker.init_from_session(sess)
        init_stats = tracker.stats()
        logger.info("CoverageTracker: L0=%d L1=%d L2A=%d L2B=%d",
                    init_stats["L0"]["total"], init_stats["L1"]["total"],
                    init_stats["L2A"]["total"], init_stats["L2B"]["total"])

        # ── Extract path gaps ─────────────────────────────────────────────────
        l2a_gaps = tracker.get_gap_cells("L2A", limit=l2a_cells)
        l2b_gaps = tracker.get_gap_cells("L2B", limit=l2b_cells)
        all_gaps = l2a_gaps + l2b_gaps
        logger.info("Gaps: L2A=%d  L2B=%d  total=%d",
                    len(l2a_gaps), len(l2b_gaps), len(all_gaps))

        # ── Per-cell processing ───────────────────────────────────────────────
        all_qa:  List[Dict] = []
        timings: List[Dict] = []
        n_llm = n_fallback = 0

        for i, cell in enumerate(all_gaps, 1):
            topo = cell.get("_level", "?")
            path = cell.get("path_pattern", "?")
            logger.info("  cell %d/%d  [%s]  %s", i, len(all_gaps), topo, path)

            try:
                qa_list, t = _process_l2_cell(
                    cell, topo, llm, driver, chain, scene_name, frame_idx
                )
            except Exception as exc:
                logger.warning("  cell [%s] %s failed: %s", topo, path, exc)
                _dlog(f"  CELL FAILED: {exc}")
                t = {"topology": topo, "path": path, "n_qa": 0,
                     "llm_used": False, "token_prompt": 0, "token_completion": 0,
                     "footprint_ok": False, "is_unique": False,
                     "constraint_trace": "", "logic_verification": "ERR"}
                qa_list = []

            if t.get("llm_used"):
                n_llm += 1
            else:
                n_fallback += 1

            for qa in qa_list:
                if qa["topology_level"] in ("L2A", "L2B"):
                    tracker.record_from_qa(qa)
            all_qa.extend(qa_list)
            timings.append(t)

        # ── Final stats ───────────────────────────────────────────────────────
        final_stats = tracker.stats()
        total_ms    = (time.perf_counter() - t_start) * 1_000
        _print_v5_summary(all_qa, timings, init_stats, final_stats,
                          n_llm, n_fallback, total_ms)

        result = {
            "pipeline_version": "v5",
            "scene_name": scene_name, "frame_idx": frame_idx,
            "n_l2a_cells": len(l2a_gaps), "n_l2b_cells": len(l2b_gaps),
            "n_qa_generated": len(all_qa),
            "n_llm_calls": n_llm, "n_fallback_calls": n_fallback,
            "total_ms": round(total_ms, 1),
            "coverage_init": init_stats, "coverage_final": final_stats,
            "cell_timings": timings, "qa_pairs": all_qa,
        }

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            logger.info("JSON written: %s", out)

        _csv = Path(csv_path) if csv_path else None
        if _csv:
            _write_v5_csv(all_qa, _csv)

        return result

    finally:
        driver.close()


# =============================================================================
# Summary
# =============================================================================

def _print_v5_summary(all_qa, timings, init, final, n_llm, n_fallback, total_ms):
    from collections import Counter
    SEP = "─" * 70
    print(f"\n{SEP}")
    print("  Gap Pipeline V5 — 终极路径覆盖报告")
    print(SEP)

    total_cells = n_llm + n_fallback
    tok_list = [t.get("token_prompt", 0) + t.get("token_completion", 0)
                for t in timings if t.get("llm_used")]
    avg_tok = sum(tok_list) / len(tok_list) if tok_list else 0

    print(f"\n  LLM 调用: {n_llm}/{total_cells}  退回: {n_fallback}  "
          f"平均 token: {avg_tok:.0f}  总耗时: {total_ms:.0f}ms")

    # Constraint method breakdown
    method_cnt = Counter(t.get("method_used","") for t in timings)
    unique_cnt = sum(1 for t in timings if t.get("is_unique"))
    fp_cnt     = sum(1 for t in timings if t.get("footprint_ok"))
    avg_sib    = (sum(t.get("n_siblings",0) for t in timings) /
                  max(len(timings), 1))
    print(f"\n  ConstraintChain: unique={unique_cnt}/{len(timings)}  "
          f"footprint_ok={fp_cnt}/{len(timings)}  avg_siblings={avg_sib:.1f}")
    for m, c in method_cnt.most_common(8):
        print(f"    {m:<35} {c}")

    # Constraint_Trace sample
    print("\n  Logic_Verification 分布:")
    verify_dist = Counter()
    for qa in all_qa:
        v = qa.get("Logic_Verification", "")
        if "✅" in v: verify_dist["✅ n=1 (unique)"] += 1
        elif "❌" in v: verify_dist["❌ n>1 (not unique)"] += 1
        else: verify_dist["?"] += 1
    for k, c in verify_dist.items():
        print(f"    {k:<30} {c}")

    # Coverage
    print(f"\n  覆盖率变化:")
    print(f"  {'Level':5}  {'Before':>8}  {'After':>8}  {'Delta':>7}  Count")
    print(f"  {'─'*45}")
    for lvl in ("L0","L1","L2A","L2B"):
        bi = init.get(lvl,{}).get("rate",0)
        af = final.get(lvl,{}).get("rate",0)
        cv = final.get(lvl,{}).get("covered",0)
        tt = final.get(lvl,{}).get("total",0)
        print(f"  {lvl:5}  {bi:>7.1f}%  {af:>7.1f}%  {af-bi:>+6.1f}%  ({cv}/{tt})")

    print(f"\n  总 QA 对: {len(all_qa)}")
    topo_dist = Counter(qa.get("Topology_Level","?") for qa in all_qa)
    for t, c in topo_dist.most_common():
        print(f"    {t:<20} {c}")
    print(f"\n{SEP}\n")


# =============================================================================
# CLI
# =============================================================================

def _parse_args():
    p = argparse.ArgumentParser(description="Gap Pipeline V5 — 终极路径覆盖")
    p.add_argument("--neo4j-uri",      default="bolt://localhost:7800")
    p.add_argument("--neo4j-user",     default="neo4j")
    p.add_argument("--neo4j-password", default="87017563")
    p.add_argument("--l2a-cells", type=int, default=25)
    p.add_argument("--l2b-cells", type=int, default=25)
    p.add_argument("--scene-name", default="scene-0553")
    p.add_argument("--frame-idx",  type=int, default=8)
    p.add_argument("--output",     default="output/pilot_50paths_v5.json")
    p.add_argument("--csv",        default="output/rq1_pilot_v5.csv")
    p.add_argument("--debug-log",  default="output/pipeline_debug.log")
    p.add_argument("--log-level",  choices=["DEBUG","INFO","WARNING"], default="INFO")
    return p.parse_args()


def main():
    args = _parse_args()
    logging.getLogger().setLevel(args.log_level)
    for noisy in ("neo4j","neo4j.io","neo4j.pool","httpx","urllib3","openai","httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    run_v5_pipeline(
        neo4j_uri=args.neo4j_uri, neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        l2a_cells=args.l2a_cells, l2b_cells=args.l2b_cells,
        scene_name=args.scene_name, frame_idx=args.frame_idx,
        output_path=args.output, csv_path=args.csv, debug_log=args.debug_log,
    )


if __name__ == "__main__":
    main()
