"""Phase 2 part 3: Generate plots and markdown report for D10-D16."""
import os, sys, pickle, json, math
from collections import defaultdict, Counter
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rq2_analysis_config import *

sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)

def main():
    print("=== Phase 2 Part 3: Generating Report ===")
    
    cache_path = PLOTS_DIR / "rq2_frame_cache.pkl"
    with open(cache_path, "rb") as f:
        frame_data = pickle.load(f)

    md_path = OUT_DIR / "rq2_report.md"
    md_lines = []
    if md_path.exists():
        with open(md_path) as f:
            md_lines = f.read().splitlines()

    def get_group_fd(gspec):
        return [fd for fd in frame_data if gspec["min"] <= fd["nodes"] <= gspec["max"]]

    # ══════════════════════════════════════════════════════════════════════
    # D10: Constraint Quality
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D10: Constraint Quality...")
    md_lines.extend(["## D10: Constraint Quality (R1)", ""])
    
    c_counts = []
    c_types = Counter()
    for fd in frame_data:
        c_counts.extend(fd["constraint_counts"])
        for k, v in fd["constraint_types"].items():
            c_types[k] += v
            
    if c_counts:
        md_lines.append(f"**Average constraints per R1 question:** {np.mean(c_counts):.2f}")
        md_lines.append(f"**Median constraints per R1 question:** {np.median(c_counts):.2f}")
        md_lines.append("")
        md_lines.append("| Constraint Type | Count | % |")
        md_lines.append("|-----------------|-------|---|")
        tot_c = sum(c_types.values())
        for k, v in c_types.most_common():
            md_lines.append(f"| {k} | {v:,} | {v/tot_c*100:.1f}% |")
        md_lines.append("")
        
        # D10 Chart: histogram of constraint counts
        fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
        max_c = min(int(np.percentile(c_counts, 99)), 20)
        ax.hist(c_counts, bins=range(0, max_c + 2), edgecolor='white', alpha=0.8, color=COLORS["All(≥3)"])
        ax.set_xlabel("Constraints per R1 Question")
        ax.set_ylabel("Count")
        ax.set_title("Constraint Count Distribution (R1)")
        fig.savefig(OUT_DIR / "D10_constraints.png")
        plt.close(fig)
        md_lines.append("![Constraints](D10_constraints.png)")
    md_lines.append("")

    # ══════════════════════════════════════════════════════════════════════
    # D11: Ego Analysis
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D11: Ego Analysis...")
    md_lines.extend(["## D11: Ego Analysis", 
                     "Gap contains the ego vehicle — most critical for ADS VQA testing.",
                     "Ego-relative questions test spatial reasoning w.r.t. the self-vehicle.", ""])
    
    table = ["| Group | Total JSONL Q | Ego Q | Ego % |", "|-------|---------------|-------|-------|"]
    ego_pcts = {}
    for gname, gspec in GROUPS.items():
        gframes = get_group_fd(gspec)
        tot = sum(fd["total_gap_from_jsonl"] for fd in gframes)
        ego = sum(fd["ego_gap_count"] for fd in gframes)
        if tot > 0:
            pct = ego/tot*100
            table.append(f"| **{gname}** | {tot:,} | {ego:,} | {pct:.1f}% |")
            if gname != "All(≥3)":
                ego_pcts[gname] = pct
    md_lines.extend(table)
    md_lines.append("")
    
    # D11 Chart: ego percentage by group
    if ego_pcts:
        fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
        labels = list(ego_pcts.keys())
        vals = [ego_pcts[g] for g in labels]
        ax.bar(labels, vals, color=[COLORS.get(g, '#888') for g in labels])
        ax.set_ylabel("Ego Gap Percentage (%)")
        ax.set_title("Ego-Related Questions by Group")
        fig.savefig(OUT_DIR / "D11_ego.png")
        plt.close(fig)
        md_lines.append("![Ego Analysis](D11_ego.png)")
    md_lines.append("")

    # ══════════════════════════════════════════════════════════════════════
    # D12: Graph Density
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D12: Graph Density...")
    md_lines.extend(["## D12: Graph Density",
                     "Graph is fully connected (complete directed graph). "
                     "Edges = N*(N-1), L2 Gaps = N*(N-1)*(N-2) (3-node paths).",
                     "Efficiency = Q_to_100% / L2_gaps.", ""])
    
    table = ["| Group | Avg Nodes | Avg L2 Gaps | Avg Q | Efficiency (Q/Gaps) |",
             "|-------|-----------|-------------|-------|---------------------|"]
    d12_nodes, d12_eff = [], []
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in get_group_fd(gspec) if fd["total_gaps"] > 0]
        if not gframes: continue
        nodes = np.mean([fd["nodes"] for fd in gframes])
        gaps = np.mean([fd["total_gaps"] for fd in gframes])
        q = np.mean([fd["q_count"] for fd in gframes])
        eff = np.mean([fd["q_count"]/fd["total_gaps"] for fd in gframes])
        table.append(f"| **{gname}** | {nodes:.1f} | {gaps:.0f} | {q:.0f} | {eff:.3f} |")
    md_lines.extend(table)
    md_lines.append("")
    
    # D12 Chart: scatter of nodes vs efficiency
    for fd in frame_data:
        if fd["total_gaps"] > 0:
            d12_nodes.append(fd["nodes"])
            d12_eff.append(fd["q_count"] / fd["total_gaps"])
    if d12_nodes:
        fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 3))
        ax.scatter(d12_nodes, d12_eff, alpha=0.15, s=3, color=COLORS["All(≥3)"])
        ax.set_xlabel("Nodes (N)")
        ax.set_ylabel("Q / L2_Gaps (Efficiency)")
        ax.set_title("Graph Size vs Generation Efficiency")
        fig.savefig(OUT_DIR / "D12_density.png")
        plt.close(fig)
        md_lines.append("![Graph Density](D12_density.png)")
    md_lines.append("")

    # ══════════════════════════════════════════════════════════════════════
    # D13: Answer Distribution
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D13: Answer Distribution...")
    md_lines.extend(["## D13: Answer Distribution (R1+R2)", ""])
    
    ans_all = Counter()
    for fd in frame_data:
        for k, v in fd["answer_types"].items():
            ans_all[k] += v
    
    table = ["| Answer Type | Count | % |", "|-------------|-------|---|"]
    tot_a = sum(ans_all.values())
    if tot_a > 0:
        for k, v in ans_all.most_common():
            table.append(f"| {k} | {v:,} | {v/tot_a*100:.1f}% |")
    md_lines.extend(table)
    md_lines.append("")
    
    # D13 Chart: pie chart of answer types
    if tot_a > 0 and len(ans_all) > 0:
        fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 3))
        labels = [k for k, _ in ans_all.most_common(8)]
        sizes = [ans_all[k] for k in labels]
        other = tot_a - sum(sizes)
        if other > 0:
            labels.append("other")
            sizes.append(other)
        colors_pie = plt.cm.Set3(np.linspace(0, 1, len(labels)))
        ax.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors_pie, startangle=90, textprops={'fontsize': 6})
        ax.set_title("Answer Type Distribution")
        fig.savefig(OUT_DIR / "D13_answer_dist.png")
        plt.close(fig)
        md_lines.append("![Answer Distribution](D13_answer_dist.png)")
    md_lines.append("")

    # ══════════════════════════════════════════════════════════════════════
    # D14: Candidate Filtering
    # ═══════════════════════════════════════════════════════════════��══════
    print("Generating D14: Candidate Filtering...")
    md_lines.extend(["## D14: Candidate Filtering (R1 constraints)", ""])
    
    # candidate_before/after are 0 because pipeline uses skip_cypher=True
    md_lines.append("**Note**: Per-question `candidate_before/after` = 0 because the pipeline uses")
    md_lines.append("`skip_cypher=True` (in-memory direct verification instead of Neo4j candidate enumeration).")
    md_lines.append("The equivalent filtering is done in the **plan_cache pre-verification** stage,")
    md_lines.append("which filters infeasible plans before selection begins.")
    md_lines.append("")
    
    # Report pre_verify stats from pipeline_timing
    table = ["| Group | Avg Plans Evaluated | Avg Plans Filtered | Filter Rate |",
             "|-------|--------------------|--------------------|-------------|"]
    d14_data = {}
    for gname, gspec in GROUPS.items():
        gframes = [fd for fd in get_group_fd(gspec) if fd["pipeline_timing"]]
        if not gframes: continue
        pv_total = [fd["pipeline_timing"].get("pre_verify_total", 0) for fd in gframes]
        pv_filtered = [fd["pipeline_timing"].get("pre_verify_filtered", 0) for fd in gframes]
        avg_total = np.mean(pv_total)
        avg_filtered = np.mean(pv_filtered)
        rate = avg_filtered / avg_total * 100 if avg_total > 0 else 0
        table.append(f"| **{gname}** | {avg_total:.0f} | {avg_filtered:.0f} | {rate:.1f}% |")
        if gname != "All(>=3)" and gname != "All(\u22653)":
            d14_data[gname] = {"total": avg_total, "filtered": avg_filtered, "rate": rate}
    md_lines.extend(table)
    md_lines.append("")
    
    # Also report constraint counts as a proxy for filtering power
    cc_all = []
    for fd in frame_data:
        cc_all.extend(fd["constraint_counts"])
    if cc_all:
        md_lines.append(f"**R1 Constraint Statistics** (from {len(cc_all):,} R1 questions with constraints):")
        md_lines.append(f"- Mean constraints per Q: {np.mean(cc_all):.2f}")
        md_lines.append(f"- Median: {np.median(cc_all):.0f}")
        md_lines.append(f"- Max: {max(cc_all)}")
        md_lines.append("")
    
    # D14 Chart: pre_verify filter rate by group
    if d14_data:
        fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
        labels = list(d14_data.keys())
        rates = [d14_data[g]["rate"] for g in labels]
        ax.bar(labels, rates, color=[COLORS.get(g, '#888') for g in labels])
        ax.set_ylabel("Pre-Verify Filter Rate (%)")
        ax.set_title("Plan Filtering Rate by Group")
        fig.savefig(OUT_DIR / "D14_candidates.png")
        plt.close(fig)
        md_lines.append("![Plan Filtering](D14_candidates.png)")
    md_lines.append("")

    # ══════════════════════════════════════════════════════════════════════
    # D15: Cross-frame Gap Overlap
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D15: Cross-frame Gap Overlap...")
    md_lines.extend(["## D15: Cross-frame Gap Overlap (Temporal Consistency)",
                     "For same-scene frames: what fraction of the scene's unique L2 gaps appear in each frame?",
                     "High overlap = temporal consistency (same objects tracked across time).", ""])
    
    scene_gaps = defaultdict(list)
    for fd in frame_data:
        scene_gaps[fd["scene_name"]].append(fd["gap_patterns"])
        
    overlaps = []
    scene_n_frames = []
    for scn, frame_sets in scene_gaps.items():
        if len(frame_sets) > 1:
            union = set().union(*frame_sets)
            if union:
                avg_frac = np.mean([len(fs) / len(union) for fs in frame_sets])
                overlaps.append(avg_frac)
                scene_n_frames.append(len(frame_sets))
                
    if overlaps:
        md_lines.append(f"**Scenes with >1 frame**: {len(overlaps)}")
        md_lines.append(f"**Average frame shares {np.mean(overlaps):.1%}** of the scene's unique gaps.")
        md_lines.append(f"**Median overlap**: {np.median(overlaps):.1%}")
        md_lines.append("")
        
        # D15 Chart: histogram of overlap fractions
        fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
        ax.hist([o*100 for o in overlaps], bins=20, edgecolor='white', alpha=0.8, color=COLORS["All(≥3)"])
        ax.set_xlabel("Frame Gap Overlap (%)")
        ax.set_ylabel("Number of Scenes")
        ax.set_title("Cross-Frame Gap Overlap Distribution")
        ax.axvline(np.mean(overlaps)*100, color='red', ls='--', lw=1.5, label=f"Mean={np.mean(overlaps)*100:.1f}%")
        ax.legend()
        fig.savefig(OUT_DIR / "D15_overlap.png")
        plt.close(fig)
        md_lines.append("![Cross-frame Overlap](D15_overlap.png)")
    md_lines.append("")

    # ══════════════════════════════════════════════════════════════════════
    # D16: Coverage Saturation
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D16: Coverage Saturation...")
    md_lines.extend(["## D16: Coverage Saturation (95%→100% cost)", ""])
    
    fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
    
    table = ["| Group | Avg Q to 95% | Avg Q 95%→100% | Tail Cost % |", "|-------|--------------|----------------|-------------|"]
    y_vals = []
    x_labels = []
    
    for gname, gspec in GROUPS.items():
        if gname == "All(≥3)": continue
        gframes = [fd for fd in get_group_fd(gspec) if fd["coverage_points"]]
        if not gframes: continue
        
        q_95, tail_q, total_q = [], [], []
        for fd in gframes:
            pts = fd["coverage_points"]
            tot = len(pts)
            first_95 = tot
            for qi, cov in enumerate(pts):
                if cov >= 0.95:
                    first_95 = qi + 1
                    break
            q_95.append(first_95)
            tail_q.append(tot - first_95)
            total_q.append(tot)
            
        m_95 = np.mean(q_95)
        m_tail = np.mean(tail_q)
        m_tot = np.mean(total_q)
        cost_pct = m_tail / m_tot * 100 if m_tot > 0 else 0
        
        table.append(f"| **{gname}** | {m_95:.1f} | {m_tail:.1f} | {cost_pct:.1f}% |")
        x_labels.append(gname)
        y_vals.append(cost_pct)
        
    ax.bar(x_labels, y_vals, color=[COLORS.get(g, '#888') for g in x_labels])
    ax.set_ylabel("Tail Cost (% of total Q)")
    ax.set_title("95%→100% Coverage Saturation Cost")
    fig.savefig(OUT_DIR / "D16_saturation.png")
    plt.close(fig)
    
    md_lines.extend(table)
    md_lines.append("")
    md_lines.append("![Saturation](D16_saturation.png)")

    # ══════════════════════════════════════════════════════════════════════
    # FINAL SUMMARY TABLE
    # ══════════════════════════════════════════════════════════════════════
    print("Generating Final Summary Table...")
    md_lines.extend(["", "## Summary Table", ""])
    
    summary_table = [
        "| Group | Frames | Avg N | Avg Q | AUC_L2 | R1 cov | conv% | dir% | dist% | vp% | div% | Redundancy |",
        "|-------|--------|-------|-------|--------|--------|-------|------|-------|-----|------|------------|"
    ]
    
    # Load npz for AUC
    import csv as csv_mod
    r1_data = np.load(str(EXTRACTED_R1 / "rq2_curves.npz"))
    r1_nq = r1_data["n_questions"]
    r1_curves_l2 = r1_data["curves_l2"]
    r1_summary = []
    with open(str(EXTRACTED_R1 / "rq2_frame_summary.csv")) as f:
        for row in csv_mod.DictReader(f): r1_summary.append(row)
    
    for gname, gspec in GROUPS.items():
        gframes = get_group_fd(gspec)
        if not gframes: continue
        n = len(gframes)
        avg_nodes = np.mean([fd["nodes"] for fd in gframes])
        avg_q = np.mean([fd["q_count"] for fd in gframes])
        
        # Family distribution
        g_fam = Counter()
        for fd in gframes:
            for k, v in fd["families"].items():
                g_fam[k] += v
        total_gq = sum(g_fam.values())
        conv = g_fam.get("converge", 0) / total_gq * 100 if total_gq > 0 else 0
        dir_c = g_fam.get("direction_chain", 0) / total_gq * 100 if total_gq > 0 else 0
        dist_c = g_fam.get("distance_chain", 0) / total_gq * 100 if total_gq > 0 else 0
        vp = g_fam.get("viewpoint_transfer", 0) / total_gq * 100 if total_gq > 0 else 0
        div = g_fam.get("diverge_compare", 0) / total_gq * 100 if total_gq > 0 else 0
        
        # R1 coverage
        r1_cov = np.mean([fd["r1_end_cov_l2"] for fd in gframes if fd["q_count"] > 0]) * 100
        
        # Redundancy
        total_dl2 = sum(fd["delta_l2_total"] for fd in gframes)
        total_rl2 = sum(fd["raw_l2_total"] for fd in gframes)
        red = (1 - total_dl2 / total_rl2) * 100 if total_rl2 > 0 else 0
        
        # AUC from npz
        indices = [i for i, row in enumerate(r1_summary)
                   if gspec["min"] <= int(row["filtered_nodes"]) <= gspec["max"] and r1_nq[i] > 0]
        auc_l2_list = []
        for idx in indices:
            nq = r1_nq[idx]
            if nq == 0: continue
            n_pts = 200
            x_norm = np.linspace(0, 1, n_pts)
            x_orig = np.linspace(0, 1, nq + 1)
            y_interp = np.interp(x_norm, x_orig, r1_curves_l2[idx, :nq+1])
            auc_l2_list.append(float(np.trapz(y_interp, x_norm)))
        auc_l2 = np.mean(auc_l2_list) if auc_l2_list else 0
        
        summary_table.append(
            f"| **{gname}** | {n} | {avg_nodes:.1f} | {avg_q:.0f} | {auc_l2:.3f} | "
            f"{r1_cov:.1f}% | {conv:.1f}% | {dir_c:.1f}% | {dist_c:.1f}% | {vp:.1f}% | {div:.2f}% | {red:.1f}% |"
        )
    
    md_lines.extend(summary_table)

    # ══════════════════════════════════════════════════════════════════════
    # Finalize MD
    # ══════════════════════════════════════════════════════════════════════
    with open(OUT_DIR / "rq2_report.md", "w") as f:
        f.write("\n".join(md_lines))
    print("Phase 2 part 3 done.")
    print(f"Full report generated at: {OUT_DIR / 'rq2_report.md'}")

if __name__ == "__main__":
    main()
