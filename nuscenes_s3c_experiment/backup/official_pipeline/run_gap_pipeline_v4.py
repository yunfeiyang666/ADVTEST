#!/usr/bin/env python3
"""
run_gap_pipeline_v4.py — V4 混合模式：路径缺口 + LLM + ConstraintChain

架构原则（设计底稿 image_4209ea.png）
══════════════════════════════════════
  拓扑即等级（V3 保留）:
    L2 Gap = 图谱中真实的三节点路径，由 Neo4j 路径 Cypher 枚举。
    等级由图谱拓扑决定，与求解策略无关。

  LLM 语义感知（V2 回归）:
    每个 L2 路径缺口都必须调用 LLM：
      L2A: 生成 ego→A→B 路径上下文 Cypher，并返回 A 的干扰项兄弟节点
           — 这些兄弟节点是 ConstraintChain 的压力源，证明 B 不唯一。
      L2B: 生成 X←ego→Y 双臂上下文 Cypher，含对比所需的距离/方向数据。

  ConstraintChain 唯一性验证（V4 新增）:
    L2A: gap_target=B, candidates=A的兄弟节点 → 最简约束组合唯一锁定 B
    L2B: 必须生成比较题（Comparison）：哪个更近/更远/哪个是动的
         — 答案依赖于 X 和 Y 两者，缺一不可。

  物理足迹核验（Footprint Guard）:
    只有当 QA 问题文本逻辑上依赖 3 个节点时，才允许 ΔL2 +1。
    L2A 检验: 问题文本必须同时包含对 A（中间节点）的引用 + B（目标节点）
    L2B 检验: 答案必须依赖 X 和 Y 两者（例如距离比较需要两个距离都已知）

运行示例
─────────
    python run_gap_pipeline_v4.py --l2a-cells 25 --l2b-cells 25 \\
        --scene-name scene-0553 --frame-idx 8 \\
        --output output/pilot_50paths_v4.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid
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
logger = logging.getLogger("run_gap_pipeline_v4")

_DIST_RANK = {"very_close": 0, "close": 1, "medium": 2, "far": 3}


# =============================================================================
# 计时工具
# =============================================================================

@contextmanager
def _measure() -> Generator[list, None, None]:
    buf: list = [0.0]
    t0 = time.perf_counter()
    yield buf
    buf[0] = (time.perf_counter() - t0) * 1_000


# =============================================================================
# 物理足迹核验
# =============================================================================

def _footprint_guard_l2a(question: str, ctx: Dict) -> bool:
    """
    L2A 足迹核验：问题文本必须同时引用：
      - A 节点（中间节点），通过类型名识别
      - B 节点（目标节点），通过类型名识别
    确保 QA 逻辑上依赖路径的两条腿。
    """
    a_type = (ctx.get("n2_type") or "").lower()
    b_type = (ctx.get("n3_type") or "").lower()
    q_lower = question.lower()
    has_a   = bool(a_type) and a_type in q_lower
    has_b   = bool(b_type) and b_type in q_lower
    return has_a and has_b


def _footprint_guard_l2b(answer: str, ctx: Dict) -> bool:
    """
    L2B 足迹核验：答案必须是基于双方比较的结果。
    通过检查 r1_dist ≠ r2_dist（距离比较时）或两者 status 均非空来确认。
    比较题：answer 不为空且是 a_type 或 b_type 之一（回答"哪个更近"时）。
    """
    a_type = (ctx.get("a_type") or "").lower()
    b_type = (ctx.get("b_type") or "").lower()
    ans_lower = str(answer).lower()
    # 答案是其中一方的类型（比较题），说明依赖了两方
    if a_type and b_type and (a_type in ans_lower or b_type in ans_lower):
        return True
    # 或者答案是方向（依赖了 b 的方向信息）
    directions = {"front", "back", "left", "right",
                  "front-left", "front-right", "back-left", "back-right"}
    if ans_lower in directions:
        return True
    # Status 答案："moving"/"stopped" 也依赖属性数据
    if ans_lower in {"moving", "stopped", "parked", "standing"}:
        return True
    return False


# =============================================================================
# L2A 候选集构造（从上下文 Cypher 结果）
# =============================================================================

def _build_l2a_candidates(ctx: Dict) -> List[Dict]:
    """
    从 LLM/fallback Cypher 结果中提取干扰项候选集。
    这是 ConstraintChain 的 candidates 参数。

    候选集 = A 的兄弟节点（A 指向的其他对象，排除 ego 和 B 自身）。
    """
    sibling_ids      = ctx.get("sibling_ids", []) or []
    sibling_types    = ctx.get("sibling_types", []) or []
    sibling_statuses = ctx.get("sibling_statuses", []) or []

    candidates = []
    for i, sid in enumerate(sibling_ids):
        if not sid:
            continue
        candidates.append({
            "id":          sid,
            "tgt_type":    sibling_types[i]    if i < len(sibling_types)    else "",
            "tgt_status":  sibling_statuses[i] if i < len(sibling_statuses) else "",
            # Direction/dist from A to sibling — not stored in parallel arrays;
            # leave blank so ConstraintChain uses type+status+dir8 from gap_target only
            "dir8":        "",
            "dist_level":  "",
            "actual_dist": None,
            "ego_dir8":    "",
        })
    return candidates


def _build_l2a_gap_target(ctx: Dict) -> Dict:
    """Build gap_target dict for ConstraintChain (node B in L2A path)."""
    return {
        "id":          ctx.get("n3_id", ""),
        "tgt_type":    ctx.get("n3_type", ""),
        "tgt_status":  ctx.get("n3_status", ""),
        "dir8":        ctx.get("r2_dir8", ""),
        "dist_level":  ctx.get("r2_dist", ""),
        "actual_dist": ctx.get("r2_actual_dist"),
        "ego_dir8":    "",
    }


# =============================================================================
# L2A QA 生成（ConstraintChain 结果 + 链式问题模板）
# =============================================================================

def _render_l2a_question(ctx: Dict, method_used: str, tighten_value: Dict) -> str:
    """
    生成 L2A 链式问题。问题必须同时引用：
      - 链的第一段: "the {A_type} in/to the {r1_dir4} of ego"
      - 链的第二段: 通过 ConstraintChain 的约束属性定位 B

    格式: "What [constraint] {B_type} is to the {r2_dir8} of the {A_type}
           that is to the {r1_dir4} of ego?"
    """
    a_type  = ctx.get("n2_type",  "vehicle")
    b_type  = ctx.get("n3_type",  "object")
    r1_dir4 = ctx.get("r1_dir4",  "front")
    r2_dir8 = ctx.get("r2_dir8",  "front")

    # Build constraint qualifier from method
    parts = method_used.split("+")
    qualifiers: List[str] = []
    if tighten_value.get("status") or ("status" in parts):
        v = tighten_value.get("status") or ctx.get("n3_status", "")
        if v:
            qualifiers.append(v)
    if tighten_value.get("dist") or ("dist_ord" in parts):
        v = tighten_value.get("dist") or tighten_value.get("dist_ord", "")
        if v:
            qualifiers.append(v)
    # Always include type (B's type) at the end
    qualifiers.append(b_type)
    constraint_str = " ".join(qualifiers)

    # Chain template — explicitly mentions ego→A→B
    question = (
        f"What {constraint_str} is to the {r2_dir8} of the {a_type} "
        f"that is to the {r1_dir4} of ego?"
    )
    return question


def _l2a_answer(ctx: Dict, method_used: str) -> str:
    """Answer is B's unique_id (specific object answer)."""
    return ctx.get("n3_id", ctx.get("n3_type", ""))


# =============================================================================
# L2B 比较题生成（强制比较，禁止并列描述）
# =============================================================================

_DIST_RANK_MAP = {"very_close": 0, "close": 1, "medium": 2, "far": 3}


def _generate_l2b_comparison_qa(
    ctx: Dict,
    scene_name: str,
    frame_idx: int,
    path_pattern: str,
) -> List[Dict]:
    """
    从 L2B 上下文生成必须依赖 X 和 Y 两者的比较题。
    禁止简单并列描述（如"X 在左，Y 在右"）。

    必须生成以下之一：
      1. 距离比较: "Which is closer to ego, the {X_type} or the {Y_type}?"
      2. 状态比较: "Of the {X_type} and {Y_type} visible from ego, which one is moving?"
      3. 方向推断: "Given the {X_type} is to the {r1_dir8} and the {Y_type} to the {r2_dir8},
                   in which direction does ego see the {Y_type}?"  (requires both to contrast)
    """
    qa_list = []

    a_type     = ctx.get("a_type", "object")
    b_type     = ctx.get("b_type", "object")
    a_status   = ctx.get("a_status", "")
    b_status   = ctx.get("b_status", "")
    r1_dir4    = ctx.get("r1_dir4", "")
    r1_dir8    = ctx.get("r1_dir8", "")
    r2_dir4    = ctx.get("r2_dir4", "")
    r2_dir8    = ctx.get("r2_dir8", "")
    r1_dist    = ctx.get("r1_dist", "")
    r2_dist    = ctx.get("r2_dist", "")
    a_id       = ctx.get("a_id", "")
    b_id       = ctx.get("b_id", "")
    ego_id     = ctx.get("ego_id", "ego")

    def _qa(tmpl_id, question, answer, answer_type="open"):
        if not answer:
            return None
        # Footprint guard: answer must depend on both
        if not _footprint_guard_l2b(answer, ctx):
            return None
        return {
            "question_id":     str(uuid.uuid4())[:8],
            "scene_name":      scene_name,
            "frame_idx":       frame_idx,
            "template_id":     tmpl_id,
            "difficulty":      "hard",
            "question_type":   "l2b_chain",
            "question":        question,
            "answer":          answer,
            "answer_type":     answer_type,
            "reference_objects": [ego_id],
            "target_objects":    [a_id, b_id],
            "source":          "L2_chain",
            "topology_level":  "L2B",
            "path_pattern":    path_pattern,
            "footprint_nodes": [a_id, ego_id, b_id],
        }

    # ── 比较 1: 距离比较（需要两个距离均已知且不相等）─────────────────
    r1_rank = _DIST_RANK_MAP.get(r1_dist, -1)
    r2_rank = _DIST_RANK_MAP.get(r2_dist, -1)
    if r1_rank >= 0 and r2_rank >= 0 and r1_rank != r2_rank:
        closer_type  = a_type if r1_rank < r2_rank else b_type
        farther_type = b_type if r1_rank < r2_rank else a_type
        q_closer  = (f"Of the {a_type} to the {r1_dir4} and the {b_type} to the "
                     f"{r2_dir4} of ego, which one is closer?")
        q_farther = (f"Of the {a_type} to the {r1_dir4} and the {b_type} to the "
                     f"{r2_dir4} of ego, which one is farther?")
        if item := _qa("L2B:closer_comparison", q_closer, closer_type):
            qa_list.append(item)
        if item := _qa("L2B:farther_comparison", q_farther, farther_type):
            qa_list.append(item)

    # ── 比较 2: 运动状态比较（两个 status 均已知且不同）──────────────
    if a_status and b_status and a_status != b_status:
        moving_type  = a_type if "moving" in a_status.lower() else (
                       b_type if "moving" in b_status.lower() else "")
        stopped_type = a_type if any(s in a_status.lower() for s in
                                     ("stopped","parked","standing")) else (
                       b_type if any(s in b_status.lower() for s in
                                     ("stopped","parked","standing")) else "")
        if moving_type:
            q = (f"Ego sees a {a_type} to the {r1_dir4} and a {b_type} to the "
                 f"{r2_dir4}. Which one is moving?")
            if item := _qa("L2B:motion_comparison", q, moving_type):
                qa_list.append(item)
        if stopped_type:
            q = (f"Between the {a_type} to the {r1_dir8} and the {b_type} to the "
                 f"{r2_dir8} of ego, which one is stopped?")
            if item := _qa("L2B:stopped_comparison", q, stopped_type):
                qa_list.append(item)

    # ── 比较 3: 方向推断（给定 X 的方向，问 Y 在哪个方向）────────────────
    # 这是"通过 ego 枢纽关联 X 和 Y 的方向"
    if r1_dir8 and r2_dir8 and r1_dir8 != r2_dir8:
        q = (f"Given ego has a {a_type} to its {r1_dir8}, "
             f"in which direction from ego is the {b_type}?")
        if item := _qa("L2B:direction_inference", q, r2_dir8):
            qa_list.append(item)

    # ── 比较 4: 类型对比计数（相同方向上两类对象的存在性推理）──────────
    if r1_dir4 == r2_dir4 and a_type != b_type:
        q = (f"To the {r1_dir4} of ego, is the {a_type} or the {b_type} "
             f"at a closer distance?")
        if r1_rank >= 0 and r2_rank >= 0 and r1_rank != r2_rank:
            ans = a_type if r1_rank < r2_rank else b_type
            if item := _qa("L2B:same_dir_closer", q, ans):
                qa_list.append(item)

    logger.debug("L2B %s → %d comparison QAs", path_pattern, len(qa_list))
    return qa_list


# =============================================================================
# Per-cell processing: L2A
# =============================================================================

def _process_l2a_cell(
    cell:        Dict[str, Any],
    llm_client,
    driver,
    cumul_chain,
    scene_name:  str,
    frame_idx:   int,
) -> Tuple[List[Dict], Dict]:
    """
    处理单个 L2A 路径缺口：LLM 上下文 + ConstraintChain 唯一性验证 + 足迹核验。
    返回 (qa_list, timing_dict)。
    """
    path    = cell.get("path_pattern", "?")
    n1, n2, n3 = cell.get("n1_id","ego"), cell.get("n2_id",""), cell.get("n3_id","")
    timing  = {"path": path, "topology": "L2A",
               "llm_ms": 0.0, "llm_used": False, "llm_tokens": 0,
               "neo4j_ms": 0.0, "constraint_ms": 0.0, "n_siblings": 0,
               "method_used": "", "is_unique": False, "footprint_ok": False,
               "n_qa": 0}

    # ── Step 5a: LLM context Cypher ──────────────────────────────────────────
    with _measure() as out:
        try:
            cypher = llm_client.generate_l2a_context_cypher(cell)
            timing["llm_used"]   = True
            timing["llm_tokens"] = llm_client.last_token_usage.get("total_tokens", 0)
        except Exception as exc:
            logger.warning("L2A Step5a LLM failed (%s), using fallback", exc)
            from gap_pipeline.llm_client import LLMClient as _LC
            cypher = _LC.build_l2a_fallback_cypher(cell)
    timing["llm_ms"] = out[0]
    logger.debug("Step5a L2A [%s] %.1fms used_llm=%s", path, out[0], timing["llm_used"])

    # ── Step 5b: Execute context Cypher ──────────────────────────────────────
    ctx: Optional[Dict] = None
    with _measure() as out:
        with driver.session() as sess:
            rec = sess.run(cypher).single()
    timing["neo4j_ms"] = out[0]
    if rec is None:
        logger.warning("L2A Step5b no result for %s", path)
        return [], timing
    ctx = dict(rec)
    timing["n_siblings"] = len(ctx.get("sibling_ids", []) or [])
    logger.debug("Step5b L2A [%s] %.1fms  siblings=%d", path, out[0], timing["n_siblings"])

    # ── Step 5d: ConstraintChain.tighten(B vs A's siblings) ──────────────────
    candidates = _build_l2a_candidates(ctx)
    gap_target = _build_l2a_gap_target(ctx)
    tvars = {
        "src_id":    n1,        "src_type":   "ego",       "src_status": "",
        "tgt_id":    n3,        "tgt_type":   ctx.get("n3_type",""),
        "tgt_status": ctx.get("n3_status",""),
        "dir4":      ctx.get("r2_dir4",""),
        "dir8":      ctx.get("r2_dir8",""),
        "dist_level": ctx.get("r2_dist",""),
        "anc_id":    n2,        "anc_type":   ctx.get("n2_type",""),
        "beyond_id":  "",       "beyond_type": "",
    }
    with _measure() as out:
        tighten = cumul_chain.tighten(
            gap_target=gap_target,
            candidates=candidates,
            tvars=tvars,
            ctx={},
        )
    timing["constraint_ms"] = out[0]
    timing["method_used"]   = tighten.method_used
    timing["is_unique"]     = tighten.is_unique
    logger.info("  [L2A] %s  siblings=%d  method=%s  unique=%s",
                path, timing["n_siblings"], tighten.method_used, tighten.is_unique)

    # ── Step 5e: Generate chain QA ────────────────────────────────────────────
    question = _render_l2a_question(ctx, tighten.method_used, tighten.value)
    answer   = _l2a_answer(ctx, tighten.method_used)

    # Footprint guard: question must reference BOTH A (middle) and B (target) by type
    fp_ok = _footprint_guard_l2a(question, ctx)
    timing["footprint_ok"] = fp_ok

    if not fp_ok:
        logger.debug("  [L2A] %s footprint guard FAILED — degrading to L1-like", path)
        # Still generate the QA but mark it honestly; record_from_qa won't count L2
        topology = "L2A_degraded"
    else:
        topology = "L2A"

    qa = {
        "question_id":     str(uuid.uuid4())[:8],
        "scene_name":      scene_name,
        "frame_idx":       frame_idx,
        "template_id":     f"L2A:{tighten.method_used}",
        "difficulty":      "hard",
        "question_type":   "l2a_chain",
        "question":        question,
        "answer":          answer,
        "answer_type":     "open",
        "reference_objects": [n1, n2],
        "target_objects":    [n3],
        "source":          "L2_chain",
        "topology_level":  topology,          # "L2A" or "L2A_degraded"
        "path_pattern":    path,
        "footprint_nodes": [n1, n2, n3],
        "path_uniqueness_validated": tighten.is_unique,
        "constraint_method": tighten.method_used,
        "llm_used":        timing["llm_used"],
        "llm_tokens":      timing["llm_tokens"],
        "n_interference_siblings": timing["n_siblings"],
    }
    timing["n_qa"] = 1
    logger.debug("  [L2A] Q: %s", question)
    return [qa], timing


# =============================================================================
# Per-cell processing: L2B
# =============================================================================

def _process_l2b_cell(
    cell:        Dict[str, Any],
    llm_client,
    driver,
    scene_name:  str,
    frame_idx:   int,
) -> Tuple[List[Dict], Dict]:
    """
    处理单个 L2B 路径缺口：LLM 上下文 + 强制比较题 + 足迹核验。
    """
    path   = cell.get("path_pattern", "?")
    a_id   = cell.get("a_id",  "")
    b_id   = cell.get("b_id",  "")
    timing = {"path": path, "topology": "L2B",
              "llm_ms": 0.0, "llm_used": False, "llm_tokens": 0,
              "neo4j_ms": 0.0, "constraint_ms": 0.0,
              "footprint_ok": False, "n_qa": 0}

    # ── Step 5a: LLM context Cypher ──────────────────────────────────────────
    with _measure() as out:
        try:
            cypher = llm_client.generate_l2b_context_cypher(cell)
            timing["llm_used"]   = True
            timing["llm_tokens"] = llm_client.last_token_usage.get("total_tokens", 0)
        except Exception as exc:
            logger.warning("L2B Step5a LLM failed (%s), using fallback", exc)
            from gap_pipeline.llm_client import LLMClient as _LC
            cypher = _LC.build_l2b_fallback_cypher(cell)
    timing["llm_ms"] = out[0]

    # ── Step 5b: Execute context Cypher ──────────────────────────────────────
    with _measure() as out:
        with driver.session() as sess:
            rec = sess.run(cypher).single()
    timing["neo4j_ms"] = out[0]
    if rec is None:
        logger.warning("L2B Step5b no result for %s", path)
        return [], timing
    ctx = dict(rec)
    logger.debug("Step5b L2B [%s] %.1fms", path, out[0])

    # ── Step 5e: Generate comparison QA ─────────────────────────────────────
    qa_list = _generate_l2b_comparison_qa(
        ctx=ctx,
        scene_name=scene_name,
        frame_idx=frame_idx,
        path_pattern=path,
    )
    timing["footprint_ok"] = len(qa_list) > 0
    timing["n_qa"] = len(qa_list)
    logger.info("  [L2B] %s  → %d comparison QAs", path, len(qa_list))
    return qa_list, timing


# =============================================================================
# Main pipeline
# =============================================================================

def run_v4_pipeline(
    neo4j_uri:   str,
    neo4j_user:  str,
    neo4j_password: str,
    l2a_cells:   int = 25,
    l2b_cells:   int = 25,
    scene_name:  str = "",
    frame_idx:   int = 0,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    from neo4j import GraphDatabase  # type: ignore[import]
    from gap_pipeline.coverage_tracker import CoverageTracker
    from gap_pipeline.llm_client import LLMClient
    from gap_pipeline.constraint_methods import CumulativeConstraintChain

    t_start = time.perf_counter()

    logger.info("V4 Pipeline starting: L2A=%d  L2B=%d  scene=%s  frame=%d",
                l2a_cells, l2b_cells, scene_name, frame_idx)

    llm    = LLMClient()
    chain  = CumulativeConstraintChain()
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        # ── Step 1: Init CoverageTracker ──────────────────────────────────────
        tracker = CoverageTracker()
        with driver.session() as sess:
            tracker.init_from_session(sess)
        init_stats = tracker.stats()
        logger.info("Tracker: L0=%d  L1=%d  L2A=%d  L2B=%d",
                    init_stats["L0"]["total"], init_stats["L1"]["total"],
                    init_stats["L2A"]["total"], init_stats["L2B"]["total"])

        # ── Step 2: Extract path gaps ─────────────────────────────────────────
        l2a_gaps = tracker.get_gap_cells("L2A", limit=l2a_cells)
        l2b_gaps = tracker.get_gap_cells("L2B", limit=l2b_cells)
        all_gaps = l2a_gaps + l2b_gaps
        logger.info("Path gaps: L2A=%d  L2B=%d  total=%d",
                    len(l2a_gaps), len(l2b_gaps), len(all_gaps))

        # ── Step 3: Per-cell hybrid processing ───────────────────────────────
        all_qa:   List[Dict] = []
        timings:  List[Dict] = []
        n_llm = n_fallback = 0

        for i, cell in enumerate(all_gaps, 1):
            topo  = cell.get("_level", "?")
            path  = cell.get("path_pattern", "?")
            logger.info("  cell %d/%d  [%s]  %s", i, len(all_gaps), topo, path)

            try:
                if topo == "L2A":
                    qa_list, t = _process_l2a_cell(
                        cell, llm, driver, chain, scene_name, frame_idx
                    )
                else:
                    qa_list, t = _process_l2b_cell(
                        cell, llm, driver, scene_name, frame_idx
                    )
            except Exception as _cell_exc:
                logger.warning("  cell [%s] %s failed: %s", topo, path, _cell_exc)
                t = {"topology": topo, "path": path, "n_qa": 0,
                     "llm_used": False, "llm_tokens": 0, "footprint_ok": False}
                qa_list = []

            if t.get("llm_used"):
                n_llm += 1
            else:
                n_fallback += 1

            # Cascade coverage update
            for qa in qa_list:
                if qa["topology_level"] in ("L2A", "L2B"):
                    tracker.record_from_qa(qa)
            all_qa.extend(qa_list)
            timings.append(t)

        # ── Step 4: Final stats ───────────────────────────────────────────────
        final_stats = tracker.stats()
        total_ms    = (time.perf_counter() - t_start) * 1_000

        _print_v4_summary(all_qa, timings, init_stats, final_stats,
                          n_llm, n_fallback, total_ms)

        result = {
            "pipeline_version":  "v4",
            "scene_name":        scene_name,
            "frame_idx":         frame_idx,
            "n_l2a_cells":       len(l2a_gaps),
            "n_l2b_cells":       len(l2b_gaps),
            "n_qa_generated":    len(all_qa),
            "n_llm_calls":       n_llm,
            "n_fallback_calls":  n_fallback,
            "total_ms":          round(total_ms, 1),
            "coverage_init":     init_stats,
            "coverage_final":    final_stats,
            "cell_timings":      timings,
            "qa_pairs":          all_qa,
        }

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            logger.info("Result written to: %s", out)

        return result

    finally:
        driver.close()


# =============================================================================
# Summary printer
# =============================================================================

def _print_v4_summary(
    all_qa:     List[Dict],
    timings:    List[Dict],
    init:       Dict,
    final:      Dict,
    n_llm:      int,
    n_fallback: int,
    total_ms:   float,
) -> None:
    from collections import Counter
    SEP = "─" * 68

    print(f"\n{SEP}")
    print("  Gap Pipeline V4 — 混合模式（LLM + ConstraintChain + 足迹核验）")
    print(SEP)

    # ── LLM 调用统计 ──────────────────────────────────────────────────────────
    total_cells = n_llm + n_fallback
    tokens_list = [t.get("llm_tokens", 0) for t in timings if t.get("llm_tokens", 0) > 0]
    avg_tok = sum(tokens_list) / len(tokens_list) if tokens_list else 0
    print(f"\n  LLM 调用: 实际={n_llm}/{total_cells}  退回={n_fallback}")
    print(f"  平均 token/call: {avg_tok:.0f}  总耗时: {total_ms:.0f}ms")

    # ── ConstraintChain 方法分布（L2A）────────────────────────────────────────
    l2a_timings = [t for t in timings if t.get("topology") == "L2A"]
    if l2a_timings:
        method_dist   = Counter(t["method_used"] for t in l2a_timings)
        unique_cnt    = sum(1 for t in l2a_timings if t.get("is_unique"))
        footprint_cnt = sum(1 for t in l2a_timings if t.get("footprint_ok"))
        avg_sib = sum(t.get("n_siblings",0) for t in l2a_timings) / len(l2a_timings)
        print(f"\n  L2A ConstraintChain 汇总 (n={len(l2a_timings)}):")
        print(f"  唯一锁定: {unique_cnt}/{len(l2a_timings)}  "
              f"足迹核验通过: {footprint_cnt}/{len(l2a_timings)}  "
              f"平均干扰项数: {avg_sib:.1f}")
        print(f"  {'方法':<35} {'成功次数':>8}")
        print(f"  {'-'*45}")
        for meth, cnt in method_dist.most_common():
            print(f"  {meth:<35} {cnt:>8}")

    # ── L2B 比较题统计 ────────────────────────────────────────────────────────
    l2b_timings = [t for t in timings if t.get("topology") == "L2B"]
    if l2b_timings:
        total_b_qa   = sum(t.get("n_qa", 0) for t in l2b_timings)
        fp_pass      = sum(1 for t in l2b_timings if t.get("footprint_ok"))
        print(f"\n  L2B 比较题 (n={len(l2b_timings)}):")
        print(f"  生成总数: {total_b_qa}  足迹通过: {fp_pass}/{len(l2b_timings)}")
        tmpl_b = Counter(qa.get("template_id","?") for qa in all_qa
                         if qa.get("topology_level","?").startswith("L2B"))
        for t, c in tmpl_b.most_common():
            print(f"    {t:<40} {c:>4}")

    # ── 覆盖率变化 ────────────────────────────────────────────────────────────
    print(f"\n  覆盖率变化:")
    print(f"  {'Level':5}  {'Before':>8}  {'After':>8}  {'Delta':>7}  {'Count'}")
    print(f"  {'─'*50}")
    for lvl in ("L0","L1","L2A","L2B"):
        bi = init.get(lvl,{}).get("rate",0)
        af = final.get(lvl,{}).get("rate",0)
        cv = final.get(lvl,{}).get("covered",0)
        tt = final.get(lvl,{}).get("total",0)
        print(f"  {lvl:5}  {bi:>7.1f}%  {af:>7.1f}%  {af-bi:>+6.1f}%  ({cv}/{tt})")

    # ── QA 样本 ───────────────────────────────────────────────────────────────
    print(f"\n  生成 QA 对总数: {len(all_qa)}")
    qt_cnt = Counter(qa.get("topology_level","?") for qa in all_qa)
    for t, c in qt_cnt.most_common():
        print(f"    {t:<20} {c:>4}")
    print(f"\n{SEP}\n")


# =============================================================================
# CLI
# =============================================================================

def _parse_args():
    p = argparse.ArgumentParser(description="Gap Pipeline V4 — Hybrid LLM+Chain")
    p.add_argument("--neo4j-uri",      default="bolt://localhost:7800")
    p.add_argument("--neo4j-user",     default="neo4j")
    p.add_argument("--neo4j-password", default="87017563")
    p.add_argument("--l2a-cells", type=int, default=25)
    p.add_argument("--l2b-cells", type=int, default=25)
    p.add_argument("--scene-name", default="scene-0553")
    p.add_argument("--frame-idx",  type=int, default=8)
    p.add_argument("--output", default="output/pilot_50paths_v4.json")
    p.add_argument("--log-level", choices=["DEBUG","INFO","WARNING"], default="INFO")
    return p.parse_args()


def main():
    args = _parse_args()
    logging.getLogger().setLevel(args.log_level)
    for noisy in ("neo4j","neo4j.io","neo4j.pool","httpx","urllib3","openai","httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    run_v4_pipeline(
        neo4j_uri=args.neo4j_uri, neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        l2a_cells=args.l2a_cells, l2b_cells=args.l2b_cells,
        scene_name=args.scene_name, frame_idx=args.frame_idx,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
