"""
RQ2 Data Analysis - Step 1: Pre-aggregate frame-level statistics.

Reads all 6011 frames' summary.json and incremental_coverage.csv to build
a compact frame_stats DataFrame cached as parquet for downstream analysis.
"""
import os
import json
import csv
import time
import pandas as pd
import numpy as np
from pathlib import Path

OUTPUTS = Path(r"E:\Project\ADVTEST\1号机代码\DATA_new\outputs")
ANALYSIS = Path(r"E:\Project\ADVTEST\1号机代码\DATA_new\analysis")
CACHE = ANALYSIS / "data_cache"
CACHE.mkdir(parents=True, exist_ok=True)


def load_frame_stats():
    """Load or compute frame-level statistics."""
    cache_path = CACHE / "frame_stats.csv"
    if cache_path.exists():
        print(f"[cache] Loading from {cache_path}")
        return pd.read_csv(cache_path)

    print("[step1] Scanning all frames...")
    t0 = time.time()
    rows = []

    for i, frame_dir in enumerate(sorted(OUTPUTS.iterdir())):
        if not frame_dir.is_dir():
            continue
        frame_name = frame_dir.name
        parts = frame_name.rsplit("_frame", 1)
        if len(parts) != 2:
            continue
        scene_id = parts[0]
        frame_id = int(parts[1])

        # --- summary.json ---
        reports_dir = frame_dir / "reports"
        summary_path = reports_dir / f"{frame_name}_summary.json"
        if not summary_path.exists():
            continue

        with open(summary_path, encoding="utf-8") as f:
            s = json.load(f)

        cov = s.get("coverage", {})
        fam = s.get("families", {})
        pt = s.get("pipeline_timing", {})
        us = s.get("universe_stats", {})

        n_objects = cov.get("l0", 0)
        n_l1 = cov.get("l1", 0)
        n_l2 = cov.get("l2", 0)
        pool_size = s.get("pool_size", 0)
        generated = s.get("generated", 0)

        # Determine size group
        if n_objects <= 15:
            size_group = "S"
        elif n_objects <= 30:
            size_group = "M"
        else:
            size_group = "L"

        # Family counts
        converge = fam.get("converge", 0)
        diverge = fam.get("diverge_compare", 0)
        dir_chain = fam.get("direction_chain", 0)
        dist_chain = fam.get("distance_chain", 0)
        viewpoint = fam.get("viewpoint_transfer", 0)

        # Timing
        precompute_ms = pt.get("precompute_ms", 0)
        plan_cache_ms = pt.get("plan_cache_ms", 0)
        selection_gen_ms = pt.get("selection_gen_ms", 0)
        total_ms = precompute_ms + plan_cache_ms + selection_gen_ms

        # Phase split: formal_selected = Phase 1, coverage_backfill = Phase 2
        phase1_count = us.get("formal_selected_count", 0)
        phase2_count = us.get("coverage_backfill_count", 0)

        # --- Initial coverage from offline/initial_coverage CSV ---
        init_l0 = init_l1 = init_l2 = 0
        ic_csv = frame_dir / "offline" / "initial_coverage" / f"{frame_name}_initial_coverage.csv"
        if ic_csv.exists():
            with open(ic_csv, encoding="utf-8") as icf:
                for icrow in csv.DictReader(icf):
                    init_l0 += int(icrow.get("delta_l0", 0))
                    init_l1 += int(icrow.get("delta_l1", 0))
                    init_l2 += int(icrow.get("delta_l2", 0))

        rows.append({
            "frame_name": frame_name,
            "scene_id": scene_id,
            "frame_id": frame_id,
            "n_objects": n_objects,
            "n_l1": n_l1,
            "n_l2": n_l2,
            "pool_size": pool_size,
            "generated": generated,
            "size_group": size_group,
            "converge": converge,
            "diverge_compare": diverge,
            "direction_chain": dir_chain,
            "distance_chain": dist_chain,
            "viewpoint_transfer": viewpoint,
            "phase1_count": phase1_count,
            "phase2_count": phase2_count,
            "precompute_ms": precompute_ms,
            "plan_cache_ms": plan_cache_ms,
            "selection_gen_ms": selection_gen_ms,
            "total_ms": total_ms,
            "init_l0": init_l0,
            "init_l1": init_l1,
            "init_l2": init_l2,
            "init_rate_l0": init_l0 / n_objects if n_objects > 0 else 1.0,
            "init_rate_l1": init_l1 / n_l1 if n_l1 > 0 else 1.0,
            "init_rate_l2": init_l2 / n_l2 if n_l2 > 0 else 1.0,
        })

        if (i + 1) % 1000 == 0:
            print(f"  [{i+1}] processed...", flush=True)

    df = pd.DataFrame(rows)
    elapsed = time.time() - t0
    print(f"[step1] Done: {len(df)} frames in {elapsed:.1f}s")
    print(f"  Size groups: {df['size_group'].value_counts().to_dict()}")
    print(f"  Total generated: {df['generated'].sum():,}")
    print(f"  Pool sizes: min={df['pool_size'].min()}, max={df['pool_size'].max()}, median={df['pool_size'].median():.0f}")

    df.to_csv(cache_path, index=False)
    print(f"[cache] Saved to {cache_path}")
    return df


def load_coverage_curves(df, sample_per_group=None):
    """
    Load incremental coverage curves from CSV files.
    Returns dict: size_group -> list of (coverage_rate_l0[], coverage_rate_l1[], coverage_rate_l2[])
    """
    print("[step1] Loading coverage curves...")
    t0 = time.time()
    curves = {"S": [], "M": [], "L": []}

    # Filter to non-empty frames
    valid = df[df["generated"] > 0].copy()

    for group in ["S", "M", "L"]:
        group_frames = valid[valid["size_group"] == group]
        if sample_per_group and len(group_frames) > sample_per_group:
            group_frames = group_frames.sample(sample_per_group, random_state=42)

        for _, row in group_frames.iterrows():
            csv_path = OUTPUTS / row["frame_name"] / "reports" / f"{row['frame_name']}_incremental_coverage.csv"
            if not csv_path.exists():
                continue
            try:
                cdf = pd.read_csv(csv_path, usecols=[
                    "order_index", "coverage_rate_l0", "coverage_rate_l1", "coverage_rate_l2",
                    "delta_l0", "delta_l1", "delta_l2", "l2_family", "selection_phase"
                ])
                curves[group].append({
                    "frame_name": row["frame_name"],
                    "n_objects": row["n_objects"],
                    "pool_size": row["pool_size"],
                    "generated": row["generated"],
                    "data": cdf,
                })
            except Exception as e:
                pass

        print(f"  Group {group}: {len(curves[group])} frames loaded")

    elapsed = time.time() - t0
    print(f"[step1] Coverage curves loaded in {elapsed:.1f}s")
    return curves


if __name__ == "__main__":
    df = load_frame_stats()
    print("\n=== Frame Stats Summary ===")
    print(df.describe())
    print(f"\nSize group distribution:")
    print(df.groupby("size_group").agg(
        count=("frame_name", "count"),
        avg_objects=("n_objects", "mean"),
        avg_pool=("pool_size", "mean"),
        avg_generated=("generated", "mean"),
        total_generated=("generated", "sum"),
    ).round(1))
