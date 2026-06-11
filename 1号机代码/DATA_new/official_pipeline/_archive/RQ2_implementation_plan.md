# RQ2 可视化实现计划

## 背景

RQ2: **在相同预算下，你的方法能更快地提高对象/关系/属性覆盖吗？**

实验已完成：6,011 帧（5,767 有效帧，≥3 nodes），总 QA 84,235,417 条，所有有效帧 L2 覆盖率 100%。

老师要求：
- **图**: 折线图，X 轴=出题数目，Y 轴=平均覆盖率
- **表**: 覆盖率 + AUC
- 额外统计值：每题平均覆盖 L2、L1 数，以及时间相关的统计

---

## 数据源

### 主数据文件

| 文件 | 路径 | 说明 |
|------|------|------|
| **逐帧统计** | `/mnt/data4/yunyang/ADVTEST_DATA/outputs/all_frames_stats.csv` | 5,767 行，含 `scene_frame, filtered_nodes, total_l2_gaps, generated_questions, final_coverage_l2` |
| **逐题增量覆盖** | `outputs/<scene_frame>/reports/<scene_frame>_incremental_coverage.csv` | 每帧一个，含 `order_index, cum_l0, cum_l1, cum_l2, coverage_rate_l0, coverage_rate_l1, coverage_rate_l2, delta_l0, delta_l1, delta_l2, l2_family, selection_phase` |
| **元信息** | `outputs/<scene_frame>/generation/qa/<scene_frame>_generated_meta.csv` | 含 `initial_coverage_l0, initial_coverage_l1, initial_coverage_l2, total_l2_gaps` 等 |
| **摘要** | `outputs/<scene_frame>/reports/<scene_frame>_summary.json` | 含 `initial_coverage`, `universe_stats`, `pipeline_timing` |

> [!NOTE]
> 所有 outputs 位于 HDD: `/mnt/data4/yunyang/ADVTEST_DATA/outputs/`（通过软链接 `/home/yunyang/ADVTEST/DATA_new/outputs/` 访问）

### 关键字段说明

`incremental_coverage.csv` 中每行代表一道题生成后的累计覆盖状态：
- `order_index`: 题目生成顺序（1-based）
- `coverage_rate_l0/l1/l2`: 累计覆盖率 = `cum_lX / total_lX`
- `delta_l0/l1/l2`: 该题新增覆盖数
- `l2_family`: 题型 (converge, diverge_compare, direction_chain, distance_chain, viewpoint_transfer)
- `selection_phase`: primary / coverage_backfill

---

## 工具选择

| 工具 | 版本 | 用途 |
|------|------|------|
| **Python 3** | 系统自带 | 数据处理脚本 |
| **matplotlib** | 2.2.3 | 绑制折线图 |
| **pandas** | 0.23.4 | 数据读取和聚合 |
| **numpy** | 1.15.1 | 数值计算（AUC 等） |
| **seaborn** | 0.9.0 | 颜色方案辅助 |

> [!IMPORTANT]
> matplotlib 2.2.3 和 pandas 0.23.4 版本较老，需要注意 API 兼容性。不使用 f-string 以外的新特性。实际上该 Python 版本应该支持 f-string。

---

## 图表规划

### 整体设计思路

按老师要求，**X 轴是出题数目，Y 轴是平均覆盖率**。6,000 帧给平均覆盖率即可。

**核心计算逻辑**：
1. 对每帧，从 `incremental_coverage.csv` 读取逐题覆盖率曲线 `coverage_rate_l2[n]`（第 n 题后的覆盖率）
2. 对所有帧，在第 n 题位置上取平均：`avg_coverage(n) = mean(coverage_rate_l2[n] for all frames where total_questions >= n)`
3. Random baseline：对每帧，随机打乱题目顺序，重新计算累计覆盖率曲线，然后同样取全局平均

**Random Baseline 模拟方法**：
- 对每帧，已知每道题覆盖的 L2 triples（来自 `coverage_l2` 字段或 `new_l2` 字段）
- 随机打乱题目顺序，按新顺序重新累计 coverage（去重）
- 重复 K 次取平均（K=10 即可，因为 5,767 帧本身提供了足够的方差平滑）

---

### 图 1: L2 覆盖率提升折线图（主图）

> 这是 RQ2 最核心的图

- **类型**: 折线图
- **X 轴**: 出题数目 (Number of Generated Questions)，范围 [0, N_max]
- **Y 轴**: 平均 L2 覆盖率 (Average L2 Coverage Rate)，范围 [0, 1.0]
- **曲线**:
  - **Ours (红/蓝实线)**: 按 pipeline 实际出题顺序的覆盖曲线
  - **Random (灰色虚线)**: 随机出题顺序的覆盖曲线
- **初始覆盖率**: 在 X=0 处标注初始覆盖率（从 NuScenes-QA 原始题目获得的初始 L2 覆盖）
- **X 轴上限**: 由于各帧题目数差异很大（5~527,839），需要做归一化或截断处理

> [!IMPORTANT]  
> **X 轴处理方案（需要确认）**：
> 
> **方案 A - 绝对数量**: X 轴直接用题目数，截断到某个合理值（如中位数或 P75），超过的帧用最终覆盖率填充。优点：直观展示实际出题数量的意义。
> 
> **方案 B - 归一化百分比**: X 轴用 `n / total_questions_for_frame`，范围 [0, 1.0]，这样所有帧统一到同一尺度。优点：消除帧间差异。缺点：失去绝对数量信息。
> 
> **建议使用方案 A**，X 轴截断到合理范围（如 200 或 500 题），因为老师明确说"横坐标是出题数目"。大帧和小帧在有限题数内的覆盖速度差异���好体现方法效果。

### 图 2: L1 覆盖率提升折线图

- 同图 1 结构，但 Y 轴改为 L1 (Relationship) Coverage Rate
- 用于展示关系级别的覆盖速度

### 图 3: L0 覆盖率提升折线图

- 同图 1 结构，但 Y 轴改为 L0 (Object) Coverage Rate
- 用于展示对象级别的覆盖速度

### 图 4: 三级覆盖率对比（子图拼接版）

- 将图 1/2/3 合并为 1×3 或 3×1 的子图，论文排版更紧凑
- 共享 X 轴，独立 Y 轴

---

### 表 1: 覆盖率与 AUC 汇总表

| 指标 | Ours | Random | 提升 |
|------|------|--------|------|
| L0 Final Coverage Rate | - | - | - |
| L1 Final Coverage Rate | - | - | - |
| L2 Final Coverage Rate | - | - | - |
| L0 AUC | - | - | - |
| L1 AUC | - | - | - |
| L2 AUC | - | - | - |
| Avg New L2 per Question | - | - | - |
| Avg New L1 per Question | - | - | - |
| Avg Questions to 90% L2 | - | - | - |
| Avg Questions to 100% L2 | - | - | - |

**AUC 计算**: 覆盖率曲线下面积，使用梯形法则 (`numpy.trapz`)，归一化到 [0, 1]。AUC 越高说明覆盖速度越快。

---

## 数据提取流程

### Step 1: 预处理脚本 `extract_rq2_data.py`

从 5,767 帧的 `incremental_coverage.csv` 中提取数据，生成中间文件：

```
对每一帧:
  1. 读取 incremental_coverage.csv
  2. 提取 (order_index, coverage_rate_l0, coverage_rate_l1, coverage_rate_l2, delta_l2, new_l2)
  3. 生成 Random baseline: 随机打乱 new_l2 列表，重新累计覆盖率
```

输出中间文件: `rq2_coverage_curves.npz` 或 `rq2_coverage_curves.csv`

> [!WARNING]
> 5,767 帧的 incremental_coverage.csv 总数据量很大（每帧平均 ~14,600 行），全部加载到内存可能需要较大 RAM。建议分批读取，每帧只保存覆盖率曲线（不保存原始题目文本），压缩后应在可接受范围内。

### Step 2: 聚合脚本 `aggregate_rq2.py`

从中间数据计算全局平均曲线：

```python
# 对每个 n (出题数目):
#   ours_avg_l2(n) = mean(frame_coverage_l2(n) for frames where total_questions >= n)
#   random_avg_l2(n) = mean(frame_random_l2(n) for frames where total_questions >= n)
```

### Step 3: 绘图脚本 `plot_rq2.py`

使用 matplotlib 生成最终图像。

---

## 实现计划

### Phase 1: 数据提取 (`extract_rq2_data.py`)

1. 读取 `all_frames_stats.csv` 获取有效帧列表
2. 遍历每帧的 `incremental_coverage.csv`，提取覆盖率曲线
3. 对每帧生成 Random baseline（打乱 `new_l2` 后重新累计）
4. 输出中间数据到 `rq2_extracted/` 目录

### Phase 2: 聚合与绘图 (`plot_rq2.py`)

1. 加载中间数据
2. 计算全局平均覆盖率曲线（Ours vs Random）
3. 计算 AUC 和其他统计量
4. 绘制 4 张图 + 1 张表
5. 输出: PNG/PDF + 表格 CSV

### 文件组织

```
/home/yunyang/ADVTEST/DATA_new/official_pipeline/rq2_plots/
├── extract_rq2_data.py        # 数据提取脚本
├── plot_rq2.py                # 绘图脚本  
├── extracted/                  # 中间数据
│   └── rq2_per_frame_curves.npz
└── figures/                    # 输出图像
    ├── rq2_l2_coverage.pdf
    ├── rq2_l1_coverage.pdf
    ├── rq2_l0_coverage.pdf
    ├── rq2_combined_coverage.pdf
    └── rq2_summary_table.csv
```

---

## Open Questions

> [!IMPORTANT]
> **1. X 轴范围**: 各帧题目数差异极大（5~527,839），X 轴截断到多少合适？建议选项：
> - 200 题（覆盖小帧的完整曲线）
> - 500 题（覆盖中等帧）
> - 按百分位截断（如 P50 = 中位数题目数）
> - 或者同时出两张图：一张放大前 200 题，一张全局？

> [!IMPORTANT]
> **2. 初始覆盖率**: 从 `summary.json` 看到有 `initial_coverage` 数据（NuScenes-QA 原始题目的覆盖贡献），是否需要在图上标注初始覆盖率？老师截图中提到"给出初始覆盖率"。

> [!IMPORTANT]
> **3. Random Baseline 定义**: 
> - **方案 A**: 打乱同一帧内的题目顺序（保持题目不变，只变排序）
> - **方案 B**: 从该帧的全部可生成题目中随机采样（但我们只有 pipeline 实际生成的题目）
> - 建议用 **方案 A**（打乱顺序），因为它公平地对比"选题策略"的效果

> [!IMPORTANT]
> **4. 图表风格**: 
> - 论文用的是哪个会议/期刊模板？(ACM / IEEE / AAAI 等)
> - 图的字体大小、宽度等是否有要求？
> - 建议默认使用：单栏宽度 3.5in，双栏宽度 7in，字体 Times New Roman 10pt

> [!IMPORTANT]
> **5. 性能预估**: 5,767 帧的 incremental_coverage.csv 位于 HDD NTFS 分区，I/O 较慢。预估数据提取需要 30-60 分钟。是否可以先用 100 帧子集验证图表效果，再跑全量？

---

## Verification Plan

### 自动验证
1. 数据提取后验证：抽检 10 帧的提取数据是否与原始 CSV 一致
2. Random baseline 验证：确认最终覆盖率与 Ours 相同（只是到达速度不同）
3. AUC 计算验证：手动计算一帧的 AUC 与代码结果对比

### 视觉验证
1. 先用小样本（100 帧）生成预览图，确认图表格式正确
2. 全量数据生成最终图后，确认曲线趋势合理（Ours 应当比 Random 上升更快）
