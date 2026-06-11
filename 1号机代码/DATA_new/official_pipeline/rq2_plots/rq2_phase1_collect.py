"""Phase 1: Read all CSVs and JSONLs from HDD.

Collects per-frame data for D2-D16.
Saves to rq2_frame_cache.pkl for reuse by plotting phase.
"""
import csv, json, os, sys, time, pickle
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from rq2_analysis_config import *

sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)


def read_scene_graph_ego(frame_dir: Path, sf: str):
    """Return set of node IDs that are ego vehicle."""
    sg_path = frame_dir / "offline" / "scene_graphs" / f"{sf}_filtered_scene_graph.json"
    if not sg_path.exists():
        return set()
    try:
        g = json.loads(sg_path.read_text())
        objs = g.get("objects") or g.get("nodes") or []
        ego_ids = set()
        for o in objs:
            uid = str(o.get("id") or o.get("unique_id") or "")
            label = str(o.get("label") or o.get("category") or o.get("type") or "")
            if uid == "ego" or "ego" in uid.lower() or label == "ego":
                ego_ids.add(uid)
        return ego_ids
    except Exception:
        return set()


def read_frame_jsonl(jsonl_path: Path):
    """Yield parsed records from a JSONL file."""
    if not jsonl_path.exists():
        return
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except Exception:
                    pass


def process_frame(row, frame_dir: Path, sf: str, ego_ids: set):
    """Process one frame: read CSV + JSONL, return frame dict."""
    nodes = int(row["filtered_nodes"])
    total_gaps = int(row["total_l2_gaps"])
    scene_name = sf.rsplit("_frame", 1)[0]

    # ── Read incremental_coverage.csv ─────────────────────────────────
    csv_path = frame_dir / "reports" / f"{sf}_incremental_coverage.csv"
    if not csv_path.exists():
        return None

    families = Counter()
    delta_l2_total = delta_l1_total = delta_l0_total = 0
    raw_l2_total = 0
    coverage_points = []      # L2 coverage rate per question
    per_q_delta_l2 = []
    r1_end_cov_l2 = 0.0
    r1_count = r2_count = 0
    r1_ended = False
    timing_ms_per_q = []

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        for qrow in csv.DictReader(f):
            fam = qrow.get("l2_family", "")
            dl2 = int(float(qrow.get("delta_l2", 0)))
            dl1 = int(float(qrow.get("delta_l1", 0)))
            dl0 = int(float(qrow.get("delta_l0", 0)))
            rl2 = int(float(qrow.get("raw_l2", 0)))
            cov_l2 = float(qrow.get("coverage_rate_l2", 0))
            elapsed = float(qrow.get("generation_elapsed_ms", 0))

            families[fam] += 1
            delta_l2_total += dl2
            delta_l1_total += dl1
            delta_l0_total += dl0
            raw_l2_total += rl2
            coverage_points.append(cov_l2)
            per_q_delta_l2.append(dl2)
            timing_ms_per_q.append(elapsed)

            is_r1 = fam in ROUND1_FAMILIES
            if is_r1 and not r1_ended:
                r1_count += 1
                r1_end_cov_l2 = cov_l2
            else:
                if not r1_ended and not is_r1:
                    r1_ended = True
                r2_count += 1

    q_count = r1_count + r2_count

    # ��─ Read summary.json for phase timing ────────────────────────────
    pipeline_timing = {}
    for fname in (frame_dir / "reports").iterdir():
        if fname.name.endswith("_summary.json"):
            try:
                s = json.loads(fname.read_text())
                pipeline_timing = s.get("pipeline_timing", {})
            except Exception:
                pass
            break

    # ── Read R1 JSONL for D10/D13/D14 ─────────────────────────────────
    answer_types = Counter()
    constraint_counts = []
    constraint_types_counter = Counter()
    cand_before_list = []
    cand_after_list = []
    # Ego-related gap detection via path_pattern
    ego_gap_count = 0
    total_gap_from_jsonl = 0

    r1_path = frame_dir / "generation" / "qa" / f"{sf}_round1.jsonl"
    for rec in read_frame_jsonl(r1_path):
        at = rec.get("answer_type", "")
        answer_types[at] += 1
        cc = rec.get("constraint_count", 0)
        if cc:
            constraint_counts.append(int(cc))
        for ct in (rec.get("constraint_types") or []):
            constraint_types_counter[str(ct)] += 1
        cb = rec.get("candidate_before", 0)
        ca = rec.get("candidate_after", 0)
        if cb and ca is not None:
            cand_before_list.append(int(cb))
            cand_after_list.append(int(ca))
        # Ego gap: any node in footprint is ego
        pp = rec.get("path_pattern", "")
        nodes_in_gap = pp.split("|")
        total_gap_from_jsonl += 1
        if any(n in ego_ids for n in nodes_in_gap):
            ego_gap_count += 1

    # R2 JSONL — answer_type only (constraint fields are 0 in R2)
    r2_path = frame_dir / "generation" / "qa" / f"{sf}_round2.jsonl"
    for rec in read_frame_jsonl(r2_path):
        at = rec.get("answer_type", "")
        answer_types[at] += 1
        # Ego gap
        pp = rec.get("path_pattern", "")
        nodes_in_gap = pp.split("|")
        total_gap_from_jsonl += 1
        if any(n in ego_ids for n in nodes_in_gap):
            ego_gap_count += 1

    # ── Cross-frame gap set (D15): R1 path patterns ───────────────────
    gap_patterns = set()
    for rec in read_frame_jsonl(r1_path):
        pp = rec.get("path_pattern", "")
        if pp:
            gap_patterns.add(pp)

    return {
        "sf": sf,
        "scene_name": scene_name,
        "nodes": nodes,
        "total_gaps": total_gaps,
        "q_count": q_count,
        "r1_count": r1_count,
        "r2_count": r2_count,
        "families": dict(families),
        "delta_l2_total": delta_l2_total,
        "delta_l1_total": delta_l1_total,
        "delta_l0_total": delta_l0_total,
        "raw_l2_total": raw_l2_total,
        "coverage_points": coverage_points,
        "per_q_delta_l2": per_q_delta_l2,
        "timing_ms_per_q": timing_ms_per_q,
        "r1_end_cov_l2": r1_end_cov_l2,
        "pipeline_timing": pipeline_timing,
        "answer_types": dict(answer_types),
        "constraint_counts": constraint_counts,
        "constraint_types": dict(constraint_types_counter),
        "cand_before_list": cand_before_list,
        "cand_after_list": cand_after_list,
        "ego_gap_count": ego_gap_count,
        "total_gap_from_jsonl": total_gap_from_jsonl,
        "ego_ids": list(ego_ids),
        "gap_patterns": gap_patterns,   # for D15
    }


def main():
    print("=== Phase 1: HDD data collection ===")
    t0 = time.time()

    frames_meta = []
    with open(ALL_FRAMES_CSV) as f:
        for row in csv.DictReader(f):
            frames_meta.append(row)
    print(f"Frames to process: {len(frames_meta)}")

    cache_path = PLOTS_DIR / "rq2_frame_cache.pkl"
    frame_data = []
    errors = 0

    for i, row in enumerate(frames_meta):
        sf = row["scene_frame"]
        frame_dir = Path(OUTPUTS_ROOT) / sf
        ego_ids = read_scene_graph_ego(frame_dir, sf)
        try:
            fd = process_frame(row, frame_dir, sf, ego_ids)
            if fd is not None:
                frame_data.append(fd)
        except Exception as e:
            errors += 1
            if errors <= 10:
                import traceback
                print(f"  ERROR {sf}: {e}")
                traceback.print_exc()

        if (i + 1) % 200 == 0:
            elapsed = time.time() - t0
            fps = (i + 1) / elapsed
            eta = (len(frames_meta) - i - 1) / fps
            print(f"  [{i+1}/{len(frames_meta)}] {fps:.1f} f/s, ETA {eta/60:.1f}min, errors={errors}")

    elapsed = time.time() - t0
    print(f"\nProcessed {len(frame_data)} frames in {elapsed/60:.1f}min, errors={errors}")

    # Save cache
    print(f"Saving cache to {cache_path}...")
    with open(cache_path, "wb") as f:
        pickle.dump(frame_data, f)
    print(f"Cache saved: {cache_path.stat().st_size / 1e6:.1f} MB")
    print("Phase 1 DONE")


if __name__ == "__main__":
    main()
