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

## 3. 一个必须提前说清的边界：官方 seed 没有对象 id

NuScenes-QA 原题通常没有具体 instance id 或 relation id。它给的是类别级答案，例如 car、pedestrian、数量、yes/no。ADVTEST 的 gap/coverage 是 instance/relation-level，例如具体某辆车、某个行人、某条结构关系。

所以官方 seed 不能天然变成 ADVTEST 的 L2 初始覆盖。要落地“我们的方法把 seed 当作初始覆盖率”，必须加一个映射层：

| seed 类型 | 是否能计入 ADVTEST 初始覆盖 | 处理方式 |
|---|---:|---|
| 能自动映射到具体 instance/relation/gap 的官方题 | 是 | 计入 initial covered gaps |
| 只能得到 category-level 答案，不能唯一定位对象的官方题 | 否 | 只作为中立 seed，不计入 L2 初始覆盖 |
| 多个对象都可能匹配的 ambiguous 题 | 否 | 标记 ambiguous，不能硬配 |

最小实验里建议这样做：

- seed bank 对三种方法共享。
- ADVTEST 的初始覆盖只使用“可自动映射”的 seed。
- 报告 seed-to-gap 映射率：`mapped_seed_count / correct_seed_count`。
- 映射不上的 seed 不要硬塞进 L2 coverage，否则 coverage 指标会变成假的。

## 4. ADVTEST 新流程

本轮不再谈“切帧”。帧集合固定后，把所有帧的 gap 合成一个全局 gap universe。

ADVTEST 流程：

1. 输入统一 seed bank。
2. 对能映射到 gap 的 seed，作为 initial coverage。
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

## 6. QAAskeR 新流程和预算口径

QAAskeR 的基本单位不是单题，而是一个 metamorphic pair：

```text
primary question + primary answer -> follow-up question + target answer
```

如果从零开始跑，QAAskeR 一个 pair 理论上需要两次 VLM 调用：

1. primary question 调用一次 VLM，得到 primary answer。
2. follow-up question 再调用一次 VLM，得到 follow-up answer。

但是本轮已经有统一 seed 筛选阶段：官方原题已经被同一个 VLM 跑过，并且只有答对的原题进入 seed bank。因此 QAAskeR 可以直接使用 seed bank 里的 `vlm_primary_answer` 作为 primary answer，再生成 follow-up。

建议本轮采用两个口径同时记录：

| 口径 | QAAskeR 怎么算 | 用途 |
|---|---|---|
| post-seed test budget | 生成 1000 个 follow-up，也就是 1000 个 pair | 和 ADVTEST/QATest 一样，比较 seed 之后新生成测试的检错率 |
| full VLM call cost | 1000 个 pair = 1000 次 seed primary call + 1000 次 follow-up call | 如老师追问真实总调用成本，用这个解释 |

也就是说，本轮为了先跑出最小结果，建议让 QAAskeR 凑 **1000 个 pair / 1000 个 follow-up question**，不是 500 个 pair。

但统计时不要把一个 pair 当成两条独立样本。正确口径是：

- primary + follow-up 都通过 metamorphic relation：算 1 个 passed pair。
- follow-up answer 违反 target answer：算 1 个 violated pair。
- 检错率：`violated_pairs / total_pairs`。

如果之后老师坚持“预算必须按完整 VLM call 从零计算”，那 QAAskeR 在 `vlm_call_budget=1000` 下只能跑 500 个 pair。这个可以作为附录敏感性口径，但不作为本轮最小实验主口径。

## 7. 预算

本轮先定：

| 阶段 | 预算 |
|---|---:|
| seed 筛选 | 约 400-500 道官方 NuScenes-QA 原题，具体由帧集合决定 |
| ADVTEST | seed 后新生成/测试 1000 道题 |
| QATest | seed 后新生成/测试 1000 道题 |
| QAAskeR | seed 后生成/测试 1000 个 follow-up，即 1000 个 pair |

seed 筛选是所有方法共享的中立前置步骤，不混进三种方法的主检错率里；但报告中要单独列 seed 筛选消耗了多少 VLM call。

## 8. 最小结果表

第一轮只做这个表：

| 方法 | correct seed 数 | 生成测试数 | VLM follow-up/new-test calls | full VLM call cost | failures/violations | fail/violation rate |
|---|---:|---:|---:|---:|---:|---:|
| ADVTEST | 待跑 | 1000 | 1000 | seed calls + 1000 | 待跑 | 待跑 |
| QATest | 待跑 | 1000 | 1000 | seed calls + 1000 | 待跑 | 待跑 |
| QAAskeR | 待跑 | 1000 pairs | 1000 | seed calls + 1000 | 待跑 | 待跑 |

ADVTEST 额外加一张覆盖表：

| 指标 | 数值 |
|---|---:|
| total gaps across selected frames | 待跑 |
| initial covered gaps from mapped seeds | 待跑 |
| final covered gaps after 1000 generated tests | 待跑 |
| coverage gain | 待跑 |
| final global coverage | 待跑 |

## 9. 立即执行顺序

1. 固定帧集合。
2. 抽取这些帧里的所有 NuScenes-QA 官方题。
3. 跑 VLM，得到 correct seed bank。
4. 做 seed-to-gap 自动映射，报告 mapped / ambiguous / unmatched。
5. 跑 ADVTEST 1000 新题。
6. 跑原始 QATest 1000 新题。
7. 跑原始 QAAskeR 1000 follow-up / 1000 pair。
8. 只汇总基础检错率和 ADVTEST 覆盖率。

## 10. 当前不做

- 不做 Random。
- 不做人工检测。
- 不做 assisted audit。
- 不做多 seed 稳定性。
- 不调 QATest / QAAskeR 参数。
- 不把 official category-level QA 强行硬配成 instance-level GT。

