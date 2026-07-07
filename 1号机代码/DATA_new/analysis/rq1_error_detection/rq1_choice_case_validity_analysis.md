# Case Analysis: Multiple-Choice RQ1 Error Cases

## 目的

这份文档整理 RQ1 故障检测实验中“选择题版”的 case 分析。它和 `rq1_case_validity_analysis.md` 的目的保持一致：不只是看错误率，而是检查错误来自哪里。

本版重点回答：

1. 选择题形式是否缓解了开放回答的同义词判分问题？
2. 选择题仍然答错时，主要是模型视觉/空间理解失败，还是选项设计、提示口径、自动判分问题？
3. ADVTEST、QATest、QAAskeR 在选择题版里分别暴露出什么问题？
4. 哪些 case 可以进入论文/汇报，哪些需要在下一轮修正后再统计？

注意：`Think` 不接入正式流程。本文件只分析正式选择题/两步选择题结果；`Think` 后续只用于典型错题的单独复盘，不进入主错误率。

## 检查过程

本轮检查分四步：

1. 读取选择题版 raw result，按方法和题型统计 `Q / Calls / Wrong / Error Rate`。
2. 对 ADVTEST-L0、ADVTEST-L1、ADVTEST-L2 抽取典型错例，记录 `question / options / GT / prediction / image_path / scene_frame`。
3. 对 QATest、QAAskeR 抽取两步选择题错例，区分自由回答阶段错误和映射阶段错误。
4. 对每类 case 给出人工判断：题是否合理、难度如何、是否需要修正提示或选项设计。

数据来源：

| 部分 | 结果目录 | 说明 |
|---|---|---|
| ADVTEST-L0/L1 choice | `E:\Project\ADVTEST\scratch\rq1_choice_suites_v1_formal\mplug_choice_eval_v2\results` | 早先选择题 formal 结果 |
| ADVTEST-L2 choice | `E:\Project\ADVTEST\scratch\rq1_choice_suites_v3_formal\mplug_choice_eval_v3_advtest_l2` | 修正 L2 选项后的正式结果 |
| QATest/QAAskeR two-step choice | `E:\Project\ADVTEST\scratch\rq1_choice_suites_v3_formal\two_step_mplug_full_v1` | 先自由回答，再映射到选项 |

## 总体结果

| Method | Q | Calls | Wrong | Error Rate | 备注 |
|---|---:|---:|---:|---:|---|
| ADVTEST-L0 choice | 1000 | 1000 | 341 | 34.10% | 选择题后低于开放回答版，但计数/状态/比较仍会错 |
| ADVTEST-L1 choice | 1000 | 1000 | 555 | 55.50% | 方向与局部关系仍然难 |
| ADVTEST-L2 converge choice | 973 | 973 | 521 | 53.55% | 多约束定位，难度高 |
| ADVTEST-L2 direction_chain choice | 1000 | 1000 | 120 | 12.00% | yes/no 结构，明显更容易 |
| ADVTEST-L2 distance_chain choice | 1000 | 1000 | 513 | 51.30% | 近远比较仍难 |
| ADVTEST-L2 viewpoint_transfer choice | 1000 | 1000 | 701 | 70.10% | 视角变换最不稳定；方向口径需进一步精确 |
| ADVTEST-L2 mixed choice | 955 | 955 | 484 | 50.68% | 当前 mixed 仍以 converge 为主 |
| QAAskeR two-step choice | 1000 | 2000 | 55 | 5.50% | 题型多为 yes/no，检测强度弱 |
| QATest two-step choice | 1000 | 2000 | 153 | 15.30% | 有语病/扰动导致的错误，也有映射错 |

总体判断：

1. 选择题确实降低了 L0/L1 中一部分同义词判分偏严问题。
2. ADVTEST-L2 仍然保持较高错误率，说明错误不是单纯由开放回答判分造成的。
3. QATest/QAAskeR 错误率低，不代表更好，而是它们生成的问题大多没有覆盖复杂空间结构；尤其 QAAskeR 大量是 yes/no 自一致性问题。
4. `viewpoint_transfer` 当前 v3 错误率很高，其中一部分是真空间推理失败，另一部分和方向提示口径有关；下一轮应使用 NuScenes-QA 的 6 类方向角度规则重跑。

## L0 选择题错例分析

### L0 典型 case

#### Case L0-1: 可见性题，选择题仍漏检

```text
Family: L0 / object_exists
Scene: scene-0003_frame0
Question: Is pedestrian7 visible?

A. yes
B. no

GT: A. yes
Prediction: B
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame0_mosaic.jpg
```

人工判断：这类题本身很简单，选择题也没有同义词问题。模型答 `no` 说明它没有稳定定位到指定 id 的目标。

结论：这是有效的 VLM 漏检 case，可以保留为 L0 视觉定位失败。

#### Case L0-2: 数量比较题，选择题不能完全解决计数难度

```text
Family: L0 / more_type_than_type
Scene: scene-0003_frame0
Question: Are there more barriers than pedestrians visible?

A. no
B. yes

GT: A. no
Prediction: B. yes
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame0_mosaic.jpg
```

人工判断：题面明确，选项只有 yes/no，判分没有歧义。错误主要来自模型没有准确计数两类目标。

结论：L0 选择题错误中，计数/比较类仍然是有效难点。

#### Case L0-3: 状态题，可能需要检查单帧状态口径

```text
Family: L0 / object_status
Scene: scene-0003_frame1
Question: Is car10 stopped?

A. yes
B. no

GT: A. yes
Prediction: B
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame1_mosaic.jpg
```

人工判断：车辆 stopped/parked/moving 的判断在单帧图像里不总是直观，但如果标签来自结构图，GT 是确定的。

结论：这类题可以保留，但论文中需要说明状态来自标注/结构信息；对人类仅凭单帧判断会比 object type 更难。

## L1 选择题错例分析

### L1 典型 case

#### Case L1-1: 方向题，选项给出后仍判断反向

```text
Family: L1 / pair_direction
Scene: scene-0003_frame0
Question: Where is barrier2 relative to car14?

Direction hint: front around 0°, front left around 45°, left around 90°, back left around 135°, back around 180°, back right around -135°, right around -90°, front right around -45°.

A. front left
B. back left
C. front
D. front right

GT: D. front right
Prediction: B. back left
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame0_mosaic.jpg
```

人工判断：题目和选项都明确，模型把 `front right` 判断成 `back left`，属于方向轴理解错误。

结论：这是有效的 L1 空间关系失败，不是开放回答判分问题。

#### Case L1-2: 存在关系题，yes/no 也会漏掉局部关系

```text
Family: L1 / relation_exists
Scene: scene-0003_frame0
Question: Are any cars to the front of car10?

A. yes
B. no

GT: A. yes
Prediction: B
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame0_mosaic.jpg
```

人工判断：这不是要求模型输出具体对象，只需要判断是否存在。模型仍然答错，说明它没有可靠搜索指定方向区域。

结论：选择题形式不能消除空间搜索能力不足。

#### Case L1-3: 指定对象关系题，容易受近邻目标干扰

```text
Family: L1 / relation_exists
Scene: scene-0003_frame1
Question: Is car10 to the front left of car23?

A. yes
B. no

GT: A. yes
Prediction: B
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1\results\mosaics\scene-0003_frame1_mosaic.jpg
```

人工判断：同帧车辆密集，目标 id 多，模型容易把 car10/car23 或方向关系混淆。

结论：这是合理难度的 L1 case。它比 L0 可见性更难，但还没有 L2 多跳组合复杂。

## L2 选择题错例分析

### L2 各题型错误分布

| L2 Family | Q | Wrong | Error Rate | 初步判断 |
|---|---:|---:|---:|---|
| `converge` | 973 | 521 | 53.55% | 多约束共同定位，模型常选同类干扰项 |
| `direction_chain` | 1000 | 120 | 12.00% | yes/no 链式方向判断，当前最容易 |
| `distance_chain` | 1000 | 513 | 51.30% | 两两距离比较，模型常被视觉近邻误导 |
| `viewpoint_transfer` | 1000 | 701 | 70.10% | 视角变换最难，且方向口径要进一步精确 |
| `mixed` | 955 | 484 | 50.68% | mixed 当前主要由 converge 支配 |

### L2 典型 case

#### Case L2-1: converge，多约束定位选错同类目标

```text
Family: converge
Scene: scene-0003_frame2
Question: There is a barrier to the front right of car1 and to the front left of pedestrian5, and to the front right of barrier2; what is it?

A. barrier4
B. barrier9
C. barrier27
D. barrier1

GT: D. barrier1
Prediction: A. barrier4
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0003_frame2_mosaic.jpg
```

人工判断：选项全是 barrier，已经避免了“选项类型泄露答案”的问题。模型仍选错，说明它没有正确同时满足多个空间约束。

结论：这是 ADVTEST 的核心有效 case。选择题降低了回答格式难度，但保留了结构推理难度。

#### Case L2-2: converge，约束越多越容易被局部线索误导

```text
Family: converge
Scene: scene-0003_frame33
Question: There is a barrier to the back of car20 and to the front of pedestrian11, and to the front left of barrier4, and to the back of pedestrian1; what is it?

A. barrier11
B. barrier7
C. barrier19
D. barrier25

GT: B. barrier7
Prediction: A. barrier11
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0003_frame33_mosaic.jpg
```

人工判断：人类需要逐条排除候选 barrier。题目不要求开放生成，只要求从同类候选中选择，因此选错更能说明空间组合推理不足。

结论：题合理，难度高，适合作为论文中的代表 case。

#### Case L2-3: direction_chain，yes/no 链式方向仍有失败

```text
Family: direction_chain
Scene: scene-0015_frame19
Question: Does car8 lie in the same direction from truck1 as car1?

A. no
B. yes

GT: A. no
Prediction: B
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000\results\mosaics\scene-0015_frame19_mosaic.jpg
```

人工判断：这个题只需比较两个方向是否一致，不需要输出具体方向。错误率低于其他 L2，说明选择题/yes-no 对模型更友好。

结论：direction_chain 可以作为“相对容易的 L2 子类”，不应和 converge/viewpoint_transfer 简单混成一个比例。

#### Case L2-4: distance_chain，近远比较仍然难

```text
Family: distance_chain
Scene: scene-0003_frame31
Question: Which object is barrier1 nearer to, car19 or car20?

A. car19
B. car20

GT: B. car20
Prediction: A
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0003_frame31_mosaic.jpg
```

人工判断：题面和选项都非常清楚，但距离判断需要模型从图像中恢复目标间相对位置。若两个候选距离接近，人类也需要仔细看标签和位置。

结论：这是有效的空间度量失败。后续 case 复核时应标记“距离是否接近”，避免把极模糊样本当作强证据。

#### Case L2-5: viewpoint_transfer，模型没有稳定完成视角转换

```text
Family: viewpoint_transfer
Scene: scene-0016_frame6
Question: From pedestrian17, facing pedestrian7, where is pedestrian4 relative to you?

Direction hint: use the ego-vehicle coordinate convention; select the most precise direction label.

A. back left
B. right
C. left
D. front

GT: C. left
Prediction: A. back left
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0016_frame6_mosaic.jpg
```

人工判断：模型不是简单左右偏差，而是把视角转换后的象限判断错了。这个题对人类也不算轻松，需要先确定“从 pedestrian17 朝向 pedestrian7”的坐标系，再定位 pedestrian4。

结论：这是有效的高难空间推理 case。但 v3 的方向提示使用 8 类近似方向，下一轮应按 NuScenes-QA 的 6 类角度规则重跑，使口径更公平。

#### Case L2-6: viewpoint_transfer，方向提示需要更精确

```text
Family: viewpoint_transfer
Scene: scene-0003_frame17
Question: From barrier4, facing pedestrian2, where is car15 relative to you?

A. front left
B. front right
C. back right
D. front

GT: C. back right
Prediction: B. front right
Image: E:\Project\ADVTEST\scratch\rq1_l2_family_formal_mplug_1000_resume1\results\mosaics\scene-0003_frame17_mosaic.jpg
```

人工判断：`front right` 和 `back right` 都在右侧，模型至少捕捉到一部分方向，但前后轴错了。严格判错合理，但为了避免“模型不知道方向标签边界”的质疑，下一轮应在题面加入 NuScenes-QA 的角度划分。

结论：这类 case 应保留，但报告时可说明“严格选择题结果”和“NuScenes-QA 角度提示版结果”会分开展示。

## QATest 选择题错例分析

### QATest 典型 case

#### Case QATest-1: 扰动后题面有语病，模型自由回答阶段已错

```text
Method: QATest two-step choice
Scene: scene-0016_frame1
Question: Ake any stopped trailers visible?

A. no
B. yes

GT: A. no
Free-form answer: Yes, there are two stopped trailers visible in the image.
Final Prediction: B. yes
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-biglabel-three-method-q1000-v1\results\mosaics\scene-0016_frame1_mosaic.jpg
```

人工判断：`Ake` 是扰动后的拼写错误，但大意仍可理解。模型答错主要发生在自由回答阶段，不是映射阶段。

结论：QATest 的错误可以作为“文本扰动后模型鲁棒性下降”的结果，但它不是覆盖引导的空间结构检错。

#### Case QATest-2: 自由回答看似对，映射阶段选错

```text
Method: QATest two-step choice
Scene: scene-0016_frame32
Question: What is the not tanding pedestrian to the front of me?

GT: A. pedestrian
Free-form answer: The standing pedestrian is in front of the car.
Final Prediction: B. car
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-biglabel-three-method-q1000-v1\results\mosaics\scene-0016_frame32_mosaic.jpg
```

人工判断：自由回答里同时出现了 `pedestrian` 和 `car`，但真正回答对象应是 pedestrian。映射阶段选了上下文里的 car。

结论：两步选择题能暴露“答案映射被上下文实体干扰”的问题。QATest 的 153 个最终错误中，有 21 个属于 primary correct but mapping wrong。

#### Case QATest-3: 题面扰动导致语义不稳

```text
Method: QATest two-step choice
Scene: scene-0016_frame26
Question: The not standing pedestrian is what??

GT: B. pedestrian
Free-form answer: The not standing pedestrian is walking.
Final Prediction: C. car
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-biglabel-three-method-q1000-v1\results\mosaics\scene-0016_frame26_mosaic.jpg
```

人工判断：题面问的是对象类型，但自由回答转向状态 `walking`，最终映射又选到 `car`。这不是我们 ADVTEST 的结构覆盖问题，而是 QATest 文本变形后语义漂移。

结论：QATest 可以作为 baseline，但要在论文里说明其错误性质不同。

## QAAskeR 选择题错例分析

### QAAskeR 典型 case

#### Case QAAskeR-1: 生成题语法重复，但 yes/no 仍能检测到模型错误

```text
Method: QAAskeR two-step choice
Scene: scene-0016_frame14
Question: Is the not standing pedestrian The not standing pedestrian is walking down the street?

A. yes
B. no

GT: A. yes
Free-form answer: No, the not standing pedestrian is not walking down the street. They are standing on the sidewalk.
Final Prediction: B. no
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-biglabel-three-method-q1000-v1\results\mosaics\scene-0016_frame14_mosaic.jpg
```

人工判断：题面有明显重复和不自然，但 yes/no 语义还能读出来。模型答错是自由回答阶段错。

结论：QAAskeR 能产生少量检错 case，但问题质量较不稳定，且题型简单。

#### Case QAAskeR-2: 题面来自 follow question 拼接，语义可读但不自然

```text
Method: QAAskeR two-step choice
Scene: scene-0014_frame31
Question: Is there a truck parked in front of the parked car . is located to the front of the parked car?

A. yes
B. no

GT: A. yes
Free-form answer: No, there is no truck parked in front of the parked car. The car is located to the front of the parked bus.
Final Prediction: B. no
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-biglabel-three-method-q1000-v1\results\mosaics\scene-0014_frame31_mosaic.jpg
```

人工判断：题面不够自然，但仍是一个可判定的 yes/no 问题。模型答错说明它没有正确处理目标和关系。

结论：可以保留为 baseline 错例，但它不如 ADVTEST case 能体现系统性覆盖能力。

#### Case QAAskeR-3: 错误率低的原因是题型简单，不是检错能力强

```text
Method: QAAskeR two-step choice
Scene: scene-0013_frame25
Question: Is the parked thing that is both to the front of the stopped car and the back right of the bicycle The parked thing that is both to the front of the stopped car and the back right of the bicycle is a truck?

A. yes
B. no

GT: A. yes
Free-form answer: No, the parked thing that is both to the front of the stopped car and the back right of the bicycle is not a truck. It is a bus.
Final Prediction: B. no
Image: E:\Project\ADVTEST\scratch\rq1_seed_expansion\runs\mplug-biglabel-three-method-q1000-v1\results\mosaics\scene-0013_frame25_mosaic.jpg
```

人工判断：这道题已经带有一定空间约束，但仍是 yes/no 验证题。与 ADVTEST converge 不同，它没有要求模型在多个同类候选里选出唯一目标。

结论：QAAskeR 错误率低不能直接解释为“更稳”，而是问题空间和 ADVTEST 不同。

## 关键结论

1. 选择题版能降低一部分开放回答判分偏严，但不能消除 ADVTEST 的检错能力。
2. ADVTEST 的有效性主要体现在：即使给出候选选项，模型仍难以完成多目标定位、距离比较和视角转换。
3. L2 内部题型差异很大，不能只报一个 mixed 总数。后续应该按 `converge / direction_chain / distance_chain / viewpoint_transfer` 分别报告，再讨论综合比例。
4. `viewpoint_transfer` 当前需要进一步精确提示。下一版应采用 NuScenes-QA 方向标准：`front / front left / front right / back left / back right / back` 六类角度区间。
5. QATest 和 QAAskeR 的错例性质与 ADVTEST 不同。它们更多检验文本扰动或 follow question 的自一致性，不是覆盖引导的结构空间检错。
6. Think 不进入正式统计。后续只从上述典型错例中抽样，用 `GT / Pred / Think` 看模型错误原因。

## 下一步

1. 用 NuScenes-QA 6 类方向角度提示重跑 `viewpoint_transfer`。
2. 对 `distance_chain` 标记候选距离是否接近，区分“合理难题”和“过于模糊题”。
3. 保留严格选择题结果作为主表；必要时补充放宽判分表。
4. 单独挑典型错题跑 Think，用于 case 解释，不并入正式流程。
