"""Phase 2 part 2: Generate plots and markdown report for D3-D9."""
import os, sys, pickle, json, math
from collections import defaultdict, Counter
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rq2_analysis_config import *

sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)

def main():
    print("=== Phase 2 Part 2: Generating Report ===")
    
    cache_path = PLOTS_DIR / "rq2_frame_cache.pkl"
    with open(cache_path, "rb") as f:
        frame_data = pickle.load(f)

    # Load existing MD
    md_path = OUT_DIR / "rq2_report.md"
    md_lines = []
    if md_path.exists():
        with open(md_path) as f:
            md_lines = f.read().splitlines()

    def get_group_fd(gspec):
        return [fd for fd in frame_data if gspec["min"] <= fd["nodes"] <= gspec["max"]]

    # ══════════════════════════════════════════════════════════════════════
    # D3: Question Type Distribution
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D3: Question Type Distribution...")
    md_lines.extend(["## D3: Question Type Distribution", ""])
    
    table = ["| Group | " + " | ".join(ALL_FAMILIES) + " | Total Q |",
             "|-------|" + "|".join(["---"]*len(ALL_FAMILIES)) + "|---------|"]
    
    # Collect data for chart
    d3_chart_data = {}  # gname -> {fam: count}
    for gname, gspec in GROUPS.items():
        gframes = get_group_fd(gspec)
        if not gframes: continue
        g_fam = Counter()
        for fd in gframes:
            for k, v in fd["families"].items():
                g_fam[k] += v
        total = sum(g_fam.values())
        if total == 0: continue
        d3_chart_data[gname] = {fam: g_fam.get(fam, 0) for fam in ALL_FAMILIES}
        
        row = [f"**{gname}**"]
        for fam in ALL_FAMILIES:
            cnt = g_fam.get(fam, 0)
            row.append(f"{cnt:,} ({cnt/total*100:.1f}%)")
        row.append(f"{total:,}")
        table.append("| " + " | ".join(row) + " |")
        
    md_lines.extend(table)
    md_lines.append("")
    
    # D3 Chart: stacked bar chart for S/M/L
    if d3_chart_data:
        fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 3))
        chart_groups = [g for g in ["S(3-15)", "M(16-30)", "L(≥31)"] if g in d3_chart_data]
        x = np.arange(len(chart_groups))
        bottom = np.zeros(len(chart_groups))
        for fam in ALL_FAMILIES:
            totals = [sum(d3_chart_data[g].values()) for g in chart_groups]
            vals = [d3_chart_data[g].get(fam, 0) / t * 100 if t > 0 else 0 for g, t in zip(chart_groups, totals)]
            ax.bar(x, vals, 0.5, label=fam, bottom=bottom, color=COLORS.get(fam, '#888'))
            bottom += np.array(vals)
        ax.set_xticks(x)
        ax.set_xticklabels(chart_groups)
        ax.set_ylabel("Percentage (%)")
        ax.set_title("Question Type Distribution by Group")
        ax.legend(fontsize=6, loc='upper right')
        fig.savefig(OUT_DIR / "D3_type_dist.png")
        plt.close(fig)
        md_lines.append("![Question Type Distribution](D3_type_dist.png)")
        md_lines.append("")

    # ══════════════════════════════════════════════════════════════════════
    # D4: Compression Ratio
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D4: Compression Ratio...")
    md_lines.extend(["## D4: Compression Ratio",
                     "Q_to_100% / total_gaps — uses R1+R2_backfill scope (R1 all + R2 where ΔL2>0). Lower is better.", ""])
    
    # R1+R2_fill count: r1_count + number of R2 Qs with delta_l2 > 0
    # We can compute this from per_q_delta_l2: first r1_count items are R1, rest are R2
    # R2 fill = count of R2 items where delta > 0
    table = ["| Group | Scope | Median | Mean | P25 | P75 |", "|-------|-------|--------|------|-----|-----|"]
    d4_boxdata = {}
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in get_group_fd(gspec) if fd["total_gaps"] > 0]
        if not gframes: continue
        # Full scope
        ratios_full = [fd["q_count"] / fd["total_gaps"] for fd in gframes]
        # R1+R2_fill scope
        ratios_fill = []
        for fd in gframes:
            r1c = fd["r1_count"]
            r2_deltas = fd["per_q_delta_l2"][r1c:]
            r2_fill = sum(1 for d in r2_deltas if d > 0)
            q_fill = r1c + r2_fill
            ratios_fill.append(q_fill / fd["total_gaps"])
        table.append(f"| **{gname}** | R1+R2_fill | {np.median(ratios_fill):.3f} | {np.mean(ratios_fill):.3f} | {np.percentile(ratios_fill, 25):.3f} | {np.percentile(ratios_fill, 75):.3f} |")
        table.append(f"| {gname} | Full R1+R2 | {np.median(ratios_full):.3f} | {np.mean(ratios_full):.3f} | {np.percentile(ratios_full, 25):.3f} | {np.percentile(ratios_full, 75):.3f} |")
        if gname != "All(≥3)":
            d4_boxdata[gname] = ratios_fill
        
    md_lines.extend(table)
    md_lines.append("")
    
    # D4 Chart: box plot
    if d4_boxdata:
        fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
        labels = list(d4_boxdata.keys())
        data = [d4_boxdata[g] for g in labels]
        bplot = ax.boxplot(data, patch_artist=True, labels=labels, showfliers=False)
        for patch, g in zip(bplot['boxes'], labels):
            patch.set_facecolor(COLORS.get(g, '#888'))
            patch.set_alpha(0.6)
        ax.set_ylabel("Compression Ratio (Q_fill / total_gaps)")
        ax.set_title("Compression Ratio by Group")
        fig.savefig(OUT_DIR / "D4_compression.png")
        plt.close(fig)
        md_lines.append("![Compression Ratio](D4_compression.png)")
        md_lines.append("")

    # ════════════���═════════════════════════════════════════════════════════
    # D5: Initial Coverage Distribution (needs npz)
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D5: Initial Coverage Distribution...")
    r1_data = np.load(str(EXTRACTED_R1 / "rq2_curves.npz"))
    r1_summary = []
    with open(str(EXTRACTED_R1 / "rq2_frame_summary.csv")) as f:
        import csv
        for row in csv.DictReader(f): r1_summary.append(row)
        
    md_lines.extend(["## D5: Initial Coverage Distribution", ""])
    
    # Plot boxplot for All(>=3)
    idx_all = [i for i, r in enumerate(r1_summary) if int(r["filtered_nodes"]) >= 3]
    if idx_all:
        init_l0 = r1_data["curves_l0"][idx_all, 0] * 100
        init_l1 = r1_data["curves_l1"][idx_all, 0] * 100
        init_l2 = r1_data["curves_l2"][idx_all, 0] * 100
        
        fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
        bplot = ax.boxplot([init_l0, init_l1, init_l2], patch_artist=True, labels=["L0", "L1", "L2"])
        for patch, color in zip(bplot['boxes'], [COLORS["L0"], COLORS["L1"], COLORS["L2"]]):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        ax.set_ylabel("Initial Coverage (%)")
        fig.savefig(OUT_DIR / "D5_initial_cov.png")
        plt.close(fig)
        md_lines.append("![Initial Coverage](D5_initial_cov.png)")
    
    table = ["| Group | Init L0 (mean) | Init L1 (mean) | Init L2 (mean) |", "|-------|----------------|----------------|----------------|"]
    for gname, gspec in GROUPS.items():
        idx = [i for i, r in enumerate(r1_summary) if gspec["min"] <= int(r["filtered_nodes"]) <= gspec["max"]]
        if not idx: continue
        l0 = np.mean(r1_data["curves_l0"][idx, 0])
        l1 = np.mean(r1_data["curves_l1"][idx, 0])
        l2 = np.mean(r1_data["curves_l2"][idx, 0])
        table.append(f"| **{gname}** | {l0:.1%} | {l1:.1%} | {l2:.1%} |")
    md_lines.extend(table)
    md_lines.append("")

    # ══════════════════════════════════════════════════════════════════════
    # D6: R1 vs R2 contribution
    # ══════════════════════════════════════════════��═══════════════════════
    print("Generating D6: R1 vs R2 Contribution...")
    md_lines.extend(["## D6: R1 vs R2 Contribution", ""])
    table = ["| Group | R1 Q | R2 Q | R1 ΔL2 | R2 ΔL2 | R1 L2_cov_end | R1 ΔL2 % |", "|-------|------|------|--------|--------|---------------|----------|"]
    d6_data = {}
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in get_group_fd(gspec) if fd["q_count"] > 0]
        if not gframes: continue
        r1q = np.mean([fd["r1_count"] for fd in gframes])
        r2q = np.mean([fd["r2_count"] for fd in gframes])
        r1dl2 = np.mean([sum(fd["per_q_delta_l2"][:fd["r1_count"]]) for fd in gframes])
        r2dl2 = np.mean([fd["delta_l2_total"] - sum(fd["per_q_delta_l2"][:fd["r1_count"]]) for fd in gframes])
        r1cov = np.mean([fd["r1_end_cov_l2"] for fd in gframes])
        r1pct = r1dl2 / (r1dl2 + r2dl2) * 100 if (r1dl2+r2dl2) > 0 else 0
        table.append(f"| **{gname}** | {r1q:.1f} | {r2q:.1f} | {r1dl2:.1f} | {r2dl2:.1f} | {r1cov:.1%} | {r1pct:.1f}% |")
        if gname != "All(≥3)":
            d6_data[gname] = {"r1_q": r1q, "r2_q": r2q, "r1_dl2": r1dl2, "r2_dl2": r2dl2}
    md_lines.extend(table)
    md_lines.append("")
    
    # D6 Chart: stacked bar for R1 vs R2 ΔL2 contribution
    if d6_data:
        fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
        groups_d6 = list(d6_data.keys())
        x = np.arange(len(groups_d6))
        r1_vals = [d6_data[g]["r1_dl2"] for g in groups_d6]
        r2_vals = [d6_data[g]["r2_dl2"] for g in groups_d6]
        ax.bar(x, r1_vals, 0.5, label="R1 ΔL2", color="#1f77b4")
        ax.bar(x, r2_vals, 0.5, bottom=r1_vals, label="R2 ΔL2", color="#ff7f0e")
        ax.set_xticks(x)
        ax.set_xticklabels(groups_d6)
        ax.set_ylabel("Average ΔL2 per frame")
        ax.set_title("R1 vs R2 Coverage Contribution")
        ax.legend()
        fig.savefig(OUT_DIR / "D6_r1_vs_r2.png")
        plt.close(fig)
        md_lines.append("![R1 vs R2 Contribution](D6_r1_vs_r2.png)")
        md_lines.append("")

    # ═════════════════════════════════════════════════════════════════���════
    # D7: Scalability
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D7: Scalability...")
    md_lines.extend(["## D7: Scalability (Q_to_100% vs Nodes)", ""])
    
    n_arr, q_arr = [], []
    for i, r in enumerate(r1_summary):
        n = int(r["filtered_nodes"])
        q = r1_data["n_questions"][i]
        if n >= 3 and q > 0:
            n_arr.append(n)
            q_arr.append(q)
            
    if n_arr:
        n_arr = np.array(n_arr)
        q_arr = np.array(q_arr)
        log_n = np.log10(n_arr)
        log_q = np.log10(q_arr)
        slope, intercept = np.polyfit(log_n, log_q, 1)
        r2 = 1 - np.sum((log_q - (slope*log_n+intercept))**2) / np.sum((log_q - np.mean(log_q))**2)
        
        fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 3))
        ax.scatter(n_arr, q_arr, alpha=0.1, s=2)
        x_line = np.linspace(min(n_arr), max(n_arr), 100)
        y_line = 10**(intercept) * x_line**slope
        ax.plot(x_line, y_line, 'r--', lw=2, label=f"Fit: $Q \\propto N^{{{slope:.2f}}}$\n$R^2={r2:.3f}$")
        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_xlabel("Nodes (N)")
        ax.set_ylabel("Questions to 100% L2 (Q)")
        ax.legend()
        fig.savefig(OUT_DIR / "D7_scalability.png")
        plt.close(fig)
        
        md_lines.append(f"Log-log fit: **Q = 10^{intercept:.2f} × N^{slope:.2f}** (R² = {r2:.3f})")
        md_lines.append("![Scalability](D7_scalability.png)")
    md_lines.append("")

    # ══════════════════════════════════════════════════════════════════════
    # D8: Redundancy
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D8: Redundancy...")
    md_lines.extend(["## D8: Redundancy Analysis", "Redundancy = 1 - (ΣΔL2 / Σraw_L2). Higher = more overlapping coverage per Q.", ""])
    table = ["| Group | Global Redundancy | Per-frame Mean | Per-frame Median |", "|-------|-------------------|----------------|------------------|"]
    d8_data = {}
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in get_group_fd(gspec) if fd["raw_l2_total"] > 0]
        if not gframes: continue
        pf = [1 - fd["delta_l2_total"]/fd["raw_l2_total"] for fd in gframes]
        glob = 1 - sum(fd["delta_l2_total"] for fd in gframes) / sum(fd["raw_l2_total"] for fd in gframes)
        table.append(f"| **{gname}** | {glob:.1%} | {np.mean(pf):.1%} | {np.median(pf):.1%} |")
        if gname != "All(≥3)":
            d8_data[gname] = pf
    md_lines.extend(table)
    md_lines.append("")
    
    # D8 Chart: box plot of per-frame redundancy
    if d8_data:
        fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
        labels = list(d8_data.keys())
        data = [[v*100 for v in d8_data[g]] for g in labels]
        bplot = ax.boxplot(data, patch_artist=True, labels=labels, showfliers=False)
        for patch, g in zip(bplot['boxes'], labels):
            patch.set_facecolor(COLORS.get(g, '#888'))
            patch.set_alpha(0.6)
        ax.set_ylabel("Redundancy (%)")
        ax.set_title("Per-frame Redundancy Distribution")
        fig.savefig(OUT_DIR / "D8_redundancy.png")
        plt.close(fig)
        md_lines.append("![Redundancy](D8_redundancy.png)")
        md_lines.append("")

    # ═════════════════════════════���════════════════════════════════════════
    # D9: Timing (both phase-level breakdown and per-question distribution)
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D9: Timing...")
    md_lines.extend(["## D9: Timing", ""])
    
    # ── 9-global: Total dataset timing ──
    md_lines.append("### 9.1 Total Dataset Timing")
    md_lines.append("")
    total_q = sum(fd["q_count"] for fd in frame_data)
    total_r1 = sum(fd["r1_count"] for fd in frame_data)
    total_r2 = sum(fd["r2_count"] for fd in frame_data)
    total_time_ms = sum(fd["pipeline_timing"].get("total_ms", 0) for fd in frame_data if fd["pipeline_timing"])
    total_time_s = total_time_ms / 1000
    md_lines.append(f"- **Total frames**: {len(frame_data):,}")
    md_lines.append(f"- **Total questions generated**: {total_q:,} (R1={total_r1:,}, R2={total_r2:,})")
    md_lines.append(f"- **Total pipeline compute time**: {total_time_s:,.0f}s = **{total_time_s/3600:.1f}h**")
    md_lines.append(f"- **Aggregate throughput**: {total_q/total_time_s:,.0f} Q/s")
    md_lines.append(f"- **Generation backend**: `programmatic` (in-memory, `skip_cypher=True`)")
    md_lines.append("")
    
    # ── 9a: Phase-level breakdown ──
    md_lines.append("### 9.2 Per-Frame Pipeline Phases")
    md_lines.append("")
    md_lines.append("Each frame goes through 3 phases: **precompute** (scene graph indexing) → **plan_cache** (plan generation + in-memory pre-verification) → **selection_gen** (greedy set-cover + question serialization).")
    md_lines.append("")
    
    timing_key_candidates = [
        ("precompute_ms", "precompute_elapsed_ms", "precompute"),
        ("plan_cache_ms", "plan_cache_elapsed_ms", "plan_cache"),
        ("selection_gen_ms", "selection_gen_elapsed_ms", "selection", "selection_ms"),
        ("total_ms", "total_elapsed_ms", "total"),
    ]
    
    def get_timing(pt, key_list):
        for k in key_list:
            v = pt.get(k, None)
            if v is not None and v != 0:
                return float(v)
        return 0.0
    
    table = ["| Group | Phase | Mean | Median | P95 | Max | % of Total |",
             "|-------|-------|------|--------|-----|-----|------------|"]
    
    d9_stacked = {}  # for chart
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in get_group_fd(gspec) if fd["pipeline_timing"]]
        if not gframes: continue
        
        pre = [get_timing(fd["pipeline_timing"], timing_key_candidates[0]) for fd in gframes]
        plc = [get_timing(fd["pipeline_timing"], timing_key_candidates[1]) for fd in gframes]
        sel = [get_timing(fd["pipeline_timing"], timing_key_candidates[2]) for fd in gframes]
        tot = [get_timing(fd["pipeline_timing"], timing_key_candidates[3]) for fd in gframes]
        avg_tot = np.mean(tot)
        
        def fmt_ms(vals):
            m = np.mean(vals)
            if m >= 1000:
                return f"{m/1000:.2f}s"
            return f"{m:.1f}ms"
        
        def fmt_pct(vals, total):
            return f"{np.mean(vals)/total*100:.1f}%" if total > 0 else "-"
        
        for phase, vals, label in [("precompute", pre, "pre"), ("plan_cache", plc, "plan"), ("selection", sel, "sel"), ("total", tot, "total")]:
            table.append(f"| {'**'+gname+'**' if phase=='precompute' else ''} | {phase} | {fmt_ms(vals)} | {fmt_ms([np.median(vals)])} | {fmt_ms([np.percentile(vals,95)])} | {fmt_ms([np.max(vals)])} | {fmt_pct(vals, avg_tot)} |")
        table.append("|  |  |  |  |  |  |  |")
        
        if gname != "All(\u22653)":
            d9_stacked[gname] = {"pre": np.mean(pre), "plan": np.mean(plc), "sel": np.mean(sel)}
    
    md_lines.extend(table)
    md_lines.append("")
    
    # ── 9b: Throughput ──
    md_lines.append("### 9.3 Throughput (Questions per Second)")
    md_lines.append("")
    table = ["| Group | Mean Q/s | Median Q/s | Total Q | Total Time |",
             "|-------|----------|------------|---------|------------|"]
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in get_group_fd(gspec) if fd["pipeline_timing"] and fd["q_count"] > 0]
        if not gframes: continue
        qps = [fd["q_count"] / (get_timing(fd["pipeline_timing"], timing_key_candidates[3])/1000) for fd in gframes if get_timing(fd["pipeline_timing"], timing_key_candidates[3]) > 0]
        g_total_q = sum(fd["q_count"] for fd in gframes)
        g_total_t = sum(get_timing(fd["pipeline_timing"], timing_key_candidates[3]) for fd in gframes) / 1000
        table.append(f"| **{gname}** | {np.mean(qps):,.0f} | {np.median(qps):,.0f} | {g_total_q:,} | {g_total_t/3600:.1f}h |")
    md_lines.extend(table)
    md_lines.append("")
    
    # ── 9c: Per-question timing ──
    md_lines.append("### 9.4 Per-Question Generation Time")
    md_lines.append("")
    md_lines.append("Pipeline uses `skip_cypher=True` (in-memory verification only). ")
    md_lines.append("R1 questions: ~10\u03bcs/Q. R2 questions: recorded as 0 (generated by `regenerate_r2.py`).")
    md_lines.append("")
    
    fig_perq, ax_perq = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
    d9_boxdata = {}
    table = ["| Group | R1 N | Mean | Median | P95 | Max |",
             "|-------|------|------|--------|-----|-----|"]
    for gname, gspec in GROUPS.items():
        if gname == "All(\u22653)": continue
        gframes = get_group_fd(gspec)
        if not gframes: continue
        r1_us = []
        for fd in gframes:
            r1c = fd["r1_count"]
            r1_us.extend([t * 1000 for t in fd["timing_ms_per_q"][:r1c]])
        if r1_us:
            d9_boxdata[gname] = r1_us
            table.append(f"| **{gname}** | {len(r1_us):,} | {np.mean(r1_us):.1f}\u03bcs | {np.median(r1_us):.1f}\u03bcs | {np.percentile(r1_us,95):.1f}\u03bcs | {np.max(r1_us):.1f}\u03bcs |")
    md_lines.extend(table)
    md_lines.append("")
    
    if d9_boxdata:
        labels = list(d9_boxdata.keys())
        data = [d9_boxdata[g] for g in labels]
        bplot = ax_perq.boxplot(data, patch_artist=True, labels=labels, showfliers=False)
        for patch, g in zip(bplot['boxes'], labels):
            patch.set_facecolor(COLORS.get(g, '#888'))
            patch.set_alpha(0.6)
        ax_perq.set_ylabel("Generation Time per Q (\u03bcs)")
        ax_perq.set_title("R1 Per-Question Timing (in-memory verification)")
        fig_perq.savefig(OUT_DIR / "D9_timing_perq.png")
        plt.close(fig_perq)
        md_lines.append("![Per-Q Timing](D9_timing_perq.png)")
        md_lines.append("")
    else:
        plt.close(fig_perq)
    
    # ── 9d: Phase breakdown stacked bar chart ──
    if d9_stacked:
        fig_stack, ax_stack = plt.subplots(figsize=(FIG_W_SINGLE, 2.8))
        labels = list(d9_stacked.keys())
        x = np.arange(len(labels))
        # Convert to seconds for display
        pre_s = [d9_stacked[g]["pre"]/1000 for g in labels]
        plan_s = [d9_stacked[g]["plan"]/1000 for g in labels]
        sel_s = [d9_stacked[g]["sel"]/1000 for g in labels]
        ax_stack.bar(x, pre_s, 0.5, label="precompute", color="#2ca02c")
        ax_stack.bar(x, plan_s, 0.5, bottom=pre_s, label="plan_cache", color="#1f77b4")
        bottom2 = [a+b for a,b in zip(pre_s, plan_s)]
        ax_stack.bar(x, sel_s, 0.5, bottom=bottom2, label="selection_gen", color="#ff7f0e")
        ax_stack.set_xticks(x)
        ax_stack.set_xticklabels(labels)
        ax_stack.set_ylabel("Average Time per Frame (s)")
        ax_stack.set_title("Pipeline Phase Breakdown")
        ax_stack.legend(fontsize=6)
        fig_stack.savefig(OUT_DIR / "D9_phase_breakdown.png")
        plt.close(fig_stack)
        md_lines.append("![Phase Breakdown](D9_phase_breakdown.png)")
        md_lines.append("")
    
    # ── 9e: Per-frame total time distribution (boxplot) ──
    fig_ft, ax_ft = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
    d9_frame_time = {}
    for gname, gspec in GROUPS.items():
        if gname == "All(\u22653)": continue
        gframes = [fd for fd in get_group_fd(gspec) if fd["pipeline_timing"]]
        if not gframes: continue
        d9_frame_time[gname] = [get_timing(fd["pipeline_timing"], timing_key_candidates[3])/1000 for fd in gframes]
    
    if d9_frame_time:
        labels = list(d9_frame_time.keys())
        data = [d9_frame_time[g] for g in labels]
        bplot = ax_ft.boxplot(data, patch_artist=True, labels=labels, showfliers=False)
        for patch, g in zip(bplot['boxes'], labels):
            patch.set_facecolor(COLORS.get(g, '#888'))
            patch.set_alpha(0.6)
        ax_ft.set_ylabel("Total Pipeline Time (s)")
        ax_ft.set_title("Per-Frame Total Time Distribution")
        fig_ft.savefig(OUT_DIR / "D9_frame_time.png")
        plt.close(fig_ft)
        md_lines.append("![Frame Time](D9_frame_time.png)")
        md_lines.append("")
    else:
        plt.close(fig_ft)

    # ══════════════════════════════════════════════════════════════════════
    # Save partial MD and continue in next script
    # ══════════════════════════════════════════════════════════════════════
    with open(OUT_DIR / "rq2_report.md", "w") as f:
        f.write("\n".join(md_lines))
    print("Phase 2 part 2 done.")

if __name__ == "__main__":
    main()
