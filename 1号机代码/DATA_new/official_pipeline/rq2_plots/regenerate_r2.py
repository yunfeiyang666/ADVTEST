#!/usr/bin/env python3
"""Regenerate Round 2 ONLY for all frames.

Keeps R1 records untouched. Re-generates R2 with fixed _gi_dist (metrics.distance fallback).
This is very fast since R2 is pure programmatic generation, no constraint planning.
"""
import csv, json, os, sys, time, traceback
from pathlib import Path
from collections import defaultdict

# Add pipeline code to path
CODE_DIR = Path(__file__).resolve().parent.parent / "code"
sys.path.insert(0, str(CODE_DIR))
sys.path.insert(0, str(CODE_DIR / "gap_pipeline"))

from gap_pipeline.l2_question_realizer import (
    direction_chain_question, distance_chain_question, viewpoint_transfer_question,
)
from gap_pipeline.l2_question_graph import chain_graph
from gap_pipeline.l2_geometry import point_from_obj, viewpoint_left_right

OUTPUTS_ROOT = Path("/mnt/data4/yunyang/ADVTEST_DATA/outputs")
ALL_FRAMES_CSV = OUTPUTS_ROOT / "all_frames_stats.csv"


def load_graph_index(path: Path):
    """Load filtered_scene_graph into graph_index format."""
    if not path.exists():
        return {"objects": {}, "out": {}}
    graph = json.loads(path.read_text(encoding="utf-8"))
    objs = graph.get("objects") or graph.get("nodes") or []
    rels = graph.get("relationships") or graph.get("edges") or []
    objects = {str(o.get("id") or o.get("unique_id")): o for o in objs}
    out = {}
    for rel in rels:
        src = str(rel.get("src") or rel.get("source") or rel.get("from"))
        dst = str(rel.get("dst") or rel.get("target") or rel.get("to"))
        if not src or not dst or src == "None" or dst == "None":
            continue
        out.setdefault(src, {})[dst] = rel
    return {"objects": objects, "out": out}


def gi_dir(gi_out, src, dst):
    """Get direction from graph_index."""
    rel = gi_out.get(src, {}).get(dst)
    if not rel:
        return None
    d = rel.get("direction_6") or rel.get("direction_official")
    if d:
        return str(d)
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
        except (ValueError, TypeError):
            pass
    # Check metrics
    metrics = rel.get("metrics")
    if isinstance(metrics, dict):
        for key in ("direction_6", "direction_source", "direction_ego"):
            val = metrics.get(key)
            if isinstance(val, dict):
                d6 = val.get("direction_6")
                if d6:
                    return str(d6)
            elif val:
                return str(val)
    return None


def gi_dist(gi_out, src, dst):
    """Get distance from graph_index (FIXED: includes metrics.distance)."""
    rel = gi_out.get(src, {}).get(dst)
    if not rel:
        return None
    d = rel.get("distance")
    if d is not None:
        try: return float(d)
        except (ValueError, TypeError): pass
    # Fallback: metrics.distance
    metrics = rel.get("metrics")
    if isinstance(metrics, dict) and metrics.get("distance") is not None:
        try: return float(metrics["distance"])
        except (ValueError, TypeError): pass
    return None


def utc_now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def regenerate_r2_for_frame(sf: str):
    """Regenerate R2 for a single frame. Returns stats dict or None on error."""
    frame_dir = OUTPUTS_ROOT / sf
    sg_path = frame_dir / "offline" / "scene_graphs" / f"{sf}_filtered_scene_graph.json"
    r1_jsonl = frame_dir / "generation" / "qa" / f"{sf}_round1.jsonl"
    r2_jsonl = frame_dir / "generation" / "qa" / f"{sf}_round2.jsonl"
    all_jsonl = frame_dir / "generation" / "qa" / f"{sf}_all.jsonl"
    inc_csv = frame_dir / "reports" / f"{sf}_incremental_coverage.csv"

    if not sg_path.exists() or not r1_jsonl.exists():
        return None

    # Load graph_index
    gi = load_graph_index(sg_path)
    gi_out = gi["out"]
    gi_obj = gi["objects"]

    # Load R1 records
    r1_records = []
    with open(r1_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r1_records.append(json.loads(line))

    if not r1_records:
        return None

    scene_id = r1_records[0].get("scene_name", sf)
    frame_idx = r1_records[0].get("frame_idx")

    # Extract gap pool from R1 records' coverage_footprint L2 keys
    # Each R1 record covers L2 gaps, and R2 generates for ALL gaps in the pool.
    # We need to reconstruct the full gap pool.
    # The gap pool = all (A,B,C) triples from the scene graph.
    # A gap exists when edges A->B and B->C exist.
    all_node_ids = list(gi_obj.keys())
    pool = []
    for b_id in all_node_ids:
        b_neighbors = gi_out.get(b_id, {})
        # Find all pairs (a, c) where a->b and b->c edges exist
        # Actually, gaps are A->B->C where edges A->B and B->C exist
        # But we need incoming edges to B as well
        pass

    # Simpler: extract ALL gaps from existing R2 JSONL (which iterated over the original pool)
    # Plus: enumerate from scene graph edges
    # The pool is: for each pair of edges (X->B) and (B->Y) where X != Y, gap = (X, B, Y)
    # But the original code uses a different pool enumeration. Let's just read old R2 path_patterns.

    old_r2_records = []
    old_r2_gaps = []
    if r2_jsonl.exists():
        with open(r2_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    old_r2_records.append(rec)
                    pp = rec.get("path_pattern", "")
                    parts = pp.split("|")
                    if len(parts) == 3:
                        old_r2_gaps.append(tuple(parts))

    # Also get gaps from R1 path_patterns (R1 covers gaps that R2 might miss)
    r1_gaps = set()
    for rec in r1_records:
        pp = rec.get("path_pattern", "")
        parts = pp.split("|")
        if len(parts) == 3:
            r1_gaps.add(tuple(parts))

    # Build the full gap pool from scene graph:
    # gap = (a_id, b_id, c_id) where edges a->b and b->c exist, a != c
    # This is the actual pool enumeration used by the pipeline
    incoming = defaultdict(set)  # b_id -> set of a_ids that have edge to b
    for src in gi_out:
        for dst in gi_out[src]:
            incoming[dst].add(src)

    full_pool = []
    seen = set()
    for b_id in all_node_ids:
        in_nodes = incoming.get(b_id, set())
        out_nodes = set(gi_out.get(b_id, {}).keys())
        for a_id in in_nodes:
            for c_id in out_nodes:
                if a_id != c_id and a_id != b_id and c_id != b_id:
                    # Check: need edge a->b (already guaranteed by incoming)
                    # and edge b->c (already guaranteed by out_nodes)
                    key = (a_id, b_id, c_id)
                    if key not in seen:
                        seen.add(key)
                        full_pool.append(key)

    # If we couldn't build pool from graph, fallback to old R2 gaps
    if not full_pool:
        full_pool = old_r2_gaps if old_r2_gaps else list(r1_gaps)

    # Generate R2 records
    r2_new = []
    r2_counter = 0
    r2_generated = 0
    r2_skipped = 0
    r2_stats = {"direction_chain": 0, "distance_chain": 0, "viewpoint_transfer": 0}

    for a_id, b_id, c_id in full_pool:
        qa = None
        gap_key = f"{a_id}|{b_id}|{c_id}"

        for attempt in range(3):
            pick = (r2_counter + attempt) % 3
            if pick == 0:
                # direction_chain
                dir_ab = gi_dir(gi_out, a_id, b_id)
                dir_bc = gi_dir(gi_out, b_id, c_id)
                if dir_ab is not None and dir_bc is not None:
                    q = direction_chain_question(a_id, b_id, c_id)
                    fp = chain_graph(a_id, b_id, c_id, family="direction_chain").footprint().as_dict()
                    qa = {
                        "question_id": "0", "scene_name": scene_id, "frame_idx": frame_idx,
                        "topology_level": "L2", "template_id": "direction_chain",
                        "constraint_trace": [], "constraint_count": 0, "constraint_types": [],
                        "candidate_before": 0, "candidate_after": 0, "unique_check": True,
                        "generation_backend": "programmatic", "llm_model": "",
                        "raw_llm_output": {}, "token_prompt": 0, "token_completion": 0,
                        "logic_verification": "IN_MEMORY_VERIFIED", "is_unique": True,
                        "n_interference_siblings": 0,
                        "question": q.question, "answer": (dir_ab == dir_bc),
                        "answer_type": q.answer_type,
                        "path_pattern": gap_key,
                        "footprint_nodes": [a_id, b_id, c_id],
                        "coverage_footprint": fp, "verify_payload": {},
                        "l2_refactor": True, "l2_family": "direction_chain", "l2_score": 1.0,
                        "timestamp_start": utc_now_iso(), "timestamp_end": utc_now_iso(),
                        "generation_elapsed_ms": 0, "plan_attempt_key": f"r2_{gap_key}_dc",
                        "generation_round": 2, "selection_phase": "primary",
                    }
                    r2_stats["direction_chain"] += 1
                    break
            elif pick == 1:
                # distance_chain (FIXED)
                d_ab = gi_dist(gi_out, a_id, b_id)
                d_bc = gi_dist(gi_out, b_id, c_id)
                if d_ab is not None and d_bc is not None and d_ab != d_bc:
                    q = distance_chain_question(a_id, b_id, c_id)
                    fp = chain_graph(a_id, b_id, c_id, family="distance_chain").footprint().as_dict()
                    answer = a_id if d_ab < d_bc else c_id
                    qa = {
                        "question_id": "0", "scene_name": scene_id, "frame_idx": frame_idx,
                        "topology_level": "L2", "template_id": "distance_chain",
                        "constraint_trace": [], "constraint_count": 0, "constraint_types": [],
                        "candidate_before": 0, "candidate_after": 0, "unique_check": True,
                        "generation_backend": "programmatic", "llm_model": "",
                        "raw_llm_output": {}, "token_prompt": 0, "token_completion": 0,
                        "logic_verification": "IN_MEMORY_VERIFIED", "is_unique": True,
                        "n_interference_siblings": 0,
                        "question": q.question, "answer": answer,
                        "answer_type": q.answer_type,
                        "path_pattern": gap_key,
                        "footprint_nodes": [a_id, b_id, c_id],
                        "coverage_footprint": fp, "verify_payload": {},
                        "l2_refactor": True, "l2_family": "distance_chain", "l2_score": 1.0,
                        "timestamp_start": utc_now_iso(), "timestamp_end": utc_now_iso(),
                        "generation_elapsed_ms": 0, "plan_attempt_key": f"r2_{gap_key}_dist",
                        "generation_round": 2, "selection_phase": "primary",
                    }
                    r2_stats["distance_chain"] += 1
                    break
            else:
                # viewpoint_transfer
                a_obj = gi_obj.get(a_id, {})
                b_obj = gi_obj.get(b_id, {})
                c_obj = gi_obj.get(c_id, {})
                pa = point_from_obj(a_obj)
                pb = point_from_obj(b_obj)
                pc = point_from_obj(c_obj)
                if pa is not None and pb is not None and pc is not None:
                    ans = viewpoint_left_right(pa, pb, pc)
                    if ans is not None:
                        q = viewpoint_transfer_question(a_id, b_id, c_id)
                        fp = chain_graph(a_id, b_id, c_id, family="viewpoint_transfer").footprint().as_dict()
                        qa = {
                            "question_id": "0", "scene_name": scene_id, "frame_idx": frame_idx,
                            "topology_level": "L2", "template_id": "viewpoint_transfer",
                            "constraint_trace": [], "constraint_count": 0, "constraint_types": [],
                            "candidate_before": 0, "candidate_after": 0, "unique_check": True,
                            "generation_backend": "programmatic", "llm_model": "",
                            "raw_llm_output": {}, "token_prompt": 0, "token_completion": 0,
                            "logic_verification": "IN_MEMORY_VERIFIED", "is_unique": True,
                            "n_interference_siblings": 0,
                            "question": q.question, "answer": ans,
                            "answer_type": q.answer_type,
                            "path_pattern": gap_key,
                            "footprint_nodes": [a_id, b_id, c_id],
                            "coverage_footprint": fp, "verify_payload": {},
                            "l2_refactor": True, "l2_family": "viewpoint_transfer", "l2_score": 1.0,
                            "timestamp_start": utc_now_iso(), "timestamp_end": utc_now_iso(),
                            "generation_elapsed_ms": 0, "plan_attempt_key": f"r2_{gap_key}_vp",
                            "generation_round": 2, "selection_phase": "primary",
                        }
                        r2_stats["viewpoint_transfer"] += 1
                        break

        r2_counter += 1
        if qa is not None:
            r2_new.append(qa)
            r2_generated += 1
        else:
            r2_skipped += 1

    # Number R2 records
    for i, qa in enumerate(r2_new):
        qa["question_id"] = str(len(r1_records) + i + 1)

    # Write R2 JSONL
    r2_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with open(r2_jsonl, "w", encoding="utf-8") as f:
        for qa in r2_new:
            f.write(json.dumps(qa, ensure_ascii=False) + "\n")

    # Write combined all.jsonl
    all_records = r1_records + r2_new
    with open(all_jsonl, "w", encoding="utf-8") as f:
        for qa in all_records:
            f.write(json.dumps(qa, ensure_ascii=False) + "\n")

    # Recalculate incremental_coverage.csv
    _write_incremental_coverage(all_records, inc_csv, full_pool)

    return {
        "sf": sf,
        "r1_count": len(r1_records),
        "r2_old_count": len(old_r2_records),
        "r2_new_count": len(r2_new),
        "r2_skipped": r2_skipped,
        "pool_size": len(full_pool),
        "stats": r2_stats,
    }


def _write_incremental_coverage(all_records, csv_path, pool):
    """Recalculate and write incremental_coverage.csv."""
    total_l2 = len(pool) if pool else 1
    # Count unique L0, L1 from all footprints
    all_l0 = set()
    all_l1 = set()
    for qa in all_records:
        fp = qa.get("coverage_footprint") or {}
        for x in fp.get("l0", []):
            all_l0.add(str(x))
        for x in fp.get("l1", []):
            all_l1.add(str(x))
    total_l0 = max(len(all_l0), 1)
    total_l1 = max(len(all_l1), 1)

    seen_l0, seen_l1, seen_l2 = set(), set(), set()
    rows = []
    for idx, qa in enumerate(all_records, start=1):
        fp = qa.get("coverage_footprint") or {}
        l0 = {str(x) for x in fp.get("l0", [])}
        l1 = {str(x) for x in fp.get("l1", [])}
        l2 = {str(x) for x in fp.get("l2", [])}
        new_l0 = l0 - seen_l0
        new_l1 = l1 - seen_l1
        new_l2 = l2 - seen_l2
        seen_l0.update(l0)
        seen_l1.update(l1)
        seen_l2.update(l2)
        rows.append({
            "order_index": idx,
            "question_id": qa.get("question_id", str(idx)),
            "selection_phase": qa.get("selection_phase", ""),
            "l2_family": qa.get("l2_family", ""),
            "timestamp_start": qa.get("timestamp_start", ""),
            "timestamp_end": qa.get("timestamp_end", ""),
            "generation_elapsed_ms": qa.get("generation_elapsed_ms", 0),
            "question": qa.get("question", ""),
            "raw_l0": len(l0),
            "raw_l1": len(l1),
            "raw_l2": len(l2),
            "delta_l0": len(new_l0),
            "delta_l1": len(new_l1),
            "delta_l2": len(new_l2),
            "cum_l0": len(seen_l0),
            "cum_l1": len(seen_l1),
            "cum_l2": len(seen_l2),
            "coverage_rate_l0": len(seen_l0) / total_l0,
            "coverage_rate_l1": len(seen_l1) / total_l1,
            "coverage_rate_l2": len(seen_l2) / max(total_l2, 1),
            "new_l0": json.dumps(sorted(new_l0)),
            "new_l1": json.dumps(sorted(new_l1)),
            "new_l2": json.dumps(sorted(new_l2)),
        })

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    import sys
    # Unbuffered output for nohup
    sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)
    
    print("Loading frame list...")
    frame_rows = []
    with open(ALL_FRAMES_CSV) as f:
        for row in csv.DictReader(f):
            frame_rows.append(row)
    print(f"Total frames: {len(frame_rows)}")

    total_r2_old = 0
    total_r2_new = 0
    total_dist_chain = 0
    total_dir_chain = 0
    total_vp = 0
    errors = 0
    t0 = time.time()

    for i, row in enumerate(frame_rows):
        sf = row["scene_frame"]
        try:
            result = regenerate_r2_for_frame(sf)
        except Exception as exc:
            print(f"  [{i+1}/{len(frame_rows)}] ERROR {sf}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            errors += 1
            continue

        if result is None:
            continue

        total_r2_old += result["r2_old_count"]
        total_r2_new += result["r2_new_count"]
        total_dist_chain += result["stats"]["distance_chain"]
        total_dir_chain += result["stats"]["direction_chain"]
        total_vp += result["stats"]["viewpoint_transfer"]

        if (i + 1) % 100 == 0 or (i + 1) <= 5:
            elapsed = time.time() - t0
            fps = (i + 1) / elapsed
            eta = (len(frame_rows) - i - 1) / fps if fps > 0 else 0
            print(
                f"  [{i+1}/{len(frame_rows)}] {fps:.1f} f/s, ETA {eta:.0f}s | "
                f"R2: {result['r2_new_count']} (dir={result['stats']['direction_chain']}, "
                f"dist={result['stats']['distance_chain']}, vp={result['stats']['viewpoint_transfer']}) "
                f"pool={result['pool_size']}"
            )

    elapsed = time.time() - t0
    print(f"\nDONE in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"  R2 old total: {total_r2_old:,}")
    print(f"  R2 new total: {total_r2_new:,}")
    print(f"  - direction_chain: {total_dir_chain:,} ({total_dir_chain/max(total_r2_new,1)*100:.1f}%)")
    print(f"  - distance_chain:  {total_dist_chain:,} ({total_dist_chain/max(total_r2_new,1)*100:.1f}%)")
    print(f"  - viewpoint:       {total_vp:,} ({total_vp/max(total_r2_new,1)*100:.1f}%)")
    print(f"  Errors: {errors}")


if __name__ == "__main__":
    main()
