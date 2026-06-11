"""
l2_chain_generator.py — 真正的链式问题生成器 (V3)

与 V2 的根本区别
─────────────────
  V2: 问的是 "ego→car35" 这条 L1 边，恰好用了 car9 作为求解参照。
      ✗ Gap 是 L1，问题视觉上是 L1，但被错误标为 L2。

  V3: Gap 本身就是一条三节点路径（L2A 或 L2B）。
      ✓ 问题文本必须显式体现两连跳/交互关系，才能被计入 L2 覆盖。

L2A (Anchor Chain):  ego → A → B
  结构语义: "从主车看 A，A 的前方又有什么？"
  示例:  "What {B_type} is to the {r2_dir8} of the {A_type}
          that is to the {r1_dir8} of ego?"
         "What is the status of the {B_type} beyond the {A_type}
          in front of ego?"

L2B (Interaction Chain):  X ← ego → Y
  结构语义: "主车同时观察 X 和 Y，问两者之间的关系/对比"
  示例:  "The {X_type} to the {X_dir} and the {Y_type} to the {Y_dir}
          of ego — which one is {closer/farther}?"
         "Both a {X_type} and a {Y_type} are visible from ego.
          What is the status of the {X_type}?"

每条 QA 必须携带:
    topology_level : "L2A" 或 "L2B"
    path_pattern   : "ego→car9→car35" 或 "car1←ego→pedestrian2"
"""
from __future__ import annotations

import random
import uuid
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# L2A 模板（ego→A→B，两连跳显式）
# ─────────────────────────────────────────────────────────────────────────────

_L2A_TEMPLATES: List[Dict[str, Any]] = [
    # 问 B 的类型（通过 A 定位）
    {
        "id": "L2A:chain_type",
        "difficulty": "hard",
        "answer_type": "open",
        "variants": [
            "What {n3_type} is to the {r2_dir8} of the {n2_type} that is to the {r1_dir8} of ego?",
            "The {n2_type} in the {r1_dir4} of ego has a {n3_type} to its {r2_dir4}. What is that {n3_type}?",
            "Beyond the {n2_type} to ego's {r1_dir8}, what {n3_type} lies to the {r2_dir8}?",
        ],
        "answer_field": "n3_id",
    },
    # 问 B 的状态（通过 A 定位）
    {
        "id": "L2A:chain_status",
        "difficulty": "hard",
        "answer_type": "open",
        "requires": "n3_status",
        "variants": [
            "What is the status of the {n3_type} that is to the {r2_dir8} of the {n2_type} in ego's {r1_dir4}?",
            "The {n2_type} to the {r1_dir8} of ego — what is the status of the {n3_type} behind it?",
            "Behind the {n2_type} ahead of ego, there is a {n3_type}. Is it moving or stopped?",
        ],
        "answer_field": "n3_status",
    },
    # 问到 B 的距离（通过 A 定位，r2_dist 非空时）
    {
        "id": "L2A:chain_dist",
        "difficulty": "hard",
        "answer_type": "open",
        "requires": "r2_dist",
        "variants": [
            "How far is the {n3_type} beyond the {n2_type} to ego's {r1_dir8}? ({r2_dist})",
            "The {n3_type} to the {r2_dir8} of the {n2_type} in ego's {r1_dir4} — is it close or far?",
        ],
        "answer_field": "r2_dist",
    },
    # 问路径中 A 的方向（从 ego 出发）
    {
        "id": "L2A:chain_a_dir",
        "difficulty": "medium",
        "answer_type": "open",
        "variants": [
            "In which direction from ego is the {n2_type} that has a {n3_type} to its {r2_dir4}?",
            "The {n2_type} with a {n3_type} beyond it — in which direction is it from ego?",
        ],
        "answer_field": "r1_dir8",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# L2B 模板（X←ego→Y，ego 作枢纽）
# ─────────────────────────────────────────────────────────────────────────────

_L2B_TEMPLATES: List[Dict[str, Any]] = [
    # 问 A/B 哪个更近（距离比较）
    {
        "id": "L2B:interact_closer",
        "difficulty": "hard",
        "answer_type": "open",
        "requires": "r1_dist_r2_dist",
        "variants": [
            "Of the {a_type} to the {r1_dir4} and the {b_type} to the {r2_dir4} of ego, which is closer?",
            "Ego has a {a_type} to its {r1_dir8} and a {b_type} to its {r2_dir8}. Which one is nearer?",
            "Between the {a_type} ({r1_dist}) and the {b_type} ({r2_dist}) visible from ego, which is closer?",
        ],
        "answer_fn": "closer_of_ab",  # computed from r1_dist vs r2_dist
    },
    # 问 A 的状态（通过 B 锁定 ego 的观测视角）
    {
        "id": "L2B:interact_a_status",
        "difficulty": "hard",
        "answer_type": "open",
        "requires": "a_status",
        "variants": [
            "Ego sees a {b_type} to its {r2_dir4} and a {a_type} to its {r1_dir4}. "
            "What is the status of the {a_type}?",
            "Both a {a_type} and a {b_type} are visible from ego. "
            "The {a_type} is to the {r1_dir8} — what is its status?",
        ],
        "answer_field": "a_status",
    },
    # 问 B 的状态（通过 A 锁定 ego 的观测视角）
    {
        "id": "L2B:interact_b_status",
        "difficulty": "hard",
        "answer_type": "open",
        "requires": "b_status",
        "variants": [
            "Ego sees a {a_type} to its {r1_dir4} and a {b_type} to its {r2_dir4}. "
            "What is the status of the {b_type}?",
            "Both a {a_type} and a {b_type} are visible from ego. "
            "The {b_type} is to the {r2_dir8} — what is its status?",
        ],
        "answer_field": "b_status",
    },
    # 问 B 在哪个方向（给定 A 的方向，利用 ego 枢纽）
    {
        "id": "L2B:interact_b_dir",
        "difficulty": "medium",
        "answer_type": "open",
        "variants": [
            "If ego's {r1_dir4} has a {a_type}, in which direction is the {b_type} from ego?",
            "Given a {a_type} to ego's {r1_dir8}, in what direction does ego see the {b_type}?",
        ],
        "answer_field": "r2_dir8",
    },
]

_DIST_RANK = {"very_close": 0, "close": 1, "medium": 2, "far": 3}


def _rank(dist: str) -> int:
    return _DIST_RANK.get(dist, 99)


def _closer_of_ab(cell: Dict) -> Optional[str]:
    """Which of A or B is closer to ego?  Returns the object's type label."""
    r1 = _rank(cell.get("r1_dist", ""))
    r2 = _rank(cell.get("r2_dist", ""))
    if r1 == 99 or r2 == 99:
        return None
    if r1 < r2:
        return cell.get("a_type", "A")
    elif r2 < r1:
        return cell.get("b_type", "B")
    return None   # tie → skip


# ─────────────────────────────────────────────────────────────────────────────
# L2ChainGenerator
# ─────────────────────────────────────────────────────────────────────────────

class L2ChainGenerator:
    """
    Generate L2 chain QA pairs from gap cells produced by CoverageTracker.

    Each generated QA pair carries:
        topology_level : "L2A" or "L2B"
        path_pattern   : e.g. "ego→car9→car35" or "car1←ego→pedestrian2"
    so that CoverageTracker.record_from_qa() can cascade-update coverage.
    """

    def __init__(self, scene_name: str = "", frame_idx: int = 0) -> None:
        self.scene_name = scene_name
        self.frame_idx  = frame_idx

    # ── L2A ──────────────────────────────────────────────────────────────────

    def generate_l2a(self, cell: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate QA pairs for one L2A gap cell (ego→A→B).

        Parameters
        ----------
        cell : dict
            From CoverageTracker.get_gap_cells("L2A").
            Must contain: n1_id, n2_id/type/status, n3_id/type/status,
            r1_dir4/dir8/dist, r2_dir4/dir8/dist.
        """
        qa_list = []
        path = cell.get("path_pattern", "")

        for tmpl in _L2A_TEMPLATES:
            # Check prerequisite field
            req = tmpl.get("requires")
            if req and not cell.get(req):
                continue

            # Pick a variant and fill
            variant = random.choice(tmpl["variants"])
            try:
                question = variant.format(**cell)
            except (KeyError, ValueError):
                continue

            # Resolve answer
            ans_field = tmpl.get("answer_field", "")
            answer = str(cell.get(ans_field, "")).strip()
            if not answer:
                continue

            qa_list.append(self._make_qa(
                template_id=tmpl["id"],
                difficulty=tmpl["difficulty"],
                answer_type=tmpl["answer_type"],
                question=question,
                answer=answer,
                path_pattern=path,
                topology_level="L2A",
                ref_objects=[cell.get("n1_id", "ego"), cell.get("n2_id", "")],
                tgt_objects=[cell.get("n3_id", "")],
                # Footprint: all 3 nodes
                footprint_nodes=[
                    cell.get("n1_id", "ego"),
                    cell.get("n2_id", ""),
                    cell.get("n3_id", ""),
                ],
            ))

        logger.debug("L2A %s → %d QAs", path, len(qa_list))
        return qa_list

    # ── L2B ──────────────────────────────────────────────────────────────────

    def generate_l2b(self, cell: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate QA pairs for one L2B gap cell (X←ego→Y).

        Parameters
        ----------
        cell : dict
            From CoverageTracker.get_gap_cells("L2B").
            Must contain: a_id/type/status, ego_id, b_id/type/status,
            r1_dir4/dir8/dist, r2_dir4/dir8/dist.
        """
        qa_list = []
        path = cell.get("path_pattern", "")

        for tmpl in _L2B_TEMPLATES:
            req = tmpl.get("requires")
            if req == "r1_dist_r2_dist":
                if not (cell.get("r1_dist") and cell.get("r2_dist")):
                    continue
            elif req and not cell.get(req):
                continue

            variant = random.choice(tmpl["variants"])
            try:
                question = variant.format(**cell)
            except (KeyError, ValueError):
                continue

            # Resolve answer
            ans_fn = tmpl.get("answer_fn")
            ans_field = tmpl.get("answer_field", "")
            if ans_fn == "closer_of_ab":
                answer = _closer_of_ab(cell)
                if answer is None:
                    continue
            else:
                answer = str(cell.get(ans_field, "")).strip()
            if not answer:
                continue

            qa_list.append(self._make_qa(
                template_id=tmpl["id"],
                difficulty=tmpl["difficulty"],
                answer_type=tmpl["answer_type"],
                question=question,
                answer=str(answer),
                path_pattern=path,
                topology_level="L2B",
                ref_objects=["ego"],
                tgt_objects=[cell.get("a_id", ""), cell.get("b_id", "")],
                footprint_nodes=[
                    cell.get("a_id", ""),
                    cell.get("ego_id", "ego"),
                    cell.get("b_id", ""),
                ],
            ))

        logger.debug("L2B %s → %d QAs", path, len(qa_list))
        return qa_list

    # ── Factory ───────────────────────────────────────────────────────────────

    def _make_qa(
        self,
        template_id: str,
        difficulty: str,
        answer_type: str,
        question: str,
        answer: str,
        path_pattern: str,
        topology_level: str,
        ref_objects: List[str],
        tgt_objects: List[str],
        footprint_nodes: List[str],
    ) -> Dict[str, Any]:
        return {
            "question_id":     str(uuid.uuid4())[:8],
            "scene_name":      self.scene_name,
            "frame_idx":       self.frame_idx,
            "template_id":     template_id,
            "difficulty":      difficulty,
            "question_type":   topology_level.lower() + "_chain",   # "l2a_chain" / "l2b_chain"
            "question":        question,
            "answer":          answer,
            "answer_type":     answer_type,
            "reference_objects": [o for o in ref_objects if o],
            "target_objects":    [o for o in tgt_objects if o],
            "source":          "L2_chain",
            # ── V3 拓扑字段（CoverageTracker.record_from_qa 使用）──
            "topology_level":  topology_level,        # "L2A" or "L2B"
            "path_pattern":    path_pattern,           # "ego→A→B" or "X←ego→Y"
            "footprint_nodes": [n for n in footprint_nodes if n],
        }
