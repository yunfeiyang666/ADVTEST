"""Profile the ACTUAL selection loop — simulate what run_neo4j does."""
import os, time, json, random
from pathlib import Path
os.environ["NEO4J_NOTIFICATIONS_MIN_SEVERITY"] = "OFF"

from run_gap_pipeline_v7 import (
    load_graph_index, make_neo4j_session, import_scene_graph_bolt,
    fetch_l2_gaps, L2GapSelector, L2DryRunner, L2ConstraintPlanner,
    graph_pivot_neighbors, graph_converge_rows, graph_directed_refs_for_candidates,
    node_obj, DryRunInput, L2Gap, _rel_dir, l2_key, l1_key,
    plan_to_qa_record, _memory_verify, verify_valid,
    choose_formal_plan, normalize_and_validate,
    L2CoverageState, compute_strict_family_targets, compute_family_targets,
    FORMAL_FAMILY_RATIO, FORMAL_FAMILY_MAX_RATIO, FORMAL_FAMILY_MIN_RATIO,
    AUXILIARY_FAMILIES, AUXILIARY_MAX_RATIO, family_cap_blocked,
    plan_attempt_key,
)
from gap_pipeline.l2_question_realizer import set_variant_seed

artifacts_dir = Path("outputs/scene-0274_frame14")
sg_path = artifacts_dir / "offline/scene_graphs/scene-0274_frame14_filtered_scene_graph.json"

graph_index = load_graph_index(sg_path)
session = make_neo4j_session()
pool = L2GapSelector(rng=random.Random(0)).shuffled(fetch_l2_gaps(session))
set_variant_seed(0)
planner = L2ConstraintPlanner(max_refs=3, allow_dist_rank=False)
dry_runner = L2DryRunner(planner=planner, min_distance_gap=0.1)

# Precompute
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

# Build plan_cache with full verify (same as run_neo4j)
print("Building plan_cache with full verify...")
t0 = time.perf_counter()
plan_cache = {}
pool_index = {}
available_family_counts = {}
filtered = 0
total_p = 0
for g in pool:
    key = l2_key(g["a_id"], g["b_id"], g["c_id"])
    data, plans = build_gap_plans(g)
    if plans:
        verified = []
        for plan in plans:
            total_p += 1
            qa = plan_to_qa_record(data, plan, question_id="0", scene_name="s", frame_idx=0)
            qa = _memory_verify(graph_index, qa)
            if verify_valid(qa):
                verified.append(plan)
            else:
                filtered += 1
        plans = verified
    plan_cache[key] = (data, plans)
    pool_index[key] = g
    for plan in plans:
        fam = plan.family.value
        available_family_counts[fam] = available_family_counts.get(fam, 0) + 1
t1 = time.perf_counter()
print(f"plan_cache: {t1-t0:.1f}s, filtered={filtered}/{total_p}")

# Now simulate selection loop
print("\nSimulating selection loop...")
selector = L2GapSelector(rng=random.Random(0))
coverage = L2CoverageState()
used_counts = {}
out = []
family_targets = compute_strict_family_targets(len(pool), available_family_counts)

# Pre-sort
_gap_plans = {}
for gk, (_, plans) in plan_cache.items():
    indexed = list(enumerate(plans))
    indexed.sort(key=lambda x: len((x[1].footprint or {}).get("l2", [])), reverse=True)
    _gap_plans[gk] = indexed

active_keys = set(pool_index.keys())

def _gap_score(gk):
    g = pool_index[gk]
    a, b, c = str(g["a_id"]), str(g["b_id"]), str(g["c_id"])
    l0_new = sum(1 for x in (a, b, c) if x not in coverage.l0)
    l1_ab = l1_key(a, b) not in coverage.l1
    l1_bc = l1_key(b, c) not in coverage.l1
    l1_new = int(l1_ab) + int(l1_bc)
    return l0_new * 100 + l1_new * 10 + 1

# Sort gap keys
t_sort_start = time.perf_counter()
sorted_keys = sorted(active_keys, key=lambda gk: _gap_score(gk), reverse=True)
t_sort_end = time.perf_counter()
print(f"  Sorting {len(sorted_keys)} gaps: {t_sort_end-t_sort_start:.1f}s")

_tried_fast = set()
cursor_pos = 0

t_sel_start = time.perf_counter()
t_select = 0
t_process = 0
t_emit = 0

while len(coverage.l2) < len(pool) and cursor_pos < len(sorted_keys):
    # Select
    ts = time.perf_counter()
    while cursor_pos < len(sorted_keys):
        gk = sorted_keys[cursor_pos]
        cursor_pos += 1
        if gk not in active_keys:
            continue
        candidates = _gap_plans.get(gk, [])
        plan = None
        pi = None
        for _pi, _plan in candidates:
            if (gk, _pi) in _tried_fast:
                continue
            if len(out) >= 50 and family_cap_blocked(_plan.family.value, used_counts, len(out)):
                continue
            plan = _plan
            pi = _pi
            break
        if plan is not None:
            break
    te_sel = time.perf_counter()
    t_select += (te_sel - ts)
    
    if plan is None:
        break
    
    # Process gap
    tp = time.perf_counter()
    g = pool_index[gk]
    data, plans = plan_cache[gk]
    qa = plan_to_qa_record(data, plan, question_id="0", scene_name="s", frame_idx=0, skip_cypher=True)
    qa["logic_verification"] = "IN_MEMORY_VERIFIED"
    qa["_family"] = plan.family.value
    _tried_fast.add((gk, pi))
    te_proc = time.perf_counter()
    t_process += (te_proc - tp)
    
    # Emit
    tem = time.perf_counter()
    qa["question_id"] = str(len(out) + 1)
    family = qa.pop("_family", "")
    qa["selection_phase"] = "primary"
    qa = normalize_and_validate(qa)
    out.append(qa)
    coverage.mark(qa.get("coverage_footprint") or {})
    fp_l2 = set(str(x) for x in (qa.get("coverage_footprint") or {}).get("l2", []))
    active_keys.difference_update(fp_l2)
    used_counts[family] = used_counts.get(family, 0) + 1
    te_emit = time.perf_counter()
    t_emit += (te_emit - tem)
    
    if len(out) % 5000 == 0:
        elapsed = time.perf_counter() - t_sel_start
        print(f"  Q{len(out)} coverage={len(coverage.l2)}/{len(pool)} elapsed={elapsed:.1f}s select={t_select:.1f}s process={t_process:.1f}s emit={t_emit:.1f}s")

t_sel_end = time.perf_counter()
total_sel = t_sel_end - t_sel_start

print(f"\n=== SELECTION LOOP DONE ===")
print(f"Generated: {len(out)} QAs")
print(f"Coverage: {len(coverage.l2)}/{len(pool)} ({len(coverage.l2)/len(pool)*100:.1f}%)")
print(f"Total selection loop: {total_sel:.1f}s")
print(f"  select:  {t_select:.1f}s ({t_select/total_sel*100:.1f}%)")
print(f"  process: {t_process:.1f}s ({t_process/total_sel*100:.1f}%)")
print(f"  emit:    {t_emit:.1f}s ({t_emit/total_sel*100:.1f}%)")
print(f"  sorting: {t_sort_end-t_sort_start:.1f}s")
print(f"\nFull pipeline estimate: plan_cache={t1-t0:.1f}s + sort={t_sort_end-t_sort_start:.1f}s + loop={total_sel:.1f}s = {t1-t0+t_sort_end-t_sort_start+total_sel:.1f}s")
