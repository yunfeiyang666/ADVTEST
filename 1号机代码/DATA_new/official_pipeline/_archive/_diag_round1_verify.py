"""Final pinpoint: the direction asymmetry bug.

Hypothesis: `dir_to` map stores _rel_dir(ref→candidate) but the planner 
uses ref_dir_to(ref, candidate) which first checks dir_to[candidate_id].
Meanwhile _gi_dir uses out[ref_id][candidate_id].

If ref_to and out use DIFFERENT edge directions (e.g. one is A→B, other B→A),
this explains the discrepancy.

Let's check with a concrete failing example.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from collections import Counter
from gap_pipeline.l2_constraint_planner import L2ConstraintPlanner, ref_dir_to, obj_id
from gap_pipeline.l2_dry_run import L2DryRunner, DryRunInput, DryRunPlan, _dir as geom_dir
from gap_pipeline.l2_taxonomy import L2Family, L2Gap
from gap_pipeline.l2_candidate_builder import build_converge_candidates, normalize_candidate
from run_gap_pipeline_v7 import (
    fetch_l2_gaps, make_neo4j_session, load_graph_index,
    graph_pivot_neighbors, graph_converge_rows, graph_directed_refs_for_candidates,
    node_obj, l2_key, _rel_dir, V7ArtifactPaths, L2GapSelector,
)
import advtest_env

advtest_env.load_advtest_env()

artifact_root = Path("outputs")
scene_id = "scene-0274"
frame_id = "14"
artifacts = V7ArtifactPaths(artifact_root, scene_id=scene_id, frame_id=frame_id)

session = make_neo4j_session()
graph_index = load_graph_index(artifacts.filtered_scene_graph)
pool = L2GapSelector(rng=__import__('random').Random(0)).shuffled(fetch_l2_gaps(session))

_gi_out = graph_index.get("out", {})
_gi_obj = graph_index.get("objects", {})

def _gi_dir(src, dst):
    rel = _gi_out.get(src, {}).get(dst)
    if not rel: return None
    d = rel.get("direction_6") or rel.get("direction_official")
    if d: return str(d)
    return None

# Precompute
_pivot_cache, _converge_cache, _refs_cache = {}, {}, {}
_unique_b_ids = set(g["b_id"] for g in pool)
for bid in _unique_b_ids:
    _pivot_cache[bid] = graph_pivot_neighbors(graph_index, bid)
_unique_ac = set((g["a_id"], g["c_id"]) for g in pool)
for a_id, c_id in _unique_ac:
    _converge_cache[(a_id, c_id)] = graph_converge_rows(graph_index, a_id, c_id)
for ac_key, rows in _converge_cache.items():
    cand_ids = [str(r.get("id")) for r in rows if r.get("id")]
    _refs_cache[ac_key] = graph_directed_refs_for_candidates(graph_index, cand_ids)

planner = L2ConstraintPlanner(max_refs=3, allow_dist_rank=False)
dry_runner = L2DryRunner(planner=planner, min_distance_gap=0.1)

# Find first failing gap and trace in detail
for g in pool:
    gap = L2Gap(g["a_id"], g["b_id"], g["c_id"], g["a_type"], g["b_type"], g["c_type"])
    a, b, c = node_obj(g, "a"), node_obj(g, "b"), node_obj(g, "c")
    converge_rows = _converge_cache.get((gap.a_id, gap.c_id), [])
    directed_refs = _refs_cache.get((gap.a_id, gap.c_id), [])
    pivot_neighbors = _pivot_cache.get(gap.b_id, [])
    a_out_dict = graph_index.get("out", {}).get(gap.a_id, {})
    b_out_dict = graph_index.get("out", {}).get(gap.b_id, {})
    c_out_dict = graph_index.get("out", {}).get(gap.c_id, {})
    data = DryRunInput(gap, a, b, c, converge_rows=converge_rows,
                       pivot_neighbors=pivot_neighbors, available_refs=directed_refs)
    data.a_to_b_dir = _rel_dir(a_out_dict.get(gap.b_id, {}))
    data.c_to_b_dir = _rel_dir(c_out_dict.get(gap.b_id, {}))
    data.b_to_a_dir = _rel_dir(b_out_dict.get(gap.a_id, {}))
    data.b_to_c_dir = _rel_dir(b_out_dict.get(gap.c_id, {}))

    all_plans = dry_runner.run(data)
    converge_feasible = [p for p in all_plans if p.feasible and p.family == L2Family.CONVERGE]
    if not converge_feasible:
        continue

    plan = converge_feasible[0]
    
    # Verify
    target_type = gap.b_type
    dir_from_a = data.a_to_b_dir or ""
    dir_from_c = data.c_to_b_dir or ""
    candidates = set()
    for dst, rel in _gi_out.get(gap.a_id, {}).items():
        obj = _gi_obj.get(dst, {})
        if obj.get("type") == target_type and _gi_dir(gap.a_id, dst) == dir_from_a:
            candidates.add(dst)
    candidates = {x for x in candidates if _gi_dir(gap.c_id, x) == dir_from_c}
    
    passed = True
    for clause in plan.clauses:
        if clause.kind == "ref_dir" and clause.ref_id and clause.value:
            old = set(candidates)
            candidates = {x for x in candidates if _gi_dir(clause.ref_id, x) == clause.value}
            if gap.b_id not in candidates and gap.b_id in old:
                # Found the failing clause!
                print(f"{'='*60}")
                print(f"FAILING GAP: A={gap.a_id}, B={gap.b_id}, C={gap.c_id}")
                print(f"B_type={gap.b_type}")
                print(f"dir A→B: {dir_from_a}")
                print(f"dir C→B: {dir_from_c}")
                print(f"{'='*60}")
                
                print(f"\nFailing clause: ref={clause.ref_id}, expected_dir={clause.value}")
                print(f"  _gi_dir(ref→B) = {_gi_dir(clause.ref_id, gap.b_id)}")
                print(f"  clause.value   = {clause.value}")
                
                # What did the planner's ref_dir_to see?
                # Find the ref in directed_refs
                ref_obj = None
                for r in directed_refs:
                    if str(r.get("id")) == clause.ref_id:
                        ref_obj = r
                        break
                
                if ref_obj:
                    dir_to_map = ref_obj.get("dir_to", {})
                    print(f"\n  ref_obj dir_to map for B ({gap.b_id}):")
                    print(f"    dir_to[B] = {dir_to_map.get(gap.b_id)}")
                    print(f"    Full dir_to: {json.dumps(dir_to_map, indent=6)}")
                    
                    # What does graph_index say about ref→B?
                    ref_to_b_rel = _gi_out.get(clause.ref_id, {}).get(gap.b_id, {})
                    print(f"\n  graph_index out[ref][B]:")
                    print(f"    _rel_dir = {_rel_dir(ref_to_b_rel)}")
                    print(f"    raw rel = {json.dumps({k:v for k,v in ref_to_b_rel.items() if k in ('direction_6','direction_official','angle','src','dst')}, indent=6)}")
                    
                    # Check reverse: B→ref
                    b_to_ref_rel = _gi_out.get(gap.b_id, {}).get(clause.ref_id, {})
                    print(f"\n  graph_index out[B][ref]:")
                    print(f"    _rel_dir = {_rel_dir(b_to_ref_rel)}")
                    print(f"    raw rel = {json.dumps({k:v for k,v in b_to_ref_rel.items() if k in ('direction_6','direction_official','angle','src','dst')}, indent=6)}")
                
                print(f"\n  Candidates before this clause: {old}")
                print(f"  Candidates after this clause:  {candidates}")
                
                # The KEY question: planner's ref_dir_to uses dir_to map which stores
                # _rel_dir(out[ref][cand]). Verify also uses _gi_dir(ref, cand) which
                # reads out[ref][cand]. If they're the same edge, the values should match.
                # 
                # UNLESS: the ref→cand edge doesn't exist in graph_index (only cand→ref exists)
                
                print(f"\n  Does edge ref→B exist? {gap.b_id in _gi_out.get(clause.ref_id, {})}")
                print(f"  Does edge B→ref exist? {clause.ref_id in _gi_out.get(gap.b_id, {})}")
                
                # Check all candidates to see what dir_to says vs _gi_dir
                print(f"\n  All candidates dir comparison:")
                for cand in old:
                    dt = dir_to_map.get(cand) if ref_obj else None
                    gi = _gi_dir(clause.ref_id, cand)
                    match = "✓" if dt == gi else "✗ MISMATCH"
                    print(f"    {cand}: dir_to={dt}, _gi_dir={gi} {match}")
                
                passed = False
                break
    
    if not passed:
        break

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print("""
The dir_to map comes from graph_directed_refs_for_candidates():
  ref["dir_to"][cand_id] = _rel_dir(out[ref_id][cand_id])

The verify _gi_dir does:
  out[ref_id][candidate_id] → direction_6 or direction_official

Both should read the SAME edge data. If they ever disagree, it means
the edge was MISSING when building dir_to (so dir_to[cand]=None was set)
but present in the full graph_index used by verify, or vice versa.

OR: the planner's ref_dir_to falls back to geometric when dir_to is None!
""")
