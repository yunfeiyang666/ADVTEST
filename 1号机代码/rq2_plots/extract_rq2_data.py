#!/usr/bin/env python3
"""Extract RQ2 coverage curve data from all frames.

Reads incremental_coverage.csv from each frame's reports/ directory,
extracts per-question cumulative coverage rates (L0, L1, L2),
initial coverage from summary.json, and saves compressed intermediate data.

Usage:
    python extract_rq2_data.py [--limit N] [--output DIR]
"""
from __future__ import print_function

import argparse
import csv
import json
import os
import sys
import time
import numpy as np

# ── Paths ──────────────────────────────────────────────────────────────
OUTPUTS_ROOT = "/mnt/data4/yunyang/ADVTEST_DATA/outputs"
ALL_FRAMES_CSV = os.path.join(OUTPUTS_ROOT, "all_frames_stats.csv")
DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "extracted")

# Round 1 families (coverage-driven), Round 2 = diversity only
ROUND1_FAMILIES = {"converge", "diverge_compare"}


def read_frame_list():
    """Read the master frame list from all_frames_stats.csv + scan for trivial frames."""
    frames = []
    csv_frames = set()
    with open(ALL_FRAMES_CSV, "r") as f:
        for row in csv.DictReader(f):
            sf = row["scene_frame"]
            csv_frames.add(sf)
            frames.append({
                "scene_frame": sf,
                "filtered_nodes": int(row["filtered_nodes"]),
                "total_l2_gaps": int(row["total_l2_gaps"]),
                "generated_questions": int(row["generated_questions"]),
                "final_coverage_l2": int(row["final_coverage_l2"]),
            })

    # Scan for trivial frames (nodes <= 2) not in the CSV
    n_trivial_added = 0
    for name in sorted(os.listdir(OUTPUTS_ROOT)):
        if not name.startswith("scene-"):
            continue
        if name in csv_frames:
            continue
        frame_dir = os.path.join(OUTPUTS_ROOT, name)
        if not os.path.isdir(frame_dir):
            continue
        # Read filtered_nodes from meta if available
        nodes = 0
        meta = read_meta(frame_dir, name)
        if meta.get("filtered_nodes"):
            nodes = int(meta["filtered_nodes"])
        frames.append({
            "scene_frame": name,
            "filtered_nodes": nodes,
            "total_l2_gaps": 0,
            "generated_questions": 0,
            "final_coverage_l2": 0,
        })
        n_trivial_added += 1

    if n_trivial_added > 0:
        print("Added {} trivial frames (nodes<=2) not in CSV".format(n_trivial_added))

    return frames


def read_initial_coverage(frame_dir):
    """Read initial coverage from summary.json."""
    summary_path = None
    reports_dir = os.path.join(frame_dir, "reports")
    if os.path.isdir(reports_dir):
        for fname in os.listdir(reports_dir):
            if fname.endswith("_summary.json"):
                summary_path = os.path.join(reports_dir, fname)
                break

    init_l0, init_l1, init_l2 = 0, 0, 0
    total_l0, total_l1, total_l2 = 0, 0, 0

    if summary_path and os.path.exists(summary_path):
        try:
            with open(summary_path, "r") as f:
                summary = json.load(f)
            # Get initial coverage
            init_cov = summary.get("universe_stats", {}).get("initial_coverage", {}).get("coverage", {})
            init_l0 = init_cov.get("l0", 0)
            init_l1 = init_cov.get("l1", 0)
            init_l2 = init_cov.get("l2", 0)
            # Get totals from neo4j stats
            neo4j = summary.get("universe_stats", {}).get("neo4j", {})
            total_l0 = neo4j.get("object_count", 0)
            total_l1 = neo4j.get("relationship_count", 0)
            total_l2 = summary.get("total_gap_count", 0)
        except Exception as e:
            print("  WARNING: Failed to read summary.json: {}".format(e))

    return {
        "init_l0": init_l0, "init_l1": init_l1, "init_l2": init_l2,
        "total_l0": total_l0, "total_l1": total_l1, "total_l2": total_l2,
    }


def read_meta(frame_dir, scene_frame):
    """Read meta CSV for total counts."""
    qa_dir = os.path.join(frame_dir, "generation", "qa")
    meta_path = os.path.join(qa_dir, "{}_generated_meta.csv".format(scene_frame))
    result = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    result[row["key"]] = row["value"]
        except Exception:
            pass
    return result


def read_incremental_coverage(frame_dir, scene_frame, round1_only=False, total_l0=1, total_l1=1, total_l2=1):
    """Read incremental coverage CSV and return arrays of coverage rates.

    If round1_only=True, filter to only Round 1 families (converge, diverge_compare)
    and recompute cumulative coverage from the filtered deltas.
    """
    reports_dir = os.path.join(frame_dir, "reports")
    csv_path = os.path.join(reports_dir, "{}_incremental_coverage.csv".format(scene_frame))

    if not os.path.exists(csv_path):
        return None

    rows_raw = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                rows_raw.append(row)
    except Exception as e:
        print("  WARNING: Failed to read {}: {}".format(csv_path, e))
        return None

    if round1_only:
        # Split into Round 1 and Round 2 questions
        r1_rows = [r for r in rows_raw if r["l2_family"] in ROUND1_FAMILIES]
        r2_rows = [r for r in rows_raw if r["l2_family"] not in ROUND1_FAMILIES]

        # Start with all R1 questions
        selected = list(r1_rows)
        # Then append R2 questions that have delta_l2 > 0 (fill remaining L2 gaps)
        # Since R2 always comes AFTER R1 in order, their deltas are correct
        for r in r2_rows:
            if int(float(r["delta_l2"])) > 0:
                selected.append(r)
        rows_raw = selected

    if not rows_raw:
        return {"n_questions": 0,
                "rate_l0": np.array([], dtype=np.float32),
                "rate_l1": np.array([], dtype=np.float32),
                "rate_l2": np.array([], dtype=np.float32)}

    if round1_only:
        # Recompute cumulative coverage from the selected questions' deltas
        cum_l0, cum_l1, cum_l2 = 0, 0, 0
        rate_l0, rate_l1, rate_l2 = [], [], []
        for r in rows_raw:
            cum_l0 += int(float(r["delta_l0"]))
            cum_l1 += int(float(r["delta_l1"]))
            cum_l2 += int(float(r["delta_l2"]))
            rate_l0.append(cum_l0 / total_l0 if total_l0 > 0 else 1.0)
            rate_l1.append(cum_l1 / total_l1 if total_l1 > 0 else 1.0)
            rate_l2.append(cum_l2 / total_l2 if total_l2 > 0 else 1.0)
    else:
        rate_l0 = [float(r["coverage_rate_l0"]) for r in rows_raw]
        rate_l1 = [float(r["coverage_rate_l1"]) for r in rows_raw]
        rate_l2 = [float(r["coverage_rate_l2"]) for r in rows_raw]

    return {
        "n_questions": len(rows_raw),
        "rate_l0": np.array(rate_l0, dtype=np.float32),
        "rate_l1": np.array(rate_l1, dtype=np.float32),
        "rate_l2": np.array(rate_l2, dtype=np.float32),
    }


def extract_all(limit=None, output_dir=None, round1_only=False):
    """Main extraction: read all frames, save compressed data."""
    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    if round1_only:
        print("*** ROUND 1 ONLY MODE: filtering to {} ***".format(ROUND1_FAMILIES))
    os.makedirs(output_dir, exist_ok=True)

    print("Reading frame list from {}".format(ALL_FRAMES_CSV))
    frames = read_frame_list()
    total_frames = len(frames)
    print("Total frames in CSV: {}".format(total_frames))

    if limit:
        frames = frames[:limit]
        print("Limited to first {} frames".format(limit))

    # Storage for per-frame data
    all_data = []
    n_success = 0
    n_trivial = 0  # nodes < 3, treated as 100% L2
    n_skip = 0
    max_questions = 0
    t_start = time.time()

    for i, frame_info in enumerate(frames):
        sf = frame_info["scene_frame"]
        nodes = frame_info["filtered_nodes"]
        frame_dir = os.path.join(OUTPUTS_ROOT, sf)

        if (i + 1) % 100 == 0 or i == 0:
            elapsed = time.time() - t_start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(frames) - i - 1) / rate if rate > 0 else 0
            print("[{}/{}] Processing {} ({:.1f} frames/s, ETA {:.0f}s)".format(
                i + 1, len(frames), sf, rate, eta))

        # Handle trivial frames (nodes < 3): no QA generated, L2 = 100%
        if nodes < 3:
            all_data.append({
                "scene_frame": sf,
                "filtered_nodes": nodes,
                "n_questions": 0,
                "is_trivial": True,
                "init_rate_l0": 1.0,
                "init_rate_l1": 1.0,
                "init_rate_l2": 1.0,
                "rate_l0": np.array([], dtype=np.float32),
                "rate_l1": np.array([], dtype=np.float32),
                "rate_l2": np.array([], dtype=np.float32),
            })
            n_trivial += 1
            continue

        if not os.path.isdir(frame_dir):
            print("  SKIP: {} not found".format(frame_dir))
            n_skip += 1
            continue

        # Read initial coverage
        init_data = read_initial_coverage(frame_dir)

        # Compute initial coverage RATES
        total_l0 = init_data["total_l0"] or nodes  # fallback
        # L1: relationship_count is directed (A->B, B->A both counted)
        # but pipeline uses undirected count (relationship_count / 2) as denominator
        total_l1_raw = init_data["total_l1"] or 1
        total_l1 = total_l1_raw // 2 if total_l1_raw > 1 else 1
        total_l2 = init_data["total_l2"] or frame_info["total_l2_gaps"] or 1
        init_rate_l0 = init_data["init_l0"] / total_l0 if total_l0 > 0 else 0.0
        init_rate_l1 = init_data["init_l1"] / total_l1 if total_l1 > 0 else 0.0
        init_rate_l2 = init_data["init_l2"] / total_l2 if total_l2 > 0 else 0.0

        # Read incremental coverage
        inc_data = read_incremental_coverage(frame_dir, sf, round1_only=round1_only,
                                             total_l0=total_l0, total_l1=total_l1, total_l2=total_l2)
        if inc_data is None:
            print("  SKIP: no incremental coverage for {}".format(sf))
            n_skip += 1
            continue
        if inc_data["n_questions"] == 0 and not round1_only:
            print("  SKIP: empty incremental coverage for {}".format(sf))
            n_skip += 1
            continue

        max_questions = max(max_questions, inc_data["n_questions"])

        all_data.append({
            "scene_frame": sf,
            "filtered_nodes": nodes,
            "n_questions": inc_data["n_questions"],
            "is_trivial": False,
            "init_rate_l0": init_rate_l0,
            "init_rate_l1": init_rate_l1,
            "init_rate_l2": init_rate_l2,
            "rate_l0": inc_data["rate_l0"],
            "rate_l1": inc_data["rate_l1"],
            "rate_l2": inc_data["rate_l2"],
        })
        n_success += 1

    elapsed = time.time() - t_start
    print("\n=== Extraction Summary ===")
    print("Processed: {} frames in {:.1f}s".format(len(frames), elapsed))
    print("Success: {}, Trivial (nodes<3): {}, Skipped: {}".format(n_success, n_trivial, n_skip))
    print("Max questions per frame: {}".format(max_questions))

    # ── Save data ──
    # Save metadata as JSON
    meta = {
        "total_frames": len(all_data),
        "n_success": n_success,
        "n_trivial": n_trivial,
        "n_skip": n_skip,
        "max_questions": max_questions,
        "extraction_time_s": elapsed,
    }
    meta_path = os.path.join(output_dir, "rq2_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print("Saved metadata to {}".format(meta_path))

    # Save per-frame summary as CSV (small file)
    summary_path = os.path.join(output_dir, "rq2_frame_summary.csv")
    with open(summary_path, "w") as f:
        writer = csv.writer(f)
        writer.writerow(["scene_frame", "filtered_nodes", "n_questions", "is_trivial",
                         "init_rate_l0", "init_rate_l1", "init_rate_l2",
                         "final_rate_l0", "final_rate_l1", "final_rate_l2"])
        for d in all_data:
            final_l0 = float(d["rate_l0"][-1]) if len(d["rate_l0"]) > 0 else d["init_rate_l0"]
            final_l1 = float(d["rate_l1"][-1]) if len(d["rate_l1"]) > 0 else d["init_rate_l1"]
            final_l2 = float(d["rate_l2"][-1]) if len(d["rate_l2"]) > 0 else d["init_rate_l2"]
            writer.writerow([
                d["scene_frame"], d["filtered_nodes"], d["n_questions"], d["is_trivial"],
                d["init_rate_l0"], d["init_rate_l1"], d["init_rate_l2"],
                final_l0, final_l1, final_l2,
            ])
    print("Saved frame summary to {}".format(summary_path))

    # Save coverage curves as numpy arrays
    # For each frame: pad to max_questions with final value, then stack
    # This allows vectorized averaging later

    # We need to create padded arrays: shape (n_frames, max_questions+1)
    # Index 0 = initial coverage, indices 1..max_questions = after each question
    n_frames = len(all_data)
    pad_len = max_questions + 1  # +1 for initial coverage at index 0

    curves_l0 = np.zeros((n_frames, pad_len), dtype=np.float32)
    curves_l1 = np.zeros((n_frames, pad_len), dtype=np.float32)
    curves_l2 = np.zeros((n_frames, pad_len), dtype=np.float32)
    n_questions_arr = np.zeros(n_frames, dtype=np.int32)

    for idx, d in enumerate(all_data):
        nq = d["n_questions"]
        n_questions_arr[idx] = nq

        init_l0 = d["init_rate_l0"]
        init_l1 = d["init_rate_l1"]
        init_l2 = d["init_rate_l2"]

        # Index 0 = initial coverage
        curves_l0[idx, 0] = init_l0
        curves_l1[idx, 0] = init_l1
        curves_l2[idx, 0] = init_l2

        if nq > 0:
            # Fill in the actual curve
            curves_l0[idx, 1:nq + 1] = d["rate_l0"]
            curves_l1[idx, 1:nq + 1] = d["rate_l1"]
            curves_l2[idx, 1:nq + 1] = d["rate_l2"]

            # Pad with final value
            if nq < max_questions:
                curves_l0[idx, nq + 1:] = d["rate_l0"][-1]
                curves_l1[idx, nq + 1:] = d["rate_l1"][-1]
                curves_l2[idx, nq + 1:] = d["rate_l2"][-1]
        else:
            # Trivial frame: all positions = initial (100%)
            curves_l0[idx, :] = init_l0
            curves_l1[idx, :] = init_l1
            curves_l2[idx, :] = init_l2

    npz_path = os.path.join(output_dir, "rq2_curves.npz")
    np.savez_compressed(npz_path,
                        curves_l0=curves_l0,
                        curves_l1=curves_l1,
                        curves_l2=curves_l2,
                        n_questions=n_questions_arr)
    file_size_mb = os.path.getsize(npz_path) / 1024 / 1024
    print("Saved coverage curves to {} ({:.1f} MB)".format(npz_path, file_size_mb))
    print("Shape: ({}, {})".format(n_frames, pad_len))

    return all_data, meta


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract RQ2 coverage data")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to first N frames (for testing)")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT_DIR,
                        help="Output directory")
    parser.add_argument("--round1-only", action="store_true",
                        help="Only include Round 1 questions (converge, diverge_compare)")
    args = parser.parse_args()
    extract_all(limit=args.limit, output_dir=args.output, round1_only=args.round1_only)
