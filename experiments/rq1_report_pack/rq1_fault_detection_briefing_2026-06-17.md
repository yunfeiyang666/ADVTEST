# RQ1 故障检测实验汇报简稿（2026-06-17）

## 1. 这段时间 RQ1 的核心定位

RQ1 现在不再只看“生成题覆盖了多少场景图 gap”，而是转成更像 software testing 的问题：

> 在相同测试预算下，哪种测试用例生成/选择方法更能暴露 VLM 在自动驾驶场景理解中的错误？

因此主指标从单纯覆盖率，升级为两类：

- 错误检测效率：同样 VLM call 下发现多少 unique failures。
- 结构化错误覆盖：这些失败对应多少 frame-qualified L2 结构项。

这里的关键叙事是：ADVTEST 的优势不是“每一道题一定更容易让模型错”，而是“它把测试预算投向更广的结构空间，因此暴露出更大的失败覆盖面”。

## 2. 为什么要重新整理对照组

早期设置里有一个方法论风险：多个 baseline 实际上复用了 ADVTEST 生成出来的候选池或 coverage footprint，只是在候选池内换排序或做文本变异。

这会导致两个问题：

- 对照组借用了我们的方法能力，不再是独立 baseline。
- coverage 指标会被高估，因为变异题可能继承原题 footprint，但语义未必仍然对应那个结构 gap。

所以后续把实验拆成不同层，不再把所有方法放在一张表里硬比。

## 3. 最终采用的实验分层

### Layer A：结构覆盖内部消融

目的：证明 ADVTEST 的 coverage-guided 选择策略比无反馈策略更会覆盖结构空间。

可比方法：

| 方法 | 角色 | 是否结构覆盖可比 | 说明 |
|---|---|---:|---|
| ADVTEST | proposed method | yes | 覆盖优先、可 adaptive frame switch |
| Random | internal ablation | yes | 在同一结构化问题空间中随机采样，不读取 gap/coverage feedback |
| Template-balanced | internal ablation | yes | 按题型/模板均衡采样 |
| Object-balanced | internal ablation | yes | 按对象参与度均衡 |
| Greedy-L0/L1 | component ablation | yes | 只看对象或一跳关系，用来证明多层覆盖必要 |

当前真实 VLM 主结果主要使用 ADVTEST vs Random 作为严格可比的内部消融。

### Layer B：跨范式故障检测参考

目的：看不同 QA/testing 范式在同样 VLM call 下能暴露多少错误。

| 方法 | 角色 | 是否结构 L2 可比 | 当前处理 |
|---|---|---:|---|
| Official NuScenes-QA | neutral reference | no | 官方类别级 GT，作为中立题集参考 |
| QATest-adapted | external comparison | no | 从官方 NuScenes-QA seed 独立变异，不读 ADVTEST coverage |
| QAAskeR | postponed external comparison | no | 需要主问+follow-up，预算口径复杂，本轮未纳入主表 |

这层只比较 VLM 错误发现效率、重复率、失败类别等，不拿结构 L2 覆盖直接排名。

### Layer C：官方 QA 选择控制（设计层）

这一层计划用于回答：“如果大家都只能从官方 NuScenes-QA 里选题，coverage-aware selector 是否仍然有帮助？”

目前还不是主结果，只作为后续补充方向。

## 4. 预算口径如何统一

我们把两个预算明确拆开：

| 预算 | 含义 | 用途 |
|---|---|---|
| `generation_budget` | 离线生成多少题 | 比较 suite 生成能力、覆盖曲线 |
| `vlm_call_budget` | 实际调用 VLM 多少次 | 比较故障检测能力 |

正式故障检测主表统一使用 VLM call budget：

- ADVTEST、Random、Official-QA、QATest-adapted：每题 1 次 VLM call。
- QAAskeR：一个完整 pair 通常包含主问和 follow-up，至少 2 次 VLM call；因此本轮未放进主表，避免预算不公平。

最终 mPLUG-Owl2 主实验预算是：

- 每方法 1000 次真实 VLM call。
- 四个方法共 4000 次真实推理。
- 没有 mock fallback。

## 5. Ground Truth 粒度边界

这是汇报时最需要主动说明的点。

| 题源 | GT 粒度 | 结构覆盖可比性 |
|---|---|---:|
| ADVTEST / Random | instance 或 relation 级，例如 `car5`、结构链 | 可比 |
| Official NuScenes-QA | category 级，例如 `car`、`yes/no`、数字 | 不可直接比较结构 L2 |
| QATest-adapted | 继承官方 QA 的 category 级 GT | 不可直接比较结构 L2 |

所以不能简单说 “Official-QA fail rate 比 ADVTEST 低，所以它更好/更差”。它们的题目难度、答案粒度和 frame 分布都不同。

## 6. QATest 的处理

我们做了 QATest fidelity audit，结论是早期的 `qatest` 不能直接叫原版 QATest。

现在的处理：

- `qatest_style`：旧的轻量文本扰动版本，只作为 legacy ablation。
- `qatest_adapted`：正式保留的 QATest comparison。

`qatest_adapted` 的边界：

- 只使用官方 NuScenes-QA seed。
- 不读取 ADVTEST candidate pool、uncovered gap、coverage score 或 footprint。
- 保留 QATest 的核心思想：seed pool、候选重试、Rouge-1 过滤、POS-transition 概率、1-4 gram coverage feedback、duplicate rejection。
- 禁用原始代码中依赖旧模型路径、外部服务或泄露 token 的算子。

1000 题生成 audit：

| 方法 | 题数 | Unique | 官方 source 保留 | Frames | Answer mismatch | Boundary violation |
|---|---:|---:|---:|---:|---:|---:|
| qatest_style | 1000 | 1000 | 1000 | 99 | 0 | 0 |
| qatest_adapted | 1000 | 1000 | 723 | 100 | 0 | 0 |

决策：主文使用 `QATest-adapted`，不要声称逐字节复现原始 QATest。

## 7. Random 的定位

Random 不是外部 SOTA baseline，而是内部消融。

它回答的问题是：

> 在相同结构化问题空间、相同 frame order、相同 per-frame cap 下，coverage-guided 顺序是否比随机顺序更有效？

这能避免一个误解：Random 看起来很强，不是因为它是独立强 baseline，而是因为它和 ADVTEST 共享了结构化生成空间。这个设置适合做 ablation，不适合包装成外部方法。

## 8. 真实 VLM 主实验结果

模型：mPLUG-Owl2
运行：四方法各 1000 call，共 4000 条真实推理
耗时：32921.27 秒，约 9.14 小时
mock fallback：0
评分：`token_boundary_v2_frame_qualified_l2`

| 方法 | 角色 | Calls | Wrong / Unique failures | UF/100 | Failed unique L2 | Frames |
|---|---|---:|---:|---:|---:|---:|
| ADVTEST | proposed | 1000 | 981 | 98.1 | 4488 | 20 |
| Random | internal ablation | 1000 | 912 | 91.2 | 2727 | 20 |
| Official-QA | neutral reference | 1000 | 650 | 65.0 | N/A | 67 |
| QATest-adapted | external comparison | 1000 | 637 wrong / 468 independent | 46.8 | N/A | 100 |

ADVTEST vs Random 的严格可比结果：

- 输入覆盖 L2：4508 vs 2818，ADVTEST +1690（+59.97%）。
- unique failures：981 vs 912，ADVTEST +69（+7.57%）。
- failed unique L2：4488 vs 2727，ADVTEST +1761（+64.58%）。

一句话结论：

> ADVTEST 在 raw failure count 上有提升，但最大优势体现在 failed structural coverage，也就是更广泛地暴露了模型在结构关系上的失败。

## 9. Random seed 稳健性检查

为了避免 Random seed 42 偶然偏弱，我们额外跑了 100-call Random seed 43、44。

| 方法 | Seed | Calls | Wrong / Independent failures | Failed unique L2 |
|---|---:|---:|---:|---:|
| ADVTEST | fixed | 100 | 92 | 236 |
| Random | 42 | 100 | 86 | 169 |
| Random | 43 | 100 | 88 | 180 |
| Random | 44 | 100 | 90 | 183 |

Random 三 seed 平均：

- independent failures：88.00，std 1.63。
- failed unique L2：177.33，std 6.02。

ADVTEST 相比 Random 平均：

- independent failures +4.00（+4.55%）。
- failed unique L2 +58.67（+33.08%）。
- 三个 seed 上 ADVTEST 都超过 Random。

解释：failure 数量优势存在但不巨大；结构失败覆盖优势更稳定、更明显。

## 10. Failure audit 做了什么

因为 reviewer 可能会问：“模型错了是否真是视觉/结构错误，还是答案粒度/字符串判分问题？”

所以我们做了两轮 audit。

### 48 行人工 sanity audit

- 48 行 sampled failure。
- 33 行 valid visual/structural failure（68.8%）。
- 15 行属于边界情况。
- Random-only validity rate 略高于 ADVTEST-only：75.0% vs 66.7%。

解释：这不能说明 Random 更好，因为 Random 的 exclusive failed L2 空间小得多。

小样本外推：

- ADVTEST-only failed L2：3070 * 66.7% ≈ 2047。
- Random-only failed L2：1309 * 75.0% ≈ 982。
- ADVTEST 约为 Random 的 2.08 倍。

### 400 行 assisted audit

后来扩成 400 行 stratified assisted audit：

- ADVTEST-only L2：100 行。
- Random-only L2：100 行。
- Shared L2 pairs：100 pair，即 200 行。
- assisted valid：311 / 400 = 77.8%。
- uncertain：25。

估计结果：

| bucket | sample rows | valid yes | uncertain | valid rate | estimated valid total |
|---|---:|---:|---:|---:|---:|
| advtest_only_l2 | 100 | 70 | 6 | 70.0% | 2149.0 |
| random_only_l2 | 100 | 87 | 3 | 87.0% | 1138.8 |
| shared_l2_advtest | 100 | 77 | 8 | 77.0% | 1091.9 |
| shared_l2_random | 100 | 77 | 8 | 77.0% | 1091.9 |

ADVTEST-only vs Random-only：

- estimated valid total difference：+1010.2。
- Wilson conservative lower-minus-upper：+647.3。

注意：400 行是 deterministic assisted review，不是最终纯人工审阅。我们已经生成 100 行 human adjudication pack，等待填 `human_*` 后校准 assisted label 的一致率。

## 11. 当前产物和可复盘性

已经固化的处理链：

- 真实 1000-call 主实验：`experiments/rq1_mplug_call1000/`
- paper-ready report pack：`experiments/rq1_report_pack/`
- Random seed variance：`experiments/rq1_mplug_random_variance/`
- QATest fidelity audit：`experiments/rq1_qatest_fidelity_audit/`
- QATest-adapted generation audit：`experiments/rq1_qatest_adapted/`
- Failure audit large pack：`experiments/rq1_failure_audit_large/`

最后一轮 artifact consistency check：

- large audit rows：400。
- large audit label counts：yes 311 / no 64 / uncertain 25。
- human adjudication rows：100。
- human reviewed rows：0。
- human pending rows：100。
- status：ok。

## 12. 今晚建议怎么讲

### 先讲问题

“我们不是在比普通 VQA accuracy，而是在比测试方法发现 VLM 错误的能力。这个任务没有完全同任务 SOTA，所以实验必须分层。”

### 再讲对照组

“Random 是内部消融，验证 coverage-guided selection 是否优于随机 selection；Official-QA 和 QATest-adapted 是外部参考，不能拿 structural coverage 直接和我们比。”

### 再讲预算

“正式故障检测统一用 VLM call budget。生成题过程不消耗 VLM call；QAAskeR 因为需要主问和 follow-up，本轮先不进入主表。”

### 再讲结果

“ADVTEST 在 1000-call mPLUG-Owl2 上发现 981 个 unique failures，Random 是 912；更关键的是 failed unique L2 是 4488 vs 2727，结构失败覆盖提升 64.58%。”

### 最后主动说限制

“我们承认 instance-level GT 比官方 QA 更严格，因此 external rows 只作参考；我们也做了 failure audit，当前 assisted audit 支持 ADVTEST 的有效结构失败总量优势，但 100 行人工校准还未完成。”

## 13. 可以放到 PPT 的一句话结论

> 在相同 VLM 调用预算下，ADVTEST 相比随机结构化采样不仅发现更多 mPLUG-Owl2 错误，更显著地扩大了被触发失败的结构关系覆盖范围；其优势主要体现为 coverage-breadth effect，而不是单题有效率更高。

## 14. 老师可能问的问题和回答

**Q1：为什么不直接和 Official NuScenes-QA 比 fail rate？**
A：官方 QA 是 category-level GT，我们的问题是 instance/relation-level GT，难度和答案粒度不同。Official-QA 可以作为 neutral reference，但不能作为结构覆盖 head-to-head baseline。

**Q2：Random 为什么不是外部 baseline？**
A：Random 和 ADVTEST 共享结构化生成空间，比较的是排序/选择策略，所以它是 internal ablation。外部方法必须独立生成或从官方 seed 出发。

**Q3：QATest 是不是原版？**
A：不是逐字节原版。原版有旧环境、硬编码模型路径和外部服务 token 风险。我们实现的是 QATest-adapted，保留核心搜索/反馈思想，并明确命名。

**Q4：为什么 QAAskeR 没进主表？**
A：QAAskeR 的主问+follow-up 至少消耗两次 VLM call，预算口径和一题一调用方法不同。先把主表建立在同一 VLM call 预算上，QAAskeR 后续作为单独 capacity 表或双调用协议补充。

**Q5：如果 Random 单题有效率更高，为什么还说我们更好？**
A：testing 关注同预算下暴露的总错误空间。Random-only 样本有效率略高，但它覆盖的 exclusive failed L2 总量小；ADVTEST 的结构空间更大，估计有效结构失败总量仍明显更高。
