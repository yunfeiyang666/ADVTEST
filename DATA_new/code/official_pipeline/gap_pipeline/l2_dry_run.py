"""
Feasibility dry-run for the L2 refactor side path.

This module composes taxonomy, candidate builders, constraint planner, geometry,
and question realizer. It does not execute Neo4j and is not wired into the old
pipeline yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from gap_pipeline.l2_candidate_builder import (
    build_converge_candidates,
    build_diverge_candidates,
    normalize_candidate,
)
from gap_pipeline.l2_constraint_planner import L2Clause, L2ConstraintPlanner, L2PlanResult
from gap_pipeline.l2_geometry import distance, official_dir6_between_objs, point_from_obj, viewpoint_left_right
from gap_pipeline.l2_question_graph import chain_graph, converge_graph, diverge_graph
from gap_pipeline.l2_question_realizer import (
    RealizedQuestion,
    converge_question,
    direction_chain_question,
    counterfactual_exist_question,
    distance_chain_question,
    diverge_branch_count_question,
    diverge_branch_exist_question,
    diverge_branch_object_question,
    diverge_branch_status_question,
    diverge_status_question,
    diverge_type_question,
    viewpoint_transfer_question,
)
from gap_pipeline.l2_taxonomy import L2Family, L2Gap, eligible_families


@dataclass
class DryRunInput:
    gap: L2Gap
    a_obj: Dict[str, Any]
    b_obj: Dict[str, Any]
    c_obj: Dict[str, Any]
    converge_rows: Sequence[Dict[str, Any]] = field(default_factory=list)
    pivot_neighbors: Sequence[Dict[str, Any]] = field(default_factory=list)
    available_refs: Sequence[Dict[str, Any]] = field(default_factory=list)
    a_to_b_dir: str = ""
    c_to_b_dir: str = ""

    b_to_a_dir: str = ""
    b_to_c_dir: str = ""

    converge_mode: str = "object"


@dataclass
class DryRunPlan:
    family: L2Family
    feasible: bool
    score: float
    question: Optional[RealizedQuestion] = None
    answer: Any = None
    clauses: List[L2Clause] = field(default_factory=list)
    footprint: Dict[str, List[str]] = field(default_factory=dict)
    reason: str = ""
    debug: Dict[str, Any] = field(default_factory=dict)


def _dir(src: Dict[str, Any], tgt: Dict[str, Any]) -> Optional[str]:
    return official_dir6_between_objs(src, tgt)


def _dist(src: Dict[str, Any], tgt: Dict[str, Any]) -> Optional[float]:
    p1, p2 = point_from_obj(src), point_from_obj(tgt)
    if p1 is None or p2 is None:
        return None
    return distance(p1, p2)


class L2DryRunner:
    def __init__(self, *, planner: Optional[L2ConstraintPlanner] = None, min_distance_gap: float = 1.0) -> None:
        self.planner = planner or L2ConstraintPlanner(max_refs=3)
        self.min_distance_gap = min_distance_gap

    def run(self, data: DryRunInput) -> List[DryRunPlan]:
        out: List[DryRunPlan] = []
        for spec in eligible_families(data.gap):
            if spec.family == L2Family.CONVERGE:
                out.extend(self._converge_all_modes(data, spec.weight))
            elif spec.family == L2Family.DIVERGE_COMPARE:
                out.extend(self._diverge_all(data, spec.weight))
            elif spec.family == L2Family.DISTANCE_CHAIN:
                out.append(self._distance_chain(data, spec.weight))
            elif spec.family == L2Family.DIRECTION_CHAIN:
                out.append(self._direction_chain(data, spec.weight))
            elif spec.family == L2Family.VIEWPOINT_TRANSFER:
                out.append(self._viewpoint_transfer(data, spec.weight))
        return out

    def feasible(self, data: DryRunInput) -> List[DryRunPlan]:
        return [p for p in self.run(data) if p.feasible]

    def _converge_all_modes(self, data: DryRunInput, weight: float) -> List[DryRunPlan]:
        """Generate converge plans for multiple ref-variant × answer-mode combinations."""
        # Prefer Neo4j-stored directions; fallback to geometric
        da = data.a_to_b_dir or _dir(data.a_obj, data.b_obj)
        dc = data.c_to_b_dir or _dir(data.c_obj, data.b_obj)
        if not da or not dc or not data.converge_rows:
            return [DryRunPlan(L2Family.CONVERGE, False, 0.0, reason="missing_converge_inputs")]
        candidates = build_converge_candidates(
            data.converge_rows,
            target_type=data.gap.b_type,
            dir_from_a=da,
            dir_from_c=dc,
        )
        target = normalize_candidate(data.b_obj)
        # Build refs with dir_to maps from available_refs (graph-stored directions).
        # Candidates from build_converge_candidates lack dir_to; if used as refs
        # by the planner, ref_dir_to() would fall back to geometric directions
        # that differ from graph_index directions used by _direct_plan_verify.
        # Fix: prefer available_refs version (with dir_to) over bare candidates.
        if data.available_refs:
            ref_by_id = {(r.get("id") or r.get("unique_id") or ""): r for r in data.available_refs}
            enriched_cands = [ref_by_id.get(c.get("id") or "", c) for c in candidates]
            cand_ids = {c.get("id") or "" for c in candidates}
            extra_refs = [r for r in data.available_refs if (r.get("id") or r.get("unique_id") or "") not in cand_ids]
            refs = enriched_cands + extra_refs
        else:
            refs = list(candidates)
        ref_variants = self.planner.plan_alternatives(target, candidates, available_refs=refs, top_k=3)
        if not any(v.unique for v in ref_variants):
            return [DryRunPlan(L2Family.CONVERGE, False, 0.0, reason="converge_non_unique", debug=ref_variants[0].as_dict())]

        b_status = str(data.b_obj.get("status") or "").strip()
        modes = ["object"]
        if b_status:
            modes.append("status")
        modes.append("count")

        plans: List[DryRunPlan] = []
        # Global mode counter for round-robin across gaps
        if not hasattr(self, '_mode_counter'):
            self._mode_counter = 0
        preferred_mode_idx = self._mode_counter % len(modes)
        self._mode_counter += 1

        for var_idx, plan in enumerate(ref_variants):
            if not plan.unique:
                continue
            ref_ids = [c.ref_id for c in plan.clauses if c.kind == "ref_dir"]
            fp = converge_graph(data.gap.a_id, data.gap.b_id, data.gap.c_id, refs=ref_ids).footprint().as_dict()
            # First ref variant gets full weight; subsequent variants get slight discount
            var_discount = 1.0 if var_idx == 0 else 0.95
            for m_idx, mode in enumerate(modes):
                q = converge_question(
                    target_type=data.gap.b_type,
                    a_id=data.gap.a_id,
                    c_id=data.gap.c_id,
                    dir_from_a=da,
                    dir_from_c=dc,
                    clauses=plan.clauses,
                    mode=mode,
                )
                # Small bonus for the globally-preferred mode (cycles: object→status→exist→count)
                mode_bonus = 0.02 if (m_idx == preferred_mode_idx) else 0.0
                mode_weight = weight + mode_bonus
                plans.append(DryRunPlan(
                    L2Family.CONVERGE, True, mode_weight * var_discount, q,
                    clauses=plan.clauses, footprint=fp, debug=plan.as_dict(),
                ))
        return plans

    def _diverge_all(self, data: DryRunInput, weight: float) -> List[DryRunPlan]:
        """Generate diverge plans for status comparison and type comparison."""
        # Prefer Neo4j-stored directions; fallback to geometric
        da = data.b_to_a_dir or _dir(data.b_obj, data.a_obj)
        dc = data.b_to_c_dir or _dir(data.b_obj, data.c_obj)
        if not da or not dc or not data.pivot_neighbors:
            return [DryRunPlan(L2Family.DIVERGE_COMPARE, False, 0.0, reason="missing_diverge_inputs")]
        a_status = str(data.a_obj.get("status") or "").strip()
        c_status = str(data.c_obj.get("status") or "").strip()
        # Use dir_official from pivot_neighbors (Neo4j-stored); only fallback to geometric
        enriched_neighbors = []
        for nb in data.pivot_neighbors:
            d = nb.get("dir_official") or _dir(data.b_obj, nb)
            if d:
                enriched = dict(nb)
                enriched["dir_official"] = d
                enriched_neighbors.append(enriched)
        div = build_diverge_candidates(
            enriched_neighbors,
            data.a_obj,
            data.c_obj,
            a_type=data.gap.a_type,
            a_dir=da,
            c_type=data.gap.c_type,
            c_dir=dc,
        )
        # Candidates-first refs: branch candidates have best discrimination power.
        # Enrich candidates with dir_to maps from available_refs to avoid
        # geometric-direction fallback in ref_dir_to (same fix as converge).
        extra_refs = list(data.available_refs) or enriched_neighbors
        ref_by_id = {(r.get("id") or r.get("unique_id") or ""): r for r in extra_refs}
        a_cand_ids = {c.get("id") or "" for c in div.a_branch.candidates}
        c_cand_ids = {c.get("id") or "" for c in div.c_branch.candidates}
        a_enriched = [ref_by_id.get(c.get("id") or "", c) for c in div.a_branch.candidates]
        c_enriched = [ref_by_id.get(c.get("id") or "", c) for c in div.c_branch.candidates]
        a_refs = a_enriched + [r for r in extra_refs if (r.get("id") or r.get("unique_id") or "") not in a_cand_ids]
        c_refs = c_enriched + [r for r in extra_refs if (r.get("id") or r.get("unique_id") or "") not in c_cand_ids]
        pa = self.planner.plan(div.a_branch.target, div.a_branch.candidates, available_refs=a_refs)
        pc = self.planner.plan(div.c_branch.target, div.c_branch.candidates, available_refs=c_refs)
        if not pa.unique or not pc.unique:
            return [DryRunPlan(L2Family.DIVERGE_COMPARE, False, 0.0, reason="branch_non_unique", debug={"a": pa.as_dict(), "c": pc.as_dict()})]
        fp = diverge_graph(
            data.gap.a_id,
            data.gap.b_id,
            data.gap.c_id,
            x_refs=[c.ref_id for c in pa.clauses if c.kind == "ref_dir"],
            y_refs=[c.ref_id for c in pc.clauses if c.kind == "ref_dir"],
        ).footprint().as_dict()
        plans: List[DryRunPlan] = []
        all_clauses = pa.clauses + pc.clauses

        # Global mode counter for round-robin across diverge gaps
        if not hasattr(self, '_div_mode_counter'):
            self._div_mode_counter = 0

        # Define all diverge modes: 2 comparison + 4 single-branch per side
        # Modes: compare_status, compare_type, branch_a_status, branch_a_object, 
        #        branch_a_exist, branch_a_count
        div_modes = []

        # Comparison modes
        if a_status and c_status:
            q_cmp_status = diverge_status_question(
                b_id=data.gap.b_id,
                a_type=data.gap.a_type, a_dir=da,
                c_type=data.gap.c_type, c_dir=dc,
                a_clauses=pa.clauses, c_clauses=pc.clauses,
            )
            answer_cmp_status = "Yes" if a_status == c_status else "No"
            div_modes.append(("compare_status", q_cmp_status, answer_cmp_status))
        if data.gap.a_type and data.gap.c_type:
            q_cmp_type = diverge_type_question(
                b_id=data.gap.b_id,
                a_type=data.gap.a_type, a_dir=da,
                c_type=data.gap.c_type, c_dir=dc,
                a_clauses=pa.clauses, c_clauses=pc.clauses,
            )
            answer_cmp_type = "Yes" if data.gap.a_type == data.gap.c_type else "No"
            div_modes.append(("compare_type", q_cmp_type, answer_cmp_type))

        # Single-branch modes (ask about A-side)
        if a_status:
            q_br_status = diverge_branch_status_question(
                b_id=data.gap.b_id, branch_type=data.gap.a_type,
                branch_dir=da, branch_clauses=pa.clauses,
            )
            div_modes.append(("branch_status", q_br_status, a_status))

        q_br_object = diverge_branch_object_question(
            b_id=data.gap.b_id, branch_type=data.gap.a_type,
            branch_dir=da, branch_clauses=pa.clauses,
        )
        div_modes.append(("branch_a_object", q_br_object, data.gap.a_id))

        # C-side object identification (different branch, same graph)
        q_br_c_object = diverge_branch_object_question(
            b_id=data.gap.b_id, branch_type=data.gap.c_type,
            branch_dir=dc, branch_clauses=pc.clauses,
        )
        div_modes.append(("branch_c_object", q_br_c_object, data.gap.c_id))

        q_br_count = diverge_branch_count_question(
            b_id=data.gap.b_id, branch_type=data.gap.a_type,
            branch_dir=da, branch_clauses=pa.clauses,
        )
        cands_in_dir = len(div.a_branch.candidates)
        div_modes.append(("branch_count", q_br_count, str(cands_in_dir)))

        # Counterfactual exist: find a type NOT present in this direction from B
        all_types = {"car", "pedestrian", "truck", "bus", "motorcycle", "bicycle", "barrier", "trailer"}
        present_types = {c.get("type") or "" for c in div.a_branch.candidates}
        missing_types = all_types - present_types
        if missing_types:
            fake_type = sorted(missing_types)[self._div_mode_counter % len(missing_types)]
            q_cf = counterfactual_exist_question(
                anchor_id=data.gap.b_id, fake_type=fake_type, direction=da,
            )
            div_modes.append(("counterfactual_exist", q_cf, "No"))

        if not div_modes:
            return [DryRunPlan(L2Family.DIVERGE_COMPARE, False, 0.0, reason="missing_branch_status_and_type")]

        # Round-robin: preferred mode gets small bonus
        preferred_idx = self._div_mode_counter % len(div_modes)
        self._div_mode_counter += 1

        for m_idx, (mode_name, q, ans) in enumerate(div_modes):
            mode_bonus = 0.02 if (m_idx == preferred_idx) else 0.0
            plans.append(DryRunPlan(
                L2Family.DIVERGE_COMPARE, True, weight + mode_bonus, q,
                answer=ans, clauses=all_clauses, footprint=fp,
                debug={"a": pa.as_dict(), "c": pc.as_dict()},
            ))
        return plans

    def _distance_chain(self, data: DryRunInput, weight: float) -> DryRunPlan:
        dab, dbc = _dist(data.a_obj, data.b_obj), _dist(data.b_obj, data.c_obj)
        if dab is None or dbc is None or abs(dab - dbc) < self.min_distance_gap:
            return DryRunPlan(L2Family.DISTANCE_CHAIN, False, 0.0, reason="distance_ambiguous")
        answer = data.gap.a_id if dab < dbc else data.gap.c_id
        q = distance_chain_question(data.gap.a_id, data.gap.b_id, data.gap.c_id)
        fp = chain_graph(data.gap.a_id, data.gap.b_id, data.gap.c_id, family="distance_chain").footprint().as_dict()
        return DryRunPlan(L2Family.DISTANCE_CHAIN, True, weight, q, answer=answer, footprint=fp)

    def _direction_chain(self, data: DryRunInput, weight: float) -> DryRunPlan:
        dab, dbc = _dir(data.a_obj, data.b_obj), _dir(data.b_obj, data.c_obj)
        if not dab or not dbc:
            return DryRunPlan(L2Family.DIRECTION_CHAIN, False, 0.0, reason="direction_missing")
        q = direction_chain_question(data.gap.a_id, data.gap.b_id, data.gap.c_id)
        fp = chain_graph(data.gap.a_id, data.gap.b_id, data.gap.c_id, family="direction_chain").footprint().as_dict()
        return DryRunPlan(L2Family.DIRECTION_CHAIN, True, weight, q, answer=(dab == dbc), footprint=fp)

    def _viewpoint_transfer(self, data: DryRunInput, weight: float) -> DryRunPlan:
        pa, pb, pc = point_from_obj(data.a_obj), point_from_obj(data.b_obj), point_from_obj(data.c_obj)
        if pa is None or pb is None or pc is None:
            return DryRunPlan(L2Family.VIEWPOINT_TRANSFER, False, 0.0, reason="point_missing")
        ans = viewpoint_left_right(pa, pb, pc)
        if ans is None:
            return DryRunPlan(L2Family.VIEWPOINT_TRANSFER, False, 0.0, reason="viewpoint_ambiguous")
        q = viewpoint_transfer_question(data.gap.a_id, data.gap.b_id, data.gap.c_id)
        fp = chain_graph(data.gap.a_id, data.gap.b_id, data.gap.c_id, family="viewpoint_transfer").footprint().as_dict()
        return DryRunPlan(L2Family.VIEWPOINT_TRANSFER, True, weight, q, answer=ans, footprint=fp)

