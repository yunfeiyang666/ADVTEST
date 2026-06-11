"""
coverage_tracker.py — 三层拓扑覆盖引擎 (V5)

核心原则：拓扑即等级
  - Gap 的等级由图谱中的拓扑模式决定（节点/边/路径），
    而不是由求解该 Gap 所用的约束方法决定。

V5 覆盖基本单元
────────────────
  L0  (Node)     : key = "node_id"
  L1  (Edge)     : key = "src_id|tgt_id"
  L2A (Ego-Anchor): key = "ego|A|B"    结构 ego→A→B
                   主车起始锚点链
  L2B (Obj-Chain): key = "A|B|C"     结构 A→B→C，**起点 A 必须非 ego**（与 L2A 区分）；
                   **B、C 允许为 ego**，从而覆盖如 A→ego→C、A→B→ego，利于 L1 与「指向主车」边对齐。

级联更新规则（Footprint）
  L2A 命中 → 同时更新 L1(ego→A)、L1(A→B)、L0(ego,A,B)
  L2B 命中 → 同时更新 L1(A→B)、L1(B→C)、L0(A,B,C)
  L1  命中 → 同时更新 L0(src, tgt)
  L0  命中 → 仅更新该节点
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Collection, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_L2_PATH_EXISTS_CYPHER = """
MATCH (a:Object {unique_id:$n1})-[:RELATES_TO]->(b:Object {unique_id:$n2})
      -[:RELATES_TO]->(c:Object {unique_id:$n3})
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
    return node_id


def _l1_key(src_id: str, tgt_id: str) -> str:
    return f"{src_id}|{tgt_id}"


def _l2a_key(ego: str, a: str, b: str) -> str:
    """ego→A→B anchor chain."""
    return f"{ego}|{a}|{b}"


def _l2b_key(n1: str, n2: str, n3: str) -> str:
    """A→B→C object chain (V5): sequential, no ego, order preserved."""
    return f"{n1}|{n2}|{n3}"


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
    gaps_l2a = tracker.get_gap_cells("L2A")
    """

    def __init__(self) -> None:
        self._L0:  Dict[str, CoverageRecord] = {}   # node_id → record
        self._L1:  Dict[str, CoverageRecord] = {}   # "src|tgt" → record
        self._L2A: Dict[str, CoverageRecord] = {}   # "ego|A|B" → record (V5)
        self._L2B: Dict[str, CoverageRecord] = {}   # "A|B|C" → record（A≠ego；B/C 可为 ego）
        # Metadata for gap cell reconstruction
        self._L0_meta:  Dict[str, Dict] = {}
        self._L1_meta:  Dict[str, Dict] = {}
        self._L2A_meta: Dict[str, Dict] = {}
        self._L2B_meta: Dict[str, Dict] = {}

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

    def _prune_phantom_l2_paths(self, session) -> Tuple[int, int]:
        """
        移除在当前 Neo4j 图上无法匹配「n1→n2→n3」两跳 RELATES_TO 的 L2 记录。
        """
        n_a = n_b = 0
        for key in list(self._L2A.keys()):
            parts = key.split("|")
            if len(parts) != 3:
                continue
            n1, n2, n3 = parts
            if self._l2_chain_exists(session, n1, n2, n3):
                continue
            self._L2A.pop(key, None)
            self._L2A_meta.pop(key, None)
            n_a += 1
        for key in list(self._L2B.keys()):
            parts = key.split("|")
            if len(parts) != 3:
                continue
            n1, n2, n3 = parts
            if self._l2_chain_exists(session, n1, n2, n3):
                continue
            self._L2B.pop(key, None)
            self._L2B_meta.pop(key, None)
            n_b += 1
        return n_a, n_b

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
  r.direction_4 AS dir4,  r.direction_8 AS dir8,
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
            # L1
            k1 = _l1_key(s, t)
            self._L1.setdefault(k1, CoverageRecord())
            self._L1_meta.setdefault(k1, {
                "src_id": s, "src_type": rec["src_type"], "src_status": rec["src_status"],
                "tgt_id": t, "tgt_type": rec["tgt_type"], "tgt_status": rec["tgt_status"],
                "dir4": rec["dir4"], "dir8": rec["dir8"],
                "dist_level": rec["dist_level"], "actual_dist": rec["actual_dist"],
            })

        # ── L2A: ego→A→B paths ───────────────────────────────────────────────
        l2a_cypher = """
MATCH (ego:Object {unique_id: 'ego'})-[r1:RELATES_TO]->(a:Object)-[r2:RELATES_TO]->(b:Object)
WHERE b.unique_id <> 'ego' AND a.unique_id <> 'ego'
RETURN
  'ego'            AS n1_id, 'ego'        AS n1_type,
  a.unique_id      AS n2_id, a.type       AS n2_type, coalesce(a.status,'') AS n2_status,
  b.unique_id      AS n3_id, b.type       AS n3_type, coalesce(b.status,'') AS n3_status,
  r1.direction_4   AS r1_dir4, r1.direction_8 AS r1_dir8,
  coalesce(r1.predicates[1],'') AS r1_dist, r1.distance AS r1_actual_dist,
  r2.direction_4   AS r2_dir4, r2.direction_8 AS r2_dir8,
  coalesce(r2.predicates[1],'') AS r2_dist, r2.distance AS r2_actual_dist
"""
        for rec in session.run(l2a_cypher):
            k = _l2a_key(rec["n1_id"], rec["n2_id"], rec["n3_id"])
            self._L2A.setdefault(k, CoverageRecord())
            self._L2A_meta.setdefault(k, dict(rec))

        # ── L2B: A→B→C，A 非 ego（与 L2A=ego→*→* 不重复）；B、C 可为 ego，覆盖更多 L1 边
        l2b_cypher = """
MATCH (a:Object)-[r1:RELATES_TO]->(b:Object)-[r2:RELATES_TO]->(c:Object)
WHERE a.unique_id <> 'ego' AND a.unique_id <> c.unique_id
RETURN
  a.unique_id AS n1_id, a.type AS n1_type, coalesce(a.status,'') AS n1_status,
  b.unique_id AS n2_id, b.type AS n2_type, coalesce(b.status,'') AS n2_status,
  c.unique_id AS n3_id, c.type AS n3_type, coalesce(c.status,'') AS n3_status,
  r1.direction_4 AS r1_dir4, r1.direction_8 AS r1_dir8,
  coalesce(r1.predicates[1],'') AS r1_dist, r1.distance AS r1_actual_dist,
  r2.direction_4 AS r2_dir4, r2.direction_8 AS r2_dir8,
  coalesce(r2.predicates[1],'') AS r2_dist, r2.distance AS r2_actual_dist
LIMIT 3000
"""  # real total (no LIMIT): 238,266 paths in scene-0553 frame-8
        for rec in session.run(l2b_cypher):
            k = _l2b_key(rec["n1_id"], rec["n2_id"], rec["n3_id"])
            self._L2B.setdefault(k, CoverageRecord())
            self._L2B_meta.setdefault(k, dict(rec))

        n_phantom_a, n_phantom_b = self._prune_phantom_l2_paths(session)
        if n_phantom_a or n_phantom_b:
            logger.warning(
                "Pruned phantom L2 paths (no matching 2-hop chain in current graph): "
                "L2A=%d  L2B=%d",
                n_phantom_a,
                n_phantom_b,
            )

        logger.info(
            "CoverageTracker initialised: L0=%d nodes  L1=%d edges  "
            "L2A=%d paths  L2B=%d pairs",
            len(self._L0), len(self._L1), len(self._L2A), len(self._L2B),
        )

    # ── Cascaded record ───────────────────────────────────────────────────────

    def record_from_qa(self, qa: Dict[str, Any]) -> None:
        """
        Cascaded coverage update from one QA pair.

        QA must contain:
            topology_level : "L2A" | "L2B" | "L1" | "L0"
            path_pattern   : e.g. "ego→car9→car35" or "car1←ego→pedestrian2"
            template_id    : template string for audit
            question_id    : UUID for audit
        """
        topology = qa.get("topology_level", "")
        path     = qa.get("path_pattern", "")
        tmpl     = qa.get("template_id", "")
        qid      = qa.get("question_id", "")

        if topology == "L2A" and "→" in path:
            parts = path.split("→")
            if len(parts) == 3:
                n1, n2, n3 = parts
                self._hit(self._L2A, _l2a_key(n1, n2, n3), tmpl, qid)
                self._hit(self._L1,  _l1_key(n1, n2))
                self._hit(self._L1,  _l1_key(n2, n3))
                for nd in (n1, n2, n3):
                    self._hit(self._L0, _l0_key(nd))

        elif topology == "L2B" and path.count("→") == 2:
            # "A→B→C"：A 非 ego；B/C 可为 ego
            parts = path.split("→")
            if len(parts) == 3:
                n1, n2, n3 = parts
                self._hit(self._L2B, _l2b_key(n1, n2, n3), tmpl, qid)
                self._hit(self._L1,  _l1_key(n1, n2))
                self._hit(self._L1,  _l1_key(n2, n3))
                for nd in (n1, n2, n3):
                    self._hit(self._L0, _l0_key(nd))

        elif topology == "L1" and "→" in path:
            parts = path.split("→")
            if len(parts) == 2:
                s, t = parts
                self._hit(self._L1, _l1_key(s, t), tmpl, qid)
                self._hit(self._L0, _l0_key(s))
                self._hit(self._L0, _l0_key(t))

        elif topology == "L0" and path:
            self._hit(self._L0, _l0_key(path), tmpl, qid)

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

    def get_gap_cells(self, level: str, limit: int = 0) -> List[Dict[str, Any]]:
        """
        Return uncovered cells at the requested topological level.

        Parameters
        ----------
        level : "L0" | "L1" | "L2A" | "L2B"
        limit : max items to return (0 = no limit)
        """
        store = {"L0": self._L0, "L1": self._L1,
                 "L2A": self._L2A, "L2B": self._L2B}[level]
        meta  = {"L0": self._L0_meta, "L1": self._L1_meta,
                 "L2A": self._L2A_meta, "L2B": self._L2B_meta}[level]

        results = []
        for key, rec in store.items():
            if rec.hit_count == 0:
                cell = dict(meta.get(key, {}))
                cell["_level"] = level
                cell["_key"]   = key
                if level in ("L2A", "L2B"):   # V5: both use n1→n2→n3 format
                    n1, n2, n3 = key.split("|")
                    cell["path_pattern"] = f"{n1}→{n2}→{n3}"
                elif level == "L1":
                    s, t = key.split("|")
                    cell["path_pattern"] = f"{s}→{t}"
                else:
                    cell["path_pattern"] = key
                results.append(cell)

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
            "L0":  _agg(self._L0),
            "L1":  _agg(self._L1),
            "L2A": _agg(self._L2A),
            "L2B": _agg(self._L2B),
        }

    def coverage_rates(self) -> Dict[str, float]:
        return {k: v["rate"] for k, v in self.stats().items()}

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

            # L2A path_pattern
            pp = q.get("path_pattern", "")
            topo = q.get("topology_level", "")
            if pp and topo in ("L2A", "L2B"):
                self.record_from_qa({"topology_level": topo, "path_pattern": pp,
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
