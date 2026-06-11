#!/usr/bin/env python3
"""D1: Grouped coverage curves + AUC analysis.

Splits frames into Small(3-10) / Medium(11-30) / Large(31-100) / All,
computes coverage curves and AUC for each group, generates comparison plots.

Runs on local extracted data — no HDD access needed.
"""
import argparse, csv, json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

# ── Config ──
GROUPS = {
    "Small (3–15)":   (3, 15),
    "Medium (16–30)": (16, 30),
    "Large (31+)":    (31, 999),
    "All (3+)":       (3, 999),
}
LEVELS = [
    ("L0 (Object)",       "curves_l0", "#2ca02c"),
    ("L1 (Relationship)", "curves_l1", "#d62728"),
    ("L2 (Triple)",       "curves_l2", "#1f77b4"),
]
INIT_COLOR = "#e377c2"

# SE top-venue style (ISSTA/ICSE/FSE/ASE) — double-column IEEE/ACM
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "font.size": 8,
    "axes.labelsize": 9,
    "axes.titlesize": 9,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "lines.linewidth": 1.2,
    "lines.markersize": 4,
    "axes.linewidth": 0.6,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.4,
    "grid.linestyle": "--",
    "figure.dpi": 300,
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
    "legend.frameon": True,
    "legend.framealpha": 0.8,
    "legend.edgecolor": "0.8",
    "legend.borderpad": 0.3,
})


def load_data(input_dir):
    data = np.load(os.path.join(input_dir, "rq2_curves.npz"))
    summary = []
    with open(os.path.join(input_dir, "rq2_frame_summary.csv")) as f:
        for row in csv.DictReader(f):
            summary.append(row)
    return data, summary


def get_group_indices(summary, lo, hi):
    indices = []
    for i, row in enumerate(summary):
        n = int(row["filtered_nodes"])
        if lo <= n <= hi:
            indices.append(i)
    return np.array(indices, dtype=int)


def compute_auc(x, y):
    if len(x) < 2: return 0.0
    x_n = (x - x[0]) / (x[-1] - x[0]) if x[-1] != x[0] else x
    _trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz")
    return float(_trapz(y, x_n))


def compute_abs_curve(curves, n_questions, max_x):
    max_x = min(max_x, curves.shape[1])
    x = np.arange(max_x)
    avg = np.mean(curves[:, :max_x], axis=0)
    p25 = np.percentile(curves[:, :max_x], 25, axis=0)
    p75 = np.percentile(curves[:, :max_x], 75, axis=0)
    return x, avg, p25, p75


def compute_norm_curve(curves, n_questions, n_pts=200):
    x_norm = np.linspace(0, 1, n_pts)
    interp = np.zeros((curves.shape[0], n_pts), dtype=np.float32)
    for i in range(curves.shape[0]):
        nq = n_questions[i]
        if nq == 0:
            interp[i, :] = curves[i, 0]
        else:
            x_orig = np.linspace(0, 1, nq + 1)
            interp[i, :] = np.interp(x_norm, x_orig, curves[i, :nq + 1])
    avg = np.mean(interp, axis=0)
    p25 = np.percentile(interp, 25, axis=0)
    p75 = np.percentile(interp, 75, axis=0)
    return x_norm, avg, p25, p75


def x_fmt(val, pos):
    return f"{val/1000:.0f}K" if val >= 1000 else f"{val:.0f}"


def plot_grouped_absolute(data, summary, output_dir):
    """One figure per group: 1×3 subplots (L0/L1/L2)."""
    auc_table = []

    for gname, (glo, ghi) in GROUPS.items():
        idx = get_group_indices(summary, glo, ghi)
        if len(idx) == 0: continue
        nq = data["n_questions"][idx]
        nq_nz = nq[nq > 0]
        if len(nq_nz) == 0: continue
        p90_q = int(np.percentile(nq_nz, 90))
        max_x = min(p90_q + 1, data["curves_l2"].shape[1])

        fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
        auc_row = {"group": gname, "n_frames": len(idx)}

        for ax, (lbl, key, color) in zip(axes, LEVELS):
            curves = data[key][idx]
            x, avg, p25, p75 = compute_abs_curve(curves, nq, max_x)

            ax.plot(x, avg, color=color, lw=2, label="Ours", zorder=3)
            ax.fill_between(x, np.clip(p25, 0, 1), np.clip(p75, 0, 1),
                            alpha=0.12, color=color, zorder=2)

            init_cov = float(avg[0])
            ax.plot(0, init_cov, "o", color=INIT_COLOR, ms=6, zorder=5)
            ax.annotate(f"Init: {init_cov:.1%}", xy=(0, init_cov),
                        xytext=(max_x * 0.15, init_cov + 0.08),
                        fontsize=8, color=INIT_COLOR,
                        arrowprops=dict(arrowstyle="->", color=INIT_COLOR, lw=0.8))

            auc = compute_auc(x.astype(float), avg)
            auc_row[f"AUC_{lbl[:2]}_abs"] = auc
            ax.text(0.97, 0.05, f"AUC = {auc:.4f}", transform=ax.transAxes,
                    fontsize=9, ha="right", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=color, alpha=0.8))

            ax.set_xlabel("Number of Generated Questions")
            ax.set_title(lbl)
            ax.set_ylim(-0.02, 1.05)
            ax.xaxis.set_major_formatter(FuncFormatter(x_fmt))
            ax.legend(loc="lower right", framealpha=0.9)

        axes[0].set_ylabel("Average Coverage Rate")
        tag = gname.split("(")[0].strip().lower()
        fig.suptitle(f"Coverage vs. Questions ��� {gname} ({len(idx)} frames)",
                     fontsize=13, fontweight="bold", y=1.02)
        plt.tight_layout()
        out = os.path.join(output_dir, f"rq2_abs_{tag}.png")
        fig.savefig(out, bbox_inches="tight")
        fig.savefig(out.replace(".png", ".pdf"), bbox_inches="tight")
        plt.close(fig)
        print(f"  Saved: {out}")

        auc_table.append(auc_row)

    return auc_table


def plot_grouped_normalized(data, summary, output_dir):
    """One figure per group: 1×3 subplots (L0/L1/L2), normalized X."""
    auc_table = []

    for gname, (glo, ghi) in GROUPS.items():
        idx = get_group_indices(summary, glo, ghi)
        if len(idx) == 0: continue
        nq = data["n_questions"][idx]

        fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
        auc_row = {"group": gname, "n_frames": len(idx)}

        for ax, (lbl, key, color) in zip(axes, LEVELS):
            curves = data[key][idx]
            x, avg, p25, p75 = compute_norm_curve(curves, nq)

            ax.plot(x * 100, avg, color=color, lw=2, label="Ours", zorder=3)
            ax.fill_between(x * 100, np.clip(p25, 0, 1), np.clip(p75, 0, 1),
                            alpha=0.12, color=color, zorder=2)

            init_cov = float(avg[0])
            ax.plot(0, init_cov, "o", color=INIT_COLOR, ms=6, zorder=5)

            auc = compute_auc(x, avg)
            auc_row[f"AUC_{lbl[:2]}_norm"] = auc
            ax.text(0.97, 0.05, f"AUC = {auc:.4f}", transform=ax.transAxes,
                    fontsize=9, ha="right", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=color, alpha=0.8))

            ax.set_xlabel("Question Budget (%)")
            ax.set_title(lbl)
            ax.set_ylim(-0.02, 1.05)
            ax.set_xlim(-2, 102)
            ax.legend(loc="lower right", framealpha=0.9)

        axes[0].set_ylabel("Average Coverage Rate")
        tag = gname.split("(")[0].strip().lower()
        fig.suptitle(f"Coverage vs. Budget — {gname} ({len(idx)} frames)",
                     fontsize=13, fontweight="bold", y=1.02)
        plt.tight_layout()
        out = os.path.join(output_dir, f"rq2_norm_{tag}.png")
        fig.savefig(out, bbox_inches="tight")
        fig.savefig(out.replace(".png", ".pdf"), bbox_inches="tight")
        plt.close(fig)
        print(f"  Saved: {out}")

        auc_table.append(auc_row)

    return auc_table


def plot_auc_comparison(auc_abs, auc_norm, output_dir):
    """Bar chart comparing AUC across groups."""
    groups = [r["group"] for r in auc_abs]
    x = np.arange(len(groups))
    w = 0.25

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

    for i, (lbl, _, color) in enumerate(LEVELS):
        key = f"AUC_{lbl[:2]}_abs"
        vals = [r[key] for r in auc_abs]
        ax1.bar(x + i * w, vals, w, label=lbl, color=color, alpha=0.85)
    ax1.set_xticks(x + w)
    ax1.set_xticklabels([r["group"].split("(")[0].strip() for r in auc_abs], fontsize=9)
    ax1.set_ylabel("AUC")
    ax1.set_title("Absolute AUC by Group")
    ax1.set_ylim(0, 1.05)
    ax1.legend(fontsize=8)

    for i, (lbl, _, color) in enumerate(LEVELS):
        key = f"AUC_{lbl[:2]}_norm"
        vals = [r[key] for r in auc_norm]
        ax2.bar(x + i * w, vals, w, label=lbl, color=color, alpha=0.85)
    ax2.set_xticks(x + w)
    ax2.set_xticklabels([r["group"].split("(")[0].strip() for r in auc_norm], fontsize=9)
    ax2.set_ylabel("AUC")
    ax2.set_title("Normalized AUC by Group")
    ax2.set_ylim(0, 1.05)
    ax2.legend(fontsize=8)

    plt.tight_layout()
    out = os.path.join(output_dir, "rq2_auc_comparison.png")
    fig.savefig(out, bbox_inches="tight")
    fig.savefig(out.replace(".png", ".pdf"), bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out}")


def save_auc_csv(auc_abs, auc_norm, output_dir):
    rows = []
    for a, n in zip(auc_abs, auc_norm):
        row = {"Group": a["group"], "Frames": a["n_frames"]}
        for lbl, _, _ in LEVELS:
            k = lbl[:2]
            row[f"AUC_{k}_Abs"] = f"{a[f'AUC_{k}_abs']:.4f}"
            row[f"AUC_{k}_Norm"] = f"{n[f'AUC_{k}_norm']:.4f}"
        rows.append(row)

    out = os.path.join(output_dir, "rq2_auc_grouped.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"  Saved: {out}")

    # Print table
    print("\n=== AUC Comparison ===")
    print(f"{'Group':<20s} {'Frames':>6s} | {'L0_Abs':>8s} {'L1_Abs':>8s} {'L2_Abs':>8s} | {'L0_Norm':>8s} {'L1_Norm':>8s} {'L2_Norm':>8s}")
    print("-" * 85)
    for r in rows:
        print(f"{r['Group']:<20s} {r['Frames']:>6d} | {r['AUC_L0_Abs']:>8s} {r['AUC_L1_Abs']:>8s} {r['AUC_L2_Abs']:>8s} | {r['AUC_L0_Norm']:>8s} {r['AUC_L1_Norm']:>8s} {r['AUC_L2_Norm']:>8s}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=os.path.join(os.path.dirname(__file__), "extracted_r1"))
    parser.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "figures_grouped"))
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print("Loading data...")
    data, summary = load_data(args.input)
    print(f"Loaded {len(summary)} frames, max_q={data['curves_l2'].shape[1]-1}")

    print("\n--- Absolute coverage curves ---")
    auc_abs = plot_grouped_absolute(data, summary, args.output)

    print("\n--- Normalized coverage curves ---")
    auc_norm = plot_grouped_normalized(data, summary, args.output)

    print("\n--- AUC comparison ---")
    plot_auc_comparison(auc_abs, auc_norm, args.output)
    save_auc_csv(auc_abs, auc_norm, args.output)

    print("\nDone!")


if __name__ == "__main__":
    main()
