"""Diagnostic: check verify pass rate across all gaps."""
import os, copy
from pathlib import Path
os.environ["NEO4J_NOTIFICATIONS_MIN_SEVERITY"] = "OFF"

from run_gap_pipeline_v7 import (
    load_graph_index, make_neo4j_session, import_scene_graph_bolt,
    _memory_verify, verify_valid,
    fetch_l2_gaps, node_obj, _rel_dir, graph_converge_rows,
    graph_directed_refs_for_candidates, graph_pivot_neighbors
)
from gap_pipeline.l2_dry_run import DryRunInput, L2DryRunner, L2Gap
from gap_pipeline.l2_constraint_planner import L2ConstraintPlanner
from gap_pipeline.l2_adapter import plan_to_qa_record
import time

sg = Path('outputs/scene-0274_frame14/offline/scene_graphs/scene-0274_frame14_filtered_scene_graph.json')
# Don't re-import, just load
graph_index = load_graph_index(sg)
session = make_neo4j_session()
pool = list(fetch_l2_gaps(session))

planner = L2ConstraintPlanner(max_refs=3, allow_dist_rank=False)
dry_runner = L2DryRunner(planner=planner, min_distance_gap=0.1)

total_gaps = 0
gaps_with_plans = 0
total_plans = 0
plans_pass = 0
plans_fail = 0
fail_reasons = {}

t0 = time.perf_counter()
for i, g in enumerate(pool[:200]):  # check first 200 gaps
    gap = L2Gap(g['a_id'], g['b_id'], g['c_id'], g['a_type'], g['b_type'], g['c_type'])
    a, b, c = node_obj(g, 'a'), node_obj(g, 'b'), node_obj(g, 'c')
    cr = graph_converge_rows(graph_index, gap.a_id, gap.c_id)
    pn = graph_pivot_neighbors(graph_index, gap.b_id)
    dr = graph_directed_refs_for_candidates(graph_index, [r.get('id') for r in cr if r.get('id')])
    out = graph_index.get('out', {})
    data = DryRunInput(gap, a, b, c, converge_rows=cr, pivot_neighbors=pn, available_refs=dr)
    data.a_to_b_dir = _rel_dir(out.get(gap.a_id, {}).get(gap.b_id, {}))
    data.c_to_b_dir = _rel_dir(out.get(gap.c_id, {}).get(gap.b_id, {}))
    data.b_to_a_dir = _rel_dir(out.get(gap.b_id, {}).get(gap.a_id, {}))
    data.b_to_c_dir = _rel_dir(out.get(gap.b_id, {}).get(gap.c_id, {}))
    plans = dry_runner.feasible(data)
    total_gaps += 1
    if plans:
        gaps_with_plans += 1
    for plan in plans:
        total_plans += 1
        qa = plan_to_qa_record(data, plan, question_id='test', scene_name='s', frame_idx=14)
        qa = _memory_verify(graph_index, qa)
        if verify_valid(qa):
            plans_pass += 1
        else:
            plans_fail += 1
            fam = plan.family.value
            fail_reasons[fam] = fail_reasons.get(fam, 0) + 1

t1 = time.perf_counter()
print(f"Checked {total_gaps} gaps in {t1-t0:.1f}s")
print(f"gaps_with_plans={gaps_with_plans}/{total_gaps}")
print(f"total_plans={total_plans} pass={plans_pass} fail={plans_fail} rate={plans_pass/max(total_plans,1)*100:.1f}%")
print(f"fail_by_family={fail_reasons}")
