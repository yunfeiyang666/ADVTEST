# RQ1 故障检测汇报 PPT 大纲（2026-06-17）

> 用途：从 `rq1_fault_detection_briefing_2026-06-17.md` 压缩成今晚汇报 slides。
> 建议页数：12 页左右。重点是先讲清实验边界，再讲结果，不要一上来堆表。

## Slide 1. 标题页

标题：面向自动驾驶 VLM 的结构化故障检测实验进展

副标题：RQ1: Equal-budget error detection with ADVTEST

讲稿提示：

- 这部分不是普通 VQA accuracy，而是 testing setting。
- 目标是同样测试预算下暴露更多 VLM 错误，尤其是结构关系错误。

## Slide 2. 问题重定义：从覆盖率到故障检测

核心信息：

- 早期只看 scene graph gap / L2 coverage。
- 现在 RQ1 更准确的表述是：哪种测试用例生成/选择策略更能发现 VLM 错误？
- 主指标分成两类：
  - unique failures / VLM call。
  - failed unique L2，即错误触发的结构项覆盖。

建议图示：

```text
Question generation -> VLM inference -> wrong answer -> unique failure -> failed L2 footprint
```

讲稿提示：

- 这句话很关键：ADVTEST 的优势主要是 coverage-breadth effect。

## Slide 3. 为什么对照组必须重设

核心信息：

- 早期 baseline 曾经共享 ADVTEST candidate pool 或 coverage footprint。
- 这样会让对照组借用我们的方法能力。
- 因此不能把 QATest/QAAskeR/Random 都放进一个无差别 baseline 表里。

可以放两列对比：

| 不严谨设置 | 当前设置 |
|---|---|
| 多方法共享 ADVTEST 生成题 | 按实验层分离 |
| 变异题继承 coverage footprint | 外部方法不读取 ADVTEST 私有字段 |
| 所有方法混排比较 | internal ablation 和 external reference 分开 |

讲稿提示：

- 主动承认早期设置风险，老师通常会更放心。

## Slide 4. 实验分层

核心表：

| 层 | 回答的问题 | 方法 |
|---|---|---|
| Layer A: Structural internal ablation | coverage guidance 是否有效 | ADVTEST vs Random 等 |
| Layer B: Cross-paradigm reference | 不同 QA/testing 范式发现多少错 | Official-QA, QATest-adapted |
| Layer C: Official-QA selection control | 只从官方题里选，coverage selector 是否有用 | 后续设计 |

讲稿提示：

- 当前今晚重点讲 Layer A 和 Layer B。
- Random 是 internal ablation，不是外部 SOTA baseline。

## Slide 5. 预算口径

核心表：

| 预算 | 含义 | 用途 |
|---|---|---|
| generation_budget | 离线生成多少题 | 覆盖曲线、suite capacity |
| vlm_call_budget | 实际调用 VLM 多少次 | 故障检测主表 |

关键结论：

- 主实验统一为每方法 1000 次真实 VLM call。
- QATest-adapted 离线生成不消耗 VLM call，评测时每题 1 call。
- QAAskeR 通常需要主问 + follow-up，至少 2 call，因此本轮不进主表。

讲稿提示：

- 老师如果追问 QAAskeR，就说后续单独做 capacity / two-call protocol。

## Slide 6. 对照组角色边界

核心表：

| 方法 | 当前角色 | 结构 L2 是否可比 | 说明 |
|---|---|---:|---|
| ADVTEST | proposed | yes | 结构化 coverage-guided testing |
| Random | internal ablation | yes | 同结构化问题空间，随机顺序 |
| Official NuScenes-QA | neutral reference | no | category-level 官方 GT |
| QATest-adapted | external comparison | no | 官方 QA seed 上独立变异 |
| QAAskeR | postponed | no | 预算口径复杂，暂不进主表 |

讲稿提示：

- 不要说 Official-QA/QATest-adapted 输给我们；说它们是 cross-paradigm reference。

## Slide 7. QATest-adapted 的处理

核心信息：

- 原始 QATest 环境老，部分算子依赖硬编码模型路径、外部服务和 token 风险。
- 不能直接声称逐字节复现原版 QATest。
- 当前使用 QATest-adapted：
  - 官方 NuScenes-QA seed。
  - seed pool 和候选重试。
  - Rouge-1 过滤。
  - POS-transition probability。
  - 1-4 gram coverage feedback。
  - duplicate rejection。

生成 audit 数字：

| 方法 | 题数 | Unique | Frames | Answer mismatch |
|---|---:|---:|---:|---:|
| qatest_style | 1000 | 1000 | 99 | 0 |
| qatest_adapted | 1000 | 1000 | 100 | 0 |

讲稿提示：

- `qatest_style` 只作为 legacy ablation，主参考是 `QATest-adapted`。

## Slide 8. 主实验设置

核心信息：

- 模型：mPLUG-Owl2。
- 每方法：1000 real VLM calls。
- 总计：4000 real inference records。
- 运行耗时：32921.27 秒，约 9.14 小时。
- mock fallback：0。
- scoring：`token_boundary_v2_frame_qualified_l2`。

输入 gate：

| 方法 | Calls | Frames | GT granularity | Coverage comparable |
|---|---:|---:|---|---:|
| ADVTEST | 1000 | 20 | instance_or_relation | yes |
| Random | 1000 | 20 | instance_or_relation | yes |
| Official-QA | 1000 | 67 | category_level_official | no |
| QATest-adapted | 1000 | 100 | category_level_official | no |

讲稿提示：

- 强调 strict real inference 和 no mock fallback。

## Slide 9. 主结果：ADVTEST vs Random

核心结果表：

| 方法 | Unique failures | UF/100 | Failed unique L2 | Input covered L2 |
|---|---:|---:|---:|---:|
| ADVTEST | 981 | 98.1 | 4488 | 4508 |
| Random | 912 | 91.2 | 2727 | 2818 |
| Gain | +69 | +7.57% | +1761 / +64.58% | +1690 / +59.97% |

讲稿提示：

- raw unique failures 有提升，但不是最大亮点。
- 最大亮点是 failed structural coverage。
- 这支撑“测试方法暴露更广结构错误空间”的叙事。

## Slide 10. Cross-paradigm reference 结果

核心表：

| 方法 | Calls | Wrong | Independent failures | Duplicate rate | Frames |
|---|---:|---:|---:|---:|---:|
| Official-QA | 1000 | 650 | 650 | 0.000 | 67 |
| QATest-adapted | 1000 | 637 | 468 | 0.265 | 100 |

讲稿提示：

- 这两行不要和 ADVTEST 的 structural L2 直接比。
- 它们说明：官方类别级题和 QATest 变异题也能暴露错误，但任务范式和 GT 粒度不同。
- QATest-adapted 的 duplicate rate 较高，说明很多变异仍回到同一类 independent failure。

## Slide 11. Random seed 稳健性

核心表：

| 方法 | Seed | Calls | Independent failures | Failed unique L2 |
|---|---:|---:|---:|---:|
| ADVTEST | fixed | 100 | 92 | 236 |
| Random | 42 | 100 | 86 | 169 |
| Random | 43 | 100 | 88 | 180 |
| Random | 44 | 100 | 90 | 183 |

结论：

- Random 平均 independent failures = 88.00，ADVTEST +4.00。
- Random 平均 failed unique L2 = 177.33，ADVTEST +58.67。
- ADVTEST 三个 seed 都超过 Random。

讲稿提示：

- failure count margin 是 modest。
- failed-L2 margin 更明显，继续支撑结构覆盖优势。

## Slide 12. Failure audit：为什么不是判分假象

核心信息：

- 48 行人工 sanity audit：
  - 33/48 valid visual or structural failures。
  - Random-only 单题有效率略高：75.0% vs ADVTEST-only 66.7%。
  - 但 ADVTEST exclusive failed-L2 空间更大。
- 400 行 assisted audit：
  - assisted valid 311/400 = 77.8%。
  - ADVTEST-only estimated valid total = 2149.0。
  - Random-only estimated valid total = 1138.8。
  - difference = +1010.2。
  - conservative lower-minus-upper = +647.3。

必须保留的 caveat：

- 400 行是 assisted review，不是最终纯人工审阅。
- 100 行 human adjudication pack 已生成，但 `human_*` 仍 pending。

讲稿提示：

- 这页的作用是提前堵住“是不是字符串匹配导致”的质疑。

## Slide 13. 当前结论

PPT 可放的一句话：

> 在相同 VLM 调用预算下，ADVTEST 相比随机结构化采样不仅发现更多 mPLUG-Owl2 错误，更显著扩大了被触发失败的结构关系覆盖范围；其优势主要体现为 coverage-breadth effect，而不是单题有效率更高。

分点：

- ADVTEST vs Random 是当前最公平的内部比较。
- Official-QA / QATest-adapted 是外部参考，不做结构覆盖 head-to-head。
- QAAskeR 暂缓纳入，原因是 two-call budget。
- 人工校准仍是下一步关键。

## Slide 14. 下一步

优先级：

1. 填完 100 行 `human_adjudication_pack.csv` 的 `human_*` 列。
2. 运行 `summarize_rq1_human_adjudication.py --require-complete`，得到 assisted label 的一致率和校准后估计。
3. 若时间允许，补 Official-QA selection control，证明 neutral official seed 上 coverage-aware selection 也有价值。
4. 再考虑 QAAskeR 的 two-call protocol 或 capacity table。

讲稿提示：

- 今晚不要承诺 QAAskeR 已经公平比较完成。
- 最稳妥的收口是：主结果已经支持结构覆盖优势，最终论文前要补人审校准。

## 备用问答

**老师问：为什么 Random 看起来也很强？**

答：因为 Random 和 ADVTEST 共享结构化问题空间，所以它是强 internal ablation。我们真正比较的是 coverage-guided ordering 是否比 random ordering 更好。

**老师问：Official-QA fail rate 更低，能说明官方题更好吗？**

答：不能。官方题是 category-level，ADVTEST 是 instance/relation-level，GT 粒度不同，不能直接比较 fail rate。

**老师问：QATest 为什么叫 adapted？**

答：原版依赖旧环境、硬编码模型路径和外部服务 token。我们保留核心搜索/反馈机制，但禁用不可复现或有风险的算子，所以必须叫 adapted。

**老师问：如果 Random-only 有效率更高，我们的方法优势在哪里？**

答：testing 关注总错误空间。Random-only 单题有效率略高，但 exclusive failed-L2 空间小；ADVTEST 的总有效结构失败覆盖仍明显更大。

