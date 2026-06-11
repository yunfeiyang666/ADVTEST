"""Verify _direct_plan_verify matches old plan_to_qa_record + _memory_verify + verify_valid."""
import os, time, random
from pathlib import Path
os.environ["NEO4J_NOTIFICATIONS_MIN_SEVERITY"] = "OFF"

from run_gap_pipeline_v7 import (
    load_graph_index, make_neo4j_session,
    fetch_l2_gaps, L2GapSelector, L2DryRunner, L2ConstraintPlanner,
    graph_pivot_neighbors, graph_converge_rows, graph_directed_refs_for_candidates,
    node_obj, DryRunInput, L2Gap, _rel_dir, l2_key,
    plan_to_qa_record, _memory_verify, verify_valid,
)

sg_path = Path("outputs/scene-0274_frame14/offline/scene_graphs/scene-0274_frame14_filtered_scene_graph.json")
graph_index = load_graph_index(sg_path)
session = make_neo4j_session()
pool = L2GapSelector(rng=random.Random(0)).shuffled(fetch_l2_gaps(session))

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
    data = DryRunInput(gap, a, b, c,
        converge_rows=_converge_cache.get((gap.a_id, gap.c_id), []),
        pivot_neighbors=_pivot_cache.get(gap.b_id, []),
        available_refs=_refs_cache.get((gap.a_id, gap.c_id), []))
    a_out = graph_index.get("out", {}).get(gap.a_id, {})
    b_out = graph_index.get("out", {}).get(gap.b_id, {})
    c_out = graph_index.get("out", {}).get(gap.c_id, {})
    data.a_to_b_dir = _rel_dir(a_out.get(gap.b_id, {}))
    data.c_to_b_dir = _rel_dir(c_out.get(gap.b_id, {}))
    data.b_to_a_dir = _rel_dir(b_out.get(gap.a_id, {}))
    data.b_to_c_dir = _rel_dir(b_out.get(gap.c_id, {}))
    plans = dry_runner.feasible(data)
    return data, plans

# Re-implement _direct_plan_verify as in run_gap_pipeline_v7
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

def _gi_dist(src, dst):
    rel = _gi_out.get(src, {}).get(dst)
    if not rel: return None
    d = rel.get("distance")
    if d is not None:
        try: return float(d)
        except: pass
    return None

def _direct_plan_verify(data, plan):
    fam = plan.family.value
    a_id, b_id, c_id = data.gap.a_id, data.gap.b_id, data.gap.c_id
    if fam == "viewpoint_transfer": return True
    if fam == "direction_chain":
        return _gi_dir(a_id, b_id) is not None and _gi_dir(b_id, c_id) is not None
    if fam == "distance_chain":
        d_ab, d_bc = _gi_dist(a_id, b_id), _gi_dist(b_id, c_id)
        return d_ab is not None and d_bc is not None and d_ab != d_bc
    if fam == "converge":
        target_type = data.gap.b_type
        dir_from_a = data.a_to_b_dir or ""
        dir_from_c = data.c_to_b_dir or ""
        candidates = set()
        for dst in _gi_out.get(a_id, {}):
            obj = _gi_obj.get(dst, {})
            if obj.get("type") == target_type and _gi_dir(a_id, dst) == dir_from_a:
                candidates.add(dst)
        if not candidates: return False
        candidates = {x for x in candidates if _gi_dir(c_id, x) == dir_from_c}
        if not candidates: return False
        for clause in plan.clauses:
            if clause.kind == "ref_dir" and clause.ref_id and clause.value:
                candidates = {x for x in candidates if _gi_dir(clause.ref_id, x) == clause.value}
                if not candidates: return False
        return len(candidates) == 1 and next(iter(candidates)) == b_id
    if fam == "diverge_compare":
        from gap_pipeline.l2_adapter import _branch_clauses
        a_type, a_dir = data.gap.a_type, data.b_to_a_dir or ""
        a_cands = set()
        for dst in _gi_out.get(b_id, {}):
            obj = _gi_obj.get(dst, {})
            if obj.get("type") == a_type and _gi_dir(b_id, dst) == a_dir:
                a_cands.add(dst)
        if not a_cands: return False
        for clause in _branch_clauses(plan, "a", excluded_ref_id=""):
            if clause.kind == "ref_dir" and clause.ref_id and clause.value:
                a_cands = {x for x in a_cands if _gi_dir(clause.ref_id, x) == clause.value}
                if not a_cands: return False
        if len(a_cands) != 1 or next(iter(a_cands)) != a_id: return False
        c_type, c_dir = data.gap.c_type, data.b_to_c_dir or ""
        c_cands = set()
        for dst in _gi_out.get(b_id, {}):
            obj = _gi_obj.get(dst, {})
            if obj.get("type") == c_type and _gi_dir(b_id, dst) == c_dir:
                c_cands.add(dst)
        if not c_cands: return False
        for clause in _branch_clauses(plan, "c", excluded_ref_id=""):
            if clause.kind == "ref_dir" and clause.ref_id and clause.value:
                c_cands = {x for x in c_cands if _gi_dir(clause.ref_id, x) == clause.value}
                if not c_cands: return False
        if len(c_cands) != 1 or next(iter(c_cands)) != c_id: return False
        return True
    return True

# Compare
print("Building gap plans and comparing verify methods...")
match = 0
mismatch = 0
mismatch_details = []
t_old = 0
t_new = 0

for i, g in enumerate(pool):
    data, plans = build_gap_plans(g)
    for plan in plans:
        # Old method
        t0 = time.perf_counter()
        qa = plan_to_qa_record(data, plan, question_id="0", scene_name="s", frame_idx=0)
        qa = _memory_verify(graph_index, qa)
        old_ok = verify_valid(qa)
        t1 = time.perf_counter()
        t_old += t1 - t0

        # New method
        t2 = time.perf_counter()
        new_ok = _direct_plan_verify(data, plan)
        t3 = time.perf_counter()
        t_new += t3 - t2

        if old_ok == new_ok:
            match += 1
        else:
            mismatch += 1
            if len(mismatch_details) < 10:
                mismatch_details.append({
                    "gap": f"{data.gap.a_id}|{data.gap.b_id}|{data.gap.c_id}",
                    "family": plan.family.value,
                    "old": old_ok,
                    "new": new_ok,
                })
    if (i+1) % 5000 == 0:
        print(f"  processed {i+1}/{len(pool)} gaps, match={match} mismatch={mismatch}")

print(f"\n=== VERIFICATION EQUIVALENCE ===")
print(f"Total plans: {match + mismatch}")
print(f"Match: {match}")
print(f"Mismatch: {mismatch}")
print(f"Old time: {t_old:.1f}s ({t_old/(match+mismatch)*1000:.3f}ms/plan)")
print(f"New time: {t_new:.1f}s ({t_new/(match+mismatch)*1000:.3f}ms/plan)")
print(f"Speedup: {t_old/t_new:.1f}x" if t_new > 0 else "N/A")
if mismatch_details:
    print(f"\nFirst {len(mismatch_details)} mismatches:")
    for d in mismatch_details:
        print(f"  {d}")
