# RQ2 统一数据分析报告

> 数据来源: 6,011 帧（5,767 有效帧 + 244 trivial 帧），总 QA 84,235,417 道

---

## 〇、关键发现：distance_chain 缺失 (Bug)

> [!CAUTION]
> **Pipeline 存在一个 bug：distance_chain 题型在输出中完全缺失（0 道）。**

### 根因

Pipeline 设计了 **5 种题型** (l2_family)：

| 题型 | 需要约束规划 | Round | 约束条件 |
|------|------------|-------|----------|
| converge | ✅ | R1 | 单分支唯一解析 |
| diverge_compare | ✅ | R1 | 双分支唯一解析 |
| **distance_chain** | ❌ | R2 | d(A,B) ≠ d(B,C) |
| direction_chain | ❌ | R2 | dir(A,B) 和 dir(B,C) 都存在 |
| viewpoint_transfer | ❌ | R2 | 3D 坐标存在 |

但实际输出中 **distance_chain 为 0**。原���是 R2 生成代码中的 `_gi_dist()` 函数（`run_gap_pipeline_v7.py:1628`）只检查了 `rel.get("distance")`，但 filtered_scene_graph 中 distance 存储在 `rel.metrics.distance` 里：

```python
# R2 用的 _gi_dist (BUG - 缺少 metrics fallback)
def _gi_dist(src, dst):
    rel = _gi_out.get(src, {}).get(dst)
    d = rel.get("distance")       # ← scene graph 中此字段不存在!
    # 缺少: metrics = rel.get("metrics"); metrics.get("distance")

# R1 verify 用的 _edge_dist (正确版本)
def _edge_dist(src, dst):
    d = rel.get("distance")
    if d is not None: return float(d)
    metrics = rel.get("metrics")  # ← 有 fallback!
    if isinstance(metrics, dict) and metrics.get("distance") is not None:
        return float(metrics["distance"])
```

**验证**：检查 scene graph edge 结构确认 `distance` 在 metrics 内部：
```
Edge[0] keys: ['direction_6', 'metrics', 'predicates', 'source', 'source_type', 'target', 'target_type']
distance: MISSING                        ← 顶层没有 distance
metrics.distance: 20.66                  ← distance 在 metrics 里
Edges with distance field: 0/342 (0.0%)  ← 所有 edge 都无顶层 distance
```

> [!IMPORTANT]
> **修复方案**：在 `_gi_dist()` 中加入 `metrics.distance` fallback，与 `_edge_dist()` 保持一致。修���后 R2 将正确生成 distance_chain 题目，预期占比约 20-25%（与 direction_chain 类似）。

---

## 一、Table 4 的问题：为什么 diverge 这么低？

### 1.1 问题复现

之前的 Table 4 使用了 **"R1 + R2 补缺"** 模式统计，结果如下：

| 题型 | 数量 | 占比 | Avg ΔL2/Q |
|------|------|------|-----------|
| converge | 38,959,695 | **96.8%** | 1.13 |
| direction_chain (R2补缺) | 540,589 | 1.3% | 1.00 |
| viewpoint_transfer (R2补缺) | 697,423 | 1.7% | 1.00 |
| diverge_compare | 50,002 | **0.1%** | 1.00 |

> [!WARNING]
> 这个统计口径有问题。只统计了 R1 的全部题 + R2 中 delta_l2 > 0 的补缺题，丢弃了绝大部分 R2 题目。

### 1.2 三种统计口径对比

| 统计口径 | 总题数 | converge | diverge | dir_chain | viewpoint |
|---------|--------|----------|---------|-----------|-----------|
| **R1 Only** | 39,009,697 | 99.9% | 0.1% | 0% | 0% |
| **R1 + R2补缺** | 40,247,709 | 96.8% | 0.1% | 1.3% | 1.7% |
| **全量 R1+R2** | **84,235,417** | **46.3%** | **0.1%** | **24.5%** | **29.2%** |

> [!IMPORTANT]
> **结论：Table 4 应该用全量 R1+R2 统计。** 当使用全量数据时：
> - converge 占 46.3%（而非 96.8%）
> - direction_chain 24.5% + viewpoint_transfer 29.2% = **53.7%**，确实多于 converge + diverge 的 46.4%
> - 这符合你的预期："其他题型的和应该多于 converge + diverge"

### 1.3 diverge_compare 为什么这么少？（根因分析）

对 20 帧（nodes ≥ 10）采样分析 candidate_potential：

| 指标 | converge | diverge_compare |
|------|----------|-----------------|
| 可用 plan 数 | 807,522 | 26,712 |
| 被选中数 | 359,148 (44.5%) | 134 (0.5%) |
| 平均 raw_l2/plan | 3.33 | **1.00** |
| 最大 raw_l2 | 10 | **1** |

**根因**（这是 pipeline 设计决定的，不是 bug）：
1. **可用性低**：diverge 需要从 B 节点出发，**两个分支**都必须唯一解析到 A 和 C，这是极其严格的约束。converge 只需要一个分支。所以可用 diverge plan 只有 converge 的 ~3%。
2. **覆盖范围窄**：每个 diverge plan 只覆盖 1 个 L2 gap（raw_l2=1），而 converge 平均覆盖 3.3 个。选题策略会优先选覆盖更多 gap 的 plan。
3. **选择竞争**：在 coverage_backfill 模式下，converge 每题能覆盖更多新 gap，自然被优先选中。

> [!NOTE]
> **这不是 agent 的错误**。diverge_compare 天然稀少是 pipeline 的设计特性。在两轮策略中，R1 用 converge 高效覆盖，R2 用 direction_chain / viewpoint_transfer 保证题型多样性。

---

## 二、修正后的 Table 4（全量 R1+R2）

### 2.1 题型贡献（Converge 系维度）

| 题型 (l2_family) | 数量 | 占比 | Avg ΔL2/Q | Round | 备注 |
|-----------------|------|------|-----------|-------|------|
| **converge** | 38,959,695 | 46.3% | 1.1278 | R1 | |
| **viewpoint_transfer** | 24,613,048 | 29.2% | 0.0283 | R2 | |
| **direction_chain** | 20,612,672 | 24.5% | 0.0262 | R2 | |
| **diverge_compare** | 50,002 | 0.1% | 1.0000 | R1 | 约束太严 |
| **distance_chain** | **0** | **0%** | - | R2 | ⚠️ Bug |

> [!WARNING]
> distance_chain 因 `_gi_dist` bug 而完全缺失。修复后预期占比 ~20-25%。

### 2.2 答案类型（Status 系维度）

| 答案类型 (answer_type) | 数量 | 占比 |
|----------------------|------|------|
| **object** | 38,959,695 | 46.3% |
| **choice** (left/right) | 24,613,048 | 29.2% |
| **boolean** (true/false) | 20,662,674 | 24.5% |

### 2.3 Family × Answer Type 交叉表

| 题型 | boolean | choice | object | status | count | 合计 |
|------|---------|--------|--------|--------|-------|------|
| converge | - | - | ✅ 主体 | ✅ 变体 | ✅ ���体 | 38,959,695 |
| direction_chain | ✅ | - | - | - | - | 20,612,672 |
| diverge_compare | ✅ 主体 | - | ✅ branch_obj | ✅ cmp_status | ✅ branch_cnt | 50,002 |
| distance_chain | - | ✅ (closer) | - | - | - | 0 (bug) |
| viewpoint_transfer | - | ✅ (left/right) | - | - | - | 24,613,048 |

> [!NOTE]
> **两个分类维度并非完全等价**：
> - **Converge 系维度** (l2_family)：按图拓扑结构分 — converge/diverge 是约束规划题，chain/viewpoint 是轻量题
> - **Status 系维度** (answer_type)：按答案形式分 — object（识别物体）、boolean（是/否）、choice（选择）、status（状态查询）、count（计数）
> - converge 和 diverge 各有**多种 answer_type 变体**（object/status/count/exist），通过 round-robin 轮换选择

### 2.4 Selection Phase

| Phase | 数量 | 占比 | Avg ΔL2/Q |
|-------|------|------|-----------|
| coverage_backfill | 62,070,781 | 73.7% | 0.7181 |
| primary | 22,164,636 | 26.3% | 0.0296 |

---

## 三、分段分析：按场景复杂度（低/中/高）

### 3.1 分组定义

| 分组 | 节点范围 | 帧数 | 平均题数/帧 | 中位数题数 |
|------|---------|------|------------|-----------|
| **低 (Low)** | 3–10 | 1,667 | 231 | - |
| **中 (Mid)** | 11–30 | 3,135 | 6,520 | - |
| **高 (High)** | 31–100 | 965 | 65,712 | - |

### 3.2 各组题型分布（全量 R1+R2）

| 分组 | converge | diverge | dir_chain | viewpoint |
|------|----------|---------|-----------|-----------|
| **低 (3-10)** | 42.0% | 1.6% | 28.1% | 28.3% |
| **中 (11-30)** | 45.1% | 0.2% | 25.4% | 29.4% |
| **高 (31-100)** | 46.6% | 0.0% | 24.2% | 29.2% |

> [!NOTE]
> - 低节点组 diverge 相对较高（1.6%），因为节点少时两分支唯一解析更容易满足
> - 高节点组 diverge 接近 0%，节点多导致分支歧义性暴增，几乎不可能满足唯一解析
> - direction_chain 和 viewpoint_transfer 各占 ~25-29%，稳定

### 3.3 各组覆盖效率（R1+R2 补缺口径，反映��实覆盖效率）

| 分组 | 总题数 | Avg ΔL2/Q | Avg Q/Frame |
|------|--------|-----------|-------------|
| **低 (3-10)** | 187,790 | 1.1559 | 113 |
| **中 (11-30)** | 9,727,442 | 1.1500 | 3,103 |
| **高 (31-100)** | 30,332,477 | 1.1150 | 31,433 |

> 三组的 Avg ΔL2/Q 都维持在 ~1.1，说明覆盖效率在不同复杂度下都很稳定。

### 3.4 各组覆盖衰减率（L2）

> 以下为 R1+R2 补缺曲线上各覆盖率区间内每题平均覆盖率增量 (Avg ΔRate/Q)。
> 注意：该值 = coverage_rate 的绝对增量，不是 gap 数。低节点组每个 gap 占的 rate 更大，所以 ΔRate/Q 更高。

#### 低节点组 (3–10 nodes, 1,667 帧)

| 覆盖区间 | Avg ΔRate/Q | 说明 |
|---------|-------------|------|
| 0% → 25% | 0.0526 | 初始效率高 |
| 25% → 50% | 0.0543 | 稳定 |
| 50% → 75% | 0.0546 | 稳定 |
| 75% → 90% | 0.0523 | 几乎无衰减 |
| 90% → 100% | 0.0523 | **无衰减** |

> ✅ 低节点帧全程无衰减，因为 gap 少（平均 ~100 个），每题都能精准覆盖新 gap。

#### 中节点组 (11–30 nodes, 3,135 帧)

| 覆盖区间 | Avg ΔRate/Q | 相对初始效率 |
|---------|-------------|-------------|
| 0% → 25% | 0.001093 | 100% |
| 25% → 50% | 0.000743 | 68.0% |
| 50% → 75% | 0.000661 | 60.5% |
| 75% → 90% | 0.000648 | 59.3% |
| 90% → 100% | 0.000646 | **59.1%** |

> 中节点帧有轻微衰减（初始 → 最终约 60%），但效率始终维持在合理水平。

#### 高节点组 (31–100 nodes, 965 帧)

| 覆盖区间 | Avg ΔRate/Q | 相对初始效率 |
|---------|-------------|-------------|
| 0% → 25% | 0.000068 | 100% |
| 25% → 50% | 0.000045 | 66.2% |
| 50% → 75% | 0.000043 | 63.2% |
| 75% → 90% | 0.000043 | 63.2% |
| 90% → 100% | 0.000042 | **61.8%** |

> 高节点帧衰减模式与中节点类似（~60%），25% 后迅速稳定，没有效率崩塌。

### 3.5 衰减总结

| 分组 | 初期 ΔRate/Q | 末期 ΔRate/Q | 末期/初期 | 特征 |
|------|-------------|-------------|----------|------|
| **低** | 0.0526 | 0.0523 | **99.4%** | 全程无衰减 |
| **中** | 0.0011 | 0.00065 | **59.1%** | 轻微衰减后稳定 |
| **高** | 0.000068 | 0.000042 | **61.8%** | 轻微衰减后稳定 |

> [!TIP]
> 覆盖衰减的主要原因是 converge 的多 L2 覆盖（avg raw_l2=3.79）在初期可以"一石多鸟"，后期重叠率增加。但全程都没有出现效率崩塌，因为 pipeline 的 first-feasible 策略总能找到覆盖新 gap 的 plan。

---

## 四、全局统计总结（R1+R2 补缺口径，用于论文覆盖效率分析）

### Table 1: 覆盖效率汇总

#### 里程碑题数

| Level | Q to 50% (Mean/Median) | Q to 90% (Mean/Median) | Q to 100% (Mean/Median) |
|-------|----------------------|----------------------|------------------------|
| L0 | 1.6 / 0 | 8.4 / 7 | 15.1 / 10 |
| L1 | 68.2 / 31 | 241.7 / 110 | 767.0 / 254 |
| L2 | 2,964.7 / 514 | 5,943.1 / 1,057 | **6,694.7 / 1,193** |

#### 每题效率

| 指标 | 数值 |
|------|------|
| Avg new L2/Q | **1.1237** |
| Avg new L1/Q | 0.0345 |
| Avg new L0/Q | 0.0027 |
| Avg raw L2/Q | 3.6991 |
| Redundancy ratio (L2) | **69.62%** |
| Total delta L2 | 45,225,720 |
| Total raw L2 | 148,879,724 |

### Table 2: 分段覆盖衰减 (L2)

| 覆盖区间 | Avg ΔL2/Q | 题数占比 | 说明 |
|---------|-----------|---------|------|
| **0% → 25%** | **1.5825** | 17.8% | 初期高效 |
| **25% → 50%** | 1.0587 | 26.5% | 稳定高效 |
| **50% → 75%** | 1.0145 | 27.7% | 接近 1:1 |
| **75% → 90%** | 1.0040 | 16.8% | 几乎 1:1 |
| **90% → 100%** | **1.0006** | **11.2%** | 补缺阶段仍 1:1 |

> ✅ 全程效率稳定：即使在 90%→100% 阶段，每题仍能贡献约 1 个新 L2，没有出现效率崩塌。

### Table 3: 场景复杂度分组

| 节点数 | 帧数 | Avg Q (R1+R2补缺) | Avg Q (全量R1+R2) | Q to 100% |
|--------|------|-------------------|-------------------|-----------|
| 0–5 | 814 | 10 | 20 | 9 |
| 3–10 | 1,667 | 113 | 231 | 112 |
| 11–20 | 2,021 | 1,357 | 2,855 | 1,356 |
| 21–30 | 1,114 | 6,269 | 13,167 | 6,268 |
| 31–50 | 838 | 22,545 | 47,096 | 22,544 |
| 51–100 | 127 | 90,075 | 188,549 | 90,074 |

> 全量 R1+R2 的题数约为 R1+R2 补缺的 2 倍，因为 R2 为每个 gap 各生成一道轻量题。

### Table 5: Pipeline 时间拆解

| 阶段 | 平均耗时 | 中位数 | P90 | 占比 |
|------|---------|--------|-----|------|
| Precompute | 76ms | 7ms | 151ms | 1.2% |
| Plan Cache | 5,401ms | 449ms | 11,809ms | **85.2%** |
| Selection + Gen | 623ms | 94ms | 1,597ms | 9.8% |
| **Total** | **6,341ms** | **606ms** | **14,279ms** | 100% |

吞吐量: 2,303.5 Q/s (全量), 总时间 609.5 min

### AUC 汇总

| 指标 | Ours |
|------|------|
| AUC L0 (Absolute) | 0.9998 |
| AUC L1 (Absolute) | 0.9945 |
| AUC L2 (Absolute) | **0.8755** |
| AUC L0 (Normalized) | 0.9928 |
| AUC L1 (Normalized) | 0.9479 |
| AUC L2 (Normalized) | **0.5645** |

---

## 五、两轮策略设计说明

### 为什么分两轮？

| Round | 题型 | 目的 | 需要约束规划 | 需要 verify |
|-------|------|------|------------|------------|
| **R1** | converge + diverge_compare | **覆盖** — 达到 L2 100% | ✅ | ✅ |
| **R2** | direction_chain + **distance_chain** + viewpoint_transfer | **多样性** — 每个 gap 一道轻量题 | ❌ | ❌ |

- R1 是覆盖的主力，通过 converge 的多 gap 覆盖能力（avg raw_l2=3.79）高效达成 100%
- R2 为每个 gap 直接生成一道不需要约束规划的轻量题，保证题型多样性（R2 有 3 种家族 round-robin 轮换）
- diverge_compare 虽然属于 R1 但因为约束太严格（需要双分支唯一解析），可用 plan 极少
- ⚠️ distance_chain 因 `_gi_dist` bug 未能生成，修复后 R2 将有 3 种家族

### 统计口径选择建议

| 用途 | 推荐口径 | 理由 |
|------|---------|------|
| **覆盖效率分析** (Table 1-2) | R1 + R2 补缺 (40M 题) | 只看对覆盖有贡献的题，避免 R2 大量 delta=0 的题拉低效率 |
| **题型分布** (Table 4) | **全量 R1+R2 (84M 题)** | 展示完整的题型多样性 |
| **覆盖率曲线** | R1 + R2 补缺 | 曲线基于覆盖进度，R2 重复题不提供新覆盖 |

---

## 六、数据文件索引

| 文件 | 位置 | 说明 |
|------|------|------|
| 详细分析日志 | `rq2_plots/detailed_analysis.log` | 三种口径 + 分段 + 交叉表完整输出 |
| R1+R2补缺分析 | `rq2_plots/analysis_r1.log` | Table 1-5 原始输出 |
| 全量分析 | `rq2_plots/analysis_full.log` | 全量口径的 Table 1-5 |
| 覆盖率曲线数据 | `rq2_plots/extracted_r1/rq2_curves.npz` | 144MB 预提取数据 |
| 帧级汇总 | `rq2_plots/extracted_r1/rq2_frame_summary.csv` | 6,011 帧 |
| 覆盖率图 | `rq2_plots/figures_r1/rq2_*.{png,pdf}` | 方案A/B覆盖图 |
