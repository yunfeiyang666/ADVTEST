"""Profile the per-QA cost breakdown in the selection loop."""
import os, time, json
from pathlib import Path
os.environ["NEO4J_NOTIFICATIONS_MIN_SEVERITY"] = "OFF"

from run_gap_pipeline_v7 import (
    load_graph_index, make_neo4j_session, import_scene_graph_bolt,
    fetch_l2_gaps, L2GapSelector, L2DryRunner, L2ConstraintPlanner,
    graph_pivot_neighbors, graph_converge_rows, graph_directed_refs_for_candidates,
    node_obj, DryRunInput, L2Gap, _rel_dir, l2_key,
    plan_to_qa_record, _memory_verify, verify_valid,
    choose_formal_plan, normalize_and_validate,
)
from gap_pipeline.l2_question_realizer import set_variant_seed

artifacts_dir = Path("outputs/scene-0274_frame14")
sg_path = artifacts_dir / "offline/scene_graphs/scene-0274_frame14_filtered_scene_graph.json"

# Setup
import_scene_graph_bolt(sg_path)
session = make_neo4j_session()
graph_index = load_graph_index(sg_path)
pool = L2GapSelector(rng=__import__('random').Random(0)).shuffled(fetch_l2_gaps(session))
set_variant_seed(0)
planner = L2ConstraintPlanner(max_refs=3, allow_dist_rank=False)
dry_runner = L2DryRunner(planner=planner, min_distance_gap=0.1)

# Precompute caches
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

print("Building plan_cache (no verify)...")
t0 = time.perf_counter()
plan_cache = {}
for g in pool:
    key = l2_key(g["a_id"], g["b_id"], g["c_id"])
    data, plans = build_gap_plans(g)
    plan_cache[key] = (data, plans)
t1 = time.perf_counter()
print(f"plan_cache: {t1-t0:.1f}s, {len(plan_cache)} gaps")

# Now profile 1000 QA generation cycles
N = 1000
timings = {"plan_to_qa": 0, "normalize": 0, "misc": 0}

print(f"\nProfiling {N} QA generation cycles...")
gaps_with_plans = [(k, v) for k, v in plan_cache.items() if v[1]]
t_start = time.perf_counter()
for i in range(min(N, len(gaps_with_plans))):
    gk, (data, plans) = gaps_with_plans[i]
    plan = plans[0]
    
    t_a = time.perf_counter()
    qa = plan_to_qa_record(data, plan, question_id="0", scene_name="scene-0274", frame_idx=14, skip_cypher=True)
    t_b = time.perf_counter()
    qa["logic_verification"] = "IN_MEMORY_VERIFIED"
    qa["timestamp_start"] = ""
    qa["timestamp_end"] = ""
    qa["generation_elapsed_ms"] = 0
    qa["plan_attempt_key"] = ""
    qa["_family"] = plan.family.value
    qa["question_id"] = str(i)
    qa["selection_phase"] = "primary"
    t_c = time.perf_counter()
    qa = normalize_and_validate(qa)
    t_d = time.perf_counter()
    
    timings["plan_to_qa"] += (t_b - t_a)
    timings["normalize"] += (t_d - t_c)
    timings["misc"] += (t_c - t_b)

t_end = time.perf_counter()
total = t_end - t_start
print(f"\n=== {N} QA cycles in {total*1000:.0f}ms ({total*1000/N:.2f}ms/QA) ===")
for k, v in sorted(timings.items(), key=lambda x: -x[1]):
    print(f"  {k:20s}: {v*1000:.0f}ms total, {v*1000/N:.3f}ms/QA, {v/total*100:.1f}%")

# Now profile what plan_to_qa_record does internally
print("\n\nDeep profiling plan_to_qa_record (with skip_cypher=True)...")
import cProfile, pstats, io
pr = cProfile.Profile()
pr.enable()
for i in range(min(N, len(gaps_with_plans))):
    gk, (data, plans) = gaps_with_plans[i]
    plan = plans[0]
    qa = plan_to_qa_record(data, plan, question_id="0", scene_name="scene-0274", frame_idx=14, skip_cypher=True)
pr.disable()
s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
ps.print_stats(20)
print(s.getvalue())
