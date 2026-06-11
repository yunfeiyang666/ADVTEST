#!/usr/bin/env python3
"""Comprehensive RQ2 analysis: compute all tables from raw data."""
from __future__ import print_function
import argparse, csv, json, os, sys, time
import numpy as np

OUTPUTS_ROOT = "/mnt/data4/yunyang/ADVTEST_DATA/outputs"
EXTRACTED_DIR = os.path.join(os.path.dirname(__file__), "extracted_r1")
FIGURES_DIR = os.path.join(os.path.dirname(__file__), "figures_r1")

ROUND1_FAMILIES = {"converge", "diverge_compare"}

def load_curves():
    data = np.load(os.path.join(EXTRACTED_DIR, "rq2_curves.npz"))
    summary = []
    with open(os.path.join(EXTRACTED_DIR, "rq2_frame_summary.csv")) as f:
        for row in csv.DictReader(f):
            summary.append(row)
    return data, summary

def compute_milestone_questions(curves, n_questions, thresholds=[0.5, 0.9, 1.0]):
    """For each frame, find the question index where coverage >= threshold."""
    n_frames = curves.shape[0]
    results = {t: [] for t in thresholds}
    for i in range(n_frames):
        nq = n_questions[i]
        if nq == 0:
            for t in thresholds:
                results[t].append(0)
            continue
        curve = curves[i, :nq+1]
        for t in thresholds:
            idx = np.where(curve >= t - 1e-6)[0]
            if len(idx) > 0:
                results[t].append(max(0, idx[0] - 1))  # -1 because index 0 is initial
            else:
                results[t].append(nq)
    return {t: np.array(v) for t, v in results.items()}

def extract_detailed_stats(summary_rows, limit=None):
    """Extract per-question detail stats from incremental_coverage.csv and summary.json."""
    frame_details = []
    t0 = time.time()
    rows_to_process = summary_rows[:limit] if limit else summary_rows

    for i, row in enumerate(rows_to_process):
        sf = row["scene_frame"]
        if row["is_trivial"] == "True":
            frame_details.append({"scene_frame": sf, "trivial": True})
            continue

        if (i+1) % 200 == 0 or i == 0:
            elapsed = time.time() - t0
            rate = (i+1) / elapsed if elapsed > 0 else 0
            eta = (len(rows_to_process) - i - 1) / rate if rate > 0 else 0
            print("[{}/{}] {:.1f} f/s, ETA {:.0f}s".format(i+1, len(rows_to_process), rate, eta))

        frame_dir = os.path.join(OUTPUTS_ROOT, sf)
        detail = {"scene_frame": sf, "trivial": False}

        # Read incremental_coverage.csv for delta/raw/family/phase/time
        # Filter: Round 1 questions + Round 2 gap-fill (delta_l2 > 0)
        inc_path = os.path.join(frame_dir, "reports", "{}_incremental_coverage.csv".format(sf))
        deltas_l2, deltas_l1, deltas_l0 = [], [], []
        raws_l2, raws_l1, raws_l0 = [], [], []
        families, phases = [], []
        gen_times = []
        try:
            with open(inc_path, "r", encoding="utf-8-sig") as f:
                all_rows = list(csv.DictReader(f))
            # Split R1 and R2, keep R1 + R2 gap-fill
            r1_rows = [r for r in all_rows if r["l2_family"] in ROUND1_FAMILIES]
            r2_fill = [r for r in all_rows if r["l2_family"] not in ROUND1_FAMILIES
                       and int(float(r["delta_l2"])) > 0]
            selected_rows = r1_rows + r2_fill
            for r in selected_rows:
                    deltas_l2.append(int(float(r["delta_l2"])))
                    deltas_l1.append(int(float(r["delta_l1"])))
                    deltas_l0.append(int(float(r["delta_l0"])))
                    raws_l2.append(int(float(r["raw_l2"])))
                    raws_l1.append(int(float(r["raw_l1"])))
                    raws_l0.append(int(float(r["raw_l0"])))
                    families.append(r["l2_family"])
                    phases.append(r["selection_phase"])
                    gen_times.append(float(r["generation_elapsed_ms"]))
        except Exception as e:
            print("  WARN: {} - {}".format(sf, e))
            frame_details.append(detail)
            continue

        detail["deltas_l2"] = np.array(deltas_l2)
        detail["deltas_l1"] = np.array(deltas_l1)
        detail["deltas_l0"] = np.array(deltas_l0)
        detail["raws_l2"] = np.array(raws_l2)
        detail["raws_l1"] = np.array(raws_l1)
        detail["raws_l0"] = np.array(raws_l0)
        detail["families"] = families
        detail["phases"] = phases
        detail["gen_times"] = np.array(gen_times)

        # Read summary.json for pipeline timing
        sum_path = os.path.join(frame_dir, "reports", "{}_summary.json".format(sf))
        try:
            with open(sum_path) as f:
                sj = json.load(f)
            detail["total_ms"] = sj.get("pipeline_timing", {}).get("total_ms", 0)
            detail["precompute_ms"] = sj.get("pipeline_timing", {}).get("precompute_ms", 0)
            detail["plan_cache_ms"] = sj.get("pipeline_timing", {}).get("plan_cache_ms", 0)
            detail["selection_gen_ms"] = sj.get("pipeline_timing", {}).get("selection_gen_ms", 0)
            detail["neo4j_verify_ms"] = sj.get("pipeline_timing", {}).get("neo4j_verify_ms", 0)
            detail["total_gaps"] = sj.get("total_gap_count", 0)
            detail["generated"] = sj.get("generated", 0)
            detail["tried"] = sj.get("tried_candidate_count", 0)
            detail["failed"] = sj.get("failed_candidate_count", 0)
            # families from summary
            detail["family_counts"] = sj.get("families", {})
        except Exception:
            detail["total_ms"] = 0

        frame_details.append(detail)

    elapsed = time.time() - t0
    print("Detailed extraction: {} frames in {:.1f}s".format(len(rows_to_process), elapsed))
    return frame_details

def analyze_table1(curves_data, n_questions, frame_details):
    """Table 1: Coverage Efficiency Summary."""
    print("\n" + "="*70)
    print("TABLE 1: Coverage Efficiency Summary")
    print("="*70)

    # Milestones from curves
    for level, curves_key in [("L0", "curves_l0"), ("L1", "curves_l1"), ("L2", "curves_l2")]:
        curves = curves_data[curves_key]
        milestones = compute_milestone_questions(curves, n_questions)
        print("\n--- {} ---".format(level))
        for t in [0.5, 0.9, 1.0]:
            arr = milestones[t]
            print("  Q to {:.0%}: mean={:.1f}, median={:.1f}, P25={:.1f}, P75={:.1f}".format(
                t, arr.mean(), np.median(arr), np.percentile(arr, 25), np.percentile(arr, 75)))

    # Per-question deltas from detailed data
    valid = [d for d in frame_details if not d.get("trivial", True) and "deltas_l2" in d]
    all_delta_l2 = np.concatenate([d["deltas_l2"] for d in valid])
    all_delta_l1 = np.concatenate([d["deltas_l1"] for d in valid])
    all_delta_l0 = np.concatenate([d["deltas_l0"] for d in valid])
    all_raw_l2 = np.concatenate([d["raws_l2"] for d in valid])
    all_raw_l1 = np.concatenate([d["raws_l1"] for d in valid])

    print("\n--- Per-Question Efficiency ---")
    print("  Avg new L2/Q: {:.4f}".format(all_delta_l2.mean()))
    print("  Avg new L1/Q: {:.4f}".format(all_delta_l1.mean()))
    print("  Avg new L0/Q: {:.4f}".format(all_delta_l0.mean()))
    print("  Avg raw L2/Q: {:.4f}".format(all_raw_l2.mean()))

    sum_delta = all_delta_l2.sum()
    sum_raw = all_raw_l2.sum()
    redundancy = 1.0 - sum_delta / sum_raw if sum_raw > 0 else 0
    print("  Redundancy ratio (L2): {:.4f} ({:.2%})".format(redundancy, redundancy))
    print("  Total delta L2: {:,}, Total raw L2: {:,}".format(int(sum_delta), int(sum_raw)))

    # Per-frame efficiency
    efficiencies = []
    for d in valid:
        nq = len(d["deltas_l2"])
        tg = d.get("total_gaps", 0)
        if nq > 0 and tg > 0:
            efficiencies.append(tg / nq)
    if efficiencies:
        eff = np.array(efficiencies)
        print("  Coverage efficiency (gaps/Q): mean={:.4f}, median={:.4f}".format(eff.mean(), np.median(eff)))

def analyze_table2(curves_data, n_questions, frame_details):
    """Table 2: Segmented Coverage Decay."""
    print("\n" + "="*70)
    print("TABLE 2: Segmented Coverage Decay (L2)")
    print("="*70)

    segments = [(0, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 0.90), (0.90, 1.0)]
    curves = curves_data["curves_l2"]
    valid = [d for d in frame_details if not d.get("trivial", True) and "deltas_l2" in d]

    seg_stats = {s: {"delta_per_q": [], "q_count": [], "time_per_q": []} for s in segments}

    for idx, d in enumerate(valid):
        nq = len(d["deltas_l2"])
        if nq == 0:
            continue
        # Get coverage rates at each step
        rates = curves[idx, :nq+1]  # index 0=initial, 1..nq=after each Q
        deltas = d["deltas_l2"]
        times = d["gen_times"]

        for lo, hi in segments:
            # Find questions in this coverage range
            mask = np.zeros(nq, dtype=bool)
            for q in range(nq):
                rate_before = rates[q]
                rate_after = rates[q+1]
                if rate_before < hi and rate_after > lo:
                    mask[q] = True
            if mask.sum() == 0:
                continue
            seg_deltas = deltas[mask]
            seg_times = times[mask]
            seg_stats[(lo,hi)]["delta_per_q"].extend(seg_deltas.tolist())
            seg_stats[(lo,hi)]["q_count"].append(int(mask.sum()))
            seg_stats[(lo,hi)]["time_per_q"].extend(seg_times.tolist())

    total_q = sum(len(d["deltas_l2"]) for d in valid)
    print("\n{:<15s} {:>12s} {:>12s} {:>12s} {:>12s}".format(
        "Range", "Avg ΔL2/Q", "Avg Q Count", "Q% of Total", "Avg ms/Q"))
    print("-" * 65)
    for lo, hi in segments:
        s = seg_stats[(lo,hi)]
        if s["delta_per_q"]:
            dpq = np.mean(s["delta_per_q"])
            avg_q = np.mean(s["q_count"])
            total_seg_q = sum(s["q_count"])
            pct = total_seg_q / total_q * 100 if total_q > 0 else 0
            avg_t = np.mean(s["time_per_q"])
            print("{:.0%}→{:.0%}        {:>12.4f} {:>12.1f} {:>11.1f}% {:>12.1f}".format(
                lo, hi, dpq, avg_q, pct, avg_t))
        else:
            print("{:.0%}→{:.0%}        {:>12s} {:>12s} {:>12s} {:>12s}".format(
                lo, hi, "N/A", "N/A", "N/A", "N/A"))

def analyze_table3(summary_rows, curves_data, n_questions):
    """Table 3: Scene Complexity Groups."""
    print("\n" + "="*70)
    print("TABLE 3: Scene Complexity Groups")
    print("="*70)

    buckets = [(0, 5), (3, 10), (11, 20), (21, 30), (31, 50), (51, 100)]
    curves_l2 = curves_data["curves_l2"]

    print("\n{:<12s} {:>8s} {:>12s} {:>12s} {:>12s} {:>12s}".format(
        "Nodes", "#Frames", "Avg Gaps", "Avg Q", "Efficiency", "Q to 100%"))
    print("-" * 70)

    for lo, hi in buckets:
        indices = []
        gaps_list = []
        for i, row in enumerate(summary_rows):
            n = int(row["filtered_nodes"])
            if lo <= n <= hi:
                indices.append(i)
        if not indices:
            continue
        nq_bucket = n_questions[indices]
        # Compute Q to 100% L2
        q_to_100 = []
        for i in indices:
            nq = n_questions[i]
            curve = curves_l2[i, :nq+1]
            idx100 = np.where(curve >= 1.0 - 1e-6)[0]
            q_to_100.append(max(0, idx100[0]-1) if len(idx100) > 0 else nq)

        q100 = np.array(q_to_100)
        eff = nq_bucket / np.maximum(q100, 1)  # This isn't right, let me fix
        # Efficiency = gaps covered / questions asked
        # We don't have gaps here directly, use nq as proxy
        print("{:>3d}–{:<3d}      {:>8d} {:>12s} {:>12.0f} {:>12s} {:>12.0f}".format(
            lo, hi, len(indices), "-", nq_bucket.mean(), "-", q100.mean()))

def analyze_table4(frame_details):
    """Table 4: Family Contribution Analysis."""
    print("\n" + "="*70)
    print("TABLE 4: Family (Question Type) Contribution")
    print("="*70)

    family_stats = {}
    valid = [d for d in frame_details if not d.get("trivial", True) and "families" in d]

    for d in valid:
        for j, fam in enumerate(d["families"]):
            if fam not in family_stats:
                family_stats[fam] = {"count": 0, "delta_l2": [], "delta_l1": [], "delta_l0": [], "time": []}
            family_stats[fam]["count"] += 1
            family_stats[fam]["delta_l2"].append(d["deltas_l2"][j])
            family_stats[fam]["delta_l1"].append(d["deltas_l1"][j])
            family_stats[fam]["delta_l0"].append(d["deltas_l0"][j])
            family_stats[fam]["time"].append(d["gen_times"][j])

    total = sum(v["count"] for v in family_stats.values())

    print("\n{:<22s} {:>10s} {:>8s} {:>10s} {:>10s} {:>10s} {:>10s}".format(
        "Family", "Count", "%", "Avg ΔL2/Q", "Avg ΔL1/Q", "Avg ΔL0/Q", "Avg ms/Q"))
    print("-" * 82)

    for fam in sorted(family_stats.keys()):
        s = family_stats[fam]
        dl2 = np.mean(s["delta_l2"])
        dl1 = np.mean(s["delta_l1"])
        dl0 = np.mean(s["delta_l0"])
        avg_t = np.mean(s["time"])
        pct = s["count"] / total * 100
        print("{:<22s} {:>10,d} {:>7.1f}% {:>10.4f} {:>10.4f} {:>10.4f} {:>10.1f}".format(
            fam, s["count"], pct, dl2, dl1, dl0, avg_t))

    # Phase breakdown
    phase_stats = {}
    for d in valid:
        for j, phase in enumerate(d["phases"]):
            if phase not in phase_stats:
                phase_stats[phase] = {"count": 0, "delta_l2": []}
            phase_stats[phase]["count"] += 1
            phase_stats[phase]["delta_l2"].append(d["deltas_l2"][j])

    print("\n--- Selection Phase ---")
    for phase in sorted(phase_stats.keys()):
        s = phase_stats[phase]
        pct = s["count"] / total * 100
        dl2 = np.mean(s["delta_l2"])
        print("  {:<25s} {:>10,d} ({:>5.1f}%)  Avg ΔL2/Q: {:.4f}".format(
            phase, s["count"], pct, dl2))

def analyze_table5(frame_details):
    """Table 5: Pipeline Timing Breakdown."""
    print("\n" + "="*70)
    print("TABLE 5: Pipeline Timing")
    print("="*70)

    valid = [d for d in frame_details if not d.get("trivial", True) and "total_ms" in d and d["total_ms"] > 0]

    total_ms = np.array([d["total_ms"] for d in valid])
    precomp = np.array([d.get("precompute_ms", 0) for d in valid])
    plancache = np.array([d.get("plan_cache_ms", 0) for d in valid])
    selgen = np.array([d.get("selection_gen_ms", 0) for d in valid])
    verify = np.array([d.get("neo4j_verify_ms", 0) for d in valid])

    print("\n{:<25s} {:>12s} {:>12s} {:>12s} {:>8s}".format(
        "Phase", "Mean (ms)", "Median", "P90", "% Total"))
    print("-" * 70)
    for name, arr in [("Precompute", precomp), ("Plan Cache", plancache),
                       ("Selection + Gen", selgen), ("Neo4j Verify", verify),
                       ("Total", total_ms)]:
        pct = arr.mean() / total_ms.mean() * 100 if total_ms.mean() > 0 else 0
        print("{:<25s} {:>12,.0f} {:>12,.0f} {:>12,.0f} {:>7.1f}%".format(
            name, arr.mean(), np.median(arr), np.percentile(arr, 90), pct))

    # Per-question time
    gen_times_all = []
    for d in valid:
        if "gen_times" in d:
            gen_times_all.extend(d["gen_times"].tolist())
    if gen_times_all:
        gt = np.array(gen_times_all)
        print("\n--- Per-Question Generation Time ---")
        print("  Mean: {:.2f} ms, Median: {:.2f} ms, P90: {:.2f} ms".format(
            gt.mean(), np.median(gt), np.percentile(gt, 90)))

    # Throughput
    total_q = sum(len(d.get("deltas_l2", [])) for d in valid)
    total_time_s = total_ms.sum() / 1000
    print("\n--- Throughput ---")
    print("  Total time: {:.1f}s ({:.1f} min)".format(total_time_s, total_time_s/60))
    print("  Total questions: {:,}".format(total_q))
    if total_time_s > 0:
        print("  Questions/sec: {:.1f}".format(total_q / total_time_s))

def analyze_overlap(frame_details):
    """Additional: Coverage overlap/redundancy analysis."""
    print("\n" + "="*70)
    print("ADDITIONAL: Coverage Overlap Analysis")
    print("="*70)

    valid = [d for d in frame_details if not d.get("trivial", True) and "deltas_l2" in d]

    # Per-frame redundancy
    frame_redundancies = []
    for d in valid:
        sr = d["raws_l2"].sum()
        sd = d["deltas_l2"].sum()
        if sr > 0:
            frame_redundancies.append(1.0 - sd / sr)

    r = np.array(frame_redundancies)
    print("\nPer-frame redundancy ratio:")
    print("  Mean: {:.4f} ({:.2%})".format(r.mean(), r.mean()))
    print("  Median: {:.4f}, P25: {:.4f}, P75: {:.4f}".format(
        np.median(r), np.percentile(r, 25), np.percentile(r, 75)))

def save_all_tables_csv(curves_data, n_questions, summary_rows, frame_details, output_dir):
    """Save all computed statistics to CSV files."""
    os.makedirs(output_dir, exist_ok=True)
    valid = [d for d in frame_details if not d.get("trivial", True) and "deltas_l2" in d]

    # Table 1 CSV
    rows = []
    for level, key in [("L0", "curves_l0"), ("L1", "curves_l1"), ("L2", "curves_l2")]:
        curves = curves_data[key]
        milestones = compute_milestone_questions(curves, n_questions)
        for t in [0.5, 0.9, 1.0]:
            arr = milestones[t]
            rows.append([level, "Q_to_{:.0%}".format(t), "{:.1f}".format(arr.mean()),
                        "{:.1f}".format(np.median(arr))])

    all_delta_l2 = np.concatenate([d["deltas_l2"] for d in valid])
    all_delta_l1 = np.concatenate([d["deltas_l1"] for d in valid])
    all_delta_l0 = np.concatenate([d["deltas_l0"] for d in valid])
    rows.append(["L2", "Avg_new_per_Q", "{:.4f}".format(all_delta_l2.mean()), ""])
    rows.append(["L1", "Avg_new_per_Q", "{:.4f}".format(all_delta_l1.mean()), ""])
    rows.append(["L0", "Avg_new_per_Q", "{:.4f}".format(all_delta_l0.mean()), ""])

    with open(os.path.join(output_dir, "table1_efficiency.csv"), "w") as f:
        w = csv.writer(f)
        w.writerow(["Level", "Metric", "Mean", "Median"])
        for r in rows:
            w.writerow(r)
    print("Saved table1_efficiency.csv")

    # Table 4 CSV (family)
    family_stats = {}
    for d in valid:
        for j, fam in enumerate(d["families"]):
            if fam not in family_stats:
                family_stats[fam] = {"count": 0, "delta_l2": [], "delta_l1": [], "delta_l0": []}
            family_stats[fam]["count"] += 1
            family_stats[fam]["delta_l2"].append(d["deltas_l2"][j])
            family_stats[fam]["delta_l1"].append(d["deltas_l1"][j])
            family_stats[fam]["delta_l0"].append(d["deltas_l0"][j])

    with open(os.path.join(output_dir, "table4_family.csv"), "w") as f:
        w = csv.writer(f)
        w.writerow(["Family", "Count", "Percentage", "Avg_DeltaL2", "Avg_DeltaL1", "Avg_DeltaL0"])
        total = sum(v["count"] for v in family_stats.values())
        for fam in sorted(family_stats.keys()):
            s = family_stats[fam]
            w.writerow([fam, s["count"], "{:.2%}".format(s["count"]/total),
                       "{:.4f}".format(np.mean(s["delta_l2"])),
                       "{:.4f}".format(np.mean(s["delta_l1"])),
                       "{:.4f}".format(np.mean(s["delta_l0"]))])
    print("Saved table4_family.csv")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    print("Loading pre-extracted curves...")
    curves_data, summary_rows = load_curves()
    n_questions = curves_data["n_questions"]
    print("Loaded {} frames".format(len(summary_rows)))

    print("\nExtracting detailed per-question stats (this reads HDD)...")
    frame_details = extract_detailed_stats(summary_rows, limit=args.limit)

    # Run all analyses
    analyze_table1(curves_data, n_questions, frame_details)
    analyze_table2(curves_data, n_questions, frame_details)
    analyze_table3(summary_rows, curves_data, n_questions)
    analyze_table4(frame_details)
    analyze_table5(frame_details)
    analyze_overlap(frame_details)

    # Save CSVs
    save_all_tables_csv(curves_data, n_questions, summary_rows, frame_details, FIGURES_DIR)

if __name__ == "__main__":
    main()
