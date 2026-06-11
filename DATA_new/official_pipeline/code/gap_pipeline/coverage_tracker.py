"""
coverage_tracker.py — 三层拓扑覆盖引擎 (V6 - Unified L2)

核心原则：拓扑即等级
  - Gap 的等级由图谱中的拓扑模式决定（节点/边/路径），
    而不是由求解该 Gap 所用的约束方法决定。

V6 覆盖基本单元（统一L2定义）
────────────────
  L0  (Node)     : key = "node_id"
  L1  (Edge)     : key = "src_id->tgt_id"
  L2  (Path)     : key = "min(A,C)|B|max(A,C)"  结构 A—B—C 两跳三节点路径
                   B 是 pivot；A/C 首尾按字典序规范化
                   **不再区分L2A/L2B**，统一为L2

级联更新规则（Footprint）
  L2  命中 → 同时更新 L1(A→B)、L1(B→C)、L0(A,B,C)
  L1  命中 → 同时更新 L0(src, tgt)
  L0  命中 → 仅更新该节点

覆盖真实性验证
────────────────
  每次记录覆盖时，验证查询结果是否真实命中目标路径：
  - 检查Cypher查询是否包含目标节点
  - 验证返回结果是否匹配预期路径
  - 区分"结构命中"和"语义命中"
  - candidates/siblings/referents 只是约束证据，不直接计入 coverage
  - exist/count fallback 不能绕过目标节点验证，否则会造成覆盖率虚高
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Collection, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# 存在性探测：无向匹配（pivot 语义：a-b 和 b-c 各有边即可）
_L2_PATH_EXISTS_CYPHER = """
MATCH (a:Object {unique_id:$n1})-[:RELATES_TO]-(b:Object {unique_id:$n2})
      -[:RELATES_TO]-(c:Object {unique_id:$n3})
RETURN 1 AS ok LIMIT 1
"""


# ─────────────────────────────────────────────────────────────────────────────
# CoverageRecord
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CoverageRecord:
    hit_count:    int       = 0
    template_ids: List[str] = field(default_factory=list)
    question_ids: List[str] = field(default_factory=list)

    def mark(self, template_id: str = "", question_id: str = "") -> None:
        self.hit_count += 1
        if template_id:
            self.template_ids.append(template_id)
        if question_id:
            self.question_ids.append(question_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hit_count":    self.hit_count,
            "template_ids": self.template_ids,
            "question_ids": self.question_ids,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Key constructors
# ─────────────────────────────────────────────────────────────────────────────

def _l0_key(node_id: str) -> str:
    """L0 key: node_id"""
    return node_id


def _l1_key(src_id: str, tgt_id: str) -> str:
    """L1 key: src_id->tgt_id (统一使用->分隔符)"""
    return f"{src_id}->{tgt_id}"


def _l1_key_normalized(src_id: str, tgt_id: str) -> str:
    """L1 key (normalized): 按字典序排序，实现无向边

    a->b 和 b->a 都规范化为字典序较小的形式
    """
    if src_id <= tgt_id:
        return f"{src_id}->{tgt_id}"
    else:
        return f"{tgt_id}->{src_id}"


def _l2_key(n1: str, n2: str, n3: str) -> str:
    """L2 key (legacy chain): A->B->C"""
    return f"{n1}->{n2}->{n3}"


def _l2_key_normalized(n1: str, n2: str, n3: str) -> str:
    """L2 key (legacy chain, normalized): 按首尾节点字典序"""
    if n1 <= n3:
        return f"{n1}->{n2}->{n3}"
    else:
        return f"{n3}->{n2}->{n1}"


def _l2_key_pivot(a: str, b: str, c: str) -> str:
    """L2 pivot key: a|b|c  (b=pivot, a/c 按字典序规范化)

    a|b|c 与 c|b|a 是同一个缺口 → 规范化为 min(a,c)|b|max(a,c)
    """
    lo, hi = (a, c) if a <= c else (c, a)
    return f"{lo}|{b}|{hi}"


def _parse_pivot_key(key: str) -> Tuple[str, str, str]:
    """解析 pivot key 'a|b|c' → (a, b, c)"""
    parts = key.split("|")
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    return "", "", ""


def _enumerate_l2_pivots_from_edges(
    edges: List[Tuple[str, str]],
    node_meta: Dict[str, Dict],
) -> Dict[str, Dict]:
    """从边列表内存穷举所有 L2 pivot gaps。

    L2 缺口 = a|b|c: b 是枢纽, 边(a,b)和(b,c)各存在至少一条。
    a≠c 且 a|b|c 与 c|b|a 是同一缺口。
    总数量级: n*(n-1)*(n-2)/2

    Args:
        edges: 无向边列表 [(u, v), ...] (已去重，含双向)
        node_meta: node_id → {type, status, ...}

    Returns:
        pivot_key → meta dict
    """
    # 构建邻接表
    neighbors: Dict[str, Set[str]] = {}
    for u, v in edges:
        neighbors.setdefault(u, set()).add(v)
        neighbors.setdefault(v, set()).add(u)

    pivots: Dict[str, Dict] = {}
    for b, nbrs in neighbors.items():
        nbr_list = sorted(nbrs)
        for i in range(len(nbr_list)):
            for j in range(i + 1, len(nbr_list)):
                a, c = nbr_list[i], nbr_list[j]
                key = _l2_key_pivot(a, b, c)
                if key not in pivots:
                    pivots[key] = {
                        "a_id": a, "b_id": b, "c_id": c,
                        "a_type": node_meta.get(a, {}).get("type", ""),
                        "a_status": node_meta.get(a, {}).get("status", ""),
                        "b_type": node_meta.get(b, {}).get("type", ""),
                        "b_status": node_meta.get(b, {}).get("status", ""),
                        "c_type": node_meta.get(c, {}).get("type", ""),
                        "c_status": node_meta.get(c, {}).get("status", ""),
                    }
    return pivots


# ─────────────────────────────────────────────────────────────────────────────
# CoverageTracker
# ─────────────────────────────────────────────────────────────────────────────

class CoverageTracker:
    """
    三层拓扑覆盖引擎。

    Usage
    -----
    tracker = CoverageTracker()
    with driver.session() as sess:
        tracker.init_from_session(sess)

    # after generating QA pairs:
    tracker.record_from_qa(qa)        # cascaded update
    print(tracker.stats())
    gaps_l2 = tracker.get_gap_cells("L2")
    """

    def __init__(self) -> None:
        self._L0:  Dict[str, CoverageRecord] = {}   # node_id → record
        self._L1:  Dict[str, CoverageRecord] = {}   # "src->tgt" → record
        self._L2:  Dict[str, CoverageRecord] = {}   # "A->B->C" → record (统一L2)
        # Metadata for gap cell reconstruction
        self._L0_meta:  Dict[str, Dict] = {}
        self._L1_meta:  Dict[str, Dict] = {}
        self._L2_meta:  Dict[str, Dict] = {}
        # Original direction tracking for audit
        self._L1_original_directions: Dict[str, List[Tuple[str, str]]] = {}
        self._L2_original_directions: Dict[str, List[Tuple[str, str, str]]] = {}

    def _l2_chain_exists(self, session, n1: str, n2: str, n3: str) -> bool:
        if not (n1 and n2 and n3):
            return False
        rec = session.run(
            _L2_PATH_EXISTS_CYPHER,
            n1=n1,
            n2=n2,
            n3=n3,
        ).single()
        return rec is not None

    def _prune_phantom_l2_paths(self, session) -> int:
        """
        移除在当前 Neo4j 图上无法匹配「n1→n2→n3」两跳 RELATES_TO 的 L2 记录。
        防御 meta/枚举与瞬时图状态不一致。

        Returns:
            移除的L2路径数量
        """
        n_removed = 0
        for key in list(self._L2.keys()):
            parts = key.split("->")
            if len(parts) != 3:
                continue
            n1, n2, n3 = parts
            if self._l2_chain_exists(session, n1, n2, n3):
                continue
            self._L2.pop(key, None)
            self._L2_meta.pop(key, None)
            n_removed += 1
        return n_removed

    # ── Initialisation ───────────────────────────────────────────────────────

    def init_from_session(self, session) -> None:
        """
        Query Neo4j for all nodes / edges / L2 paths and initialise
        every coverage entry to hit_count=0.

        Must be called once before gap detection.
        """
        # ── L0 + L1: all directed edges ─────────────────────────────────────
        edge_cypher = """
MATCH (s:Object)-[r:RELATES_TO]->(t:Object)
RETURN
  s.unique_id AS src_id,  s.type AS src_type,  coalesce(s.status,'') AS src_status,
  t.unique_id AS tgt_id,  t.type AS tgt_type,  coalesce(t.status,'') AS tgt_status,
  r.direction_6 AS dir6,
  coalesce(r.predicates[1],'') AS dist_level,  r.distance AS actual_dist
"""
        for rec in session.run(edge_cypher):
            s, t = rec["src_id"], rec["tgt_id"]
            # L0
            meta0 = {"node_id": s, "type": rec["src_type"], "status": rec["src_status"]}
            self._L0.setdefault(_l0_key(s), CoverageRecord())
            self._L0_meta.setdefault(_l0_key(s), meta0)
            meta0t = {"node_id": t, "type": rec["tgt_type"], "status": rec["tgt_status"]}
            self._L0.setdefault(_l0_key(t), CoverageRecord())
            self._L0_meta.setdefault(_l0_key(t), meta0t)
            # L1 - 使用规范化key
            k1 = _l1_key_normalized(s, t)
            self._L1.setdefault(k1, CoverageRecord())
            self._L1_meta.setdefault(k1, {
                "src_id": s, "src_type": rec["src_type"], "src_status": rec["src_status"],
                "tgt_id": t, "tgt_type": rec["tgt_type"], "tgt_status": rec["tgt_status"],
                "dir6": rec["dir6"],
                "dist_level": rec["dist_level"], "actual_dist": rec["actual_dist"],
            })
            # 记录原始方向
            self._L1_original_directions.setdefault(k1, []).append((s, t))

        # ── L2: Pivot 枢纽式 a|b|c（从内存边列表穷举） ─────────────────────
        # 收集所有无向边（用于 pivot 穷举）
        _all_edges: List[Tuple[str, str]] = []
        _edge_seen: Set[Tuple[str, str]] = set()
        for k1 in self._L1:
            parts = k1.split("->")
            if len(parts) == 2:
                u, v = parts
                if (u, v) not in _edge_seen:
                    _edge_seen.add((u, v))
                    _edge_seen.add((v, u))
                    _all_edges.append((u, v))

        # 构建 node_meta
        _node_meta: Dict[str, Dict] = {}
        for nid, meta in self._L0_meta.items():
            _node_meta[nid] = {
                "type": meta.get("type", ""),
                "status": meta.get("status", ""),
            }

        # 穷举 pivot gaps
        pivot_gaps = _enumerate_l2_pivots_from_edges(_all_edges, _node_meta)
        for key, meta in pivot_gaps.items():
            self._L2.setdefault(key, CoverageRecord())
            self._L2_meta.setdefault(key, meta)

        logger.info(
            "CoverageTracker initialised: L0=%d nodes  L1=%d edges  L2=%d paths",
            len(self._L0), len(self._L1), len(self._L2),
        )

    def restore_from_csv(self, scene_id: str, frame_id: int) -> int:
        """
        从 question_answer_our.csv 恢复该帧已生成问题的覆盖信息。
        用于断点续跑时避免重复覆盖相同缺口。

        Returns:
            恢复的问题数量
        """
        try:
            from csv_writer import _get_csv_generated
            import csv
            import json

            csv_path = _get_csv_generated()
            if not csv_path.exists():
                return 0

            restored_count = 0
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 只恢复当前帧的问题
                    if row.get('scene_id') != scene_id or str(row.get('frame_id')) != str(frame_id):
                        continue

                    # 严格断点恢复：只恢复 verify 明确通过且目标节点在 ids 中的记录。
                    # 避免历史 CSV 中的 fallback/non-unique 老记录污染当前 coverage。
                    verify_text = str(row.get('verify_result') or row.get('logic_verification') or '')
                    if '✅' not in verify_text and 'pass' not in verify_text.lower():
                        continue


                    # 构造 QA 对象用于 record_from_qa
                    qa = {
                        'topology_level': row.get('num_hop', ''),  # L0/L1/L2
                        'template_id': row.get('q_type', ''),
                        'question_id': row.get('qa_unique_id', ''),
                    }

                    # 从 l2_paths 恢复 path_pattern
                    l2_paths_str = row.get('l2_paths', '')
                    if l2_paths_str:
                        try:
                            l2_paths = json.loads(l2_paths_str) if isinstance(l2_paths_str, str) else []
                            if l2_paths and len(l2_paths) > 0:
                                # 取第一条路径作为 path_pattern
                                path = l2_paths[0]
                                if isinstance(path, list) and len(path) >= 2:
                                    target_id = str(path[-1])
                                    if target_id not in verify_text:
                                        continue
                                    qa['path_pattern'] = '→'.join(path)
                                    self.record_from_qa(qa)
                                    restored_count += 1
                        except Exception:
                            pass

            if restored_count > 0:
                logger.info(
                    "Restored coverage from CSV: %d questions for %s/frame-%d",
                    restored_count, scene_id, frame_id
                )
            return restored_count

        except Exception as exc:
            logger.warning("Failed to restore coverage from CSV: %s", exc)
            return 0

    # ── Cascaded record ───────────────────────────────────────────────────────

    def record_from_qa(self, qa: Dict[str, Any]) -> None:
        """
        Cascaded coverage update from one QA pair.

        QA must contain:
            topology_level : "L2" | "L1" | "L0"
            path_pattern   : pivot "a|b|c"
            template_id    : template string for audit
            question_id    : UUID for audit
        """
        topology = qa.get("topology_level", "")
        path     = qa.get("path_pattern", "")
        tmpl     = qa.get("template_id", "")
        qid      = qa.get("question_id", "")

        if topology == "L2":
            parts = path.split("|")
            if len(parts) == 3:
                a, b, c = parts
                self._hit(self._L2, _l2_key_pivot(a, b, c), tmpl, qid)
                self._hit(self._L1, _l1_key_normalized(a, b))
                self._hit(self._L1, _l1_key_normalized(b, c))
                for nd in (a, b, c):
                    self._hit(self._L0, _l0_key(nd))

        elif topology == "L1" and "→" in path:
            parts = path.split("→")
            if len(parts) == 2:
                s, t = parts
                self._hit(self._L1, _l1_key_normalized(s, t), tmpl, qid)
                self._hit(self._L0, _l0_key(s))
                self._hit(self._L0, _l0_key(t))

        elif topology == "L0" and path:
            self._hit(self._L0, _l0_key(path), tmpl, qid)

    def record_from_qa_with_candidates(
        self,
        qa: Dict[str, Any],
        candidates: List[Dict],
        ctx: Optional[Dict] = None,
    ) -> None:
        """
        记录真实覆盖。

        注意：candidates/referents 只是约束过程中的干扰项或辅助证据，不能直接算覆盖。
        旧版本会把所有 sibling/referent 也记为覆盖，导致覆盖率虚高但问题并没有真正询问这些 path。
        因此这里仅记录 QA 本身对应的 verified target path；候选对象最多应进入审计日志，不能进入 coverage。
        """
        self.record_from_qa(qa)

    @staticmethod
    def _hit(
        d: Dict[str, CoverageRecord],
        key: str,
        tmpl: str = "",
        qid: str = "",
    ) -> None:
        rec = d.setdefault(key, CoverageRecord())
        rec.mark(tmpl, qid)

    # ── Gap queries ───────────────────────────────────────────────────────────

    def get_gap_cells(self, level: str, limit: int = 0, prioritize_uncovered: bool = True) -> List[Dict[str, Any]]:
        """
        Return uncovered cells at the requested topological level.

        Parameters
        ----------
        level : "L0" | "L1" | "L2"
        limit : max items to return (0 = no limit)
        prioritize_uncovered : if True, sort by hit_count (ascending) to prioritize fresh nodes
        """
        store = {"L0": self._L0, "L1": self._L1, "L2": self._L2}[level]
        meta  = {"L0": self._L0_meta, "L1": self._L1_meta, "L2": self._L2_meta}[level]

        results = []
        for key, rec in store.items():
            if rec.hit_count == 0:
                cell = dict(meta.get(key, {}))
                cell["_level"] = level
                cell["_key"]   = key
                cell["_hit_count"] = rec.hit_count  # 添加覆盖次数用于排序
                if level == "L2":
                    a, b, c = _parse_pivot_key(key)
                    cell["path_pattern"] = f"{a}|{b}|{c}"
                    cell["a_id"] = a
                    cell["b_id"] = b
                    cell["c_id"] = c
                    # Bridge: downstream expects n1_id/n2_id/n3_id
                    cell["n1_id"] = a
                    cell["n2_id"] = b
                    cell["n3_id"] = c
                    cell.setdefault("n1_type", cell.get("a_type", ""))
                    cell.setdefault("n2_type", cell.get("b_type", ""))
                    cell.setdefault("n3_type", cell.get("c_type", ""))
                    cell.setdefault("n1_status", cell.get("a_status", ""))
                    cell.setdefault("n2_status", cell.get("b_status", ""))
                    cell.setdefault("n3_status", cell.get("c_status", ""))
                elif level == "L1":
                    s, t = key.split("->")
                    cell["path_pattern"] = f"{s}→{t}"
                else:
                    cell["path_pattern"] = key
                results.append(cell)

        # 优先选择未覆盖或覆盖次数少的节点
        if prioritize_uncovered and results:
            results.sort(key=lambda x: (x.get("_hit_count", 0), x.get("_key", "")))

        if limit > 0:
            results = results[:limit]
        return results

    # ── Statistics ────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        def _agg(d: Dict[str, CoverageRecord]) -> Dict[str, Any]:
            total   = len(d)
            covered = sum(1 for v in d.values() if v.hit_count > 0)
            return {
                "total":   total,
                "covered": covered,
                "gap":     total - covered,
                "rate":    round(covered / total * 100, 2) if total else 0.0,
            }
        return {
            "L0": _agg(self._L0),
            "L1": _agg(self._L1),
            "L2": _agg(self._L2),
        }

    def coverage_rates(self) -> Dict[str, float]:
        return {k: v["rate"] for k, v in self.stats().items()}

    # ── Coverage authenticity verification ────────────────────────────────────

    def verify_authentic_coverage(
        self,
        session,
        qa: Dict[str, Any],
        cypher_query: str,
        query_results: List[Dict]
    ) -> Dict[str, Any]:
        """
        验证覆盖的真实性

        Returns:
            {
                "is_authentic": bool,
                "structural_match": bool,  # Cypher包含目标节点
                "semantic_match": bool,    # 结果匹配预期路径
                "reason": str
            }
        """
        topology = qa.get("topology_level", "")
        path = qa.get("path_pattern", "")

        if not path or "→" not in path:
            return {"is_authentic": False, "reason": "Invalid path pattern"}

        parts = path.split("→")
        target_nodes = set(parts)

        # 1. 结构匹配：检查Cypher是否包含目标节点
        cypher_lower = cypher_query.lower()
        structural_match = all(
            node.lower() in cypher_lower for node in target_nodes
        )

        # 2. 语义匹配：检查返回结果是否包含目标路径
        semantic_match = False
        if query_results:
            for result in query_results:
                # 提取结果中的节点ID
                result_nodes = set()
                for key, value in result.items():
                    if isinstance(value, str):
                        result_nodes.add(value)
                    elif hasattr(value, 'get') and 'unique_id' in value:
                        result_nodes.add(value['unique_id'])

                # 检查目标节点是否都在结果中
                if target_nodes.issubset(result_nodes):
                    semantic_match = True
                    break

        is_authentic = structural_match and semantic_match

        reason = ""
        if not structural_match:
            reason = "Cypher query does not contain target nodes"
        elif not semantic_match:
            reason = "Query results do not match target path"
        else:
            reason = "Authentic coverage verified"

        return {
            "is_authentic": is_authentic,
            "structural_match": structural_match,
            "semantic_match": semantic_match,
            "reason": reason
        }

    def record_from_qa_with_verification(
        self,
        session,
        qa: Dict[str, Any],
        cypher_query: str = "",
        query_results: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        带验证的覆盖记录

        Returns:
            验证结果字典
        """
        # 先验证
        verification = self.verify_authentic_coverage(
            session, qa, cypher_query, query_results or []
        )

        # 只有真实覆盖才记录
        if verification["is_authentic"]:
            self.record_from_qa(qa)
            logger.info(
                "Authentic coverage recorded: %s %s",
                qa.get("topology_level"), qa.get("path_pattern")
            )
        else:
            logger.warning(
                "Coverage rejected (not authentic): %s - %s",
                qa.get("path_pattern"), verification["reason"]
            )

        return verification

    # ── Baseline loading (V6) ─────────────────────────────────────────────────

    def load_nuscenes_qa_baseline(
        self,
        qa_file: str,
        scene_name: str = "",
        sample_tokens: Optional[Collection[str]] = None,
    ) -> Dict[str, int]:
        """读入 NuScenes-QA 原题并将其拓扑指纹标记为已覆盖，使后续生成只针对真正缺口。

        支持两种 NuScenes-QA JSON 格式：
          1. 官方格式： {"questions": [{"scene_name":...,"question":...,
               "template_type":..., "node_ids":[...], "edge_pairs":[[s,t],...]}]}
          2. 简化格式： {"qa_pairs": [{"scene_name":...,"cell_info":{...}}]}

        sample_tokens:
          若提供（非 None），只处理 sample_token 落在该集合内的题（用于单帧流水线，
          避免把同场景其它帧的 footprint 标进当前帧的 tracker）。

        Returns: dict of {"n_L0":int, "n_L1":int, "n_L2":int} loaded.
        """
        import json, pathlib
        path = pathlib.Path(qa_file)
        if not path.exists():
            logger.warning("baseline file not found: %s", qa_file)
            return {}

        data = json.loads(path.read_text(encoding="utf-8"))
        n_l0 = n_l1 = n_l2 = 0
        tmpl  = "nuscenes_qa_baseline"
        qid   = "baseline"
        tok_filter: Optional[Set[str]] = None
        if sample_tokens is not None:
            tok_filter = {str(t).strip() for t in sample_tokens if str(t).strip()}

        # 格式 1： 官方格式
        questions = data.get("questions") or data.get("qa_pairs", [])
        for q in questions:
            # 屏蔽其他场景
            if scene_name and q.get("scene_name","") != scene_name:
                continue
            if tok_filter is not None:
                qt = str(q.get("sample_token", "") or "").strip()
                if qt not in tok_filter:
                    continue

            # L0：直接提供 node_ids
            for nid in q.get("node_ids", []):
                if nid:
                    self._hit(self._L0, _l0_key(str(nid)), tmpl, qid)
                    n_l0 += 1

            # L1： edge_pairs or cell_info.src/tgt
            for ep in q.get("edge_pairs", []):
                if len(ep) >= 2:
                    s, t = str(ep[0]), str(ep[1])
                    self._hit(self._L1, _l1_key(s, t), tmpl, qid)
                    self._hit(self._L0, _l0_key(s))
                    self._hit(self._L0, _l0_key(t))
                    n_l1 += 1

            # cell_info format (our own QA)
            ci = q.get("cell_info", {})
            s  = ci.get("src_id", "")
            t  = ci.get("tgt_id", "")
            if s and t:
                self._hit(self._L1, _l1_key(s, t), tmpl, qid)
                self._hit(self._L0, _l0_key(s))
                self._hit(self._L0, _l0_key(t))
                n_l1 += 1

            # L2 path_pattern
            pp = q.get("path_pattern", "")
            topo = q.get("topology_level", "")
            if pp and topo in ("L2", "L2A", "L2B"):
                self.record_from_qa({"topology_level": "L2", "path_pattern": pp,
                                     "template_id": tmpl, "question_id": qid})
                n_l2 += 1

        stats = {"n_L0": n_l0, "n_L1": n_l1, "n_L2": n_l2}
        logger.info(
            "Baseline loaded: %s  L0+=%d  L1+=%d  L2+=%d",
            path.name, n_l0, n_l1, n_l2,
        )
        return stats

    # ── Coverage-priority sort (V6 smart sampling) ────────────────────────────

    def priority_sort_gaps(
        self,
        gaps: List[Dict[str, Any]],
        shuffle_first: bool = True,
    ) -> List[Dict[str, Any]]:
        """覆盖率优先排序：接触最多未覆盖 L0/L1 节点的路径排在前面。

        算法：
          1. 随机洗牌（打破局部遇历领域集中）
          2. 按 gain_score 逆序排列：路径中每有一个 L0 hit_count==0的节点，+1
          效果：同样 50 题中，L1 覆盖的多样性明显提升。
        """
        import random
        if shuffle_first:
            random.shuffle(gaps)

        def _gain(cell: Dict) -> int:
            score = 0
            for nd in (
                cell.get("n1_id",""), cell.get("n2_id",""), cell.get("n3_id","")
            ):
                if nd and self._L0.get(_l0_key(nd), CoverageRecord()).hit_count == 0:
                    score += 1
            return score

        return sorted(gaps, key=_gain, reverse=True)

    def select_gaps_with_priority(
        self,
        topology: str,
        top_k: int = 1,
        adaptive: bool = True
    ) -> List[Tuple[str, Dict, float]]:
        """
        使用优先级评分选择gaps

        优先级评分公式：priority = len(uncovered_l0) × 10 + len(uncovered_l1) × 15
        L1边权重更高，因为边比节点更稀缺

        Args:
            topology: "L0", "L1", or "L2"
            top_k: 返回前k个gap
            adaptive: 是否使用自适应策略（80%高优先级 + 20%随机）

        Returns:
            List of (gap_key, gap_meta, priority_score)
        """
        # 获取所有未覆盖gaps
        gaps = self.get_gap_cells(topology)

        if not gaps:
            return []

        scored_gaps = []
        for gap_dict in gaps:
            gap_key = gap_dict.get("_key", "")

            # 提取路径节点
            path = gap_key
            if "→" in path:
                nodes = path.split("→")
            elif "->" in path:
                nodes = path.split("->")
            else:
                nodes = [path]

            # 计算未覆盖的L0和L1
            uncovered_l0 = []
            for n in nodes:
                if n:
                    key_l0 = _l0_key(n)
                    if key_l0 not in self._L0 or self._L0[key_l0].hit_count == 0:
                        uncovered_l0.append(n)

            uncovered_l1 = []
            if len(nodes) >= 2:
                for i in range(len(nodes) - 1):
                    n1, n2 = nodes[i], nodes[i+1]
                    if n1 and n2 and not self.is_covered_l1(n1, n2):
                        uncovered_l1.append((n1, n2))

            # 优先级评分：L0×10 + L1×15
            priority = len(uncovered_l0) * 10 + len(uncovered_l1) * 15
            scored_gaps.append((gap_key, gap_dict, priority))

        # 排序并选择top_k
        scored_gaps.sort(key=lambda x: x[2], reverse=True)

        if adaptive and len(scored_gaps) > top_k:
            # 自适应策略：前80%高优先级，20%随机
            import random
            high_priority_count = int(top_k * 0.8)
            random_count = top_k - high_priority_count

            result = scored_gaps[:high_priority_count]
            if random_count > 0 and len(scored_gaps) > high_priority_count:
                result.extend(random.sample(
                    scored_gaps[high_priority_count:],
                    min(random_count, len(scored_gaps) - high_priority_count)
                ))
            return result

        return scored_gaps[:top_k]

    def is_covered_l1(self, n1: str, n2: str) -> bool:
        """检查L1边是否已覆盖（考虑规范化）"""
        key = _l1_key_normalized(n1, n2)
        return key in self._L1 and self._L1[key].hit_count > 0

    def is_covered_l0(self, node_id: str) -> bool:
        """检查L0节点是否已覆盖"""
        key = _l0_key(node_id)
        return key in self._L0 and self._L0[key].hit_count > 0

    # ── V7 Pivot L2: Coverage level & tiered selection ─────────────────────

    def _compute_coverage_level(self, pivot_key: str) -> int:
        """计算 pivot gap 的覆盖等级 (0-5)

        | 等级 | 未覆盖L0 | 未覆盖L1 |
        |------|---------|----------|
        | 5    | 3       | 2        |
        | 4    | 2       | 2        |
        | 3    | ≥1      | 2        |
        | 2    | 0       | 2        |
        | 1    | ≥1      | ≤1       |
        | 0    | 0       | ≤1       |
        """
        a, b, c = _parse_pivot_key(pivot_key)
        if not a or not b or not c:
            return 0

        unc_l0 = sum(
            1 for n in (a, b, c) if not self.is_covered_l0(n)
        )
        unc_l1 = sum(
            1 for pair in ((a, b), (b, c))
            if not self.is_covered_l1(*pair)
        )

        if unc_l0 == 3 and unc_l1 == 2:
            return 5
        if unc_l0 == 2 and unc_l1 == 2:
            return 4
        if unc_l0 >= 1 and unc_l1 == 2:
            return 3
        if unc_l0 == 0 and unc_l1 == 2:
            return 2
        if unc_l0 >= 1 and unc_l1 <= 1:
            return 1
        return 0

    def select_next_gap_tiered(self, limit: int = 1) -> List[Dict[str, Any]]:
        """分档 gap 选择：打乱 + 按覆盖等级 early-exit

        算法：
        1. 收集所有未覆盖 L2 gaps
        2. random.shuffle 打破局部聚集
        3. 计算每个 gap 的覆盖等级
        4. 找到当前最高可用等级 → early_exit_threshold
        5. 线性扫描，遇到 ≥ threshold 的立刻收集
        6. 返回前 limit 个

        Returns:
            List of gap cell dicts with _level, _key, _coverage_level, path_pattern etc.
        """
        uncovered = []
        for key, rec in self._L2.items():
            if rec.hit_count == 0:
                uncovered.append(key)

        if not uncovered:
            return []

        random.shuffle(uncovered)

        # 计算所有 gap 的等级
        levels = {k: self._compute_coverage_level(k) for k in uncovered}
        max_level = max(levels.values()) if levels else 0
        threshold = min(max_level, 5)

        # 按等级降序收集
        selected = []
        for key in uncovered:
            if levels[key] >= threshold:
                meta = self._L2_meta.get(key, {})
                cell = dict(meta)
                cell["_level"] = "L2"
                cell["_key"] = key
                cell["_coverage_level"] = levels[key]
                a, b, c = _parse_pivot_key(key)
                cell["path_pattern"] = f"{a}|{b}|{c}"
                # 保留三节点 id 便于后续使用
                cell["a_id"] = a
                cell["b_id"] = b
                cell["c_id"] = c
                selected.append(cell)
                if len(selected) >= limit:
                    break

        return selected
