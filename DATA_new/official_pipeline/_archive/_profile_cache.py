"""Profile the plan_cache build phase — the real bottleneck."""
import os, time, json
from pathlib import Path
os.environ["NEO4J_NOTIFICATIONS_MIN_SEVERITY"] = "OFF"

from run_gap_pipeline_v7 import (
    load_graph_index, make_neo4j_session, import_scene_graph_bolt,
    fetch_l2_gaps, L2GapSelector, L2DryRunner, L2ConstraintPlanner,
    graph_pivot_neighbors, graph_converge_rows, graph_directed_refs_for_candidates,
    node_obj, DryRunInput, L2Gap, _rel_dir, l2_key,
    plan_to_qa_record, _memory_verify, verify_valid,
)

artifacts_dir = Path("outputs/scene-0274_frame14")
sg_path = artifacts_dir / "offline/scene_graphs/scene-0274_frame14_filtered_scene_graph.json"

# Setup
graph_index = load_graph_index(sg_path)
session = make_neo4j_session()
pool = L2GapSelector(rng=__import__('random').Random(0)).shuffled(fetch_l2_gaps(session))

planner = L2ConstraintPlanner(max_refs=3, allow_dist_rank=False)
dry_runner = L2DryRunner(planner=planner, min_distance_gap=0.1)

# Precompute caches (same as main code)
_pivot_cache = {}
for bid in set(g["b_id"] for g in pool):
    _pivot_cache[bid] = graph_pivot_neighbors(graph_index, bid)
_converge_cache = {}
for a_id, c_id in set((g["a_id"], g["c_id"]) for g in pool):
    _converge_cache[(a_id, c_id)] = graph_converge_rows(graph_index, a_id, c_id)
_refs_cache = {}
for ac_key, rows in _converge_cache.items():
    cand_ids = [str(r.get("id")) for r in rows if r.get("id")]
    _refs_cache[ac_key] = graph_directed_refs_for_candidates(graph_index, cand_ids)

def build_gap_plans(g):
    gap = L2Gap(g["a_id"], g["b_id"], g["c_id"], g["a_type"], g["b_type"], g["c_type"])
    a, b, c = node_obj(g, "a"), node_obj(g, "b"), node_obj(g, "c")
    converge_rows = _converge_cache.get((gap.a_id, gap.c_id), [])
    directed_refs = _refs_cache.get((gap.a_id, gap.c_id), [])
    pivot_neighbors = _pivot_cache.get(gap.b_id, [])
    a_out = graph_index.get("out", {}).get(gap.a_id, {})
    b_out = graph_index.get("out", {}).get(gap.b_id, {})
    c_out = graph_index.get("out", {}).get(gap.c_id, {})
    data = DryRunInput(gap, a, b, c, converge_rows=converge_rows, pivot_neighbors=pivot_neighbors, available_refs=directed_refs)
    data.a_to_b_dir = _rel_dir(a_out.get(gap.b_id, {}))
    data.c_to_b_dir = _rel_dir(c_out.get(gap.b_id, {}))
    data.b_to_a_dir = _rel_dir(b_out.get(gap.a_id, {}))
    data.b_to_c_dir = _rel_dir(b_out.get(gap.c_id, {}))
    plans = dry_runner.feasible(data)
    return data, plans

# Phase 1: build_gap_plans only (no verify)
print("Phase 1: build_gap_plans only...")
t0 = time.perf_counter()
cache_no_verify = {}
total_plans = 0
for g in pool:
    key = l2_key(g["a_id"], g["b_id"], g["c_id"])
    data, plans = build_gap_plans(g)
    cache_no_verify[key] = (data, plans)
    total_plans += len(plans)
t1 = time.perf_counter()
print(f"  {t1-t0:.1f}s for {len(pool)} gaps, {total_plans} plans")

# Phase 2: plan_to_qa_record (skip_cypher=False) only — separate cost
print("\nPhase 2: plan_to_qa_record (skip_cypher=False) for ALL plans...")
t2 = time.perf_counter()
qa_count = 0
for key, (data, plans) in cache_no_verify.items():
    for plan in plans:
        qa = plan_to_qa_record(data, plan, question_id="0", scene_name="s", frame_idx=0, skip_cypher=False)
        qa_count += 1
t3 = time.perf_counter()
print(f"  {t3-t2:.1f}s for {qa_count} plan_to_qa_record calls ({(t3-t2)/qa_count*1000:.3f}ms/call)")

# Phase 3: _memory_verify only — separate cost
print("\nPhase 3: _memory_verify for ALL plans...")
t4 = time.perf_counter()
verify_count = 0
for key, (data, plans) in cache_no_verify.items():
    for plan in plans:
        qa = plan_to_qa_record(data, plan, question_id="0", scene_name="s", frame_idx=0, skip_cypher=False)
        qa = _memory_verify(graph_index, qa)
        verify_count += 1
t5 = time.perf_counter()
print(f"  {t5-t4:.1f}s for {verify_count} (plan_to_qa + _memory_verify) ({(t5-t4)/verify_count*1000:.3f}ms/call)")

# Phase 4: plan_to_qa_record (skip_cypher=True) — see if cypher building matters
print("\nPhase 4: plan_to_qa_record (skip_cypher=True) for ALL plans...")
t6 = time.perf_counter()
qa_count2 = 0
for key, (data, plans) in cache_no_verify.items():
    for plan in plans:
        qa = plan_to_qa_record(data, plan, question_id="0", scene_name="s", frame_idx=0, skip_cypher=True)
        qa_count2 += 1
t7 = time.perf_counter()
print(f"  {t7-t6:.1f}s for {qa_count2} calls ({(t7-t6)/qa_count2*1000:.3f}ms/call)")

# Phase 5: just _memory_verify (given pre-built qa)
print("\nPhase 5: _memory_verify only (pre-built QAs)...")
sample_qas = []
for key, (data, plans) in list(cache_no_verify.items())[:500]:
    for plan in plans:
        qa = plan_to_qa_record(data, plan, question_id="0", scene_name="s", frame_idx=0, skip_cypher=False)
        sample_qas.append(qa)
        if len(sample_qas) >= 5000:
            break
    if len(sample_qas) >= 5000:
        break
t8 = time.perf_counter()
for qa in sample_qas:
    qa2 = _memory_verify(graph_index, dict(qa))
t9 = time.perf_counter()
print(f"  {t9-t8:.1f}s for {len(sample_qas)} _memory_verify calls ({(t9-t8)/len(sample_qas)*1000:.3f}ms/call)")

print("\n=== SUMMARY ===")
print(f"build_gap_plans (dry_runner.feasible):  {t1-t0:.1f}s  (this is the main cost)")
print(f"plan_to_qa_record(skip_cypher=False):   {t3-t2:.1f}s  for {qa_count} plans")
print(f"plan_to_qa_record(skip_cypher=True):    {t7-t6:.1f}s  for {qa_count2} plans")
print(f"_memory_verify alone:                   {(t9-t8)/len(sample_qas)*qa_count:.1f}s  (extrapolated for {qa_count})")
print(f"Total plan_cache with full verify:      ~{t1-t0 + t3-t2 + (t9-t8)/len(sample_qas)*qa_count:.1f}s")
