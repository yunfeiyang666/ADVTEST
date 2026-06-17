# RQ1 组会后最小实验方案

日期：2026-06-17

目标：先删繁就简，只做三条方法线的最基础故障检测结果。Random 暂时移到后续消融 RQ；人工检测后面单独做，不进入这轮最小实验。

## 1. 这轮要比较什么

这轮只比较三条线：

| 方法 | 角色 | 本轮是否跑 | 说明 |
|---|---|---:|---|
| ADVTEST | 我们的方法 | 是 | 使用统一 seed bank，并在选定帧集合的全局 gap 上继续扩展覆盖 |
| QATest | 外部 baseline | 是 | 直接用原始代码，不调优，只给 seed 和预算 |
| QAAskeR | 外部 baseline | 是 | 直接用原始代码，不调优，只给 seed 和预算 |
| Random | 消融 baseline | 否 | 先不做，后续消融 RQ 再统一做 |

本轮先只要最基础检错率数据：

- 生成/测试了多少题。
- 调用了多少次 VLM。
- 发现多少自动判错或 metamorphic violation。
- fail rate / violation rate。
- ADVTEST 额外报告结构覆盖率：`covered_gap / total_gap`。

人工检测、valid failure audit、human adjudication 全部后置。

## 2. 统一 seed 怎么来

统一 seed bank 的构造流程：

1. 先确定一批评测帧，例如按当前帧池选若干帧。
2. 把这些帧里所有 NuScenes-QA 原始题取出来，目标量级约 400-500 道，具体数量取决于选多少帧以及每帧官方题量。
3. 用同一个 VLM 跑这些官方原题。
4. 只保留 VLM 答对的官方题作为 seed。

这样做的目的：

- 所有方法从同一批“模型已经能答对的原始 QA”出发。
- 后续检错更像是在问：从这些安全起点继续生成测试，谁更容易把模型逼错。
- 避免 baseline 复用 ADVTEST 私有候选池或 coverage footprint。

seed bank 至少要保存：

| 字段 | 用途 |
|---|---|
| `seed_id` | 唯一标识 |
| `scene_frame` / `sample_token` | 绑定帧和图像 |
| `official_question` | 官方原题 |
| `official_answer` | 官方答案 |
| `vlm_primary_answer` | VLM 在 seed 筛选阶段的回答 |
| `is_seed_correct` | 是否答对，只有 true 进入 seed bank |
| `source_dataset` | NuScenes-QA |

## 3. 初始覆盖怎么算

初始覆盖不再复杂展开。按我们之前那套 initial coverage 计算方法来做：把统一 seed bank 放到选定帧集合里，直接算这些 seed 对全局 gap universe 的初始覆盖。

因为这轮选的帧不会太多，初始覆盖一次性算完即可，不把它做成新的研究问题。

报告里只需要写清楚三项：

- `total_gap_count`：选定帧集合里的总 gap 数。
- `initial_covered_gap_count`：统一 seed bank 带来的初始覆盖。
- `initial_coverage`：`initial_covered_gap_count / total_gap_count`。

## 4. ADVTEST 新流程

本轮不再谈“切帧”。帧集合固定后，把所有帧的 gap 合成一个全局 gap universe。

ADVTEST 流程：

1. 输入统一 seed bank。
2. 按旧方法从 seed bank 直接得到 initial coverage state。
3. 构建所选帧集合内的所有可生成候选。
4. 每轮随机选一个帧，随机过程固定 seed，保证可复现。
5. 在这个帧内，根据该帧当前覆盖状态选择 coverage gain 最大或综合得分最高的问题。
6. 生成/加入一道新题后，更新该帧 coverage，同时更新全局 coverage。
7. 重复直到生成 1000 道新题，或者候选耗尽。

最终 ADVTEST 覆盖率：

```text
global_coverage = covered_gaps_across_selected_frames / total_gaps_across_selected_frames
```

这里不再有“换帧条件”。每轮选帧由固定随机过程控制；覆盖状态只影响该帧内选哪道题。

## 5. QATest 新流程

组会决策：QATest 直接用原始代码，不做任何调优。

本轮只做最小适配：

1. 把统一 seed bank 转成 QATest 原始代码需要的输入格式。
2. 给它预算 1000。
3. 不改它的策略、不加我们的 coverage、不调参数。
4. 如果它生成质量差，这是 baseline 自己的结果，保留。

QATest 的评测口径：

- 生成 1000 道题。
- 每道题调用 VLM 一次。
- 用对应答案或变异继承答案做自动判错。
- 报告 fail rate。
- QATest 没有可靠自检机制，所以不提前人工剔除坏题；生成失败、重复、明显空题等作为单独质量数据记录，后面人工检测阶段再统一处理。

## 6. QAAskeR 新流程和预算口径

QAAskeR 的基本单位不是单题，而是一个 metamorphic pair：

```text
primary question + primary answer -> follow-up question + target answer
```

如果从零开始跑，QAAskeR 一个 pair 理论上需要两次 VLM 调用：

1. primary question 调用一次 VLM，得到 primary answer。
2. follow-up question 再调用一次 VLM，得到 follow-up answer。

但是本轮已经有统一 seed 筛选阶段：官方原题已经被同一个 VLM 跑过，并且只有答对的原题进入 seed bank。因此 QAAskeR 可以直接使用 seed bank 里的 `vlm_primary_answer` 作为 primary answer，再生成 follow-up。

本轮统一要求：**每种方法都凑 1000 道新题**。对 QAAskeR 来说，新题就是 follow-up question。

建议 QAAskeR 采用两个口径同时记录：

| 口径 | QAAskeR 怎么算 | 用途 |
|---|---|---|
| post-seed test budget | 生成 1000 道 self-check passed follow-up question，也就是 1000 个可评测 pair | 和 ADVTEST/QATest 一样，比较 seed 之后新生成测试的检错率 |
| full VLM call cost | 1000 个 pair = 1000 次 seed primary call + 1000 次 follow-up call | 如老师追问真实总调用成本，用这个解释 |

也就是说，本轮为了先跑出最小结果，让 QAAskeR 凑 **1000 道通过它自身质量检查的 follow-up 新题**，不是 500 个 pair。

但统计时不要把一个 pair 当成两条独立样本。正确口径是：

- primary + follow-up 都通过 metamorphic relation：算 1 个 passed pair。
- follow-up answer 违反 target answer：算 1 个 violated pair。
- 检错率：`violated_pairs / total_pairs`。

如果之后老师坚持“预算必须按完整 VLM call 从零计算”，那 QAAskeR 在 `vlm_call_budget=1000` 下只能跑 500 个 pair。这个可以作为附录敏感性口径，但不作为本轮最小实验主口径。

QAAskeR 有自检/过滤机制，所以要求它一直生成，直到拿到 1000 道通过自检的 follow-up。中间被它自己过滤掉的候选不要丢，记录成生成质量数据：

- attempted follow-up candidates。
- self-check rejected count。
- self-check passed count。
- 最终是否凑满 1000 道可评测 follow-up。

这部分不做人工裁判，只当作生成质量指标。后期人工检测时再统一看这些题到底是否真的有效。

## 7. 生成失败怎么处理

ADVTEST 是程序化结构题生成，正常情况下不会出现“生成失败”；如果候选耗尽或字段缺失，按工程异常记录。

QATest 和 QAAskeR 要把生成质量也作为考察数据：

| 方法 | 生成失败处理 | 本轮是否人工剔除 |
|---|---|---:|
| ADVTEST | 默认生成成功；异常才记录 | 否 |
| QATest | 原始代码生成什么就先接什么；空题、重复、格式坏、答案缺失都记录为 generation quality issue | 否 |
| QAAskeR | 使用它自己的 self-check，直到凑满 1000 道通过自检的 follow-up；被过滤的候选计入 rejected | 否 |

最小结果表除了 fail rate，还要加生成质量列：

- `attempted_generated`
- `accepted_for_eval`
- `generation_rejected`
- `generation_rejection_rate`
- `self_check_pass_rate`，没有自检的 QATest 写 N/A

## 8. 预算

本轮先定：

| 阶段 | 预算 |
|---|---:|
| seed 筛选 | 约 400-500 道官方 NuScenes-QA 原题，具体由帧集合决定 |
| ADVTEST | seed 后新生成/测试 1000 道题 |
| QATest | seed 后新生成/测试 1000 道题 |
| QAAskeR | seed 后生成/测试 1000 道通过自检的 follow-up，即 1000 个 pair |

seed 筛选是所有方法共享的中立前置步骤，不混进三种方法的主检错率里；但报告中要单独列 seed 筛选消耗了多少 VLM call。

## 9. 最小结果表

第一轮只做这个表：

| 方法 | correct seed 数 | attempted generated | accepted for eval | VLM new-test calls | full VLM call cost | failures/violations | fail/violation rate | generation rejection rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ADVTEST | 待跑 | 1000 | 1000 | 1000 | seed calls + 1000 | 待跑 | 待跑 | 0 |
| QATest | 待跑 | 待跑 | 1000 | 1000 | seed calls + 1000 | 待跑 | 待跑 | 待跑 |
| QAAskeR | 待跑 | 待跑 | 1000 follow-up | 1000 | seed calls + 1000 | 待跑 | 待跑 | 待跑 |

ADVTEST 额外加一张覆盖表：

| 指标 | 数值 |
|---|---:|
| total gaps across selected frames | 待跑 |
| initial covered gaps from mapped seeds | 待跑 |
| final covered gaps after 1000 generated tests | 待跑 |
| coverage gain | 待跑 |
| final global coverage | 待跑 |

## 10. 立即执行顺序

1. 固定帧集合。
2. 抽取这些帧里的所有 NuScenes-QA 官方题。
3. 跑 VLM，得到 correct seed bank。
4. 按旧方法直接计算 seed bank 的 initial coverage。
5. 跑 ADVTEST 1000 新题。
6. 跑原始 QATest，拿到 1000 道新题，同时记录生成质量问题。
7. 跑原始 QAAskeR，凑满 1000 道 self-check passed follow-up，同时记录 self-check rejected。
8. 只汇总基础检错率、生成质量和 ADVTEST 覆盖率。

## 11. 当前不做

- 不做 Random。
- 不做人工检测。
- 不做 assisted audit。
- 不做多 seed 稳定性。
- 不调 QATest / QAAskeR 参数。
- 不把 official category-level QA 强行硬配成 instance-level GT。

## 12. 当前执行记录（2026-06-17 晚）

本轮先跑统一 seed 前置步骤，不先进入三方法 1000 新题主实验。

已完成：

- 固定前 30 个 RQ1 评估帧。
- 从这些帧中抽取官方 NuScenes-QA 原题，共 454 道候选 seed 题。
- 生成候选 suite：`E:\Project\ADVTEST\scratch\rq1_group_minimal\runs\group-seed-candidates-f30\results\official_qa_suite.jsonl`。
- 用 MOCK 模式验证评测链路 5 题，输出正常。
- 新增 `build_seed_bank_from_eval.py`：用于把 VLM raw results 中 `is_correct=true` 的官方 QA 抽成统一 seed bank。
- 已用 MOCK 5 题验证 seed bank 抽取，输出 `correct_seed_bank.jsonl` 和 `correct_seed_bank_summary.json`。

正在跑：

- Run ID：`seed-filter-mplug-f30-q454-v5`。
- 目的：用 mPLUG-Owl2 跑 454 道官方 QA 候选题，只保留模型答对的题作为 correct seed bank。
- 运行目录：`E:\Project\ADVTEST\scratch\rq1_group_minimal\runs\seed-filter-mplug-f30-q454-v5`。
- 输入：`group-seed-candidates-f30/results/official_qa_suite.jsonl`。
- 输出 raw results：`seed-filter-mplug-f30-q454-v5/results/official_qa_suite_raw_results.jsonl`。
- 当前状态：已开始写入 raw results；完成后执行 seed bank 抽取脚本。

启动命令口径：

```powershell
E:\Project\ADVTEST\.venv310\Scripts\python.exe run_recorded_experiment.py `
  --run-id seed-filter-mplug-f30-q454-v5 `
  --purpose GroupMeeting_RQ1_seed_filter_454_official_questions_mPLUG `
  --run-root E:\Project\ADVTEST\scratch\rq1_group_minimal\runs `
  --input-file E:\Project\ADVTEST\scratch\rq1_group_minimal\runs\group-seed-candidates-f30\results\official_qa_suite.jsonl `
  --parameter frame_pool_size=30 `
  --parameter seed_candidate_questions=454 `
  --parameter model_mode=MPLUG `
  --cwd E:\Project\ADVTEST\1号机代码\DATA_new\analysis\rq1_error_detection `
  -- E:\Project\ADVTEST\.venv310\Scripts\python.exe run_suite_evaluation.py `
    --suite-dir E:\Project\ADVTEST\scratch\rq1_group_minimal\runs\group-seed-candidates-f30\results `
    --output-dir E:\Project\ADVTEST\scratch\rq1_group_minimal\runs\seed-filter-mplug-f30-q454-v5\results `
    --outputs-root E:\Project\ADVTEST\1号机代码\DATA_new\outputs `
    --dataroot E:\Project\ADVTEST\1号机代码\DATA_new\data `
    --mode MPLUG `
    --methods official_qa `
    --vlm-call-budget 454
```
