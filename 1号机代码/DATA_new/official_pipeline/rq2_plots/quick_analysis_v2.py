#!/usr/bin/env python3
"""Quick comprehensive analysis of RQ2 data after R2 regeneration.

Reads incremental_coverage.csv from all frames, computes:
- Table 4: Family distribution (full R1+R2)
- Per-question efficiency metrics
- Coverage decay by segment
- Node complexity group breakdown
"""
import csv, json, os, sys, time
import numpy as np
from collections import Counter, defaultdict

OUTPUTS_ROOT = "/mnt/data4/yunyang/ADVTEST_DATA/outputs"
ALL_FRAMES_CSV = os.path.join(OUTPUTS_ROOT, "all_frames_stats.csv")

sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)

def main():
    print("Loading frame list...")
    frames = []
    with open(ALL_FRAMES_CSV) as f:
        for row in csv.DictReader(f):
            frames.append(row)
    print(f"Total frames: {len(frames)}")

    # Accumulators
    family_count = Counter()
    family_delta_l2 = defaultdict(float)
    family_delta_l1 = defaultdict(float)
    family_delta_l0 = defaultdict(float)
    family_raw_l2 = defaultdict(float)
    
    phase_count = Counter()
    phase_delta_l2 = defaultdict(float)
    
    # Per-frame stats
    frame_stats = []
    
    # Node group accumulators
    node_groups = {
        "low_3_10": {"min": 3, "max": 10, "frames": []},
        "mid_11_30": {"min": 11, "max": 30, "frames": []},
        "high_31_100": {"min": 31, "max": 100, "frames": []},
    }
    
    total_questions = 0
    total_delta_l2 = 0
    total_raw_l2 = 0
    
    t0 = time.time()
    
    for i, row in enumerate(frames):
        sf = row["scene_frame"]
        nodes = int(row["filtered_nodes"])
        csv_path = os.path.join(OUTPUTS_ROOT, sf, "reports", f"{sf}_incremental_coverage.csv")
        
        if not os.path.exists(csv_path):
            continue
        
        frame_q = 0
        frame_delta_l2 = 0
        frame_raw_l2 = 0
        frame_families = Counter()
        
        # Coverage decay tracking
        frame_coverage_points = []  # (q_idx, coverage_rate_l2)
        
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            for qrow in csv.DictReader(f):
                fam = qrow.get("l2_family", "")
                phase = qrow.get("selection_phase", "")
                dl2 = int(float(qrow.get("delta_l2", 0)))
                dl1 = int(float(qrow.get("delta_l1", 0)))
                dl0 = int(float(qrow.get("delta_l0", 0)))
                rl2 = int(float(qrow.get("raw_l2", 0)))
                cov_l2 = float(qrow.get("coverage_rate_l2", 0))
                
                family_count[fam] += 1
                family_delta_l2[fam] += dl2
                family_delta_l1[fam] += dl1
                family_delta_l0[fam] += dl0
                family_raw_l2[fam] += rl2
                
                phase_count[phase] += 1
                phase_delta_l2[phase] += dl2
                
                frame_q += 1
                frame_delta_l2 += dl2
                frame_raw_l2 += rl2
                frame_families[fam] += 1
                frame_coverage_points.append(cov_l2)
        
        total_questions += frame_q
        total_delta_l2 += frame_delta_l2
        total_raw_l2 += frame_raw_l2
        
        fs = {
            "sf": sf, "nodes": nodes, "q_count": frame_q,
            "delta_l2": frame_delta_l2, "raw_l2": frame_raw_l2,
            "families": dict(frame_families),
            "coverage_points": frame_coverage_points,
        }
        frame_stats.append(fs)
        
        # Assign to node group
        for gname, ginfo in node_groups.items():
            if ginfo["min"] <= nodes <= ginfo["max"]:
                ginfo["frames"].append(fs)
                break
        
        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            fps = (i + 1) / elapsed
            print(f"  [{i+1}/{len(frames)}] {fps:.1f} f/s, ETA {(len(frames)-i-1)/fps:.0f}s")
    
    elapsed = time.time() - t0
    print(f"\nProcessed {len(frame_stats)} frames in {elapsed:.0f}s")
    
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("TABLE 4: Family (Question Type) Distribution - Full R1+R2")
    print("="*70)
    print(f"\n{'Family':<25s} {'Count':>12s} {'%':>7s} {'Avg ΔL2/Q':>10s} {'Avg ΔL1/Q':>10s} {'Avg ΔL0/Q':>10s} {'Avg raw_L2/Q':>12s}")
    print("-"*90)
    for fam, cnt in family_count.most_common():
        pct = cnt / total_questions * 100
        avg_dl2 = family_delta_l2[fam] / cnt if cnt > 0 else 0
        avg_dl1 = family_delta_l1[fam] / cnt if cnt > 0 else 0
        avg_dl0 = family_delta_l0[fam] / cnt if cnt > 0 else 0
        avg_rl2 = family_raw_l2[fam] / cnt if cnt > 0 else 0
        print(f"  {fam:<23s} {cnt:>12,d} {pct:>6.1f}% {avg_dl2:>10.4f} {avg_dl1:>10.4f} {avg_dl0:>10.4f} {avg_rl2:>12.4f}")
    print(f"\n  {'TOTAL':<23s} {total_questions:>12,d}")
    print(f"  Overall Avg ΔL2/Q: {total_delta_l2/total_questions:.4f}")
    print(f"  Redundancy ratio: {1 - total_delta_l2/total_raw_l2:.4f} ({(1-total_delta_l2/total_raw_l2)*100:.2f}%)")
    
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("TABLE 4b: Selection Phase")
    print("="*70)
    for phase, cnt in phase_count.most_common():
        pct = cnt / total_questions * 100
        avg_dl2 = phase_delta_l2[phase] / cnt if cnt > 0 else 0
        print(f"  {phase:<25s} {cnt:>12,d} ({pct:>5.1f}%)  Avg ΔL2/Q: {avg_dl2:.4f}")
    
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("TABLE: Coverage Decay by Segment (L2)")
    print("="*70)
    
    segments = [(0, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 0.90), (0.90, 1.0)]
    print(f"\n{'Segment':<15s} {'Avg ΔL2/Q':>10s} {'Avg Q count':>12s} {'Q% of Total':>12s}")
    print("-"*55)
    
    for seg_start, seg_end in segments:
        seg_deltas = []
        seg_q_counts = []
        for fs in frame_stats:
            if not fs["coverage_points"]:
                continue
            pts = fs["coverage_points"]
            # Find questions in this coverage segment
            q_in_seg = 0
            delta_in_seg = 0
            for qi, cov in enumerate(pts):
                if seg_start <= cov < seg_end or (seg_end == 1.0 and cov >= seg_start):
                    q_in_seg += 1
            if q_in_seg > 0:
                seg_q_counts.append(q_in_seg)
        
        avg_q = np.mean(seg_q_counts) if seg_q_counts else 0
        pct_total = avg_q / np.mean([fs["q_count"] for fs in frame_stats if fs["q_count"] > 0]) * 100 if avg_q > 0 else 0
        # For avg delta, we need to compute from the actual data
        # Approximate: total_delta_l2 in segment / total_q in segment
        print(f"  {seg_start*100:.0f}%→{seg_end*100:.0f}%      {'-':>10s} {avg_q:>12.1f} {pct_total:>11.1f}%")
    
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("TABLE: Node Complexity Groups")
    print("="*70)
    print(f"\n{'Group':<15s} {'#Frames':>8s} {'Avg Q':>10s} {'Avg ΔL2/Q':>10s} {'converge%':>10s} {'dir_chain%':>11s} {'dist_chain%':>12s} {'viewpoint%':>11s} {'diverge%':>9s}")
    print("-"*110)
    
    for gname, ginfo in node_groups.items():
        gframes = ginfo["frames"]
        if not gframes:
            continue
        n = len(gframes)
        avg_q = np.mean([f["q_count"] for f in gframes])
        total_dl2 = sum(f["delta_l2"] for f in gframes)
        total_gq = sum(f["q_count"] for f in gframes)
        avg_dl2_q = total_dl2 / total_gq if total_gq > 0 else 0
        
        # Family percentages
        g_fam_total = Counter()
        for f in gframes:
            for fam, cnt in f["families"].items():
                g_fam_total[fam] += cnt
        
        conv_pct = g_fam_total.get("converge", 0) / total_gq * 100 if total_gq > 0 else 0
        dir_pct = g_fam_total.get("direction_chain", 0) / total_gq * 100 if total_gq > 0 else 0
        dist_pct = g_fam_total.get("distance_chain", 0) / total_gq * 100 if total_gq > 0 else 0
        vp_pct = g_fam_total.get("viewpoint_transfer", 0) / total_gq * 100 if total_gq > 0 else 0
        div_pct = g_fam_total.get("diverge_compare", 0) / total_gq * 100 if total_gq > 0 else 0
        
        label = f"{ginfo['min']}-{ginfo['max']}"
        print(f"  {label:<13s} {n:>8d} {avg_q:>10.0f} {avg_dl2_q:>10.4f} {conv_pct:>9.1f}% {dir_pct:>10.1f}% {dist_pct:>11.1f}% {vp_pct:>10.1f}% {div_pct:>8.2f}%")
    
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("SUMMARY STATISTICS")
    print("="*70)
    print(f"  Total frames: {len(frame_stats)}")
    print(f"  Total questions: {total_questions:,}")
    print(f"  Total delta L2: {total_delta_l2:,}")
    print(f"  Total raw L2: {total_raw_l2:,}")
    print(f"  Avg Q/frame: {total_questions/len(frame_stats):.0f}")
    print(f"  Avg new L2/Q: {total_delta_l2/total_questions:.4f}")
    print(f"  Avg raw L2/Q: {total_raw_l2/total_questions:.4f}")
    print(f"  Redundancy: {(1-total_delta_l2/total_raw_l2)*100:.2f}%")
    
    print("\nDONE")


if __name__ == "__main__":
    main()
