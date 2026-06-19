# RQ1 Case Validity Analysis: L0/L1/L2 Error Cases

## 1. 目的

这份文档整理本轮 RQ1 故障检测实验中，我们对 ADVTEST-L0、ADVTEST-L1、ADVTEST-L2 错例的人工快速检查过程和分析结果。

核心问题不是只看错误率，而是回答：

1. 这些题本身有没有明显问题？
2. 这些题对人类来说是否合理、是否过难？
3. VLM 答错是否正常？
4. 哪些错误是真正的模型失败，哪些是自动判分偏严，哪些是题面/模板需要清理？

## 2. 数据来源

本次检查基于以下正式结果：

| 层级/方法 | Raw result |
|---|---|
| ADVTEST-L0 | `E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\advtest_l0_suite_raw_results.jsonl` |
| ADVTEST-L1 | `E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\advtest_l1_suite_raw_results.jsonl` |
| ADVTEST-L2 | `E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-biglabel-three-method-q1000-v1\results\advtest_suite_raw_results.jsonl` |
| 汇总表 | `E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\rq1-error-summary-tables-v1\results\rq1_error_tables.md` |

对应输入图像为评测输出目录下的 `mosaics/*.jpg`，均为带对象 ID 标注的六视角拼图。

## 3. 检查过程

本轮检查分三步：

1. 读取 L0/L1/L2 的 raw result，按 `family` 统计错例数量。
2. 每个主要题型抽取多个错例，记录 `question / GT / predicted / image_path / scene_frame`。
3. 打开典型 mosaic 图，判断该题对人类是否可答，以及模型答错是否正常。

检查重点题型：

| 层级 | 重点题型 |
|---|---|
| L0 | `l0_count_type`, `l0_object_status`, `l0_object_status_no`, `l0_object_type`, `l0_object_type_no`, `l0_more_type_than_type`, `l0_object_exists` |
| L1 | `l1_pair_direction`, `l1_pair_direction_reverse`, `l1_relation_exists`, `l1_relation_exists_neg`, `l1_exist_direction_type`, `l1_exist_direction_type_no`, `l1_count_direction_type`, `l1_object_at_direction` |
| L2 | `converge`, `viewpoint_transfer`, `distance_chain` |

## 4. 总体结果

| Method | Q | Wrong | Error Rate |
|---|---:|---:|---:|
| ADVTEST-L0 | 1000 | 452 | 45.20% |
| ADVTEST-L1 | 1000 | 640 | 64.00% |
| ADVTEST-L2 | 1000 | 902 | 90.20% |

从总结果看，错误率随结构复杂度升高明显上升：

`L0 45.20% -> L1 64.00% -> L2 90.20%`

这个趋势符合预期：L2 的多关系交汇定位比单对象识别、单关系判断更容易暴露模型错误。

## 5. L0 错例分析

### 5.1 L0 各题型错误分布

| L0 Family | Q | Wrong | Error Rate | 初步判断 |
|---|---:|---:|---:|---|
| `l0_count_type` | 110 | 109 | 99.09% | 计数难，VLM 常漏数 |
| `l0_object_status_no` | 96 | 90 | 93.75% | status 否定题难，且单帧状态口径需谨慎 |
| `l0_object_status` | 99 | 77 | 77.78% | status 开放回答难，部分判分偏严 |
| `l0_object_type` | 91 | 48 | 52.75% | 类别开放回答有同义词/粒度问题 |
| `l0_object_type_no` | 105 | 49 | 46.67% | yes/no 类型负例，模型有误判 |
| `l0_more_type_than_type` | 84 | 47 | 55.95% | 类别比较依赖计数 |
| `l0_exist_status_type` | 99 | 28 | 28.28% | 难度中等 |
| `l0_object_status_yes` | 111 | 2 | 1.80% | 简单题，模型基本能做 |
| `l0_object_exists` | 100 | 1 | 1.00% | 简单题 |
| `l0_object_type_yes` | 105 | 1 | 0.95% | 简单题 |

### 5.2 L0 典型 case

#### Case L0-1: 计数题，题合理但对 VLM 难

```text
Family: l0_count_type
Scene: scene-0003_frame9
Question: How many pedestrians are visible?
GT: 9
Prediction: There are two pedestrians visible in the image.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame9_mosaic.jpg
```

人工观察：图中 pedestrian 分散在多个相机视角里，带标签可以数出来，但需要逐个找。  
结论：题是合理的，但不是简单题。VLM 答错正常。

#### Case L0-2: 大数量计数，题合理但高负荷

```text
Family: l0_count_type
Scene: scene-0003_frame11
Question: How many cars are visible?
GT: 12
Prediction: There are two cars visible in the image.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame11_mosaic.jpg
```

人工观察：人类可根据标签数出，但跨六视角、多遮挡、多近邻，工作量较大。  
结论：题合理；VLM 低估数量是典型视觉计数失败。

#### Case L0-3: 状态题，自动判分偏严

```text
Family: l0_object_status
Scene: scene-0003_frame7
Question: What is the movement status of pedestrian5?
GT: moving
Prediction: Pedestrian5 is walking.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame7_mosaic.jpg
```

人工判断：`walking` 与 `moving` 在该任务中应视为等价。  
结论：这不是模型真正错误，而是自动判分没有做同义归一。

#### Case L0-4: 状态题，模型明显错

```text
Family: l0_object_status_no
Scene: scene-0003_frame4
Question: Is barrier6 moving?
GT: no
Prediction: Yes, barrier6 is moving in the image.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame4_mosaic.jpg
```

人工判断：barrier 一般不应被判断为 moving。  
结论：题合理，模型明显错误。

#### Case L0-5: 类型题，类别粒度/同义词问题

```text
Family: l0_object_type
Scene: scene-0003_frame0
Question: What type of object is barrier1?
GT: barrier
Prediction: Barrier1 is a metal fence.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame0_mosaic.jpg
```

人工判断：`metal fence` 与 `barrier` 语义接近，但结构图类别是 `barrier`。  
结论：如果按结构类别严格判分，算错；如果按自然语义，属于近似正确。需要在 evaluator 或人工复核里单独标记。

#### Case L0-6: 类型题，同义词问题

```text
Family: l0_object_type
Scene: scene-0003_frame34
Question: What type of object is pedestrian2?
GT: pedestrian
Prediction: Pedestrian2 is a person.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame34_mosaic.jpg
```

人工判断：`person` 应该可以归一到 `pedestrian`。  
结论：当前自动判分偏严。

#### Case L0-7: 存在题，模型少数漏检

```text
Family: l0_object_exists
Scene: scene-0014_frame35
Question: Is bicycle2 visible?
GT: yes
Prediction: No, bicycle2 is not visible in the image.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0014_frame35_mosaic.jpg
```

人工判断：这类题通常最简单，但如果目标小、边缘、遮挡，模型仍可能漏。  
结论：题大概率合理，需看图确认 bicycle2 是否足够清楚。

### 5.3 L0 小结

L0 中并不是所有题都难：

- `object_exists`、`object_type_yes` 基本是简单题。
- `count`、`status`、开放类别回答明显更难。
- 一些错例来自自动判分偏严，而不是题本身错。

对人类而言：

- 有标签时，L0 计数题可做，但需要耐心逐个数。
- status 题存在单帧判断不稳定的问题，尤其 `moving/stopped/parked`。
- 对象类型题要明确是按结构类别还是自然语言类别判分。

## 6. L1 错例分析

### 6.1 L1 各题型错误分布

| L1 Family | Q | Wrong | Error Rate | 初步判断 |
|---|---:|---:|---:|---|
| `l1_count_direction_type` | 107 | 106 | 99.07% | 方向 + 计数，极难 |
| `l1_count_status_direction_type` | 96 | 94 | 97.92% | 方向 + 状态 + 计数，极难 |
| `l1_pair_direction_reverse` | 92 | 92 | 100.00% | 反向方向非常不直观，需重点复核 |
| `l1_pair_direction` | 111 | 102 | 91.89% | 细方向难，且判分对 `behind/back` 偏严 |
| `l1_relation_exists_neg` | 104 | 89 | 85.58% | 否定关系题，模型 yes-bias 明显 |
| `l1_exist_direction_type_no` | 79 | 55 | 69.62% | 方向存在负例，较难 |
| `l1_object_at_direction` | 96 | 55 | 57.29% | 方向内找类别，较难 |
| `l1_exist_status_direction_type` | 97 | 19 | 19.59% | 中等偏易 |
| `l1_relation_exists` | 108 | 16 | 14.81% | 正例关系题较容易 |
| `l1_exist_direction_type` | 110 | 12 | 10.91% | 正例存在题较容易 |

### 6.2 L1 典型 case

#### Case L1-1: 方向题，部分正确但严格判错

```text
Family: l1_pair_direction
Scene: scene-0003_frame1
Question: Where is car25 relative to barrier1?
GT: back left
Prediction: Car25 is located behind the barrier1.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame1_mosaic.jpg
```

人工判断：`behind` 对应 `back`，但缺少 `left`。  
结论：严格判错合理，但这是部分正确，不是完全错误。

#### Case L1-2: 方向同义词导致判分偏严

```text
Family: l1_pair_direction
Scene: scene-0003_frame7
Question: Where is car18 relative to car2?
GT: back
Prediction: Car18 is located behind car2.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame7_mosaic.jpg
```

人工判断：`behind` 应该等价于 `back`。  
结论：这应归为判分偏严。

#### Case L1-3: 反向方向题，逻辑有效但人类也不直观

```text
Family: l1_pair_direction_reverse
Scene: scene-0003_frame0
Question: Where is barrier2 relative to car14?
GT: front right
Prediction: Barrier2 is located behind car14.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame0_mosaic.jpg
```

人工观察：图上标签清楚，但方向不是屏幕方向，而是场景/BEV 方向。  
结论：题在结构坐标下有效，但对人类也需要明确方向定义。不能把它当普通自然视觉题。

#### Case L1-4: 反向方向题，VLM 按图像直觉答

```text
Family: l1_pair_direction_reverse
Scene: scene-0003_frame1
Question: Where is car21 relative to car23?
GT: front left
Prediction: Car21 is located behind car23.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame1_mosaic.jpg
```

人工判断：人类如果只看透视图，也容易按“图像中的前后”理解。  
结论：题偏难，适合作为 hard case，但需在论文中说明方向口径。

#### Case L1-5: 否定关系题，模型 yes-bias

```text
Family: l1_relation_exists_neg
Scene: scene-0003_frame5
Question: Is pedestrian10 to the back of car2?
GT: no
Prediction: Yes, pedestrian10 is to the back of car2.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame5_mosaic.jpg
```

人工判断：这类题是明确的关系判断。  
结论：若 GT 由结构图确认无误，则是有效检错题。模型容易顺着问题答 yes。

#### Case L1-6: 方向内类别存在，模型漏检

```text
Family: l1_exist_direction_type
Scene: scene-0012_frame8
Question: Are any pedestrians to the front of me?
GT: yes
Prediction: No, there are no pedestrians in the image.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0012_frame8_mosaic.jpg
```

人工判断：这类题如果目标可见，比较合理。  
结论：模型漏检；需人工确认目标是否足够可见。

#### Case L1-7: 方向计数，题合理但高难

```text
Family: l1_count_direction_type
Scene: scene-0003_frame9
Question: How many pedestrians are to the front left of barrier1?
GT: 3
Prediction: There are two pedestrians to the front left of barrier1.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame9_mosaic.jpg
```

人工判断：需要同时理解方位和计数。  
结论：题合理，但对人类也偏难；VLM 答错正常。

### 6.3 L1 小结

L1 里最需要注意的是方向定义：

- 如果按结构图/BEV 坐标，题是有效的。
- 如果按六视角图像直觉，人类也容易错。
- `pair_direction_reverse` 100% 错，不能简单解释成模型极差，也可能反映模板过于反直觉。

建议：

1. L1 方向类题在论文中说明方向口径。
2. 对 `pair_direction_reverse` 做人工抽检，决定是否作为 hard subset 单独报告。
3. 修 evaluator，把 `behind` 归一到 `back`。

## 7. L2 错例分析

### 7.1 L2 各题型错误分布

| L2 Family | Q | Wrong | Error Rate | 初步判断 |
|---|---:|---:|---:|---|
| `converge` | 994 | 898 | 90.34% | 主体题型，多约束交汇定位，合理 hard case |
| `viewpoint_transfer` | 3 | 3 | 100.00% | 题数很少，且有题面污染 |
| `distance_chain` | 2 | 1 | 50.00% | 题数很少 |
| `direction_chain` | 1 | 0 | 0.00% | 题数太少，不单独解释 |

### 7.2 L2 典型 case

#### Case L2-1: 多约束交汇定位，模型找错目标

```text
Family: converge
Scene: scene-0003_frame0
Question: Identify the car located to the back left of car24 and to the back right of pedestrian8, and to the front left of car23, and to the back right of car10.
GT: car21
Prediction: The car located ... is car14.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-biglabel-three-method-q1000-v1\results\mosaics\scene-0003_frame0_mosaic.jpg
```

人工观察：图上对象标签清楚，但需要同时核对 4 个关系。  
结论：题合理；对人类是高负荷题，对 VLM 答错非常正常。这是 ADVTEST 的核心检错能力。

#### Case L2-2: 多约束交汇定位，模型未输出具体 ID

```text
Family: converge
Scene: scene-0003_frame0
Question: Identify the barrier located to the front right of pedestrian8 and to the back left of pedestrian9, and to the back left of barrier1, and to the front right of barrier3.
GT: barrier2
Prediction: The barrier is located to the front right of pedestrian8 and to the back left of pedestrian9, and to the back left of barrier1, and to the front right of barrier3.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-biglabel-three-method-q1000-v1\results\mosaics\scene-0003_frame0_mosaic.jpg
```

人工判断：模型复述了条件，但没有输出目标 ID。  
结论：严格算错合理，因为题目要求 identify 具体对象。

#### Case L2-3: 多约束定位，题面有 `ego`

```text
Family: converge
Scene: scene-0003_frame0
Question: Identify the car located to the back left of car14 and to the back left of ego, and to the back right of car25, and to the back of car2.
GT: car17
Prediction: ... is car21.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-biglabel-three-method-q1000-v1\results\mosaics\scene-0003_frame0_mosaic.jpg
```

人工判断：逻辑可能有效，但 `ego` 对读者不自然，应改成 `me`。  
结论：题面需要清理，避免审稿人质疑。

#### Case L2-4: viewpoint_transfer 有异常字符

```text
Family: viewpoint_transfer
Scene: scene-0013_frame38
Question: From bicycle1, facing bus1, which side is car1 on бк left or right?
GT: left
Prediction: Car1 is on the right side of the image, facing the bus.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-biglabel-three-method-q1000-v1\results\mosaics\scene-0013_frame38_mosaic.jpg
```

人工判断：题面出现异常字符 `бк`。  
结论：该 case 不能作为正式证据，需要模板清理。

#### Case L2-5: 距离链

```text
Family: distance_chain
Scene: scene-0015_frame9
Question: Of bus2 and truck1, which is at a shorter distance from car2?
GT: truck1
Prediction: Bus2 is at a shorter distance from car2.
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-biglabel-three-method-q1000-v1\results\mosaics\scene-0015_frame9_mosaic.jpg
```

人工判断：距离题需要读图或依赖结构坐标，视觉上不一定直观。  
结论：题型合理，但数量太少，本轮不应重点解释。

### 7.3 L2 小结

L2 的主要结论：

- `converge` 是有效 hard case。
- 人类有标注图和方向定义时可以做，但需要多步推理。
- VLM 高错误率是正常的，也正是我们要展示的检错能力。
- 需要清理题面：`ego -> me`，异常字符删除，过长句子适当压缩。

## 8. 题是否有问题：分类结论

| 类别 | 说明 | 代表 case | 处理方式 |
|---|---|---|---|
| 题合理，模型真实错误 | 题面清楚，GT 合理，模型答错 | `barrier6 moving`, L2 `car21 -> car14` | 保留 |
| 题合理，但对人类也偏难 | 需要跨视角、计数、方向坐标、多步约束 | L0 count, L1 direction count, L2 converge | 保留，但标为 hard |
| 自动判分偏严 | 模型回答语义正确或部分正确，但字符串不匹配 | `walking/moving`, `person/pedestrian`, `behind/back` | 修 evaluator |
| 题面需要清理 | 题面不自然或有污染字符 | L2 `ego`, `бк` | 修模板/过滤 |
| 口径需要人工确认 | 单帧 status、反向方向 | L0 status, L1 reverse | 抽样人工标注 |

## 9. 相较于人类做题的难度判断

| 层级/题型 | 人类难度 | VLM 答错是否正常 | 备注 |
|---|---|---|---|
| L0 object exists | 易 | 不太正常 | 主要考读标签/识别目标 |
| L0 object type yes/no | 易 | 不太正常 | 若错，多为识别或类别混淆 |
| L0 open type | 中 | 正常 | 存在类别粒度和同义词问题 |
| L0 count | 中到难 | 正常 | 六视角分散目标，容易漏数 |
| L0 status | 中到难 | 正常 | 单帧不总公平，需谨慎 |
| L1 relation exists | 中 | 正常 | 正例相对容易 |
| L1 negative relation | 中到难 | 正常 | 模型 yes-bias 明显 |
| L1 pair direction | 难 | 正常 | 方向不是屏幕方向 |
| L1 reverse direction | 很难 | 很正常 | 对人类也反直觉 |
| L1 direction count | 很难 | 很正常 | 方位 + 计数双重难点 |
| L2 converge | 高负荷 | 非常正常 | 多约束交汇定位，是核心 hard case |
| L2 viewpoint/distance | 难 | 正常 | 当前题量少，且部分题面需清理 |

## 10. 对论文/汇报的建议表述

建议这样表述：

> 本轮错例检查表明，ADVTEST 的高错误率并非来自简单模板错误。L0/L1 中确实存在较容易的问题，例如对象是否存在、对象类型 yes/no，模型错误率很低；错误主要集中在计数、状态、方向和否定关系上。L2 的高错误率主要来自多约束交汇定位，这类题对人类在有标注图时可以完成，但需要多步核对，属于合理的 hard case。与此同时，我们也发现自动判分存在偏严问题，例如 `walking` 与 `moving`、`person` 与 `pedestrian`、`behind` 与 `back` 未被归一；L2 中还存在 `ego` 和异常字符等题面清理问题。因此，后续应将错误分为模型真实失败、判分偏严、题面需清理三类，并通过小规模人工复核进一步校准最终数字。

## 11. 后续行动建议

1. **修 evaluator 归一化**
   - `walking -> moving`
   - `person -> pedestrian`
   - `behind -> back`
   - `in front -> front`
   - `no / none / no objects -> 0`

2. **清理 L2 题面**
   - `ego -> me`
   - 删除异常字符，例如 `бк`
   - 限制过长 converge 句子，必要时拆成更自然的表达。

3. **人工抽检**
   - L0 status：抽 20 个。
   - L1 reverse direction：抽 20 个。
   - L2 converge：抽 20 个。
   - 标注字段建议：`valid`, `hard_but_valid`, `scoring_issue`, `invalid_template`, `unclear_visibility`。

4. **最终汇报时拆开讲**
   - 不要只报总错误率。
   - 报总表 + 题型表 + case 分类。
   - 强调 L2 是多约束 hard case，L0/L1 的错误主要来自 count/status/direction，而不是所有低阶题都难。

