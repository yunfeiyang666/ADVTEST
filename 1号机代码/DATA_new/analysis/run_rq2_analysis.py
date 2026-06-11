import os
import json
import csv
import time
import collections
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import linregress

OUTPUTS = Path("E:/Project/ADVTEST/1号机代码/DATA_new/outputs")
ANALYSIS = Path("E:/Project/ADVTEST/1号机代码/DATA_new/analysis")
FIGURES = ANALYSIS / "figures"
CACHE = ANALYSIS / "data_cache"

def load_frame_stats():
    return pd.read_csv(CACHE / "frame_stats.csv")

def analyze_d2_d3_k(df, sample_size=200):
    print("[D2/D3/K] Analyzing decay, family contribution, and K-value...")
    valid = df[df["generated"] > 0].copy()
    
    # Intervals for D2
    intervals = [
        (0.0, 0.10, "0-10%"),
        (0.10, 0.25, "10-25%"),
        (0.25, 0.50, "25-50%"),
        (0.50, 0.75, "50-75%"),
        (0.75, 0.90, "75-90%"),
        (0.90, 1.01, "90-100%")
    ]
    
    # We will accumulate results per group
    d2_results = {g: {label: {"l0": [], "l1": [], "l2": []} for _, _, label in intervals} for g in ["S", "M", "L"]}
    d2_family_contrib = {g: {label: collections.Counter() for _, _, label in intervals} for g in ["S", "M", "L"]}
    
    d3_family_counts = {g: {"phase1": collections.Counter(), "phase2": collections.Counter()} for g in ["S", "M", "L"]}
    d3_family_gains = {g: {"phase1": collections.defaultdict(list), "phase2": collections.defaultdict(list)} for g in ["S", "M", "L"]}
    d3_slot_counts = {g: collections.Counter() for g in ["S", "M", "L"]}
    
    k_values = {g: [] for g in ["S", "M", "L"]}
    
    for group in ["S", "M", "L"]:
        group_df = valid[valid["size_group"] == group]
        if len(group_df) > sample_size:
            sampled_df = group_df.sample(sample_size, random_state=42)
        else:
            sampled_df = group_df
            
        for _, row in sampled_df.iterrows():
            frame_name = row["frame_name"]
            csv_path = OUTPUTS / frame_name / "reports" / f"{frame_name}_incremental_coverage.csv"
            summary_path = OUTPUTS / frame_name / "reports" / f"{frame_name}_summary.json"
            
            if not csv_path.exists():
                continue
                
            try:
                cdf = pd.read_csv(csv_path)
                if cdf.empty:
                    continue
                
                # --- D2: Decay by intervals ---
                for low, high, label in intervals:
                    # Filter questions belonging to this coverage rate interval
                    mask = (cdf["coverage_rate_l2"] >= low) & (cdf["coverage_rate_l2"] < high)
                    sub = cdf[mask]
                    if not sub.empty:
                        q_count = len(sub)
                        d2_results[group][label]["l0"].append(sub["delta_l0"].sum() / q_count)
                        d2_results[group][label]["l1"].append(sub["delta_l1"].sum() / q_count)
                        d2_results[group][label]["l2"].append(sub["delta_l2"].sum() / q_count)
                        
                        # Family counts in this interval
                        counts = sub["l2_family"].value_counts()
                        for fam, cnt in counts.items():
                            d2_family_contrib[group][label][fam] += cnt
                
                # --- D3: Family & Phase Analysis ---
                records = cdf[["selection_phase", "l2_family", "delta_l2"]].to_dict("records")
                for qrow in records:
                    phase = "phase1" if qrow["selection_phase"] == "primary" else "phase2"
                    fam = qrow["l2_family"]
                    d3_family_counts[group][phase][fam] += 1
                    d3_family_gains[group][phase][fam].append(qrow["delta_l2"])
                    
                # --- D3 Slot Counts ---
                if summary_path.exists():
                    with open(summary_path, encoding="utf-8") as f:
                        s = json.load(f)
                        slots = s.get("universe_stats", {}).get("phase2_slot_counts", {})
                        for slot, count in slots.items():
                            d3_slot_counts[group][slot] += count
                            
                # --- K-value (plateau switch point) ---
                p1_df = cdf[cdf["selection_phase"] == "primary"]
                if not p1_df.empty:
                    k_values[group].append(p1_df["coverage_rate_l2"].iloc[-1])
                    
            except Exception as e:
                pass
                
    # --- Process and plot D2 ---
    print("  Plotting D2...")
    d2_tables = {}
    for group in ["S", "M", "L"]:
        plt.figure(figsize=(7, 5))
        x_labels = [label for _, _, label in intervals]
        y_l0 = [np.mean(d2_results[group][lbl]["l0"]) if d2_results[group][lbl]["l0"] else 0 for lbl in x_labels]
        y_l1 = [np.mean(d2_results[group][lbl]["l1"]) if d2_results[group][lbl]["l1"] else 0 for lbl in x_labels]
        y_l2 = [np.mean(d2_results[group][lbl]["l2"]) if d2_results[group][lbl]["l2"] else 0 for lbl in x_labels]
        
        plt.plot(x_labels, y_l0, marker="o", label="L0 Gaps/Q", color="tab:blue", linewidth=2)
        plt.plot(x_labels, y_l1, marker="s", label="L1 Gaps/Q", color="tab:orange", linewidth=2)
        plt.plot(x_labels, y_l2, marker="d", label="L2 Gaps/Q", color="tab:red", linewidth=2)
        plt.yscale("log")
        plt.xlabel("L2 Coverage Progress Interval")
        plt.ylabel("Avg Gaps Covered per Question (Log Scale)")
        plt.title(f"Group {group} - Coverage Decay Analysis")
        plt.grid(True, which="both", linestyle="--", alpha=0.5)
        plt.legend()
        plt.tight_layout()
        plt.savefig(FIGURES / f"D2_Decay_{group}.png", dpi=300)
        plt.close()
        
        # Save table data
        d2_tables[group] = pd.DataFrame({
            "Interval": x_labels,
            "L0 Gaps/Q": y_l0,
            "L1 Gaps/Q": y_l1,
            "L2 Gaps/Q": y_l2
        })
        
        # D2 Stacked bar charts (family contribution by interval)
        plt.figure(figsize=(8, 5))
        families_list = ["converge", "diverge_compare", "direction_chain", "distance_chain", "viewpoint_transfer"]
        bottom = np.zeros(len(intervals))
        
        for fam in families_list:
            vals = []
            for _, _, lbl in intervals:
                total = sum(d2_family_contrib[group][lbl].values())
                vals.append(d2_family_contrib[group][lbl][fam] / total if total > 0 else 0)
            plt.bar(x_labels, vals, bottom=bottom, label=fam, alpha=0.85)
            bottom += np.array(vals)
            
        plt.xlabel("L2 Coverage Progress Interval")
        plt.ylabel("Question Family Share")
        plt.title(f"Group {group} - Question Family Share by Interval")
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.tight_layout()
        plt.savefig(FIGURES / f"D2_Family_Share_{group}.png", dpi=300)
        plt.close()
        
    # --- Process and plot D3 ---
    print("  Plotting D3...")
    for group in ["S", "M", "L"]:
        # Phase 1 vs Phase 2 Family share
        p1_total = sum(d3_family_counts[group]["phase1"].values())
        p2_total = sum(d3_family_counts[group]["phase2"].values())
        
        families_list = ["converge", "diverge_compare", "direction_chain", "distance_chain", "viewpoint_transfer"]
        p1_shares = [d3_family_counts[group]["phase1"][f] / p1_total if p1_total > 0 else 0 for f in families_list]
        p2_shares = [d3_family_counts[group]["phase2"][f] / p2_total if p2_total > 0 else 0 for f in families_list]
        
        x = np.arange(len(families_list))
        width = 0.35
        
        plt.figure(figsize=(8, 5))
        plt.bar(x - width/2, p1_shares, width, label="Phase 1 (Primary)", color="tab:blue")
        plt.bar(x + width/2, p2_shares, width, label="Phase 2 (Backfill)", color="tab:green")
        plt.xticks(x, families_list, rotation=15)
        plt.ylabel("Share of Questions")
        plt.title(f"Group {group} - Question Family Distribution by Phase")
        plt.legend()
        plt.tight_layout()
        plt.savefig(FIGURES / f"D3_Family_Phase_Share_{group}.png", dpi=300)
        plt.close()
        
        # Family gains (L2 Gaps/Q) by Phase
        p1_gains = [np.mean(d3_family_gains[group]["phase1"][f]) if d3_family_gains[group]["phase1"][f] else 0 for f in families_list]
        p2_gains = [np.mean(d3_family_gains[group]["phase2"][f]) if d3_family_gains[group]["phase2"][f] else 0 for f in families_list]
        
        plt.figure(figsize=(8, 5))
        plt.bar(x - width/2, p1_gains, width, label="Phase 1", color="tab:blue")
        plt.bar(x + width/2, p2_gains, width, label="Phase 2", color="tab:green")
        plt.xticks(x, families_list, rotation=15)
        plt.ylabel("Avg L2 Gaps Covered / Question")
        plt.title(f"Group {group} - L2 Coverage Ability by Family")
        plt.legend()
        plt.tight_layout()
        plt.savefig(FIGURES / f"D3_Family_Coverage_Ability_{group}.png", dpi=300)
        plt.close()
        
    # Grouped bar chart for Slot counts in Phase 2
    plt.figure(figsize=(7, 5))
    slots = ["A", "B", "C", "D"]
    x = np.arange(len(slots))
    width = 0.25
    for i, group in enumerate(["S", "M", "L"]):
        counts = [d3_slot_counts[group][s] for s in slots]
        plt.bar(x + (i - 1) * width, counts, width, label=f"Group {group}")
    plt.xticks(x, slots)
    plt.ylabel("Total Questions")
    plt.xlabel("Slot")
    plt.title("Slot Balancing in Phase 2 Across Groups")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIGURES / "D3_Slot_Counts.png", dpi=300)
    plt.close()
    
    # --- K-value boxplot ---
    plt.figure(figsize=(6, 5))
    k_data = [k_values[g] for g in ["S", "M", "L"]]
    plt.boxplot(k_data, labels=["Group S", "Group M", "Group L"])
    plt.ylabel("L2 Coverage at Phase Switch Point (K)")
    plt.title("Distribution of Phase 1→2 Switch Points (K)")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(FIGURES / "K_Value_Switch_Points.png", dpi=300)
    plt.close()
    
    return d2_tables, k_values

def analyze_d7(df):
    print("[D7] Analyzing Node Scalability...")
    valid = df[df["generated"] > 0].copy()
    
    log_n = np.log10(valid["n_objects"])
    log_q = np.log10(valid["generated"])
    
    # Drop NaNs or infinite values if any
    mask = np.isfinite(log_n) & np.isfinite(log_q)
    log_n = log_n[mask]
    log_q = log_q[mask]
    
    slope, intercept, r_value, p_value, std_err = linregress(log_n, log_q)
    
    plt.figure(figsize=(6, 5))
    plt.scatter(valid["n_objects"], valid["generated"], alpha=0.3, color="tab:blue", edgecolors="none")
    
    # Fit line
    n_fit = np.logspace(np.log10(max(1, valid["n_objects"].min())), np.log10(valid["n_objects"].max()), 100)
    q_fit = 10**intercept * (n_fit**slope)
    plt.plot(n_fit, q_fit, color="tab:red", linewidth=2, label=f"Fit: Q = {10**intercept:.2f} * N^{slope:.2f}")
    
    plt.xscale("log")
    plt.yscale("log")
    plt.xlabel("Number of Objects (N)")
    plt.ylabel("Generated Questions (Q)")
    plt.title(f"Node Scalability: Q vs N\nR^2 = {r_value**2:.4f}")
    plt.legend()
    plt.grid(True, which="both", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(FIGURES / "D7_Scalability_Fit.png", dpi=300)
    plt.close()
    
    return slope, 10**intercept, r_value**2

def analyze_d9(df):
    print("[D9] Analyzing timing stats...")
    timing_stats = {}
    for group in ["S", "M", "L"]:
        group_df = df[df["size_group"] == group]
        timing_stats[group] = {
            "precompute_mean": group_df["precompute_ms"].mean(),
            "plan_cache_mean": group_df["plan_cache_ms"].mean(),
            "selection_gen_mean": group_df["selection_gen_ms"].mean(),
            "total_mean": group_df["total_ms"].mean(),
            "precompute_p95": group_df["precompute_ms"].quantile(0.95),
            "plan_cache_p95": group_df["plan_cache_ms"].quantile(0.95),
            "selection_gen_p95": group_df["selection_gen_ms"].quantile(0.95),
            "total_p95": group_df["total_ms"].quantile(0.95),
            "throughput": group_df["generated"].sum() / (group_df["total_ms"].sum() / 1000.0) if group_df["total_ms"].sum() > 0 else 0
        }
        
    # Plot stacked bar chart of stage timings
    plt.figure(figsize=(7, 5))
    groups = ["S", "M", "L"]
    precompute = [timing_stats[g]["precompute_mean"] for g in groups]
    plan_cache = [timing_stats[g]["plan_cache_mean"] for g in groups]
    selection_gen = [timing_stats[g]["selection_gen_mean"] for g in groups]
    
    plt.bar(groups, precompute, label="Precompute", color="tab:blue")
    plt.bar(groups, plan_cache, bottom=precompute, label="Plan Cache", color="tab:orange")
    plt.bar(groups, selection_gen, bottom=np.array(precompute)+np.array(plan_cache), label="Selection & realization", color="tab:green")
    
    plt.ylabel("Time (ms)")
    plt.xlabel("Group")
    plt.title("Pipeline Execution Time Breakdown")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIGURES / "D9_Timing_Breakdown.png", dpi=300)
    plt.close()
    
    # Plot throughput
    plt.figure(figsize=(6, 5))
    throughputs = [timing_stats[g]["throughput"] for g in groups]
    plt.bar(groups, throughputs, color="tab:purple", width=0.5)
    plt.ylabel("Throughput (Questions / sec)")
    plt.xlabel("Group")
    plt.title("Pipeline Throughput Across Groups")
    plt.grid(True, axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(FIGURES / "D9_Throughput.png", dpi=300)
    plt.close()
    
    return timing_stats

def analyze_auxiliary(df, num_json_samples=50):
    print("[AUX] Analyzing Ego participation, Answer type distribution, and Cross-frame overlap...")
    
    # D11 & D13: Sample some generated JSONLs
    valid = df[df["generated"] > 0].copy()
    ego_counts = {"S": 0, "M": 0, "L": 0}
    ego_totals = {"S": 0, "M": 0, "L": 0}
    
    answer_types = {"S": collections.Counter(), "M": collections.Counter(), "L": collections.Counter()}
    
    for group in ["S", "M", "L"]:
        group_df = valid[valid["size_group"] == group]
        if len(group_df) > num_json_samples:
            samples = group_df.sample(num_json_samples, random_state=42)
        else:
            samples = group_df
            
        for _, row in samples.iterrows():
            gen_file = OUTPUTS / row["frame_name"] / "generation" / "qa" / f"{row['frame_name']}_generated.jsonl"
            if gen_file.exists():
                try:
                    with open(gen_file, encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            qa = json.loads(line)
                            ego_totals[group] += 1
                            # check ego in path_pattern
                            path = str(qa.get("path_pattern", ""))
                            if "ego" in path.lower():
                                ego_counts[group] += 1
                            # check answer type
                            atype = qa.get("answer_type", "unknown")
                            answer_types[group][atype] += 1
                except Exception:
                    pass
                    
    ego_rates = {g: ego_counts[g] / ego_totals[g] if ego_totals[g] > 0 else 0 for g in ["S", "M", "L"]}
    
    # D15: Cross-frame overlap within scene
    # Group frames by scene_id and sort by frame_id
    scene_frames = collections.defaultdict(list)
    for _, row in valid.iterrows():
        scene_frames[row["scene_id"]].append(row)
        
    jaccards = []
    # Sample 20 scenes with at least 2 frames
    multi_frame_scenes = [sid for sid, rlist in scene_frames.items() if len(rlist) >= 2]
    sampled_scenes = np.random.choice(multi_frame_scenes, min(20, len(multi_frame_scenes)), replace=False)
    
    for sid in sampled_scenes:
        flist = sorted(scene_frames[sid], key=lambda r: r["frame_id"])
        # Compare adjacent frames
        for i in range(len(flist) - 1):
            f1, f2 = flist[i], flist[i+1]
            
            # Read covered L2 paths
            csv1 = OUTPUTS / f1["frame_name"] / "reports" / f"{f1['frame_name']}_incremental_coverage.csv"
            csv2 = OUTPUTS / f2["frame_name"] / "reports" / f"{f2['frame_name']}_incremental_coverage.csv"
            
            if csv1.exists() and csv2.exists():
                try:
                    # In CSV, we can collect the L2 paths generated by looking at l2_family / question / order_index.
                    # Wait! Since we don't write path lists to CSV, let's load JSONLs for adjacent frames.
                    json1 = OUTPUTS / f1["frame_name"] / "generation" / "qa" / f"{f1['frame_name']}_generated.jsonl"
                    json2 = OUTPUTS / f2["frame_name"] / "generation" / "qa" / f"{f2['frame_name']}_generated.jsonl"
                    
                    l2_set1 = set()
                    l2_set2 = set()
                    
                    with open(json1, encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            l2_set1.update(json.loads(line).get("coverage_footprint", {}).get("l2", []))
                            
                    with open(json2, encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            l2_set2.update(json.loads(line).get("coverage_footprint", {}).get("l2", []))
                            
                    if l2_set1 and l2_set2:
                        jaccard = len(l2_set1.intersection(l2_set2)) / len(l2_set1.union(l2_set2))
                        jaccards.append(jaccard)
                except Exception:
                    pass
                    
    avg_jaccard = np.mean(jaccards) if jaccards else 0
    
    return ego_rates, answer_types, avg_jaccard

def main():
    t_start = time.time()
    
    df = load_frame_stats()
    
    # 1. D2, D3, K-value
    d2_tables, k_values = analyze_d2_d3_k(df)
    
    # 2. D7
    d7_slope, d7_intercept, d7_r2 = analyze_d7(df)
    
    # 3. D9
    d9_stats = analyze_d9(df)
    
    # 4. Auxiliary (D5, D11, D13, D15)
    ego_rates, answer_types, avg_jaccard = analyze_auxiliary(df)
    
    # --- Generate Markdown Report ---
    report_path = ANALYSIS / "rq2_report.md"
    print(f"[Main] Generating markdown report at {report_path}...")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# RQ2 全面数据分析实验报告\n\n")
        f.write(f"> **生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"> **数据集规模**: {len(df)} 帧有效数据，总生成问题数 {df['generated'].sum():,} 个。\n\n")
        
        f.write("## 1. D1: 覆盖率曲线与 AUC\n")
        f.write("已成功绘制 18 张覆盖率变化曲线，并输出在 `analysis/figures/` 目录下：\n")
        f.write("- **Normalized Budget 曲线 (9张)**: `D1_Budget_<Group>_<Level>.png`\n")
        f.write("- **Absolute Question Count 曲线 (9张)**: `D1_Absolute_<Group>_<Level>.png`\n\n")
        
        f.write("## 2. D2: 覆盖衰减与效率 (Avg Gaps/Q)\n")
        f.write("以下展示了在不同的 L2 覆盖进度区间中，平均每个问题能覆盖的新 L0/L1/L2 元素个数：\n\n")
        
        for g in ["S", "M", "L"]:
            f.write(f"### 规模组 {g} 覆盖衰减表\n")
            f.write("| 进度区间 | L0 Gaps/Q | L1 Gaps/Q | L2 Gaps/Q |\n")
            f.write("|---|---|---|---|\n")
            for _, row in d2_tables[g].iterrows():
                f.write(f"| {row['Interval']} | {row['L0 Gaps/Q']:.4f} | {row['L1 Gaps/Q']:.4f} | {row['L2 Gaps/Q']:.4f} |\n")
            f.write("\n")
            
        f.write("## 3. D3: 题型分布与覆盖贡献\n")
        f.write("不同题型（拓扑族）和 Phase 1 (Primary) 与 Phase 2 (Backfill) 阶段的表现已成功绘制在图表中：\n")
        f.write("- `D3_Family_Phase_Share_<Group>.png`: 展示不同 Phase 阶段的各题型占比。\n")
        f.write("- `D3_Family_Coverage_Ability_<Group>.png`: 展示各题型的 L2 覆盖能力（Avg L2 Gaps/Q）。\n")
        f.write("- `D3_Slot_Counts.png`: 展示 Phase 2 四槽平衡性的统计柱状图。\n\n")
        
        f.write("## 4. D7: 节点规模可扩展性拟合\n")
        f.write("基于双对数坐标下的线性拟合 $Q$ vs $N$ 结果：\n")
        f.write(f"- **拟合公式**: $\\log Q = {d7_slope:.4f} \\cdot \\log N + {np.log10(d7_intercept):.4f}$\n")
        f.write(f"- **幂律系数 (指数)**: $a = {d7_slope:.4f}$\n")
        f.write(f"- **拟合决定系数 $R^2$**: ${d7_r2:.4f}$\n")
        f.write("拟合散点图见 `analysis/figures/D7_Scalability_Fit.png`。\n\n")
        
        f.write("## 5. D9: 模块 Timing 与吞吐量分析\n")
        f.write("| 规模组 | Precompute (ms) | Plan Cache (ms) | Selection & Gen (ms) | Total Time (ms) | Throughput (Q/s) |\n")
        f.write("|---|---|---|---|---|---|\n")
        for g in ["S", "M", "L"]:
            stats = d9_stats[g]
            f.write(f"| {g} | {stats['precompute_mean']:.1f} (P95: {stats['precompute_p95']:.1f}) | {stats['plan_cache_mean']:.1f} (P95: {stats['plan_cache_p95']:.1f}) | {stats['selection_gen_mean']:.1f} (P95: {stats['selection_gen_p95']:.1f}) | {stats['total_mean']:.1f} (P95: {stats['total_p95']:.1f}) | {stats['throughput']:.2f} |\n")
        f.write("\n")
        
        f.write("## 6. 辅助维度分析\n")
        f.write(f"### D5: 初始覆盖率分布\n")
        f.write(f"- **L0 初始覆盖率均值**: {df['init_rate_l0'].mean()*100:.2f}%\n")
        f.write(f"- **L1 初始覆盖率均值**: {df['init_rate_l1'].mean()*100:.2f}%\n")
        f.write(f"- **L2 初始覆盖率均值**: {df['init_rate_l2'].mean()*100:.2f}%\n\n")
        
        f.write(f"### D11: Ego 主车参与度\n")
        for g in ["S", "M", "L"]:
            f.write(f"- **规模组 {g} 主车参与问题比例**: `{ego_rates[g]*100:.2f}%`\n")
        f.write("\n")
        
        f.write(f"### D13: 答案分布平衡度\n")
        for g in ["S", "M", "L"]:
            f.write(f"- **规模组 {g} 答案类型统计**: {dict(answer_types[g])}\n")
        f.write("\n")
        
        f.write(f"### D15: 跨帧 L2 Gap 重叠度\n")
        f.write(f"- **相邻时序帧 L2 Gap 集合的平均 Jaccard 相似度**: `{avg_jaccard*100:.2f}%`\n\n")
        
        f.write(f"### K-value: Phase 1→2 切换点分布\n")
        for g in ["S", "M", "L"]:
            k_vals = k_values[g]
            if k_vals:
                f.write(f"- **规模组 {g} 平均切换点 K 覆盖率**: `{np.mean(k_vals)*100:.2f}%` (中位数: `{np.median(k_vals)*100:.2f}%`)\n")
        f.write("\n")
        
    print(f"[Main] Completed in {time.time() - t_start:.1f}s")

if __name__ == "__main__":
    main()
