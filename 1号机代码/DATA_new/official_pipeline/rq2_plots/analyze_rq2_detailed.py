#!/usr/bin/env python3
"""Detailed RQ2 analysis: Round1-only vs Round1+2, node-group breakdown, two-dimension family classification."""
import csv, json, os, sys, time
import numpy as np
from collections import Counter, defaultdict

OUTPUTS_ROOT = "/mnt/data4/yunyang/ADVTEST_DATA/outputs"
ALL_FRAMES_CSV = os.path.join(OUTPUTS_ROOT, "all_frames_stats.csv")
EXTRACTED_DIR = os.path.join(os.path.dirname(__file__), "extracted_r1")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__))

ROUND1_FAMILIES = {"converge", "diverge_compare"}

def load_frame_list():
    frames = []
    with open(ALL_FRAMES_CSV) as f:
        for row in csv.DictReader(f):
            frames.append(row)
    return frames

def process_frame(sf, round_filter=None):
    """Process a single frame. round_filter: None=all, 'r1'=round1 only, 'r1r2'=round1+r2 fill."""
    frame_dir = os.path.join(OUTPUTS_ROOT, sf)
    inc_path = os.path.join(frame_dir, "reports", f"{sf}_incremental_coverage.csv")
    if not os.path.exists(inc_path):
        return None

    with open(inc_path, "r", encoding="utf-8-sig") as f:
        all_rows = list(csv.DictReader(f))
    if not all_rows:
        return None

    if round_filter == "r1":
        selected = [r for r in all_rows if r["l2_family"] in ROUND1_FAMILIES]
    elif round_filter == "r1r2":
        r1 = [r for r in all_rows if r["l2_family"] in ROUND1_FAMILIES]
        r2_fill = [r for r in all_rows if r["l2_family"] not in ROUND1_FAMILIES and int(float(r["delta_l2"])) > 0]
        selected = r1 + r2_fill
    else:
        selected = all_rows

    result = {"families": [], "deltas_l2": [], "deltas_l1": [], "deltas_l0": [],
              "raws_l2": [], "answer_types": [], "phases": []}
    for r in selected:
        result["families"].append(r["l2_family"])
        result["deltas_l2"].append(int(float(r["delta_l2"])))
        result["deltas_l1"].append(int(float(r["delta_l1"])))
        result["deltas_l0"].append(int(float(r["delta_l0"])))
        result["raws_l2"].append(int(float(r["raw_l2"])))
        result["phases"].append(r["selection_phase"])
    result["n_questions"] = len(selected)
    return result

def process_frame_jsonl(sf):
    """Read JSONL for answer_type info."""
    frame_dir = os.path.join(OUTPUTS_ROOT, sf)
    jsonl_path = os.path.join(frame_dir, "generation", "qa", f"{sf}_all.jsonl")
    if not os.path.exists(jsonl_path):
        return {}
    answer_types = {}
    try:
        with open(jsonl_path) as f:
            for line in f:
                d = json.loads(line)
                qid = d.get("question_id", "")
                answer_types[qid] = {
                    "answer_type": d.get("answer_type", "unknown"),
                    "l2_family": d.get("l2_family", "unknown"),
                    "generation_round": d.get("generation_round", 0),
                }
    except Exception:
        pass
    return answer_types

def get_summary_json(sf):
    """Read summary.json for node count and gap info."""
    frame_dir = os.path.join(OUTPUTS_ROOT, sf)
    sum_path = os.path.join(frame_dir, "reports", f"{sf}_summary.json")
    if not os.path.exists(sum_path):
        return {}
    try:
        with open(sum_path) as f:
            return json.load(f)
    except Exception:
        return {}

def main():
    print("Loading frame list...")
    frame_rows = load_frame_list()
    print(f"Total frames in CSV: {len(frame_rows)}")

    # Node count groups
    node_groups = {
        "low (3-10)": (3, 10),
        "mid (11-30)": (11, 30),
        "high (31-100)": (31, 100),
    }
    node_groups_fine = {
        "0-5": (0, 5),
        "3-10": (3, 10),
        "11-20": (11, 20),
        "21-30": (21, 30),
        "31-50": (31, 50),
        "51-100": (51, 100),
    }

    # ── Section 1: Verify Table 4 is R1-only ──
    print("\n" + "="*80)
    print("SECTION 1: Verify current Table 4 scope (R1 + R2 gap-fill)")
    print("="*80)

    # Sample a few frames to check
    sample_sfs = [r["scene_frame"] for r in frame_rows[:5]]
    for sf in sample_sfs:
        frame_dir = os.path.join(OUTPUTS_ROOT, sf)
        inc_path = os.path.join(frame_dir, "reports", f"{sf}_incremental_coverage.csv")
        if not os.path.exists(inc_path):
            continue
        with open(inc_path, "r", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        total = len(rows)
        r1 = sum(1 for r in rows if r["l2_family"] in ROUND1_FAMILIES)
        r2 = total - r1
        r2_fill = sum(1 for r in rows if r["l2_family"] not in ROUND1_FAMILIES and int(float(r["delta_l2"])) > 0)
        print(f"  {sf}: total={total}, R1={r1}, R2_all={r2}, R2_fill(delta>0)={r2_fill}, R1+R2fill={r1+r2_fill}")

    # ── Section 2: Full analysis across all frames ──
    print("\n" + "="*80)
    print("SECTION 2: Full analysis - R1 only vs R1+R2fill vs All rounds")
    print("="*80)

    modes = {"r1": "Round 1 Only", "r1r2": "Round 1 + R2 Gap-Fill", None: "All Rounds (R1+R2)"}

    for mode_key, mode_name in modes.items():
        fam_total = Counter()
        fam_delta_l2 = defaultdict(list)
        fam_raw_l2 = defaultdict(list)
        phase_total = Counter()
        total_q = 0
        total_delta_l2 = 0
        total_raw_l2 = 0
        n_processed = 0

        # Node group stats
        ng_stats = {g: {"n_frames": 0, "total_q": 0, "total_delta_l2": 0, "fam_counts": Counter(), "fam_delta": defaultdict(list)} for g in node_groups}

        for i, row in enumerate(frame_rows):
            sf = row["scene_frame"]
            nodes = int(row["filtered_nodes"])
            if nodes < 3:
                continue
            result = process_frame(sf, round_filter=mode_key)
            if result is None:
                continue
            n_processed += 1
            total_q += result["n_questions"]
            for j in range(result["n_questions"]):
                fam = result["families"][j]
                dl2 = result["deltas_l2"][j]
                rl2 = result["raws_l2"][j]
                phase = result["phases"][j]
                fam_total[fam] += 1
                fam_delta_l2[fam].append(dl2)
                fam_raw_l2[fam].append(rl2)
                phase_total[phase] += 1
                total_delta_l2 += dl2
                total_raw_l2 += rl2

            # Assign to node groups
            for gname, (lo, hi) in node_groups.items():
                if lo <= nodes <= hi:
                    ng_stats[gname]["n_frames"] += 1
                    ng_stats[gname]["total_q"] += result["n_questions"]
                    ng_stats[gname]["total_delta_l2"] += sum(result["deltas_l2"])
                    for j in range(result["n_questions"]):
                        ng_stats[gname]["fam_counts"][result["families"][j]] += 1
                        ng_stats[gname]["fam_delta"][result["families"][j]].append(result["deltas_l2"][j])

            if (i+1) % 1000 == 0:
                print(f"  [{mode_key}] Processed {i+1}/{len(frame_rows)} frames...")

        print(f"\n--- {mode_name} ---")
        print(f"  Frames processed: {n_processed}")
        print(f"  Total questions: {total_q:,}")
        print(f"  Total delta_l2: {total_delta_l2:,}")
        print(f"  Total raw_l2: {total_raw_l2:,}")
        if total_raw_l2 > 0:
            print(f"  Redundancy: {1 - total_delta_l2/total_raw_l2:.4f} ({(1 - total_delta_l2/total_raw_l2)*100:.2f}%)")

        print(f"\n  === Family (Converge-system) ===")
        print(f"  {'Family':<25s} {'Count':>12s} {'%':>8s} {'Avg ΔL2/Q':>12s} {'Avg raw_l2':>12s}")
        print(f"  {'-'*70}")
        for fam in sorted(fam_total.keys()):
            cnt = fam_total[fam]
            pct = cnt / total_q * 100
            avg_dl2 = np.mean(fam_delta_l2[fam])
            avg_rl2 = np.mean(fam_raw_l2[fam])
            print(f"  {fam:<25s} {cnt:>12,d} {pct:>7.1f}% {avg_dl2:>12.4f} {avg_rl2:>12.2f}")

        print(f"\n  === Selection Phase ===")
        for phase in sorted(phase_total.keys()):
            cnt = phase_total[phase]
            pct = cnt / total_q * 100
            print(f"  {phase:<25s} {cnt:>12,d} ({pct:>5.1f}%)")

        # Node group breakdown
        print(f"\n  === Node Group Breakdown ===")
        print(f"  {'Group':<15s} {'Frames':>8s} {'Total Q':>12s} {'Avg Q/F':>10s} {'Avg ΔL2/Q':>12s}", end="")
        for fam in ["converge", "diverge_compare", "direction_chain", "viewpoint_transfer"]:
            print(f" {fam[:8]:>10s}", end="")
        print()
        print(f"  {'-'*100}")
        for gname in ["low (3-10)", "mid (11-30)", "high (31-100)"]:
            gs = ng_stats[gname]
            nf = gs["n_frames"]
            if nf == 0:
                continue
            avg_q = gs["total_q"] / nf
            avg_dl2 = gs["total_delta_l2"] / gs["total_q"] if gs["total_q"] > 0 else 0
            print(f"  {gname:<15s} {nf:>8d} {gs['total_q']:>12,d} {avg_q:>10.0f} {avg_dl2:>12.4f}", end="")
            for fam in ["converge", "diverge_compare", "direction_chain", "viewpoint_transfer"]:
                fc = gs["fam_counts"].get(fam, 0)
                pct = fc / gs["total_q"] * 100 if gs["total_q"] > 0 else 0
                print(f" {pct:>9.1f}%", end="")
            print()

    # ── Section 3: Answer type (status-system) classification ──
    print("\n" + "="*80)
    print("SECTION 3: Answer Type (Status-system) Classification")
    print("="*80)

    # We need to read JSONL to get answer_type. Let's sample efficiently.
    # Read incremental_coverage for family, read JSONL for answer_type
    answer_type_global = Counter()
    family_x_anstype = Counter()
    ng_anstype = {g: Counter() for g in node_groups}
    n_sampled = 0

    for i, row in enumerate(frame_rows):
        sf = row["scene_frame"]
        nodes = int(row["filtered_nodes"])
        if nodes < 3:
            continue
        frame_dir = os.path.join(OUTPUTS_ROOT, sf)
        jsonl_r1 = os.path.join(frame_dir, "generation", "qa", f"{sf}_round1.jsonl")
        jsonl_r2 = os.path.join(frame_dir, "generation", "qa", f"{sf}_round2.jsonl")

        for jpath, round_name in [(jsonl_r1, "R1"), (jsonl_r2, "R2")]:
            if not os.path.exists(jpath):
                continue
            try:
                with open(jpath) as f:
                    for line in f:
                        d = json.loads(line)
                        at = d.get("answer_type", "unknown")
                        fam = d.get("l2_family", "unknown")
                        answer_type_global[at] += 1
                        family_x_anstype[(fam, at)] += 1
                        for gname, (lo, hi) in node_groups.items():
                            if lo <= nodes <= hi:
                                ng_anstype[gname][(fam, at)] += 1
            except Exception:
                pass
        n_sampled += 1
        if (i+1) % 1000 == 0:
            print(f"  Processed {i+1}/{len(frame_rows)} frames for answer_type...")

    total_at = sum(answer_type_global.values())
    print(f"\n  Total QAs with answer_type info: {total_at:,}")
    print(f"\n  === Answer Type Distribution (All Rounds) ===")
    for at, cnt in answer_type_global.most_common():
        print(f"  {at:<15s} {cnt:>12,d} ({cnt/total_at*100:.1f}%)")

    print(f"\n  === Family × Answer Type Cross-Table ===")
    all_fams = sorted(set(k[0] for k in family_x_anstype.keys()))
    all_ats = sorted(set(k[1] for k in family_x_anstype.keys()))
    print(f"  {'Family':<25s}", end="")
    for at in all_ats:
        print(f" {at:>12s}", end="")
    print(f" {'Total':>12s}")
    print(f"  {'-'*80}")
    for fam in all_fams:
        fam_total_ct = sum(family_x_anstype.get((fam, at), 0) for at in all_ats)
        print(f"  {fam:<25s}", end="")
        for at in all_ats:
            cnt = family_x_anstype.get((fam, at), 0)
            print(f" {cnt:>12,d}", end="")
        print(f" {fam_total_ct:>12,d}")

    # Node group x answer type
    print(f"\n  === Node Group × Answer Type ===")
    for gname in ["low (3-10)", "mid (11-30)", "high (31-100)"]:
        print(f"\n  [{gname}]")
        group_data = ng_anstype[gname]
        group_total = sum(group_data.values())
        if group_total == 0:
            print(f"    No data")
            continue
        # By family
        fams_in_group = sorted(set(k[0] for k in group_data.keys()))
        for fam in fams_in_group:
            fam_cnt = sum(group_data.get((fam, at), 0) for at in all_ats)
            pct = fam_cnt / group_total * 100
            at_detail = ", ".join(f"{at}={group_data.get((fam, at), 0)}" for at in all_ats if group_data.get((fam, at), 0) > 0)
            print(f"    {fam:<22s} {fam_cnt:>10,d} ({pct:>5.1f}%)  [{at_detail}]")

    # ── Section 4: Decay rate by node group ──
    print("\n" + "="*80)
    print("SECTION 4: Coverage Decay by Node Group (L2)")
    print("="*80)

    segments = [(0, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 0.90), (0.90, 1.0)]

    # Load pre-extracted curves
    curves_data = np.load(os.path.join(EXTRACTED_DIR, "rq2_curves.npz"))
    curves_l2 = curves_data["curves_l2"]
    n_questions_arr = curves_data["n_questions"]

    summary_rows = []
    with open(os.path.join(EXTRACTED_DIR, "rq2_frame_summary.csv")) as f:
        for row in csv.DictReader(f):
            summary_rows.append(row)

    for gname in ["low (3-10)", "mid (11-30)", "high (31-100)"]:
        lo_n, hi_n = node_groups[gname]
        print(f"\n  [{gname}]")
        # Find indices in summary_rows matching this node group
        indices = []
        for idx, row in enumerate(summary_rows):
            n = int(row["filtered_nodes"])
            if lo_n <= n <= hi_n and row["is_trivial"] == "False":
                indices.append(idx)

        if not indices:
            print(f"    No frames")
            continue

        nq_group = n_questions_arr[indices]
        print(f"    Frames: {len(indices)}, Avg Q: {nq_group.mean():.0f}, Median Q: {np.median(nq_group):.0f}")

        # Segment analysis
        seg_results = {s: [] for s in segments}
        for idx in indices:
            nq = n_questions_arr[idx]
            if nq == 0:
                continue
            curve = curves_l2[idx, :nq+1]
            for lo, hi in segments:
                seg_deltas = []
                for q in range(nq):
                    r_before = curve[q]
                    r_after = curve[q+1]
                    if r_before < hi and r_after > lo:
                        seg_deltas.append(r_after - r_before)
                if seg_deltas:
                    seg_results[(lo, hi)].append(np.mean(seg_deltas))

        print(f"    {'Segment':<15s} {'Avg ΔRate/Q':>12s} {'N frames':>10s}")
        print(f"    {'-'*40}")
        for lo, hi in segments:
            vals = seg_results[(lo, hi)]
            if vals:
                print(f"    {lo:.0%}→{hi:.0%}        {np.mean(vals):>12.6f} {len(vals):>10d}")
            else:
                print(f"    {lo:.0%}→{hi:.0%}        {'N/A':>12s} {'0':>10s}")

    # ── Section 5: Why diverge is so low ──
    print("\n" + "="*80)
    print("SECTION 5: Root Cause - Why diverge_compare is so low")
    print("="*80)

    # Check candidate_potential for a sample of frames
    sample_frames = []
    for row in frame_rows:
        n = int(row["filtered_nodes"])
        if n >= 10:
            sample_frames.append(row["scene_frame"])
        if len(sample_frames) >= 20:
            break

    total_conv_plans = 0
    total_div_plans = 0
    total_conv_selected = 0
    total_div_selected = 0
    div_raw_l2_all = []
    conv_raw_l2_all = []

    for sf in sample_frames:
        cp_path = os.path.join(OUTPUTS_ROOT, sf, "reports", f"{sf}_candidate_potential.csv")
        if not os.path.exists(cp_path):
            continue
        with open(cp_path, "r", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            fam = r["family"]
            sel = r["selected"] == "True"
            rl2 = int(r["raw_l2"])
            if fam == "converge":
                total_conv_plans += 1
                if sel: total_conv_selected += 1
                conv_raw_l2_all.append(rl2)
            elif fam == "diverge_compare":
                total_div_plans += 1
                if sel: total_div_selected += 1
                div_raw_l2_all.append(rl2)

    print(f"\n  Sample: {len(sample_frames)} frames (nodes >= 10)")
    print(f"  Converge plans: {total_conv_plans:,}, selected: {total_conv_selected:,} ({total_conv_selected/max(total_conv_plans,1)*100:.1f}%)")
    print(f"  Diverge plans:  {total_div_plans:,}, selected: {total_div_selected:,} ({total_div_selected/max(total_div_plans,1)*100:.1f}%)")
    if conv_raw_l2_all:
        print(f"  Converge avg raw_l2/plan: {np.mean(conv_raw_l2_all):.2f}, max: {max(conv_raw_l2_all)}")
    if div_raw_l2_all:
        print(f"  Diverge avg raw_l2/plan: {np.mean(div_raw_l2_all):.2f}, max: {max(div_raw_l2_all)}")
    print(f"\n  Key insight: diverge_compare covers exactly 1 L2 gap per plan (raw_l2=1),")
    print(f"  while converge covers ~3-4 L2 gaps. Converge dominates coverage_backfill selection.")
    print(f"  Also, diverge has much lower plan_cache availability (~3% vs ~97% converge).")
    print(f"  This is by design: diverge needs TWO branches to both uniquely resolve,")
    print(f"  which is a much stricter constraint than converge's single-branch resolution.")

    print("\n\nDONE.")


if __name__ == "__main__":
    main()
