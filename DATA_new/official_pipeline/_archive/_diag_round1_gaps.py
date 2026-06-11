"""Diagnose why Round 1 (converge + diverge) fails to cover all L2 gaps.

Runs on a single frame and reports:
1. How many gaps have NO feasible converge/diverge plan at all (dry_runner.feasible returns empty)
2. How many gaps have feasible plans but fail _direct_plan_verify
3. Breakdown of failure reasons from DryRunner (non-unique, missing inputs, etc.)
4. Impact of allow_dist_rank=False vs True
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from collections import Counter
from gap_pipeline.l2_constraint_planner import L2ConstraintPlanner
from gap_pipeline.l2_dry_run import L2DryRunner, DryRunInput, DryRunPlan
from gap_pipeline.l2_taxonomy import L2Family, L2Gap
from run_gap_pipeline_v7 import (
    fetch_l2_gaps, make_neo4j_session, load_graph_index,
    graph_pivot_neighbors, graph_converge_rows, graph_directed_refs_for_candidates,
    node_obj, l2_key, _rel_dir, import_scene_graph_bolt,
    V7ArtifactPaths, L2GapSelector,
)
import advtest_env

advtest_env.load_advtest_env()

# Use frame14 as test case
artifact_root = Path("outputs")
scene_id = "scene-0274"
frame_id = "14"
artifacts = V7ArtifactPaths(artifact_root, scene_id=scene_id, frame_id=frame_id)

print(f"=== Diagnosing Round 1 coverage for {scene_id} frame {frame_id} ===")
print(f"Scene graph: {artifacts.filtered_scene_graph}")

# Load scene graph
import_scene_graph_bolt(artifacts.filtered_scene_graph)
session = make_neo4j_session()
graph_index = load_graph_index(artifacts.filtered_scene_graph)
pool = L2GapSelector(rng=__import__('random').Random(0)).shuffled(fetch_l2_gaps(session))
print(f"Total L2 gaps (pool): {len(pool)}")

# Precompute caches (same as production)
_pivot_cache = {}
_converge_cache = {}
_refs_cache = {}
_unique_b_ids = set(g["b_id"] for g in pool)
for bid in _unique_b_ids:
    _pivot_cache[bid] = graph_pivot_neighbors(graph_index, bid)
_unique_ac = set((g["a_id"], g["c_id"]) for g in pool)
for a_id, c_id in _unique_ac:
    _converge_cache[(a_id, c_id)] = graph_converge_rows(graph_index, a_id, c_id)
for ac_key, rows in _converge_cache.items():
    cand_ids = [str(r.get("id")) for r in rows if r.get("id")]
    _refs_cache[ac_key] = graph_directed_refs_for_candidates(graph_index, cand_ids)

_gi_out = graph_index.get("out", {})
_gi_obj = graph_index.get("objects", {})

def _gi_dir(src, dst):
    rel = _gi_out.get(src, {}).get(dst)
    if not rel: return None
    d = rel.get("direction_6") or rel.get("direction_official")
    if d: return str(d)
    angle = rel.get("angle")
    if angle is not None:
        try:
            a = float(angle)
            if -30 < a <= 30: return "front"
            if 30 < a <= 90: return "front_left"
            if -90 < a <= -30: return "front_right"
            if 90 < a <= 150: return "back_left"
            if -150 < a <= -90: return "back_right"
            return "back"
        except: pass
    return None

_ROUND1_FAMILIES = {"converge", "diverge_compare"}

# ── Test 1: Current config (allow_dist_rank=False, max_refs=3) ──
print("\n" + "="*60)
print("TEST 1: Current config (allow_dist_rank=False, max_refs=3)")
print("="*60)

planner_current = L2ConstraintPlanner(max_refs=3, allow_dist_rank=False)
dry_runner_current = L2DryRunner(planner=planner_current, min_distance_gap=0.1)

# Counters
no_plan_reasons = Counter()  # gaps with no feasible plan at all
has_plan_but_verify_fails = 0
has_plan_and_verify_passes = 0
no_feasible_at_all = 0
total_plans_before_verify = 0
total_plans_after_verify = 0
converge_fail_reasons = Counter()
diverge_fail_reasons = Counter()

for g in pool:
    gap = L2Gap(g["a_id"], g["b_id"], g["c_id"], g["a_type"], g["b_type"], g["c_type"])
    a, b, c = node_obj(g, "a"), node_obj(g, "b"), node_obj(g, "c")
    converge_rows = _converge_cache.get((gap.a_id, gap.c_id), [])
    directed_refs = _refs_cache.get((gap.a_id, gap.c_id), [])
    pivot_neighbors = _pivot_cache.get(gap.b_id, [])
    a_out = graph_index.get("out", {}).get(gap.a_id, {})
    b_out = graph_index.get("out", {}).get(gap.b_id, {})
    c_out = graph_index.get("out", {}).get(gap.c_id, {})
    data = DryRunInput(gap, a, b, c, converge_rows=converge_rows,
                       pivot_neighbors=pivot_neighbors, available_refs=directed_refs)
    data.a_to_b_dir = _rel_dir(a_out.get(gap.b_id, {}))
    data.c_to_b_dir = _rel_dir(c_out.get(gap.b_id, {}))
    data.b_to_a_dir = _rel_dir(b_out.get(gap.a_id, {}))
    data.b_to_c_dir = _rel_dir(b_out.get(gap.c_id, {}))

    # All plans (before Round1 filter)
    all_plans = dry_runner_current.run(data)
    
    # Round 1 feasible plans
    r1_feasible = [p for p in all_plans if p.feasible and p.family.value in _ROUND1_FAMILIES]
    
    # Track non-feasible reasons
    for p in all_plans:
        if not p.feasible and p.family.value in _ROUND1_FAMILIES:
            if p.family == L2Family.CONVERGE:
                converge_fail_reasons[p.reason] += 1
            elif p.family == L2Family.DIVERGE_COMPARE:
                diverge_fail_reasons[p.reason] += 1
    
    if not r1_feasible:
        no_feasible_at_all += 1
        # What are the reasons?
        reasons = set()
        for p in all_plans:
            if p.family.value in _ROUND1_FAMILIES:
                reasons.add(f"{p.family.value}:{p.reason}")
        for r in reasons:
            no_plan_reasons[r] += 1
        continue
    
    total_plans_before_verify += len(r1_feasible)
    
    # Check verify
    gap_has_passing = False
    for plan in r1_feasible:
        # Inline _direct_plan_verify
        fam = plan.family.value
        a_id, b_id, c_id = data.gap.a_id, data.gap.b_id, data.gap.c_id
        passed = False
        
        if fam == "converge":
            target_type = data.gap.b_type
            dir_from_a = data.a_to_b_dir or ""
            dir_from_c = data.c_to_b_dir or ""
            candidates = set()
            for dst, rel in _gi_out.get(a_id, {}).items():
                obj = _gi_obj.get(dst, {})
                if obj.get("type") == target_type and _gi_dir(a_id, dst) == dir_from_a:
                    candidates.add(dst)
            if candidates:
                candidates = {x for x in candidates if _gi_dir(c_id, x) == dir_from_c}
                if candidates:
                    for clause in plan.clauses:
                        if clause.kind == "ref_dir" and clause.ref_id and clause.value:
                            candidates = {x for x in candidates if _gi_dir(clause.ref_id, x) == clause.value}
                            if not candidates:
                                break
                    passed = len(candidates) == 1 and next(iter(candidates)) == b_id
        
        elif fam == "diverge_compare":
            from gap_pipeline.l2_adapter import _branch_clauses
            a_type, a_dir = data.gap.a_type, data.b_to_a_dir or ""
            a_cands = set()
            for dst, rel in _gi_out.get(b_id, {}).items():
                obj = _gi_obj.get(dst, {})
                if obj.get("type") == a_type and _gi_dir(b_id, dst) == a_dir:
                    a_cands.add(dst)
            if a_cands:
                a_clauses_list = _branch_clauses(plan, "a", excluded_ref_id="")
                for clause in a_clauses_list:
                    if clause.kind == "ref_dir" and clause.ref_id and clause.value:
                        a_cands = {x for x in a_cands if _gi_dir(clause.ref_id, x) == clause.value}
                        if not a_cands:
                            break
                if len(a_cands) == 1 and next(iter(a_cands)) == a_id:
                    c_type, c_dir = data.gap.c_type, data.b_to_c_dir or ""
                    c_cands = set()
                    for dst, rel in _gi_out.get(b_id, {}).items():
                        obj = _gi_obj.get(dst, {})
                        if obj.get("type") == c_type and _gi_dir(b_id, dst) == c_dir:
                            c_cands.add(dst)
                    if c_cands:
                        c_clauses_list = _branch_clauses(plan, "c", excluded_ref_id="")
                        for clause in c_clauses_list:
                            if clause.kind == "ref_dir" and clause.ref_id and clause.value:
                                c_cands = {x for x in c_cands if _gi_dir(clause.ref_id, x) == clause.value}
                                if not c_cands:
                                    break
                        passed = len(c_cands) == 1 and next(iter(c_cands)) == c_id
        
        if passed:
            total_plans_after_verify += 1
            gap_has_passing = True
            break  # one passing plan is enough
        
    if gap_has_passing:
        has_plan_and_verify_passes += 1
    else:
        has_plan_but_verify_fails += 1

print(f"\nTotal gaps: {len(pool)}")
print(f"  ✓ Has passing plan (Round1 can cover):  {has_plan_and_verify_passes} ({has_plan_and_verify_passes*100/len(pool):.1f}%)")
print(f"  ✗ Has feasible plan but verify fails:   {has_plan_but_verify_fails} ({has_plan_but_verify_fails*100/len(pool):.1f}%)")
print(f"  ✗ No feasible converge/diverge plan:    {no_feasible_at_all} ({no_feasible_at_all*100/len(pool):.1f}%)")
print(f"\nConverge failure reasons:")
for reason, count in converge_fail_reasons.most_common():
    print(f"  {reason}: {count}")
print(f"\nDiverge failure reasons:")
for reason, count in diverge_fail_reasons.most_common():
    print(f"  {reason}: {count}")
print(f"\nNo-plan-at-all breakdown:")
for reason, count in no_plan_reasons.most_common(10):
    print(f"  {reason}: {count}")

# ── Test 2: With allow_dist_rank=True ──
print("\n" + "="*60)
print("TEST 2: With allow_dist_rank=True, max_refs=3")
print("="*60)

planner_dist = L2ConstraintPlanner(max_refs=3, allow_dist_rank=True)
dry_runner_dist = L2DryRunner(planner=planner_dist, min_distance_gap=0.1)

has_plan_dist = 0
for g in pool:
    gap = L2Gap(g["a_id"], g["b_id"], g["c_id"], g["a_type"], g["b_type"], g["c_type"])
    a, b, c = node_obj(g, "a"), node_obj(g, "b"), node_obj(g, "c")
    converge_rows = _converge_cache.get((gap.a_id, gap.c_id), [])
    directed_refs = _refs_cache.get((gap.a_id, gap.c_id), [])
    pivot_neighbors = _pivot_cache.get(gap.b_id, [])
    a_out = graph_index.get("out", {}).get(gap.a_id, {})
    b_out = graph_index.get("out", {}).get(gap.b_id, {})
    c_out = graph_index.get("out", {}).get(gap.c_id, {})
    data = DryRunInput(gap, a, b, c, converge_rows=converge_rows,
                       pivot_neighbors=pivot_neighbors, available_refs=directed_refs)
    data.a_to_b_dir = _rel_dir(a_out.get(gap.b_id, {}))
    data.c_to_b_dir = _rel_dir(c_out.get(gap.b_id, {}))
    data.b_to_a_dir = _rel_dir(b_out.get(gap.a_id, {}))
    data.b_to_c_dir = _rel_dir(b_out.get(gap.c_id, {}))
    r1 = [p for p in dry_runner_dist.feasible(data) if p.family.value in _ROUND1_FAMILIES]
    if r1:
        has_plan_dist += 1

print(f"Gaps with feasible plan (dist_rank=True):  {has_plan_dist} ({has_plan_dist*100/len(pool):.1f}%)")
print(f"Gaps with feasible plan (dist_rank=False): {has_plan_and_verify_passes + has_plan_but_verify_fails} ({(has_plan_and_verify_passes + has_plan_but_verify_fails)*100/len(pool):.1f}%)")
print(f"Improvement: +{has_plan_dist - (has_plan_and_verify_passes + has_plan_but_verify_fails)} gaps")

# ── Test 3: With max_refs=5 ──
print("\n" + "="*60)
print("TEST 3: With max_refs=5, allow_dist_rank=False")
print("="*60)

planner_5 = L2ConstraintPlanner(max_refs=5, allow_dist_rank=False)
dry_runner_5 = L2DryRunner(planner=planner_5, min_distance_gap=0.1)

has_plan_5 = 0
for g in pool:
    gap = L2Gap(g["a_id"], g["b_id"], g["c_id"], g["a_type"], g["b_type"], g["c_type"])
    a, b, c = node_obj(g, "a"), node_obj(g, "b"), node_obj(g, "c")
    converge_rows = _converge_cache.get((gap.a_id, gap.c_id), [])
    directed_refs = _refs_cache.get((gap.a_id, gap.c_id), [])
    pivot_neighbors = _pivot_cache.get(gap.b_id, [])
    a_out = graph_index.get("out", {}).get(gap.a_id, {})
    b_out = graph_index.get("out", {}).get(gap.b_id, {})
    c_out = graph_index.get("out", {}).get(gap.c_id, {})
    data = DryRunInput(gap, a, b, c, converge_rows=converge_rows,
                       pivot_neighbors=pivot_neighbors, available_refs=directed_refs)
    data.a_to_b_dir = _rel_dir(a_out.get(gap.b_id, {}))
    data.c_to_b_dir = _rel_dir(c_out.get(gap.b_id, {}))
    data.b_to_a_dir = _rel_dir(b_out.get(gap.a_id, {}))
    data.b_to_c_dir = _rel_dir(b_out.get(gap.c_id, {}))
    r1 = [p for p in dry_runner_5.feasible(data) if p.family.value in _ROUND1_FAMILIES]
    if r1:
        has_plan_5 += 1

print(f"Gaps with feasible plan (max_refs=5):  {has_plan_5} ({has_plan_5*100/len(pool):.1f}%)")
print(f"Improvement over current: +{has_plan_5 - (has_plan_and_verify_passes + has_plan_but_verify_fails)} gaps")

# ── Test 4: With max_refs=5 AND allow_dist_rank=True ──
print("\n" + "="*60)
print("TEST 4: max_refs=5 + allow_dist_rank=True (最宽松)")
print("="*60)

planner_max = L2ConstraintPlanner(max_refs=5, allow_dist_rank=True)
dry_runner_max = L2DryRunner(planner=planner_max, min_distance_gap=0.1)

has_plan_max = 0
for g in pool:
    gap = L2Gap(g["a_id"], g["b_id"], g["c_id"], g["a_type"], g["b_type"], g["c_type"])
    a, b, c = node_obj(g, "a"), node_obj(g, "b"), node_obj(g, "c")
    converge_rows = _converge_cache.get((gap.a_id, gap.c_id), [])
    directed_refs = _refs_cache.get((gap.a_id, gap.c_id), [])
    pivot_neighbors = _pivot_cache.get(gap.b_id, [])
    a_out = graph_index.get("out", {}).get(gap.a_id, {})
    b_out = graph_index.get("out", {}).get(gap.b_id, {})
    c_out = graph_index.get("out", {}).get(gap.c_id, {})
    data = DryRunInput(gap, a, b, c, converge_rows=converge_rows,
                       pivot_neighbors=pivot_neighbors, available_refs=directed_refs)
    data.a_to_b_dir = _rel_dir(a_out.get(gap.b_id, {}))
    data.c_to_b_dir = _rel_dir(c_out.get(gap.b_id, {}))
    data.b_to_a_dir = _rel_dir(b_out.get(gap.a_id, {}))
    data.b_to_c_dir = _rel_dir(b_out.get(gap.c_id, {}))
    r1 = [p for p in dry_runner_max.feasible(data) if p.family.value in _ROUND1_FAMILIES]
    if r1:
        has_plan_max += 1

print(f"Gaps with feasible plan (max settings):  {has_plan_max} ({has_plan_max*100/len(pool):.1f}%)")
print(f"Improvement over current: +{has_plan_max - (has_plan_and_verify_passes + has_plan_but_verify_fails)} gaps")

# ── Summary ──
print("\n" + "="*60)
print("SUMMARY: Round 1 coverage ceiling under different configs")
print("="*60)
print(f"  Current  (refs=3, dist_rank=off): {has_plan_and_verify_passes + has_plan_but_verify_fails}/{len(pool)} = {(has_plan_and_verify_passes + has_plan_but_verify_fails)*100/len(pool):.1f}%")
print(f"  +dist_rank (refs=3, dist_rank=on): {has_plan_dist}/{len(pool)} = {has_plan_dist*100/len(pool):.1f}%")
print(f"  +more_refs (refs=5, dist_rank=off): {has_plan_5}/{len(pool)} = {has_plan_5*100/len(pool):.1f}%")
print(f"  Max       (refs=5, dist_rank=on):  {has_plan_max}/{len(pool)} = {has_plan_max*100/len(pool):.1f}%")
print(f"\n  Note: verify pass rate further reduces these numbers.")
print(f"  Current verify pass: {has_plan_and_verify_passes}/{has_plan_and_verify_passes + has_plan_but_verify_fails} = {has_plan_and_verify_passes*100/max(has_plan_and_verify_passes + has_plan_but_verify_fails,1):.1f}%")
