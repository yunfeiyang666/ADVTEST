# RQ2 数据分析头脑风暴

## 一、我们拥有的数据维度

从 6,011 帧的实验结果中，我们有以下 **7 大类数据源**：

### 数据源 1: 逐题增量覆盖 (`incremental_coverage.csv`)
每帧一个文件，每行 = 一道题生成后的状态。

| 字段 | 含义 | 分析价值 |
|------|------|---------|
| `order_index` | 题目生成顺序 (1-based) | X 轴 |
| `l2_family` | 题型: converge, diverge, direction_chain, distance_chain, viewpoint_transfer | 按题型拆分分析 |
| `selection_phase` | primary / coverage_backfill | 策略对比 |
| `timestamp_start/end` | 生成时间戳 | 时间维度分析 |
| `generation_elapsed_ms` | 单题生成耗时 (ms) | 效率分析 |
| `raw_l0/l1/l2` | 该题覆盖的原始 L0/L1/L2 数量 | 每题原始贡献 |
| `delta_l0/l1/l2` | 该题新增（去重后）的覆盖数 | **每题有效增量** |
| `cum_l0/l1/l2` | 累计覆盖数 | 覆盖进度 |
| `coverage_rate_l0/l1/l2` | 累计覆盖率 | Y 轴 |
| `new_l0/l1/l2` | 新覆盖的具体项（列表） | 可计算覆盖重叠率 |

### 数据源 2: 逐题详细记录 (`_round1.csv` / `_round2.csv`)
每帧的完整 QA 记录。

| 字段 | 含义 | 分析价值 |
|------|------|---------|
| `answer_type` | object, boolean, count, status, comparison | 答案类型分布 |
| `path_pattern` | 涉及的节点路径 (如 `A\|B\|C`) | 题目复杂度 |
| `footprint_nodes` | 涉及的节点列表 | 覆盖范围 |
| `external_refs` | 外部引用 | 约束复杂度 |
| `constraint_count` | 约束数量 | 题目难度 |
| `candidate_before/after` | 候选数变化 | 区分度 |
| `difficulty_score` | 难度分数 | 难度分布 |
| `coverage_l0/l1/l2` | 该题覆盖的项列表 | 每题覆盖贡献 |
| `generation_elapsed_ms` | 生成耗时 | 效率 |
| `verify_elapsed_ms` | 验证耗时 | 效率 |

### 数据源 3: 帧级摘要 (`summary.json`)

| 字段 | 含义 | 分析价值 |
|------|------|---------|
| `elapsed_ms` | 全帧 pipeline 总耗�� | **时间效率** |
| `generated` | 总生成题数 | 效率比 |
| `total_gap_count` | L2 gaps 总数 | 场景复杂度 |
| `covered_gap_count` | 已覆盖 gaps 数 | 覆盖结果 |
| `tried_candidate_count` | 尝试的候选数 | 搜索效率 |
| `failed_candidate_count` | 失败候选数 | 搜索浪费 |
| `pipeline_timing.*` | 各阶段耗时 (precompute, plan_cache, selection_gen, neo4j_verify) | **时间拆解** |
| `families.*` | 各题型生成数 | 题型分布 |
| `initial_coverage.*` | 初始覆盖 (L0/L1/L2 数量 + 状态统计) | 初始覆盖分析 |
| `universe_stats.neo4j.*` | 对象数、关系数 | 场景复杂度 |
| `universe_stats.feasible_gap_count` | 可行 gap 数 | 可行性 |
| `universe_stats.unavailable_gap_count` | 不可行 gap 数 | 可行性 |

### 数据源 4: 帧级元数据 (`_generated_meta.csv`)

| 字段 | 含义 |
|------|------|
| `raw_nodes / filtered_nodes` | 原始/过滤后节点数 |
| `raw_edges / filtered_edges` | 原始/过滤后边数 |
| `total_l2_gaps` | L2 总 gap 数 |
| `total_l0_objects / total_l1_pairs` | L0/L1 总数 |
| `initial_coverage_l0/l1/l2` | 初始覆盖数 |
| `generated_questions` | 生成题数 |
| `final_coverage_l2` | 最终 L2 覆盖数 |

### 数据源 5: 初始覆盖详情 (`offline/initial_coverage/`)

| 字段 | 含义 |
|------|------|
| `template_type` | 原始题目模板类型 (exist, count, object, status, comparison) |
| `num_hop` | 跳数 (0, 1, 2) |
| `llm_status` | 确定性/LLM 匹配状态 |
| `l0_count / l1_count / l2_count` | 该原始题覆盖的 L0/L1/L2 数 |

### 数据源 6: 候选潜力 (`candidate_potential.csv`)

| 字段 | 含义 |
|------|------|
| `gap_key` | L2 gap 标识 (A\|B\|C) |
| `family` | 题型 |
| `plan_rank` | 候选排名 |
| `raw_l0/l1/l2` | 原始覆盖 |
| `selected` | 是否被选中 |
| `selected_delta_l2` | 选中时的增量贡献 |

### 数据源 7: 提取的中间数据 (`rq2_frame_summary.csv`)

已有 6,011 帧汇总: nodes、n_questions、初始覆盖率、最终覆盖率。

---

## 二、已知的关键统计数据

| 维度 | 数值 |
|------|------|
| 总帧数 | 6,011 (5,767 有效 + 244 trivial) |
| 总 L2 gaps | 45,225,720 |
| 总 QA | 84,235,417 |
| 平均 QA/帧 | 14,014 (中位数 3,007) |
| 平均节点/帧 | 18.7 (中位数 16) |
| 节点范围 | 3–83 |
| 平均初始 L0 覆盖 | 46.9% (中位数 40.0%) |
| 平均初始 L1 覆盖 | 2.3% (中位数 0.6%) |
| 平均初始 L2 覆盖 | 1.0% (中位数 0.0%) |
| 有初始 L2>0 的帧 | 51.2% (2,951 帧) |
| 最终覆盖率 | L0/L1/L2 全部 100% |

---

## 三、可做的分析方向

### 方向 A: 覆盖效率分析（核心表）

> 这���最直接体现方法效率的表

| 指标 | 说明 | 数据来源 |
|------|------|---------|
| **Avg New L2 per Question** | 每题平均新增 L2 覆盖数 | `delta_l2` 均值 |
| **Avg New L1 per Question** | 每题平均新增 L1 覆盖数 | `delta_l1` 均值 |
| **Avg New L0 per Question** | 每题平均新增 L0 覆盖数 | `delta_l0` 均值 |
| **Avg Raw L2 per Question** | 每题平均原始 L2 覆盖（含重复） | `raw_l2` 均值 |
| **Coverage Efficiency** | = `total_gaps / total_questions` | 比值越高越好 |
| **Redundancy Ratio** | = `1 - (sum_delta_l2 / sum_raw_l2)` | 重复覆盖比例 |
| **Avg Questions to 50% L2** | 平均需要多少题达到 50% 覆盖 | 从曲线提取 |
| **Avg Questions to 90% L2** | 平均需要多少题达到 90% 覆盖 | 从曲线提取 |
| **Avg Questions to 100% L2** | 平均需要多少题达到 100% 覆盖 | 从曲线提取 |

---

### 方向 B: 分段覆盖衰减分析

> 类似你之前做过的分析 — 把覆盖过程分成几段，分析每段的效率变化

| 覆盖率区间 | Avg ΔL2/Question | 占总题数% | 说明 |
|-----------|-------------------|----------|------|
| 0% → 25% | (高效) | (小) | 初期快速覆盖 |
| 25% → 50% | ... | ... | |
| 50% → 75% | ... | ... | 效率递减 |
| 75% → 90% | ... | ... | |
| 90% → 100% | (低效) | (大) | 最后冲刺 |

分析意义：展示覆盖从"容易覆盖的 gaps"到"难覆盖的 gaps"的效率衰减过程。

---

### 方向 C: 题型贡献分析

> 不同题型对覆盖的贡献差异

| 题型 (l2_family) | 平均占比% | Avg ΔL2/Q | 说明 |
|-----------------|----------|-----------|------|
| converge | ~40% | 高 | 主力覆盖 |
| diverge_compare | ~35% | ? | |
| direction_chain | ~8% | ? | Round 2 轻量题 |
| distance_chain | ~8% | ? | Round 2 轻量题 |
| viewpoint_transfer | ~9% | ? | Round 2 轻量题 |

也可以分 Round 1 (converge+diverge) vs Round 2 (chain+viewpoint) 来对比。

---

### 方向 D: 时间效率分析

> 与时间相关的指标

| 指标 | 说明 | 数据来源 |
|------|------|---------|
| **Avg pipeline time/frame** | 每帧平均生成耗时 | `summary.json → elapsed_ms` |
| **Avg time per question** | 每题平均生成时间 | `generation_elapsed_ms` |
| **Avg time per new L2** | 每新增一个 L2 覆盖的时间成本 | `elapsed / delta_l2` |
| **Pipeline breakdown** | precompute / plan_cache / selection_gen / verify | `pipeline_timing.*` |
| **Throughput** | 题/秒, gaps/秒 | 计算得出 |
| **Time to 50%/90%/100%** | 按时间轴的覆盖里程碑 | 从时间戳提取 |

---

### 方向 E: 场景复杂度 vs 覆盖效率

> 分析场景复杂度如何影响覆盖效率

按节点数分桶（如 3-10, 11-20, 21-30, 31-50, 50+），分析每个桶的:
- 平均 L2 gap 数
- 平均生成题数
- 覆盖效率 (gaps/questions)
- 平均每题新增 L2
- 到达 100% 所需平均题数

---

### 方向 F: 初始覆盖率影响分析

> NuScenes-QA 原始题目提供了多少起点覆盖？

| 指标 | 说明 |
|------|------|
| 有初始覆盖的帧比例 | 51.2% 的帧有 L2>0 初始覆盖 |
| 初始覆盖来源 | 确定性匹配 vs LLM 匹配 (从 `initial_coverage` 状态统计) |
| 初始 L0 平均覆盖率 | 46.9% — 说明原始QA已覆盖近半对象 |
| 初始 L2 平均覆盖率 | 1.0% — 但 L2 层面几乎没有覆盖 |
| 初始覆盖与最终效率的关系 | 初始覆盖高的帧是否需要更少的题? |

---

### 方向 G: Selection Phase 对比

> primary vs coverage_backfill 的效率差异

| Phase | 题数占比 | Avg ΔL2/Q | 说明 |
|-------|---------|-----------|------|
| primary | ? | ? | 首选出题 |
| coverage_backfill | ? | ? | 覆盖补充 |

---

### 方向 H: 覆盖重叠率分析

> 每道题的 raw_l2（理论覆盖）vs delta_l2（实际新增），衡量选题策略避免重复的能力

| 指标 | 说明 |
|------|------|
| 全局重复率 | `1 - sum(delta_l2) / sum(raw_l2)` |
| 分段重复率 | ��同覆盖率阶段的重复比例 |
| 随出题数增加的重复率趋势 | 后期重复率是否显著上升 |

---

## 四、AUC 展示方式建议

> [!IMPORTANT]
> 关于 AUC 的展示，有 3 种方案：

### 方案 1: 直接在覆盖率图上标注（现在的做法）✅
- 优点：直观、一目了然
- 缺点：只能展示一个数字，缺乏对比

### 方案 2: 在覆盖率图的曲线与 x=1.0 之间填色标注
- 用浅色填充 AUC 区域，视觉上直接表达"面积"含义
- 后续加入 Random 后，两条曲线之间的 AUC 差可以用不同颜色填充

### 方案 3: 放入汇总表中
- AUC 作为表格的一行，与其他指标（覆盖效率、到达里程碑题数等）并列
- 适合论文正文中作为量化对比的主要参考

**我的建议**: **方案 1 + 方案 3 结合** — 图上保留 AUC 标注（直观），同时在汇总表中也列出完整 AUC 对比（严谨）。后续 Random baseline 加入后，表中可以直接对比两者 AUC。

---

## 五、建议的表格设计

### 表 1: 覆盖效率汇总表（RQ2 核心表）

| Metric | L0 (Object) | L1 (Relationship) | L2 (Triple) |
|--------|-------------|-------------------|-------------|
| Total Count | 107,648 | ? | 45,225,720 |
| Initial Coverage (avg) | 46.9% | 2.3% | 1.0% |
| Final Coverage (avg) | 100% | 100% | 100% |
| AUC (Absolute) | 0.9999 | 0.9974 | 0.9287 |
| AUC (Normalized) | 0.9961 | 0.9738 | 0.7739 |
| Avg New per Q | ? | ? | ? |
| Avg Q to 50% | ? | ? | ? |
| Avg Q to 90% | ? | ? | ? |
| Avg Q to 100% | ? | ? | ? |
| Redundancy Ratio | ? | ? | ? |

### 表 2: 分段覆盖效率表

| Coverage Range | Avg ΔL2/Q | Cumulative Q% | Avg Time (ms/Q) |
|---------------|-----------|---------------|-----------------|
| Initial → 25% | ? | ? | ? |
| 25% → 50% | ? | ? | ? |
| 50% → 75% | ? | ? | ? |
| 75% → 90% | ? | ? | ? |
| 90% → 100% | ? | ? | ? |

### 表 3: 按场景复杂度分组

| Node Range | #Frames | Avg Gaps | Avg Q | Efficiency | Avg Time |
|-----------|---------|----------|-------|------------|----------|
| 3–10 | ? | ? | ? | ? | ? |
| 11–20 | ? | ? | ? | ? | ? |
| 21–30 | ? | ? | ? | ? | ? |
| 31–50 | ? | ? | ? | ? | ? |
| 50+ | ? | ? | ? | ? | ? |

### 表 4: 题型贡献分析

| Family | Count | % | Avg ΔL2/Q | Avg ΔL1/Q | Round |
|--------|-------|---|-----------|-----------|-------|
| converge | ? | ? | ? | ? | 1 |
| diverge_compare | ? | ? | ? | ? | 1 |
| direction_chain | ? | ? | ? | ? | 2 |
| distance_chain | ? | ? | ? | ? | 2 |
| viewpoint_transfer | ? | ? | ? | ? | 2 |

### 表 5: Pipeline 时间拆解

| Phase | Avg Time | % of Total | Description |
|-------|----------|-----------|-------------|
| Precompute | ? | ? | 场景图预计算 |
| Plan Cache | ? | ? | 候选规划缓存 |
| Selection + Gen | ? | ? | 选题 + 生成 |
| Verify | ? | ? | 验证 |
| **Total** | ? | 100% | |

---

## 六、你觉得哪些值得做？

以上 A~H 八个方向和 5 张表都是可以从现有数据中提取的。我建议的优先级：

1. **表 1 (覆盖效率汇总)** — 必做，RQ2 核心数据
2. **表 2 (分段覆盖衰减)** — 强烈推荐，展示方法的覆盖策略特点
3. **表 4 (题型贡献)** — 推荐，展示多题型设计的合理性
4. **表 5 (时间拆解)** — 推荐，展示方法的实用性
5. **表 3 (场景复杂度)** — 可选，展示方法对不同复杂度的鲁棒性

请告诉我你觉得哪些值得做，我来填充这些表的具体数据。
