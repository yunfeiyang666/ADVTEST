# RQ1 Baseline 与实验设置存疑点记录（2026-06-11）

## 当前优先级

短期目标不是立刻定死 baseline，而是先把完整流程跑通：

1. 固定预算问题集生成；
2. 不同方法输出同等 budget 的 question suite；
3. suite 可送入真实 VLM；
4. VLM 输出可自动判错；
5. 统计 unique failures / failure gaps / coverage proxy；
6. 全流程可复现实验日志与结果表。

baseline 细节后续与老师讨论后再收敛。

## 可作为相关工作 / SOTA 对照的方向

目前看，完全同任务的“自动驾驶 VLM 场景图 gap 主动测试”方法不多，可能没有一个直接一一对应的 SOTA。因此 baseline 需要分层组织。

### 1. 自动驾驶 VQA / VLM Benchmark 类

这些更适合作为相关数据集、任务背景或 evaluation protocol 参考，不一定能直接作为测试生成 baseline：

- NuScenes-QA：基于 nuScenes 的视觉问答数据集，可作为问题形式和数据来源参考。
- DriveLM / Graph VQA for autonomous driving：强调驾驶场景中的图式推理、规划相关问答，可作为任务动机和评测维度参考。
- Talk2BEV：语言与 BEV 表征结合的自动驾驶理解任务，可作为语言-场景结构结合的相关工作。
- LingoQA / DriveBench / 多模态驾驶问答 benchmark：可作为 VLM 在驾驶场景评估的相关 benchmark。

这些工作通常评估模型能力，而不是主动生成测试用例发现模型错误。

### 2. QA 系统测试 / Metamorphic Testing 类

这些可作为“QA 测试方法”的 SOTA-ish 对照，但任务域不完全一致：

- QATest：偏向 QA 系统的文本扰动 / metamorphic testing。
- QAAskeR：递归提问、follow-up question、metamorphic relation 类方法。

问题：它们主要做语义变形，不理解自动驾驶场景图、object relation、gap coverage；若直接用于本任务可能很弱。若使用我们的候选池和 coverage metadata，又会被显著增强。

### 3. 通用 VLM / VQA robustness 测试类

可调研是否有：

- VQA robustness testing；
- adversarial question generation；
- scene graph based VQA testing；
- multimodal metamorphic testing；
- VLM hallucination / consistency evaluation。

这些可能比 QATest/QAAskeR 更接近，但仍需确认是否支持自动驾驶场景和结构化 gap。

## 目前 baseline 设置的核心存疑

### 疑问 1：当前 Random 是否过强？

当前 Random 实际上是从 ADVTEST 已生成的高质量 candidate pool 中随机排序/采样。因此它不是 raw random generation，而是：

> Random ordering over ADVTEST-generated candidate pool

这会显著抬高 Random，导致 ADVTEST 相比 Random 的优势不明显。

需要后续区分：

- Raw Random Generation：从原始 object / relation / template 空间随机生成；
- Template Uniform：均匀模板采样；
- Gap Uniform：均匀 gap 采样；
- ADVTEST-pool Random Ordering：当前版本，用于排序消融。

### 疑问 2：offline coverage proxy 是否高估 baseline？

当前 fixed-budget 实验主要基于 metadata footprint 计算 L2 coverage。问题是：

- Random/QATest/QAAskeR 只要继承了 coverage metadata，就会被算作覆盖；
- mutated/follow-up question 即使语义变差，也可能保留原始 footprint；
- 这不等价于真实 VLM 错误发现。

最终主实验必须转向真实 VLM failure detection。

### 疑问 3：QATest / QAAskeR baseline 是否借用了我们的方法能力？

当前 adapted 版本大致是：

- 从我们的候选问题中选问题；
- 对文本做 mutation 或 follow-up；
- 继承原始 coverage footprint。

这使它们不再是纯原始 SOTA，而是“ADVTEST candidate pool + SOTA-style mutation”。

后续论文中需要明确区分：

- QATest-original / QAAskeR-original：尽量忠实原方法，不使用我们的 gap priority 和 candidate pool；
- QATest-adapted / QAAskeR-adapted：允许在相同 seed question 上做迁移适配，但不能使用隐藏 coverage label 或我们的排序分数。

### 疑问 4：我们的方法优势到底应该体现在哪里？

当前结果显示排序优势存在但不够大。可能真正优势不在单纯“同一候选池排序”，而在：

- scene-aware gap generation；
- safety-critical relation prioritization；
- adaptive frame/question budget allocation；
- real VLM failure discovery；
- 去重和覆盖多样性。

因此最终实验不应只报告 offline L2 coverage，还应报告真实错误发现效率。

## 建议的实验分层

### Layer A：生成能力 baseline

比较谁能生成更有价值的问题：

- Raw Random Generator；
- Template Uniform；
- Gap Uniform；
- heuristic generator；
- ADVTEST generator。

### Layer B：排序能力 baseline

在同一候选池下比较排序策略：

- Random ordering；
- template-balanced ordering；
- coverage-greedy ordering；
- ADVTEST ranking；
- ablation：w/o risk score, w/o diversity, w/o adaptive budget。

### Layer C：真实 VLM 错误发现 baseline

最终主表应比较固定 VLM query budget 下：

- unique failures；
- failure / question；
- unique failure-related L2 gaps；
- safety-critical failures；
- answer consistency / hallucination rate。

## 当前流程优先事项

1. 保持当前 fixed-budget runner 可复现；
2. 把 cap=50/100/150 的 suite 生成流程跑通；
3. 让所有 suite 可以送入 VLM evaluator；
4. 先跑小规模真实 VLM trial，验证判错链路；
5. 再与老师讨论最终 baseline 命名和是否保留 QATest/QAAskeR。
