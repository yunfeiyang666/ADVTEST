"""
场景覆盖率计算模块

两套覆盖模式：

1. Cell 级 KV map （新模式，推荐）
   CoverageMap 按 (src_type, src_status, tgt_type, tgt_status, dir4, dist_level)
   展开 L0/L1/L2 三层覆盖单元；增量更新通过 QA 的 cell_info 字段完成。
   入口： SceneCoverageCalculator.build_coverage_map(llm_client)

2. 边对级 （旧模式，向下兼容）
   对每个 QA 的每个 (anchor, direction) 组合，在 Neo4j 中查询实际被
   对应方向指向的所有 target.unique_id，组成 (anchor, target) 覆盖集。
   入口： SceneCoverageCalculator.calculate_coverage(qa_pairs) / get_gap_edges()
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# 边对类型别名
EdgePair = Tuple[str, str]  # (source_unique_id, target_unique_id)


# ─────────────────────────────────────────────────────────────────────────────
# Cell 级 KV 覆盖地图
# ─────────────────────────────────────────────────────────────────────────────

class CoverageMap:
    """Cell 级 KV 覆盖计数表（{cell_key: count}）。

    层级设计：
      L0  — (tgt_type, tgt_status)                   目标对象类型/状态
      L1  — (src_type, src_status, tgt_type,           六维完整 cell
              tgt_status, dir4, dist_level)
      L2A — (anc_type, anc_status, src_type,           前置链 ancestor→src→tgt
              src_status, dir_as, dir_st)
      L2B — (src_type, src_status, tgt_type,           后置链 src→tgt→beyond
              tgt_status, dir_st, beyond_type,
              beyond_status, dir_tb)

    L0/L1 的 _totals 在 init_from_records() 时由场景分析 Cypher 写入；
    L2A/L2B 仅在 QA 生成时动态累积 counts，无需预设 totals。
    """

    def __init__(self):
        self._counts: Dict[tuple, int] = {}
        self._totals: Dict[tuple, int] = {}  # 仅 L0/L1

    # ── key 构造器 ────────────────────────────────────────────────────────────

    @staticmethod
    def _l0_key(tgt_type: str, tgt_status: str) -> tuple:
        return ("L0", tgt_type, tgt_status)

    @staticmethod
    def _l1_key(
        src_type: str, src_status: str,
        tgt_type: str, tgt_status: str,
        dir4: str, dist_level: str,
    ) -> tuple:
        return ("L1", src_type, src_status, tgt_type, tgt_status, dir4, dist_level)

    @staticmethod
    def _l2a_key(
        anc_type: str, anc_status: str,
        src_type: str, src_status: str,
        dir_as: str, dir_st: str,
    ) -> tuple:
        return ("L2A", anc_type, anc_status, src_type, src_status, dir_as, dir_st)

    @staticmethod
    def _l2b_key(
        src_type: str, src_status: str,
        tgt_type: str, tgt_status: str,
        dir_st: str, beyond_type: str, beyond_status: str, dir_tb: str,
    ) -> tuple:
        return ("L2B", src_type, src_status, tgt_type, tgt_status,
                dir_st, beyond_type, beyond_status, dir_tb)

    # ── 初始化 ────────────────────────────────────────────────────────────────

    def init_from_records(self, records: List[Dict[str, Any]]) -> None:
        """从场景分析 Cypher 结果初始化 L0/L1 的 totals 和 counts(=0)。

        records 字段: src_type, src_status, tgt_type, tgt_status,
                      dir4, dist_level, edge_count
        """
        for rec in records:
            src_type   = rec.get("src_type",   "")
            src_status = rec.get("src_status", "")
            tgt_type   = rec.get("tgt_type",   "")
            tgt_status = rec.get("tgt_status", "")
            dir4       = rec.get("dir4",       "")
            dist_level = rec.get("dist_level", "")
            edge_count = int(rec.get("edge_count", 1))

            l1 = self._l1_key(src_type, src_status, tgt_type, tgt_status, dir4, dist_level)
            self._totals[l1]  = self._totals.get(l1, 0) + edge_count
            self._counts.setdefault(l1, 0)

            l0 = self._l0_key(tgt_type, tgt_status)
            self._totals[l0]  = self._totals.get(l0, 0) + edge_count
            self._counts.setdefault(l0, 0)

    # ── 增量更新 ──────────────────────────────────────────────────────────────

    def update(self, qa_pair: Dict[str, Any]) -> None:
        """根据一道 QA 对的 cell_info 增量更新覆盖计数。

        始终更新 L1 + L0；若 difficulty=="L2" 且 cell_info 含链字段，
        同步更新 L2A/L2B。
        """
        ci = qa_pair.get("cell_info", {})
        if not ci:
            return

        src_type   = ci.get("src_type",   "")
        src_status = ci.get("src_status", "")
        tgt_type   = ci.get("tgt_type",   "")
        tgt_status = ci.get("tgt_status", "")
        dir4       = ci.get("dir4",       "")
        dist_level = ci.get("dist_level", "")

        l1 = self._l1_key(src_type, src_status, tgt_type, tgt_status, dir4, dist_level)
        self._counts[l1] = self._counts.get(l1, 0) + 1

        l0 = self._l0_key(tgt_type, tgt_status)
        self._counts[l0] = self._counts.get(l0, 0) + 1

        if qa_pair.get("difficulty", "") == "L2":
            anc_type      = ci.get("anc_type",      "")
            anc_status    = ci.get("anc_status",    "")
            dir_as        = ci.get("dir_as",        "")
            dir_st        = ci.get("dir_st",        "")
            beyond_type   = ci.get("beyond_type",   "")
            beyond_status = ci.get("beyond_status", "")
            dir_tb        = ci.get("dir_tb",        "")

            if anc_type:
                l2a = self._l2a_key(anc_type, anc_status, src_type, src_status, dir_as, dir_st)
                self._counts[l2a] = self._counts.get(l2a, 0) + 1

            if beyond_type:
                l2b = self._l2b_key(src_type, src_status, tgt_type, tgt_status,
                                    dir_st, beyond_type, beyond_status, dir_tb)
                self._counts[l2b] = self._counts.get(l2b, 0) + 1

    # ── 查询接口 ──────────────────────────────────────────────────────────────

    def get_gap_cells(self, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """返回尚未被覆盖（count == 0）的 cell 列表。

        Parameters
        ----------
        level : None | "L0" | "L1" | "L2A" | "L2B"
            过滤层级；None 返回所有层级中 count==0 的 cell。
        """
        result = []
        for key, cnt in self._counts.items():
            if cnt > 0:
                continue
            cell_level = key[0]
            if level and cell_level != level:
                continue
            result.append(self._key_to_dict(key))
        return result

    @staticmethod
    def _key_to_dict(key: tuple) -> Dict[str, Any]:
        """将 cell tuple 解包为描述 dict。"""
        level = key[0]
        if level == "L0":
            _, tgt_type, tgt_status = key
            return {"level": "L0", "tgt_type": tgt_type, "tgt_status": tgt_status}
        if level == "L1":
            _, src_type, src_status, tgt_type, tgt_status, dir4, dist_level = key
            return {
                "level": "L1",
                "src_type": src_type, "src_status": src_status,
                "tgt_type": tgt_type, "tgt_status": tgt_status,
                "dir4": dir4, "dist_level": dist_level,
            }
        if level == "L2A":
            _, anc_type, anc_status, src_type, src_status, dir_as, dir_st = key
            return {
                "level": "L2A",
                "anc_type": anc_type, "anc_status": anc_status,
                "src_type": src_type, "src_status": src_status,
                "dir_as": dir_as, "dir_st": dir_st,
            }
        if level == "L2B":
            _, src_type, src_status, tgt_type, tgt_status, dir_st, \
                beyond_type, beyond_status, dir_tb = key
            return {
                "level": "L2B",
                "src_type": src_type, "src_status": src_status,
                "tgt_type": tgt_type, "tgt_status": tgt_status,
                "dir_st": dir_st,
                "beyond_type": beyond_type, "beyond_status": beyond_status,
                "dir_tb": dir_tb,
            }
        return {"level": level, "key": list(key)}

    def stats(self) -> Dict[str, Any]:
        """返回各层级覆盖统计。

        每个层级返回：
          covered        — 已被覆盖的 cell 数
          total          — 总 cell 数
          gap            — 未被覆盖的 cell 数
          rate           — cell 覆盖率%
          edge_covered   — 已覆盖边数合计（L0/L1 可用）
          edge_total     — 边总数（_totals 累存）
          edge_rate      — 边数加权覆盖率%
        """
        # Cell 级统计
        agg: Dict[str, Dict[str, int]] = defaultdict(lambda: {"covered": 0, "total": 0})
        for key, cnt in self._counts.items():
            lvl = key[0]
            agg[lvl]["total"] += 1
            if cnt > 0:
                agg[lvl]["covered"] += 1

        # 边数加权统计（仅 L0/L1 有 _totals）
        edge_covered_by_lvl: Dict[str, int] = defaultdict(int)
        edge_total_by_lvl:   Dict[str, int] = defaultdict(int)
        for key, total_edges in self._totals.items():
            lvl = key[0]
            edge_total_by_lvl[lvl] += total_edges
            if self._counts.get(key, 0) > 0:
                edge_covered_by_lvl[lvl] += total_edges

        result: Dict[str, Any] = {}
        for lvl, data in agg.items():
            total   = data["total"]
            covered = data["covered"]
            e_total   = edge_total_by_lvl.get(lvl, 0)
            e_covered = edge_covered_by_lvl.get(lvl, 0)
            result[lvl] = {
                "covered":      covered,
                "total":        total,
                "gap":          total - covered,
                "rate":         round(covered   / total   * 100, 2) if total   > 0 else 0.0,
                "edge_covered": e_covered,
                "edge_total":   e_total,
                "edge_rate":    round(e_covered / e_total * 100, 2) if e_total > 0 else 0.0,
            }
        return result


# ─────────────────────────────────────────────────────────────────────────────
# 主计算器
# ─────────────────────────────────────────────────────────────────────────────

class SceneCoverageCalculator:
    """场景覆盖率计算器（Neo4j精确模式）。

    Parameters
    ----------
    neo4j_driver :
        已初始化的 Neo4j driver 实例。
    """

    def __init__(self, neo4j_driver):
        if neo4j_driver is None:
            raise ValueError("neo4j_driver 不能为 None，覆盖率计算必须连接 Neo4j。")
        self._driver = neo4j_driver

    def close(self):
        """关闭 Neo4j 连接。"""
        self._driver.close()

    def calculate_coverage(
        self,
        qa_pairs: List[Any],
    ) -> Dict[str, Any]:
        """计算 QA 对列表对场景图的边覆盖率。

        对每个 QA 的每个 (anchor, direction) 组合，执行
        ``cypher_find_covered_edge_ids()`` 在 Neo4j 中查询实际被指向的
        target.unique_id，组成覆盖边对集合，无本地推断。

        Parameters
        ----------
        qa_pairs : List[QAPair | dict]
            生成器输出的问答对列表。

        Returns
        -------
        dict
            覆盖率统计字典，包含 total_edges / covered_edges /
            coverage_rate / covered_edge_ids / question_coverage / summary。
        """
        from .cypher_generator import cypher_find_covered_edge_ids  # type: ignore

        covered_set: Set[EdgePair] = set()
        question_details = []

        with self._driver.session() as session:
            total_edges: int = session.run(
                "MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS c"
            ).single()["c"]

            for i, qa in enumerate(qa_pairs):
                q_text, q_id, ref_objs, directions = self._unpack_qa_for_coverage(qa, i)
                qa_edges: Set[EdgePair] = set()

                for anchor_id, direction in zip(ref_objs, directions):
                    try:
                        cypher = cypher_find_covered_edge_ids(anchor_id, direction)
                        for record in session.run(cypher):
                            target_uid = record.get("target_id")
                            if target_uid:
                                qa_edges.add((anchor_id, target_uid))
                    except Exception as exc:
                        logger.debug(
                            "coverage query error anchor=%s dir=%s: %s",
                            anchor_id, direction, exc,
                        )

                covered_set.update(qa_edges)
                question_details.append({
                    "question_id": q_id,
                    "question": q_text,
                    "covered_edges_count": len(qa_edges),
                    "covered_edge_ids": list(qa_edges),
                })

        coverage_rate = (
            round(len(covered_set) / total_edges * 100, 2) if total_edges > 0 else 0.0
        )
        return {
            "total_edges": total_edges,
            "covered_edges": len(covered_set),
            "uncovered_edges": max(0, total_edges - len(covered_set)),
            "coverage_rate": coverage_rate,
            "covered_edge_ids": list(covered_set),
            "question_coverage": question_details,
            "summary": {
                "total_questions": len(qa_pairs),
                "questions_with_coverage": sum(
                    1 for q in question_details if q["covered_edges_count"] > 0
                ),
            },
        }

    # ── CoverageMap 构建 ─────────────────────────────────────────────────────

    def build_coverage_map(self, llm_client) -> CoverageMap:
        """调用 LLM 生成场景分析 Cypher，执行并初始化 CoverageMap。

        Parameters
        ----------
        llm_client : LLMClient
            已初始化的大模型客户端，需实现 generate_scene_analysis_cypher()。

        Returns
        -------
        CoverageMap
            已用场景图边统计数据初始化的覆盖地图。
        """
        cypher = llm_client.generate_scene_analysis_cypher()
        logger.debug("场景分析 Cypher:\n%s", cypher)
        with self._driver.session() as session:
            records = [dict(rec) for rec in session.run(cypher)]
        cmap = CoverageMap()
        cmap.init_from_records(records)
        l1_cnt = sum(1 for k in cmap._counts if k[0] == "L1")
        logger.info("CoverageMap 初始化完成: %d L1 cells", l1_cnt)
        return cmap

    def get_gap_cells(
        self,
        coverage_map: CoverageMap,
        level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """返回 coverage_map 中尚未覆盖的 cell 列表。

        Parameters
        ----------
        coverage_map : CoverageMap
            已初始化的覆盖地图。
        level : None | "L0" | "L1" | "L2A" | "L2B"
            过滤层级；None 返回所有层级。
        """
        return coverage_map.get_gap_cells(level=level)

    # ── 旧接口：边级缺口检测（保持向下兼容）────────────────────────────────────

    def get_gap_edges(
        self,
        covered_edge_ids: List[EdgePair],
    ) -> List[Dict[str, Any]]:
        """在 Neo4j 中查询未被任何 QA 覆盖的场景图边（缺口边）。

        Parameters
        ----------
        covered_edge_ids : list of (source_id, target_id)
            已覆盖边列表。

        Returns
        -------
        list of dict
            每条记录包含 ``source``, ``target``, ``dir4``,
            ``predicates``, ``distance`` 字段，按距离升序排列。
        """
        from .cypher_generator import cypher_gap_find_uncovered_edges  # type: ignore

        cypher = cypher_gap_find_uncovered_edges(covered_edge_ids)
        with self._driver.session() as session:
            return [dict(record) for record in session.run(cypher)]

    # ── 内部辅助 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _unpack_qa_for_coverage(
        qa: Any, fallback_idx: int
    ) -> Tuple[str, str, List[str], List[str]]:
        """(问题文本, question_id, reference_objects, directions_used)。"""
        if hasattr(qa, "question"):
            return (
                qa.question,
                qa.question_id,
                list(qa.reference_objects),
                list(qa.directions_used),
            )
        return (
            qa.get("question", ""),
            qa.get("question_id", str(fallback_idx + 1)),
            list(qa.get("reference_objects", [])),
            list(qa.get("directions_used", [])),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 便捷函数
# ─────────────────────────────────────────────────────────────────────────────

def calculate_scene_coverage(
    qa_pairs: List[Any],
    neo4j_uri: str = "bolt://localhost:7600",
    neo4j_user: str = "neo4j",
    neo4j_password: str = "12345678",
) -> Dict[str, Any]:
    """便捷函数：连接 Neo4j 计算场景覆盖率。

    Parameters
    ----------
    qa_pairs : list
        QAPair 对象列表（dataclass 或 dict）。
    neo4j_uri / neo4j_user / neo4j_password :
        Neo4j 连接参数。
    """
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    calc = SceneCoverageCalculator(neo4j_driver=driver)
    try:
        return calc.calculate_coverage(qa_pairs)
    finally:
        calc.close()
