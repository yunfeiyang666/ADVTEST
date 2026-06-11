"""Trace the EXACT planner flow vs verify flow for the failing gap."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from gap_pipeline.l2_constraint_planner import L2ConstraintPlanner, ref_dir_to, obj_id
from gap_pipeline.l2_dry_run import L2DryRunner, DryRunInput
from gap_pipeline.l2_taxonomy import L2Family, L2Gap
from gap_pipeline.l2_candidate_builder import build_converge_candidates, normalize_candidate
from run_gap_pipeline_v7 import (
    fetch_l2_gaps, make_neo4j_session, load_graph_index,
    graph_converge_rows, graph_directed_refs_for_candidates,
    graph_pivot_neighbors, node_obj, _rel_dir, V7ArtifactPaths, L2GapSelector,
)
import advtest_env
advtest_env.load_advtest_env()

artifact_root = Path("outputs")
artifacts = V7ArtifactPaths(artifact_root, scene_id="scene-0274", frame_id="14")
session = make_neo4j_session()
graph_index = load_graph_index(artifacts.filtered_scene_graph)
pool = L2GapSelector(rng=__import__('random').Random(0)).shuffled(fetch_l2_gaps(session))
_gi_out = graph_index.get("out", {})
_gi_obj = graph_index.get("objects", {})

# Find the specific failing gap
target_gap = None
for g in pool:
    if g["a_id"] == "barrier30" and g["b_id"] == "pedestrian16" and g["c_id"] == "truck1":
        target_gap = g
        break

gap = L2Gap(target_gap["a_id"], target_gap["b_id"], target_gap["c_id"],
            target_gap["a_type"], target_gap["b_type"], target_gap["c_type"])
a, b, c = node_obj(target_gap, "a"), node_obj(target_gap, "b"), node_obj(target_gap, "c")

# Build data exactly like production
converge_rows = graph_converge_rows(graph_index, gap.a_id, gap.c_id)
cand_ids = [str(r.get("id")) for r in converge_rows if r.get("id")]
directed_refs = graph_directed_refs_for_candidates(graph_index, cand_ids)
pivot_neighbors = graph_pivot_neighbors(graph_index, gap.b_id)

a_out_d = graph_index.get("out", {}).get(gap.a_id, {})
c_out_d = graph_index.get("out", {}).get(gap.c_id, {})
data = DryRunInput(gap, a, b, c, converge_rows=converge_rows,
                   pivot_neighbors=pivot_neighbors, available_refs=directed_refs)
data.a_to_b_dir = _rel_dir(a_out_d.get(gap.b_id, {}))
data.c_to_b_dir = _rel_dir(c_out_d.get(gap.b_id, {}))

print(f"Gap: A={gap.a_id}, B={gap.b_id} (type={gap.b_type}), C={gap.c_id}")
print(f"dir A→B: {data.a_to_b_dir}")
print(f"dir C→B: {data.c_to_b_dir}")

# ── 1. What converge_rows returns (candidates for type + dir filtering) ──
print(f"\n{'='*60}")
print("1. converge_rows (common neighbors of A and C with stored dirs)")
print(f"Total: {len(converge_rows)}")
for r in converge_rows:
    if r.get("type") == gap.b_type:
        marker = " ← TARGET" if r.get("id") == gap.b_id else ""
        print(f"  {r['id']}: type={r['type']}, dir_from_a={r.get('dir_from_a')}, dir_from_c={r.get('dir_from_c')}{marker}")

# ── 2. build_converge_candidates (after type + dir filter) ──
candidates = build_converge_candidates(
    converge_rows,
    target_type=gap.b_type,
    dir_from_a=data.a_to_b_dir,
    dir_from_c=data.c_to_b_dir,
)
print(f"\n{'='*60}")
print(f"2. build_converge_candidates (type={gap.b_type}, dir_a={data.a_to_b_dir}, dir_c={data.c_to_b_dir})")
print(f"Count: {len(candidates)}")
for cd in candidates:
    marker = " ← TARGET" if (cd.get("id") or cd.get("unique_id")) == gap.b_id else ""
    print(f"  {cd.get('id') or cd.get('unique_id')}: type={cd.get('type')}{marker}")

# ── 3. Planner trace ──
target = normalize_candidate(b)
planner = L2ConstraintPlanner(max_refs=3, allow_dist_rank=False)

# Add refs
cand_ids_set = {c.get("id") or "" for c in candidates}
extra_refs = [r for r in directed_refs if (r.get("id") or r.get("unique_id") or "") not in cand_ids_set]
refs = candidates + extra_refs

result = planner.plan(target, candidates, available_refs=refs)
print(f"\n{'='*60}")
print(f"3. Planner result")
print(f"Unique: {result.unique}")
print(f"Clauses: {len(result.clauses)}")
for cl in result.clauses:
    print(f"  kind={cl.kind}, ref={cl.ref_id}, value={cl.value}")
print(f"Trace: {result.trace}")

# ── 4. Now trace what verify does with these clauses ──
print(f"\n{'='*60}")
print(f"4. Verify trace")

def _gi_dir(src, dst):
    rel = _gi_out.get(src, {}).get(dst)
    if not rel: return None
    d = rel.get("direction_6") or rel.get("direction_official")
    if d: return str(d)
    return None

# Step 1: type + dir from A
verify_cands = set()
for dst, rel in _gi_out.get(gap.a_id, {}).items():
    obj = _gi_obj.get(dst, {})
    if obj.get("type") == gap.b_type and _gi_dir(gap.a_id, dst) == data.a_to_b_dir:
        verify_cands.add(dst)
print(f"After type+dir_from_A filter: {sorted(verify_cands)}")

# Step 2: dir from C
verify_cands = {x for x in verify_cands if _gi_dir(gap.c_id, x) == data.c_to_b_dir}
print(f"After dir_from_C filter: {sorted(verify_cands)}")

# Step 3: apply each clause
for cl in result.clauses:
    if cl.kind == "ref_dir" and cl.ref_id and cl.value:
        before = set(verify_cands)
        verify_cands = {x for x in verify_cands if _gi_dir(cl.ref_id, x) == cl.value}
        removed = before - verify_cands
        print(f"\nClause: ref={cl.ref_id}, expected_dir={cl.value}")
        print(f"  Before: {sorted(before)}")
        print(f"  After:  {sorted(verify_cands)}")
        print(f"  Removed: {sorted(removed)}")
        # For each candidate, show what direction we see
        for cand in sorted(before):
            actual = _gi_dir(cl.ref_id, cand)
            # Also check what planner's ref_dir_to would return
            ref_obj = None
            for r in refs:
                if (r.get("id") or r.get("unique_id")) == cl.ref_id:
                    ref_obj = r
                    break
            cand_obj = None
            for cd in candidates:
                if (cd.get("id") or cd.get("unique_id")) == cand:
                    cand_obj = cd
                    break
            planner_dir = ref_dir_to(ref_obj, cand_obj) if ref_obj and cand_obj else "N/A"
            match = "✓" if actual == cl.value else "✗"
            print(f"    {cand}: _gi_dir={actual}, ref_dir_to={planner_dir} {match}")

print(f"\nFinal verify candidates: {sorted(verify_cands)}")
print(f"Expected: exactly [{gap.b_id}]")
print(f"PASS: {len(verify_cands) == 1 and gap.b_id in verify_cands}")
