"""Diagnostic: compare _memory_verify vs Neo4j execute_verify on same QA records."""
import json, sys, os, copy
from pathlib import Path

# Suppress Neo4j warnings
import warnings; warnings.filterwarnings("ignore")
os.environ["NEO4J_NOTIFICATIONS_MIN_SEVERITY"] = "OFF"

from run_gap_pipeline_v7 import (
    load_graph_index, make_neo4j_session, import_scene_graph_bolt,
    _memory_verify, execute_verify, verify_valid, classify_verify_failure,
    fetch_l2_gaps, l2_key,
    node_obj, _rel_dir, graph_converge_rows, graph_directed_refs_for_candidates,
    graph_pivot_neighbors
)
from gap_pipeline.l2_dry_run import DryRunInput, L2DryRunner, L2Gap
from gap_pipeline.l2_constraint_planner import L2ConstraintPlanner
from gap_pipeline.l2_adapter import plan_to_qa_record

sg = Path('outputs/scene-0274_frame14/offline/scene_graphs/scene-0274_frame14_filtered_scene_graph.json')
import_scene_graph_bolt(sg)
session = make_neo4j_session()
graph_index = load_graph_index(sg)

pool = list(fetch_l2_gaps(session))[:30]
planner = L2ConstraintPlanner(max_refs=3, allow_dist_rank=False)
dry_runner = L2DryRunner(planner=planner, min_distance_gap=0.1)

match = 0
mismatch = 0
mem_only_fail = 0
neo_only_fail = 0

for g in pool:
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
    if not plans:
        continue
    
    for plan in plans[:3]:  # test first 3 plans per gap
        qa_base = plan_to_qa_record(data, plan, question_id='test', scene_name='scene-0274', frame_idx=14)
        
        # Memory verify
        qa_mem = copy.deepcopy(qa_base)
        _memory_verify(graph_index, qa_mem)
        mem_valid = verify_valid(qa_mem)
        
        # Neo4j verify
        qa_neo = copy.deepcopy(qa_base)
        execute_verify(session, qa_neo)
        neo_valid = verify_valid(qa_neo)
        
        if mem_valid == neo_valid:
            match += 1
        else:
            mismatch += 1
            if not mem_valid and neo_valid:
                mem_only_fail += 1
            elif mem_valid and not neo_valid:
                neo_only_fail += 1
            fam = plan.family.value
            print(f"MISMATCH gap={gap.a_id}|{gap.b_id}|{gap.c_id} family={fam}")
            print(f"  MEM valid={mem_valid} result={json.dumps(qa_mem.get('verify_result'), default=str)[:200]}")
            print(f"  NEO valid={neo_valid} result={json.dumps(qa_neo.get('verify_result'), default=str)[:200]}")
            print(f"  verify_payload params={json.dumps((qa_base.get('verify_payload') or {}).get('params', {}), default=str)[:200]}")
            print()

print(f"\n=== SUMMARY: match={match} mismatch={mismatch} mem_only_fail={mem_only_fail} neo_only_fail={neo_only_fail} ===")
