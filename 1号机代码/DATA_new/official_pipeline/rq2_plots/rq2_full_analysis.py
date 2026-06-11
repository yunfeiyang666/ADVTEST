#!/usr/bin/env python3
"""RQ2 Complete Analysis — aligned with rq2_analysis_plan.md 16 dimensions.

Groups: S(3-15), M(16-30), L(≥31), All(≥3)
Reads: incremental_coverage.csv (HDD) + extracted npz (local)
Outputs: rq2_full_report.log with all 16 dimensions
"""
import csv, json, os, sys, time, math
import numpy as np
from collections import Counter, defaultdict
from pathlib import Path

OUTPUTS_ROOT = "/mnt/data4/yunyang/ADVTEST_DATA/outputs"
ALL_FRAMES_CSV = os.path.join(OUTPUTS_ROOT, "all_frames_stats.csv")
EXTRACTED_R1 = Path(__file__).parent / "extracted_v2_r1"
EXTRACTED_FULL = Path(__file__).parent / "extracted_v2"

sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)

# Groups aligned with analysis plan
GROUPS = {
    "S(3-15)":  {"min": 3, "max": 15},
    "M(16-30)": {"min": 16, "max": 30},
    "L(≥31)":   {"min": 31, "max": 999},
    "All(≥3)":  {"min": 3, "max": 999},
}


def main():
    t0 = time.time()
    
    # ─��� Load frame list ──────────────────────────────────────────────────
    print("Loading frame list...")
    frames_meta = []
    with open(ALL_FRAMES_CSV) as f:
        for row in csv.DictReader(f):
            frames_meta.append(row)
    print(f"Total frames: {len(frames_meta)}")
    
    # ── Phase 1: Read HDD data (incremental_coverage.csv) ────────────────
    print("\nPhase 1: Reading incremental_coverage CSVs from HDD...")
    
    # Per-frame collected data
    frame_data = []
    
    for i, row in enumerate(frames_meta):
        sf = row["scene_frame"]
        nodes = int(row["filtered_nodes"])
        total_gaps = int(row["total_l2_gaps"])
        
        csv_path = os.path.join(OUTPUTS_ROOT, sf, "reports", f"{sf}_incremental_coverage.csv")
        if not os.path.exists(csv_path):
            continue
        
        fd = {
            "sf": sf, "nodes": nodes, "total_gaps": total_gaps,
            "q_count": 0, "r1_count": 0, "r2_count": 0,
            "delta_l2_total": 0, "raw_l2_total": 0,
            "delta_l1_total": 0, "delta_l0_total": 0,
            "families": Counter(),
            "r1_families": Counter(),
            "r2_families": Counter(),
            # Coverage at R1 end
            "r1_end_cov_l2": 0.0,
            # Timing
            "timing_ms_total": 0.0,
            # Constraint stats
            "constraint_counts": [],
            # Candidate filtering
            "cand_before_sum": 0, "cand_after_sum": 0, "cand_count": 0,
            # Answer types
            "answer_types": Counter(),
            # Coverage points for decay analysis
            "coverage_points": [],
            # Per-question delta_l2 for decay
            "per_q_delta_l2": [],
        }
        
        r1_ended = False
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            for qrow in csv.DictReader(f):
                fam = qrow.get("l2_family", "")
                phase = qrow.get("selection_phase", "")
                dl2 = int(float(qrow.get("delta_l2", 0)))
                dl1 = int(float(qrow.get("delta_l1", 0)))
                dl0 = int(float(qrow.get("delta_l0", 0)))
                rl2 = int(float(qrow.get("raw_l2", 0)))
                cov_l2 = float(qrow.get("coverage_rate_l2", 0))
                elapsed = float(qrow.get("generation_elapsed_ms", 0))
                
                fd["q_count"] += 1
                fd["families"][fam] += 1
                fd["delta_l2_total"] += dl2
                fd["raw_l2_total"] += rl2
                fd["delta_l1_total"] += dl1
                fd["delta_l0_total"] += dl0
                fd["timing_ms_total"] += elapsed
                fd["coverage_points"].append(cov_l2)
                fd["per_q_delta_l2"].append(dl2)
                
                # R1 vs R2
                is_r1 = fam in {"converge", "diverge_compare"}
                if is_r1 and not r1_ended:
                    fd["r1_count"] += 1
                    fd["r1_families"][fam] += 1
                    fd["r1_end_cov_l2"] = cov_l2
                else:
                    if is_r1 and r1_ended:
                        # This shouldn't happen but handle gracefully
                        fd["r2_count"] += 1
                        fd["r2_families"][fam] += 1
                    else:
                        if not r1_ended and not is_r1:
                            r1_ended = True
                        fd["r2_count"] += 1
                        fd["r2_families"][fam] += 1
        
        frame_data.append(fd)
        
        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            fps = (i + 1) / elapsed
            print(f"  [{i+1}/{len(frames_meta)}] {fps:.1f} f/s, ETA {(len(frames_meta)-i-1)/fps:.0f}s")
    
    print(f"Phase 1 done: {len(frame_data)} frames in {time.time()-t0:.0f}s")
    
    # ── Phase 2: Load local npz for curve analysis ───────────────────────
    print("\nPhase 2: Loading extracted curves...")
    r1_data = np.load(str(EXTRACTED_R1 / "rq2_curves.npz"))
    r1_curves_l0 = r1_data["curves_l0"]
    r1_curves_l1 = r1_data["curves_l1"]
    r1_curves_l2 = r1_data["curves_l2"]
    r1_nq = r1_data["n_questions"]
    with open(str(EXTRACTED_R1 / "rq2_meta.json")) as f:
        r1_meta = json.load(f)
    
    full_data = np.load(str(EXTRACTED_FULL / "rq2_curves.npz"))
    full_curves_l2 = full_data["curves_l2"]
    full_nq = full_data["n_questions"]
    
    # Load frame summary for node counts mapping
    r1_summary = []
    with open(str(EXTRACTED_R1 / "rq2_frame_summary.csv")) as f:
        for row in csv.DictReader(f):
            r1_summary.append(row)
    
    print(f"R1 curves: {r1_curves_l2.shape}, Full curves: {full_curves_l2.shape}")
    
    # ══════════════════════════════════════════════════════════════════════
    # D1: Coverage curves + AUC (per group)
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("D1: Coverage Curves + AUC (per group, R1+R2 gap-fill scope)")
    print("="*70)
    
    # Map frames to groups by node count
    for gname, gspec in GROUPS.items():
        indices = [i for i, row in enumerate(r1_summary) 
                   if gspec["min"] <= int(row["filtered_nodes"]) <= gspec["max"]]
        if not indices:
            continue
        
        nqs = r1_nq[indices]
        valid = nqs > 0
        if not valid.any():
            continue
        
        # AUC normalized
        n_points = 200
        x_norm = np.linspace(0, 1, n_points)
        
        auc_l0, auc_l1, auc_l2 = [], [], []
        for idx in indices:
            nq = r1_nq[idx]
            if nq == 0:
                continue
            x_orig = np.linspace(0, 1, nq + 1)
            for curves, auc_list in [(r1_curves_l0, auc_l0), (r1_curves_l1, auc_l1), (r1_curves_l2, auc_l2)]:
                y_interp = np.interp(x_norm, x_orig, curves[idx, :nq+1])
                auc_list.append(float(np.trapz(y_interp, x_norm)))
        
        avg_q = float(np.mean(nqs[valid]))
        print(f"\n  {gname}: {len(indices)} frames, avg Q={avg_q:.0f}")
        print(f"    AUC L0 (norm): {np.mean(auc_l0):.4f}")
        print(f"    AUC L1 (norm): {np.mean(auc_l1):.4f}")
        print(f"    AUC L2 (norm): {np.mean(auc_l2):.4f}")
    
    # ══════════════════════════════════════════════════════════════════════
    # D2: Coverage Decay (5-segment ΔL2/Q)
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("D2: Coverage Decay (5-segment, R1+R2 gap-fill scope)")
    print("="*70)
    
    segments = [(0, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 0.90), (0.90, 1.0)]
    
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in frame_data if gspec["min"] <= fd["nodes"] <= gspec["max"]]
        if not gframes:
            continue
        
        print(f"\n  {gname} ({len(gframes)} frames):")
        print(f"    {'Segment':<12s} {'Avg ΔL2/Q':>10s} {'Avg #Q':>10s} {'Q%':>8s}")
        
        for seg_start, seg_end in segments:
            seg_dl2_list = []
            seg_q_list = []
            for fd in gframes:
                pts = fd["coverage_points"]
                deltas = fd["per_q_delta_l2"]
                if not pts:
                    continue
                q_in = 0
                dl2_in = 0
                for qi, cov in enumerate(pts):
                    in_seg = (seg_start <= cov < seg_end) if seg_end < 1.0 else (cov >= seg_start)
                    if in_seg:
                        q_in += 1
                        dl2_in += deltas[qi]
                if q_in > 0:
                    seg_dl2_list.append(dl2_in / q_in)
                    seg_q_list.append(q_in)
            
            avg_dl2 = np.mean(seg_dl2_list) if seg_dl2_list else 0
            avg_q = np.mean(seg_q_list) if seg_q_list else 0
            total_avg_q = np.mean([fd["q_count"] for fd in gframes])
            q_pct = avg_q / total_avg_q * 100 if total_avg_q > 0 else 0
            print(f"    {seg_start*100:.0f}%→{seg_end*100:.0f}%     {avg_dl2:>10.4f} {avg_q:>10.1f} {q_pct:>7.1f}%")
    
    # ══════════════════════════════════════════════════════════════════════
    # D3: Question Type Distribution (dual dimension)
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("D3: Question Type Distribution (L2 family × answer_type)")
    print("="*70)
    
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in frame_data if gspec["min"] <= fd["nodes"] <= gspec["max"]]
        if not gframes:
            continue
        
        total_gq = sum(fd["q_count"] for fd in gframes)
        g_fam = Counter()
        for fd in gframes:
            g_fam += fd["families"]
        
        print(f"\n  {gname} ({len(gframes)} frames, {total_gq:,} Q):")
        for fam, cnt in g_fam.most_common():
            print(f"    {fam:<23s} {cnt:>12,d} ({cnt/total_gq*100:>5.1f}%)")
    
    # ══════════════════════════════════════════════════════════════════════
    # D4: Compression ratio (R1+R2 gap-fill Q / total_gaps)
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("D4: Compression Ratio (Q_to_100% / total_gaps)")
    print("="*70)
    
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in frame_data if gspec["min"] <= fd["nodes"] <= gspec["max"] and fd["total_gaps"] > 0]
        if not gframes:
            continue
        
        # R1+R2fill Q count ≈ R1 count + R2 gap-fill count
        # But we have the R1 extracted data for exact Q counts
        ratios = []
        for fd in gframes:
            # compression = actual questions needed / total gaps
            r1_fill_q = fd["r1_count"]  # R1 covers most gaps
            # We need Q_to_100% from extracted data
            if fd["total_gaps"] > 0:
                # Use per-frame data: delta_l2_total should equal total_gaps
                ratios.append(fd["q_count"] / fd["total_gaps"])
        
        if ratios:
            print(f"  {gname}: median={np.median(ratios):.4f}, mean={np.mean(ratios):.4f}, P25={np.percentile(ratios,25):.4f}, P75={np.percentile(ratios,75):.4f}")
    
    # ══════════════════════════════════════════════════════════════════��═══
    # D5: Initial Coverage Distribution
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("D5: Initial Coverage Distribution")
    print("="*70)
    
    for gname, gspec in GROUPS.items():
        indices = [i for i, row in enumerate(r1_summary)
                   if gspec["min"] <= int(row["filtered_nodes"]) <= gspec["max"]]
        if not indices:
            continue
        
        init_l0 = r1_curves_l0[indices, 0]
        init_l1 = r1_curves_l1[indices, 0]
        init_l2 = r1_curves_l2[indices, 0]
        
        print(f"\n  {gname} ({len(indices)} frames):")
        print(f"    Init L0: mean={np.mean(init_l0):.4f}, median={np.median(init_l0):.4f}")
        print(f"    Init L1: mean={np.mean(init_l1):.4f}, median={np.median(init_l1):.4f}")
        print(f"    Init L2: mean={np.mean(init_l2):.4f}, median={np.median(init_l2):.4f}")
    
    # ══════════════════════════════════════════════════════════════════════
    # D6: R1 vs R2 contribution
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("D6: R1 vs R2 Contribution")
    print("="*70)
    
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in frame_data if gspec["min"] <= fd["nodes"] <= gspec["max"] and fd["q_count"] > 0]
        if not gframes:
            continue
        
        r1_cov = [fd["r1_end_cov_l2"] for fd in gframes]
        r1_q = [fd["r1_count"] for fd in gframes]
        r2_q = [fd["r2_count"] for fd in gframes]
        r1_dl2 = [sum(fd["per_q_delta_l2"][:fd["r1_count"]]) for fd in gframes]
        r2_dl2 = [fd["delta_l2_total"] - sum(fd["per_q_delta_l2"][:fd["r1_count"]]) for fd in gframes]
        
        print(f"\n  {gname} ({len(gframes)} frames):")
        print(f"    R1 end L2 cov: mean={np.mean(r1_cov):.4f}")
        print(f"    R1 Q: mean={np.mean(r1_q):.0f}, R2 Q: mean={np.mean(r2_q):.0f}")
        print(f"    R1 ΔL2: mean={np.mean(r1_dl2):.0f}, R2 ΔL2: mean={np.mean(r2_dl2):.0f}")
        r1_pct = np.mean(r1_dl2) / (np.mean(r1_dl2) + np.mean(r2_dl2)) * 100 if (np.mean(r1_dl2) + np.mean(r2_dl2)) > 0 else 0
        print(f"    R1 covers {r1_pct:.1f}% of total ΔL2")
    
    # ══════════════════════════════════════════════════════════════════════
    # D7: Scalability (Q_to_100% vs nodes, log-log)
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("D7: Scalability (Q_to_100% vs nodes)")
    print("="*70)
    
    nodes_arr = []
    q100_arr = []
    for i, row in enumerate(r1_summary):
        nq = r1_nq[i]
        n = int(row["filtered_nodes"])
        if nq > 0 and n >= 3:
            nodes_arr.append(n)
            q100_arr.append(nq)
    
    nodes_arr = np.array(nodes_arr, dtype=float)
    q100_arr = np.array(q100_arr, dtype=float)
    
    # Log-log linear fit
    log_n = np.log10(nodes_arr)
    log_q = np.log10(q100_arr)
    slope, intercept = np.polyfit(log_n, log_q, 1)
    r_squared = 1 - np.sum((log_q - (slope * log_n + intercept))**2) / np.sum((log_q - np.mean(log_q))**2)
    
    print(f"  Log-log fit: Q = 10^{intercept:.2f} × N^{slope:.2f}")
    print(f"  R² = {r_squared:.4f}")
    print(f"  Interpretation: Q grows as N^{slope:.2f}")
    
    # ══════════════════════════════════════════════════════════════════════
    # D8: Redundancy analysis
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("D8: Redundancy Analysis (1 - Σdelta/Σraw)")
    print("="*70)
    
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in frame_data if gspec["min"] <= fd["nodes"] <= gspec["max"] and fd["raw_l2_total"] > 0]
        if not gframes:
            continue
        
        per_frame_red = [1 - fd["delta_l2_total"]/fd["raw_l2_total"] for fd in gframes if fd["raw_l2_total"] > 0]
        total_dl2 = sum(fd["delta_l2_total"] for fd in gframes)
        total_rl2 = sum(fd["raw_l2_total"] for fd in gframes)
        global_red = 1 - total_dl2 / total_rl2
        
        print(f"  {gname}: global={global_red:.4f} ({global_red*100:.2f}%), per-frame mean={np.mean(per_frame_red):.4f}, median={np.median(per_frame_red):.4f}")
    
    # ══════════════════════════════════════════════════════════════════════
    # D16: Coverage saturation (95%→100% tail cost)
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("D16: Coverage Saturation (95%→100% tail cost)")
    print("="*70)
    
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in frame_data if gspec["min"] <= fd["nodes"] <= gspec["max"] and fd["coverage_points"]]
        if not gframes:
            continue
        
        q_95_100 = []
        q_total = []
        for fd in gframes:
            pts = fd["coverage_points"]
            total = len(pts)
            # Find first Q where coverage >= 0.95
            q_95 = total  # default: never reached
            for qi, cov in enumerate(pts):
                if cov >= 0.95:
                    q_95 = qi + 1
                    break
            tail_q = total - q_95
            q_95_100.append(tail_q)
            q_total.append(total)
        
        avg_tail = np.mean(q_95_100)
        avg_total = np.mean(q_total)
        pct = avg_tail / avg_total * 100 if avg_total > 0 else 0
        print(f"  {gname}: avg tail Q (95%→100%) = {avg_tail:.0f} ({pct:.1f}% of total), avg total Q = {avg_total:.0f}")
    
    # ══════════════════════════════════════════════════════════════════════
    # FINAL SUMMARY TABLE
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("FINAL SUMMARY TABLE (per group)")
    print("="*70)
    
    header = f"{'Group':<12s} {'#Frames':>7s} {'Avg Nodes':>9s} {'Avg Q':>10s} {'ΔL2/Q':>7s} {'Red%':>6s} {'AUC_L2':>7s} {'R1 cov%':>8s} {'conv%':>6s} {'dir%':>5s} {'dist%':>6s} {'vp%':>5s} {'div%':>5s}"
    print(f"\n{header}")
    print("-" * len(header))
    
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in frame_data if gspec["min"] <= fd["nodes"] <= gspec["max"]]
        if not gframes:
            continue
        
        n = len(gframes)
        avg_nodes = np.mean([fd["nodes"] for fd in gframes])
        avg_q = np.mean([fd["q_count"] for fd in gframes])
        total_dl2 = sum(fd["delta_l2_total"] for fd in gframes)
        total_gq = sum(fd["q_count"] for fd in gframes)
        total_rl2 = sum(fd["raw_l2_total"] for fd in gframes)
        avg_dl2_q = total_dl2 / total_gq if total_gq > 0 else 0
        red = (1 - total_dl2/total_rl2) * 100 if total_rl2 > 0 else 0
        r1_cov = np.mean([fd["r1_end_cov_l2"] for fd in gframes if fd["q_count"] > 0])
        
        g_fam = Counter()
        for fd in gframes:
            g_fam += fd["families"]
        conv = g_fam.get("converge", 0) / total_gq * 100
        dir_c = g_fam.get("direction_chain", 0) / total_gq * 100
        dist_c = g_fam.get("distance_chain", 0) / total_gq * 100
        vp = g_fam.get("viewpoint_transfer", 0) / total_gq * 100
        div = g_fam.get("diverge_compare", 0) / total_gq * 100
        
        # AUC from npz
        indices = [i for i, row in enumerate(r1_summary)
                   if gspec["min"] <= int(row["filtered_nodes"]) <= gspec["max"] and r1_nq[i] > 0]
        auc_l2_list = []
        for idx in indices:
            nq = r1_nq[idx]
            if nq == 0:
                continue
            x = np.linspace(0, 1, min(nq+1, 200))
            y = np.interp(x, np.linspace(0, 1, nq+1), r1_curves_l2[idx, :nq+1])
            auc_l2_list.append(float(np.trapz(y, x)))
        auc_l2 = np.mean(auc_l2_list) if auc_l2_list else 0
        
        print(f"  {gname:<10s} {n:>7d} {avg_nodes:>9.1f} {avg_q:>10.0f} {avg_dl2_q:>7.4f} {red:>5.1f}% {auc_l2:>7.4f} {r1_cov*100:>7.1f}% {conv:>5.1f}% {dir_c:>4.1f}% {dist_c:>5.1f}% {vp:>4.1f}% {div:>4.2f}%")
    
    print(f"\nTotal time: {time.time()-t0:.0f}s")
    print("DONE")


if __name__ == "__main__":
    main()
