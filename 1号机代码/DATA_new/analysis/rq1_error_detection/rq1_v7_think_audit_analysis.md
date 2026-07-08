# RQ1 v7 Think Audit 分析

这份文档只分析典型错题的 think 试点，不进入正式错误率指标。

## 1. 运行口径

- 输入：v7 case 分析中的 9 类 case，每类 2 题，共 18 题。
- 模型：mPLUG-Owl2，本地 ModelScope 权重，`.venv310` 环境。
- v1/v2 单轮格式：要求模型同时输出 `Pred` 和 `Reason/Think`。
- 单轮结果：`Reason/Think` 非空 0/18，mPLUG 基本只输出选项，不输出理由。
- v3 two-call 格式：第一问选项，第二问固定其选择，让模型补一句视觉依据。
- v3 结果：非空理由 18/18，总 VLM 调用 36 次。
- v3 选项正确 3/18；相对原先错误结果，选项字母变化 5/18，保持同一选项 13/18。

重要说明：这里的 `Think` 不是模型真实内部推理，只能看作“事后给出的可见线索/解释”。但它仍然有用，因为能暴露模型到底在抓哪个错误线索。

## 2. 按 case 类别汇总

| Case | Q | Correct | 主要观察 |
|---|---:|---:|---|
| L0-count | 2 | 0 | 两题都仍然数错，理由也没有真正解释数量，只给出泛化场景描述。这说明计数题的错误更接近视觉计数失败，而不是答案格式问题。 |
| L0-status | 2 | 1 | 一题在 think 重问后改对，一题仍坚持 moving。理由能明确说出 stopped/moving，适合人工复核图像状态是否可见。 |
| L1-direction | 2 | 0 | 两题都错，理由只用了 left/back/front 这类粗方向，没有按角度表完成精确方向选择。 |
| L1-count-direction | 2 | 0 | 两题都错，理由显示模型能抓到局部线索，但计数或方向约束没有同时满足。 |
| L2-converge | 2 | 0 | 两题都错，理由只覆盖部分约束或复述题干，不能证明它真的完成了唯一目标交汇定位。 |
| L2-direction-chain | 2 | 2 | 两题在重问后都改对，但理由非常泛化，没有解释关系链本身；这类题的答案可被选择题格式纠正，但 reason 证据弱。 |
| L2-distance-chain | 2 | 0 | 两题都错，理由没有比较距离，只给出泛化场景描述或重复选项；说明距离比较仍是实际难点。 |
| L2-viewpoint-back | 2 | 0 | 两题都错，理由明确说目标在 behind/back，说明模型按粗略场景方位判断，没有完成以目标朝向为 0° 的坐标转换。 |
| L2-viewpoint-left-right | 2 | 0 | 两题都错，理由都说目标在 left，暴露出 left/right 方向选择偏差；这正是 v7 角度精细化后想检出的错误。 |

## 3. 逐题结果

| Case | Sample | Family | Scene | GT | Prior Pred | Think Pred | Correct | Think / Reason |
|---|---:|---|---|---|---|---|---:|---|
| L0-count | 1 | `l0:count_type` | scene-0003_frame9 | B. 9 | A | A. 11 | False | A car is parked in front of a building. |
| L0-count | 2 | `l0:count_type` | scene-0003_frame10 | B. 7 | C | A. 6 | False | A car is parked in front of a building. |
| L0-status | 1 | `l0:status_yes` | scene-0003_frame1 | A. yes | B | A. yes | True | A car is stopped in front of a building. |
| L0-status | 2 | `l0:status` | scene-0003_frame6 | C. stopped | B. moving | B. moving | False | The car20 is moving. |
| L1-direction | 1 | `l1:direction_reverse` | scene-0003_frame0 | D. front right (-90° < theta <= -30°) | C. front (-30° < theta <= 30°) | A. front left (30° < theta <= 90°) | False | The barrier is located to the left of the car14. |
| L1-direction | 2 | `l1:direction` | scene-0003_frame1 | C. back left (90° < theta <= 150°) | A. back (otherwise) | A. back (otherwise) | False | A car is parked in front of a barrier. |
| L1-count-direction | 1 | `l1:count_status_direction_type` | scene-0003_frame2 | B. 4 | A. 3 | A. 3 | False | A car is parked behind car14. |
| L1-count-direction | 2 | `l1:count_direction_type` | scene-0003_frame7 | A. 1 | C. 2 | C. 2 | False | The image shows two pedestrians to the back right of barrier2. |
| L2-converge | 1 | `converge` | scene-0003_frame33 | B. barrier7 | C. barrier3 | C. barrier3 | False | The barrier is in front of pedestrian1 and to the back of car20. |
| L2-converge | 2 | `converge` | scene-0016_frame17 | D. pedestrian12 | A. pedestrian3 | A. pedestrian3 | False | A pedestrian is positioned to the front left of pedestrian14 and pedestrian20, and to the back left of pedestrian8. |
| L2-direction-chain | 1 | `direction_chain` | scene-0015_frame19 | A. no | B | A. no | True | A car is driving down the street. |
| L2-direction-chain | 2 | `direction_chain` | scene-0016_frame19 | A. yes | B. no | A. yes | True | A man is walking on the sidewalk. |
| L2-distance-chain | 1 | `distance_chain` | scene-0003_frame31 | B. car20 | A | A. car19 | False | A car is parked in front of a barrier. |
| L2-distance-chain | 2 | `distance_chain` | scene-0016_frame28 | B. car3 | A | A. car1 | False | A. car1 |
| L2-viewpoint-back | 1 | `viewpoint_transfer` | scene-0003_frame10 | A. front right (-90° < theta <= -30°) | C. back (otherwise) | C. back (otherwise) | False | The car23 is located behind the pedestrian5. |
| L2-viewpoint-back | 2 | `viewpoint_transfer` | scene-0017_frame15 | D. front right (-90° < theta <= -30°) | C. back | C. back (otherwise) | False | The pedestrian is behind the barrier and truck. |
| L2-viewpoint-left-right | 1 | `viewpoint_transfer` | scene-0003_frame3 | D. front right (-90° < theta <= -30°) | C. front left (30° < theta <= 90°) | C. front left (30° < theta <= 90°) | False | The pedestrian is located to the left of the car21. |
| L2-viewpoint-left-right | 2 | `viewpoint_transfer` | scene-0016_frame18 | C. front right (-90° < theta <= -30°) | A. front left (30° < theta <= 90°) | A. front left (30° < theta <= 90°) | False | The pedestrian19 is located to the left of pedestrian15. |

## 4. 当前判断

1. `L0-count`、`L1-count-direction`、`L2-distance-chain` 的理由常常是泛化描述，说明模型没有真正给出可验证的计数/距离依据。
2. `L2-converge` 的理由经常只覆盖局部约束，支持我们对 converge 的判断：它难在多约束同时满足，而不是单个关系看不懂。
3. `L2-viewpoint_transfer` 的理由最有诊断价值：模型明确说 behind/left，但 GT 是 front right，说明它在目标朝向坐标系转换上失败。
4. `L2-direction-chain` 在 two-call 后改对，但理由不解释关系链，说明这个子类不宜作为强 hard-case 主证据。
5. think 机制后续建议只用于典型错题解释和人工复核辅助，不作为正式自动指标。
