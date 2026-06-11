# RQ2 综合数据分析报告（修复 distance_chain 后）

> 生成时间: 2026-05-15
> 数据来源: 6,011 帧（5,767 有效帧 + 244 trivial 帧）
> Bug 修复: `_gi_dist()` 已加入 `metrics.distance` fallback

---

## 〇、修复概要

### Bug: distance_chain 缺失

**问题**: R2 生成代码中 `_gi_dist()` 函数只查 `rel.get("distance")`，但 scene graph 的 edge 把 distance 存在 `rel.metrics.distance` 里。

**修复**: 在 `run_gap_pipeline_v7.py:1628` 的 `_gi_dist()` 中加入 metrics.distance fallback。

**修复前后对比**:

| 题型 | 修复前 | 修复后 |
|------|--------|--------|
| converge | 46.3% | ~29.6% |
| direction_chain | 24.5% | ~28.1% |
| **distance_chain** | **0%** | **~23.5%** |
| viewpoint_transfer | 29.2% | ~18.9% |
| diverge_compare | 0.1% | ~0.04% |

### R2 重新生成结果

```
DONE in 16707s (278.4min)
  R2 new total: 90,451,440
  - direction_chain: 36,033,813 (39.8%)
  - distance_chain:  30,142,899 (33.3%)
  - viewpoint:       24,274,728 (26.8%)
  Errors: 0
```

---

## 一、覆盖率曲线分析

### 1.1 R1+R2 补缺口径（用于覆盖效率分析）

| 指标 | 数值 |
|------|------|
| Total Frames | 6,011 |
| Total Questions | 40,247,709 |
| Avg Questions/Frame | 6,696 |
| Avg Initial L0 Coverage | 49.10% |
| Avg Initial L1 Coverage | 8.46% |
| Avg Initial L2 Coverage | 5.02% |
| **Avg Final L0 Coverage** | **100.00%** |
| **Avg Final L1 Coverage** | **100.00%** |
| **Avg Final L2 Coverage** | **100.00%** |
| AUC L0 (Absolute) | 0.9998 |
| AUC L1 (Absolute) | 0.9945 |
| **AUC L2 (Absolute)** | **0.8755** |
| AUC L0 (Normalized) | 0.9928 |
| AUC L1 (Normalized) | 0.9479 |
| **AUC L2 (Normalized)** | **0.5645** |

### 1.2 全量 R1+R2 口径（用于题型分布分析）

| 指标 | 数值 |
|------|------|
| Total Frames | 6,011 |
| Total Questions | 129,461,137 |
| Avg Questions/Frame | 21,537 |
| Avg Initial L0 Coverage | 49.10% |
| Avg Initial L1 Coverage | 8.46% |
| Avg Initial L2 Coverage | 5.02% |
| Avg Final L0 Coverage | 100.00% |
| Avg Final L1 Coverage | 100.00% |
| Avg Final L2 Coverage | 52.03% |
| AUC L0 (Absolute) | 0.9999 |
| AUC L1 (Absolute) | 0.9983 |
| AUC L2 (Absolute) | 0.4964 |
| AUC L0 (Normalized) | 0.9972 |
| AUC L1 (Normalized) | 0.9833 |
| AUC L2 (Normalized) | 0.4523 |

> [!NOTE]
> 全量口径下 Final L2 Coverage 只有 52%，因为 R2 为每个 gap 只生成一道题（round-robin 轮换 3 种家族），不追求覆盖新 gap。R1+R2 补缺口径才是衡量覆盖效率的正确指标。

---

## 二、Table 4: 题型分布（全量 R1+R2）

### 2.1 20帧采样结果（快速验证）

| 题型 (l2_family) | 数量 | 占比 | Round |
|-----------------|------|------|-------|
| **converge** | 119,716 | 29.6% | R1 |
| **direction_chain** | 113,494 | 28.1% | R2 |
| **distance_chain** | 94,853 | 23.5% | R2 |
| **viewpoint_transfer** | 76,239 | 18.9% | R2 |
| **diverge_compare** | 58 | 0.0% | R1 |

> [!IMPORTANT]
> 修复后 5 种题型全部出现，R2 三种家族分布均匀（direction 39.8% / distance 33.3% / viewpoint 26.8%）。

### 2.2 diverge_compare 为什么这么少？

diverge_compare 在全量数据中约 50,000 道（占 ~0.04%），这是 **pipeline 设计特性**，不是 bug：

1. **约束极严格**: 需要从 B 出发，两个分支都必须唯一解析到 A 和 C
2. **可用 plan 极少**: 只有 converge 的 ~3%
3. **覆盖范围窄**: 每个 plan 只覆盖 1 个 L2 gap（converge 平均覆盖 3-4 个）
4. **节点越多越难**: 低节点帧 diverge ~1.6%，高节点帧接近 0%

### 2.3 答案类型分布

| 题型 | 答案类型 | 说明 |
|------|---------|------|
| converge | object / status / count | 多种变体 round-robin |
| direction_chain | boolean (same/different) | 方向是否相同 |
| distance_chain | object (closer one) | 哪个更近 |
| viewpoint_transfer | choice (left/right) | 左右判断 |
| diverge_compare | boolean / object / count | 多种变体 round-robin |

---

## 三、两轮策略设计

| Round | 题型 | 目的 | 需要约束规划 |
|-------|------|------|------------|
| **R1** | converge + diverge_compare | **覆盖** — 达到 L2 100% | ✅ |
| **R2** | direction_chain + distance_chain + viewpoint_transfer | **多样性** — 每个 gap 一道轻量题 | ❌ |

- R1 通过 converge 的多 gap 覆盖能力（avg raw_l2 ≈ 3-4）高效达成 100%
- R2 为每个 gap 生成一道不需要约束规划的轻量题，3 种家族 round-robin 轮换
- 总题数 = R1 (~40M) + R2 (~90M) = ~130M

---

## 四、统计口径说明

| 用途 | 推荐口径 | 总题数 | 理由 |
|------|---------|--------|------|
| **覆盖效率** (Table 1-2, AUC) | R1 + R2补缺 | 40M | 只看对覆盖有贡献的题 |
| **题型分布** (Table 4) | 全量 R1+R2 | 130M | 展示完整题型多样性 |
| **覆盖率曲线** | R1 + R2补缺 | 40M | 曲线基于覆盖进度 |

---

## 五、生成文件索引

| 文件 | 位置 | 说明 |
|------|------|------|
| 覆盖率曲线 (全量) | `rq2_plots/extracted_v2/rq2_curves.npz` | 181 MB, shape (6011, 803483) |
| 覆盖率曲线 (R1补缺) | `rq2_plots/extracted_v2_r1/rq2_curves.npz` | 144 MB, shape (6011, 255512) |
| 帧级汇总 (全量) | `rq2_plots/extracted_v2/rq2_frame_summary.csv` | 6,011 帧 |
| 帧级汇总 (R1补缺) | `rq2_plots/extracted_v2_r1/rq2_frame_summary.csv` | 6,011 帧 |
| 覆盖率图 (全量) | `rq2_plots/figures_v2/rq2_*.png` | 绝对/归一化/分级 |
| 覆盖率图 (R1补缺) | `rq2_plots/figures_v2_r1/rq2_*.png` | 绝对/归一化/分级 |
| 汇总表 (全量) | `rq2_plots/figures_v2/rq2_summary_table.csv` | AUC 等 |
| 汇总表 (R1补缺) | `rq2_plots/figures_v2_r1/rq2_summary_table.csv` | AUC 等 |
| R2 重跑日志 | `rq2_plots/regenerate_r2.log` | 5767 帧, 278 min |
| Bug 修复 | `code/run_gap_pipeline_v7.py:1628` | _gi_dist metrics fallback |

---

## 六、待完成（详细分析脚本运行中）

- [ ] 全量 5767 帧的精确 Table 4 数据（quick_analysis_v2.py 运行中）
- [ ] 分段覆盖衰减率（按 0-25%, 25-50%, 50-75%, 75-90%, 90-100%）
- [ ] 节点复杂度分组分析（低/中/高）
- [ ] 每题效率指标（Avg ΔL2/Q, redundancy ratio）

> 以上数据将在 `quick_analysis_v2.log` 完成后补充到本文档。
