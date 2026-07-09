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

补充：严格版各项均为 1000 题；v7 中 `mixed` 为 955 题、`converge` 为 973 题，因为选择题转换时强制要求同类候选、唯一正确项、无重复选项，转换不出的题没有纳入正式判分。

## 2. 同一题目上的变化

这一节只列同一题目在两版之间的转移数字；原因统一放到第 3 节解释。

| 数据项 | 可对齐题数 | 严格错→v7对 | 严格对→v7错 | 两版都错 | 两版都对 |
|---|---:|---:|---:|---:|---:|
| ADVTEST-L0 | 1000 | 292 | 202 | 160 | 346 |
| ADVTEST-L1 | 1000 | 331 | 252 | 309 | 108 |
| ADVTEST-L2 mixed | 955 | 361 | 16 | 541 | 37 |
| ADVTEST-L2 converge | 973 | 362 | 30 | 541 | 40 |
| ADVTEST-L2 direction_chain | 1000 | 816 | 98 | 22 | 64 |
| ADVTEST-L2 distance_chain | 1000 | 225 | 209 | 304 | 262 |
| ADVTEST-L2 viewpoint_transfer | 1000 | 113 | 449 | 370 | 68 |

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

下面只放 v7 错题。每个 case 只展示题目、标准答案、模型答案、Think 原文和图像路径。

说明：`Think` 是让模型带理由作答时的第一次原始输出；如果它只写理由、没写答案，报告也按原样保留。

### Case L0-1：数量题，Think 没有真正计数

```text
Scene: scene-0003_frame9
Question: How many pedestrians are visible?

A. 11
B. 9
C. 8
D. 7

GT: B. 9
Answer: C. 8
Think: The image shows a car driving down a street.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame9_mosaic.jpg
```

人工分析：
标准答案是 `9`，模型答 `C. 8`，这次选错了。Think 没有真正数目标，只是在泛泛描述场景，所以答案偏成 `C. 8`。

### Case L0-2：状态题，目标状态看错

```text
Scene: scene-0003_frame6
Question: What is the movement status of car20?

A. parked
B. moving
C. stopped

GT: C. stopped
Answer: B. moving
Think: The car is driving down the street.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame6_mosaic.jpg
```

人工分析：
标准答案是 `stopped`，模型答 `B. moving`，这次选错了。Think 没有说清目标状态，说明它没有抓住题目真正问的属性。

### Case L1-1：方向题，只做粗方向判断

```text
Scene: scene-0003_frame0
Question: Where is barrier2 relative to car14?

A. front left (30° < theta <= 90°)
B. back left (90° < theta <= 150°)
C. front (-30° < theta <= 30°)
D. front right (-90° < theta <= -30°)

GT: D. front right (-90° < theta <= -30°)
Answer: A. front left
Think: The barrier is in front of the car.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame0_mosaic.jpg
```

人工分析：
标准答案是 `front right (-90° < theta <= -30°)`，模型答 `A. front left`，这次选错了。Think 只给了粗方向关系 `The barrier is in front of the car.`，没有按六类角度区间判断，所以选到了 `A. front left`。

### Case L1-2：方向约束计数，只抓局部线索

```text
Scene: scene-0003_frame2
Question: How many stopped cars are to the back (otherwise) of car14?

A. 3
B. 4
C. 6
D. 2

GT: B. 4
Answer: D. 2
Think: The car14 is stopped in the middle of the road.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame2_mosaic.jpg
```

人工分析：
标准答案是 `4`，模型答 `D. 2`，这次选错了。Think 只抓到一个局部线索 `The car14 is stopped in the middle of the road.`，没有完成“方向筛选后再计数”，所以数量选错。

### Case L2-1：converge，只验证部分约束

```text
Scene: scene-0003_frame33
Question: There is a barrier to the back (otherwise) of car20 and to the front (-30° < theta <= 30°) of pedestrian11, and to the front left (30° < theta <= 90°) of barrier4, and to the back (otherwise) of pedestrian1; what is it?

A. barrier10
B. barrier7
C. barrier3
D. barrier9

GT: B. barrier7
Answer: C. barrier3
Think: The barrier is in the back of car20 and in front of pedestrian11.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0003_frame33_mosaic.jpg
```

人工分析：
标准答案是 `barrier7`，模型答 `C. barrier3`，这次选错了。Think 只验证了部分关系 `The barrier is in the back of car20 and in front of pedestrian11.`，没有把题干里的多条约束同时交汇到唯一目标。

### Case L2-2：direction_chain，退化成普通场景描述

```text
Scene: scene-0015_frame19
Question: Does car8 lie in the same direction from truck1 as car1?

A. no
B. yes

GT: A. no
Answer: B. yes
Think: The cars are lined up in a row.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0015_frame19_mosaic.jpg
```

人工分析：
标准答案是 `no`，模型答 `B. yes`，这次选错了。Think 退化成普通位置描述 `The cars are lined up in a row.`，没有真正完成关系链判断。

### Case L2-3：distance_chain，没有完成距离比较

```text
Scene: scene-0003_frame31
Question: Which object is barrier1 nearer to, car19 or car20?

A. car19
B. car20

GT: B. car20
Answer: A. car19
Think: The image shows a car with the number 19 and another car with the number 20.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0003_frame31_mosaic.jpg
```

人工分析：
标准答案是 `car20`，模型答 `A. car19`，这次选错了。Think 没有比较两个候选距离，只描述了局部对象 `The image shows a car with the number 19 and another car with the number 20.`，所以答案缺少有效依据。

### Case L2-4：viewpoint_transfer，使用图像坐标而非目标朝向坐标

```text
Scene: scene-0003_frame10
Question: From barrier8, facing pedestrian5, where is car23 relative to you?

A. front right (-90° < theta <= -30°)
B. back left (90° < theta <= 150°)
C. back (otherwise)
D. back right (-150° < theta <= -90°)

GT: A. front right (-90° < theta <= -30°)
Answer: C. back
Think: The car is in the middle of the image.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0003_frame10_mosaic.jpg
```

人工分析：
标准答案是 `front right (-90° < theta <= -30°)`，模型答 `C. back`，这次选错了。Think 使用的是图像画面里的左右/中间 `The car is in the middle of the image.`，没有切换到目标朝向为 0° 的坐标系。

### Case L2-5：viewpoint_transfer，朝向对象被看见但方向转换仍错

```text
Scene: scene-0003_frame3
Question: From car21, facing pedestrian8, where is pedestrian9 relative to you?

A. front (-30° < theta <= 30°)
B. back left (90° < theta <= 150°)
C. front left (30° < theta <= 90°)
D. front right (-90° < theta <= -30°)

GT: D. front right (-90° < theta <= -30°)
Answer: C. front left
Think: The car21 is facing pedestrian8.
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0003_frame3_mosaic.jpg
```

人工分析：
标准答案是 `front right (-90° < theta <= -30°)`，模型答 `C. front left`，这次选错了。Think 给的是普通空间描述 `The car21 is facing pedestrian8.`，没有体现题目要求的视角转换。

## 6. 当前结论

1. v7 让 L0 和部分 L2 的判分更公平，尤其减少了自由回答带来的同义词、格式和精确 ID 生成损失。
2. v7 没有把所有题都变简单：L1 基本不降，distance_chain 基本不变，viewpoint_transfer 反而显著升高。
3. converge 的错误率从 90.3% 降到 58.7%，但仍是强 hard case；它的价值不在开放生成 ID，而在同类候选中的多约束定位。
4. viewpoint_transfer 是 v7 最强信号，但汇报时必须明确：方向词按 NuScenes-QA 角度表定义，角度以目标朝向为 0°。
5. 后续人工复核优先看三类：L0/L1 是否仍有判分别名问题、converge 是否存在过长或歧义题干、viewpoint_transfer 的 GT 角度边界是否正确。
