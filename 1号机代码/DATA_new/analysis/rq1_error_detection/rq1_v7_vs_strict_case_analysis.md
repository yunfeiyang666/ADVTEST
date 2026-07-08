# RQ1 ADVTEST v7 与严格问答版 case 分析

本文只比较两版：

- 严格问答版：模型自由生成答案，按冻结的自动判分结果统计。
- v7 角度精细化选择题版：题目来源保持一致，转成选择题；涉及方向的题，在题干和选项里显式给出 NuScenes-QA 的方向角度标准，角度以目标朝向为 0°。

这里不讨论 v1/v3/v6，也不重算 QATest、QAAskeR；重点是看我们的题在“自由回答”和“选项明确化”之后，错误率变化是否合理。

## 1. 总体对比

| 数据项 | 严格版错误率 | v7 错误率 | 变化 |
|---|---:|---:|---:|
| ADVTEST-L0 | 45.2% | 36.2% | -9.0 pp |
| ADVTEST-L1 | 64.0% | 56.1% | -7.9 pp |
| ADVTEST-L2 mixed | 90.2% | 58.3% | -31.9 pp |
| ADVTEST-L2 converge | 90.3% | 58.7% | -31.6 pp |
| ADVTEST-L2 direction_chain | 83.8% | 12.0% | -71.8 pp |
| ADVTEST-L2 distance_chain | 52.9% | 51.3% | -1.6 pp |
| ADVTEST-L2 viewpoint_transfer | 48.3% | 81.9% | +33.6 pp |

简要读法：

- ADVTEST-L0：下降，主要是类型/状态/数量题不再被同义词和表达格式额外惩罚。
- ADVTEST-L1：小幅下降，但方向关系和计数关系仍然难，说明不是纯判分格式问题。
- ADVTEST-L2 mixed：大幅下降；mixed 仍几乎由 converge 支配，v7 去掉了自由回答的 ID/格式损失。
- ADVTEST-L2 converge：大幅下降但仍高；同类候选选择后，剩下主要是多约束定位错误。
- ADVTEST-L2 direction_chain：大幅下降；二值选择把输出格式问题压低，这类不应单独当最强证据。
- ADVTEST-L2 distance_chain：几乎不变；选择题没有明显降低难度，错误更接近真实空间距离判断失败。
- ADVTEST-L2 viewpoint_transfer：显著上升；v7 从粗粒度表达变成 6 类角度方向选择，暴露了视角转换能力弱。

补充：严格版各项均为 1000 题；v7 中 `mixed` 为 955 题、`converge` 为 973 题，因为选择题转换时强制要求同类候选、唯一正确项、无重复选项，转换不出的题没有纳入正式判分。

## 2. 同一题目上的变化

这部分不再铺宽表，只保留最关键的转移现象：

- ADVTEST-L0：可对齐 1000 题；严格错→v7对 292，严格对→v7错 202，两版都错 160。v7 修掉一部分同义词/格式问题，但仍保留大量视觉判断错误。
- ADVTEST-L1：可对齐 1000 题；严格错→v7对 331，严格对→v7错 252，两版都错 309。有改善也有反向变差，说明选项化不是简单降难度；方向关系仍会误选。
- ADVTEST-L2 mixed：可对齐 955 题；严格错→v7对 361，严格对→v7错 16，两版都错 541。主要反映 converge 的变化：自由回答时代很容易答不到精确 ID，选项化后仍有大量同类误选。
- ADVTEST-L2 converge：可对齐 973 题；严格错→v7对 362，严格对→v7错 30，两版都错 541。很多 strict 错题在 v7 能选对，但双错仍最多，说明多约束定位本身仍难。
- ADVTEST-L2 direction_chain：可对齐 1000 题；严格错→v7对 816，严格对→v7错 98，两版都错 22。大批 strict 错题在 v7 变对，说明原严格版里 yes/no 或自然语言判分损失偏大。
- ADVTEST-L2 distance_chain：可对齐 1000 题；严格错→v7对 225，严格对→v7错 209，两版都错 304。双错和反向变化都存在，整体几乎不变，比较像真实距离关系难点。
- ADVTEST-L2 viewpoint_transfer：可对齐 1000 题；严格错→v7对 113，严格对→v7错 449，两版都错 370。大量 strict 对题在 v7 变错，是因为 v7 要求按 6 类角度规则精确选方向，不再接受粗略 behind/left 叙述。

## 3. 分数据项解释

### ADVTEST-L0

- 严格版错误率 45.2%，v7 为 36.2%。这说明 L0 中确实有一部分是自动判分过严，例如 `walking` 与 `moving`、`person` 与 `pedestrian` 这类同义表达。
- 但 v7 仍有 362/1000 错题，不能把 L0 的错全归因于判分。数量题、状态题和小目标类型判断依旧会出错。

### ADVTEST-L1

- 严格版 64.0%，v7 56.1%，有小幅改善。也就是说，给出方向角度和选项后能减少一部分表达/判分损失，但 L1 的主要困难仍在空间关系本身。
- 这类题适合保留，但报告时要说明它比 L0 明显更难，尤其是方向+计数、负关系、对象间相对方向。

### ADVTEST-L2 mixed

- 严格版 90.2%，v7 58.3%，降幅很大。原因是 strict open QA 要求模型自由生成准确目标 ID；v7 把候选压到同一选项集合，减少了格式和 ID 生成负担。
- v7 mixed 有 955 题，其中 949 题是 converge，因此 mixed 不能作为均衡 L2 结论，只能作为“当前混合池主要由 converge 驱动”的补充结果。

### ADVTEST-L2 converge

- 严格版 90.3%，v7 58.7%。下降不是因为题变简单，而是因为 v7 把答案空间从开放 ID 生成改成同类候选选择。
- 即使这样仍错 571/973，说明 converge 的多约束定位仍然很强：模型经常抓住其中一两个条件，但无法同时满足全部条件。

### ADVTEST-L2 direction_chain

- 严格版 83.8%，v7 12.0%，这是最大幅下降。原因主要是这类题转成 yes/no 或 A/B 选择后，模型不用组织自然语言答案，判分也不再受表达影响。
- 所以 direction_chain 可以作为 L2 子类报告，但不适合作为“最强检错能力”的主证据；它更像检查模型是否能做一条明确关系链判断。

### ADVTEST-L2 distance_chain

- 严格版 52.9%，v7 51.3%，基本不变。这反而是最干净的信号：选择题没有明显把它变简单，模型仍然在相对距离比较上犯错。
- 这类题可以作为稳定的中等难度 L2 子类。

### ADVTEST-L2 viewpoint_transfer

- 严格版 48.3%，v7 81.9%，显著上升。这里不是 bug，而是任务口径变严格了：v7 要求从目标朝向为 0° 的坐标系里，在 `front/front left/front right/back left/back right/back` 六类中选最精确方向。
- 从错题分布看，模型大量偏向选 `back`，说明它不是不知道选项，而是没有稳定完成视角坐标转换。这一项非常适合作为空间推理 hard case，但要在论文中清楚写明方向角度规则。

## 4. L0/L1 v7 分题型错误率

L0/L1 的原始评测结果里 `family` 字段统一是 `unknown`，但 `source_question_id` 保留了结构化题型片段。下面的表就是从 `source_question_id` 中解析出的题型，例如 `scene-0003_frame0:l1:direction_reverse:car14:barrier2` 归为 `l1:direction_reverse`。

### ADVTEST-L0

| 类型 | Q | 错题率 | 为什么看它 |
|---|---:|---:|---|
| `l0:status_yes`（高错） | 111 | 92.8% | 状态肯定式 yes/no；当前 v7 错误率异常高，需优先人工复核题干/GT/图像。 |
| `l0:count_type`（高错） | 110 | 58.2% | 按类别计数，主要考察能否数清同类对象。 |
| `l0:status`（高错） | 99 | 48.5% | 询问具体对象运动状态。 |
| `l0:status_no`（低错） | 96 | 0.0% | 状态否定式 yes/no。 |
| `l0:type`（低错） | 91 | 2.2% | 询问具体对象类别。 |
| `l0:type_yes`（低错） | 105 | 7.6% | 类别肯定式 yes/no。 |

### ADVTEST-L1

| 类型 | Q | 错题率 | 为什么看它 |
|---|---:|---:|---|
| `l1:relation_yes`（高错） | 108 | 100.0% | 关系肯定式 yes/no；当前错误率极高，需优先检查是否存在 yes/no 选项或 GT 方向口径问题。 |
| `l1:exists_status_direction_type`（高错） | 97 | 94.8% | 某方向是否存在某类且某状态对象。 |
| `l1:exists_direction_type`（高错） | 110 | 81.8% | 某方向是否存在某类对象。 |
| `l1:exists_direction_type_no`（低错） | 79 | 2.5% | 方向存在题的否定式。 |
| `l1:relation_no`（低错） | 104 | 20.2% | 关系否定式 yes/no。 |
| `l1:object_at`（低错） | 96 | 36.5% | 具体对象是否位于某方向。 |

完整 L0/L1 明细不放正文铺开。当前最需要人工复核的是高错项：`l0:status_yes`、`l1:relation_yes`、`l1:exists_status_direction_type`；它们可能混有模型错误、题干口径问题和 GT/自动判分问题。

## 5. v7 错题 case

下面只放 v7 错题。每个 case 都按当前选择题版口径展示：题干、选项、GT、模型输出、two-call think 和图像路径。

说明：`Think` 不是模型内部推理，而是第二次固定其选择后，让模型补充的一句视觉依据；它用于解释错因，不进入正式指标。

### Case L0-1：数量题仍然容易错（样例 a）

```text
Method: advtest_l0_choice
Family: l0:count_type
Scene: scene-0003_frame9
Question: How many pedestrians are visible?

A. 11
B. 9
C. 8
D. 7

GT: B. 9
Pred: A
Think Pred: A. 11
Think: The image shows a car driving down a street with 11 pedestrians visible.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame9_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，但对视觉模型和人类都偏费眼：需要先识别目标类别/状态，再在指定范围内计数。
- 错误位置：模型把数量答成 `A`，重问后为 `A. 11`；这不是同义词判分问题，而是没有数清对象数量。
- 事后解释怎么看：事后解释能给出一个数量判断，但通常只是复述最终数值，没有展示逐个目标的可核验计数过程。
- 这个 case 说明什么：这类题不是同义词问题，而是需要模型数清同一类对象数量；v7 给了选项后仍会错。 本题的事后解释是 `The image shows a car driving down a street with 11 pedestrians visible.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The image shows a car driving down a street with 11 pedestrians visible.

### Case L0-1：数量题仍然容易错（样例 b）

```text
Method: advtest_l0_choice
Family: l0:count_type
Scene: scene-0003_frame10
Question: How many pedestrians are visible?

A. 6
B. 7
C. 5
D. 8

GT: B. 7
Pred: C
Think Pred: A. 6
Think: The image shows a car driving down a street with 6 pedestrians visible.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame10_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，但对视觉模型和人类都偏费眼：需要先识别目标类别/状态，再在指定范围内计数。
- 错误位置：模型把数量答成 `C`，重问后为 `A. 6`；这不是同义词判分问题，而是没有数清对象数量。
- 事后解释怎么看：事后解释能给出一个数量判断，但通常只是复述最终数值，没有展示逐个目标的可核验计数过程。
- 这个 case 说明什么：这类题不是同义词问题，而是需要模型数清同一类对象数量；v7 给了选项后仍会错。 本题的事后解释是 `The image shows a car driving down a street with 6 pedestrians visible.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The image shows a car driving down a street with 6 pedestrians visible.

### Case L0-1：数量题仍然容易错（样例 c）

```text
Method: advtest_l0_choice
Family: l0:count_type
Scene: scene-0003_frame16
Question: How many pedestrians are visible?

A. 6
B. 8
C. 5
D. 9

GT: A. 6
Pred: C
Think Pred: A. 6
Think: The image shows a car driving down a street with 6 pedestrians visible.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame16_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，但对视觉模型和人类都偏费眼：需要先识别目标类别/状态，再在指定范围内计数。
- 错误位置：模型把数量答成 `C`，重问后为 `A. 6`；这不是同义词判分问题，而是没有数清对象数量。
- 事后解释怎么看：事后解释能给出一个数量判断，但通常只是复述最终数值，没有展示逐个目标的可核验计数过程。
- 这个 case 说明什么：这类题不是同义词问题，而是需要模型数清同一类对象数量；v7 给了选项后仍会错。 本题的事后解释是 `The image shows a car driving down a street with 6 pedestrians visible.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The image shows a car driving down a street with 6 pedestrians visible.

### Case L0-2：状态/属性题的视觉判断错误（样例 a）

```text
Method: advtest_l0_choice
Family: l0:status_yes
Scene: scene-0003_frame1
Question: Is car10 stopped?

A. yes
B. no

GT: A. yes
Pred: B
Think Pred: A. yes
Think: The car10 is stopped at the intersection.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame1_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留：题干给出了明确对象、选项和标答，适合作为该类错误的代表样例。
- 错误位置：模型在状态判断上与 GT `yes` 不一致，原回答 `B`，重问为 `A. yes`。
- 事后解释怎么看：事后解释直接给出 stopped/moving 之类判断，适合后续人工看图确认状态是否真的可见。
- 这个 case 说明什么：状态题在严格版里有同义词风险，v7 后仍错的 case 更接近真实视觉状态识别失败。 本题的事后解释是 `The car10 is stopped at the intersection.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The car10 is stopped at the intersection.

### Case L0-2：状态/属性题的视觉判断错误（样例 b）

```text
Method: advtest_l0_choice
Family: l0:status
Scene: scene-0003_frame6
Question: What is the movement status of car20?

A. parked
B. moving
C. stopped

GT: C. stopped
Pred: B. moving
Think Pred: B. moving
Think: The car20 is moving in the image.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame6_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留：题干给出了明确对象、选项和标答，适合作为该类错误的代表样例。
- 错误位置：模型在状态判断上与 GT `stopped` 不一致，原回答 `B. moving`，重问为 `B. moving`。
- 事后解释怎么看：事后解释直接给出 stopped/moving 之类判断，适合后续人工看图确认状态是否真的可见。
- 这个 case 说明什么：状态题在严格版里有同义词风险，v7 后仍错的 case 更接近真实视觉状态识别失败。 本题的事后解释是 `The car20 is moving in the image.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The car20 is moving in the image.

### Case L0-2：状态/属性题的视觉判断错误（样例 c）

```text
Method: advtest_l0_choice
Family: l0:status_yes
Scene: scene-0003_frame6
Question: Is barrier4 stopped?

A. yes
B. no

GT: A. yes
Pred: B
Think Pred: A. yes
Think: The car in barrier4 is stopped.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame6_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留：题干给出了明确对象、选项和标答，适合作为该类错误的代表样例。
- 错误位置：模型在状态判断上与 GT `yes` 不一致，原回答 `B`，重问为 `A. yes`。
- 事后解释怎么看：事后解释直接给出 stopped/moving 之类判断，适合后续人工看图确认状态是否真的可见。
- 这个 case 说明什么：状态题在严格版里有同义词风险，v7 后仍错的 case 更接近真实视觉状态识别失败。 本题的事后解释是 `The car in barrier4 is stopped.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The car in barrier4 is stopped.

### Case L1-1：方向关系选错（样例 a）

```text
Method: advtest_l1_choice
Family: l1:direction_reverse
Scene: scene-0003_frame0
Question: Where is barrier2 relative to car14?

A. front left (30° < theta <= 90°)
B. back left (90° < theta <= 150°)
C. front (-30° < theta <= 30°)
D. front right (-90° < theta <= -30°)

GT: D. front right (-90° < theta <= -30°)
Pred: C. front (-30° < theta <= 30°)
Think Pred: A. front left (30° < theta <= 90°)
Think: The barrier is located to the left of the car14.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame0_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，关键在方向坐标系：题干和选项已经给出角度规则，错误更能反映空间方向理解问题。
- 错误位置：模型选了 `C. front (-30° < theta <= 30°)`，但 GT 是 `front right (-90° < theta <= -30°)`；重问后 `A. front left (30° < theta <= 90°)`，仍然没有稳定落到正确角度区间。
- 事后解释怎么看：事后解释通常只说 left/back/front 这样的粗方向，没有按 NuScenes-QA 角度表做精确分类。
- 这个 case 说明什么：题干已经要求相对方向，v7 也给了角度标准；仍错说明模型的相对方位判断不稳。 本题的事后解释是 `The barrier is located to the left of the car14.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The barrier is located to the left of the car14.

### Case L1-1：方向关系选错（样例 b）

```text
Method: advtest_l1_choice
Family: l1:direction
Scene: scene-0003_frame1
Question: Where is car25 relative to barrier1?

A. back (otherwise)
B. front left (30° < theta <= 90°)
C. back left (90° < theta <= 150°)
D. front (-30° < theta <= 30°)

GT: C. back left (90° < theta <= 150°)
Pred: A. back (otherwise)
Think Pred: A. back (otherwise)
Think: The car25 is located behind the barrier1.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame1_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，关键在方向坐标系：题干和选项已经给出角度规则，错误更能反映空间方向理解问题。
- 错误位置：模型选了 `A. back (otherwise)`，但 GT 是 `back left (90° < theta <= 150°)`；重问后 `A. back (otherwise)`，仍然没有稳定落到正确角度区间。
- 事后解释怎么看：事后解释通常只说 left/back/front 这样的粗方向，没有按 NuScenes-QA 角度表做精确分类。
- 这个 case 说明什么：题干已经要求相对方向，v7 也给了角度标准；仍错说明模型的相对方位判断不稳。 本题的事后解释是 `The car25 is located behind the barrier1.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The car25 is located behind the barrier1.

### Case L1-1：方向关系选错（样例 c）

```text
Method: advtest_l1_choice
Family: l1:direction_reverse
Scene: scene-0003_frame1
Question: Where is car21 relative to car23?

A. back (otherwise)
B. back left (90° < theta <= 150°)
C. front left (30° < theta <= 90°)
D. left (around +90°)

GT: C. front left (30° < theta <= 90°)
Pred: A. back (otherwise)
Think Pred: A. back (otherwise)
Think: A car is parked in front of a building.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame1_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，关键在方向坐标系：题干和选项已经给出角度规则，错误更能反映空间方向理解问题。
- 错误位置：模型选了 `A. back (otherwise)`，但 GT 是 `front left (30° < theta <= 90°)`；重问后 `A. back (otherwise)`，仍然没有稳定落到正确角度区间。
- 事后解释怎么看：事后解释通常只说 left/back/front 这样的粗方向，没有按 NuScenes-QA 角度表做精确分类。
- 这个 case 说明什么：题干已经要求相对方向，v7 也给了角度标准；仍错说明模型的相对方位判断不稳。 本题的事后解释是 `A car is parked in front of a building.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：A car is parked in front of a building.

### Case L1-2：带方向约束的计数题（样例 a）

```text
Method: advtest_l1_choice
Family: l1:count_status_direction_type
Scene: scene-0003_frame2
Question: How many stopped cars are to the back (otherwise) of car14?

A. 3
B. 4
C. 6
D. 2

GT: B. 4
Pred: A. 3
Think Pred: A. 3
Think: A car is parked behind car14.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame2_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，但对视觉模型和人类都偏费眼：需要先识别目标类别/状态，再在指定范围内计数。
- 错误位置：模型在带方向约束的计数上答成 `A. 3`，重问后 `A. 3`；错因是方向筛选和计数叠加失败。
- 事后解释怎么看：事后解释一般只抓到一个局部线索，例如某对象在后方，但没有说明完整计数过程。
- 这个 case 说明什么：这类题同时要求识别类别、判断方位、再计数，比单纯 yes/no 难很多。 本题的事后解释是 `A car is parked behind car14.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：A car is parked behind car14.

### Case L1-2：带方向约束的计数题（样例 b）

```text
Method: advtest_l1_choice
Family: l1:count_direction_type
Scene: scene-0003_frame7
Question: How many pedestrians are to the back right (-150° < theta <= -90°) of barrier2?

A. 1
B. 0
C. 2
D. 3

GT: A. 1
Pred: C. 2
Think Pred: C. 2
Think: The pedestrians are to the back right of barrier2.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame7_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，但对视觉模型和人类都偏费眼：需要先识别目标类别/状态，再在指定范围内计数。
- 错误位置：模型在带方向约束的计数上答成 `C. 2`，重问后 `C. 2`；错因是方向筛选和计数叠加失败。
- 事后解释怎么看：事后解释一般只抓到一个局部线索，例如某对象在后方，但没有说明完整计数过程。
- 这个 case 说明什么：这类题同时要求识别类别、判断方位、再计数，比单纯 yes/no 难很多。 本题的事后解释是 `The pedestrians are to the back right of barrier2.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The pedestrians are to the back right of barrier2.

### Case L1-2：带方向约束的计数题（样例 c）

```text
Method: advtest_l1_choice
Family: l1:count_direction_type
Scene: scene-0003_frame9
Question: How many pedestrians are to the front left (30° < theta <= 90°) of barrier1?

A. 5
B. 2
C. 1
D. 3

GT: D. 3
Pred: B. 2
Think Pred: B. 2
Think: The pedestrian is standing in front of the barrier.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame9_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，但对视觉模型和人类都偏费眼：需要先识别目标类别/状态，再在指定范围内计数。
- 错误位置：模型在带方向约束的计数上答成 `B. 2`，重问后 `B. 2`；错因是方向筛选和计数叠加失败。
- 事后解释怎么看：事后解释一般只抓到一个局部线索，例如某对象在后方，但没有说明完整计数过程。
- 这个 case 说明什么：这类题同时要求识别类别、判断方位、再计数，比单纯 yes/no 难很多。 本题的事后解释是 `The pedestrian is standing in front of the barrier.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The pedestrian is standing in front of the barrier.

### Case L2-1：converge 多约束定位误选同类目标（样例 a）

```text
Method: advtest_l2_converge_choice
Family: converge
Scene: scene-0003_frame33
Question: There is a barrier to the back (otherwise) of car20 and to the front (-30° < theta <= 30°) of pedestrian11, and to the front left (30° < theta <= 90°) of barrier4, and to the back (otherwise) of pedestrian1; what is it?

A. barrier10
B. barrier7
C. barrier3
D. barrier9

GT: B. barrier7
Pred: C. barrier3
Think Pred: C. barrier3
Think: The barrier is in front of pedestrian1 and to the back of car20.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0003_frame33_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，是典型 hard case：多个关系约束共同确定唯一目标，人类也需要逐条排除候选。
- 错误位置：模型选中 `C. barrier3` 而不是 `barrier7`，重问后 `C. barrier3`；说明它被同类候选或局部关系误导。
- 事后解释怎么看：事后解释往往只覆盖部分约束，或者复述题干中的一两条关系，不能证明它完成了所有约束交汇。
- 这个 case 说明什么：converge 的核心价值在这里：选项都是可混淆同类对象，模型必须同时满足多个关系约束。 本题的事后解释是 `The barrier is in front of pedestrian1 and to the back of car20.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The barrier is in front of pedestrian1 and to the back of car20.

### Case L2-1：converge 多约束定位误选同类目标（样例 b）

```text
Method: advtest_l2_converge_choice
Family: converge
Scene: scene-0016_frame17
Question: What pedestrian is positioned to the front left (30° < theta <= 90°) of pedestrian14 and also to the front left (30° < theta <= 90°) of pedestrian20, and to the back left (90° < theta <= 150°) of pedestrian8?

A. pedestrian3
B. pedestrian24
C. pedestrian1
D. pedestrian12

GT: D. pedestrian12
Pred: A. pedestrian3
Think Pred: A. pedestrian3
Think: A pedestrian is positioned to the front left of pedestrian14 and pedestrian20, and to the back left of pedestrian8.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0016_frame17_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，是典型 hard case：多个关系约束共同确定唯一目标，人类也需要逐条排除候选。
- 错误位置：模型选中 `A. pedestrian3` 而不是 `pedestrian12`，重问后 `A. pedestrian3`；说明它被同类候选或局部关系误导。
- 事后解释怎么看：事后解释往往只覆盖部分约束，或者复述题干中的一两条关系，不能证明它完成了所有约束交汇。
- 这个 case 说明什么：converge 的核心价值在这里：选项都是可混淆同类对象，模型必须同时满足多个关系约束。 本题的事后解释是 `A pedestrian is positioned to the front left of pedestrian14 and pedestrian20, and to the back left of pedestrian8.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：A pedestrian is positioned to the front left of pedestrian14 and pedestrian20, and to the back left of pedestrian8.

### Case L2-1：converge 多约束定位误选同类目标（样例 c）

```text
Method: advtest_l2_converge_choice
Family: converge
Scene: scene-0017_frame24
Question: Which barrier can be found to the back (otherwise) of barrier11 and to the back (otherwise) of barrier30, and to the back right (-150° < theta <= -90°) of ego, and to the front (-30° < theta <= 30°) of barrier27, and to the back (otherwise) of barrier19?

A. barrier20
B. barrier14
C. barrier29
D. barrier16

GT: C. barrier29
Pred: B. barrier14
Think Pred: B. barrier14
Think: Barrier14 is the barrier that can be found to the back (otherwise) of barrier11 and to the back (otherwise) of barrier30, and to the back right (-150° < the
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0017_frame24_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，是典型 hard case：多个关系约束共同确定唯一目标，人类也需要逐条排除候选。
- 错误位置：模型选中 `B. barrier14` 而不是 `barrier29`，重问后 `B. barrier14`；说明它被同类候选或局部关系误导。
- 事后解释怎么看：事后解释往往只覆盖部分约束，或者复述题干中的一两条关系，不能证明它完成了所有约束交汇。
- 这个 case 说明什么：converge 的核心价值在这里：选项都是可混淆同类对象，模型必须同时满足多个关系约束。 本题的事后解释是 `Barrier14 is the barrier that can be found to the back (otherwise) of barrier11 and to the back (otherwise) of barrier30, and to the back right (-150° < the`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：Barrier14 is the barrier that can be found to the back (otherwise) of barrier11 and to the back (otherwise) of barrier30, and to the back right (-150° < the

### Case L2-2：direction_chain 二值选择仍有少量错（样例 a）

```text
Method: advtest_l2_direction_chain_choice
Family: direction_chain
Scene: scene-0015_frame19
Question: Does car8 lie in the same direction from truck1 as car1?

A. no
B. yes

GT: A. no
Pred: B
Think Pred: A. no
Think: The car8 is in the opposite direction from truck1.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0015_frame19_mosaic.jpg
```

人工分析：
- 题目有效性：题目可以作为关系链样例，但不宜作为最强 hard case：选项化后模型容易被 yes/no 格式纠正。
- 错误位置：原回答 `B` 与 GT `no` 不一致，重问后 `A. no`；这一类容易被二次选择题格式纠正。
- 事后解释怎么看：事后解释很泛化，通常没有真正解释关系链，因此这类 case 的 reason 证据弱。
- 这个 case 说明什么：虽然 v7 后错误率大幅下降，但剩下的错题说明关系链判断并非完全 trivial。 本题的事后解释是 `The car8 is in the opposite direction from truck1.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The car8 is in the opposite direction from truck1.

### Case L2-2：direction_chain 二值选择仍有少量错（样例 b）

```text
Method: advtest_l2_direction_chain_choice
Family: direction_chain
Scene: scene-0016_frame19
Question: Is pedestrian16 in the same direction from pedestrian10 as pedestrian10 is from pedestrian15?

A. yes
B. no

GT: A. yes
Pred: B. no
Think Pred: A. yes
Think: The pedestrians are in the same direction from pedestrian10 as pedestrian10 is from pedestrian15.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0016_frame19_mosaic.jpg
```

人工分析：
- 题目有效性：题目可以作为关系链样例，但不宜作为最强 hard case：选项化后模型容易被 yes/no 格式纠正。
- 错误位置：原回答 `B. no` 与 GT `yes` 不一致，重问后 `A. yes`；这一类容易被二次选择题格式纠正。
- 事后解释怎么看：事后解释很泛化，通常没有真正解释关系链，因此这类 case 的 reason 证据弱。
- 这个 case 说明什么：虽然 v7 后错误率大幅下降，但剩下的错题说明关系链判断并非完全 trivial。 本题的事后解释是 `The pedestrians are in the same direction from pedestrian10 as pedestrian10 is from pedestrian15.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The pedestrians are in the same direction from pedestrian10 as pedestrian10 is from pedestrian15.

### Case L2-2：direction_chain 二值选择仍有少量错（样例 c）

```text
Method: advtest_l2_direction_chain_choice
Family: direction_chain
Scene: scene-0015_frame17
Question: Does ego lie in the same direction from bicycle1 as car2?

A. yes
B. no

GT: A. yes
Pred: B
Think Pred: A. yes
Think: The bus is in the same direction as the car.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0015_frame17_mosaic.jpg
```

人工分析：
- 题目有效性：题目可以作为关系链样例，但不宜作为最强 hard case：选项化后模型容易被 yes/no 格式纠正。
- 错误位置：原回答 `B` 与 GT `yes` 不一致，重问后 `A. yes`；这一类容易被二次选择题格式纠正。
- 事后解释怎么看：事后解释很泛化，通常没有真正解释关系链，因此这类 case 的 reason 证据弱。
- 这个 case 说明什么：虽然 v7 后错误率大幅下降，但剩下的错题说明关系链判断并非完全 trivial。 本题的事后解释是 `The bus is in the same direction as the car.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The bus is in the same direction as the car.

### Case L2-3：distance_chain 距离比较错误（样例 a）

```text
Method: advtest_l2_distance_chain_choice
Family: distance_chain
Scene: scene-0003_frame31
Question: Which object is barrier1 nearer to, car19 or car20?

A. car19
B. car20

GT: B. car20
Pred: A
Think Pred: A. car19
Think: The barrier1 is nearer to car19.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0003_frame31_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，主要考察相对距离比较；选项化不会明显降低难度。
- 错误位置：模型在二选一距离比较中选了 `A`，GT 是 `car20`，重问后 `A. car19`。
- 事后解释怎么看：事后解释没有进行距离比较，常常只是描述一个对象在场景中，说明它没有给出可靠距离依据。
- 这个 case 说明什么：distance_chain 在两版之间错误率几乎不变，这类错更可能是真正的距离关系理解问题。 本题的事后解释是 `The barrier1 is nearer to car19.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The barrier1 is nearer to car19.

### Case L2-3：distance_chain 距离比较错误（样例 b）

```text
Method: advtest_l2_distance_chain_choice
Family: distance_chain
Scene: scene-0016_frame28
Question: Between car1 and car3, which one is closer to pedestrian2?

A. car1
B. car3

GT: B. car3
Pred: A
Think Pred: A. car1
Think: A. car1 is closer to pedestrian2.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0016_frame28_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，主要考察相对距离比较；选项化不会明显降低难度。
- 错误位置：模型在二选一距离比较中选了 `A`，GT 是 `car3`，重问后 `A. car1`。
- 事后解释怎么看：事后解释没有进行距离比较，常常只是描述一个对象在场景中，说明它没有给出可靠距离依据。
- 这个 case 说明什么：distance_chain 在两版之间错误率几乎不变，这类错更可能是真正的距离关系理解问题。 本题的事后解释是 `A. car1 is closer to pedestrian2.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：A. car1 is closer to pedestrian2.

### Case L2-3：distance_chain 距离比较错误（样例 c）

```text
Method: advtest_l2_distance_chain_choice
Family: distance_chain
Scene: scene-0015_frame24
Question: Which object is ego nearer to, bicycle1 or bus1?

A. bicycle1
B. bus1

GT: A. bicycle1
Pred: B
Think Pred: B. bus1
Think: The bus is closer to the camera than the bicycle.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0015_frame24_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，主要考察相对距离比较；选项化不会明显降低难度。
- 错误位置：模型在二选一距离比较中选了 `B`，GT 是 `bicycle1`，重问后 `B. bus1`。
- 事后解释怎么看：事后解释没有进行距离比较，常常只是描述一个对象在场景中，说明它没有给出可靠距离依据。
- 这个 case 说明什么：distance_chain 在两版之间错误率几乎不变，这类错更可能是真正的距离关系理解问题。 本题的事后解释是 `The bus is closer to the camera than the bicycle.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The bus is closer to the camera than the bicycle.

### Case L2-4：viewpoint_transfer 过度选择 back（样例 a）

```text
Method: advtest_l2_viewpoint_transfer_choice
Family: viewpoint_transfer
Scene: scene-0003_frame10
Question: From barrier8, facing pedestrian5, where is car23 relative to you?

A. front right (-90° < theta <= -30°)
B. back left (90° < theta <= 150°)
C. back (otherwise)
D. back right (-150° < theta <= -90°)

GT: A. front right (-90° < theta <= -30°)
Pred: C. back (otherwise)
Think Pred: C. back (otherwise)
Think: The car23 is located behind the pedestrian5.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0003_frame10_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，关键在方向坐标系：题干和选项已经给出角度规则，错误更能反映空间方向理解问题。
- 错误位置：模型把 GT `front right (-90° < theta <= -30°)` 误选成 `C. back (otherwise)`，重问后 `C. back (otherwise)`；这是目标朝向坐标系转换失败。
- 事后解释怎么看：事后解释直接暴露了错因：它按粗略的 behind/left 去判断，没有转换到题目指定的观察者朝向。
- 这个 case 说明什么：v7 把角度规则说清后，模型仍大量选 back，说明它对目标朝向坐标系的转换能力弱。 本题的事后解释是 `The car23 is located behind the pedestrian5.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The car23 is located behind the pedestrian5.

### Case L2-4：viewpoint_transfer 过度选择 back（样例 b）

```text
Method: advtest_l2_viewpoint_transfer_choice
Family: viewpoint_transfer
Scene: scene-0017_frame15
Question: From barrier1, facing truck2, where is pedestrian35 relative to you?

A. front left (30° < theta <= 90°)
B. back left (90° < theta <= 150°)
C. back (otherwise)
D. front right (-90° < theta <= -30°)

GT: D. front right (-90° < theta <= -30°)
Pred: C. back
Think Pred: C. back (otherwise)
Think: The pedestrian is located behind the barrier and truck.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0017_frame15_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，关键在方向坐标系：题干和选项已经给出角度规则，错误更能反映空间方向理解问题。
- 错误位置：模型把 GT `front right (-90° < theta <= -30°)` 误选成 `C. back`，重问后 `C. back (otherwise)`；这是目标朝向坐标系转换失败。
- 事后解释怎么看：事后解释直接暴露了错因：它按粗略的 behind/left 去判断，没有转换到题目指定的观察者朝向。
- 这个 case 说明什么：v7 把角度规则说清后，模型仍大量选 back，说明它对目标朝向坐标系的转换能力弱。 本题的事后解释是 `The pedestrian is located behind the barrier and truck.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The pedestrian is located behind the barrier and truck.

### Case L2-4：viewpoint_transfer 过度选择 back（样例 c）

```text
Method: advtest_l2_viewpoint_transfer_choice
Family: viewpoint_transfer
Scene: scene-0003_frame10
Question: From barrier2, facing ego, where is barrier4 relative to you?

A. back left (90° < theta <= 150°)
B. back (otherwise)
C. front (-30° < theta <= 30°)
D. front left (30° < theta <= 90°)

GT: D. front left (30° < theta <= 90°)
Pred: B. back (otherwise)
Think Pred: B. back (otherwise)
Think: The car is parked in front of the barrier.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0003_frame10_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，关键在方向坐标系：题干和选项已经给出角度规则，错误更能反映空间方向理解问题。
- 错误位置：模型把 GT `front left (30° < theta <= 90°)` 误选成 `B. back (otherwise)`，重问后 `B. back (otherwise)`；这是目标朝向坐标系转换失败。
- 事后解释怎么看：事后解释直接暴露了错因：它按粗略的 behind/left 去判断，没有转换到题目指定的观察者朝向。
- 这个 case 说明什么：v7 把角度规则说清后，模型仍大量选 back，说明它对目标朝向坐标系的转换能力弱。 本题的事后解释是 `The car is parked in front of the barrier.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The car is parked in front of the barrier.

### Case L2-5：viewpoint_transfer 前后/左右混淆（样例 a）

```text
Method: advtest_l2_viewpoint_transfer_choice
Family: viewpoint_transfer
Scene: scene-0003_frame3
Question: From car21, facing pedestrian8, where is pedestrian9 relative to you?

A. front (-30° < theta <= 30°)
B. back left (90° < theta <= 150°)
C. front left (30° < theta <= 90°)
D. front right (-90° < theta <= -30°)

GT: D. front right (-90° < theta <= -30°)
Pred: C. front left (30° < theta <= 90°)
Think Pred: C. front left (30° < theta <= 90°)
Think: The pedestrian is located to the left of the car21.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0003_frame3_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，关键在方向坐标系：题干和选项已经给出角度规则，错误更能反映空间方向理解问题。
- 错误位置：模型把 GT `front right (-90° < theta <= -30°)` 误选成 `C. front left (30° < theta <= 90°)`，重问后 `C. front left (30° < theta <= 90°)`；这是目标朝向坐标系转换失败。
- 事后解释怎么看：事后解释直接暴露了错因：它按粗略的 behind/left 去判断，没有转换到题目指定的观察者朝向。
- 这个 case 说明什么：这类错不是答案格式问题，而是在六方向角度标准下选到了相反或邻近方向。 本题的事后解释是 `The pedestrian is located to the left of the car21.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：The pedestrian is located to the left of the car21.

### Case L2-5：viewpoint_transfer 前后/左右混淆（样例 b）

```text
Method: advtest_l2_viewpoint_transfer_choice
Family: viewpoint_transfer
Scene: scene-0016_frame18
Question: From pedestrian15, facing pedestrian8, where is pedestrian19 relative to you?

A. front left (30° < theta <= 90°)
B. back right (-150° < theta <= -90°)
C. front right (-90° < theta <= -30°)
D. back left (90° < theta <= 150°)

GT: C. front right (-90° < theta <= -30°)
Pred: A. front left (30° < theta <= 90°)
Think Pred: A. front left (30° < theta <= 90°)
Think: A. front left (30° < theta <= 90°)
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0016_frame18_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，关键在方向坐标系：题干和选项已经给出角度规则，错误更能反映空间方向理解问题。
- 错误位置：模型把 GT `front right (-90° < theta <= -30°)` 误选成 `A. front left (30° < theta <= 90°)`，重问后 `A. front left (30° < theta <= 90°)`；这是目标朝向坐标系转换失败。
- 事后解释怎么看：事后解释直接暴露了错因：它按粗略的 behind/left 去判断，没有转换到题目指定的观察者朝向。
- 这个 case 说明什么：这类错不是答案格式问题，而是在六方向角度标准下选到了相反或邻近方向。 本题的事后解释是 `A. front left (30° < theta <= 90°)`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：A. front left (30° < theta <= 90°)

### Case L2-5：viewpoint_transfer 前后/左右混淆（样例 c）

```text
Method: advtest_l2_viewpoint_transfer_choice
Family: viewpoint_transfer
Scene: scene-0016_frame25
Question: From car1, facing pedestrian8, where is pedestrian4 relative to you?

A. front left (30° < theta <= 90°)
B. back right (-150° < theta <= -90°)
C. front right (-90° < theta <= -30°)
D. front (-30° < theta <= 30°)

GT: A. front left (30° < theta <= 90°)
Pred: C. front right (-90° < theta <= -30°)
Think Pred: A. front left (30° < theta <= 90°)
Think: A car is driving down the street and is facing pedestrian8. Pedestrian4 is located to the left of the car.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0016_frame25_mosaic.jpg
```

人工分析：
- 题目有效性：题目本身可保留，关键在方向坐标系：题干和选项已经给出角度规则，错误更能反映空间方向理解问题。
- 错误位置：模型把 GT `front left (30° < theta <= 90°)` 误选成 `C. front right (-90° < theta <= -30°)`，重问后 `A. front left (30° < theta <= 90°)`；这是目标朝向坐标系转换失败。
- 事后解释怎么看：事后解释直接暴露了错因：它按粗略的 behind/left 去判断，没有转换到题目指定的观察者朝向。
- 这个 case 说明什么：这类错不是答案格式问题，而是在六方向角度标准下选到了相反或邻近方向。 本题的事后解释是 `A car is driving down the street and is facing pedestrian8. Pedestrian4 is located to the left of the car.`，它可以帮助判断模型抓住了哪条线索，但不能当作内部推理链。

模型事后解释（二次询问得到的视觉依据）：A car is driving down the street and is facing pedestrian8. Pedestrian4 is located to the left of the car.

## 6. 当前结论

1. v7 让 L0 和部分 L2 的判分更公平，尤其减少了自由回答带来的同义词、格式和精确 ID 生成损失。
2. v7 没有把所有题都变简单：L1 基本不降，distance_chain 基本不变，viewpoint_transfer 反而显著升高。
3. converge 的错误率从 90.3% 降到 58.7%，但仍是强 hard case；它的价值不在开放生成 ID，而在同类候选中的多约束定位。
4. viewpoint_transfer 是 v7 最强信号，但汇报时必须明确：方向词按 NuScenes-QA 角度表定义，角度以目标朝向为 0°。
5. 后续人工复核优先看三类：L0/L1 是否仍有判分别名问题、converge 是否存在过长或歧义题干、viewpoint_transfer 的 GT 角度边界是否正确。
