#!/usr/bin/env python3
"""
run_gap_pipeline_v6.py — V6 性能跃迁版

核心改进
════════
  ① Bug Fix (is_unique 恢复)
       · fallback Cypher 用 collect({id,dir8,dist}) 保留 sibling 空间属性
       · _build_l2_candidates() 把 gap_target 本身放入 candidates 第一位
       · ConstraintChain.tighten() 找到 gap_target 之后 len(remaining)==1 才算唯一

  ② LLM 批处理 (×3-8 吞吐提升)
       · generate_context_cypher_batch() 一次请求覆盖 BATCH_SIZE 条路径
       · 各条独立验证；单条解析失败降级到硬编码 fallback

  ③ 并发执行 (×N_WORKERS 额外提升)
       · ThreadPoolExecutor(N_WORKERS=3) 同时发起多组 batch 请求
       · 跑满 API QPS 限制，总耗时 ≈ 串行 / (BATCH_SIZE × N_WORKERS)

  ④ 智能采样 (覆盖率斜率改善)
       · 全局随机洗牌 → 打破局部遇历导致的冗余
       · priority_sort_gaps() → 接触最多未覆盖节点的路径优先处理

  ⑤ Baseline 集成
       · --baseline-file 加载 NuScenes-QA 原题，增量生成只针对真正缺口

  ⑥ RTT 诊断输出
       · 汇总每次 LLM 调用的 total_ms、tok/s、est_rtt_overhead_ms
       · 给出"瓶颈在 API RTT 还是推理速度"的明确结论

V6 vs V5 耗时对比示例：
  V5 串行   50 cells × 9.8s = 490s
  V6 batch8 + worker3 ≈ 50/(8×3) ≈ 3 批 × 9.8s ≈ 20-30s  (~15x 加速)
"""
from __future__ import annotations

import argparse, csv, json, logging, os, sys, time, uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

try:
    from advtest_env import load_advtest_env

    load_advtest_env()
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_gap_pipeline_v6")

# ── 批处理 / 并发参数（可用环境变量覆盖，利于打满网关并发）──────────────────────
BATCH_SIZE = int(os.getenv("VQA_GAP_BATCH_SIZE", "12"))
N_WORKERS  = int(os.getenv("VQA_GAP_N_WORKERS", "8"))

_debug_log_path: Optional[Path] = None

def _dlog(msg: str) -> None:
    if _debug_log_path:
        with _debug_log_path.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")


@contextmanager
def _measure() -> Generator[list, None, None]:
    buf: list = [0.0]
    t0 = time.perf_counter()
    yield buf
    buf[0] = (time.perf_counter() - t0) * 1_000


# =============================================================================
# Bug Fix: _build_l2_candidates
# =============================================================================

def _build_l2_candidates(
    ctx: Dict, n3: str
) -> Tuple[List[Dict], Dict]:
    """
    V6 关键修复：返回 [gap_target] + siblings 作为 candidates。

    V5 Bug 原因：
      candidates = siblings only（不含 gap_target）
      ConstraintChain 检查 `len(remaining)==1 AND remaining[0].id==gap_target.id`
      但 gap_target 从不在 remaining 里 → 永远 False → is_unique 永远 False

    V6 修复：
      candidates = [gap_target] + siblings
      tighten() 内部: others = [c for c in candidates if c.id != gap_target.id] = siblings
      filter_candidates 对 candidates 过滤 → [gap_target] 如果满足约束
      len==1 AND id matches → is_unique = True ✅

    sibling dir8/dist 由新 fallback Cypher 的 collect({...}) 语法填充。
    """
    sibling_ids      = ctx.get("sibling_ids",      []) or []
    sibling_types    = ctx.get("sibling_types",    []) or []
    sibling_statuses = ctx.get("sibling_statuses", []) or []
    sibling_dir8s    = ctx.get("sibling_dir8s",    []) or []   # ← V6 新增
    sibling_dists    = ctx.get("sibling_dists",    []) or []   # ← V6 新增
    sibling_actual_dists = ctx.get("sibling_actual_dists", []) or []  # ← V7
    sibling_txs      = ctx.get("sibling_txs",      []) or []  # ← V7
    sibling_tys      = ctx.get("sibling_tys",      []) or []  # ← V7
    sibling_degrees  = ctx.get("sibling_degrees",  []) or []  # ← V7

    # gap_target：路径终点节点（含其相对于中间节点的方向属性）
    gap_target = {
        "id":          ctx.get("n3_id", n3),
        "tgt_type":    ctx.get("n3_type", ""),
        "tgt_status":  ctx.get("n3_status", ""),
        "dir8":        ctx.get("r2_dir8", ""),      # ← n2→n3 方向
        "dist_level":  ctx.get("r2_dist", ""),
        "actual_dist": ctx.get("r2_actual_dist"),
        "ego_dir8":    "",
        "tx":          ctx.get("n3_tx"),             # ← V7 translation
        "ty":          ctx.get("n3_ty"),             # ← V7
        "degree":      ctx.get("n3_degree"),         # ← V7 连接度
    }

    # siblings：中间节点的其他邻居（干扰项），现在带有 dir8/dist
    siblings = []
    for i, sid in enumerate(sibling_ids):
        if not sid:
            continue
        siblings.append({
            "id":          sid,
            "tgt_type":    sibling_types[i]    if i < len(sibling_types)    else "",
            "tgt_status":  sibling_statuses[i] if i < len(sibling_statuses) else "",
            "dir8":        sibling_dir8s[i]    if i < len(sibling_dir8s)    else "",  # ← FIX
            "dist_level":  "",
            "actual_dist": (sibling_actual_dists[i] if i < len(sibling_actual_dists)
                            else (sibling_dists[i] if i < len(sibling_dists) else None)),
            "ego_dir8":    "",
            "tx":          sibling_txs[i]      if i < len(sibling_txs)      else None,  # ← V7
            "ty":          sibling_tys[i]      if i < len(sibling_tys)      else None,  # ← V7
            "degree":      sibling_degrees[i]  if i < len(sibling_degrees)  else None,  # ← V7
        })

    # ← 核心修复：gap_target 放第一位，tighten() 会把它识别为目标
    candidates = [gap_target] + siblings
    return candidates, gap_target


# =============================================================================
# Constraint Trace + Logic Verify (reused from V5)
# =============================================================================

def _format_trace(trace_log: list, method_used: str) -> str:
    parts = ["Path"]
    for item in trace_log:
        flag = "S" if item["success"] else "F"
        n    = item.get("remaining_n", "?")
        parts.append(f"{item['method']}({flag},{n})")
    if not trace_log and method_used:
        parts.append(f"{method_used}(S,1)")
    return "→".join(parts)


def _build_verify_cypher(
    n1: str, n2: str, n3: str,
    method_used: str,
    tighten_value: Dict,
    ctx: Dict,
    tighten_referent_ids: str = "",
) -> str:
    def _esc(v: str) -> str:
        return str(v or "").replace("'", "\\'")
    conditions: List[str] = []
    parts = set(method_used.split("+"))
    is_two_hop_method = ("two_hop" in method_used)
    is_dual_hop_method = ("dual_hop" in method_used)
    is_referent_method = is_two_hop_method or is_dual_hop_method

    _ref_map = {
        str(r.get("ref_id") or "").strip(): r
        for r in (ctx.get("referents", []) or [])
        if str(r.get("ref_id") or "").strip()
    }
    needs_dist_rank = (
        "dist_ord" in parts
        or "dist_rank" in parts
        or method_used in ("dist_order", "ordinal_by_distance", "dist_rank")
    )

    # type
    needs_type = (
        "type" in parts
        or method_used
        in (
            "type_filter",
            "type_status_anchor",
            "type_dist_combo",
            "type_dir8_dist_combo",
            "all_props_combo",
            "dist_order",
            "ordinal_by_distance",
        )
        or needs_dist_rank
        or "degree" in parts       # V7: degree 需要 type 过滤
        or "quadrant" in parts     # V7: quadrant 需要 type 过滤
        or "dist_rank" in parts    # V7: dist_rank 需要 type 过滤
    )
    if needs_type:
        v = tighten_value.get("type") or ctx.get("n3_type", "")
        if v:
            conditions.append(f"c.type = '{_esc(v)}'")
    if is_referent_method and "type" not in parts:
        v = tighten_value.get("tgt_type") or ctx.get("n3_type", "")
        if v:
            conditions.append(f"c.type = '{_esc(v)}'")
    # status
    if "status" in parts or method_used in (
        "status_anchor",
        "type_status_anchor",
        "all_props_combo",
    ):
        v = tighten_value.get("status") or ctx.get("n3_status", "")
        if v:
            conditions.append(f"coalesce(c.status,'') = '{_esc(v)}'")
    # dir8（dist 序验证：仅当 tighten 值里显式含 dir8 或 method 需要八向时再加，避免 type+dist_ord 误用 ctx 单角）
    _dir8_from_method = method_used in (
        "dir8_refine",
        "type_dir8_dist_combo",
        "all_props_combo",
    )
    if "dir8" in parts or _dir8_from_method or (
        needs_dist_rank and tighten_value.get("dir8")
    ):
        v = tighten_value.get("dir8") or ctx.get("r2_dir8", "")
        if v:
            conditions.append(f"r2.direction_8 = '{_esc(v)}'")
    # 精确距离档位（TypeDistCombo / TypeDir8DistCombo / all_props 的 dist 字段为 near/mid/far 等）
    dv = tighten_value.get("dist")
    if (not is_referent_method) and dv and str(dv) not in ("closest", "farthest"):
        dv_s = str(dv).replace("'", "\\'")
        conditions.append(f"trim(coalesce(r2.predicates[1],'')) = '{dv_s}'")
    extra_matches: List[str] = []
    extra_conditions: List[str] = []
    ref_ids_from_result = [x for x in str(tighten_referent_ids or "").split("|") if x]

    # ── V7: degree 约束 ──
    # degree 验证通过子查询 EXISTS 实现
    _degree_val = None
    if "degree" in parts or method_used == "degree":
        _degree_val = tighten_value.get("degree")

    # ── V7: quadrant 约束（不加 Cypher 条件，靠 type 过滤 + count 验证） ──

    if is_dual_hop_method:
        ref1_id = (
            str(tighten_value.get("ref1_id") or "").strip()
            or (ref_ids_from_result[0] if len(ref_ids_from_result) >= 1 else "")
        )
        ref2_id = (
            str(tighten_value.get("ref2_id") or "").strip()
            or (ref_ids_from_result[1] if len(ref_ids_from_result) >= 2 else "")
        )
        if ref1_id:
            extra_matches.append(
                f"MATCH (ref1:Object {{unique_id:'{_esc(ref1_id)}'}})-[ref_r1:RELATES_TO]->(c:Object)"
            )
            ref1_dir = (
                tighten_value.get("ref1_dir8")
                or (_ref_map.get(ref1_id, {}) or {}).get("dir8")
                or ""
            )
            if ref1_dir:
                extra_conditions.append(f"ref_r1.direction_8 = '{_esc(ref1_dir)}'")
        if ref2_id:
            extra_matches.append(
                f"MATCH (ref2:Object {{unique_id:'{_esc(ref2_id)}'}})-[ref_r2:RELATES_TO]->(c:Object)"
            )
            ref2_dir = (
                tighten_value.get("ref2_dir8")
                or (_ref_map.get(ref2_id, {}) or {}).get("dir8")
                or ""
            )
            if ref2_dir:
                extra_conditions.append(f"ref_r2.direction_8 = '{_esc(ref2_dir)}'")
    elif is_two_hop_method:
        ref_id = (
            str(tighten_value.get("ref_id") or "").strip()
            or (ref_ids_from_result[0] if ref_ids_from_result else "")
        )
        if ref_id:
            extra_matches.append(
                f"MATCH (ref:Object {{unique_id:'{_esc(ref_id)}'}})-[ref_r:RELATES_TO]->(c:Object)"
            )
            ref_dir = (
                tighten_value.get("ref_dir8")
                or tighten_value.get("dir8")
                or (_ref_map.get(ref_id, {}) or {}).get("dir8")
                or ""
            )
            if ref_dir:
                extra_conditions.append(f"ref_r.direction_8 = '{_esc(ref_dir)}'")

    where_terms = conditions + extra_conditions
    where = " AND ".join(where_terms) if where_terms else "true"

    # 用有向 a->b->c 保持 direction_8 与 context candidates 的参考系一致。
    # 旧版无向匹配会同时命中 b->c 和 c->b 两条边，导致 ids=['x','x'] 重复和 dir8 错配。
    base_match = (
        f"MATCH (a:Object {{unique_id:'{_esc(n1)}'}})-[:RELATES_TO]->(b:Object {{unique_id:'{_esc(n2)}'}})"
        f"-[r2:RELATES_TO]->(c:Object)"
    )
    match_block = "\n".join([base_match, *extra_matches])

    # ── V7: dist_rank / dist_ord 验证 ──
    # nearest/farthest/2nd-nearest/2nd-farthest 需要 ORDER BY + SKIP/LIMIT
    _dist_rank_label = None
    if "dist_rank" in parts or method_used == "dist_rank":
        _dist_rank_label = tighten_value.get("dist_rank") or tighten_value.get("label")
    # dist_ord 也用 ORDER BY 验证（修复旧 bug：之前只 count 不验证排序）
    if not _dist_rank_label and ("dist_ord" in parts or needs_dist_rank):
        v = tighten_value.get("dist_ord") or tighten_value.get("dist", "")
        if v in ("closest", "nearest"):
            _dist_rank_label = "nearest"
        elif v in ("farthest",):
            _dist_rank_label = "farthest"

    if _dist_rank_label:
        # 用 ORDER BY + collect 取排序后的第 N 个
        if _dist_rank_label == "nearest":
            return (
                f"{match_block}\nWHERE {where}\n"
                f"WITH c, r2.distance AS d ORDER BY d ASC\n"
                f"WITH collect(c.unique_id) AS sorted_ids\n"
                f"RETURN CASE WHEN size(sorted_ids) >= 1 THEN 1 ELSE 0 END AS n, "
                f"CASE WHEN size(sorted_ids) >= 1 THEN [sorted_ids[0]] ELSE [] END AS ids"
            )
        elif _dist_rank_label == "farthest":
            return (
                f"{match_block}\nWHERE {where}\n"
                f"WITH c, r2.distance AS d ORDER BY d DESC\n"
                f"WITH collect(c.unique_id) AS sorted_ids\n"
                f"RETURN CASE WHEN size(sorted_ids) >= 1 THEN 1 ELSE 0 END AS n, "
                f"CASE WHEN size(sorted_ids) >= 1 THEN [sorted_ids[0]] ELSE [] END AS ids"
            )
        elif _dist_rank_label == "second nearest":
            return (
                f"{match_block}\nWHERE {where}\n"
                f"WITH c, r2.distance AS d ORDER BY d ASC\n"
                f"WITH collect(c.unique_id) AS sorted_ids\n"
                f"RETURN CASE WHEN size(sorted_ids) >= 2 THEN 1 ELSE 0 END AS n, "
                f"CASE WHEN size(sorted_ids) >= 2 THEN [sorted_ids[1]] ELSE [] END AS ids"
            )
        elif _dist_rank_label == "second farthest":
            return (
                f"{match_block}\nWHERE {where}\n"
                f"WITH c, r2.distance AS d ORDER BY d DESC\n"
                f"WITH collect(c.unique_id) AS sorted_ids\n"
                f"RETURN CASE WHEN size(sorted_ids) >= 2 THEN 1 ELSE 0 END AS n, "
                f"CASE WHEN size(sorted_ids) >= 2 THEN [sorted_ids[1]] ELSE [] END AS ids"
            )

    # ── V7: degree 约束用 WITH 子句过滤 ──
    if _degree_val is not None:
        return (
            f"{match_block}\nWHERE {where}\n"
            f"WITH DISTINCT c\n"
            f"OPTIONAL MATCH (c)-[:RELATES_TO]-(deg_neighbor:Object)\n"
            f"WITH c, count(DISTINCT deg_neighbor) AS deg\n"
            f"WHERE deg = {int(_degree_val)}\n"
            f"RETURN count(DISTINCT c) AS n, collect(DISTINCT c.unique_id) AS ids"
        )

    # ── V7: quadrant 约束用坐标象限过滤 ──
    _quadrant = None
    if "quadrant" in parts:
        _quadrant = tighten_value.get("quadrant")
    if _quadrant:
        # 解析象限 → 坐标条件（相对于 n2）
        q_conds = []
        if "front" in _quadrant:
            q_conds.append(f"c.translation_y >= b.translation_y")
        elif "rear" in _quadrant:
            q_conds.append(f"c.translation_y < b.translation_y")
        if "right" in _quadrant:
            q_conds.append(f"c.translation_x >= b.translation_x")
        elif "left" in _quadrant:
            q_conds.append(f"c.translation_x < b.translation_x")
        if q_conds:
            q_where = " AND ".join(q_conds)
            full_where = f"{where} AND {q_where}" if where != "true" else q_where
            return (
                f"{match_block}\nWHERE {full_where}\n"
                f"RETURN count(DISTINCT c) AS n, collect(DISTINCT c.unique_id) AS ids"
            )

    return (
        f"{match_block}\nWHERE {where}\n"
        f"RETURN count(DISTINCT c) AS n, collect(DISTINCT c.unique_id) AS ids"
    )


def _run_verify(driver, vcypher: str, tgt_id: str) -> str:
    try:
        with driver.session() as sess:
            rec = sess.run(vcypher).single()
        if rec:
            raw_ids = [x for x in list(rec.get("ids", [])) if x is not None]
            ids = sorted(set(raw_ids))
            # 以 distinct ids 为准，防止双向边/多路径造成重复计数。
            n = len(ids)
            ok = (n == 1 and tgt_id in ids)
            return f"n={n} {'✅' if ok else '❌'} ids={ids[:5]}"
        return "n=0 ❌"
    except Exception as exc:
        return f"ERR:{exc}"


# =============================================================================
# Question rendering (reused from V5)
# =============================================================================

def _render_l2_question(topology: str, ctx: Dict,
                        method_used: str, tighten_value: Dict) -> str:
    n1_id   = ctx.get("n1_id",  "ego")
    n1_type = ctx.get("n1_type", "ego")
    n2_type = ctx.get("n2_type", "vehicle")
    n3_type = ctx.get("n3_type", "object")
    r1_dir  = ctx.get("r1_dir4") or ctx.get("r1_dir8") or "front"
    r2_dir  = ctx.get("r2_dir8") or ctx.get("r2_dir4") or "front"

    parts = method_used.split("+")

    # ── V7: degree 约束 → 特殊模板 ──
    if "degree" in parts:
        deg = tighten_value.get("degree", "?")
        n2_ref = _l2_n2_ref(n1_id, n1_type, n2_type, r1_dir)
        return (f"Which {n3_type} near {n2_ref} is connected "
                f"to exactly {deg} objects?")

    # ── V7: quadrant 约束 → 特殊模板 ──
    if "quadrant" in parts:
        q = tighten_value.get("quadrant", "?")
        n2_ref = _l2_n2_ref(n1_id, n1_type, n2_type, r1_dir)
        return (f"What is the {n3_type} in the {q} area "
                f"relative to {n2_ref}?")

    qualifiers: List[str] = []
    if tighten_value.get("status") or "status" in parts:
        v = tighten_value.get("status") or ctx.get("n3_status","")
        if v: qualifiers.append(v)
    if tighten_value.get("dist") or "dist_ord" in parts:
        v = tighten_value.get("dist") or tighten_value.get("dist_ord","")
        if v: qualifiers.append(v)
    # V7: dist_rank
    if "dist_rank" in parts:
        v = tighten_value.get("dist_rank") or tighten_value.get("label","")
        if v: qualifiers.append(v)
    qualifiers.append(n3_type)
    constraint_str = " ".join(qualifiers)

    if n1_id == "ego" or n1_type.lower() == "ego":
        return (f"What {constraint_str} is to the {r2_dir} of the {n2_type} "
                f"that is to the {r1_dir} of ego?")
    else:
        n1_label = (n1_id if n1_id.lower().startswith(n1_type.lower())
                    else f"{n1_type} {n1_id}")
        return (f"What {constraint_str} is to the {r2_dir} of the {n2_type} "
                f"that is to the {r1_dir} of {n1_label}?")


def _l2_n2_ref(n1_id, n1_type, n2_type, r1_dir):
    """生成 L2 问题中对 n2 的引用描述。"""
    if n1_id == "ego" or n1_type.lower() == "ego":
        return f"the {n2_type} to the {r1_dir} of ego"
    n1_label = (n1_id if n1_id.lower().startswith(n1_type.lower())
                else f"{n1_type} {n1_id}")
    return f"the {n2_type} to the {r1_dir} of {n1_label}"


# =============================================================================
# Per-cell processor (V6: uses fixed candidates)
# =============================================================================

def _process_single_cell(
    cell:       Dict,
    topology:   str,
    cypher:     str,   # already generated (batch or fallback)
    driver,
    chain,
    scene_name: str,
    frame_idx:  int,
    llm_timing: Dict,   # {total_ms, tok_per_sec, est_rtt_overhead_ms}
    render_local_question: bool = True,
) -> Tuple[Optional[Dict], Dict]:
    """
    Execute context Cypher → ConstraintChain → Verify → QA.
    Returns (qa_dict_or_None, timing_dict).
    """
    path   = cell.get("path_pattern", "?")
    n1, n2, n3 = cell.get("n1_id",""), cell.get("n2_id",""), cell.get("n3_id","")

    t = {
        "path": path, "topology": topology,
        "llm_ms":          llm_timing.get("total_ms", 0.0),
        "tok_per_sec":     llm_timing.get("tok_per_sec", 0.0),
        "est_rtt_ms":      llm_timing.get("est_rtt_overhead_ms", 0.0),
        "neo4j_ms": 0.0, "verify_ms": 0.0, "constraint_ms": 0.0,
        "n_siblings": 0,
        "method_used": "", "is_unique": False, "footprint_ok": False,
        "constraint_trace": "", "logic_verification": "",
        "timestamp_cypher_return": "",
        "n_qa": 0,
    }


    # V26: L2 context 强制使用硬编码有向 fallback。
    # 旧流程会优先执行 LLM 生成 Cypher；只要返回一行就不会 fallback，
    # 但 LLM Cypher 常使用无向匹配，导致 siblings/dir8 与 verify 参考系不一致。
    # 为保证“约束链 candidates”和“verify Cypher”语义完全对齐，L2 一律使用 fallback。
    if n1 and n2 and n3:
        from gap_pipeline.llm_client import LLMClient as _LC
        cypher = _LC.build_l2_fallback_cypher(cell)

    # Step 5b: Execute context Cypher
    # V15.1: 如果 LLM 生成的 Cypher 有语法错误，自动降级到硬编码 fallback
    # V25: 语法合法但 0 行时此前会直接放弃；补一层 fallback（与 SyntaxError 路径共用模板）
    attempted_syntax_fallback = False
    with _measure() as out:
        rec = None
        try:
            with driver.session() as sess:
                rec = sess.run(cypher).single()
                # V18 [物理采样点-timestamp_cypher_return]：紧跟 single() 之后
                t["timestamp_cypher_return"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        except Exception as cypher_err:
            _err_msg = str(cypher_err)
            if "SyntaxError" in _err_msg or "not defined" in _err_msg:
                logger.info(
                    "Cypher SyntaxError (%s...), retrying with hardcoded fallback",
                    _err_msg[:80]
                )
                attempted_syntax_fallback = True
                # 使用统一的 L2 fallback Cypher
                from gap_pipeline.llm_client import LLMClient as _LC
                _fb = _LC.build_l2_fallback_cypher(cell)
                try:
                    with driver.session() as sess2:
                        rec = sess2.run(_fb).single()
                        # fallback 成功时同样记录物理返回时刻
                        t["timestamp_cypher_return"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                except Exception as fb_err:
                    logger.warning("Fallback Cypher also failed: %s", fb_err)
                    rec = None
            else:
                raise  # 非 Cypher 语法错误，向上抛出
    t["neo4j_ms"] = out[0]
    if rec is None and not attempted_syntax_fallback:
        from gap_pipeline.llm_client import LLMClient as _LC0
        _fb0 = _LC0.build_l2_fallback_cypher(cell)
        if cypher.strip() != _fb0.strip():
            logger.info(
                "Context Cypher 返回 0 行（语法合法但无匹配），降级硬编码 fallback topology=%s path=%s",
                topology,
                path,
            )
            try:
                with _measure() as out_z:
                    with driver.session() as _sess_z:
                        rec = _sess_z.run(_fb0).single()
                        if rec is not None:
                            t["timestamp_cypher_return"] = datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S.%f"
                            )[:-3]
                t["neo4j_ms"] += out_z[0]
            except Exception as _z_err:
                logger.warning("0-row fallback Cypher failed: %s", _z_err)
                rec = None
    if rec is None:
        return None, t
    ctx = dict(rec)
    sib_ids = ctx.get("sibling_ids", []) or []
    t["n_siblings"] = len(sib_ids)

    # LLM 生成的 context Cypher 常「语法合法但 RETURN 缺 sibling_ids」→ candidates 只剩
    # gap_target → tighten 误走 no_constraint_needed，而 verify 仍数 b 的全邻居(n=6)。
    if not sib_ids:
        logger.warning(
            "Context Cypher returned empty sibling_ids (likely LLM schema drift); "
            "retrying with hardcoded L2 fallback"
        )
        from gap_pipeline.llm_client import LLMClient as _LC_fb
        _fb = _LC_fb.build_l2_fallback_cypher(cell)
        try:
            with _measure() as out_fb:
                with driver.session() as _sess_fb:
                    _rec_fb = _sess_fb.run(_fb).single()
                    if _rec_fb is not None:
                        t["timestamp_cypher_return"] = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S.%f"
                        )[:-3]
                        ctx = dict(_rec_fb)
                        sib_ids = ctx.get("sibling_ids", []) or []
                        t["n_siblings"] = len(sib_ids)
            t["neo4j_ms"] += out_fb[0]
        except Exception as _sib_fb_err:
            logger.warning("Hardcoded sibling fallback failed: %s", _sib_fb_err)

    _dlog(f"\n[{topology}] {path}")
    _dlog(f"  siblings={t['n_siblings']}  "
          f"n3={ctx.get('n3_id','?')}({ctx.get('n3_type','?')}/{ctx.get('n3_status','?')})")
    if sib_ids:
        _dlog(f"  dir8s: {(ctx.get('sibling_dir8s',[]) or [])[:5]}")

    # Step 5d: ConstraintChain (V6 fixed candidates)
    candidates, gap_target = _build_l2_candidates(ctx, n3)
    # P5b：与 V5 一致的二跳 referent 批量查询（含 sibling_cnt / sibling_ids），供 P11/P14
    ctx["src_status"] = ctx.get("n1_status", "")
    _tid = (n3 or str(ctx.get("n3_id") or "")).strip()
    _mid = (n2 or str(ctx.get("n2_id") or "")).strip()
    _ttp = str(ctx.get("n3_type") or "").strip()
    with _measure() as out_ref:
        if _tid and _mid and _ttp:
            try:
                from run_gap_pipeline import _fetch_referents as _fetch_referents_v5

                with driver.session() as _sess_r:
                    ctx["referents"] = _fetch_referents_v5(
                        _sess_r, tgt_id=_tid, src_id=_mid, tgt_type=_ttp
                    )
            except Exception as _ref_exc:
                logger.warning("referent prefetch failed: %s", _ref_exc)
                ctx["referents"] = []
        else:
            ctx["referents"] = []
    t["neo4j_ms"] += out_ref[0]

    tvars = {
        "src_id": n1, "src_type": ctx.get("n1_type",""), "src_status": "",
        "tgt_id": n3, "tgt_type": ctx.get("n3_type",""), "tgt_status": ctx.get("n3_status",""),
        "dir4": ctx.get("r2_dir4",""), "dir8": ctx.get("r2_dir8",""),
        "dist_level": ctx.get("r2_dist",""),
        "anc_id": n2, "anc_type": ctx.get("n2_type",""),
        "beyond_id": "", "beyond_type": "",
    }
    with _measure() as out:
        tighten = chain.tighten(
            gap_target=gap_target, candidates=candidates, tvars=tvars, ctx=ctx,
        )
    t["constraint_ms"] = out[0]
    t["method_used"]   = tighten.method_used
    t["is_unique"]     = tighten.is_unique
    t["referent_ids"]  = getattr(tighten, "referent_ids", "")
    t["constraint_trace"] = _format_trace(tighten.trace_log, tighten.method_used)
    # V24: 真实约束搜索深度 = trace_log 条数；无尝试且唯一（如 no_constraint_needed）记为 1
    _n_try = len(tighten.trace_log)
    t["constraint_rounds"] = _n_try if _n_try > 0 else 1

    _dlog(f"  ConstraintChain: method={tighten.method_used}  unique={tighten.is_unique}")
    _dlog(f"  Trace: {t['constraint_trace']}")

    # Step 5d.5: Logic Verification
    vcypher = _build_verify_cypher(
        n1,
        n2,
        n3,
        tighten.method_used,
        tighten.value,
        ctx,
        tighten_referent_ids=t.get("referent_ids", ""),
    )
    with _measure() as out:
        verify_result = _run_verify(driver, vcypher, n3)
    t["verify_ms"]          = out[0]
    t["logic_verification"] = verify_result
    t["verify_cypher"]      = vcypher          # V12: expose for cypher_question column
    _dlog(f"  Verify: {verify_result}")

    # Step 5e: Generate QA
    question = (_render_l2_question(topology, ctx, tighten.method_used, tighten.value)
                if render_local_question else "")
    answer   = ctx.get("n3_id", n3)
    if render_local_question:
        n2_lower = (ctx.get("n2_type") or "").lower()
        n3_lower = (ctx.get("n3_type") or "").lower()
        fp_ok    = (n2_lower in question.lower()) and (n3_lower in question.lower())
    else:
        fp_ok = True
    t["footprint_ok"] = fp_ok
    t["n_qa"] = 1

    qa = {
        "question_id":   str(uuid.uuid4())[:8],
        "scene_name":    scene_name,
        "frame_idx":     frame_idx,
        "Path_Structure":    path,
        "Topology_Level":    topology if fp_ok else f"{topology}_degraded",
        "Template_ID":       f"{topology}:{tighten.method_used}",
        "Constraint_Trace":  t["constraint_trace"],
        "Token_Prompt":      0,   # filled by caller from batch
        "Token_Completion":  0,   # filled by caller from batch
        "Logic_Verification": verify_result,
        "Footprint_Nodes":   f"{n1}|{n2}|{n3}",
        "is_unique":         tighten.is_unique,
        "n_interference_siblings": t["n_siblings"],
        "question":          question,
        "answer":            answer,
        "answer_type":       "open",
        "topology_level":    topology if fp_ok else f"{topology}_degraded",
        "path_pattern":      path,
        "footprint_nodes":   [n1, n2, n3],
        # 新增：用于覆盖记录的额外信息
        "_candidates":       candidates,
        "_ctx":              ctx,
    }
    _dlog(f"  Q: {question}  A: {answer}  fp_ok={fp_ok}")
    return qa, t


# =============================================================================
# Batch group processor (runs in one thread)
# =============================================================================

def _process_batch_group(
    cells:      List[Dict],
    topology:   str,
    llm_client,
    driver,
    chain,
    scene_name: str,
    frame_idx:  int,
) -> Tuple[List[Dict], List[Dict]]:
    """
    One batch group: single LLM call → N Neo4j executions → N QA pairs.
    """
    # Step 5a: batch LLM call
    t_llm0 = time.perf_counter()
    cyphers = llm_client.generate_context_cypher_batch(cells, topology=topology)
    t_llm1 = time.perf_counter()
    batch_llm_ms = (t_llm1 - t_llm0) * 1000

    # Distribute token usage equally across cells in the batch
    batch_tokens   = llm_client.last_token_usage
    per_cell_pmt   = batch_tokens.get("prompt_tokens", 0) // max(len(cells), 1)
    per_cell_comp  = batch_tokens.get("completion_tokens", 0) // max(len(cells), 1)
    per_cell_llm_ms = batch_llm_ms / max(len(cells), 1)

    llm_timing = llm_client.last_call_timing  # {total_ms, tok_per_sec, est_rtt_overhead_ms}

    all_qa: List[Dict] = []
    timings: List[Dict] = []

    for i, (cell, cypher) in enumerate(zip(cells, cyphers)):
        qa, t = _process_single_cell(
            cell=cell, topology=topology, cypher=cypher,
            driver=driver, chain=chain,
            scene_name=scene_name, frame_idx=frame_idx,
            llm_timing={"total_ms": per_cell_llm_ms,
                        "tok_per_sec": llm_timing.get("tok_per_sec", 0),
                        "est_rtt_overhead_ms": llm_timing.get("est_rtt_overhead_ms", 0)},
        )
        if qa is not None:
            qa["Token_Prompt"]     = per_cell_pmt
            qa["Token_Completion"] = per_cell_comp
            all_qa.append(qa)
        timings.append(t)

    return all_qa, timings


# =============================================================================
# CSV schema (V6 = V5 + llm_ms + tok_per_sec)
# =============================================================================

_V6_CSV_FIELDS = [
    "question_id", "scene_name", "frame_idx",
    "Path_Structure", "Topology_Level", "Template_ID",
    "Constraint_Trace", "Token_Prompt", "Token_Completion",
    "Logic_Verification", "Footprint_Nodes",
    "is_unique", "n_interference_siblings",
    "question", "answer",
]


# =============================================================================
# Main pipeline
# =============================================================================

def run_v6_pipeline(
    neo4j_uri:     str,
    neo4j_user:    str,
    neo4j_password:str,
    l2a_cells:     int = 25,
    l2b_cells:     int = 25,
    scene_name:    str = "",
    frame_idx:     int = 0,
    output_path:   Optional[str] = None,
    csv_path:      Optional[str] = None,
    debug_log:     Optional[str] = None,
    baseline_file: Optional[str] = None,
    batch_size:    int = BATCH_SIZE,
    n_workers:     int = N_WORKERS,
) -> Dict[str, Any]:
    global _debug_log_path
    from neo4j import GraphDatabase  # type: ignore[import]
    from gap_pipeline.coverage_tracker import CoverageTracker
    from gap_pipeline.llm_client import LLMClient
    from gap_pipeline.constraint_methods import CumulativeConstraintChain

    if debug_log:
        _debug_log_path = Path(debug_log)
        _debug_log_path.parent.mkdir(parents=True, exist_ok=True)
        _debug_log_path.write_text(
            f"=== V6 Debug Log — {time.strftime('%Y-%m-%dT%H:%M:%S')} ===\n"
            f"batch_size={batch_size}  n_workers={n_workers}\n\n",
            encoding="utf-8",
        )

    t_start = time.perf_counter()
    llm    = LLMClient()
    chain  = CumulativeConstraintChain()
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        # ── Step 1: Init tracker ──────────────────────────────────────────────
        tracker = CoverageTracker()
        with driver.session() as sess:
            tracker.init_from_session(sess)
        logger.info("Tracker: L0=%d L1=%d L2=%d",
                    tracker.stats()["L0"]["total"], tracker.stats()["L1"]["total"],
                    tracker.stats()["L2"]["total"])

        # ── Step 1b: Baseline (optional) ─────────────────────────────────────
        if baseline_file:
            base_stats = tracker.load_nuscenes_qa_baseline(baseline_file, scene_name)
            logger.info("Baseline: %s", base_stats)

        # ── Step 2: Extract + priority-based selection ───────────────────────
        # 使用新的优先级选择策略
        total_l2_needed = l2a_cells + l2b_cells
        selected = tracker.select_gaps_with_priority("L2", top_k=total_l2_needed, adaptive=True)
        if not selected:
            logger.warning("No L2 gaps available")
            return {}

        # 转换为旧格式的gap列表
        l2_gaps = [gap_dict for gap_key, gap_dict, priority in selected]
        avg_priority = sum(p for _, _, p in selected) / len(selected) if selected else 0
        logger.info("Gaps after priority selection: L2=%d (avg priority=%.1f)",
                   len(l2_gaps), avg_priority)
        logger.info("Priority range: min=%.1f, max=%.1f",
                   min(p for _, _, p in selected) if selected else 0,
                   max(p for _, _, p in selected) if selected else 0)


        # ── Step 3: Split into batch groups ──────────────────────────────────
        def _chunks(lst, n):
            for i in range(0, len(lst), n):
                yield lst[i:i+n]

        l2_batches = [(chunk, "L2") for chunk in _chunks(l2_gaps, batch_size)]
        all_batches = l2_batches
        logger.info("Batch groups: %d  (batch_size=%d  workers=%d)",
                    len(all_batches), batch_size, n_workers)

        init_stats = tracker.stats()

        # ── Step 4: Parallel batch execution ─────────────────────────────────
        all_qa:   List[Dict] = []
        timings:  List[Dict] = []

        t_v5_equiv_start = time.perf_counter()

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = {
                executor.submit(
                    _process_batch_group,
                    cells, topology, llm, driver, chain, scene_name, frame_idx,
                ): (cells, topology)
                for cells, topology in all_batches
            }
            for future in as_completed(futures):
                cells, topology = futures[future]
                try:
                    qa_list, t_list = future.result()
                except Exception as exc:
                    logger.warning("Batch [%s, %d cells] failed: %s",
                                   topology, len(cells), exc)
                    qa_list, t_list = [], []

                # Cascade coverage update (with candidates and ctx)
                for qa in qa_list:
                    if qa.get("topology_level") in ("L2", "L2A", "L2B"):
                        # 使用新的覆盖记录方法，包含candidates和ctx
                        candidates = qa.pop("_candidates", [])
                        ctx = qa.pop("_ctx", None)
                        if candidates:
                            tracker.record_from_qa_with_candidates(qa, candidates, ctx)
                        else:
                            tracker.record_from_qa(qa)
                all_qa.extend(qa_list)
                timings.extend(t_list)
                logger.info("  Batch done [%s×%d] → %d QAs",
                            topology, len(cells), len(qa_list))

        t_wall = (time.perf_counter() - t_v5_equiv_start) * 1000
        total_ms = (time.perf_counter() - t_start) * 1000

        # ── Summary ───────────────────────────────────────────────────────────
        final_stats = tracker.stats()
        v5_equiv_serial = sum(t.get("llm_ms", 0) for t in timings)  # if serial
        speedup = v5_equiv_serial / max(t_wall, 1)

        _print_v6_summary(all_qa, timings, init_stats, final_stats,
                          total_ms, t_wall, v5_equiv_serial, speedup,
                          batch_size, n_workers)

        result = {
            "pipeline_version": "v6",
            "scene_name": scene_name, "frame_idx": frame_idx,
            "n_l2_cells": len(l2_gaps),
            "n_qa_generated": len(all_qa),
            "total_ms": round(total_ms, 1),
            "wall_ms":  round(t_wall, 1),
            "v5_equiv_serial_ms": round(v5_equiv_serial, 1),
            "speedup_x": round(speedup, 1),
            "coverage_init":  init_stats,
            "coverage_final": final_stats,
            "cell_timings": timings,
            "qa_pairs": all_qa,
        }

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            logger.info("JSON → %s", out)

        if csv_path:
            _csv = Path(csv_path)
            with _csv.open("w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=_V6_CSV_FIELDS, extrasaction="ignore")
                w.writeheader(); w.writerows(all_qa)
            logger.info("CSV  → %s", _csv)

        return result

    finally:
        driver.close()


# =============================================================================
# Quality Check
# =============================================================================

def check_question_quality(qa_pairs: List[Dict]) -> Dict[str, Any]:
    """
    检查生成问题的质量

    Returns:
        {
            "total": int,
            "unique_answers": int,
            "avg_question_length": float,
            "template_distribution": Dict[str, int],
            "topology_distribution": Dict[str, int],
            "issues": List[str]
        }
    """
    if not qa_pairs:
        return {"total": 0, "issues": ["No QA pairs to check"]}

    issues = []
    answers = set()
    question_lengths = []
    template_counts = {}
    topology_counts = {}

    for qa in qa_pairs:
        # 检查必需字段
        if not qa.get("question"):
            issues.append(f"Missing question in QA {qa.get('question_id')}")
        if not qa.get("answer"):
            issues.append(f"Missing answer in QA {qa.get('question_id')}")

        # 统计
        answers.add(qa.get("answer", ""))
        question_lengths.append(len(qa.get("question", "")))

        template = qa.get("Template_ID", "unknown")
        template_counts[template] = template_counts.get(template, 0) + 1

        topology = qa.get("Topology_Level", "unknown")
        topology_counts[topology] = topology_counts.get(topology, 0) + 1

        # 检查问题长度
        q_len = len(qa.get("question", ""))
        if q_len < 10:
            issues.append(f"Question too short ({q_len} chars): {qa.get('question_id')}")
        elif q_len > 500:
            issues.append(f"Question too long ({q_len} chars): {qa.get('question_id')}")

    return {
        "total": len(qa_pairs),
        "unique_answers": len(answers),
        "avg_question_length": sum(question_lengths) / len(question_lengths) if question_lengths else 0,
        "template_distribution": template_counts,
        "topology_distribution": topology_counts,
        "issues": issues
    }


# =============================================================================
# Summary
# =============================================================================

def _print_v6_summary(all_qa, timings, init, final,
                      total_ms, wall_ms, v5_serial, speedup,
                      batch_size, n_workers) -> None:
    from collections import Counter
    SEP = "─" * 70
    print(f"\n{SEP}")
    print("  Gap Pipeline V6 — 性能诊断 + 覆盖率报告")
    print(SEP)

    # ── RTT 诊断 ─────────────────────────────────────────────────────────────
    llm_ms_list = [t.get("llm_ms", 0) for t in timings if t.get("llm_ms", 0) > 0]
    tok_ps_list  = [t.get("tok_per_sec", 0) for t in timings if t.get("tok_per_sec", 0) > 0]
    rtt_list     = [t.get("est_rtt_ms", 0) for t in timings if t.get("est_rtt_ms", 0) > 0]

    avg_llm    = sum(llm_ms_list) / len(llm_ms_list)   if llm_ms_list  else 0
    avg_tokps  = sum(tok_ps_list) / len(tok_ps_list)    if tok_ps_list  else 0
    avg_rtt    = sum(rtt_list)    / len(rtt_list)        if rtt_list     else 0
    rtt_pct    = avg_rtt / max(avg_llm, 1) * 100

    print(f"\n  ── RTT 诊断 ─────────────────────────────────────────────────")
    print(f"  每 cell 分摊 LLM 耗时 : {avg_llm:.0f} ms  (batch={batch_size}×workers={n_workers})")
    print(f"  推理速度              : {avg_tokps:.0f} tok/s")
    print(f"  估算 RTT 占比         : {rtt_pct:.0f}%  ({avg_rtt:.0f}ms / {avg_llm:.0f}ms)")
    if rtt_pct > 70:
        print("  ⚠  RTT 主导 → 换更近节点或提高并发")
    else:
        print("  ✅ 推理主导 → 精简 Prompt 或换 7B 小模型可进一步提速")

    # ── 性能对比 ─────────────────────────────────────────────────────────────
    print(f"\n  ── V5 vs V6 耗时对比 ─────────────────────────────────────────")
    print(f"  V5 串行估算  : {v5_serial/1000:.0f}s  ({len(timings)} cells × {v5_serial/max(len(timings),1)/1000:.0f}s)")
    print(f"  V6 实际耗时  : {wall_ms/1000:.0f}s   (wall clock, batch+parallel)")
    print(f"  加速比       : {speedup:.1f}×")

    # ── is_unique 恢复验证 ────────────────────────────────────────────────────
    unique_cnt = sum(1 for t in timings if t.get("is_unique"))
    fp_cnt     = sum(1 for t in timings if t.get("footprint_ok"))
    print(f"\n  ── Bug 修复验证 ─────────────────────────────────────────────")
    print(f"  is_unique: {unique_cnt}/{len(timings)}")
    print(f"  footprint_ok: {fp_cnt}/{len(timings)}")

    verify_ok = sum(1 for qa in all_qa if "✅" in qa.get("Logic_Verification",""))
    print(f"  Logic_Verification n=1: {verify_ok}/{len(all_qa)}")

    # ── 约束方法分布 ─────────────────────────────────────────────────────────
    method_cnt = Counter(t.get("method_used","") for t in timings)
    print(f"\n  ConstraintChain 方法:")
    for m, c in method_cnt.most_common(8):
        print(f"    {m:<35} {c}")

    # ── 覆盖率 ───────────────────────────────────────────────────────────────
    print(f"\n  覆盖率变化:")
    print(f"  {'Level':5}  {'Before':>8}  {'After':>8}  {'Δ':>7}  Count")
    print(f"  {'─'*45}")
    for lvl in ("L0","L1","L2"):
        bi = init.get(lvl,{}).get("rate",0)
        af = final.get(lvl,{}).get("rate",0)
        cv = final.get(lvl,{}).get("covered",0)
        tt = final.get(lvl,{}).get("total",0)
        print(f"  {lvl:5}  {bi:>7.2f}%  {af:>7.2f}%  {af-bi:>+6.3f}%  ({cv}/{tt})")

    # ── 质量检查 ─────────────────────────────────────────────────────────────
    quality = check_question_quality(all_qa)
    print(f"\n  ── 质量检查 ─────────────────────────────────────────────────")
    print(f"  总问题数         : {quality['total']}")
    print(f"  唯一答案数       : {quality['unique_answers']}")
    print(f"  平均问题长度     : {quality['avg_question_length']:.1f} 字符")

    if quality.get('issues'):
        print(f"  质量问题         : {len(quality['issues'])} 个")
        for issue in quality['issues'][:5]:  # 只显示前5个
            print(f"    - {issue}")
        if len(quality['issues']) > 5:
            print(f"    ... 还有 {len(quality['issues']) - 5} 个问题")
    else:
        print(f"  质量问题         : 无")

    print(f"\n  Total QA: {len(all_qa)}  |  总耗时: {total_ms/1000:.0f}s")
    print(f"\n{SEP}\n")


# =============================================================================
# CLI
# =============================================================================

def _parse_args():
    p = argparse.ArgumentParser(description="Gap Pipeline V6 — 批处理 + 并发 + 智能采样")
    p.add_argument("--neo4j-uri",      default="bolt://localhost:7687")
    p.add_argument("--neo4j-user",     default="neo4j")
    p.add_argument("--neo4j-password", default="87017563")
    p.add_argument("--l2a-cells",  type=int, default=25)
    p.add_argument("--l2b-cells",  type=int, default=25)
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                   help=f"LLM 每次打包路径数 (default={BATCH_SIZE})")
    p.add_argument("--workers",    type=int, default=N_WORKERS,
                   help=f"并发 API 请求数 (default={N_WORKERS})")
    p.add_argument("--scene-name", default="scene-0553")
    p.add_argument("--frame-idx",  type=int, default=8)
    p.add_argument("--output",     default="output/pilot_50paths_v6.json")
    p.add_argument("--csv",        default="output/rq1_pilot_v6.csv")
    p.add_argument("--debug-log",  default="output/pipeline_debug_v6.log")
    p.add_argument("--baseline-file", default=None,
                   help="NuScenes-QA 原题 JSON，加载后跳过已覆盖路径")
    p.add_argument("--log-level", choices=["DEBUG","INFO","WARNING"], default="INFO")
    return p.parse_args()


def main():
    args = _parse_args()
    logging.getLogger().setLevel(args.log_level)
    for noisy in ("neo4j","neo4j.io","neo4j.pool","httpx","urllib3","openai","httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    run_v6_pipeline(
        neo4j_uri=args.neo4j_uri, neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        l2a_cells=args.l2a_cells, l2b_cells=args.l2b_cells,
        scene_name=args.scene_name, frame_idx=args.frame_idx,
        output_path=args.output, csv_path=args.csv,
        debug_log=args.debug_log,
        baseline_file=args.baseline_file,
        batch_size=args.batch_size, n_workers=args.workers,
    )


if __name__ == "__main__":
    main()
