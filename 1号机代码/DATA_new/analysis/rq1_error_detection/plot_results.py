import json
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Paths
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
ANALYSIS_DIR = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "analysis"
CACHE_FILE = ANALYSIS_DIR / "data_cache" / "rq1_results.json"
OUT_DIR = ANALYSIS_DIR / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Styling setup consistent with RQ2
PLOT_STYLE = {
    "font.family": "serif",
    "font.size": 8,
    "axes.labelsize": 9,
    "axes.titlesize": 9,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "lines.linewidth": 1.5,
    "figure.dpi": 150,
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.5,
    "grid.linestyle": "--",
}
plt.rcParams.update(PLOT_STYLE)

# Distinct styles for the 4 methods
METHOD_STYLES = {
    "Ours (Complete)":  {"color": "#1f77b4", "marker": "o", "linestyle": "-"},
    "Ours-Random":       {"color": "#ff7f0e", "marker": "x", "linestyle": "--"},
    "Qatest":            {"color": "#2ca02c", "marker": "^", "linestyle": ":"},
    "Recursive Asking":  {"color": "#d62728", "marker": "s", "linestyle": "-."}
}

def load_data():
    if not CACHE_FILE.exists():
        print(f"Error: Cache file {CACHE_FILE} does not exist. Run run_experiment.py first.")
        sys.exit(1)
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)["summary"]

def main():
    data = load_data()
    results = data["results"]
    num_frames = data["num_frames"]
    mode = data["mode"]

    print(f"Plotting results for {num_frames} frames evaluated under {mode} mode...")

    # --- Plot 1: Wrong Questions Count (Failures Detected) ---
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    for method, stats in results.items():
        budgets = [item["budget"] for item in stats]
        avg_wrongs = [item["avg_wrong"] for item in stats]
        
        style = METHOD_STYLES.get(method, {"color": "#7f7f7f", "marker": "d", "linestyle": "-"})
        ax.plot(
            budgets, avg_wrongs, 
            label=method, 
            color=style["color"], 
            marker=style["marker"], 
            linestyle=style["linestyle"],
            markersize=4
        )
        
    ax.set_xlabel("Question Budget ($B$)")
    ax.set_ylabel("Avg. Failures Detected")
    ax.set_title("VLM Failures vs. Question Budget")
    ax.legend(loc="upper left")
    
    png_path = OUT_DIR / "rq1_failures_detected.png"
    pdf_path = OUT_DIR / "rq1_failures_detected.pdf"
    fig.savefig(png_path)
    fig.savefig(pdf_path)
    plt.close(fig)
    print(f"Saved: {png_path} and {pdf_path}")

    # --- Plot 2: Object Involvement Coverage ---
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    for method, stats in results.items():
        budgets = [item["budget"] for item in stats]
        avg_involvement = [item["avg_involvement"] * 100 for item in stats]  # Convert to percentage
        
        style = METHOD_STYLES.get(method, {"color": "#7f7f7f", "marker": "d", "linestyle": "-"})
        ax.plot(
            budgets, avg_involvement, 
            label=method, 
            color=style["color"], 
            marker=style["marker"], 
            linestyle=style["linestyle"],
            markersize=4
        )
        
    ax.set_xlabel("Question Budget ($B$)")
    ax.set_ylabel("Avg. Object Involvement Rate (%)")
    ax.set_title("Object Involvement Rate vs. Budget")
    ax.legend(loc="upper left")
    
    png_path = OUT_DIR / "rq1_object_involvement.png"
    pdf_path = OUT_DIR / "rq1_object_involvement.pdf"
    fig.savefig(png_path)
    fig.savefig(pdf_path)
    plt.close(fig)
    print(f"Saved: {png_path} and {pdf_path}")
    
    print("Plotting complete.")

if __name__ == "__main__":
    main()
