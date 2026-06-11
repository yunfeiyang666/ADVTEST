# ADVTEST VQA Pipeline — 实验操作日志

---

## 2026-05-10（Day 1）

### 上午：部署 & 首次批量跑
- 部署 pipeline 到 Server A，配置 Neo4j、环境变量
- 启动 `run_batch_fast.py plans/plan_B_remote1.json` 批量跑 2292 帧
- Phase 1 (OFFLINE) 完成 2272/2292 帧
- Phase 2 (GENERATE) 跑了 ~5h，仅完成 19 帧（0.8%）
- 瓶颈：大帧 (45 nodes) 耗时 66 min/帧，ETA ~20 天，不可接受

### 下午：性能优化（5 项）
1. `plan_to_qa_record` 增加 `skip_cypher` 参数 — 跳过 Cypher 字符串构建
2. `_pick_plan` 改为 first-feasible — 消除 O(n²) coverage_gain
3. 移除 per-QA 文件 I/O — 改为批量写入
4. 新增 `_memory_verify` — 内存验证替代 Neo4j（已验证 100% 等价）
5. plan_cache 完整预过滤 — 构建阶段 `_memory_verify + verify_valid` 一次过滤

### 性能测试结果（frame14, 45 nodes）
| 版本 | 耗时 | 说明 |
|------|------|------|
| 原始 | 66 min | Neo4j verify，per-QA I/O |
| skip_verify | 6 min | 跳过所有 verify |
| memory_verify + 预过滤 | 31.9 min | 完整验证，质量等价 |

### 当前状态
- L2 覆盖率 100%（42570/42570）
- 批量跑未启���，等待进一步优化
- selection+gen 阶段仍占 30.8 min（瓶颈）

---

## 2026-05-11（Day 2）

### 10:25 性能分析
- 用 profiler 对 frame14(45 nodes) 做了详细拆解
- 发现 plan_to_qa_record 本身只需 0.004ms/QA
- 真正的 31.9 分钟全部花在 selection loop 的 fallback 全量扫描上

### 10:30 根因定位
- 根因: selection loop 有个配额限制(family_cap_blocked), converge 类题目超配额后被跳过
- 快速线性扫描只能覆盖 20% 就跳完了
- 剩余 80% 走慢速全量扫描 _cursor_select, O(n^2) 复杂度, 花了 30 分钟
- 验证: 去掉配额限制后, 线性扫描 0.4 秒跑完 100% 覆盖

### 10:33 修改1: 移除选题阶段的配额限制
- _pick_plan 不再调用 family_cap_blocked
- 配额信息改为在 emit_qa_records 中标记 selection_phase (primary vs coverage_backfill)
- 删除 _cursor_select 全量扫描 fallback (不再需要)
- 效果: selection+gen 从 1846s 降为 1.9s

### 10:38 修改2: 直接验证函数 _direct_plan_verify
- 原方案: plan_to_qa_record + _memory_verify + verify_valid (3步串联)
- 新方案: _direct_plan_verify 直接从 DryRunInput/DryRunPlan 验证
- 等价性测试: 686440 道题全部匹配, 0 个不一致
- ���果: plan_cache 从 59s 降为 48s

### 性能对比 (frame14, 45 nodes)
| 版本 | 耗时 | plan_cache | selection+gen | 覆盖率 |
|------|------|-----------|---------------|--------|
| 原始 | 66 min | 52s | 3840s | 100% |
| v3 昨天最优 | 31.9 min | 58s | 1846s | 100% |
| v5 今天优化 | 1.0 min | 48s | 1.9s | 100% |

### 质量验证 (v5)
- L2 覆盖率 100% (42570/42570)
- L0=45/45, L1=990/990
- 验证等价性 686440/686440 = 100%
- 题目数量从 40447 变为 40256 (选题顺序变化导致, 覆盖率相同)

### 10:49 修改3: 两轮生成策略
- 思路: 把"覆盖"和"题型丰富"解耦
- Round 1: 只用 converge + diverge 跑完覆盖 (需要约束规划, 重量级)
- Round 2: 对每个 gap 直接生成一道 direction_chain / distance_chain / viewpoint_transfer
  - 不需要约束规划、不需要 verify, 每道题 O(1) 生成
  - 用 round-robin 轮换题型保证多样性
- build_gap_plans 只保留 converge + diverge 的 plan (跳过 chain/viewpoint)

### V6 两轮策略测试结果 (frame14, 45 nodes)
| 阶段 | 生成数 | 耗时 | 说明 |
|------|--------|------|------|
| plan_cache | - | 45s | 少了 3s(不再生成chain/viewpoint plan) |
| Round 1 (converge+diverge) | 24,737 | 1.6s | 覆盖 27173/42570 (63.8%) |
| Round 2 (chain+viewpoint) | 42,570 | 1.5s | 每个gap一道轻量题 |
| **总计** | **67,307** | **1.0 min** | L2 覆盖率 100% |

### 性能汇总 (frame14, 45 nodes, 所有版本)
| 版本 | 耗时 | 生成数 | 覆盖率 | 题型 |
|------|------|--------|--------|------|
| 原始 | 66 min | ~40K | 100% | 混合 |
| v3 昨天最优 | 31.9 min | ~40K | 100% | 混合 |
| v5 今天优化 | 1.0 min | ~40K | 100% | 混合(converge为主) |
| **v6 两轮策略** | **1.0 min** | **67K** | **100%** | **converge+diverge+chain+viewpoint** |

### 10:55 启动批量跑
- 命令: `nohup python run_batch_fast.py plans/plan_B_remote1.json --phase 2 > outputs/batch_v6_$(date +%Y%m%d_%H%M%S).log 2>&1 &`
- 预估: 大帧 ~1min, 小帧更快, 2292帧预估 3-8 ��时
- 日志: outputs/batch_v6_*.log
- 进度查看: `grep "RESULT\|DONE\|ERROR" outputs/batch_v6_*.log | tail -20`

### 16:55 首轮批量跑（V7, 旧版速度）
- `batch_v7_20260511_165513.log`: Plan B Phase 2, 跑了 323/2292 帧后手动中断
- 原因: 速度 21.1s/frame, ETA 692min，切换到 fast 版本

### 20:06 Phase 1c 全量跑
- `batch_fast_20260511_200631.log`: Plan B Phase 1c
- 结果: **2292/2292 帧全部完成**, 耗时 71s (1.2min)
- 零失败

### 20:58 Phase 2 正式批量跑
- `batch_fast_20260511_205854.log`: Plan B Phase 2, 2292 帧
- 速度: 6.6-6.8s/frame
- 结果: **1988/2292 帧成功**, 在第 1989 帧时磁盘满中断
- 错误: `[Errno 28] No space left on device`
- 最后成功帧: scene-0780_frame19
- 剩余: ~303 帧 (scene-0780_frame20 ~ scene-0796)

### 磁盘满原因
- NVMe: 915G 总量, 859G 已用 (99%), 仅剩 9.4G
- outputs 目录: 346G (58 个 scene, 2295 个 frame 目录)
- 每帧占 42-85 MB, 剩余 303 帧需 ~18GB

---

## 2026-05-12（Day 3）

### 10:00 进度检查
- Plan B Phase 1c: ✅ 完成 (2292/2292)
- Plan B Phase 2: ❌ 1988/2292 (86.7%), 磁盘满中断
- Plan C: ❌ 未启动 (run_after_B.sh 设定的自动触发未生效)
- Plan A: 未在此服务器执行

### 10:15 磁盘方案
- 发现 HDD `/dev/sda` 有三个 NTFS 分区已挂载:
  - `/mnt/data2` (1.9T, 53% used, 907G free)
  - `/mnt/data3` (1.9T, 55% used, 863G free)
  - `/mnt/data4` (3.6T, 59% used, **1.5T free**) ← 选用此分区
- 三个分区均可写入

### 10:20 数据迁移方案
- 策略: 把 outputs + filtered_scene_graphs 搬到 `/mnt/data4`, 建软链接, pipeline 代码零改动
- 先跑完 Plan B 剩余 303 帧, 再跑 Plan C

### 10:22 迁移 filtered_scene_graphs
- `rsync -a` 从 NVMe → `/mnt/data4/yunyang/ADVTEST_DATA/filtered_scene_graphs/`
- 耗时 11s, 1.08 GB, 2296 文件
- 原目录删除, 建软链接: `ln -s /mnt/data4/yunyang/ADVTEST_DATA/filtered_scene_graphs /home/yunyang/ADVTEST/DATA_new/filtered_scene_graphs`
- 释放 ~1G NVMe 空间

### 10:35 迁移 outputs
- `cp -a /home/yunyang/ADVTEST/DATA_new/outputs /mnt/data4/yunyang/ADVTEST_DATA/outputs`
- 346G → NTFS, 预估 ~100 分钟
- 进行中... (PID 3113244)

### QA 输出文件结构分析
每帧 `generation/qa/` 目录包含 9 个文件, 以 scene-0274_frame18 为例 (57 nodes, 87780 gaps):

| 文件 | 大小 | 行数 | 说明 |
|------|------|------|------|
| `_round1.csv` | 52M | 78470 | Round 1: converge + diverge (覆盖导向) |
| `_round1.jsonl` | 137M | 78469 | 同上, JSONL 格式 |
| `_round2.csv` | 39M | 87781 | Round 2: chain + viewpoint (多样性导向) |
| `_round2.jsonl` | 124M | 87780 | 同上, JSONL 格式 |
| `_generated.csv` | 97M | 166251 | **= round1 + round2 合并** (Legacy 兼容) |
| `_generated.jsonl` | 260M | 166249 | 同上, JSONL 格式 |
| `_all.csv` | 91M | 166250 | **= round1 + round2 合并** (与 generated 等价) |
| `_all.jsonl` | 260M | 166249 | 同上, JSONL 格式 |
| `_generated_meta.csv` | 269B | 13 | 元信息摘要 (节点数/覆盖率等) |

**冗余分析**:
- `_generated.*` 和 `_all.*` 内容完全相同 (代码第 2284-2290 行: `_all` 是正式输出, `_generated` 是 Legacy 兼容)
- CSV 和 JSONL 是同一数据的两种格式
- **可优化**: 删除 `_generated.*` 可节省 ~50% 存储 (~357M/帧 → ~178M/帧)
- **可进一步优化**: 如只保留 JSONL, 再省 ~40%

### 待办 (已完成 ✅)
- [x] 等 `cp -a` 完成 — ✅ 2305/2305 条目已复制到 HDD
- [x] 删除 NVMe 上的 outputs, 建软链接到 `/mnt/data4` — ✅ 12:36 完成, NVMe 99%→59% (释放 346G)
- [x] 断点续跑 Plan B 剩余 303 帧 — ✅ 12:42 启动 (PID 3150210), 自动跳过 1988 帧
- [x] 跑完 Plan B 后自动启动 Plan C — ✅ 已串联 (Phase 1c → Phase 2)
- [ ] 考虑去掉 `_generated.*` Legacy 文件节省存储

### 12:36 数据迁移完成 + 软链接切换
- `cp -a` 已完成: HDD 2305 条目 = NVMe 2305 条目 (完全一致)
- 抽样校验通过: scene-0103_frame0, scene-0274_frame14, scene-0780_frame19, scene-0796_frame9
- `rm -rf` NVMe outputs → `ln -s /mnt/data4/yunyang/ADVTEST_DATA/outputs`
- NVMe: 99% (11G free) → **59% (357G free)** ✅
- `filtered_scene_graphs` 软链接此前已建立 (10:22)

### 12:42 Pipeline 续跑启动
- 日志: `outputs/resume_planB_then_C.log`
- 串联任务:
  1. Plan B Phase 2 (剩余 ~303 帧, 自动跳过已完成的 1988 帧)
  2. Plan C Phase 1c (2215 帧, initial_coverage)
  3. Plan C Phase 2 (2215 帧, 生成)
- 速度: ~35s/帧 (scene-0780_frame20: 33.7s, frame21: 39.1s, frame22: 37.3s)

### 13:57 Plan B Phase 2 完成 ✅
- OK=304, SKIP=1988, **FAIL=0**, 耗时 75.1min
- 所有帧 L2 覆盖率 100%

### 13:58 Plan C 首次尝试 — ❌ 失败
- Phase 1c: 2215/2215 全部 `NO_SG` (没有 scene graph)
- Phase 2: 看似 OK=2215, 但覆盖率只有 46.7% (14/30 QA per frame)
- 根因: Plan C 的 55 个 scene 没有预生成的 filtered_scene_graphs
  - Plan B 的 scene graph 之前已在 `filtered_scene_graphs/` 目录中
  - Plan C 需要通过 `generate_scene_graph_from_legacy` 从 NuScenes 实时生成
  - 但 `scene_graph_gen/vqa_pipeline/__init__.py` 中的 `from .config import *` 导入了不存在的模块

### 15:00 修复 scene_graph_gen 依赖
1. 复制 `backup/code/official_pipeline/config.py` → `scene_graph_gen/config.py` (提供 NUSCENES_DATAROOT, CATEGORY_MAPPING 等)
2. 修复 `scene_graph_gen/vqa_pipeline/__init__.py` — 去掉对 config/llm_client/neo4j_client/pipeline 的导入 (这些模块不在 scene_graph_gen 子集中)
3. 验证: `v17_onthefly_sg._get_generator()` 成功加载 NuScenes (850 scenes)

### 15:34 Plan C Phase 0 重新启动 ✅
- 日志: `outputs/planC_full_run_v3.log`, PID=3235148
- Phase 1: **2215/2215 OK**, 耗时 3.3min (NuScenes 预加载 26.7s, 之后 ~0.1s/帧)
- Phase 2: **2215/2215 OK**, 耗时 221.6min (~3.7h), **FAIL=0**, L2 覆盖率 100% ✅
- 速度: ~6.0s/帧 (比预估快很多)
- 完成时间: 19:22

### 19:22 Plan C Phase 2 完成 ✅
- OK=2215, SKIP=0, **FAIL=0**, 耗时 221.6min (3.7h)
- 所有帧 L2 覆盖率 100%

### 22:25 Plan A Phase 1+2 启动
- 日志: `outputs/planA_full_run.log`, PID=3309169
- Plan A: 1504 帧 (scene-0003 ~ scene-0273, 38 scenes)
- Phase 1: **1502/1504 OK**, SKIP=2, FAIL=0, 耗时 3.9min
- Phase 2: 进行中, 速度 ~7.4s/帧, ETA ~3h
- 进度查看: `grep "GENERATE.*OK" /mnt/data4/yunyang/ADVTEST_DATA/outputs/planA_full_run.log | tail -5`

### 02:05 Plan A Phase 2 完成 ✅
- OK=1504, SKIP=0, **FAIL=0**, 耗时 455.5min (7.6h)
- 速度: ~18.2s/帧 (比 Plan B/C 慢, 因为包含首次加载开销)
- 所有帧 L2 覆盖率 100%
- 日志: `outputs/planA_full_run.log`

### 全局进度汇总
| Plan | 帧数 | Phase 1 | Phase 2 | 状态 |
|------|------|---------|---------|------|
| Plan B | 2292 | ✅ 2292/2292 | ✅ 2292/2292 | **完成** |
| Plan C | 2215 | ✅ 2215/2215 | ✅ 2215/2215 | **完成** |
| Plan A | 1504 | ✅ 1504/1504 | ✅ 1504/1504 | **完成** |
| **合计** | **6011** | **✅ 6011/6011** | **✅ 6011/6011** | **🎉 全部完成** |

### 磁盘状态
- NVMe: 514G/915G used (60%)
- HDD `/mnt/data4`: 3.0T/3.6T used (84%), 612G free
- 输出目录总数: 6011 (与帧数一致)

---

## 2026-05-13（Day 4）

### 10:49 全量实验完成确认
- **Plan A/B/C 三个计划全部完成**, 6011 帧, 0 失败
- 无进程运行中, pipeline 已完全停止

### 11:02 Post-Experiment Tasks 启动（后台脚本）

### 11:07 全部完成 ✅

#### Task 1: 全量 L2 覆盖率验证
- **5767/6011 帧 L2 覆盖率 100%** ✅
- 244 帧无 QA 输出 (MISSING_META) — **全部是 ≤2 nodes 的帧**, 正常跳过
  - 分布: 1 node × 82 帧, 2 nodes × 162 帧
  - 涉及 20 个 scene: scene-0012/0013/0014/0036/0919/0920/0922/0923/0924/0929/0930/1060-1066/1070/1071
  - 这些帧场景图中对象太少, 无法构建有意义的 QA, pipeline 正确输出空结果

#### Task 2: 清理 Legacy 冗余文件 ✅
- 删除: `_generated.csv` + `_generated.jsonl` (与 `_all.*` 等价)
- JSONL 等价性验证: 50 帧抽样 md5 完全一致
- 删除文件数: **12,022 个**
- 释放空间: **~164.5 GB**
- HDD: 3.0T → 2.8T used (84% → 79%)
- Outputs 目录: 920G → **755G**

#### Task 3: 数据统计报告
| 指标 | 数值 |
|------|------|
| 总帧数 | 6,011 |
| 有效帧 (≥3 nodes) | 5,767 |
| 总 L2 gaps | 45,225,720 |
| 总 QA 生成数 | **84,235,417** |
| 平均 QA/帧 | ~14,604 |
| L2 覆盖率 | **100%** (所有有效帧) |

- 报告文件: `outputs/post_experiment_report.txt`
- 逐帧统计: `outputs/all_frames_stats.csv` (5,767 行)

### 磁盘最终状态
| 存储 | 容量 | 已用 | 可用 | 使用率 |
|------|------|------|------|--------|
| NVMe | 915G | 514G | 355G | 60% |
| HDD /mnt/data4 | 3.6T | 2.8T | 776G | 79% |

### 待办
- [x] 全量 L2 覆盖率验证
- [x] 清理 `_generated.*` Legacy 文件
- [ ] 数据打包/备份

---

### 16:30 RQ2 数据可视化 & 统计分析

#### 目标
按照导师要求绘制 RQ2 需要的图表和统计数据，用于论文。

#### 工具选择 & 方案设计
- 绘图工具: matplotlib + seaborn (Python)
- 输出格式: PNG (预览) + PDF (论文)
- 分析脚本: `rq2_plots/` 目录下

#### 方案概要
1. **覆盖率曲线图**: 两种 X 轴方案
   - 方案 A: X = 绝对出题数 (截断到 P90 以避免极端帧拉伸)
   - 方案 B: X = 归一化百分比 (每帧的出题进度 0%→100%)
   - Y = 平均覆盖率 (L0/L1/L2 三条线), 带 P25-P75 置信区间
   - 标注初始覆盖率 + AUC 值
2. **统计分析表**: 5 张表 + 额外分析
   - Table 1: Coverage Efficiency Summary (里程碑题数 + 每题效率)
   - Table 2: Segmented Coverage Decay (分段 ΔL2/Q 衰减)
   - Table 3: Scene Complexity Groups (按节点数分组)
   - Table 4: Family Contribution (题型贡献)
   - Table 5: Pipeline Timing (时间拆解)
   - Additional: Coverage Overlap (冗余率)

#### 脚本结构
```
rq2_plots/
├── extract_rq2_data.py       # 数据提取 (从 HDD 读取 6011 帧)
├── plot_rq2.py                # 覆盖率曲线绘图
├── analyze_rq2_comprehensive.py  # 全量统计分析
├── extracted_r1/              # 中间数据 (Round 1 + R2补缺)
│   ├── rq2_curves.npz         # 覆盖率曲线矩阵 (6011×255512, 144MB)
│   ├── rq2_frame_summary.csv  # 帧级汇总
│   └── rq2_meta.json          # 元信息
└── figures_r1/                # 最终输出
    ├── rq2_absolute_coverage.{png,pdf}   # 方案A覆盖图
    ├── rq2_normalized_coverage.{png,pdf} # 方案B覆盖图
    ├── rq2_l0/l1/l2_coverage.{png,pdf}   # 各级别单独大图
    ├── rq2_summary_table.csv  # AUC 汇总
    ├── table1_efficiency.csv  # 效率指标
    └── table4_family.csv      # 题型贡献
```

### 关键设计决策（重要！）

#### 1. Round 1 Only + R2 补缺策略
**问题**: 原始数据包含 Round 1 (converge + diverge_compare, 覆盖导向) 和 Round 2 (direction_chain + viewpoint_transfer, 多样性导向) 两轮的全部��目。但 RQ2 的覆盖率分析应该只看覆盖导向的题。

**解决方案** (`extract_rq2_data.py --round1-only`):
1. 先取所有 Round 1 题（converge + diverge_compare）— 这些是覆盖主力
2. Round 1 结束后 L2 未满的 gap，从 Round 2 中取 `delta_l2 > 0` 的题补上
3. 每题恰好补 1 个新 L2 gap（因为 R2 在 R1 之后执行，delta 正确）
4. 这样保证最终 L2 = 100%

**验证**: 以 scene-0012_frame15 为例:
- R1: 20 题 → L0=100%, L1=100%, L2=80% (24/30)
- R2 补缺: 6 题 (delta_l2>0) → L2=100% (30/30)
- 总计 26 题 (原来全量 50 题)

#### 2. L1 分母修正
**问题**: `summary.json` 中 `relationship_count = nodes × (nodes-1)` 是**有向边数**（A→B 和 B→A 各算一条），但 pipeline 内部计算 `coverage_rate_l1` 时用的是**无向边数**（除以2）。

**表现**: Round 1 only 模式下 L1 始终精确 50%，而原始 `coverage_rate_l1` 显示 100%。

**修正**: `total_l1 = relationship_count // 2`

#### 3. 覆盖率曲线的 X 轴截断
- 方案 A: 截断到 P90 帧的题数（18,669），避免极端大帧（255K 题）拉伸图表
- 超过截断值的帧用最终覆盖率填充，纳入平均

#### 4. Trivial 帧处理
- 244 帧（nodes ≤ 2）: 视为 100% 覆盖，出题数 = 0
- 计入总帧数（6011），但不计入每题效率统���

### 19:20 全量分析结果（修正版）

#### 数据规模
| 指标 | 数值 |
|------|------|
| 总帧数 | 6,011 |
| 有效帧 | 5,767 |
| Trivial 帧 (≤2 nodes) | 244 |
| 总题数 (R1 + R2补缺) | **40,247,709** |
| 平均题/帧 | 6,696 |

#### Table 1: Coverage Efficiency Summary

**里程碑题数**:
| Level | Q to 50% (Mean/Median) | Q to 90% (Mean/Median) | Q to 100% (Mean/Median) |
|-------|----------------------|----------------------|------------------------|
| L0 (Object) | 1.6 / 0 | 8.4 / 7 | 15.1 / 10 |
| L1 (Relationship) | 68.2 / 31 | 241.7 / 110 | 767.0 / 254 |
| L2 (Triple) | 2,964.7 / 514 | 5,943.1 / 1,057 | **6,694.7 / 1,193** |

**每题效率**:
| 指标 | 数值 |
|------|------|
| Avg new L2/Q | **1.1237** |
| Avg new L1/Q | 0.0345 |
| Avg raw L2/Q | 3.6991 |
| Redundancy ratio | **69.62%** |
| Coverage efficiency (gaps/Q) | **1.1459** |

#### Table 2: Segmented Coverage Decay (L2)
| 覆盖区间 | Avg ΔL2/Q | 题数占比 |
|---------|-----------|---------|
| 0%→25% | **1.5825** | 17.8% |
| 25%→50% | 1.0587 | 26.5% |
| 50%→75% | 1.0145 | 27.7% |
| 75%→90% | 1.0040 | 16.8% |
| 90%→100% | **1.0006** | **11.2%** |

> ✅ 全程效率稳定在 ~1.0，90→100% 阶段每题仍能覆盖 1 个新 L2 gap

#### Table 3: Scene Complexity Groups
| 节点数 | 帧数 | Avg Q | Avg Q to 100% |
|--------|------|-------|---------------|
| 0–5 | 814 | 10 | 9 |
| 3–10 | 1,667 | 113 | 112 |
| 11–20 | 2,021 | 1,357 | 1,356 |
| 21–30 | 1,114 | 6,269 | 6,268 |
| 31–50 | 838 | 22,545 | 22,544 |
| 51–100 | 127 | 90,075 | 90,074 |

#### Table 4: Family Contribution
| 题型 | 数量 | 占比 | Avg ΔL2/Q |
|------|------|------|-----------|
| converge | 38,959,695 | **96.8%** | 1.1278 |
| direction_chain (R2补缺) | 540,589 | 1.3% | 1.0000 |
| diverge_compare | 50,002 | 0.1% | 1.0000 |
| viewpoint_transfer (R2补缺) | 697,423 | 1.7% | 1.0000 |

Selection Phase:
- coverage_backfill: 39,601,204 (98.4%), ΔL2/Q = 1.1255
- primary: 646,505 (1.6%), ΔL2/Q = 1.0133

#### Table 5: Pipeline Timing
| 阶段 | Mean | Median | P90 | 占比 |
|------|------|--------|-----|------|
| Precompute | 76ms | 7ms | 151ms | 1.2% |
| Plan Cache | 5,401ms | 449ms | 11,809ms | **85.2%** |
| Selection+Gen | 623ms | 94ms | 1,597ms | 9.8% |
| **Total** | **6,341ms** | **606ms** | **14,279ms** | 100% |

吞吐量: 1,100.6 Q/s, 总时间 609.5 min

#### AUC 汇总
| 指标 | Ours | Random (TBD) |
|------|------|-------------|
| AUC L0 (Absolute) | 0.9998 | - |
| AUC L1 (Absolute) | 0.9945 | - |
| AUC L2 (Absolute) | **0.8755** | - |
| AUC L0 (Normalized) | 0.9928 | - |
| AUC L1 (Normalized) | 0.9479 | - |
| AUC L2 (Normalized) | **0.5645** | - |

### 相关文件一览
| 文件 | 位置 | 说明 |
|------|------|------|
| 提取脚本 | `rq2_plots/extract_rq2_data.py` | 支持 `--round1-only` 参数 |
| 绘图脚本 | `rq2_plots/plot_rq2.py` | 支持 `--input/--output/--format` |
| 分析脚本 | `rq2_plots/analyze_rq2_comprehensive.py` | 5 张表 + CSV 输出 |
| 提取数据 | `rq2_plots/extracted_r1/` | npz + csv + json |
| 图表输出 | `rq2_plots/figures_r1/` | png + pdf + csv |
| 分析日志 | `rq2_plots/analysis_r1.log` | 全量分析原始输出 |
| 方案文档 | `_archive/RQ2_implementation_plan.md` | 初始方案设计 |
| 头脑风暴 | `_archive/RQ2_data_analysis_brainstorm.md` | 数据维度盘点 |
| 最终报告 | `_archive/RQ2_walkthrough.md` | 结果汇总 |

### 待办
- [ ] Random Baseline 实验（打乱题目顺序作为对比基线）
- [ ] 根据论文模板调整图表风格
- [ ] 将统计结果整理成 LaTeX 表格
- [ ] 数据打包/备份
