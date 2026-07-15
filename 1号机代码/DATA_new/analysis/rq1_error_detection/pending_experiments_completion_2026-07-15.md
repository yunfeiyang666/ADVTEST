# 待测实验补充记录

> 日期：2026-07-15

## 1. Random 固定预算覆盖实验

### 实验设置

- 共同帧池：308 帧。
- 共同 Seed：1001 道 mPLUG-Owl2 能答对的 NuScenes-QA 原题。
- 新题预算：1000 道。
- 帧分配：直接复用 ADVTEST 正式实验 `advtest-expanded-f308-q1000-v2` 的分配表，共 239 个有效帧；每帧题数逐项一致。
- Random 选题：在对应帧的完整可生成题池中随机抽取，不读取当前覆盖集合，不根据新增覆盖调整后续选题。
- 随机种子：42。

### 结果

| 层级 | 共同 Seed 覆盖数（初始覆盖率） | Random 新增覆盖数（新增覆盖率） | Random 最终覆盖数（最终覆盖率） | ADVTEST 新增覆盖数 |
|---|---:|---:|---:|---:|
| L0 | 1128（22.90%） | 1216（24.69%） | 2344（47.59%） | 1851（37.58%） |
| L1 | 286（0.41%） | 1666（2.39%） | 1952（2.80%） | 2756（3.95%） |
| L2 | 736（0.029%） | 1328（0.053%） | 2064（0.082%） | 4959（0.198%） |

ADVTEST 相比 Random 多新增 635 个 L0、1090 个 L1 和 3631 个 L2 覆盖项。

### 产物

- Random 套件：`scratch/rq1_seed_expansion/runs/random-expanded-f308-q1000-v2/results/random_suite.jsonl`
- 固定预算汇总：`scratch/rq1_seed_expansion/runs/random-expanded-f308-q1000-v2/results/fixed_budget_summary.json`
- Seed 去重结果：`scratch/rq1_seed_expansion/runs/random-expanded-f308-q1000-v2/results/seeded_incremental_coverage.json`
- ADVTEST 分配来源：`scratch/rq1_seed_expansion/runs/advtest-expanded-f308-q1000-v2/results/fixed_budget_summary.json`

### 验证

- Random 与 ADVTEST 的 `frame_question_counts` 完全一致。
- 两组均为 1000 道新题、239 个有效帧。
- 1001 条 Seed 全部匹配原始覆盖记录，未匹配数为 0。
- 首次试跑 `random-expanded-f308-q1000-v1` 因重新分配后访问了 251 帧，不满足逐帧一致要求，未纳入正式结果；表中只使用修正后的 v2。

## 2. QATest、QAAskeR 选择题结果

这两组的正式结果此前已经完成，但未回填到总表。本次重新核对了题库、原始输出和汇总文件。

| 方法 | 题数 | VLM 调用数 | 严格版错题数（错误率） | 两步选择版错题数（错误率） |
|---|---:|---:|---:|---:|
| QATest | 1000 | 2000 | 152（15.2%） | 153（15.3%） |
| QAAskeR | 1000 | 2000 | 58（5.8%） | 55（5.5%） |

两步选择协议先让模型自由回答原问题，再让模型把该答案映射到给定选项，因此每题调用模型两次。两组的选择题错误率与严格版基本一致。

### 产物

- 题库与构建清单：`scratch/rq1_choice_suites_v3_formal/choice_suites/choice_suite_manifest.json`
- 结果汇总：`scratch/rq1_choice_suites_v3_formal/two_step_mplug_full_v1/two_step_choice_summary.json`
- 原始逐题输出：`scratch/rq1_choice_suites_v3_formal/two_step_mplug_full_v1/`
