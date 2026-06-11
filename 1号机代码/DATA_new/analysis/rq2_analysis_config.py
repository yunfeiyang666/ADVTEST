"""Shared config for RQ2 analysis pipeline."""
import os
from pathlib import Path

OUTPUTS_ROOT = "E:/Project/ADVTEST/1号机代码/DATA_new/outputs"
ALL_FRAMES_CSV = os.path.join(OUTPUTS_ROOT, "all_frames_stats.csv")

PLOTS_DIR = Path(__file__).parent
EXTRACTED_R1 = PLOTS_DIR / "data_cache/extracted_v2_r1"
EXTRACTED_FULL = PLOTS_DIR / "data_cache/extracted_v2"
OUT_DIR = PLOTS_DIR / "figures"

ROUND1_FAMILIES = {"converge", "diverge_compare"}
ROUND2_FAMILIES = {"direction_chain", "distance_chain", "viewpoint_transfer"}
ALL_FAMILIES = ["converge", "direction_chain", "distance_chain", "viewpoint_transfer", "diverge_compare"]

# Groups per analysis plan
GROUPS = {
    "S(3-15)":  {"min": 3,  "max": 15},
    "M(16-30)": {"min": 16, "max": 30},
    "L(≥31)":   {"min": 31, "max": 9999},
    "All(≥3)":  {"min": 3,  "max": 9999},
}

# Plot style — SE top conference (ISSTA/ICSE/FSE/ASE)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PLOT_STYLE = {
    "font.family": "serif",
    "font.size": 8,
    "axes.labelsize": 9,
    "axes.titlesize": 9,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "lines.linewidth": 1.5,
    "figure.dpi": 150,      # preview; save at 600
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.5,
    "grid.linestyle": "--",
}
plt.rcParams.update(PLOT_STYLE)

# Color palette — colorblind-friendly tab10 first 6
COLORS = {
    "All(≥3)":  "#1f77b4",
    "S(3-15)":  "#ff7f0e",
    "M(16-30)": "#2ca02c",
    "L(≥31)":   "#d62728",
    "L0": "#2ca02c",
    "L1": "#d62728",
    "L2": "#1f77b4",
    "converge":           "#1f77b4",
    "direction_chain":    "#ff7f0e",
    "distance_chain":     "#2ca02c",
    "viewpoint_transfer": "#d62728",
    "diverge_compare":    "#9467bd",
}

FIG_W_SINGLE = 3.5   # inches, single column
FIG_W_DOUBLE = 7.16  # inches, double column
