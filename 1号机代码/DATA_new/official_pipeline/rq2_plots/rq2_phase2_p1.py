"""Phase 2: Generate plots and markdown report for D1-D16."""
import os, sys, pickle, json, math
from collections import defaultdict
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rq2_analysis_config import *

sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)

def compute_auc(x, y):
    if len(x) < 2: return 0.0
    x_norm = (x - x[0]) / (x[-1] - x[0]) if x[-1] != x[0] else x
    return float(np.trapz(y, x_norm))

def main():
    print("=== Phase 2: Generating Plots and Report ===")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load cache
    cache_path = PLOTS_DIR / "rq2_frame_cache.pkl"
    if not cache_path.exists():
        print(f"Error: {cache_path} not found. Run phase 1 first.")
        return
    
    print("Loading cache...")
    with open(cache_path, "rb") as f:
        frame_data = pickle.load(f)
    print(f"Loaded {len(frame_data)} frames.")

    # Load extracted npz for curves
    r1_data = np.load(str(EXTRACTED_R1 / "rq2_curves.npz"))
    r1_curves_l0 = r1_data["curves_l0"]
    r1_curves_l1 = r1_data["curves_l1"]
    r1_curves_l2 = r1_data["curves_l2"]
    r1_nq = r1_data["n_questions"]
    
    # Read frame summary to map index to nodes
    r1_summary = []
    with open(str(EXTRACTED_R1 / "rq2_frame_summary.csv")) as f:
        import csv
        for row in csv.DictReader(f):
            r1_summary.append(row)

    md_lines = [
        "# RQ2 Comprehensive Analysis Report",
        "> Data scope: 6011 frames (S/M/L grouped)",
        "> Metrics: D1-D16 from Analysis Plan",
        "",
    ]
    
    # ── Helpers for grouping ───────────────────────────────────────────
    def get_group_fd(gspec):
        return [fd for fd in frame_data if gspec["min"] <= fd["nodes"] <= gspec["max"]]
        
    def get_group_idx(gspec):
        return [i for i, row in enumerate(r1_summary) 
                if gspec["min"] <= int(row["filtered_nodes"]) <= gspec["max"]]

    # ══════════════════════════════════════════════════════════════════════
    # D1: Coverage curves + AUC
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D1: Coverage Curves...")
    md_lines.extend(["## D1: Coverage Curves & AUC", ""])
    
    for gname, gspec in GROUPS.items():
        indices = get_group_idx(gspec)
        if not indices: continue
        valid_idx = [i for i in indices if r1_nq[i] > 0]
        if not valid_idx: continue
        
        n_points = 200
        x_norm = np.linspace(0, 1, n_points)
        
        fig, axes = plt.subplots(1, 3, figsize=(FIG_W_DOUBLE, 2.5), sharey=True)
        levels = [
            ("L0 Object", r1_curves_l0, COLORS["L0"]),
            ("L1 Rel", r1_curves_l1, COLORS["L1"]),
            ("L2 Triple", r1_curves_l2, COLORS["L2"]),
        ]
        
        auc_res = []
        for ax, (title, curves, color) in zip(axes, levels):
            interp_curves = np.zeros((len(valid_idx), n_points))
            for k, idx in enumerate(valid_idx):
                nq = r1_nq[idx]
                x_orig = np.linspace(0, 1, nq + 1)
                interp_curves[k] = np.interp(x_norm, x_orig, curves[idx, :nq+1])
            
            avg = np.mean(interp_curves, axis=0)
            std = np.std(interp_curves, axis=0)
            auc = compute_auc(x_norm, avg)
            auc_res.append(auc)
            
            ax.plot(x_norm * 100, avg, color=color, lw=2)
            ax.fill_between(x_norm * 100, np.clip(avg-std,0,1), np.clip(avg+std,0,1), alpha=0.15, color=color)
            ax.set_title(f"{title} (AUC={auc:.3f})")
            ax.set_xlabel("Question Budget (%)")
            ax.set_xlim(0, 100)
            ax.set_ylim(-0.05, 1.05)
            if ax == axes[0]: ax.set_ylabel("Coverage Rate")
            
        fig.suptitle(f"Group: {gname} (N={len(valid_idx)})", y=1.05)
        out_name = f"D1_curves_{gname.replace('(','_').replace(')','').replace('≥','ge')}.png"
        fig.savefig(OUT_DIR / out_name)
        plt.close(fig)
        
        md_lines.append(f"**{gname}**: AUC (L0={auc_res[0]:.3f}, L1={auc_res[1]:.3f}, L2={auc_res[2]:.3f})")
        md_lines.append(f"![{gname} Curves]({out_name})")
        md_lines.append("")

    # ════════���═════════════════════════════════════════════════════════════
    # D2: Coverage Decay
    # ══════════════════════════════════════════════════════════════════════
    print("Generating D2: Coverage Decay...")
    md_lines.extend(["## D2: Coverage Decay", "Average ΔL2 per question across coverage segments.", ""])
    segments = [(0, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 0.90), (0.90, 1.0)]
    
    fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, 2.5))
    x_labels = [f"{s[0]*100:.0f}-{s[1]*100:.0f}%" for s in segments]
    bar_w = 0.2
    
    for i, (gname, gspec) in enumerate(GROUPS.items()):
        if gname == "All(≥3)": continue
        gframes = get_group_fd(gspec)
        if not gframes: continue
        
        y_vals = []
        for seg_start, seg_end in segments:
            seg_dl2, seg_q = [], []
            for fd in gframes:
                pts = fd["coverage_points"]
                dl2s = fd["per_q_delta_l2"]
                qin, din = 0, 0
                for qi, cov in enumerate(pts):
                    if (seg_start <= cov < seg_end) if seg_end < 1.0 else (cov >= seg_start):
                        qin += 1
                        din += dl2s[qi]
                if qin > 0:
                    seg_dl2.append(din / qin)
            y_vals.append(np.mean(seg_dl2) if seg_dl2 else 0)
            
        x_pos = np.arange(len(segments)) + (i - 1) * bar_w
        ax.bar(x_pos, y_vals, bar_w, label=gname, color=COLORS[gname])
    
    ax.set_xticks(np.arange(len(segments)))
    ax.set_xticklabels(x_labels)
    ax.set_ylabel("Avg ΔL2 / Q")
    ax.legend()
    fig.savefig(OUT_DIR / "D2_decay.png")
    plt.close(fig)
    md_lines.append("![Coverage Decay](D2_decay.png)")
    md_lines.append("")

    # ══════════════════════════════════════════════════════════════════════
    # Save partial MD and continue in next script
    # ══════════════════════════════════════════════════════════════════════
    with open(OUT_DIR / "rq2_report.md", "w") as f:
        f.write("\n".join(md_lines))
    print("Phase 2 part 1 done.")

if __name__ == "__main__":
    main()
