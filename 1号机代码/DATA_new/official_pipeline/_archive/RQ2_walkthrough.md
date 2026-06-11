# RQ2 完整分析报告（修正版 — Round 1 + R2补缺）

## 数据处理说明

- **Round 1** (converge + diverge_compare): 以覆盖为目标的主力题型
- **Round 2 补缺**: 仅取 Round 2 中 `delta_l2 > 0` 的题（每题恰好覆盖 1 个新 L2 gap）
- **L1 修正**: `relationship_count` 是有向边数，实际分母应为 `relationship_count / 2`（无向边数）
- 全量 6,011 帧，总题数 40,247,709

---

## 一、覆盖率曲线图

### 方案A: X = 绝对出题数

![RQ2 Absolute Coverage](/home/yunyang/ADVTEST/DATA_new/official_pipeline/rq2_plots/figures_r1/rq2_absolute_coverage.png)

### 方案B: X = 归一化百分比

![RQ2 Normalized Coverage](/home/yunyang/ADVTEST/DATA_new/official_pipeline/rq2_plots/figures_r1/rq2_normalized_coverage.png)

---

## 二、全量统计结果

### Table 1: 覆盖效率汇总

#### 里程碑 — 到达各覆盖率所需题数

| Level | Q to 50% (Mean / Median) | Q to 90% (Mean / Median) | Q to 100% (Mean / Median) |
|-------|--------------------------|--------------------------|---------------------------|
| **L0** | 1.6 / 0 | 8.4 / 7 | 15.1 / 10 |
| **L1** | 68.2 / 31 | 241.7 / 110 | 767.0 / 254 |
| **L2** | 2,964.7 / 514 | 5,943.1 / 1,057 | **6,694.7 / 1,193** |

#### 每题效率

| 指标 | 数值 |
|------|------|
| Avg new L2 per Question | **1.1237** |
| Avg new L1 per Question | 0.0345 |
| Avg new L0 per Question | 0.0027 |
| Avg raw L2 per Question | 3.6991 |
| Redundancy ratio (L2) | **69.62%** |
| Coverage efficiency (gaps/Q) | **1.1459** (mean) |
| Total delta L2 | 45,225,720 |
| Total raw L2 | 148,879,724 |

### Table 2: 分段覆盖衰减 (L2)

| 覆盖区间 | Avg ΔL2/Q | 题数占比 | 说明 |
|---------|-----------|---------|------|
| **0% → 25%** | **1.5825** | 17.8% | 初期高效，每题 ~1.6 个新 L2 |
| **25% → 50%** | 1.0587 | 26.5% | 稳定高效 |
| **50% → 75%** | 1.0145 | 27.7% | 接近 1:1 |
| **75% → 90%** | 1.0040 | 16.8% | 几乎 1:1 |
| **90% → 100%** | **1.0006** | **11.2%** | 补缺阶段仍保持 1:1 |

> ✅ 全程效率稳定：即使在 90%→100% 阶段，每题仍能贡献约 1 个新 L2，没有出现效率崩塌。

### Table 3: 场景复杂度分组

| 节点数 | 帧数 | Avg Q | Avg Q to 100% |
|--------|------|-------|---------------|
| 0–5 | 814 | 10 | 9 |
| 3–10 | 1,667 | 113 | 112 |
| 11–20 | 2,021 | 1,357 | 1,356 |
| 21–30 | 1,114 | 6,269 | 6,268 |
| 31–50 | 838 | 22,545 | 22,544 |
| 51–100 | 127 | 90,075 | 90,074 |

### Table 4: 题型贡献分析

| 题型 | 数量 | 占比 | Avg ΔL2/Q |
|------|------|------|-----------|
| **converge** | 38,959,695 | **96.8%** | 1.1278 |
| **direction_chain** (R2补缺) | 540,589 | 1.3% | 1.0000 |
| **diverge_compare** | 50,002 | 0.1% | 1.0000 |
| **viewpoint_transfer** (R2补缺) | 697,423 | 1.7% | 1.0000 |

#### Selection Phase

| Phase | 数量 | 占比 | Avg ΔL2/Q |
|-------|------|------|-----------|
| **coverage_backfill** | 39,601,204 | **98.4%** | 1.1255 |
| **primary** | 646,505 | 1.6% | 1.0133 |

### Table 5: Pipeline 时间拆解

| 阶段 | 平均耗时 | 中位数 | P90 | 占比 |
|------|---------|--------|-----|------|
| Precompute | 76ms | 7ms | 151ms | 1.2% |
| Plan Cache | 5,401ms | 449ms | 11,809ms | **85.2%** |
| Selection + Gen | 623ms | 94ms | 1,597ms | 9.8% |
| **Total** | **6,341ms** | **606ms** | **14,279ms** | 100% |

| 吞吐量 | 数值 |
|--------|------|
| 总时间 | 609.5 分钟 |
| 题/秒 | 1,100.6 |

### 覆盖重叠率

| 指标 | 数值 |
|------|------|
| 帧均冗余率 | **48.06%** (Mean), 53.48% (Median) |
| P25 / P75 | 37.46% / 63.99% |

---

## 三、AUC 汇总

| 指标 | Ours |
|------|------|
| AUC L0 (Absolute) | 0.9998 |
| AUC L1 (Absolute) | 0.9945 |
| AUC L2 (Absolute) | **0.8755** |
| AUC L0 (Normalized) | 0.9928 |
| AUC L1 (Normalized) | 0.9479 |
| AUC L2 (Normalized) | **0.5645** |

---

## 四、输出文件清单

| 文件 | 位置 |
|------|------|
| 覆盖率图 (PNG+PDF) | `rq2_plots/figures_r1/rq2_*.{png,pdf}` |
| 统计表 CSV | `rq2_plots/figures_r1/table1_efficiency.csv`, `table4_family.csv` |
| 中间数据 | `rq2_plots/extracted_r1/rq2_curves.npz` (144MB) |
| 分析日志 | `rq2_plots/analysis_r1.log` |

## 五、待完成

- [ ] Random Baseline 实验
- [ ] 根据论文模板调整图表风格
- [ ] 将统计结果整理成 LaTeX 表格
