# ADVTEST 全量实验汇总报告

> 数据来源: 1号机 `EXPERIMENT_LOG.md` + `rq2_plots/` 分析结果

---

## 一、实验总览

| 指标 | 数值 |
|------|------|
| **总帧数** | 6,011 |
| **有效帧** (≥3 nodes) | 5,767 |
| **Trivial 帧** (≤2 nodes, 跳过) | 244 |
| **总 QA 生成数** (R1+R2补缺) | **40,247,709** |
| **平均 QA/帧** | 6,696 |
| **L2 覆盖率** | **100%** (所有有效帧) |
| **吞吐量** | 1,100.6 Q/s |

---

## 二、执行时间线 (Day 1–4)

### Day 1 (5/10): 部署 + 首跑 + 优化
- 部署到 Server A，启动 Plan B (2292帧)
- Phase 2 首跑: 19帧/5h，大��� 66min/帧，ETA 20天 ❌
- **5项性能优化**:
  1. `skip_cypher` 跳过 Cypher 构建
  2. `first-feasible` 替代 O(n²) coverage_gain
  3. 批量写入替代 per-QA I/O
  4. `_memory_verify` 内存验证替代 Neo4j
  5. `plan_cache` 预过滤
- 结果: 66min → 31.9min/帧 (frame14, 45 nodes)

### Day 2 (5/11): 极限优化 + 批量跑
- **根因定位**: `family_cap_blocked` 导致 80% 题走慢速全量扫描
- **v5 优化**: 移除配额限制 → 31.9min → **1.0min/帧** (66倍加速)
- **v6 两轮策略**:
  - Round 1: converge + diverge (覆盖导向)
  - Round 2: chain + viewpoint (多样性导向, O(1) 生成)
- Plan B Phase 2: 1988/2292 完成后**磁盘满** (NVMe 99%)

### Day 3 (5/12): 磁盘迁移 + 全量完成
- 迁移 outputs (346G) + filtered_sg (1G) 到 HDD `/mnt/data4`
- NVMe 99% → 59%
- **Plan B** 断点续跑: 剩余 304帧 ✅ (75min, 0 fail)
- **Plan C** scene_graph_gen 修复后重跑: 2215帧 ✅ (3.7h, 0 fail)
- **Plan A** 启动: 1504帧, 深夜完成

### Day 4 (5/13): 验证 + 清理 + RQ2 分析
- 全量 L2 覆盖率验证: 5767/6011 = 100% ✅
- 清理 Legacy 冗余文件: 释放 164.5GB
- 完成 RQ2 可视化和统计分析

---

## 三、性能优化历程

> frame14 (45 nodes, 42570 L2 gaps) 单帧测试

| 版本 | 耗时 | 关键改动 | 题数 |
|------|------|----------|------|
| 原始 | **66 min** | Neo4j verify, per-QA I/O | ~40K |
| v3 | 31.9 min | memory_verify + 预过滤 | ~40K |
| v5 | **1.0 min** | 移除 family_cap + _direct_plan_verify | ~40K |
| v6 (最终) | **1.0 min** | 两轮策略 (R1覆盖 + R2多样性) | **67K** |

---

## 四、三个 Plan 执行结果

| Plan | 帧数 | Scenes | Phase 1 | Phase 2 | 速度 |
|------|------|--------|---------|---------|------|
| **Plan B** | 2,292 | 58 | ✅ 71s | ✅ 5.5h | ~6.8s/帧 |
| **Plan C** | 2,215 | 55 | ✅ 3.3min | ✅ 3.7h | ~6.0s/帧 |
| **Plan A** | 1,504 | 38 | ✅ 3.9min | ✅ 7.6h | ~18.2s/帧 |
| **合计** | **6,011** | **151** | **全部完成** | **全部完成** | - |

---

## 五、RQ2 核心数据

### 5.1 覆盖效率 (Table 1)

**里程碑题数** (到达指定覆盖率所需题数):

| Level | Q→50% (Mean/Med) | Q→90% (Mean/Med) | Q→100% (Mean/Med) |
|-------|-------------------|-------------------|---------------------|
| L0 (Object) | 1.6 / 0 | 8.4 / 7 | 15.1 / 10 |
| L1 (Relationship) | 68.2 / 31 | 241.7 / 110 | 767.0 / 254 |
| L2 (Triple) | 2,964.7 / 514 | 5,943.1 / 1,057 | **6,694.7 / 1,193** |

**每题效率**:
- Avg new L2/Q: **1.1237** (每题平均覆盖 1.12 个新 L2 gap)
- Redundancy ratio: **69.62%** (raw L2 有冗余, 但 delta L2 几乎无冗余)
- Coverage efficiency: **1.1459** gaps/Q

### 5.2 分段效率衰减 (Table 2)

| 覆盖区间 | Avg ΔL2/Q | 题数占比 |
|---------|-----------|---------|
| 0%→25% | **1.58** | 17.8% |
| 25%→50% | 1.06 | 26.5% |
| 50%→75% | 1.01 | 27.7% |
| 75%→90% | 1.00 | 16.8% |
| 90%→100% | **1.00** | 11.2% |

> 全程 ΔL2/Q ≈ 1.0，pipeline 几乎不产生冗余题

### 5.3 场景复杂度分组 (Table 3)

| 节点数 | 帧数 | Avg Q/帧 | Avg Q→100% |
|--------|------|----------|------------|
| 0–5 | 814 | 10 | 9 |
| 3–10 | 1,667 | 113 | 112 |
| 11–20 | 2,021 | 1,357 | 1,356 |
| 21–30 | 1,114 | 6,269 | 6,268 |
| 31–50 | 838 | 22,545 | 22,544 |
| 51–100 | 127 | 90,075 | 90,074 |

> Q ≈ Q_to_100% (差值仅1)，复杂度符合 O(n²) 增长

### 5.4 题型贡献 (Table 4)

| 题型 | 数量 | 占比 | Avg ΔL2/Q |
|------|------|------|-----------|
| converge | 38,959,695 | **96.8%** | 1.13 |
| direction_chain (R2补缺) | 540,589 | 1.3% | 1.00 |
| viewpoint_transfer (R2补缺) | 697,423 | 1.7% | 1.00 |
| diverge_compare | 50,002 | 0.1% | 1.00 |

### 5.5 Pipeline Timing (Table 5)

| 阶段 | Mean | Median | P90 | 占比 |
|------|------|--------|-----|------|
| Precompute | 76ms | 7ms | 151ms | 1.2% |
| Plan Cache | 5,401ms | 449ms | 11,809ms | **85.2%** |
| Selection+Gen | 623ms | 94ms | 1,597ms | 9.8% |
| **Total/帧** | **6,341ms** | **606ms** | **14,279ms** | 100% |

### 5.6 AUC 汇总

| 指标 | Ours | Random |
|------|------|--------|
| AUC L0 (Absolute) | 0.9998 | TBD |
| AUC L1 (Absolute) | 0.9945 | TBD |
| **AUC L2 (Absolute)** | **0.8755** | TBD |
| AUC L0 (Normalized) | 0.9928 | TBD |
| AUC L1 (Normalized) | 0.9479 | TBD |
| **AUC L2 (Normalized)** | **0.5645** | TBD |

### 5.7 初始覆盖率 (原始题集)

| Level | Avg Initial Coverage |
|-------|---------------------|
| L0 (Object) | 49.10% |
| L1 (Relationship) | 8.46% |
| L2 (Triple) | **5.02%** |

---

## 六、已生成图表

| 文件 | 说明 |
|------|------|
| `figures_r1/rq2_absolute_coverage.{png,pdf}` | L0+L1+L2 覆盖率 vs 绝对题数 (1×3) |
| `figures_r1/rq2_normalized_coverage.{png,pdf}` | L0+L1+L2 覆盖率 vs 归一化预算% (1×3) |
| `figures_r1/rq2_l0_coverage.{png,pdf}` | L0 单独大图 |
| `figures_r1/rq2_l1_coverage.{png,pdf}` | L1 单独大图 |
| `figures_r1/rq2_l2_coverage.{png,pdf}` | L2 单独大图 |
| `figures_r1/rq2_summary_table.csv` | AUC 汇总表 |
| `figures_r1/table1_efficiency.csv` | 效率指标表 |
| `figures_r1/table4_family.csv` | 题型贡献表 |

---

## 七、待办事项

- [ ] **Random Baseline 实验** — 方案待定 (随机选gap vs 打乱题序)
- [ ] 统计显著性检验 (Ours vs Random)
- [ ] LaTeX 表格格式化
- [ ] 图表风格调整 (论文模板配色/字体)
- [ ] 数据打包/备份

---

## 八、数据存储

### 磁盘状态
| 存储 | 容量 | 已用 | 可用 | 使用率 |
|------|------|------|------|--------|
| NVMe | 915G | 514G | 355G | 60% |
| HDD /mnt/data4 | 3.6T | 2.8T | 776G | 79% |

### 文件冗余优化
- 已删除 `_generated.csv` + `_generated.jsonl` (与 `_all.*` 等价)
- 释放 164.5GB, outputs 920G → 755G
- 可进一步优化: 只保留 JSONL (再省 ~40%)

### QA 输出结构 (per frame)
| 文件 | 大小 (典型) | 说明 |
|------|------------|------|
| `_round1.csv` | 52M | converge + diverge |
| `_round1.jsonl` | 137M | 同上 JSONL |
| `_round2.csv` | 39M | chain + viewpoint |
| `_round2.jsonl` | 124M | 同上 JSONL |
| `_all.csv` | 91M | R1+R2 合并 |
| `_all.jsonl` | 260M | 同上 JSONL |
| `_generated_meta.csv` | 269B | 元信息 |
