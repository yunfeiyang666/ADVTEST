#!/usr/bin/env python3
"""Fixed Phase 2: Generate all D1-D16 plots and markdown report.

Key fixes:
- D2/D16: Use extracted_v2_r1 npz curves (reaches 100%) instead of raw CSV (caps at 50%)
- D4: Use extracted_v2_r1 n_questions as Q_to_100%
- D6: Correct R1 coverage denominator (actual reachable gaps = total_gaps/2)
"""
import os, sys, pickle, json, math, csv
from collections import defaultdict, Counter
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rq2_analysis_config import *

sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)

def compute_auc(x, y):
    if len(x) < 2: return 0.0
    xn = (x - x[0]) / (x[-1] - x[0]) if x[-1] != x[0] else x
    return float(np.trapz(y, xn))

def main():
    print("=== Fixed Phase 2: Full D1-D16 Report ===")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load HDD cache
    cache_path = PLOTS_DIR / "rq2_frame_cache.pkl"
    if not cache_path.exists():
        print("ERROR: Run rq2_phase1_collect.py first"); return
    with open(cache_path, "rb") as f:
        frame_data = pickle.load(f)
    print(f"Loaded {len(frame_data)} frames from cache.")

    # Load extracted npz (R1+R2 gap-fill, reaches 100%)
    r1_npz = np.load(str(EXTRACTED_R1 / "rq2_curves.npz"))
    r1_curves_l0 = r1_npz["curves_l0"]
    r1_curves_l1 = r1_npz["curves_l1"]
    r1_curves_l2 = r1_npz["curves_l2"]
    r1_nq = r1_npz["n_questions"]

    r1_summary = []
    with open(str(EXTRACTED_R1 / "rq2_frame_summary.csv")) as f:
        for row in csv.DictReader(f): r1_summary.append(row)
    print(f"R1 npz: {r1_curves_l2.shape}, summary: {len(r1_summary)} rows")

    # Helpers
    def get_group_fd(gspec):
        return [fd for fd in frame_data if gspec["min"] <= fd["nodes"] <= gspec["max"]]
    def get_group_idx(gspec):
        return [i for i, r in enumerate(r1_summary) if gspec["min"] <= int(r["filtered_nodes"]) <= gspec["max"]]

    md = ["# RQ2 Comprehensive Analysis Report (Fixed)", "",
          "> Generated: 2026-05-18", "> Scope: 5767 valid frames, S/M/L/All groups",
          "> Coverage scope: R1 + R2_backfill (reaches 100% L2)", ""]

    # ═══ D1: Coverage Curves + AUC ═══════════════════════════════════════
    print("D1: Coverage Curves...")
    md += ["## D1: Coverage Curves & AUC", ""]
    n_pts = 200
    x_norm = np.linspace(0, 1, n_pts)

    for gname, gspec in GROUPS.items():
        valid_idx = [i for i in get_group_idx(gspec) if r1_nq[i] > 0]
        if not valid_idx: continue

        fig, axes = plt.subplots(1, 3, figsize=(FIG_W_DOUBLE, 2.5), sharey=True)
        levels = [("L0", r1_curves_l0, COLORS["L0"]),
                  ("L1", r1_curves_l1, COLORS["L1"]),
                  ("L2", r1_curves_l2, COLORS["L2"])]
        aucs = []
        for ax, (lbl, curves, color) in zip(axes, levels):
            interp = np.zeros((len(valid_idx), n_pts))
            for k, idx in enumerate(valid_idx):
                nq = r1_nq[idx]
                interp[k] = np.interp(x_norm, np.linspace(0,1,nq+1), curves[idx,:nq+1])
            avg = interp.mean(axis=0)
            std = interp.std(axis=0)
            auc = compute_auc(x_norm, avg)
            aucs.append(auc)
            ax.plot(x_norm*100, avg, color=color, lw=2)
            ax.fill_between(x_norm*100, np.clip(avg-std,0,1), np.clip(avg+std,0,1), alpha=0.15, color=color)
            ax.set_title(f"{lbl} (AUC={auc:.3f})")
            ax.set_xlabel("Budget (%)")
            ax.set_xlim(0,100); ax.set_ylim(-0.05,1.05)
            if ax == axes[0]: ax.set_ylabel("Coverage")
        fig.suptitle(f"{gname} (N={len(valid_idx)})", y=1.02)
        fname = f"D1_curves_{gname.replace('(','').replace(')','').replace('≥','ge')}.png"
        fig.savefig(OUT_DIR / fname, bbox_inches='tight'); plt.close(fig)
        md.append(f"**{gname}** (N={len(valid_idx)}): AUC L0={aucs[0]:.3f}, L1={aucs[1]:.3f}, L2={aucs[2]:.3f}")
        md.append(f"![{gname}]({fname})"); md.append("")

    # ═══ D2: Coverage Decay (from npz curves) ════════════════════════════
    print("D2: Coverage Decay...")
    md += ["## D2: Coverage Decay (ΔL2/Q by segment)", "Using R1+R2_backfill curves (reaches 100%).", ""]
    segments = [(0,0.25),(0.25,0.50),(0.50,0.75),(0.75,0.90),(0.90,1.0)]

    fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.8))
    bar_w = 0.22
    x_pos_base = np.arange(len(segments))
    group_list = [g for g in GROUPS if g != "All(≥3)"]

    table_d2 = ["| Segment | " + " | ".join(group_list) + " |",
                "|---------|" + "|".join(["---"]*len(group_list)) + "|"]

    for gi, gname in enumerate(group_list):
        valid_idx = [i for i in get_group_idx(GROUPS[gname]) if r1_nq[i] > 0]
        y_vals = []
        for s_start, s_end in segments:
            seg_deltas = []
            for idx in valid_idx:
                nq = r1_nq[idx]
                curve = r1_curves_l2[idx, :nq+1]
                deltas = np.diff(curve)
                mask = (curve[:-1] >= s_start) & (curve[:-1] < s_end)
                if mask.any():
                    seg_deltas.append(deltas[mask].mean())
            y_vals.append(np.mean(seg_deltas) if seg_deltas else 0)
        ax.bar(x_pos_base + gi*bar_w, y_vals, bar_w, label=gname, color=COLORS[gname])

    # Build table rows
    for si, (s_start, s_end) in enumerate(segments):
        row_vals = []
        for gname in group_list:
            valid_idx = [i for i in get_group_idx(GROUPS[gname]) if r1_nq[i] > 0]
            seg_deltas = []
            for idx in valid_idx:
                nq = r1_nq[idx]
                curve = r1_curves_l2[idx, :nq+1]
                deltas = np.diff(curve)
                mask = (curve[:-1] >= s_start) & (curve[:-1] < s_end)
                if mask.any():
                    seg_deltas.append(deltas[mask].mean())
            row_vals.append(f"{np.mean(seg_deltas):.6f}" if seg_deltas else "N/A")
        table_d2.append(f"| {s_start*100:.0f}%-{s_end*100:.0f}% | " + " | ".join(row_vals) + " |")

    ax.set_xticks(x_pos_base + bar_w)
    ax.set_xticklabels([f"{s[0]*100:.0f}-{s[1]*100:.0f}%" for s in segments])
    ax.set_ylabel("Avg ΔL2 per Q"); ax.legend()
    fig.savefig(OUT_DIR / "D2_decay.png", bbox_inches='tight'); plt.close(fig)
    md += table_d2 + ["", "![Decay](D2_decay.png)", ""]

    # ═══ D3: Question Type Distribution ══════════════════════════════════
    print("D3: Question Type...")
    md += ["## D3: Question Type Distribution (Full R1+R2)", ""]
    table = ["| Group | converge | dir_chain | dist_chain | viewpoint | diverge | Total |",
             "|-------|----------|-----------|------------|-----------|---------|-------|"]
    for gname, gspec in GROUPS.items():
        gf = get_group_fd(gspec)
        if not gf: continue
        fam = Counter()
        for fd in gf: fam += Counter(fd["families"])
        tot = sum(fam.values())
        if tot == 0: continue
        table.append(f"| **{gname}** | {fam.get('converge',0)/tot*100:.1f}% | {fam.get('direction_chain',0)/tot*100:.1f}% | {fam.get('distance_chain',0)/tot*100:.1f}% | {fam.get('viewpoint_transfer',0)/tot*100:.1f}% | {fam.get('diverge_compare',0)/tot*100:.2f}% | {tot:,} |")
    md += table + [""]

    # Build lookup dict for D4
    fd_by_sf = {fd["sf"]: fd for fd in frame_data}

    # ═══ D4: Compression Ratio (from npz n_questions) ════════════════════
    print("D4: Compression...")
    md += ["## D4: Compression Ratio", "Q_to_100% / total_L2_gaps (lower = more efficient)", ""]
    table = ["| Group | Median | Mean | P25 | P75 |", "|-------|--------|------|-----|-----|"]
    fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
    box_data = []; box_labels = []
    for gname, gspec in GROUPS.items():
        indices = get_group_idx(gspec)
        ratios = []
        for idx in indices:
            nq = r1_nq[idx]
            sf_name = r1_summary[idx]["scene_frame"]
            fd_match = fd_by_sf.get(sf_name)
            gaps = fd_match["total_gaps"] if fd_match else 0
            if nq > 0 and gaps > 0:
                ratios.append(nq / gaps)
        if ratios:
            table.append(f"| **{gname}** | {np.median(ratios):.3f} | {np.mean(ratios):.3f} | {np.percentile(ratios,25):.3f} | {np.percentile(ratios,75):.3f} |")
            if gname != "All(≥3)":
                box_data.append(ratios); box_labels.append(gname)
    if box_data:
        ax.boxplot(box_data, labels=box_labels)
        ax.set_ylabel("Q_to_100% / total_gaps")
        fig.savefig(OUT_DIR / "D4_compression.png", bbox_inches='tight')
    plt.close(fig)
    md += table + ["", "![Compression](D4_compression.png)", ""]

    # ═══ D5: Initial Coverage ═════════════════════════════════════════════
    print("D5: Initial Coverage...")
    md += ["## D5: Initial Coverage Distribution", ""]
    fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
    idx_all = [i for i in range(len(r1_summary)) if int(r1_summary[i]["filtered_nodes"]) >= 3]
    bdata = [r1_curves_l0[idx_all,0]*100, r1_curves_l1[idx_all,0]*100, r1_curves_l2[idx_all,0]*100]
    bp = ax.boxplot(bdata, patch_artist=True, labels=["L0","L1","L2"])
    for patch, c in zip(bp['boxes'], [COLORS["L0"],COLORS["L1"],COLORS["L2"]]):
        patch.set_facecolor(c); patch.set_alpha(0.6)
    ax.set_ylabel("Initial Coverage (%)")
    fig.savefig(OUT_DIR / "D5_initial_cov.png", bbox_inches='tight'); plt.close(fig)

    table = ["| Group | Init L0 | Init L1 | Init L2 |", "|-------|---------|---------|---------|"]
    for gname, gspec in GROUPS.items():
        idx = get_group_idx(gspec)
        if not idx: continue
        table.append(f"| **{gname}** | {r1_curves_l0[idx,0].mean():.1%} | {r1_curves_l1[idx,0].mean():.1%} | {r1_curves_l2[idx,0].mean():.1%} |")
    md += table + ["", "![Init Cov](D5_initial_cov.png)", ""]

    # ═══ D6: R1 vs R2 Contribution (fixed denominator) ═══════════════════
    print("D6: R1 vs R2...")
    md += ["## D6: R1 vs R2 Contribution", "R1 coverage uses actual reachable gaps as denominator.", ""]
    table = ["| Group | R1 avg Q | R2_fill avg Q | R1 ΔL2% | R1 end cov (corrected) |",
             "|-------|----------|---------------|---------|------------------------|"]
    fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
    for gname, gspec in GROUPS.items():
        gf = [fd for fd in get_group_fd(gspec) if fd["q_count"] > 0]
        if not gf: continue
        r1q = np.mean([fd["r1_count"] for fd in gf])
        r2q = np.mean([fd["r2_count"] for fd in gf])
        r1dl2 = [sum(fd["per_q_delta_l2"][:fd["r1_count"]]) for fd in gf]
        total_dl2 = [fd["delta_l2_total"] for fd in gf]
        r1_pct = np.sum(r1dl2) / np.sum(total_dl2) * 100 if np.sum(total_dl2) > 0 else 0
        # Corrected R1 end coverage: R1_delta_l2 / (total_gaps that R1+R2 actually cover)
        r1_cov_corrected = [r1dl2[i] / total_dl2[i] if total_dl2[i] > 0 else 0 for i in range(len(gf))]
        table.append(f"| **{gname}** | {r1q:.1f} | {r2q:.1f} | {r1_pct:.1f}% | {np.mean(r1_cov_corrected):.1%} |")
    md += table + [""]

    # ═══ D7: Scalability ══════════════════════════════════════════════════
    print("D7: Scalability...")
    md += ["## D7: Scalability (Q_to_100% vs Nodes)", ""]
    n_arr, q_arr = [], []
    for i, r in enumerate(r1_summary):
        n = int(r["filtered_nodes"]); q = r1_nq[i]
        if n >= 3 and q > 0: n_arr.append(n); q_arr.append(q)
    n_arr = np.array(n_arr, dtype=float); q_arr = np.array(q_arr, dtype=float)
    log_n = np.log10(n_arr); log_q = np.log10(q_arr)
    slope, intercept = np.polyfit(log_n, log_q, 1)
    r2 = 1 - np.sum((log_q-(slope*log_n+intercept))**2)/np.sum((log_q-log_q.mean())**2)

    fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 3))
    ax.scatter(n_arr, q_arr, alpha=0.08, s=2, c='gray')
    xl = np.linspace(n_arr.min(), n_arr.max(), 100)
    ax.plot(xl, 10**intercept * xl**slope, 'r--', lw=2, label=f"$Q \\propto N^{{{slope:.2f}}}$, $R^2$={r2:.3f}")
    ax.set_xscale('log'); ax.set_yscale('log')
    ax.set_xlabel("Nodes"); ax.set_ylabel("Q to 100%"); ax.legend()
    fig.savefig(OUT_DIR / "D7_scalability.png", bbox_inches='tight'); plt.close(fig)
    md += [f"**Fit**: Q = 10^{intercept:.2f} x N^{slope:.2f} (R²={r2:.4f})", "![Scalability](D7_scalability.png)", ""]

    # ═══ D8: Redundancy ══════════════════════════════════════════════════
    print("D8: Redundancy...")
    md += ["## D8: Redundancy (1 - ΣΔL2/Σraw_L2)", ""]
    fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
    table = ["| Group | Global | Per-frame mean | Per-frame median |", "|-------|--------|----------------|------------------|"]
    vals = []; labels = []
    for gname, gspec in GROUPS.items():
        gf = [fd for fd in get_group_fd(gspec) if fd["raw_l2_total"] > 0]
        if not gf: continue
        pf = [1-fd["delta_l2_total"]/fd["raw_l2_total"] for fd in gf]
        glob = 1 - sum(fd["delta_l2_total"] for fd in gf)/sum(fd["raw_l2_total"] for fd in gf)
        table.append(f"| **{gname}** | {glob:.1%} | {np.mean(pf):.1%} | {np.median(pf):.1%} |")
        if gname != "All(≥3)": vals.append([v*100 for v in pf]); labels.append(gname)
    if vals:
        ax.boxplot(vals, labels=labels); ax.set_ylabel("Redundancy (%)")
        fig.savefig(OUT_DIR / "D8_redundancy.png", bbox_inches='tight')
    plt.close(fig)
    md += table + ["", "![Redundancy](D8_redundancy.png)", ""]

    # ═══ D9: Timing ══════════════════════════════════════════════════════
    print("D9: Timing...")
    md += ["## D9: Timing (Pipeline Phase Breakdown)", ""]
    table = ["| Group | precompute_ms | plan_cache_ms | selection_ms | total_ms |",
             "|-------|---------------|---------------|--------------|----------|"]
    for gname, gspec in GROUPS.items():
        gf = [fd for fd in get_group_fd(gspec) if fd.get("pipeline_timing")]
        if not gf: continue
        pre = np.mean([fd["pipeline_timing"].get("precompute_ms",0) for fd in gf])
        plc = np.mean([fd["pipeline_timing"].get("plan_cache_ms",0) for fd in gf])
        sel = np.mean([fd["pipeline_timing"].get("selection_gen_ms",0) for fd in gf])
        tot = np.mean([fd["pipeline_timing"].get("total_ms",0) for fd in gf])
        table.append(f"| **{gname}** | {pre:.0f} | {plc:.0f} | {sel:.0f} | {tot:.0f} |")
    md += table + [""]

    # ═══ D10: Constraint Quality ═════════════════════════════════════════
    print("D10: Constraints...")
    md += ["## D10: Constraint Quality (R1 only)", ""]
    c_counts = []; c_types = Counter()
    for fd in frame_data:
        c_counts.extend(fd.get("constraint_counts", []))
        for k, v in fd.get("constraint_types", {}).items(): c_types[k] += v
    if c_counts:
        md.append(f"Avg constraints/Q: **{np.mean(c_counts):.2f}**")
        table = ["| Type | Count | % |", "|------|-------|---|"]
        tot = sum(c_types.values())
        for k, v in c_types.most_common(10):
            table.append(f"| {k} | {v:,} | {v/tot*100:.1f}% |")
        md += table
    md.append("")

    # ═══ D11: Ego Analysis ═══════════════════════════════════════════════
    print("D11: Ego...")
    md += ["## D11: Ego Analysis", "Questions involving the ego vehicle.", ""]
    table = ["| Group | Total Q (JSONL) | Ego Q | Ego % |", "|-------|-----------------|-------|-------|"]
    for gname, gspec in GROUPS.items():
        gf = get_group_fd(gspec)
        tot = sum(fd.get("total_gap_from_jsonl",0) for fd in gf)
        ego = sum(fd.get("ego_gap_count",0) for fd in gf)
        if tot > 0: table.append(f"| **{gname}** | {tot:,} | {ego:,} | {ego/tot*100:.1f}% |")
    md += table + [""]

    # ═══ D12: Graph Density ══════════════════════════════════════════════
    print("D12: Density...")
    md += ["## D12: Graph Density", "Complete graph: edges = N*(N-1) directed pairs.", ""]
    table = ["| Group | Avg N | Avg Gaps | Gaps/N | Gaps/N² |", "|-------|-------|----------|--------|---------|"]
    for gname, gspec in GROUPS.items():
        gf = get_group_fd(gspec)
        if not gf: continue
        ns = np.array([fd["nodes"] for fd in gf], dtype=float)
        gs = np.array([fd["total_gaps"] for fd in gf], dtype=float)
        table.append(f"| **{gname}** | {ns.mean():.1f} | {gs.mean():.0f} | {(gs/ns).mean():.1f} | {(gs/ns**2).mean():.3f} |")
    md += table + [""]

    # ═══ D13: Answer Distribution ════════════════════════════════════════
    print("D13: Answers...")
    md += ["## D13: Answer Type Distribution", ""]
    ans = Counter()
    for fd in frame_data: ans += Counter(fd.get("answer_types", {}))
    table = ["| Type | Count | % |", "|------|-------|---|"]
    tot = sum(ans.values())
    if tot > 0:
        for k, v in ans.most_common():
            table.append(f"| {k} | {v:,} | {v/tot*100:.1f}% |")
    md += table + [""]

    # ═══ D14: Candidate Filtering ════════════════════════════════════════
    print("D14: Candidates...")
    md += ["## D14: Candidate Filtering", ""]
    cb = []; ca = []
    for fd in frame_data:
        cb.extend(fd.get("cand_before_list", []))
        ca.extend(fd.get("cand_after_list", []))
    if cb and sum(cb) > 0:
        md.append(f"- Avg before: {np.mean(cb):.1f}, Avg after: {np.mean(ca):.1f}")
        md.append(f"- Reduction: {(1-sum(ca)/sum(cb))*100:.1f}%")
    else:
        md.append("Note: candidate_before/after = 0 in JSONL (constraints applied in plan_cache phase, not per-question).")
    md.append("")

    # ═══ D15: Cross-frame Overlap ════════════════════════════════════════
    print("D15: Cross-frame...")
    md += ["## D15: Cross-frame Gap Overlap", ""]
    scene_gaps = defaultdict(list)
    for fd in frame_data:
        gp = fd.get("gap_patterns", set())
        if gp: scene_gaps[fd["scene_name"]].append(gp)
    overlaps = []
    for scn, fsets in scene_gaps.items():
        if len(fsets) > 1:
            union = set().union(*fsets)
            if union:
                overlaps.append(np.mean([len(fs)/len(union) for fs in fsets]))
    if overlaps:
        md.append(f"Avg frame coverage of scene gap union: **{np.mean(overlaps):.1%}**")
        md.append(f"(Each frame covers ~{np.mean(overlaps)*100:.1f}% of its scene's unique gaps)")
    md.append("")

    # ═══ D16: Coverage Saturation (from npz) ═════════════════════════════
    print("D16: Saturation...")
    md += ["## D16: Coverage Saturation (95%→100% tail cost)", "Using R1+R2_backfill curves.", ""]
    fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
    table = ["| Group | Avg Q_to_95% | Avg Q_95%→100% | Tail % |", "|-------|--------------|----------------|--------|"]
    bar_vals = []; bar_labels = []

    for gname, gspec in GROUPS.items():
        valid_idx = [i for i in get_group_idx(gspec) if r1_nq[i] > 0]
        if not valid_idx: continue
        tails = []; totals = []; q95s = []
        for idx in valid_idx:
            nq = r1_nq[idx]
            curve = r1_curves_l2[idx, :nq+1]
            q95 = int(np.searchsorted(curve, 0.95))
            tails.append(nq - q95)
            totals.append(nq)
            q95s.append(q95)
        avg_q95 = np.mean(q95s)
        avg_tail = np.mean(tails)
        avg_tot = np.mean(totals)
        pct = avg_tail / avg_tot * 100 if avg_tot > 0 else 0
        table.append(f"| **{gname}** | {avg_q95:.0f} | {avg_tail:.0f} | {pct:.1f}% |")
        if gname != "All(≥3)":
            bar_vals.append(pct); bar_labels.append(gname)

    if bar_vals:
        ax.bar(bar_labels, bar_vals, color=[COLORS[g] for g in bar_labels])
        ax.set_ylabel("Tail Cost (%)")
        fig.savefig(OUT_DIR / "D16_saturation.png", bbox_inches='tight')
    plt.close(fig)
    md += table + ["", "![Saturation](D16_saturation.png)", ""]

    # ═══ Write final report ══════════════════════════════════════════════
    report_path = OUT_DIR / "rq2_report.md"
    with open(report_path, "w") as f:
        f.write("\n".join(md))
    print(f"\nReport saved: {report_path}")
    print("DONE")

if __name__ == "__main__":
    main()
