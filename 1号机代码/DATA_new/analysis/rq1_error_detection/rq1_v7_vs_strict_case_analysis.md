# RQ1 ADVTEST v7 与严格问答版 case 分析

本文只比较两版：

- 严格问答版：模型自由生成答案，按冻结的自动判分结果统计。
- v7 角度精细化选择题版：题目来源保持一致，转成选择题；涉及方向的题，在题干和选项里显式给出 NuScenes-QA 的方向角度标准，角度以目标朝向为 0°。

这里不讨论 v1/v3/v6，也不重算 QATest、QAAskeR；重点是看我们的题在“自由回答”和“选项明确化”之后，错误率变化是否合理。

## 1. 总体对比

| 数据项 | 严格版 Q | 严格版错题 | 严格版错误率 | v7 Q | v7 错题 | v7 错误率 | 变化 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| ADVTEST-L0 | 1000 | 452 | 45.2% | 1000 | 362 | 36.2% | -9.0 pp | 下降，主要是类型/状态/数量题不再被同义词和表达格式额外惩罚。 |
| ADVTEST-L1 | 1000 | 640 | 64.0% | 1000 | 561 | 56.1% | -7.9 pp | 小幅下降，但方向关系和计数关系仍然难，说明不是纯判分格式问题。 |
| ADVTEST-L2 mixed | 1000 | 902 | 90.2% | 955 | 557 | 58.3% | -31.9 pp | 大幅下降；mixed 仍几乎由 converge 支配，v7 去掉了自由回答的 ID/格式损失。 |
| ADVTEST-L2 converge | 1000 | 903 | 90.3% | 973 | 571 | 58.7% | -31.6 pp | 大幅下降但仍高；同类候选选择后，剩下主要是多约束定位错误。 |
| ADVTEST-L2 direction_chain | 1000 | 838 | 83.8% | 1000 | 120 | 12.0% | -71.8 pp | 大幅下降；二值选择把输出格式问题压低，这类不应单独当最强证据。 |
| ADVTEST-L2 distance_chain | 1000 | 529 | 52.9% | 1000 | 513 | 51.3% | -1.6 pp | 几乎不变；选择题没有明显降低难度，错误更接近真实空间距离判断失败。 |
| ADVTEST-L2 viewpoint_transfer | 1000 | 483 | 48.3% | 1000 | 819 | 81.9% | +33.6 pp | 显著上升；v7 从粗粒度表达变成 6 类角度方向选择，暴露了视角转换能力弱。 |

说明：`mixed` 和 `converge` 的 v7 分母不是 1000，是因为选择题转换时强制要求选项公平，例如同类候选、唯一正确项、无重复选项；转换不出的题没有纳入 v7 正式判分。

## 2. 同一题目上的变化

| 数据项 | 可对齐题数 | 严格错→v7对 | 严格对→v7错 | 两版都错 | 两版都对 | 解释 |
|---|---:|---:|---:|---:|---:|---|
| ADVTEST-L0 | 1000 | 292 | 202 | 160 | 346 | v7 修掉一部分同义词/格式问题，但仍保留大量视觉判断错误。 |
| ADVTEST-L1 | 1000 | 331 | 252 | 309 | 108 | 有改善也有反向变差，说明选项化不是简单降难度；方向关系仍会误选。 |
| ADVTEST-L2 mixed | 955 | 361 | 16 | 541 | 37 | 主要反映 converge 的变化：自由回答时代很容易答不到精确 ID，选项化后仍有大量同类误选。 |
| ADVTEST-L2 converge | 973 | 362 | 30 | 541 | 40 | 很多 strict 错题在 v7 能选对，但双错仍最多，说明多约束定位本身仍难。 |
| ADVTEST-L2 direction_chain | 1000 | 816 | 98 | 22 | 64 | 大批 strict 错题在 v7 变对，说明原严格版里 yes/no 或自然语言判分损失偏大。 |
| ADVTEST-L2 distance_chain | 1000 | 225 | 209 | 304 | 262 | 双错和反向变化都存在，整体几乎不变，比较像真实距离关系难点。 |
| ADVTEST-L2 viewpoint_transfer | 1000 | 113 | 449 | 370 | 68 | 大量 strict 对题在 v7 变错，是因为 v7 要求按 6 类角度规则精确选方向，不再接受粗略 behind/left 叙述。 |

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

| 题型 | Q | 错题 | 错误率 | 说明 |
|---|---:|---:|---:|---|
| `l0:status_yes` | 111 | 103 | 92.8% | 状态肯定式 yes/no；当前 v7 错误率异常高，需优先人工复核题干/GT/图像。 |
| `l0:count_type` | 110 | 64 | 58.2% | 按类别计数，主要考察能否数清同类对象。 |
| `l0:type_no` | 105 | 21 | 20.0% | 类别否定式 yes/no。 |
| `l0:type_yes` | 105 | 8 | 7.6% | 类别肯定式 yes/no。 |
| `l0:exists` | 100 | 40 | 40.0% | 判断具体对象是否存在。 |
| `l0:exists_status_type` | 99 | 44 | 44.4% | 判断某类/某状态对象是否存在，带类型和状态约束。 |
| `l0:status` | 99 | 48 | 48.5% | 询问具体对象运动状态。 |
| `l0:status_no` | 96 | 0 | 0.0% | 状态否定式 yes/no。 |
| `l0:type` | 91 | 2 | 2.2% | 询问具体对象类别。 |
| `l0:more_type` | 84 | 32 | 38.1% | 比较两类对象数量多少。 |

### ADVTEST-L1

| 题型 | Q | 错题 | 错误率 | 说明 |
|---|---:|---:|---:|---|
| `l1:direction` | 111 | 61 | 55.0% | 对象相对方向。 |
| `l1:exists_direction_type` | 110 | 90 | 81.8% | 某方向是否存在某类对象。 |
| `l1:relation_yes` | 108 | 108 | 100.0% | 关系肯定式 yes/no；当前错误率极高，需优先检查是否存在 yes/no 选项或 GT 方向口径问题。 |
| `l1:count_direction_type` | 107 | 51 | 47.7% | 带方向约束的类别计数。 |
| `l1:relation_no` | 104 | 21 | 20.2% | 关系否定式 yes/no。 |
| `l1:exists_status_direction_type` | 97 | 92 | 94.8% | 某方向是否存在某类且某状态对象。 |
| `l1:count_status_direction_type` | 96 | 58 | 60.4% | 带方向、类别、状态约束的计数。 |
| `l1:object_at` | 96 | 35 | 36.5% | 具体对象是否位于某方向。 |
| `l1:direction_reverse` | 92 | 43 | 46.7% | 反向对象相对方向。 |
| `l1:exists_direction_type_no` | 79 | 2 | 2.5% | 方向存在题的否定式。 |

从这张表看，L0/L1 不是均匀难：有些 yes/no 子类很低，有些状态/关系子类异常高。后续人工复核应该优先抽 `l0:status_yes`、`l1:relation_yes`、`l1:exists_status_direction_type` 这类极端项，判断是模型确实错、题干口径问题，还是 GT/自动判分问题。

## 5. v7 错题 case

下面只放 v7 错题。每个 case 都按当前选择题版口径展示：题干、选项、GT、模型输出和图像路径。

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
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame9_mosaic.jpg
```

分析：这类题不是同义词问题，而是需要模型数清同一类对象数量；v7 给了选项后仍会错。

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
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame10_mosaic.jpg
```

分析：这类题不是同义词问题，而是需要模型数清同一类对象数量；v7 给了选项后仍会错。

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
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame1_mosaic.jpg
```

分析：状态题在严格版里有同义词风险，v7 后仍错的 case 更接近真实视觉状态识别失败。

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
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame6_mosaic.jpg
```

分析：状态题在严格版里有同义词风险，v7 后仍错的 case 更接近真实视觉状态识别失败。

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
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame0_mosaic.jpg
```

分析：题干已经要求相对方向，v7 也给了角度标准；仍错说明模型的相对方位判断不稳。

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
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame1_mosaic.jpg
```

分析：题干已经要求相对方向，v7 也给了角度标准；仍错说明模型的相对方位判断不稳。

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
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame2_mosaic.jpg
```

分析：这类题同时要求识别类别、判断方位、再计数，比单纯 yes/no 难很多。

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
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame7_mosaic.jpg
```

分析：这类题同时要求识别类别、判断方位、再计数，比单纯 yes/no 难很多。

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
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0003_frame33_mosaic.jpg
```

分析：converge 的核心价值在这里：选项都是可混淆同类对象，模型必须同时满足多个关系约束。

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
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0016_frame17_mosaic.jpg
```

分析：converge 的核心价值在这里：选项都是可混淆同类对象，模型必须同时满足多个关系约束。

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
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0015_frame19_mosaic.jpg
```

分析：虽然 v7 后错误率大幅下降，但剩下的错题说明关系链判断并非完全 trivial。

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
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0016_frame19_mosaic.jpg
```

分析：虽然 v7 后错误率大幅下降，但剩下的错题说明关系链判断并非完全 trivial。

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
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0003_frame31_mosaic.jpg
```

分析：distance_chain 在两版之间错误率几乎不变，这类错更可能是真正的距离关系理解问题。

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
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0016_frame28_mosaic.jpg
```

分析：distance_chain 在两版之间错误率几乎不变，这类错更可能是真正的距离关系理解问题。

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
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0003_frame10_mosaic.jpg
```

分析：v7 把角度规则说清后，模型仍大量选 back，说明它对目标朝向坐标系的转换能力弱。

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
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0017_frame15_mosaic.jpg
```

分析：v7 把角度规则说清后，模型仍大量选 back，说明它对目标朝向坐标系的转换能力弱。

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
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0003_frame3_mosaic.jpg
```

分析：这类错不是答案格式问题，而是在六方向角度标准下选到了相反或邻近方向。

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
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0016_frame18_mosaic.jpg
```

分析：这类错不是答案格式问题，而是在六方向角度标准下选到了相反或邻近方向。

## 6. 当前结论

1. v7 让 L0 和部分 L2 的判分更公平，尤其减少了自由回答带来的同义词、格式和精确 ID 生成损失。
2. v7 没有把所有题都变简单：L1 基本不降，distance_chain 基本不变，viewpoint_transfer 反而显著升高。
3. converge 的错误率从 90.3% 降到 58.7%，但仍是强 hard case；它的价值不在开放生成 ID，而在同类候选中的多约束定位。
4. viewpoint_transfer 是 v7 最强信号，但汇报时必须明确：方向词按 NuScenes-QA 角度表定义，角度以目标朝向为 0°。
5. 后续人工复核优先看三类：L0/L1 是否仍有判分别名问题、converge 是否存在过长或歧义题干、viewpoint_transfer 的 GT 角度边界是否正确。
