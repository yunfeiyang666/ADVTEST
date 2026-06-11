import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

OUTPUTS = Path("E:/Project/ADVTEST/1号机代码/DATA_new/outputs")
ANALYSIS = Path("E:/Project/ADVTEST/1号机代码/DATA_new/analysis")
FIGURES = ANALYSIS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)
CACHE = ANALYSIS / "data_cache"

def generate_d1_plots(sample_size=200):
    print("[D1] Generating coverage rate curves...")
    frame_stats_path = CACHE / "frame_stats.csv"
    if not frame_stats_path.exists():
        print("[D1] Error: frame_stats.csv not found")
        return
        
    df = pd.read_csv(frame_stats_path)
    # Filter to frames that actually generated questions
    valid = df[df["generated"] > 0].copy()
    
    colors = {"l0": "tab:blue", "l1": "tab:orange", "l2": "tab:red"}
    levels = ["l0", "l1", "l2"]
    groups = ["S", "M", "L"]
    
    # Grid sizes for absolute plots
    absolute_limits = {
        "S": 1146,
        "M": 9858,
        "L": 81298
    }
    
    for group in groups:
        group_df = valid[valid["size_group"] == group]
        if len(group_df) > sample_size:
            sampled_df = group_df.sample(sample_size, random_state=42)
        else:
            sampled_df = group_df
            
        print(f"  Group {group}: loaded {len(sampled_df)} frames for curve calculation.")
        
        # We will collect data for interpolation
        # 1. Budget% grid (100 points)
        grid_budget = np.linspace(0, 1, 100)
        budget_curves = {lvl: [] for lvl in levels}
        
        # 2. Absolute step grid (100 points up to P95 limit)
        max_abs = absolute_limits[group]
        grid_abs = np.linspace(0, max_abs, 100)
        abs_curves = {lvl: [] for lvl in levels}
        
        for _, row in sampled_df.iterrows():
            csv_path = OUTPUTS / row["frame_name"] / "reports" / f"{row['frame_name']}_incremental_coverage.csv"
            if not csv_path.exists():
                continue
                
            try:
                cdf = pd.read_csv(csv_path)
                if cdf.empty:
                    continue
                
                # Fetch initial coverage rate from row
                init_rates = {
                    "l0": row["init_rate_l0"],
                    "l1": row["init_rate_l1"],
                    "l2": row["init_rate_l2"]
                }
                
                for lvl in levels:
                    col = f"coverage_rate_{lvl}"
                    # Prep data: step 0 has initial rate
                    steps = np.zeros(len(cdf) + 1)
                    rates = np.zeros(len(cdf) + 1)
                    
                    steps[0] = 0
                    rates[0] = init_rates[lvl]
                    
                    steps[1:] = cdf["order_index"].values
                    rates[1:] = cdf[col].values
                    
                    # Normalized budget interpolation
                    norm_steps = steps / steps[-1] if steps[-1] > 0 else steps
                    budget_y = np.interp(grid_budget, norm_steps, rates)
                    budget_curves[lvl].append(budget_y)
                    
                    # Absolute step interpolation (with padding at final rate)
                    abs_y = np.interp(grid_abs, steps, rates)
                    abs_curves[lvl].append(abs_y)
            except Exception as e:
                # print(f"Error loading {row['frame_name']}: {e}")
                pass
                
        # Now plot for each level
        for lvl in levels:
            lvl_name = lvl.upper()
            color = colors[lvl]
            
            # --- Plot Budget% (Normalized) ---
            b_data = np.array(budget_curves[lvl])
            if len(b_data) > 0:
                b_mean = np.mean(b_data, axis=0)
                b_std = np.std(b_data, axis=0)
                # Compute AUC (simple trapezoidal rule over [0,1])
                auc_val = np.trapz(b_mean, grid_budget)
                
                plt.figure(figsize=(6, 5))
                plt.plot(grid_budget * 100, b_mean, label=f"Mean {lvl_name}", color=color, linewidth=2)
                plt.fill_between(grid_budget * 100, np.clip(b_mean - b_std, 0, 1), np.clip(b_mean + b_std, 0, 1), color=color, alpha=0.15, label="±1 Std Dev")
                plt.xlim(0, 100)
                plt.ylim(0, 1.05)
                plt.xlabel("Budget %")
                plt.ylabel("Coverage Rate")
                plt.title(f"Group {group} - {lvl_name} Coverage (Normalized)\nAUC = {auc_val:.4f}")
                plt.grid(True, linestyle="--", alpha=0.5)
                plt.legend(loc="lower right")
                plt.tight_layout()
                
                out_path = FIGURES / f"D1_Budget_{group}_{lvl_name}.png"
                plt.savefig(out_path, dpi=300)
                plt.close()
                
            # --- Plot Absolute Steps ---
            a_data = np.array(abs_curves[lvl])
            if len(a_data) > 0:
                a_mean = np.mean(a_data, axis=0)
                a_std = np.std(a_data, axis=0)
                # Compute AUC relative to max_abs
                auc_val = np.trapz(a_mean, grid_abs) / max_abs if max_abs > 0 else 0
                
                plt.figure(figsize=(6, 5))
                plt.plot(grid_abs, a_mean, label=f"Mean {lvl_name}", color=color, linewidth=2)
                plt.fill_between(grid_abs, np.clip(a_mean - a_std, 0, 1), np.clip(a_mean + a_std, 0, 1), color=color, alpha=0.15, label="±1 Std Dev")
                plt.xlim(0, max_abs)
                plt.ylim(0, 1.05)
                plt.xlabel("Number of Questions")
                plt.ylabel("Coverage Rate")
                plt.title(f"Group {group} - {lvl_name} Coverage (Absolute)\nNormalized AUC = {auc_val:.4f}")
                plt.grid(True, linestyle="--", alpha=0.5)
                plt.legend(loc="lower right")
                plt.tight_layout()
                
                out_path = FIGURES / f"D1_Absolute_{group}_{lvl_name}.png"
                plt.savefig(out_path, dpi=300)
                plt.close()

    print("[D1] Finished generating 18 curves.")

if __name__ == "__main__":
    generate_d1_plots()
