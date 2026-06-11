"""
Coverage-priority gap selector for unified L2.

Gap selection is independent from template-family selection:
  1) shuffle candidate gaps to avoid deterministic bias;
  2) score each gap by the highest uncovered coverage level it can improve;
  3) select the first candidate in the highest available level;
  4) update coverage only after a verified QA is emitted.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


@dataclass
class L2CoverageState:
    l0: Set[str] = field(default_factory=set)
    l1: Set[str] = field(default_factory=set)
    l2: Set[str] = field(default_factory=set)

    def mark(self, footprint: Dict[str, List[str]]) -> None:
        self.l0.update(footprint.get("l0", []))
        self.l1.update(footprint.get("l1", []))
        self.l2.update(footprint.get("l2", []))


def l1_key(a: str, b: str) -> str:
    return "|".join(sorted([str(a), str(b)]))


def l2_key(a: str, b: str, c: str) -> str:
    """Canonical L2 key: endpoints sorted, pivot fixed.

    This matches gap_pipeline.l2_question_graph.canon_l2(), which is used by
    generated QA coverage footprints. Keeping the selector and replay analyzer
    on the same key space is required for coverage-aware gap selection.
    """
    left, right = sorted([str(a), str(c)])
    return f"{left}|{b}|{right}"


def gap_coverage_level(row: Dict[str, Any], state: L2CoverageState) -> int:
    """
    Return the highest coverage level this gap can improve.

    2 = new L2 path, 1 = new L1 edge, 0 = new L0 node, -1 = no new coverage.
    """
    a, b, c = str(row["a_id"]), str(row["b_id"]), str(row["c_id"])
    if l2_key(a, b, c) not in state.l2:
        return 2
    if l1_key(a, b) not in state.l1 or l1_key(b, c) not in state.l1:
        return 1
    if a not in state.l0 or b not in state.l0 or c not in state.l0:
        return 0
    return -1


class L2GapSelector:
    def __init__(self, *, rng: Optional[random.Random] = None) -> None:
        self.rng = rng or random.Random()

    def shuffled(self, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = list(rows)
        self.rng.shuffle(out)
        return out

    def select_next(
        self,
        rows: Sequence[Dict[str, Any]],
        state: L2CoverageState,
        *,
        already_tried: Optional[Set[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        tried = already_tried or set()
        best_level = -1
        best: Optional[Dict[str, Any]] = None
        for row in rows:
            key = l2_key(row["a_id"], row["b_id"], row["c_id"])
            if key in tried:
                continue
            level = gap_coverage_level(row, state)
            if level > best_level:
                best_level = level
                best = row
                if level == 2:
                    break
        return best

    def rank(self, rows: Iterable[Dict[str, Any]], state: L2CoverageState) -> List[Dict[str, Any]]:
        shuffled = self.shuffled(list(rows))
        return sorted(shuffled, key=lambda r: gap_coverage_level(r, state), reverse=True)

