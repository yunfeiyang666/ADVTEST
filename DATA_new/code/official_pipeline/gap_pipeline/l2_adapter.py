"""
Adapter from new L2 dry-run plans to the legacy QA record shape.

This is the boundary layer for future run_gap_pipeline_v7 integration. It does
not execute Neo4j and does not mutate coverage trackers.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from gap_pipeline.l2_cypher_builders import (
    verify_converge,
    verify_branch,
    verify_diverge_pair,
    verify_direction_chain,
    verify_distance_chain,
)
from gap_pipeline.l2_constraint_planner import L2Clause
from gap_pipeline.l2_dry_run import DryRunInput, DryRunPlan
from gap_pipeline.l2_geometry import official_dir6_between_objs
from gap_pipeline.l2_taxonomy import L2Family


def _obj_id(obj: Dict[str, Any]) -> str:
    return str(obj.get("id") or obj.get("unique_id") or "")


def _branch_clauses(plan: DryRunPlan, side: str, excluded_ref_id: str) -> list[L2Clause]:
    debug = plan.debug or {}
    branch_debug = debug.get(side, {}) if isinstance(debug, dict) else {}
    raw_clauses = branch_debug.get("clauses") if isinstance(branch_debug, dict) else None
    if raw_clauses:
        clauses: list[L2Clause] = []
        for item in raw_clauses:
            if not isinstance(item, dict):
                continue
            ref_id = str(item.get("ref_id") or "")
            if ref_id == excluded_ref_id:
                continue
            clauses.append(L2Clause(kind=str(item.get("kind") or "ref_dir"), value=str(item.get("value") or ""), ref_id=ref_id, text_hint=str(item.get("text_hint") or "")))
        return clauses
    return [c for c in plan.clauses if c.ref_id != excluded_ref_id]


def _status(obj: Dict[str, Any]) -> str:
    return str(obj.get("status") or "")


def _answer_for_plan(data: DryRunInput, plan: DryRunPlan) -> Any:
    if plan.family == L2Family.CONVERGE:
        if plan.question and plan.question.answer_type == "status":
            return _status(data.b_obj)
        if plan.question and plan.question.answer_type == "boolean":
            return True
        if plan.question and plan.question.answer_type == "count":
            # Count is only exact after executing verify_converge; leave a safe marker.
            return plan.debug.get("verify_n", None) if plan.debug else None
        return data.gap.b_id
    return plan.answer


def _verify_payload(data: DryRunInput, plan: DryRunPlan) -> Dict[str, Any]:
    if plan.family == L2Family.CONVERGE:
        q = verify_converge(
            a_id=data.gap.a_id,
            c_id=data.gap.c_id,
            target_type=data.gap.b_type,
            dir_from_a=data.a_to_b_dir or official_dir6_between_objs(data.a_obj, data.b_obj) or "",
            dir_from_c=data.c_to_b_dir or official_dir6_between_objs(data.c_obj, data.b_obj) or "",
            clauses=plan.clauses,
        )
        return {"cypher": q.cypher, "params": q.params}

    if plan.family == L2Family.DIVERGE_COMPARE:
        # Extract per-branch clauses from plan debug
        a_clauses = _branch_clauses(plan, "a", excluded_ref_id="")
        c_clauses = _branch_clauses(plan, "c", excluded_ref_id="")
        qa = verify_branch(
            b_id=data.gap.b_id,
            branch_type=data.gap.a_type,
            branch_dir=data.b_to_a_dir or official_dir6_between_objs(data.b_obj, data.a_obj) or "",
            clauses=a_clauses,
        )
        qc = verify_branch(
            b_id=data.gap.b_id,
            branch_type=data.gap.c_type,
            branch_dir=data.b_to_c_dir or official_dir6_between_objs(data.b_obj, data.c_obj) or "",
            clauses=c_clauses,
        )
        return {
            "branches": [
                {"cypher": qa.cypher, "params": qa.params},
                {"cypher": qc.cypher, "params": qc.params},
            ]
        }

    if plan.family == L2Family.DISTANCE_CHAIN:
        q = verify_distance_chain(data.gap.a_id, data.gap.b_id, data.gap.c_id)
        return {"cypher": q.cypher, "params": q.params}

    if plan.family == L2Family.DIRECTION_CHAIN:
        q = verify_direction_chain(data.gap.a_id, data.gap.b_id, data.gap.c_id)
        return {"cypher": q.cypher, "params": q.params}

    return {"cypher": "", "params": {}}




def _constraint_meta(plan: DryRunPlan) -> Dict[str, Any]:
    debug = plan.debug or {}
    branches = [debug]
    if "a" in debug or "c" in debug:
        branches = [debug.get("a", {}), debug.get("c", {})]
    before = 0
    after = 0
    unique = True
    traces = []
    for item in branches:
        rem = item.get("remaining_ids") or []
        after += len(rem)
        unique = unique and bool(item.get("unique", False))
        tr = item.get("trace") or []
        traces.extend(tr)
        if tr and isinstance(tr[0], str) and tr[0].startswith("start:"):
            before += tr[0].count("'") // 2
    return {
        "constraint_trace": traces,
        "constraint_count": len(plan.clauses),
        "constraint_types": sorted({c.kind for c in plan.clauses}),
        "candidate_before": before,
        "candidate_after": after,
        "unique_check": unique,
    }

def plan_to_qa_record(
    data: DryRunInput,
    plan: DryRunPlan,
    *,
    question_id: Optional[str] = None,
    scene_name: str = "",
    frame_idx: Optional[int] = None,
    skip_cypher: bool = False,
) -> Dict[str, Any]:
    if not plan.feasible or plan.question is None:
        raise ValueError("Cannot adapt infeasible plan or plan without question")

    footprint_nodes = [data.gap.a_id, data.gap.b_id, data.gap.c_id]

    if skip_cypher:
        verify: Dict[str, Any] = {}
        constraint_meta = {
            "constraint_trace": [],
            "constraint_count": len(plan.clauses),
            "constraint_types": sorted({c.kind for c in plan.clauses}),
            "candidate_before": 0,
            "candidate_after": 0,
            "unique_check": True,
        }
    else:
        verify = _verify_payload(data, plan)
        constraint_meta = _constraint_meta(plan)

    qa = {
        "question_id": question_id or "",
        "scene_name": scene_name,
        "frame_idx": frame_idx,
        "topology_level": "L2",
        "template_id": plan.family.value,
        "constraint_trace": constraint_meta["constraint_trace"],
        "constraint_count": constraint_meta["constraint_count"],
        "constraint_types": constraint_meta["constraint_types"],
        "candidate_before": constraint_meta["candidate_before"],
        "candidate_after": constraint_meta["candidate_after"],
        "unique_check": constraint_meta["unique_check"],
        "generation_backend": "programmatic",
        "llm_model": "",
        "raw_llm_output": {},
        "token_prompt": 0,
        "token_completion": 0,
        "logic_verification": "PENDING_L2_REFACTOR_VERIFY",
        "is_unique": True,
        "n_interference_siblings": 0,
        "question": plan.question.question,
        "answer": _answer_for_plan(data, plan),
        "answer_type": plan.question.answer_type,
        "path_pattern": f"{data.gap.a_id}|{data.gap.b_id}|{data.gap.c_id}",
        "footprint_nodes": footprint_nodes,
        "coverage_footprint": plan.footprint,
        "verify_payload": verify,
        "l2_refactor": True,
        "l2_family": plan.family.value,
        "l2_score": plan.score,
    }
    return qa

