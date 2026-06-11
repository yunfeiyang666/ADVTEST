#!/usr/bin/env python3
"""Gap Pipeline 主运行脚本 — 全流程计时

每个环节均使用 time.perf_counter() 记录精确耗时（ms），重点计时：
    ConstraintChain.tighten()（约束收束步骤 / 限定环节）

流水线步骤
----------
  0. 连接初始化（Neo4j + LLM）
  1. scene_llm       LLM 生成场景枚举 Cypher
  2. scene_neo4j     Neo4j 执行场景枚举，获取全量有向边
  3. cmap_init       CoverageMap 初始化
  4. gap_detect      识别 gap cells（未覆盖边）

  每个 gap cell（循环）：
  5a. ctx_llm        LLM 生成上下文 Cypher
  5b. ctx_neo4j      Neo4j 执行上下文查询
  5c. cand_neo4j     Neo4j 查询同向候选集（常态执行）+ referent 批量查询（constraint 模式）
  5d. constraint     ConstraintChain.tighten()  ←  重点计时
  5e. template_fill  模板选择 + 填空 + 答案解析

  6. cmap_update     CoverageMap 批量更新

输出
----
  - 控制台: 每步汇总表（ms），per-cell 平均/最大/最小/p95
  - JSON:   --output 指定路径（默认不写出）

Usage (在 core_pipeline 目录下运行)
-------------------------------------
    python run_gap_pipeline.py
    python run_gap_pipeline.py --max-cells 20 --use-constraint-chain
    python run_gap_pipeline.py --output output/gap_timing.json
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

# ── 确保 core_pipeline 在路径中 ──────────────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

# ── 日志设置 ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_gap_pipeline")


# =============================================================================
# 计时工具
# =============================================================================

class _CellTiming:
    """存储单个 gap cell 的各子步耗时（ms）。"""

    __slots__ = (
        "cell_id",          # 'src_id→tgt_id'
        "ctx_llm_ms",       # Step 5a  LLM 生成上下文 Cypher
        "ctx_llm_used_llm", # Step 5a  是否实际调用了 LLM（fallback 时为 False）
        "ctx_neo4j_ms",     # Step 5b
        "cand_neo4j_ms",    # Step 5c (仅 constraint chain 模式)
        "constraint_ms",    # Step 5d (仅 constraint chain 模式)
        "template_fill_ms", # Step 5e
        "total_ms",         # 以上之和
        "n_qa",             # 本 cell 生成的 QA 对数
        "method_used",      # constraint chain 使用的约束方法
        "is_unique",        # 约束结果是否唯一
        "method_timings",   # Dict[str, float]  逐方法计时结果
        # ―― RQ1 新字段 ――――――――――――――――――――――
        "constraint_trace_str",  # 'type(F,0.02ms)->two_hop(S,22.7ms)'
        "n_failed_attempts",     # int: 失败尝试次数
        "llm_token_prompt",      # int: LLM prompt tokens
        "llm_token_completion",  # int: LLM completion tokens
        "llm_cypher_depth",      # int: Cypher 中 MATCH 关键词数量
        "n_candidates",          # int: Step 5c 候选集大小
    )

    def __init__(self, cell_id: str) -> None:
        self.cell_id = cell_id
        self.ctx_llm_ms       = 0.0
        self.ctx_llm_used_llm = False
        self.ctx_neo4j_ms     = 0.0
        self.cand_neo4j_ms    = 0.0
        self.constraint_ms    = 0.0
        self.template_fill_ms = 0.0
        self.total_ms         = 0.0
        self.n_qa             = 0
        self.method_used      = ""
        self.is_unique        = False
        self.method_timings: Dict[str, float] = {}
        self.constraint_trace_str = ""
        self.n_failed_attempts    = 0
        self.llm_token_prompt     = 0
        self.llm_token_completion = 0
        self.llm_cypher_depth     = 0
        self.n_candidates         = 0

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.__slots__}

    @property
    def _slot_keys(self):
        return self.__slots__


@contextmanager
def _measure() -> Generator[list, None, None]:
    """用法: with _measure() as out: ...  → out[0] = 耗时 ms"""
    buf: list = [0.0]
    t0 = time.perf_counter()
    yield buf
    buf[0] = (time.perf_counter() - t0) * 1_000


def _percentile(data: List[float], p: int) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = (len(s) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _agg(vals: List[float]) -> Dict[str, float]:
    if not vals:
        return {"n": 0, "mean": 0.0, "max": 0.0, "min": 0.0, "p95": 0.0, "total": 0.0}
    return {
        "n":     len(vals),
        "mean":  round(sum(vals) / len(vals), 2),
        "max":   round(max(vals), 2),
        "min":   round(min(vals), 2),
        "p95":   round(_percentile(vals, 95), 2),
        "total": round(sum(vals), 2),
    }


# =============================================================================
# 验证 Cypher 生成器（Python 确定性生成，非 LLM）
# =============================================================================

def _build_verify_cypher(
    method_used: str,
    tvars: Dict[str, Any],
    gap_target: Dict[str, Any],
    tighten_value: Dict[str, Any],
) -> Optional[str]:
    """根据约束方法和属性值生成验证 Cypher。

    返回的 Cypher 运行后应该恒返回：
        n=1  AND  ids=[<tgt_id>]   → 验证通过 ✅
        n>1  OR   ids!=[<tgt_id>]  → 验证失败 ❗

    谁来写这个 Cypher？
        本函数是一个确定性的 Python 生成器，它将约束链选择的属性
        （type / status / dir8 / referent 等）直接转化为 WHERE 子句。
        不使用 LLM，不需要额外网络请求。
    """
    src_id  = tvars.get("src_id", "")
    dir4    = tvars.get("dir4", "")
    parts   = set(method_used.split("+"))

    # ――― 双二跳 referent：两个参照交集唯一 ―――――――――――――――――――――――
    if "dual_hop" in method_used or method_used == "dual_hop_referent":
        ref1_id  = tighten_value.get("ref1_id", "")
        ref1_dir = tighten_value.get("ref1_dir8", "")
        ref2_id  = tighten_value.get("ref2_id", "")
        ref2_dir = tighten_value.get("ref2_dir8", "")
        tgt_type = gap_target.get("tgt_type", "")
        type_cond = f"\n  AND tgt.type = '{tgt_type}'" if tgt_type else ""
        return (
            f"-- Step 5d.5 验证 Cypher (双二跳交集，Python 生成)\n"
            f"MATCH (ref1:Object {{unique_id: '{ref1_id}'}})-[r1:RELATES_TO]->(tgt:Object)\n"
            f"WHERE r1.direction_8 = '{ref1_dir}'{type_cond}\n"
            f"WITH collect(tgt.unique_id) AS ids1\n"
            f"MATCH (ref2:Object {{unique_id: '{ref2_id}'}})-[r2:RELATES_TO]->(tgt2:Object)\n"
            f"WHERE r2.direction_8 = '{ref2_dir}'{type_cond.replace('tgt','tgt2')}\n"
            f"WITH ids1, collect(tgt2.unique_id) AS ids2\n"
            f"WITH [x IN ids1 WHERE x IN ids2] AS intersection\n"
            f"RETURN size(intersection) AS n, intersection AS ids"
        )

    # ――― 单二跳 referent 类方法 ―――――――――――――――――――――――――――――――
    if "two_hop" in method_used or method_used in ("two_hop_referent",):
        ref_id  = tighten_value.get("ref_id", "")
        ref_dir = tighten_value.get("dir8", "")
        tgt_type = tighten_value.get("tgt_type", gap_target.get("tgt_type", ""))
        # 属性维度修饰词（type+two_hop 时）
        attr_cond = ""
        if "type" in parts and tighten_value.get("type"):
            attr_cond = f"\n  AND tgt.type = '{tighten_value['type']}'"
        elif tgt_type:
            attr_cond = f"\n  AND tgt.type = '{tgt_type}'"
        dir_cond = f"\n  AND r.direction_8 = '{ref_dir}'" if ref_dir else ""
        return (
            f"-- Step 5d.5 验证 Cypher (由 Python 生成，不经 LLM)\n"
            f"MATCH (ref:Object {{unique_id: '{ref_id}'}})"
            f"-[r:RELATES_TO]->(tgt:Object)\n"
            f"WHERE ref.unique_id IS NOT NULL{dir_cond}{attr_cond}\n"
            f"RETURN count(tgt) AS n, collect(tgt.unique_id) AS ids"
        )

    # ――― 属性组合类方法 ――――――――――――――――――――――――――――――――
    conditions: List[str] = []
    if dir4:
        conditions.append(f"r.direction_4 = '{dir4}'")

    # type
    if "type" in parts or method_used in ("type_filter", "type_status_anchor",
                                          "type_dist_combo", "type_dir8_dist_combo",
                                          "all_props_combo"):
        v = tighten_value.get("type") or gap_target.get("tgt_type", "")
        if v:
            conditions.append(f"tgt.type = '{v}'")

    # status
    if "status" in parts or method_used in ("status_anchor", "type_status_anchor",
                                            "all_props_combo"):
        v = tighten_value.get("status") or gap_target.get("tgt_status", "")
        if v:
            conditions.append(f"coalesce(tgt.status,'') = '{v}'")

    # dir8
    if "dir8" in parts or method_used in ("dir8_refine", "type_dir8_dist_combo",
                                          "all_props_combo"):
        v = tighten_value.get("dir8") or gap_target.get("dir8", "")
        if v:
            conditions.append(f"r.direction_8 = '{v}'")

    # dist_ord / ordinal: 用距离排序远似验证
    if "dist_ord" in parts or method_used in ("ordinal_by_distance", "dist_order"):
        order = tighten_value.get("dist_ord") or tighten_value.get("order", "closest")
        order_sql = "ASC" if order == "closest" else "DESC"
        where = "\n  AND ".join(conditions) if conditions else "true"
        return (
            f"-- Step 5d.5 验证 Cypher (排序类，Python 生成)\n"
            f"MATCH (src:Object {{unique_id: '{src_id}'}})-[r:RELATES_TO]->(tgt:Object)\n"
            f"WHERE {where}\n"
            f"RETURN tgt.unique_id AS id, r.distance AS dist\n"
            f"ORDER BY r.distance {order_sql} LIMIT 3"
        )

    if not conditions:
        return None

    where = "\n  AND ".join(conditions)
    return (
        f"-- Step 5d.5 验证 Cypher (属性类，Python 生成)\n"
        f"MATCH (src:Object {{unique_id: '{src_id}'}})-[r:RELATES_TO]->(tgt:Object)\n"
        f"WHERE {where}\n"
        f"RETURN count(tgt) AS n, collect(tgt.unique_id) AS ids"
    )


# =============================================================================
# 候选集查询（固定 Cypher，不经 LLM）
# =============================================================================

# 从 src 出发，查询同 dir4 方向的全部候选节点（ConstraintChain 单跳层用）
_CANDIDATES_CYPHER = """
MATCH (src:Object {unique_id: $src_id})-[r:RELATES_TO]->(tgt:Object)
WHERE r.direction_4 = $dir4
OPTIONAL MATCH (:Object {unique_id: 'ego'})-[ego_r:RELATES_TO]->(tgt)
RETURN
    tgt.unique_id                    AS id,
    tgt.type                         AS tgt_type,
    coalesce(tgt.status, '')         AS tgt_status,
    r.direction_8                    AS dir8,
    coalesce(r.predicates[1], '')    AS dist_level,
    r.distance                       AS actual_dist,
    coalesce(ego_r.direction_8, '')  AS ego_dir8
"""

# 批量获取指向 gap_target 的 referent，按 sibling_cnt 升序排列（二跳约束用）
_REFERENT_BATCH_CYPHER = """
MATCH (ref:Object)-[r:RELATES_TO]->(tgt:Object {unique_id: $tgt_id})
WHERE ref.unique_id <> $src_id
OPTIONAL MATCH (:Object {unique_id: 'ego'})-[ego_r:RELATES_TO]->(ref)
WITH ref, r, coalesce(ego_r.direction_8, '') AS ref_ego_dir8
MATCH (ref)-[r2:RELATES_TO]->(sibling:Object {type: $tgt_type})
WHERE r2.direction_8 = r.direction_8
WITH ref, r, ref_ego_dir8, count(sibling) AS sibling_cnt,
     [x IN collect(sibling.unique_id) | x] AS sibling_ids
RETURN ref.unique_id AS ref_id, ref.type AS ref_type,
       r.direction_8 AS dir8, coalesce(r.predicates[1],'') AS dist,
       ref_ego_dir8, sibling_cnt, sibling_ids
ORDER BY sibling_cnt ASC
LIMIT 10
"""


def _fetch_candidates(session, src_id: str, dir4: str) -> List[Dict[str, Any]]:
    """从 Neo4j 查询同方向（dir4）的全部候选对象。"""
    result = session.run(_CANDIDATES_CYPHER, src_id=src_id, dir4=dir4)
    return [dict(rec) for rec in result]


def _fetch_referents(
    session, tgt_id: str, src_id: str, tgt_type: str
) -> List[Dict[str, Any]]:
    """批量获取指向 gap_target 的 referent，按唔一性升序。
    每条含: ref_id, ref_type, dir8, dist, sibling_cnt, sibling_ids
    """
    result = session.run(
        _REFERENT_BATCH_CYPHER,
        tgt_id=tgt_id, src_id=src_id, tgt_type=tgt_type,
    )
    return [dict(rec) for rec in result]


# =============================================================================
# 核心 per-cell 处理（带计时）
# =============================================================================

def _process_cell_timed(
    cell: Dict[str, Any],
    llm_client,
    driver,
    use_constraint_chain: bool,
    constraint_chain,          # ConstraintChain 实例，仅在 use_constraint_chain=True 时使用
    max_per_cell: int,
    scene_name: str,
    frame_idx: int,
) -> tuple[List[Dict[str, Any]], _CellTiming]:
    """处理单个 gap cell，返回 (qa_list, timing)。"""
    from gap_pipeline.gap_templates import (
        TEMPLATE_META,
        get_applicable_templates,
        pick_variation,
        resolve_answer,
    )

    from gap_pipeline.constraint_methods import _ref_label as _ref_label_fn
    src_id = cell.get("src_id", "?")
    tgt_id = cell.get("tgt_id", "?")
    timing = _CellTiming(f"{src_id}→{tgt_id}")

    # ── Step 5a: LLM 生成上下文 Cypher（实际调用大模型，失败时退回硬编码）────
    with _measure() as out:
        from gap_pipeline.llm_client import LLMClient as _LC
        try:
            cypher = llm_client.generate_gap_context_cypher(cell)
            timing.ctx_llm_used_llm = True
        except Exception as _llm_exc:
            logger.warning(
                "Step 5a LLM 失败（%s），退回硬编码 Cypher", _llm_exc
            )
            cypher = _LC.build_gap_context_cypher(src_id, tgt_id)
            timing.ctx_llm_used_llm = False
    timing.ctx_llm_ms = out[0]
    # RQ1: 单次 token 用量 + Cypher 复杂度
    if timing.ctx_llm_used_llm:
        u = llm_client.last_token_usage
        timing.llm_token_prompt     = u.get("prompt_tokens", 0)
        timing.llm_token_completion = u.get("completion_tokens", 0)
    timing.llm_cypher_depth = cypher.upper().count("MATCH")
    logger.debug(
        "Step 5a  ctx_llm  %.1f ms  used_llm=%s  tokens=%d+%d  depth=%d",
        timing.ctx_llm_ms, timing.ctx_llm_used_llm,
        timing.llm_token_prompt, timing.llm_token_completion,
        timing.llm_cypher_depth,
    )
    logger.debug(
        "Step 5a  LLM 生成 Cypher（%s）:\n%s",
        "实际调用" if timing.ctx_llm_used_llm else "硬编码 fallback",
        cypher,
    )

    # ── Step 5b: Neo4j 执行上下文查询 ─────────────────────────────────────────
    ctx: Optional[Dict[str, Any]] = None
    with driver.session() as session:
        with _measure() as out:
            record = session.run(cypher).single()
        timing.ctx_neo4j_ms = out[0]
        logger.debug("Step 5b  ctx_neo4j  %.1f ms", timing.ctx_neo4j_ms)

        if record is None:
            logger.warning("Gap-context query 无结果: %s→%s", src_id, tgt_id)
            return [], timing
        ctx = dict(record)
        logger.debug(
            "Step 5b  ctx 关键字段:\n"
            "        src=%s(%s/%s)  tgt=%s(%s/%s)\n"
            "        dir4=%-8s  dir8=%-14s  dist_level=%-10s  actual_dist=%s\n"
            "        ego_dir8=%-12s  anc=%s(%s)  beyond=%s(%s)",
            ctx.get("src_id",""), ctx.get("src_type",""), ctx.get("src_status",""),
            ctx.get("tgt_id",""), ctx.get("tgt_type",""), ctx.get("tgt_status",""),
            ctx.get("dir4",""),    ctx.get("dir8",""),     ctx.get("dist_level",""),
            ctx.get("actual_dist",""),
            ctx.get("ego_dir8",""),
            ctx.get("anc_id","-"),  ctx.get("anc_type","-"),
            ctx.get("beyond_id","-"), ctx.get("beyond_type","-"),
        )

        # ── Step 5c: 查询候选集（常需，用于单跳约束 + 模板唯一性检验）───────
        candidates: List[Dict[str, Any]] = []
        dir4 = ctx.get("dir4") or cell.get("dir4", "front")
        with _measure() as out:
            candidates = _fetch_candidates(session, src_id, dir4)
        timing.cand_neo4j_ms = out[0]
        timing.n_candidates = len(candidates)
        logger.debug(
            "Step 5c  cand_neo4j  %.1f ms  %d candidates",
            timing.cand_neo4j_ms, len(candidates),
        )

        logger.debug(
            "Step 5c  候选集 %d 个:\n%s",
            len(candidates),
            "\n".join(
                f"        {c.get('id','?'):20s} {c.get('tgt_type','?'):12s} "
                f"{c.get('tgt_status','?'):10s} {c.get('dir8','?'):14s} "
                f"{c.get('dist_level','?'):10s} dist={c.get('actual_dist','?')}"
                for c in candidates
            ),
        )

        # ── Step 5c2: referent 批量查询（仅 constraint chain 模式，二跳用）────────
        referents: List[Dict[str, Any]] = []
        if use_constraint_chain:
            tgt_type_for_ref = ctx.get("tgt_type") or cell.get("tgt_type", "")
            with _measure() as out2:
                referents = _fetch_referents(session, tgt_id, src_id, tgt_type_for_ref)
            timing.cand_neo4j_ms += out2[0]   # 并入 5c 计时
            logger.debug(
                "Step 5c2 referents  %.1f ms  %d refs:\n%s",
                out2[0], len(referents),
                "\n".join(
                    f"        {r.get('ref_id','?'):20s} → {r.get('dir8','?'):12s} "
                    f"sibling_cnt={r.get('sibling_cnt','?')}"
                    for r in referents
                ),
            )

    # ── 构建 tvars ─────────────────────────────────────────────────────────────
    def _s(v: Any) -> str:
        return str(v) if v is not None else ""

    tvars: Dict[str, str] = {
        "src_id":      _s(ctx.get("src_id")     or cell.get("src_id")),
        "src_type":    _s(ctx.get("src_type")   or cell.get("src_type")),
        "src_status":  _s(ctx.get("src_status") or cell.get("src_status")),
        "tgt_id":      _s(ctx.get("tgt_id")     or cell.get("tgt_id")),
        "tgt_type":    _s(ctx.get("tgt_type")   or cell.get("tgt_type")),
        "tgt_status":  _s(ctx.get("tgt_status") or cell.get("tgt_status")),
        "dir4":        _s(ctx.get("dir4")        or cell.get("dir4")),
        "dir8":        _s(ctx.get("dir8")        or cell.get("dir8")),
        "dist_level":  _s(ctx.get("dist_level") or cell.get("dist_level")),
        "anc_id":      _s(ctx.get("anc_id")   or ""),
        "anc_type":    _s(ctx.get("anc_type") or ""),
        "beyond_id":   _s(ctx.get("beyond_id")   or ""),
        "beyond_type": _s(ctx.get("beyond_type") or ""),
    }

    cell_info: Dict[str, str] = {
        "src_id":    tvars["src_id"],
        "tgt_id":    tvars["tgt_id"],
        "anc_id":    tvars["anc_id"],
        "beyond_id": tvars["beyond_id"],
    }

    qa_list: List[Dict[str, Any]] = []

    # ── Step 5d: ConstraintChain.tighten()  ←  重点计时 ──────────────────────
    if use_constraint_chain and constraint_chain is not None:
        gap_target: Dict[str, Any] = {
            "id":          tvars["tgt_id"],
            "tgt_type":    tvars["tgt_type"],
            "tgt_status":  tvars["tgt_status"],
            "dist_level":  tvars["dist_level"],
            "dir8":        tvars["dir8"],
            "actual_dist": ctx.get("actual_dist"),         # None 当 DB 无距离属性
            "ego_dir8":    ctx.get("ego_dir8", ""),         # DualReference 用
        }
        ctx_for_chain = {**ctx, "referents": referents}   # 二跳方法通过此 key 取 referents
        with _measure() as out:
            tighten_result = constraint_chain.tighten(
                gap_target=gap_target,
                candidates=candidates,
                tvars=tvars,
                ctx=ctx_for_chain,
            )
        timing.constraint_ms        = out[0]
        timing.method_used          = tighten_result.method_used
        timing.is_unique            = tighten_result.is_unique
        timing.method_timings       = tighten_result.method_timings
        timing.constraint_trace_str = tighten_result.format_trace()
        timing.n_failed_attempts    = tighten_result.n_failed_attempts
        logger.debug(
            "Step 5d  约束链  %.2f ms\n"
            "         方法: %s   唯一: %s\n"
            "         问题: %s\n"
            "         答案: %s",
            timing.constraint_ms,
            tighten_result.method_used, tighten_result.is_unique,
            tighten_result.question,
            tighten_result.answer,
        )

        # ── Step 5d.5: 验证 Cypher（Python 自动生成，确认约束是否真正唯一）────
        if tighten_result.is_unique:
            _vcypher = _build_verify_cypher(
                method_used=tighten_result.method_used,
                tvars=tvars,
                gap_target=gap_target,
                tighten_value=tighten_result.value,
            )
            if _vcypher:
                logger.debug("Step 5d.5  验证 Cypher：\n%s", _vcypher)
                try:
                    with driver.session() as _vsess:
                        _vr = _vsess.run(
                            _vcypher.split("\n",1)[1]  # 去掉注释行
                        ).single()
                    if _vr:
                        _vn   = _vr.get("n", len(_vr.get("ids", [])))
                        _vids = list(_vr.get("ids", [_vr.get("id","?")]))
                    else:
                        _vn, _vids = 0, []
                    _ok = (_vn == 1 and tvars["tgt_id"] in _vids)
                    logger.debug(
                        "Step 5d.5  验证结果: n=%d  ids=%s  %s",
                        _vn, _vids,
                        "✅ 确认唯一" if _ok else "❗ 验证失败"
                    )
                except Exception as _ve:
                    logger.debug("Step 5d.5  验证运行异常: %s", _ve)

        # constraint chain 结果作为一个高质量 QA 对
        if tighten_result.question and tighten_result.answer:
            qa_list.append({
                "question_id":       str(uuid.uuid4())[:8],
                "scene_name":        scene_name,
                "frame_idx":         frame_idx,
                "template_id":       f"constraint:{tighten_result.method_used}",
                "difficulty":        "hard" if tighten_result.is_unique else "medium",
                "question_type":     "constraint_chain",
                "question":          tighten_result.question,
                "answer":            tighten_result.answer,
                "answer_type":       "open" if tighten_result.is_unique else "yes_no",
                "reference_objects": [tvars["src_id"]],
                "target_objects":    [tvars["tgt_id"]],
                "source":            "gap_constraint",
                "cell_info":         cell_info,
                "is_unique":         tighten_result.is_unique,
                "method_used":       tighten_result.method_used,
            })

    # ── Step 5d+: 否定题 + 多跳链式题（丰富题型多样性）───────────────
    _COMMON_TYPES = {"car", "truck", "pedestrian", "bicycle", "motorcycle"}
    _present_types = {c.get("tgt_type", "") for c in candidates}
    _absent_types  = sorted(_COMMON_TYPES - _present_types)  # 在该方向不存在的类型

    # 否定题：候选集中某类型不存在 → "Is there a truck to the front of car1?" → No
    if _absent_types:
        from gap_pipeline.constraint_methods import _src as _cs
        _absent = _absent_types[0]  # 确定性取第一个
        _dir4   = tvars.get("dir4", ctx.get("dir4", ""))
        _src_str = _cs(tvars)
        _neg_q   = f"Is there a {_absent} to the {_dir4} of {_src_str}?"
        qa_list.append({
            "question_id":   str(uuid.uuid4())[:8],
            "scene_name":    scene_name,
            "frame_idx":     frame_idx,
            "template_id":   "negation:absent_type",
            "difficulty":    "medium",
            "question_type": "negation",
            "question":      _neg_q,
            "answer":        "No",
            "answer_type":   "yes_no",
            "reference_objects": [tvars["src_id"]],
            "target_objects":    [],
            "source":        "negation",
            "cell_info":     cell_info,
            "is_unique":     True,
        })
        logger.debug("Step 5d+  negation: %s", _neg_q)

    # 多跳题：利用 beyond 节点生成链式问题
    # "What {beyond_type} is to the {dir8} of {tgt_id}?"
    _beyond_id   = ctx.get("beyond_id", "")
    _beyond_type = ctx.get("beyond_type", "")
    if _beyond_id and _beyond_type and _beyond_type != tvars.get("tgt_type", ""):
        # 使用 tgt 自己的类型检查 ID 是否已包含类型前缀，不要用 beyond_type
        _tgt_label = _ref_label_fn(tvars.get("tgt_type", ""), tvars["tgt_id"])
        _dir8 = tvars.get("dir8", "front")
        _hop_q = f"What {_beyond_type} is to the {_dir8} of {_tgt_label}?"
        qa_list.append({
            "question_id":   str(uuid.uuid4())[:8],
            "scene_name":    scene_name,
            "frame_idx":     frame_idx,
            "template_id":   "multihop:beyond_node",
            "difficulty":    "hard",
            "question_type": "multihop",
            "question":      _hop_q,
            "answer":        _beyond_id,
            "answer_type":   "open",
            "reference_objects": [tvars["src_id"], tvars["tgt_id"]],
            "target_objects":    [_beyond_id],
            "source":        "multihop",
            "cell_info":     cell_info,
            "is_unique":     True,  # beyond 已经是同方向唯一的下一跳
        })
        logger.debug("Step 5d+  multihop beyond: %s", _hop_q)

    # ── Step 5e: 模板填充 ───────────────────────────────────────────────
    with _measure() as out:
        applicable = get_applicable_templates(tvars)
        import random
        random.shuffle(applicable)

        tmpl_qa: List[Dict[str, Any]] = []
        for tmpl_id in applicable:
            meta = TEMPLATE_META[tmpl_id]
            try:
                question = pick_variation(tmpl_id).format(**tvars)
            except KeyError:
                continue
            answer = resolve_answer(tmpl_id, tvars)
            if not answer:
                continue
            tmpl_qa.append({
                "question_id":       str(uuid.uuid4())[:8],
                "scene_name":        scene_name,
                "frame_idx":         frame_idx,
                "template_id":       tmpl_id,
                "difficulty":        meta["difficulty"],
                "question_type":     meta["category"],
                "question":          question,
                "answer":            answer,
                "answer_type":       meta["answer_type"],
                "reference_objects": [tvars["src_id"]],
                "target_objects":    [tvars["tgt_id"]],
                "source":            "gap_fill",
                "cell_info":         cell_info,
            })
            if len(tmpl_qa) >= max_per_cell:
                break

    timing.template_fill_ms = out[0]
    qa_list.extend(tmpl_qa)
    logger.debug("Step 5e  template_fill  %.1f ms  %d pairs", timing.template_fill_ms, len(tmpl_qa))

    timing.total_ms = (
        timing.ctx_llm_ms
        + timing.ctx_neo4j_ms
        + timing.cand_neo4j_ms
        + timing.constraint_ms
        + timing.template_fill_ms
    )
    timing.n_qa = len(qa_list)
    return qa_list, timing


# =============================================================================
# 打印汇总
# =============================================================================

def _print_summary(
    global_times: Dict[str, float],
    cell_timings: List[_CellTiming],
    all_qa: List[Dict[str, Any]],
    use_constraint_chain: bool,
) -> None:
    """控制台打印完整计时报告。"""
    SEP = "─" * 70

    print(f"\n{SEP}")
    print("  Gap Pipeline — 计时报告")
    print(SEP)

    # 全局步骤
    print("\n【全局步骤耗时】")
    for step, ms in global_times.items():
        print(f"  {step:<25} {ms:>10.1f} ms")

    # per-cell 汇总
    if cell_timings:
        print(f"\n【per-cell 耗时汇总（共 {len(cell_timings)} 个 gap cell）】")

        steps = [
            ("ctx_llm_ms",       "5a  LLM 生成上下文 Cypher"),
            ("ctx_neo4j_ms",     "5b  Neo4j 执行上下文查询"),
            ("cand_neo4j_ms",    "5c  Neo4j 候选集 + referent 批量查询"),
        ]
        if use_constraint_chain:
            steps += [
                ("constraint_ms",   "5d  ConstraintChain.tighten()  ◄ 重点"),
            ]
        steps += [
            ("template_fill_ms", "5e  模板选择 + 填空"),
            ("total_ms",         "    TOTAL per-cell"),
        ]

        header = f"  {'步骤':<40} {'mean':>8} {'max':>8} {'min':>8} {'p95':>8} {'total':>10}"
        print(header)
        print("  " + "─" * 68)
        for attr, label in steps:
            vals = [getattr(t, attr) for t in cell_timings]
            a = _agg(vals)
            marker = "  ◄◄" if "重点" in label else ""
            print(
                f"  {label:<40} {a['mean']:>7.1f}  {a['max']:>7.1f}  "
                f"{a['min']:>7.1f}  {a['p95']:>7.1f}  {a['total']:>9.1f}{marker}"
            )

        # Step 5a LLM 使用统计
        llm_cnt  = sum(1 for t in cell_timings if getattr(t, 'ctx_llm_used_llm', False))
        fallback_cnt = len(cell_timings) - llm_cnt
        print(f"\n  Step 5a LLM 调用统计: 实际调用={llm_cnt}  退回硬编码={fallback_cnt}")

        # constraint chain 方法分布
        if use_constraint_chain:
            from collections import Counter, defaultdict
            method_dist = Counter(t.method_used for t in cell_timings if t.method_used)
            unique_cnt  = sum(1 for t in cell_timings if t.is_unique)
            print(f"\n  约束方法分布 (共 {len(cell_timings)} cells, 唯一锁定 {unique_cnt}):")
            print(f"  {'方法名':<35} {'成功次数':>8} {'平均耗时ms':>12}")
            print("  " + "─" * 58)
            for method, cnt in method_dist.most_common():
                # 收集该方法的耗时字数据
                times = [
                    t.method_timings[method]
                    for t in cell_timings
                    if isinstance(t.method_timings, dict) and method in t.method_timings
                ]
                avg_ms = sum(times) / len(times) if times else 0.0
                is_unique_method = method not in ("count_fallback", "yesno_fallback",
                                                   "emergency_fallback")
                tag = " ✓唯一" if is_unique_method else " (fallback)"
                print(f"  {method:<35} {cnt:>8}     {avg_ms:>9.2f} ms{tag}")

            # 逆向统计：每个方法被尝试的次数（包括失败的）
            all_tried_counts: Dict[str, int] = defaultdict(int)
            for t in cell_timings:
                if isinstance(t.method_timings, dict):
                    for mname in t.method_timings:
                        all_tried_counts[mname] += 1
            print(f"\n  [各方法被计载(含未成功)次数和平均耗时]")
            print(f"  {'方法名':<35} {'被计载次':>8} {'平均耗时ms':>12}")
            print("  " + "─" * 58)
            for mname, tried in sorted(all_tried_counts.items(),
                                        key=lambda x: -x[1]):
                times = [
                    t.method_timings[mname]
                    for t in cell_timings
                    if isinstance(t.method_timings, dict) and mname in t.method_timings
                ]
                avg_ms = sum(times) / len(times) if times else 0.0
                success = method_dist.get(mname, 0)
                print(f"  {mname:<35} {tried:>8}     {avg_ms:>9.2f} ms  (success={success})")

    print(f"\n  生成 QA 对总数: {len(all_qa)}")
    print(f"{SEP}\n")


# =============================================================================
# 主流程
# =============================================================================

# =============================================================================
# 持久化 timing log
# =============================================================================

def _append_timing_log(
    log_path: Path,
    run_id: str,
    args_dict: Dict[str, Any],
    global_times: Dict[str, float],
    cell_timings: "List[_CellTiming]",
    result: Dict[str, Any],
) -> None:
    """将本次运行的计时摘要追加写入 timing_log.jsonl。
    每条 JSON 包含： run_id / timestamp / 参数 / 全局耐时 / per_method 分布
    """
    unique_cnt = sum(1 for t in cell_timings if t.is_unique)
    entry = {
        "run_id":          run_id,
        "timestamp":       time.strftime("%Y-%m-%dT%H:%M:%S"),
        "params":          args_dict,
        "n_gap_cells":     result.get("n_gap_cells", 0),
        "n_qa_generated":  result.get("n_qa_generated", 0),
        "unique_qa_cells": unique_cnt,
        "step5a_llm_calls": result.get("step5a_llm_calls", 0),
        "global_times_ms": global_times,
        "per_cell_agg":    result.get("per_cell_agg", {}),
        "per_method_timing": result.get("per_method_timing", {}),
        "coverage":        result.get("coverage", {}),
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.info("计时日志已追加写入: %s", log_path)


def run_pipeline(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    max_cells: int = 0,
    max_per_cell: int = 8,
    use_constraint_chain: bool = False,
    use_cumulative_chain: bool = False,
    l2_only: bool = False,
    scene_name: str = "",
    frame_idx: int = 0,
    output_path: Optional[str] = None,
    target_coverage: float = 0.0,
    max_qa: int = 0,
    timing_log_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    执行完整 gap pipeline 并返回计时 + QA 结果字典。

    Parameters
    ----------
    neo4j_uri / neo4j_user / neo4j_password : 连接参数
    max_cells      : 最多处理的 gap cell 数（0 = 不限）
    max_per_cell   : 每 cell 最多生成的模板 QA 对数
    use_constraint_chain : True 时启用 ConstraintChain
    scene_name, frame_idx : 写入 QA 元数据
    output_path    : JSON 输出路径（None = 不写出）
    target_coverage : 目标 edge 覆盖率 %（0 = 不限，如 30.0 表示达到 30% 即停）
    max_qa         : 目标 QA 对总数（0 = 不限，如 5000 表示生成 5000 条即停）
    """
    from neo4j import GraphDatabase  # type: ignore[import]
    from gap_pipeline.llm_client import LLMClient
    from gap_pipeline.scene_coverage import CoverageMap, SceneCoverageCalculator

    # 支持两种约束模式。cumulative 优先于 constraint_chain
    constraint_chain = None
    _chain_label = "none"
    if use_cumulative_chain:
        from gap_pipeline.constraint_methods import CumulativeConstraintChain
        constraint_chain = CumulativeConstraintChain()
        _chain_label = "cumulative"
        use_constraint_chain = True   # 复用存在的分支逻辑
        logger.info("使用 CumulativeConstraintChain（动态叠加约束）")
    elif use_constraint_chain:
        from gap_pipeline.constraint_methods import ConstraintChain
        constraint_chain = ConstraintChain()
        _chain_label = "fixed"
        logger.info("使用 ConstraintChain（固定优先级约束）")

    global_times: Dict[str, float] = {}

    # ── Step 0: 初始化连接 ────────────────────────────────────────────────────
    with _measure() as out:
        llm    = LLMClient()
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    global_times["0_init_ms"] = out[0]
    logger.info("Step 0  init  %.1f ms", global_times["0_init_ms"])

    try:
        # ── Step 1: 场景枚举 Cypher（硬编码，不走 LLM）─────────────────────────
        with _measure() as out:
            from gap_pipeline.llm_client import LLMClient as _LC
            scene_cypher = _LC.build_scene_analysis_cypher()
        global_times["1_scene_cypher_ms"] = out[0]
        logger.info("Step 1  scene_cypher(hardcoded)  %.3f ms", global_times["1_scene_cypher_ms"])

        # ── Step 2: Neo4j 执行场景枚举 ────────────────────────────────────────
        with _measure() as out:
            with driver.session() as session:
                edge_records = [dict(rec) for rec in session.run(scene_cypher)]
        global_times["2_scene_neo4j_ms"] = out[0]
        logger.info(
            "Step 2  scene_neo4j  %.1f ms  edges=%d",
            global_times["2_scene_neo4j_ms"], len(edge_records),
        )

        # ── Step 3: CoverageMap 初始化 ────────────────────────────────────────
        with _measure() as out:
            cmap = CoverageMap()
            cmap.init_from_records(edge_records)
        global_times["3_cmap_init_ms"] = out[0]
        logger.info("Step 3  cmap_init  %.1f ms", global_times["3_cmap_init_ms"])

        # ── Step 4: 识别 gap cells ────────────────────────────────────────────
        with _measure() as out:
            gap_cells = cmap.get_gap_cells(level="edge")
        global_times["4_gap_detect_ms"] = out[0]
        logger.info(
            "Step 4  gap_detect  %.1f ms  gaps=%d",
            global_times["4_gap_detect_ms"], len(gap_cells),
        )

        # L2 过滤：只保留 src != ego 的 gap cell
        if l2_only:
            before = len(gap_cells)
            gap_cells = [c for c in gap_cells if c.get("src_id") != "ego"]
            logger.info("⚙  --l2-only: %d → %d cells（过滤掉 ego-src）", before, len(gap_cells))

        if max_cells > 0:
            gap_cells = gap_cells[:max_cells]
            logger.info("⚙  max_cells=%d → 截取 %d cells", max_cells, len(gap_cells))

        # ── Step 5: per-cell 循环 ─────────────────────────────────────────────
        all_qa: List[Dict[str, Any]] = []
        cell_timings: List[_CellTiming] = []

        # 预算停止条件说明
        stop_reasons: List[str] = []
        if max_qa > 0:
            stop_reasons.append(f"max_qa={max_qa}")
        if target_coverage > 0:
            stop_reasons.append(f"target_coverage={target_coverage}%")
        if stop_reasons:
            logger.info("⚙  停止条件: %s", " | ".join(stop_reasons))

        total_edges = len(cmap._edge_counts)

        for i, cell in enumerate(gap_cells, 1):
            # ── 预算检查（每 cell 前） ──────────────────────────────────────────
            if max_qa > 0 and len(all_qa) >= max_qa:
                logger.info("  🛑 达到 max_qa=%d，已生成 %d 条，提前停止", max_qa, len(all_qa))
                break
            if target_coverage > 0:
                covered = sum(1 for c in cmap._edge_counts.values() if c > 0)
                current_rate = covered / total_edges * 100 if total_edges else 0
                if current_rate >= target_coverage:
                    logger.info(
                        "  🛑 达到目标覆盖率 %.1f%%（当前 %.2f%%），提前停止",
                        target_coverage, current_rate,
                    )
                    break

            src_id = cell.get("src_id", "?")
            tgt_id = cell.get("tgt_id", "?")
            logger.info("  cell %d/%d  %s→%s", i, len(gap_cells), src_id, tgt_id)
            try:
                qa_list, ct = _process_cell_timed(
                    cell=cell,
                    llm_client=llm,
                    driver=driver,
                    use_constraint_chain=use_constraint_chain,
                    constraint_chain=constraint_chain,
                    max_per_cell=max_per_cell,
                    scene_name=scene_name,
                    frame_idx=frame_idx,
                )
                all_qa.extend(qa_list)
                cell_timings.append(ct)
                # 实时更新 CoverageMap 以便覆盖率检查准确
                for qa in qa_list:
                    cmap.update(qa)
            except Exception as exc:  # noqa: BLE001
                logger.warning("  cell %s→%s 失败: %s", src_id, tgt_id, exc)

        # ── Step 6: CoverageMap 最终统计（已在循环中实时更新）────────────────
        with _measure() as out:
            pass  # updates already done per-cell in the loop above
        global_times["6_cmap_update_ms"] = out[0]

        # ── 打印汇总 ──────────────────────────────────────────────────────────
        _print_summary(global_times, cell_timings, all_qa, use_constraint_chain)

        cov_stats = cmap.stats()
        logger.info("Coverage: %s", cov_stats)

        # ── 构建结果字典 ─────────────────────────────────────────────────
        # 逐方法计时汇总
        from collections import defaultdict
        _method_agg: Dict[str, list] = defaultdict(list)
        for ct in cell_timings:
            if isinstance(ct.method_timings, dict):
                for mname, ms in ct.method_timings.items():
                    _method_agg[mname].append(ms)
        per_method_timing = {
            mname: _agg(vals)
            for mname, vals in sorted(_method_agg.items())
        }

        # Step 5a LLM 使用统计
        llm_call_count = sum(1 for ct in cell_timings
                             if getattr(ct, 'ctx_llm_used_llm', False))

        result: Dict[str, Any] = {
            "global_times_ms":     global_times,
            "n_gap_cells":         len(gap_cells),
            "n_qa_generated":      len(all_qa),
            "coverage":            cov_stats,
            "step5a_llm_calls":    llm_call_count,
            "step5a_fallback_calls": len(cell_timings) - llm_call_count,
            "cell_timings":        [ct.to_dict() for ct in cell_timings],
            "per_cell_agg": {
                step: _agg([getattr(t, step) for t in cell_timings])
                for step in (
                    "ctx_llm_ms",
                    "ctx_neo4j_ms",
                    "cand_neo4j_ms",
                    "constraint_ms",
                    "template_fill_ms",
                    "total_ms",
                )
            },
            "per_method_timing":   per_method_timing,
            "qa_pairs": all_qa,
        }

        if output_path:
            _out = Path(output_path)
            _out.parent.mkdir(parents=True, exist_ok=True)
            _out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("结果已写入: %s", _out)

        # 持久化计时日志
        _log_path = Path(timing_log_path) if timing_log_path else (
            Path(__file__).parent / "output" / "timing_log.jsonl"
        )
        _run_id = time.strftime("%Y%m%d_%H%M%S")
        _args_dict = {
            "neo4j_uri":           neo4j_uri,
            "max_cells":           max_cells,
            "max_per_cell":        max_per_cell,
            "chain_mode":          _chain_label,
            "use_constraint_chain": use_constraint_chain,
            "target_coverage":     target_coverage,
            "max_qa":              max_qa,
        }
        try:
            _append_timing_log(_log_path, _run_id, _args_dict,
                                global_times, cell_timings, result)
        except Exception as _log_exc:
            logger.warning("计时日志写入失败: %s", _log_exc)

        return result

    finally:
        driver.close()


# =============================================================================
# CLI 入口
# =============================================================================

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Gap Pipeline 主运行脚本（带全流程计时）",
    )
    p.add_argument("--neo4j-uri",      default="bolt://localhost:7800")
    p.add_argument("--neo4j-user",     default="neo4j")
    p.add_argument("--neo4j-password", default="87017563")
    p.add_argument(
        "--max-cells", type=int, default=0,
        help="最多处理的 gap cell 数（0 = 不限）",
    )
    p.add_argument(
        "--max-per-cell", type=int, default=8,
        help="每 cell 最多生成的模板 QA 对数（默认 8）",
    )
    p.add_argument(
        "--use-constraint-chain", action="store_true",
        help="启用 ConstraintChain（5c 候选查询 + 5d 约束收束），并单独计时",
    )
    p.add_argument(
        "--use-cumulative-chain", action="store_true",
        help="启用 CumulativeConstraintChain（动态叠加约束，自动寻找最少属性组合）",
    )
    p.add_argument(
        "--l2-only", action="store_true",
        help="只处理 src != ego 的 gap cell（L2 级别问题）",
    )
    p.add_argument(
        "--timing-log", default=None,
        help="计时日志路径（默认: output/timing_log.jsonl）",
    )
    p.add_argument("--scene-name", default="")
    p.add_argument("--frame-idx",  type=int, default=0)
    p.add_argument(
        "--output", default=None,
        help="JSON 结果输出路径（含 QA 对 + 全部计时数据）",
    )
    p.add_argument(
        "--target-coverage", type=float, default=0.0,
        help="目标 edge 覆盖率 %%（如 30.0 = 达到 30%% 后停止，0 = 不限）",
    )
    p.add_argument(
        "--max-qa", type=int, default=0,
        help="目标 QA 对总数（如 5000 = 生成 5000 条后停止，0 = 不限）",
    )
    p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING"],
        default="INFO",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.getLogger().setLevel(args.log_level)

    # 如果要求 DEBUG，只把自己的 logger 调到 DEBUG；
    # neo4j.io / neo4j.pool / httpx 等第三方库最多输 INFO。
    if args.log_level == "DEBUG":
        for _noisy in ("neo4j", "neo4j.io", "neo4j.pool", "httpx",
                       "urllib3", "openai", "httpcore",
                       "httpcore.connection", "httpcore.http11",
                       "httpcore.proxy"):
            logging.getLogger(_noisy).setLevel(logging.WARNING)
        for _ours in ("run_gap_pipeline", "gap_pipeline",
                      "gap_pipeline.constraint_chain",
                      "gap_pipeline.llm_client",
                      "gap_pipeline.scene_coverage"):
            logging.getLogger(_ours).setLevel(logging.DEBUG)

    chain_mode = (
        "cumulative" if args.use_cumulative_chain
        else ("fixed" if args.use_constraint_chain else "none")
    )
    logger.info(
        "启动 Gap Pipeline  neo4j=%s  max_cells=%s  chain_mode=%s",
        args.neo4j_uri, args.max_cells or "∞", chain_mode,
    )

    run_pipeline(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        max_cells=args.max_cells,
        max_per_cell=args.max_per_cell,
        use_constraint_chain=args.use_constraint_chain,
        use_cumulative_chain=args.use_cumulative_chain,
        l2_only=args.l2_only,
        scene_name=args.scene_name,
        frame_idx=args.frame_idx,
        output_path=args.output,
        target_coverage=args.target_coverage,
        max_qa=args.max_qa,
        timing_log_path=args.timing_log,
    )


if __name__ == "__main__":
    main()
