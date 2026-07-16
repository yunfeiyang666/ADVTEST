"""
REG-style constraint planner for the L2 refactor side path.

Input is already a candidate set for one answer slot/branch. The planner tries to
make the target unique by adding explicit reference-object direction clauses and,
if needed, a distance-rank clause.

This module does not query Neo4j and is not connected to the existing pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from gap_pipeline.l2_geometry import official_dir6_between_objs, distance_rank


def obj_id(obj: Dict[str, Any]) -> str:
    return str(obj.get("id") or obj.get("unique_id") or obj.get("node_id") or "")


def ref_dir_to(ref: Dict[str, Any], target: Dict[str, Any], *, boundary_margin: float = 0.0) -> Optional[str]:
    """Return directed ref->target availability direction.

    If the ref object carries a dir_to map, only directions backed by an actual
    directed graph edge are accepted. Otherwise fall back to geometry for legacy
    callers.
    """
    tid = obj_id(target)
    dir_map = ref.get("dir_to") or {}
    if isinstance(dir_map, dict):
        val = dir_map.get(tid)
        if val:
            return str(val)
        if dir_map:
            return None
    return official_dir6_between_objs(ref, target, boundary_margin=boundary_margin)


@dataclass(frozen=True)

class L2Clause:
    kind: str                 # ref_dir | dist_rank
    value: str
    ref_id: str = ""
    text_hint: str = ""


@dataclass
class L2PlanResult:
    unique: bool
    target_id: str
    remaining_ids: List[str]
    clauses: List[L2Clause] = field(default_factory=list)
    trace: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "unique": self.unique,
            "target_id": self.target_id,
            "remaining_ids": self.remaining_ids,
            "clauses": [c.__dict__ for c in self.clauses],
            "trace": self.trace,
        }


class L2ConstraintPlanner:
    """Greedy distractor-elimination planner."""

    def __init__(
        self,
        *,
        max_refs: int = 2,
        allow_dist_rank: bool = True,
        boundary_margin: float = 0.0,
        allowed_rank_labels: Optional[Set[str]] = None,
    ) -> None:
        self.max_refs = max_refs
        self.allow_dist_rank = allow_dist_rank
        self.boundary_margin = boundary_margin
        self.allowed_rank_labels = allowed_rank_labels or {
            "nearest", "farthest", "2nd-nearest", "2nd-farthest"
        }

    def plan(
        self,
        target: Dict[str, Any],
        candidates: Sequence[Dict[str, Any]],
        *,
        available_refs: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> L2PlanResult:
        tid = obj_id(target)
        current = [c for c in candidates if obj_id(c)]
        trace = [f"start:{[obj_id(c) for c in current]}"]
        clauses: List[L2Clause] = []

        if not tid or tid not in {obj_id(c) for c in current}:
            return L2PlanResult(False, tid, [obj_id(c) for c in current], trace=trace + ["target_missing"])
        if len(current) == 1:
            return L2PlanResult(True, tid, [tid], clauses, trace + ["already_unique"])

        refs = list(available_refs) if available_refs is not None else list(current)
        used_refs: Set[str] = set()

        for _ in range(self.max_refs):
            picked = self._pick_best_ref(target, current, refs, used_refs)
            if picked is None:
                trace.append("no_ref_available")
                break
            ref, direction, kept = picked
            rid = obj_id(ref)
            if len(kept) >= len(current):
                trace.append(f"ref_no_gain:{rid}:{direction}")
                break
            used_refs.add(rid)
            current = kept
            clauses.append(L2Clause(
                kind="ref_dir",
                ref_id=rid,
                value=direction,
                text_hint=f"to the {direction.replace('_', ' ').replace('-', ' ')} of {rid}",
            ))
            trace.append(f"ref:{rid}:{direction}->{[obj_id(c) for c in current]}")
            if len(current) == 1 and obj_id(current[0]) == tid:
                return L2PlanResult(True, tid, [tid], clauses, trace)

        if self.allow_dist_rank and len(current) > 1:
            label = distance_rank(tid, current)
            if label in self.allowed_rank_labels:
                clauses.append(L2Clause(kind="dist_rank", value=label, text_hint=label))
                trace.append(f"dist_rank:{label}->[{tid}]")
                return L2PlanResult(True, tid, [tid], clauses, trace)
            trace.append(f"dist_rank_unusable:{label}")

        return L2PlanResult(False, tid, [obj_id(c) for c in current], clauses, trace)

    def plan_alternatives(
        self,
        target: Dict[str, Any],
        candidates: Sequence[Dict[str, Any]],
        *,
        available_refs: Optional[Iterable[Dict[str, Any]]] = None,
        top_k: int = 3,
    ) -> List[L2PlanResult]:
        """Generate up to top_k unique plans with different ref combinations.

        Each successive plan excludes the first-round ref from the previous
        plan, forcing the planner to pick a different landmark. Only plans
        that achieve uniqueness are returned.
        """
        refs_list = sorted(
            list(available_refs) if available_refs is not None else list(candidates),
            key=obj_id,
        )
        seen_ref_sets: List[frozenset[str]] = []
        results: List[L2PlanResult] = []
        exclude_refs: Set[str] = set()

        for _ in range(top_k):
            filtered_refs = [r for r in refs_list if obj_id(r) not in exclude_refs]
            if not filtered_refs:
                break
            result = self.plan(target, candidates, available_refs=filtered_refs)
            ref_set = frozenset(c.ref_id for c in result.clauses if c.kind == "ref_dir")
            if result.unique and ref_set not in seen_ref_sets:
                seen_ref_sets.append(ref_set)
                results.append(result)
                # Exclude the first ref chosen in this plan to force diversity
                first_refs = [c.ref_id for c in result.clauses if c.kind == "ref_dir"]
                if first_refs:
                    exclude_refs.add(first_refs[0])
            else:
                # This ref subset can't achieve uniqueness; stop trying
                break

        if not results:
            # Fallback: return the single best plan (may be non-unique)
            results.append(self.plan(target, candidates, available_refs=refs_list))

        return results

    def _pick_best_ref(
        self,
        target: Dict[str, Any],
        current: Sequence[Dict[str, Any]],
        refs: Sequence[Dict[str, Any]],
        used_refs: Set[str],
    ) -> Optional[Tuple[Dict[str, Any], str, List[Dict[str, Any]]]]:
        tid = obj_id(target)
        current_ids = {obj_id(c) for c in current}
        best = None

        for ref in refs:
            rid = obj_id(ref)
            if not rid or rid == tid or rid in used_refs:
                continue
            direction = ref_dir_to(ref, target, boundary_margin=self.boundary_margin)
            if direction is None:
                continue
            kept: List[Dict[str, Any]] = []
            for cand in current:
                cid = obj_id(cand)
                if cid == rid and rid in current_ids:
                    continue
                d = ref_dir_to(ref, cand, boundary_margin=self.boundary_margin)
                if d == direction:
                    kept.append(cand)
            if tid not in {obj_id(c) for c in kept}:
                continue
            gain = len(current) - len(kept)
            score = (gain, -len(kept), 1 if rid in current_ids else 0)
            if best is None or score > best[0]:
                best = (score, ref, direction, kept)

        if best is None:
            return None
        _, ref, direction, kept = best
        return ref, direction, kept
