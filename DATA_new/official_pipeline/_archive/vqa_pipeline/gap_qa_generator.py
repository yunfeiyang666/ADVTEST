"""
缺口补题模块 — GapQAGenerator

主流程（cell 模式，新主入口）：
  CoverageMap.get_gap_cells() 返回未覆盖 L1 cell
      ↓
  LLM 按 cell 模式（src_type/status/tgt_type/status/dir4/dist_level）
  生成上下文查询 Cypher（含 OPTIONAL MATCH L2 链）
      ↓
  Neo4j 执行 → 返回结构化上下文（19 个字段别名）
      ↓
  规则选模板 + 填空 → QA 对列表（answer 从上下文直接提取，LLM 不参与）
      ↓
  每条 QA 携带 cell_info → CoverageMap.update() 增量更新覆盖计数

兼容接口（旧流程）：
  generate_from_gaps(gap_edges) — 按 unique_id 边级处理，保持向下兼容

设计原则：
  - LLM 只负责生成"上下文查询 Cypher"，难度低、输入结构化
  - 模板选择与自然语言问题文本由规则程序生成，与 qa_generator 保持一致
  - 每条缺口最多生成 max_per_edge 道题（默认 8），控制题集膨胀
"""
from __future__ import annotations

import logging
import random
import uuid
from typing import Any, Dict, List, Optional

from .llm_client import LLMClient
from .neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

# ── 类型名称映射（与 core_pipeline/qa_generator/config.py 保持一致）──────────
_TYPE_NAMES: Dict[str, tuple] = {
    "car":                  ("car",                "cars"),
    "truck":                ("truck",              "trucks"),
    "bus":                  ("bus",                "buses"),
    "trailer":              ("trailer",            "trailers"),
    "motorcycle":           ("motorcycle",         "motorcycles"),
    "bicycle":              ("bicycle",            "bicycles"),
    "pedestrian":           ("pedestrian",         "pedestrians"),
    "barrier":              ("barrier",            "barriers"),
    "traffic_cone":         ("traffic cone",       "traffic cones"),
    "construction_vehicle": ("construction vehicle", "construction vehicles"),
    "ego":                  ("ego vehicle",        "ego vehicles"),
}


def _type_name(obj_type: str) -> str:
    """返回对象类型的单数自然语言名称。"""
    return _TYPE_NAMES.get(obj_type, (obj_type, obj_type))[0]


def _direction(dir8: Optional[str], dir4: Optional[str]) -> str:
    """优先使用8方位词；若为纯4方位词则用4方位。"""
    if dir8 and "-" in dir8:
        return dir8
    return dir4 or dir8 or ""


# ─────────────────────────────────────────────────────────────────────────────
# 主类
# ─────────────────────────────────────────────────────────────────────────────

class GapQAGenerator:
    """基于缺口边，通过 LLM→Cypher→Neo4j 获取上下文，然后规则填模板出题。

    Parameters
    ----------
    llm_client : LLMClient
        用于调用大模型生成上下文查询 Cypher。
    neo4j_client : Neo4jClient
        用于执行 Cypher 获取节点属性和链上下文。
    max_per_edge : int
        每个缺口最多生成的题目数量（默认 8）。
    """

    def __init__(
        self,
        llm_client: LLMClient,
        neo4j_client: Neo4jClient,
        max_per_edge: int = 8,
    ):
        self.llm = llm_client
        self.neo4j = neo4j_client
        self.max_per_edge = max_per_edge

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def generate_from_gaps(
        self,
        gap_edges: List[Dict[str, Any]],
        scene_name: str = "",
        frame_idx: int = 0,
    ) -> List[Dict[str, Any]]:
        """遍历缺口边列表，为每条边生成若干 QA 对。

        Parameters
        ----------
        gap_edges : list of dict
            ``SceneCoverageCalculator.get_gap_edges()`` 的返回值，
            每项包含 ``source``, ``target``, ``dir4``, ``predicates``,
            ``distance`` 等字段。
        scene_name : str
            当前场景名称，写入 QA 元数据。
        frame_idx : int
            当前帧序号，写入 QA 元数据。

        Returns
        -------
        list of dict
            与 QAPair dataclass 字段对应的字典列表，可直接序列化。
        """
        results: List[Dict[str, Any]] = []
        for edge in gap_edges:
            src_id = edge.get("source", "?")
            tgt_id = edge.get("target", "?")
            try:
                qa_list = self._process_edge(edge, scene_name, frame_idx)
                results.extend(qa_list)
                logger.info(
                    "缺口边 %s→%s 生成 %d 道题", src_id, tgt_id, len(qa_list)
                )
            except Exception as exc:
                logger.warning("跳过缺口边 %s→%s: %s", src_id, tgt_id, exc)
        return results

    def generate_from_gap_cells(
        self,
        gap_cells: List[Dict[str, Any]],
        scene_name: str = "",
        frame_idx: int = 0,
    ) -> List[Dict[str, Any]]:
        """基于 CoverageMap.get_gap_cells() 返回的 cell 列表生成补题 QA 对（新主入口）。

        Parameters
        ----------
        gap_cells : list of dict
            CoverageMap.get_gap_cells() 的返回値，每项为含有
            src_type/src_status/tgt_type/tgt_status/dir4/dist_level 的 L1 cell dict。
        scene_name / frame_idx :
            写入 QA 元数据。
        """
        results: List[Dict[str, Any]] = []
        for cell in gap_cells:
            if cell.get("level", "L1") != "L1":
                # L0 仅作统计参考，由 L1 QA 间接覆盖无需单独处理
                continue
            try:
                qa_list = self._process_cell(cell, scene_name, frame_idx)
                results.extend(qa_list)
                logger.info(
                    "gap cell %s/%s→%s/%s(%s,%s) 生成 %d 道题",
                    cell.get("src_type"), cell.get("src_status"),
                    cell.get("tgt_type"), cell.get("tgt_status"),
                    cell.get("dir4"), cell.get("dist_level"),
                    len(qa_list),
                )
            except Exception as exc:
                logger.warning("跳过 gap cell %s: %s", cell, exc)
        return results

    # ── 单条边处理 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _gap_edge_to_cell(gap_edge: Dict[str, Any]) -> Dict[str, Any]:
        """将旧式 gap_edge（unique_id面向）转换为 cell 字段。

        旧式边只有 unique_id，无法直接转化为类型/状态，
        最少保留 dir4 和 dist_level 作为匹配条件。
        """
        predicates = gap_edge.get("predicates") or []
        dist_level = predicates[1] if len(predicates) > 1 else gap_edge.get("dist_level", "")
        return {
            "src_type":   "",
            "src_status": "",
            "tgt_type":   "",
            "tgt_status": "",
            "dir4":       gap_edge.get("dir4", ""),
            "dist_level": dist_level,
        }

    def _process_edge(
        self,
        gap_edge: Dict[str, Any],
        scene_name: str,
        frame_idx: int,
    ) -> List[Dict[str, Any]]:
        """处理单条缺口边：LLM→Cypher→Neo4j→模板填空。

        .. deprecated::
            请使用 :meth:`generate_from_gap_cells` + CoverageMap 流程。
            这里保留仅为向下兼容；上下文 Cypher 会按方向/距离匹配，
            但没有类型/状态过滤。
        """
        # 将旧式为 gap_edge 适配为 cell 字段（仅能提取 dir4/dist_level）
        gap_cell_compat = self._gap_edge_to_cell(gap_edge)
        cypher = self.llm.generate_gap_context_cypher(gap_cell_compat)
        logger.debug("缺口上下文 Cypher:\n%s", cypher)

        # Step 2: 执行 Cypher
        result = self.neo4j.execute_query(cypher)
        if not result.get("data"):
            logger.warning(
                "缺口上下文查询无结果: %s→%s",
                gap_edge.get("source"), gap_edge.get("target"),
            )
            return []

        ctx: Dict[str, Any] = result["data"][0]  # LIMIT 1

        # Step 3: 规则选模板填空
        return self._fill_templates(ctx, scene_name, frame_idx)

    def _process_cell(
        self,
        gap_cell: Dict[str, Any],
        scene_name: str,
        frame_idx: int,
    ) -> List[Dict[str, Any]]:
        """处理单个 gap cell：LLM→Cypher→Neo4j→模板填空。"""
        # Step 1: LLM 按 cell 模式生成上下文查询 Cypher
        cypher = self.llm.generate_gap_context_cypher(gap_cell)
        logger.debug("缺口上下文 Cypher:\n%s", cypher)

        # Step 2: 执行 Cypher
        result = self.neo4j.execute_query(cypher)
        if not result.get("data"):
            logger.warning(
                "缺口 cell %s/%s→%s/%s 查询无结果",
                gap_cell.get("src_type"), gap_cell.get("src_status"),
                gap_cell.get("tgt_type"), gap_cell.get("tgt_status"),
            )
            return []

        ctx: Dict[str, Any] = result["data"][0]  # LIMIT 1

        # Step 3: 规则选模板填空（传入 gap_cell 供构建 cell_info）
        return self._fill_templates(ctx, scene_name, frame_idx, gap_cell=gap_cell)

    # ── 模板填空 ──────────────────────────────────────────────────────────────

    def _fill_templates(
        self,
        ctx: Dict[str, Any],
        scene_name: str,
        frame_idx: int,
        gap_cell: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """根据上下文字段，从 300 个模板中筛选可用模板并随机选变体出题。

        答案来源：
          exist 类 → 硬编码 "yes"（缺口边在图中真实存在）
          status 类 → ctx["tgt/src/beyond_status"]（LLM 查回的节点属性）
          type  类 → ctx["tgt/beyond_type"]
          dir   类 → dir8 优先的方向字符串
          dist  类 → ctx["dist_level"]
        """
        from .gap_templates import (
            TEMPLATE_META, get_applicable_templates,
            pick_variation, resolve_answer,
        )

        # ── 构建模板变量字典 ──────────────────────────────────────────────────
        src_id        = ctx.get("src_id", "")
        src_type      = ctx.get("src_type", "")
        src_status    = ctx.get("src_status", "")
        tgt_id        = ctx.get("tgt_id", "")
        tgt_type      = ctx.get("tgt_type", "")
        tgt_status    = ctx.get("tgt_status", "")
        direction     = _direction(ctx.get("dir8"), ctx.get("dir4"))
        dist          = ctx.get("dist_level", "")

        anc_type      = ctx.get("anc_type", "")
        anc_status    = ctx.get("anc_status", "")
        dir_as        = _direction(ctx.get("anc_dir8"), ctx.get("anc_dir4"))

        beyond_type   = ctx.get("beyond_type", "")
        beyond_status = ctx.get("beyond_status", "")
        dir_tb        = _direction(ctx.get("beyond_dir8"), ctx.get("beyond_dir4"))

        # ── 构建 cell_info（优先用 gap_cell 的维度字段，回落 ctx 提取値） ───────────────
        ci_src_type   = (gap_cell.get("src_type")   or src_type)   if gap_cell else src_type
        ci_src_status = (gap_cell.get("src_status") or src_status) if gap_cell else src_status
        ci_tgt_type   = (gap_cell.get("tgt_type")   or tgt_type)   if gap_cell else tgt_type
        ci_tgt_status = (gap_cell.get("tgt_status") or tgt_status) if gap_cell else tgt_status
        ci_dir4       = (gap_cell.get("dir4")       or ctx.get("dir4", "")) if gap_cell else ctx.get("dir4", "")
        ci_dist_level = (gap_cell.get("dist_level") or dist)       if gap_cell else dist

        cell_info: Dict[str, Any] = {
            "src_type":      ci_src_type,
            "src_status":    ci_src_status,
            "tgt_type":      ci_tgt_type,
            "tgt_status":    ci_tgt_status,
            "dir4":          ci_dir4,
            "dist_level":    ci_dist_level,
            "anc_type":      anc_type,
            "anc_status":    anc_status,
            "dir_as":        dir_as,
            "dir_st":        direction,   # src→tgt 主方向
            "beyond_type":   beyond_type,
            "beyond_status": beyond_status,
            "dir_tb":        dir_tb,
        }

        tvars: Dict[str, str] = {
            # L0 变量（src=ego 时 type/status 指向 tgt）
            "type":          _type_name(tgt_type),
            "status":        tgt_status,
            # L1 变量
            "src_type":      _type_name(src_type),
            "src_status":    src_status,
            "tgt_type":      _type_name(tgt_type),
            "tgt_status":    tgt_status,
            "dir":           direction,
            "dist":          dist,
            # L2 链 A 变量
            "anc_type":      _type_name(anc_type),
            "anc_status":    anc_status,
            "dir_as":        dir_as,
            "dir_st":        direction,   # src→tgt 方向 = 主方向
            # L2 链 B 变量
            "beyond_type":   _type_name(beyond_type),
            "beyond_status": beyond_status,
            "dir_tb":        dir_tb,
        }

        # ── 筛选可用模板并随机排序 ────────────────────────────────────────────
        applicable = get_applicable_templates(ctx)
        random.shuffle(applicable)

        qa_list: List[Dict[str, Any]] = []
        for tmpl_id in applicable:
            meta = TEMPLATE_META[tmpl_id]

            # 选一个语义变体并填空
            try:
                question = pick_variation(tmpl_id).format(**tvars)
            except KeyError:
                continue

            # 提取答案
            answer = resolve_answer(meta.answer_source, ctx, tvars)
            if not answer:
                continue

            qa_list.append(self._make_qa(
                scene_name=scene_name, frame_idx=frame_idx,
                template_id=tmpl_id,
                difficulty=meta.difficulty,
                question_type=meta.category,
                question=question,
                answer=answer,
                answer_type=meta.answer_type,
                target_objects=[tgt_id],
                reference_objects=[src_id],
                directions=[direction],
                cell_info=cell_info,
            ))

            if len(qa_list) >= self.max_per_edge:
                break

        return qa_list

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _make_qa(
        scene_name: str,
        frame_idx: int,
        template_id: str,
        difficulty: str,
        question_type: str,
        question: str,
        answer: str,
        answer_type: str,
        target_objects: List[str],
        reference_objects: List[str],
        directions: List[str],
        cell_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构造与 QAPair dataclass 字段对应的字典。

        cell_info 字段由 CoverageMap.update() 利用，用于增量更新覆盖计数。
        """
        return {
            "question_id":       str(uuid.uuid4())[:8],
            "scene_name":        scene_name,
            "frame_idx":         frame_idx,
            "template_id":       template_id,
            "difficulty":        difficulty,
            "question_type":     question_type,
            "question":          question,
            "answer":            answer,
            "answer_type":       answer_type,
            "target_objects":    target_objects,
            "reference_objects": reference_objects,
            "directions_used":   directions,
            "source":            "gap_fill",
            "cell_info":         cell_info or {},
        }


# ─────────────────────────────────────────────────────────────────────────────
# 便捷函数
# ─────────────────────────────────────────────────────────────────────────────

def fill_gap_cells(
    gap_cells: List[Dict[str, Any]],
    scene_name: str = "",
    frame_idx: int = 0,
    max_per_edge: int = 8,
    neo4j_uri: str = "bolt://localhost:7600",
    neo4j_user: str = "neo4j",
    neo4j_password: str = "12345678",
) -> List[Dict[str, Any]]:
    """便捷函数：一步完成基于 CoverageMap gap cells 的补题。

    Parameters
    ----------
    gap_cells : list
        CoverageMap.get_gap_cells() 的返回值（L1 cell dict 列表）。
    """
    llm   = LLMClient()
    neo4j = Neo4jClient(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)
    gen   = GapQAGenerator(llm, neo4j, max_per_edge=max_per_edge)
    return gen.generate_from_gap_cells(gap_cells, scene_name=scene_name, frame_idx=frame_idx)


def fill_gaps(
    gap_edges: List[Dict[str, Any]],
    scene_name: str = "",
    frame_idx: int = 0,
    max_per_edge: int = 8,
    neo4j_uri: str = "bolt://localhost:7600",
    neo4j_user: str = "neo4j",
    neo4j_password: str = "12345678",
) -> List[Dict[str, Any]]:
    """便捷函数：一步完成缺口补题。

    Parameters
    ----------
    gap_edges : list
        ``SceneCoverageCalculator.get_gap_edges()`` 的返回值。
    scene_name / frame_idx : str / int
        写入 QA 元数据。
    max_per_edge : int
        每条缺口边最多生成的题目数。
    neo4j_uri / neo4j_user / neo4j_password :
        Neo4j 连接参数。

    Returns
    -------
    list of dict
        生成的 QA 对字典列表。
    """
    llm    = LLMClient()
    neo4j  = Neo4jClient(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)
    gen    = GapQAGenerator(llm, neo4j, max_per_edge=max_per_edge)
    return gen.generate_from_gaps(gap_edges, scene_name=scene_name, frame_idx=frame_idx)
