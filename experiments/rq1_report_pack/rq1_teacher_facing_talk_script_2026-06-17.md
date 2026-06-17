# RQ1 Teacher-Facing Talk Script

Date: 2026-06-17

Purpose: use this as the spoken script for the evening report. It is written in
the voice of a student explaining the experiment to a teacher.

Related files:

- Main report: `rq1_evening_report_2026-06-17.md`
- Source index: `rq1_evening_report_source_index_2026-06-17.md`
- Slide outline: `rq1_fault_detection_slide_outline_2026-06-17.md`

## Opening

老师，我这次主要汇报 RQ1 故障检测实验的重新整理和当前结果。

我们现在把 RQ1 从“看生成问题覆盖了多少 scene graph gap”，调整成一个更接近测试的问题：

> 在相同测试预算下，哪种问题生成或选择方法，更能发现 VLM 在自动驾驶场景理解里的错误？

所以我现在不只看覆盖率，还看两个结果。

第一，同样调用 VLM 多少次，能发现多少独立错误。

第二，这些错误背后覆盖了多少结构关系，尤其是 frame-qualified L2 结构项。

这里要先讲明白：ADVTEST 的优势不是每一道题单独来看一定更容易让模型错，而是它把测试预算投向了更广的结构空间，所以能暴露更多结构关系上的失败。

## Method Flows

### ADVTEST

先讲我们的完整方法 ADVTEST。

ADVTEST 会先对每一帧构建结构化候选问题空间。每道候选题都对应一些结构覆盖信息，比如对象层面的 L0、一跳关系 L1，以及更复杂的 L2 关系。

然后我们按固定帧顺序进入每一帧。在当前帧里，ADVTEST 不是随机选题，而是优先选择能带来最大新增结构覆盖的问题。每生成一道题后，就更新当前已经覆盖的结构项。等到当前帧覆盖收益变低、候选题耗尽，或者达到单帧题数上限，就切到下一帧。

所以 ADVTEST 的特点是：它用 coverage feedback 指导选题，目标是在固定题数或固定 VLM 调用次数下，让测试覆盖尽可能多的结构关系。

### Random

然后是 Random。

Random 和 ADVTEST 用的是同一个结构化候选问题空间、同一批帧、同样的单帧上限。区别只有一个：Random 不看 coverage，不看 gap，也不根据历史覆盖更新策略，它就是随机抽题。

所以 Random 不是外部 baseline，而是内部消融。它回答的问题是：在同样的候选空间里，coverage-guided selection 是否比 random selection 更好。

### Official NuScenes-QA

接着是 Official NuScenes-QA。

Official-QA 是官方题集参考。它直接使用官方 NuScenes-QA 原题和官方答案，不读取我们的候选池，不读取我们的 gap，也不继承我们的 coverage footprint。

但它的 ground truth 是 category-level，比如 car、truck、数量、yes/no；而我们的方法是 instance 或 relation-level，比如具体对象和结构链。所以 Official-QA 只能作为中立参考，不能和 ADVTEST 直接比较结构 L2 覆盖。

### QATest-adapted

然后是 QATest-adapted。

QATest-adapted 是外部方法参考。它不是逐字节复现原版 QATest，因为原版依赖旧环境、硬编码模型路径和外部服务，不适合直接复现实验。

我们保留它的核心思想：从官方 NuScenes-QA seed 出发，做文本变异，然后用 Rouge-1、POS transition、n-gram coverage、去重等机制筛选候选问题。它不读取 ADVTEST 的候选池或 coverage 信息。

所以 QATest-adapted 是独立外部参考，但它仍然继承官方 QA 的 category-level 答案粒度，因此也不能参与 structural L2 head-to-head。

### QAAskeR

最后是 QAAskeR。

QAAskeR 当前没有放进主表。原因是它的预算口径不同。它通常需要先问 primary question，得到模型回答后，再生成 follow-up question，再调用一次 VLM。所以一个完整 pair 至少消耗两次 VLM call。

而 ADVTEST、Random、Official-QA、QATest-adapted 都是一题一次 VLM call。为了主表公平，本轮先不把 QAAskeR 放进 1000-call 主比较，后续可以单独做 two-call protocol 或 capacity table。

## Seeds And Budgets

seed 方面，ADVTEST 和 Random 都来自我们程序化构造的结构化候选空间。它们共享帧顺序、单帧上限和 instance/relation-level GT。区别只是选题策略。

Official-QA 的 seed 是官方 NuScenes-QA 原题，不做结构扩展。

QATest-adapted 的 seed 也是官方 NuScenes-QA，但它会从官方原题出发做变异、过滤和去重。

预算方面，我现在明确区分两个预算。

generation_budget 是离线生成多少题，用来看覆盖和生成能力。

vlm_call_budget 是实际调用 VLM 多少次，用来看故障检测能力。

主实验统一使用 VLM call budget，因为我们最终比较的是同样测试成本下谁发现更多错误。

本轮主实验是每个方法 1000 次真实 VLM call，四个方法一共 4000 次真实推理，没有 mock fallback。

## Main Experiment

主实验模型是 mPLUG-Owl2。

结果是：

- ADVTEST：1000 calls，981 个 wrong，也就是 981 个 independent failures，failed unique L2 是 4488。
- Random：1000 calls，912 个 independent failures，failed unique L2 是 2727。
- Official-QA：1000 calls，650 个 independent failures。
- QATest-adapted：1000 calls，637 个 wrong，但去重后 independent failures 是 468，duplicate rate 是 0.265。

这里最公平的比较是 ADVTEST vs Random。

ADVTEST 比 Random 多发现 69 个 independent failures，相对提升 7.57%。

更关键的是 failed unique L2：ADVTEST 是 4488，Random 是 2727，多 1761，相对提升 64.58%。

所以我的结论不是简单说 ADVTEST 让模型错得更多，而是说 ADVTEST 能把模型错误暴露到更广的结构关系空间里。

## Random Seed Check

为了确认不是 Random seed 42 偶然偏弱，我又做了 100-call 的 Random seed 检查。

ADVTEST 在 100 calls 下发现 92 个 independent failures，failed unique L2 是 236。

Random seed 42 是 86 个 failures，failed L2 是 169。

seed 43 是 88 个 failures，failed L2 是 180。

seed 44 是 90 个 failures，failed L2 是 183。

Random 三个 seed 的平均 independent failures 是 88，平均 failed unique L2 是 177.33。

ADVTEST 对比 Random 平均值，independent failures 多 4 个，failed unique L2 多 58.67。

所以 raw failure count 的优势是有的，但不算巨大；结构失败覆盖，也就是 failed L2，优势更稳定、更明显。

## Failure Audit

我还做了 failure audit，因为自动评分得到的 wrong 不一定都是真实视觉或结构错误，可能有答案粒度不匹配、问题歧义、mosaic artifact 或 lexical scoring artifact。

先做了 48 行人工 sanity audit。

整体 48 行里，33 行是 valid visual or structural failure，15 行是边界问题。

其中 ADVTEST-only 的有效率是 66.7%，Random-only 是 75.0%。Random-only 单样本有效率略高。

但关键是 Random-only 的 exclusive failed L2 总空间小得多。如果粗略外推，ADVTEST-only 约 2047 个有效结构失败，Random-only 约 982 个。所以即使 Random 单样本有效率略高，ADVTEST 的有效结构失败总量仍然更大。

后来又做了 400 行 deterministic assisted audit。

结果是 311/400 是 assisted valid，25 行 uncertain。

按 bucket 看：

- ADVTEST-only：100 行里 70 行 valid，估计有效总量 2149.0。
- Random-only：100 行里 87 行 valid，估计有效总量 1138.8。

ADVTEST-only 减 Random-only 的 estimated valid total 差值是 1010.2。保守 Wilson lower-minus-upper 仍然是 +647.3。

但这里要强调：400 行是 assisted audit，不是最终纯人工审定。我们已经准备了 100 行 human adjudication pack，目前 `human_*` 还没有填，pending rows 是 100。所以今晚只能说 assisted audit 支持这个方向，不能说 human-calibrated 已经完成。

## Current Conclusion

所以目前可以总结为：

第一，我们已经把实验边界重新整理清楚，不再让外部方法复用 ADVTEST 的候选池或 coverage footprint。

第二，当前最公平的主比较是 ADVTEST vs Random，因为它们共享结构化候选空间，区别只在 selection strategy。

第三，在 1000-call mPLUG-Owl2 实验中，ADVTEST 比 Random 多发现 69 个 independent failures。

第四，更重要的是，ADVTEST 的 failed unique L2 是 4488，Random 是 2727，提升 64.58%。

第五，Random 多 seed 检查说明这个优势不是 seed 42 偶然造成的，尤其结构失败覆盖优势更稳定。

第六，failure audit 显示 Random-only 单样本有效率可以更高，但 ADVTEST 覆盖的 exclusive failed L2 空间更大，所以估计有效结构失败总量仍然更高。

最后一句话就是：

> 在相同 VLM 调用预算下，ADVTEST 相比随机结构化采样，不仅发现更多 mPLUG-Owl2 错误，更显著扩大了被触发失败的结构关系覆盖范围。它的优势主要来自覆盖广度，而不是单题有效率更高。

## If Asked

如果老师问为什么不直接说 Official-QA 或 QATest-adapted 输给我们，我就回答：

> 它们的 GT 粒度和任务来源不一样，也没有 structural L2 footprint，所以只能作为跨范式参考，不能做结构覆盖的 head-to-head。

如果老师问为什么 QAAskeR 没放进主表，我就回答：

> QAAskeR 一个完整 pair 至少消耗 primary 和 follow-up 两次 VLM call，和一题一 call 的方法预算不一致，所以后续单独做 two-call protocol。

如果老师问 Random 单样本有效率更高怎么办，我就回答：

> 是的，audit 里 Random-only 单样本有效率略高。但 testing 关心同预算下暴露的总错误空间。ADVTEST 的 exclusive failed L2 universe 更大，所以估计有效结构失败总量仍然更高。
