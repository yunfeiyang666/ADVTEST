"""
Template taxonomy for the L2 refactor side path.

This module only defines template-family metadata and cheap eligibility rules.
It does not query Neo4j and does not modify the existing pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Optional, Set


class L2Family(str, Enum):
    CONVERGE = "converge"
    DIVERGE_COMPARE = "diverge_compare"
    DISTANCE_CHAIN = "distance_chain"
    DIRECTION_CHAIN = "direction_chain"
    VIEWPOINT_TRANSFER = "viewpoint_transfer"


class CandidateMode(str, Enum):
    NONE = "none"
    SINGLE_SLOT = "single_slot"
    DOUBLE_BRANCH = "double_branch"


@dataclass(frozen=True)
class L2TemplateSpec:
    family: L2Family
    weight: float
    candidate_mode: CandidateMode
    needs_constraint_planner: bool
    uses_count_exist: bool = False
    description: str = ""


DEFAULT_SPECS: Dict[L2Family, L2TemplateSpec] = {
    L2Family.CONVERGE: L2TemplateSpec(
        family=L2Family.CONVERGE,
        weight=0.50,
        candidate_mode=CandidateMode.SINGLE_SLOT,
        needs_constraint_planner=True,
        uses_count_exist=True,
        description="a -> x <- c; answer slot is pivot x",
    ),
    L2Family.DIVERGE_COMPARE: L2TemplateSpec(
        family=L2Family.DIVERGE_COMPARE,
        weight=0.10,
        candidate_mode=CandidateMode.DOUBLE_BRANCH,
        needs_constraint_planner=True,
        uses_count_exist=False,
        description="x <- b -> y; both branches described through pivot b",
    ),
    L2Family.DISTANCE_CHAIN: L2TemplateSpec(
        family=L2Family.DISTANCE_CHAIN,
        weight=0.20,
        candidate_mode=CandidateMode.NONE,
        needs_constraint_planner=False,
        description="compare dist(a,b) and dist(b,c)",
    ),
    L2Family.DIRECTION_CHAIN: L2TemplateSpec(
        family=L2Family.DIRECTION_CHAIN,
        weight=0.10,
        candidate_mode=CandidateMode.NONE,
        needs_constraint_planner=False,
        description="compare dir(a,b) and dir(b,c)",
    ),
    L2Family.VIEWPOINT_TRANSFER: L2TemplateSpec(
        family=L2Family.VIEWPOINT_TRANSFER,
        weight=0.10,
        candidate_mode=CandidateMode.NONE,
        needs_constraint_planner=False,
        description="face from a toward b, locate c left/right",
    ),
}


@dataclass(frozen=True)
class L2Gap:
    """Minimal gap representation used by side-path modules."""

    a_id: str
    b_id: str
    c_id: str
    a_type: str = ""
    b_type: str = ""
    c_type: str = ""

    @classmethod
    def from_cell(cls, cell: Dict) -> "L2Gap":
        return cls(
            a_id=str(cell.get("a_id") or cell.get("n1_id") or ""),
            b_id=str(cell.get("b_id") or cell.get("n2_id") or ""),
            c_id=str(cell.get("c_id") or cell.get("n3_id") or ""),
            a_type=str(cell.get("a_type") or cell.get("n1_type") or ""),
            b_type=str(cell.get("b_type") or cell.get("n2_type") or ""),
            c_type=str(cell.get("c_type") or cell.get("n3_type") or ""),
        )

    def has_all_ids(self) -> bool:
        return bool(self.a_id and self.b_id and self.c_id)

    def ego_slot(self) -> Optional[str]:
        if self.a_id == "ego":
            return "a"
        if self.b_id == "ego":
            return "b"
        if self.c_id == "ego":
            return "c"
        return None


def family_allowed_by_ego(gap: L2Gap, family: L2Family) -> bool:
    """Apply agreed ego slot rules."""
    slot = gap.ego_slot()
    if slot is None:
        return True
    if slot == "b":
        # ego as pivot: diverge is okay; converge question asks for ego and is odd.
        return family != L2Family.CONVERGE
    if slot in {"a", "c"}:
        # Final pipeline keeps diverge available even when ego is one branch; the
        # realizer uses the concrete object id and verification remains geometric.
        return True
    return True


def cheap_family_eligible(gap: L2Gap, family: L2Family) -> bool:
    """
    Cheap eligibility independent of candidate-query dry-run.

    Later dry-run can still reject a family because candidates are non-unique,
    geometry is ambiguous, distances are too close, etc.
    """
    if not gap.has_all_ids():
        return False
    if not family_allowed_by_ego(gap, family):
        return False
    if family == L2Family.CONVERGE and not gap.b_type:
        return False
    if family == L2Family.DIVERGE_COMPARE and (not gap.a_type or not gap.c_type):
        return False
    return True


def eligible_families(
    gap: L2Gap,
    *,
    specs: Dict[L2Family, L2TemplateSpec] = DEFAULT_SPECS,
    disabled: Optional[Iterable[L2Family]] = None,
) -> List[L2TemplateSpec]:
    disabled_set: Set[L2Family] = set(disabled or [])
    out: List[L2TemplateSpec] = []
    for fam, spec in specs.items():
        if fam in disabled_set:
            continue
        if cheap_family_eligible(gap, fam):
            out.append(spec)
    return out

