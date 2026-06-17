# RQ1 故障检测晚间汇报稿

日期：2026-06-17

## 1. 这次汇报要讲清楚的问题

我们现在的 RQ1 不是单纯问“谁生成的问题覆盖了更多 scene graph gap”，而是问：

> 在相同测试预算下，哪种测试用例生成或选择方法更能发现 VLM 在自动驾驶场景理解中的错误？

所以主结果看两件事：

1. 同样 VLM 调用次数下，发现多少独立错误。
2. 这些错误覆盖了多少结构项，特别是 frame-qualified L2 关系项。

这里要先讲明白：ADVTEST 的优势不是“每一道题都更容易让模型错”，而是“把预算投向更广的结构空间，从而暴露更多结构关系上的失败”。

## 2. 方法流程

### 2.1 ADVTEST 完整流程

ADVTEST 是我们的完整方法。流程如下：

1. 对每一帧构建结构化候选问题空间。
2. 每个候选问题带有结构覆盖信息，包括 L0 对象、L1 一跳关系、L2 多跳或组合关系。
3. 按固定帧顺序进入当前帧。
4. 在当前帧内，优先选择能带来最大新增结构覆盖的问题。
5. 每生成一道题后，更新当前已经覆盖的结构项。
6. 如果当前帧已经覆盖充分、候选题耗尽，或者达到单帧上限，就切到下一帧。
7. 最后得到一个按覆盖增益排序的测试 suite。
8. 用 VLM 逐题推理，用自动评分判断模型是否答错。
9. 对错误样本统计独立错误数和 failed unique L2。

关键特点：

- 使用结构覆盖反馈。
- 选择题目时会看“新增覆盖收益”。
- 同一帧内是自适应更新，不是一次性排序后不变。
- 主要目标不是生成更多题，而是在固定题数或固定 VLM call 下覆盖更多关键结构。

### 2.2 Random

Random 是内部消融，不是外部 SOTA baseline。

它和 ADVTEST 使用同一个结构化候选问题空间、同一批帧、同样的单帧题数上限。不同点只有一个：

- ADVTEST 按覆盖增益选题。
- Random 完全随机选题，不读取 gap、coverage score 或历史覆盖反馈。

关键特点：

- 用来回答“coverage-guided selection 是否比随机 selection 有效”。
- 因为它共享我们的结构化候选空间，所以只能叫 internal ablation。
- 不能把 Random 包装成一个独立外部方法。

### 2.3 Official NuScenes-QA

Official NuScenes-QA 是中立参考题集。

流程：

1. 从官方 NuScenes-QA 中按 sample token 匹配当前可用帧。
2. 保留官方问题和官方答案。
3. 不改写问题。
4. 不读取 ADVTEST 的候选池、coverage、gap 或 footprint。
5. 用同样的 VLM call 预算评测。

关键特点：

- 它是 category-level ground truth，比如 car、truck、yes/no、数量。
- 它没有我们的 frame-qualified L2 footprint。
- 所以它能作为“官方 QA 参考”，不能和 ADVTEST 直接比较结构覆盖。

### 2.4 QATest-adapted

QATest-adapted 是外部方法参考，不是逐字节复现原版 QATest。

原因是原版 QATest 依赖旧环境、硬编码模型路径、外部服务或 token 风险，不能直接作为可复现实验代码使用。我们保留它的核心思想，做成可运行的 adapted 版本。

流程：

1. 只使用官方 NuScenes-QA 作为 seed。
2. 从 seed pool 中取官方问题。
3. 使用文本变异算子生成候选问题。
4. 用 Rouge-1 过滤过度偏离原题的候选。
5. 用 POS-transition probability 和 1-4 gram coverage feedback 选择更有语言变化的候选。
6. 做 duplicate rejection。
7. 生成后的题仍继承官方 QA 的答案粒度。
8. 不读取 ADVTEST 候选池、coverage gap、coverage score 或 footprint。

当前实现使用的变异算子包括：

- double question mark
- keyboard substitution
- OCR substitution
- spelling deletion
- synonym replacement
- wh contraction

QATest-adapted 的修改程度要这样理解：

| 修改项 | 是否修改 | 具体含义 |
|---|---|---|
| 图像/帧 | 否 | 仍使用官方 NuScenes-QA 对应的原始 frame，不换图、不合成新图 |
| GT 答案 | 否 | 继承官方答案，因此仍是 category-level 或 yes/no/数量级答案 |
| 目标对象/结构关系 | 否 | 不新增 instance-level 或 relation-level ground truth，也不构造我们的 L2 footprint |
| 问题文本 | 是 | 对官方原题做轻量文本变异，例如拼写删除、键盘邻近替换、OCR 混淆、同义词替换、疑问词缩写、重复问号 |
| 候选选择 | 是 | 不直接收下所有变异题，而是用 Rouge-1 保持语义贴近原题，再用 POS-transition 和 1-4 gram coverage feedback 选更有语言变化的候选 |
| 去重 | 是 | 归一化文本去重，避免同一变异题重复进入测试集 |
| ADVTEST 私有信息 | 否 | 不读取我们的候选池、gap、coverage score、coverage footprint |

这意味着 QATest-adapted 的“改”主要发生在语言表面和候选选择上，不是视觉场景改造，也不是结构标签改造。它适合回答“官方 QA 经过 QATest 风格文本变异后，会不会更容易测出 VLM 错误”；但它不适合直接回答“谁覆盖了更多结构 L2”。

本轮 1000 题里，QATest-adapted 的生成行为是：

- 最终接受 1000 题。
- 实际尝试 1478 个候选。
- duplicate rejection 478 次。
- quality rejection 0 次，说明 Rouge-1 阈值在本轮没有真正挡掉候选。
- feedback insertion 357 次，说明确实启用了语言覆盖反馈。
- 1000 题来自 723 道官方 source，覆盖 100 个帧。

接受下来的变异算子分布：

| 变异算子 | 接受题数 |
|---|---:|
| keyboard_substitution | 234 |
| spelling_deletion | 232 |
| OCR substitution | 201 |
| double question mark | 188 |
| synonym replacement | 120 |
| wh contraction | 25 |

关键特点：

- 独立于 ADVTEST。
- 使用官方 QA seed。
- 保留 QATest 的“变异加反馈选择”思路。
- 但 GT 仍是官方 category-level，所以不参与结构 L2 head-to-head。

### 2.5 QAAskeR

QAAskeR 当前不进入主表。

原因不是它不重要，而是预算口径不同。QAAskeR 的完整流程通常需要：

1. 先问 primary question。
2. 得到 SUT 的 primary answer。
3. 根据这个 answer 生成 follow-up question。
4. 再问 follow-up。
5. 检查 primary 和 follow-up 是否违反 metamorphic relation。

所以一个完整 pair 至少消耗 2 次 VLM call。ADVTEST、Random、Official-QA、QATest-adapted 都是每题 1 次 VLM call。为了主表公平，本轮先不把 QAAskeR 放进 1000-call 主比较。

后续可以单独做 QAAskeR 的 two-call protocol 或 capacity table。

QAAskeR 复现接入的原理要这样讲：

| 步骤 | 原版 QAAskeR 做什么 | 接入到我们实验时的含义 |
|---|---|---|
| 1. primary question | 先拿一条源 QA 问题去问被测系统，得到 primary answer | 对 VLM 来说，就是先对一张图问原始问题，拿到模型回答 |
| 2. declarative sentence | 把“源问题 + 模型回答”改写成一个陈述句 | 例如“车在哪里？”+“左侧”变成“车在左侧”这类事实陈述 |
| 3. follow-up question | 根据陈述句生成新的追问题 | 追问题不是随便生成，而是由 metamorphic relation 约束 |
| 4. target answer | 同时推出 follow-up 的期望答案 | 这个答案来自前一步的陈述句和变形规则，不依赖人工新标注 |
| 5. violation check | 再问一次被测系统，把 follow-up answer 和 target answer 比较 | 如果不一致，就算违反 metamorphic relation，也就是发现潜在错误 |

原版 QAAskeR 有三类 MR：

- MR1：wh-question 变成另一个 wh-question，目标是问陈述句里的另一个对象。
- MR2：wh-question 变成 general yes/no question，目标答案通常是 yes。
- MR3：general/alternative question 变成 wh-question。

我们现在复现接入的是它的工具链和思想边界：`Q2S/GA2S` 负责把问题和模型回答转成陈述句，`S2G/S2W` 负责从陈述句生成 follow-up 或候选 target answer，`calculate_score` 负责比较 follow-up answer 和 target answer。它和 QATest-adapted 完全不是一条线：QAAskeR 的核心是“先问一次模型，再根据模型回答追问一次”，所以成本天然是 two-call；QATest-adapted 的核心是“对官方原题做文本变异”，生成阶段不问 VLM。

今晚可以直接这样说：

> QAAskeR 不是简单生成一批新题。它先问模型原题，拿模型自己的回答构造一个陈述事实，再围绕这个事实生成 follow-up 问题。然后它再问模型 follow-up，如果前后回答违反变形关系，就判为 failure。因此它的一个测试单元不是单题，而是 primary + follow-up 这一对，至少两次 VLM 调用。这个预算口径和我们主表里一题一 call 的方法不同，所以本轮先不放进主表。

## 3. Seed 怎么用

### 3.1 ADVTEST 和 Random

两者 seed 来源相同：

- 都来自我们程序化构造的结构化候选问题空间。
- 都使用相同帧顺序。
- 都使用相同单帧上限。
- 都保留 instance/relation-level ground truth。

不同点：

- ADVTEST 用覆盖反馈排序。
- Random 不用覆盖反馈，随机抽取。

Random 的随机种子用于控制随机抽样顺序。当前做过 seed 42、43、44 的稳定性检查。

### 3.2 Official-QA

Official-QA 的 seed 就是官方 NuScenes-QA 原题。

- 不生成新结构问题。
- 不做覆盖反馈。
- 不继承 ADVTEST footprint。
- 如果前 1000 条里有同帧重复题，会跳过重复并继续补足到 1000 calls。

### 3.3 QATest-adapted

QATest-adapted 的 seed 也是官方 NuScenes-QA。

它和 Official-QA 的区别是：

- Official-QA 直接使用原题。
- QATest-adapted 从官方原题出发做文本变异，再过滤、选择、去重。

QATest-adapted 的 1000 题生成审计结果：

这张表是在检查 QATest-adapted 生成题集本身是否干净。它不是 VLM 评测结果，而是题集构造审计：看 1000 道变异题是否重复、是否保留官方答案边界、是否误用了 ADVTEST 私有信息。

表头含义：

- `方法`：被审计的题集生成方法。
- `题数`：最终生成并保留下来的问题数量。
- `唯一问题数`：按归一化文本去重后的问题数量，用来检查是否大量重复。
- `官方 source 数`：这些变异题来自多少道官方 NuScenes-QA 原题。
- `覆盖帧数`：这些题覆盖了多少个不同帧。
- `answer mismatch`：变异题是否出现答案和官方 source 不一致的问题，0 表示没有发现。
- `boundary violation`：是否误用 ADVTEST 私有候选池、gap、coverage 或 footprint，0 表示没有边界违规。

| 方法 | 题数 | 唯一问题数 | 官方 source 数 | 覆盖帧数 | answer mismatch | boundary violation |
|---|---:|---:|---:|---:|---:|---:|
| qatest_adapted | 1000 | 1000 | 723 | 100 | 0 | 0 |

解释一下 723 个官方 source：这不是说只用了 723 道题，而是 1000 道变异题里，有些来自同一道官方原题的不同文本变体。因为它不改官方答案和图像，所以这类重复 source 会在后面的 independent failure 去重里体现出来。

这个过程可以按“抽 seed、造候选、过滤、收满预算”来讲：

1. 先从官方 NuScenes-QA 里拿 source question，当作 seed。
2. 对每个 seed 尝试多个轻量文本变异算子，比如键盘邻近替换、拼写删除、OCR 混淆、同义词替换、疑问词缩写、重复问号。
3. 每生成一个候选，就检查它是否和原题语义偏离太多、是否和已接受题重复。
4. 如果通过，就把它收进 QATest-adapted suite，并记录它来自哪一道官方 source。
5. 如果没通过，就继续尝试下一个候选，直到收满 `generation_budget=1000`。

所以 723 到 1000 的意思是：723 道官方原题贡献了 1000 个最终被接受的文本变体，其中有 277 个额外题来自已经用过的官方 source 的第二个或更多变体。中间实际尝试了 1478 个候选，丢掉了 478 个重复候选，最后留下 1000 个唯一问题文本。

这也解释了为什么 QATest-adapted 的 wrong 是 637，但 independent failures 只有 468：它确实生成了 1000 个唯一文本问题，但很多问题仍然绑定到同一张图、同一个官方答案边界、甚至同一个 source，所以发现错误时需要按 source/语义边界去重。

## 4. 预算怎么算

我们现在明确区分两个预算。

这张表是在说明本实验里“预算”到底限制什么。这里必须拆开，因为离线生成题目和真实调用 VLM 是两件事。

表头含义：

- `预算`：预算名称。
- `含义`：这个预算实际限制的对象。
- `用途`：这个预算用于回答哪类实验问题。

| 预算 | 含义 | 用途 |
|---|---|---|
| generation_budget | 离线生成多少题 | 看生成能力和结构覆盖 |
| vlm_call_budget | 实际调用 VLM 多少次 | 看故障检测能力 |

主实验使用 `vlm_call_budget`，因为最终目标是比较同样模型测试成本下能发现多少错误。

本轮主实验设置：

- 每个方法 1000 次真实 VLM call。
- 4 个方法共 4000 次真实推理。
- 无 mock fallback。
- 模型为 mPLUG-Owl2。
- 评分方式为 `token_boundary_v2_frame_qualified_l2`。

输入侧约束：

这张表是在说明四种方法进入 1000-call 主实验前的输入条件。它主要用来说明哪些方法可以直接比较结构覆盖，哪些只能作为跨范式参考。

表头含义：

- `方法`：参与评测的方法。
- `Calls`：该方法实际消耗的 VLM 调用次数。
- `Frames`：该方法的 1000 道题覆盖了多少个不同帧。
- `Max/frame`：单个帧里最多包含多少道题。
- `GT 粒度`：答案标注粒度，`instance_or_relation` 表示具体实例或结构关系级，`category_level_official` 表示官方类别级。
- `结构覆盖可比`：是否能和 ADVTEST/Random 直接比较 structural L2 覆盖。

| 方法 | Calls | Frames | Max/frame | GT 粒度 | 结构覆盖可比 |
|---|---:|---:|---:|---|---:|
| ADVTEST | 1000 | 20 | 50 | instance_or_relation | 是 |
| Random | 1000 | 20 | 50 | instance_or_relation | 是 |
| Official-QA | 1000 | 67 | 28 | category_level_official | 否 |
| QATest-adapted | 1000 | 100 | 29 | category_level_official | 否 |

因此：

- ADVTEST vs Random 是严格可比的内部消融。
- Official-QA 和 QATest-adapted 只能作为跨范式参考，不能拿 structural L2 覆盖和 ADVTEST 直接排位。

### 4.1 对象 id 和 GT 粒度怎么影响比较

这里还有一个必须讲清楚的边界：官方 NuScenes-QA 原题通常只给类别级答案，不给我们这种具体对象 id。比如官方题可能问“有几辆 car”“是否有 pedestrian”，答案是类别、数量或 yes/no；而 ADVTEST/Random 的题会绑定到具体 instance 或具体 relation，例如某个 token/id 对应的车、行人、车道关系。

所以这几种方法不是在同一个标注粒度上产生 GT：

| 方法 | 是否有具体对象 id | GT 粒度 | 能直接比较什么 |
|---|---|---|---|
| ADVTEST | 有 | instance/relation-level | 可以比较 wrong、independent failure、failed unique L2、结构覆盖 |
| Random | 有 | instance/relation-level | 可以和 ADVTEST 严格比较结构覆盖和失败结构覆盖 |
| Official-QA | 通常没有 | category-level official answer | 可以比较同等 VLM call 下的答错数量，但不能比较具体结构覆盖 |
| QATest-adapted | 沿用官方原题，通常没有 | category-level official answer | 可以比较同等 VLM call 下的答错数量和去重后失败，但不能比较具体结构覆盖 |
| QAAskeR | 取决于 source QA，本轮未进主表 | metamorphic pair-level | 后续按 two-call protocol 单独比较 violation |

因此，比较口径要分两层：

| 比较问题 | 可以放哪些方法 | 原因 |
|---|---|---|
| 同样 1000 次 VLM call，谁让模型答错更多 | ADVTEST、Random、Official-QA、QATest-adapted | 都能形成一题一 call 的测试输入和自动判错 |
| 同样结构化候选空间下，谁覆盖更多失败 L2 | 只能 ADVTEST vs Random | 两者都有具体对象 id 和 relation-level GT |
| QATest-adapted 是否比直接用官方题更强 | QATest-adapted vs Official-QA | 两者都基于官方 QA，GT 粒度一致 |
| QAAskeR 是否有效 | 单独 two-call / pair-level 表 | 它的测试单元是 primary + follow-up，不是一题一 call |

不能做的比较是：把 Official-QA 或 QATest-adapted 的结果拿来和 ADVTEST 的 failed unique L2 直接比。原因不是它们一定更弱，而是它们没有具体对象 id，无法落到同一个 L2 denominator 上。

也不要临时给官方 QA 强行补对象 id。因为“这道官方题到底指哪辆车、哪个行人、哪个 relation”很多时候并不唯一，靠规则硬配会引入新的 oracle 偏差。后续如果要做更严格的跨方法结构比较，需要单独做一个人工或半自动对齐层：把官方 QA 映射到具体 instance/relation，并记录 ambiguous / unmatched 的比例。这个目前不是主实验结论的一部分。

### 4.2 做题速度怎么算

这里也要把“做题速度”讲清楚。我们现在有两个速度口径：

- 离线出题速度：生成测试题本身花多久，不调用被测 VLM。
- VLM 测试速度：把题喂给 mPLUG-Owl2 后，平均每道题推理多久。

这张表说明每种方法在出题阶段是否需要 VLM，以及目前已有的计时结果。

表头含义：

- `方法`：参与比较的方法。
- `出题阶段是否调用 VLM`：生成题目时是否要问被测视觉模型。
- `已有出题计时`：目前脚本记录到的离线生成耗时。
- `说明`：为什么这个速度不能直接和另一个速度混在一起比。

| 方法 | 出题阶段是否调用 VLM | 已有出题计时 | 说明 |
|---|---|---:|---|
| ADVTEST | 否 | 结构化六方法联合生成约 9.78 秒 | 当前未拆成单方法精确计时，但离线生成不是主耗时 |
| Random | 否 | 同上 | 与 ADVTEST 使用同一结构化候选空间，差别是随机选题 |
| Official-QA | 否 | 约 2.00 秒生成 1100 条候选，去重后取 1000 call | 本质是从官方 QA 中取题，不做结构搜索 |
| QATest-adapted | 否 | 18.65 秒生成 1000 题 | 需要做语言覆盖评分、候选重试和 seed pool 更新，所以比简单取题慢 |
| QAAskeR | 是 | 本轮未并入主表 | 完整流程依赖 VLM primary answer 再追问，预算口径是 two-call protocol |

这张表说明真实测试阶段的速度。这里的速度不是公平性指标，只是告诉我们一轮实验大概会跑多久。公平性仍然看 `vlm_call_budget` 是否一致。

表头含义：

- `方法`：参与 1000-call 主实验的方法。
- `Calls`：真实 VLM 调用次数。
- `平均推理秒/题`：每道题调用 mPLUG-Owl2 的平均耗时。
- `约合 1000 题耗时`：按该平均速度估算，1000 题需要多久。

| 方法 | Calls | 平均推理秒/题 | 约合 1000 题耗时 |
|---|---:|---:|---:|
| ADVTEST | 1000 | 12.80 | 3.56 小时 |
| Random | 1000 | 7.86 | 2.18 小时 |
| Official-QA | 1000 | 7.21 | 2.00 小时 |
| QATest-adapted | 1000 | 4.82 | 1.34 小时 |

整轮 4000 条真实推理总耗时 32921.27 秒，约 9.14 小时。ADVTEST 单题推理更慢，主要可能和题目文本、目标关系复杂度、输出长度和机器负载有关；所以今晚不要把“跑得慢”讲成方法劣势，只讲成工程成本和后续并行化需求。

### 4.3 换帧条件和预算设置

预算设置现在采用“题数/调用数”而不是“帧数”。原因是我们的目标不是证明某个方法在固定帧数里做得更满，而是比较在相同测试成本下，谁能发现更多错误、覆盖更多失败结构。

目前已经明确的规则：

- 主实验统一 `vlm_call_budget = 1000`，也就是每个方法最多真实测试 1000 道题。
- ADVTEST 和 Random 使用同一个 100-frame pool、同一个帧顺序、同一个结构化候选空间。
- 当前主实验对 ADVTEST/Random 使用 `Max/frame = 50`，所以 1000 题正好访问 20 个帧。
- Official-QA 和 QATest-adapted 不按 structural L2 排位，只作为跨范式参考。
- QAAskeR 因为一组测试至少涉及 primary + follow-up 两次 VLM 调用，后面要单独按 two-call protocol 做。

我们前面调研和试过的换帧条件包括：

| 条件 | 含义 | 当前状态 |
|---|---|---|
| full coverage | 当前帧的 L2 gap 已覆盖满就换帧 | 适合作为 ADVTEST 的自适应策略 |
| zero-gain plateau | 连续若干题不增加新 L2，就换帧 | 候选条件是连续 10 题无增益 |
| marginal-gain decline | 后 20 题平均增益低于前 20 题的一定比例 | 候选系数是 25%，但还没定稿 |
| hard cap | 当前帧最多出多少题 | 主实验实际用 50 题/帧 |
| candidate exhausted | 当前帧候选耗尽 | 保留为自然停止条件 |

这里最关键的边界是：coverage-based 换帧只能算 ADVTEST 方法的一部分，不能给 Random、Official-QA、QATest-adapted 使用。否则 baseline 也间接用了我们的 coverage footprint，实验又会变得不干净。

当前主实验的实际情况是，ADVTEST 和 Random 都主要被 `Max/frame = 50` 控制：前 19 个帧达到 frame cap，最后在全局 1000-call 预算处停止。这说明本轮主结果主要回答的是“相同 1000 次 VLM 调用、相同 50 题/帧上限下，ADVTEST 的 selection 是否优于 Random”，还不能最终回答“最佳换帧条件是什么”。

所以今晚要把不确定性说清楚：

- `50 题/帧` 是当前主实验设置，不一定是最终最优设置。
- `100 题/帧` 是早期方案里讨论过的 hard cap，但可能让单帧消耗过多预算，需要做敏感性分析。
- `连续 10 题无增益` 和 `后 20 题增益低于前 20 题 25%` 是候选规则，不能在看完 VLM 结果后再调参。
- 下一步应该固定一组不看 VLM 结果的换帧规则，至少比较 `cap=50` 和 `cap=100`，再报告覆盖收益和故障检测收益是否稳定。

## 5. 实验一：1000-call 主实验

### 5.1 设置

模型：mPLUG-Owl2

方法：

- ADVTEST
- Random
- Official-QA
- QATest-adapted

预算：

- 每个方法 1000 real VLM calls。
- 总计 4000 real inference records。

运行情况：

- 运行完成。
- 耗时 32921.27 秒，约 9.14 小时。
- mock fallback records = 0。
- raw audit 没有 wrong mode、empty output、error 或 nonpositive-duration 记录。

### 5.2 结果

这张表是 1000-call 主实验的总结果。它在相同 VLM 调用预算下比较四种方法发现错误的情况。注意这里四种方法都能比较“错误发现效率”，但只有 ADVTEST 和 Random 能严格比较 structural L2 覆盖。

表头含义：

- `方法`：被评测的方法。
- `角色`：该方法在实验里的定位，例如 proposed、internal ablation、neutral reference 或 external reference。
- `Calls`：实际 VLM 调用次数。
- `Wrong`：自动评分判定模型答错的题数。
- `Independent failures`：去重后的独立错误数。对 QATest-adapted 来说，多道变异题可能对应同一个官方 seed，所以 wrong 和 independent failures 不一定相等。
- `UF/100`：每 100 次 VLM 调用发现多少独立错误。
- `Duplicate rate`：错误中被去重掉的比例。
- `Failed unique L2`：这些错误触发了多少个不同的 frame-qualified L2 结构项。只有 ADVTEST 和 Random 有这个指标。
- `Frames`：实际覆盖的帧数。

| 方法 | 角色 | Calls | Wrong | Independent failures | UF/100 | Duplicate rate | Failed unique L2 | Frames |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ADVTEST | proposed | 1000 | 981 | 981 | 98.1 | 0.000 | 4488 | 20 |
| Random | internal ablation | 1000 | 912 | 912 | 91.2 | 0.000 | 2727 | 20 |
| Official-QA | neutral reference | 1000 | 650 | 650 | 65.0 | 0.000 | N/A | 67 |
| QATest-adapted | external reference | 1000 | 637 | 468 | 46.8 | 0.265 | N/A | 100 |

严格可比的主结论只看 ADVTEST vs Random：

这张表只保留 ADVTEST 和 Random 的可比指标。它们使用同一个结构化候选空间、同样的帧、同样的单帧上限，区别只在 selection strategy，所以这张表才是本轮最核心的公平比较。

表头含义：

- `指标`：比较的实验指标。
- `ADVTEST`：ADVTEST 在该指标上的结果。
- `Random`：Random 在该指标上的结果。
- `差值`：ADVTEST 减 Random，正数表示 ADVTEST 更高。

| 指标 | ADVTEST | Random | 差值 |
|---|---:|---:|---:|
| 输入 covered L2 | 4508 | 2818 | +1690 |
| Independent failures | 981 | 912 | +69 |
| Failed unique L2 | 4488 | 2727 | +1761 |

相对提升：

- 输入 L2 覆盖提升 59.97%。
- independent failures 提升 7.57%。
- failed unique L2 提升 64.58%。

这说明 ADVTEST 的核心优势在 failed structural coverage，而不只是 raw failure count。

### 5.3 对 Official-QA 和 QATest-adapted 的解释

Official-QA 和 QATest-adapted 的结果不能直接说“输给 ADVTEST”，原因是：

- 它们是 category-level official GT。
- ADVTEST 和 Random 是 instance/relation-level GT。
- 它们没有 structural L2 footprint。
- 它们覆盖的帧分布也不同。

所以这两行只说明跨范式情况下的错误发现效率，不作为结构覆盖排名。

QATest-adapted 的 wrong 是 637，但 independent failures 是 468，duplicate rate 是 0.265。这说明它生成的变异题中，有不少题最终指向同一个独立失败。

## 6. 实验二：Random seed 稳定性检查

### 6.1 设置

目的：避免 Random seed 42 偶然偏弱导致 ADVTEST 看起来更好。

设置：

- ADVTEST 固定 100 calls。
- Random 分别跑 seed 42、43、44。
- 每组 100 real VLM calls。
- 仍使用 frame-qualified L2 scoring。

### 6.2 结果

这张表是在检查 Random 的结果是否受单个随机种子影响。我们固定 ADVTEST 的 100-call 结果，再把 Random 换成 3 个 seed 来跑，观察 ADVTEST 是否只是碰巧赢了 seed 42。

表头含义：

- `方法`：ADVTEST 或 Random。
- `Seed`：Random 的随机种子；ADVTEST 是固定策略，所以写 fixed。
- `Calls`：本次稳定性检查中实际调用 VLM 的次数。
- `Independent failures`：100 次调用里发现的独立错误数。
- `Failed unique L2`：这些错误覆盖到的不同 L2 结构项数量。

| 方法 | Seed | Calls | Independent failures | Failed unique L2 |
|---|---:|---:|---:|---:|
| ADVTEST | fixed | 100 | 92 | 236 |
| Random | 42 | 100 | 86 | 169 |
| Random | 43 | 100 | 88 | 180 |
| Random | 44 | 100 | 90 | 183 |

Random 三个 seed：

- independent failures 平均 88.00，标准差 1.63。
- failed unique L2 平均 177.33，标准差 6.02。

ADVTEST 相比 Random 平均值：

- independent failures +4.00，相对提升 4.55%。
- failed unique L2 +58.67，相对提升 33.08%。
- ADVTEST 在三个 Random seed 上都更高。

结论：

- failure count 上 ADVTEST 有提升，但幅度不算巨大。
- failed unique L2 上优势更明显，说明结构覆盖收益更稳定。

## 7. 实验三：Failure audit

### 7.1 为什么要做 audit

VLM 答错不一定都是真实视觉或结构错误，也可能是：

- answer granularity mismatch
- ambiguous question
- mosaic or label artifact
- lexical scoring artifact

所以我们做 failure audit，检查自动评分得到的 failure 里有多少是真正有效的视觉或结构失败。

### 7.2 48 行人工 sanity audit

设置：

- 48 行 sampled failures。
- 分成 ADVTEST-only、Random-only、shared_l2_advtest、shared_l2_random 四类。

结果：

这张表是在做 48 行人工 sanity audit。它不是重新跑 VLM，而是人工检查一小批自动判错样本里有多少是真实视觉或结构失败。

表头含义：

- `bucket`：样本来源类别。`advtest_only_l2` 表示只被 ADVTEST 触发的 L2，`random_only_l2` 表示只被 Random 触发的 L2，`shared_l2_*` 表示两边都触发过的共享 L2。
- `rows`：该类别人工检查了多少行。
- `valid yes`：人工认为是真实视觉或结构失败的行数。
- `valid rate`：`valid yes / rows`。

| bucket | rows | valid yes | valid rate |
|---|---:|---:|---:|
| advtest_only_l2 | 12 | 8 | 66.7% |
| random_only_l2 | 12 | 9 | 75.0% |
| shared_l2_advtest | 12 | 8 | 66.7% |
| shared_l2_random | 12 | 8 | 66.7% |

总体：

- 33/48 是 valid visual or structural failure。
- 15/48 是边界问题，主要是 answer granularity mismatch。

解释：

- Random-only 的单样本有效率略高。
- 但 Random-only 的 exclusive failed L2 总空间更小。
- 所以最终要看“有效失败总量”，不是只看单样本有效率。

按 48 行 audit 粗略外推：

- ADVTEST-only：3070 * 66.7% 约 2047。
- Random-only：1309 * 75.0% 约 982。
- ADVTEST 约为 Random 的 2.08 倍。

### 7.3 400 行 assisted audit

设置：

- ADVTEST-only L2：100 行。
- Random-only L2：100 行。
- Shared L2 pairs：100 pair，也就是 200 行。
- 总计 400 行。

当前是 deterministic assisted review，不是最终人工审定。

结果：

这张表是在做 400 行 deterministic assisted audit。它扩大了 48 行人工检查的规模，用确定性 assisted label 先估计各类失败的有效比例。注意它还不是最终人工审定。

表头含义：

- `bucket`：样本来源类别，含义和 48 行 audit 相同。
- `sample rows`：该类别抽样检查的行数。
- `valid yes`：assisted review 认为是真实视觉或结构失败的行数。
- `uncertain`：assisted review 不能确定、需要人工再审的行数。
- `valid rate`：`valid yes / sample rows`。
- `estimated valid total`：把该 bucket 的有效率外推到对应 L2 universe 后得到的估计有效失败总量。

| bucket | sample rows | valid yes | uncertain | valid rate | estimated valid total |
|---|---:|---:|---:|---:|---:|
| advtest_only_l2 | 100 | 70 | 6 | 70.0% | 2149.0 |
| random_only_l2 | 100 | 87 | 3 | 87.0% | 1138.8 |
| shared_l2_advtest | 100 | 77 | 8 | 77.0% | 1091.9 |
| shared_l2_random | 100 | 77 | 8 | 77.0% | 1091.9 |

总体：

- 311/400 assisted valid。
- 64 no。
- 25 uncertain。
- assisted valid rate = 77.8%。

ADVTEST-only vs Random-only：

- estimated valid total difference = +1010.2。
- conservative Wilson lower-minus-upper = +647.3。

解释：

- Random-only 单样本有效率仍更高。
- 但 ADVTEST-only 的 exclusive failed L2 universe 大得多。
- 所以估计有效结构失败总量仍然是 ADVTEST 更高。

### 7.4 Human adjudication 当前状态

我们已经生成 100 行 human adjudication calibration pack。

分布：

- 25 行 ADVTEST-only。
- 25 行 Random-only。
- 25 行 shared_l2_advtest。
- 25 行 shared_l2_random。

按 assisted label：

- yes：43。
- no：32。
- uncertain：25。

当前状态：

- reviewed rows = 0。
- pending rows = 100。
- calibrated estimates 还不可用。

所以今晚汇报必须说：

> 400 行 assisted audit 支持当前方向，但 human-calibrated 结果仍 pending。

不能说：

> 人工审计已经最终确认。

## 8. 当前结论

可以这样讲：

1. 我们已经把实验边界重新整理清楚，不再让外部 baseline 复用 ADVTEST 的候选池或 coverage footprint。
2. 当前最公平的主比较是 ADVTEST vs Random，因为它们共享结构化候选空间，区别只在 selection strategy。
3. 在 1000-call mPLUG-Owl2 主实验中，ADVTEST 比 Random 多发现 69 个 independent failures。
4. 更关键的是，ADVTEST 的 failed unique L2 是 4488，Random 是 2727，提升 64.58%。
5. Random 多 seed 检查显示，ADVTEST 在 100-call 下超过三个 Random seed，尤其 failed unique L2 优势稳定。
6. Failure audit 显示，Random-only 单样本有效率略高，但 ADVTEST 覆盖的 exclusive failed L2 空间更大，估计有效结构失败总量仍更高。
7. Official-QA 和 QATest-adapted 是跨范式参考，不能作为 structural L2 head-to-head baseline。
8. QAAskeR 由于 two-call protocol，本轮不进入主表，后续单独做。
9. 做题速度要分清离线出题和 VLM 推理；本轮公平性按 1000 次真实 VLM call 控制，不按 wall-clock 控制。
10. 换帧条件目前还不是最终定稿，`cap=50` 是当前主实验设置，后续需要做 `cap=50/100` 和 plateau/gain 阈值敏感性分析。

## 9. 今晚建议怎么讲

建议顺序：

1. 先说 RQ1 现在是 testing 问题：同预算下谁发现更多 VLM 错误。
2. 再说为什么要拆 baseline：不能让对照组复用 ADVTEST 能力。
3. 然后讲方法流程：ADVTEST 完整版，Random 只改 selection，Official-QA 直接用官方题，QATest-adapted 从官方题变异，QAAskeR 暂缓。
4. 接着讲 seed 和预算：seed 来源不同，预算统一用 VLM call。
5. 单独补一句速度：出题阶段大多不调用 VLM，真正耗时在 4000 次 mPLUG-Owl2 推理，整轮约 9.14 小时。
6. 再补一句换帧：本轮用 `Max/frame=50` 固定上限，换帧阈值还要做敏感性分析，不能现在拍死。
7. 讲主结果：ADVTEST vs Random，重点讲 failed unique L2。
8. 讲 Random seed 检查：不是 seed 42 偶然。
9. 讲 failure audit：承认边界问题，但总量优势仍在。
10. 最后讲下一步：完成 100 行 human adjudication，把 assisted audit 校准成 human-calibrated estimate；同时补 `cap=50/100` 换帧敏感性分析。

## 10. 一句话总结

在相同 VLM 调用预算下，ADVTEST 相比随机结构化采样能发现更多 mPLUG-Owl2 错误，更重要的是显著扩大了被触发失败的结构关系覆盖范围；它的优势主要来自覆盖广度，而不是单题有效率更高。
