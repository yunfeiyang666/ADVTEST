#!/usr/bin/env python3
"""Plot RQ2 coverage improvement charts.

Reads extracted data from extract_rq2_data.py and generates:
- Figure A: Coverage vs absolute question count (L0/L1/L2 combined)
- Figure B: Coverage vs normalized question percentage (L0/L1/L2 combined)
- Summary table with AUC values

Usage:
    python plot_rq2.py [--input DIR] [--output DIR] [--format pdf|png]
"""
from __future__ import print_function

import argparse
import csv
import json
import os
import sys
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

# ── Style ──────────────────────────────────────────────────────────────
# Academic paper style: clean, readable, publication-quality
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "legend.fontsize": 9,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "lines.linewidth": 1.5,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linewidth": 0.5,
})

# Color palette — distinguishable, colorblind-friendly
COLORS = {
    "ours_l2": "#2563EB",     # Blue
    "ours_l1": "#DC2626",     # Red
    "ours_l0": "#16A34A",     # Green
    "random_l2": "#93C5FD",   # Light blue (placeholder)
    "random_l1": "#FCA5A5",   # Light red (placeholder)
    "random_l0": "#86EFAC",   # Light green (placeholder)
    "init": "#F59E0B",        # Amber for initial coverage marker
}


def load_data(input_dir):
    """Load extracted data."""
    npz_path = os.path.join(input_dir, "rq2_curves.npz")
    meta_path = os.path.join(input_dir, "rq2_meta.json")

    data = np.load(npz_path)
    with open(meta_path, "r") as f:
        meta = json.load(f)

    return {
        "curves_l0": data["curves_l0"],
        "curves_l1": data["curves_l1"],
        "curves_l2": data["curves_l2"],
        "n_questions": data["n_questions"],
        "meta": meta,
    }


def compute_avg_curve_absolute(curves, n_questions, max_x=None):
    """Compute average coverage curve with absolute X axis.

    For frames with fewer questions, their final coverage is used for padding.
    All frames contribute to every X position.

    Returns: (x_values, avg_curve, std_curve, n_contributing)
    """
    n_frames, curve_len = curves.shape
    if max_x is None:
        max_x = curve_len

    max_x = min(max_x, curve_len)

    x = np.arange(max_x)
    avg = np.mean(curves[:, :max_x], axis=0)
    std = np.std(curves[:, :max_x], axis=0)
    # All frames contribute (padded with final value)
    n_contributing = np.full(max_x, n_frames, dtype=np.int32)

    return x, avg, std, n_contributing


def compute_avg_curve_normalized(curves, n_questions, n_points=200):
    """Compute average coverage curve with normalized X axis [0, 1].

    For each frame, interpolate its coverage curve to n_points evenly spaced
    positions in [0, 1]. Then average across all frames.

    Returns: (x_values, avg_curve, std_curve)
    """
    x_norm = np.linspace(0.0, 1.0, n_points)
    interp_curves = np.zeros((curves.shape[0], n_points), dtype=np.float32)

    for i in range(curves.shape[0]):
        nq = n_questions[i]
        if nq == 0:
            # Trivial frame: constant at initial coverage
            interp_curves[i, :] = curves[i, 0]
        else:
            # Original x positions: [0, 1, 2, ..., nq] mapped to [0, 1]
            x_orig = np.linspace(0.0, 1.0, nq + 1)
            y_orig = curves[i, :nq + 1]
            interp_curves[i, :] = np.interp(x_norm, x_orig, y_orig)

    avg = np.mean(interp_curves, axis=0)
    std = np.std(interp_curves, axis=0)

    return x_norm, avg, std


def compute_auc(x, y):
    """Compute AUC using trapezoidal rule, normalized to [0, 1]."""
    if len(x) < 2:
        return 0.0
    x_norm = (x - x[0]) / (x[-1] - x[0]) if x[-1] != x[0] else x
    return float(np.trapz(y, x_norm))


def plot_absolute_combined(data, output_dir, fmt="pdf"):
    """Plot L0/L1/L2 coverage vs absolute question count in a single 1x3 figure."""
    curves = {
        "L0 (Object)": (data["curves_l0"], COLORS["ours_l0"]),
        "L1 (Relationship)": (data["curves_l1"], COLORS["ours_l1"]),
        "L2 (Triple)": (data["curves_l2"], COLORS["ours_l2"]),
    }

    n_questions = data["n_questions"]
    # Determine X range: use median question count as primary range
    median_q = int(np.median(n_questions[n_questions > 0]))
    p90_q = int(np.percentile(n_questions[n_questions > 0], 90))
    # Use a reasonable range that shows the interesting part
    max_x = min(p90_q, data["curves_l2"].shape[1])
    print("Absolute plot: median_q={}, p90_q={}, max_x={}".format(median_q, p90_q, max_x))

    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)

    auc_values = {}

    for ax, (label, (curve_data, color)) in zip(axes, curves.items()):
        x, avg, std, n_contrib = compute_avg_curve_absolute(curve_data, n_questions, max_x)

        # Plot average curve
        ax.plot(x, avg, color=color, linewidth=2.0, label="Ours", zorder=3)

        # Shaded confidence band (±1 std)
        ax.fill_between(x, np.clip(avg - std, 0, 1), np.clip(avg + std, 0, 1),
                        alpha=0.15, color=color, zorder=2)

        # Mark initial coverage (x=0)
        init_cov = float(avg[0])
        ax.plot(0, init_cov, "o", color=COLORS["init"], markersize=6, zorder=5)
        ax.annotate("Init: {:.1%}".format(init_cov),
                    xy=(0, init_cov), xytext=(max_x * 0.15, init_cov + 0.08),
                    fontsize=8, color=COLORS["init"],
                    arrowprops=dict(arrowstyle="->", color=COLORS["init"], lw=0.8),
                    zorder=5)

        # Placeholder for Random baseline (dashed, grayed out)
        # ax.plot(x, random_avg, "--", color=random_color, linewidth=1.5, label="Random", alpha=0.6)
        ax.plot([], [], "--", color="gray", linewidth=1.5, label="Random (TBD)", alpha=0.5)

        # Compute and display AUC
        auc = compute_auc(x.astype(float), avg)
        auc_values[label] = auc
        ax.text(0.97, 0.05, "AUC = {:.4f}".format(auc),
                transform=ax.transAxes, fontsize=9,
                ha="right", va="bottom",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                          edgecolor=color, alpha=0.8))

        ax.set_xlabel("Number of Generated Questions")
        ax.set_title(label)
        ax.set_ylim(-0.02, 1.05)
        ax.legend(loc="lower right", framealpha=0.9)

        # Format x-axis with K suffix for large numbers
        def x_formatter(val, pos):
            if val >= 1000:
                return "{:.0f}K".format(val / 1000)
            return "{:.0f}".format(val)
        ax.xaxis.set_major_formatter(FuncFormatter(x_formatter))

    axes[0].set_ylabel("Average Coverage Rate")

    fig.suptitle("RQ2: Coverage Rate vs. Number of Generated Questions",
                 fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()

    out_path = os.path.join(output_dir, "rq2_absolute_coverage.{}".format(fmt))
    fig.savefig(out_path, format=fmt, bbox_inches="tight")
    plt.close(fig)
    print("Saved: {}".format(out_path))
    return auc_values


def plot_normalized_combined(data, output_dir, fmt="pdf"):
    """Plot L0/L1/L2 coverage vs normalized question percentage in 1x3 figure."""
    curves = {
        "L0 (Object)": (data["curves_l0"], COLORS["ours_l0"]),
        "L1 (Relationship)": (data["curves_l1"], COLORS["ours_l1"]),
        "L2 (Triple)": (data["curves_l2"], COLORS["ours_l2"]),
    }

    n_questions = data["n_questions"]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)

    auc_values = {}

    for ax, (label, (curve_data, color)) in zip(axes, curves.items()):
        x, avg, std = compute_avg_curve_normalized(curve_data, n_questions, n_points=200)

        ax.plot(x * 100, avg, color=color, linewidth=2.0, label="Ours", zorder=3)
        ax.fill_between(x * 100, np.clip(avg - std, 0, 1), np.clip(avg + std, 0, 1),
                        alpha=0.15, color=color, zorder=2)

        # Mark initial coverage
        init_cov = float(avg[0])
        ax.plot(0, init_cov, "o", color=COLORS["init"], markersize=6, zorder=5)
        ax.annotate("Init: {:.1%}".format(init_cov),
                    xy=(0, init_cov), xytext=(15, init_cov + 0.08),
                    fontsize=8, color=COLORS["init"],
                    arrowprops=dict(arrowstyle="->", color=COLORS["init"], lw=0.8),
                    zorder=5)

        # Placeholder for Random baseline
        ax.plot([], [], "--", color="gray", linewidth=1.5, label="Random (TBD)", alpha=0.5)

        # AUC
        auc = compute_auc(x, avg)
        auc_values[label] = auc
        ax.text(0.97, 0.05, "AUC = {:.4f}".format(auc),
                transform=ax.transAxes, fontsize=9,
                ha="right", va="bottom",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                          edgecolor=color, alpha=0.8))

        ax.set_xlabel("Question Budget (%)")
        ax.set_title(label)
        ax.set_ylim(-0.02, 1.05)
        ax.set_xlim(-2, 102)
        ax.legend(loc="lower right", framealpha=0.9)

    axes[0].set_ylabel("Average Coverage Rate")

    fig.suptitle("RQ2: Coverage Rate vs. Normalized Question Budget",
                 fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()

    out_path = os.path.join(output_dir, "rq2_normalized_coverage.{}".format(fmt))
    fig.savefig(out_path, format=fmt, bbox_inches="tight")
    plt.close(fig)
    print("Saved: {}".format(out_path))
    return auc_values


def plot_individual_levels(data, output_dir, fmt="pdf"):
    """Plot individual L0/L1/L2 charts (larger, more detailed)."""
    n_questions = data["n_questions"]
    median_q = int(np.median(n_questions[n_questions > 0]))
    p90_q = int(np.percentile(n_questions[n_questions > 0], 90))
    max_x = min(p90_q, data["curves_l2"].shape[1])

    level_configs = [
        ("L0 (Object Coverage)", data["curves_l0"], COLORS["ours_l0"], "rq2_l0_coverage"),
        ("L1 (Relationship Coverage)", data["curves_l1"], COLORS["ours_l1"], "rq2_l1_coverage"),
        ("L2 (Triple Coverage)", data["curves_l2"], COLORS["ours_l2"], "rq2_l2_coverage"),
    ]

    for title, curve_data, color, fname in level_configs:
        fig, ax = plt.subplots(1, 1, figsize=(7, 4.5))

        x, avg, std, _ = compute_avg_curve_absolute(curve_data, n_questions, max_x)

        ax.plot(x, avg, color=color, linewidth=2.0, label="Ours", zorder=3)
        ax.fill_between(x, np.clip(avg - std, 0, 1), np.clip(avg + std, 0, 1),
                        alpha=0.15, color=color, zorder=2)

        # Initial coverage
        init_cov = float(avg[0])
        ax.plot(0, init_cov, "o", color=COLORS["init"], markersize=7, zorder=5)
        ax.annotate("Initial: {:.2%}".format(init_cov),
                    xy=(0, init_cov), xytext=(max_x * 0.12, init_cov + 0.10),
                    fontsize=9, color=COLORS["init"],
                    arrowprops=dict(arrowstyle="->", color=COLORS["init"], lw=1.0),
                    zorder=5)

        # Placeholder for random
        ax.plot([], [], "--", color="gray", linewidth=1.5, label="Random (TBD)", alpha=0.5)

        # AUC
        auc = compute_auc(x.astype(float), avg)
        ax.text(0.97, 0.05, "AUC = {:.4f}".format(auc),
                transform=ax.transAxes, fontsize=10,
                ha="right", va="bottom",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                          edgecolor=color, alpha=0.9))

        # Stats annotation
        n_frames = curve_data.shape[0]
        avg_q = np.mean(n_questions)
        ax.text(0.97, 0.18, "Frames: {}\nAvg Q/frame: {:.0f}".format(n_frames, avg_q),
                transform=ax.transAxes, fontsize=8,
                ha="right", va="bottom", color="gray")

        ax.set_xlabel("Number of Generated Questions", fontsize=11)
        ax.set_ylabel("Average Coverage Rate", fontsize=11)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_ylim(-0.02, 1.05)
        ax.legend(loc="center right", framealpha=0.9, fontsize=10)

        def x_formatter(val, pos):
            if val >= 1000:
                return "{:.0f}K".format(val / 1000)
            return "{:.0f}".format(val)
        ax.xaxis.set_major_formatter(FuncFormatter(x_formatter))

        plt.tight_layout()
        out_path = os.path.join(output_dir, "{}.{}".format(fname, fmt))
        fig.savefig(out_path, format=fmt, bbox_inches="tight")
        plt.close(fig)
        print("Saved: {}".format(out_path))


def generate_summary_table(data, auc_abs, auc_norm, output_dir):
    """Generate summary statistics table."""
    n_questions = data["n_questions"]
    n_frames = len(n_questions)

    # Per-frame final coverage rates
    final_l0 = np.array([data["curves_l0"][i, n_questions[i]] if n_questions[i] > 0 else data["curves_l0"][i, 0] for i in range(n_frames)])
    final_l1 = np.array([data["curves_l1"][i, n_questions[i]] if n_questions[i] > 0 else data["curves_l1"][i, 0] for i in range(n_frames)])
    final_l2 = np.array([data["curves_l2"][i, n_questions[i]] if n_questions[i] > 0 else data["curves_l2"][i, 0] for i in range(n_frames)])

    # Initial coverage rates
    init_l0 = data["curves_l0"][:, 0]
    init_l1 = data["curves_l1"][:, 0]
    init_l2 = data["curves_l2"][:, 0]

    # Average new L2 per question (delta_l2 / n_questions)
    # Not directly available, compute from final - initial coverage count
    # For now, use available data

    table = [
        ["Metric", "Ours", "Random (TBD)"],
        ["Total Frames", str(n_frames), "-"],
        ["Total Questions", "{:,}".format(int(np.sum(n_questions))), "-"],
        ["Avg Questions/Frame", "{:,.0f}".format(np.mean(n_questions)), "-"],
        ["", "", ""],
        ["Avg Initial L0 Coverage", "{:.2%}".format(np.mean(init_l0)), "-"],
        ["Avg Initial L1 Coverage", "{:.2%}".format(np.mean(init_l1)), "-"],
        ["Avg Initial L2 Coverage", "{:.2%}".format(np.mean(init_l2)), "-"],
        ["", "", ""],
        ["Avg Final L0 Coverage", "{:.2%}".format(np.mean(final_l0)), "-"],
        ["Avg Final L1 Coverage", "{:.2%}".format(np.mean(final_l1)), "-"],
        ["Avg Final L2 Coverage", "{:.2%}".format(np.mean(final_l2)), "-"],
        ["", "", ""],
        ["AUC L0 (Absolute)", "{:.4f}".format(auc_abs.get("L0 (Object)", 0)), "-"],
        ["AUC L1 (Absolute)", "{:.4f}".format(auc_abs.get("L1 (Relationship)", 0)), "-"],
        ["AUC L2 (Absolute)", "{:.4f}".format(auc_abs.get("L2 (Triple)", 0)), "-"],
        ["", "", ""],
        ["AUC L0 (Normalized)", "{:.4f}".format(auc_norm.get("L0 (Object)", 0)), "-"],
        ["AUC L1 (Normalized)", "{:.4f}".format(auc_norm.get("L1 (Relationship)", 0)), "-"],
        ["AUC L2 (Normalized)", "{:.4f}".format(auc_norm.get("L2 (Triple)", 0)), "-"],
    ]

    out_path = os.path.join(output_dir, "rq2_summary_table.csv")
    with open(out_path, "w") as f:
        writer = csv.writer(f)
        for row in table:
            writer.writerow(row)
    print("Saved: {}".format(out_path))

    # Print table to console
    print("\n=== RQ2 Summary ===")
    for row in table:
        print("  {:<30s} {:<15s} {:<15s}".format(*row))


def main():
    parser = argparse.ArgumentParser(description="Plot RQ2 coverage charts")
    parser.add_argument("--input", type=str,
                        default=os.path.join(os.path.dirname(__file__), "extracted"),
                        help="Input directory with extracted data")
    parser.add_argument("--output", type=str,
                        default=os.path.join(os.path.dirname(__file__), "figures"),
                        help="Output directory for figures")
    parser.add_argument("--format", type=str, default="png", choices=["pdf", "png"],
                        help="Output format")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print("Loading data from {}".format(args.input))
    data = load_data(args.input)
    n_frames = data["curves_l2"].shape[0]
    max_q = data["meta"]["max_questions"]
    print("Loaded {} frames, max_questions={}".format(n_frames, max_q))

    # Plot combined charts
    print("\n--- Absolute X-axis charts ---")
    auc_abs = plot_absolute_combined(data, args.output, args.format)

    print("\n--- Normalized X-axis charts ---")
    auc_norm = plot_normalized_combined(data, args.output, args.format)

    # Plot individual charts
    print("\n--- Individual level charts ---")
    plot_individual_levels(data, args.output, args.format)

    # Summary table
    generate_summary_table(data, auc_abs, auc_norm, args.output)


if __name__ == "__main__":
    main()
