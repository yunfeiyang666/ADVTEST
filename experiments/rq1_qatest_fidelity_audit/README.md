# QATest 基线真实性审计

## 审计目标

确认当前 RQ1 中名为 `qatest` 的方法是否等价于 QATest 原始方法，并确定正式
论文实验应采用的接入方式。

本阶段只读代码，不调用 VLM，不运行长实验。

## 结论

当前 `official_qa_experiment.py` 中的实现不能直接标记为原版 QATest。它是一个
确定性的 QATest 风格文本变异基线，应改称 `QATest-style`。

正式实验建议新增 `QATest-adapted`：

- 使用官方 NuScenes-QA 作为独立 seed；
- 保留 QATest 的迭代 seed pool；
- 保留 DTMC 词性转移概率与 n-gram 覆盖反馈；
- 保留 Rouge 质量阈值、重复过滤和算子重试；
- 使用可离线、无凭据、可复现的变异算子；
- 明确说明这是面向视觉问答数据的适配版，不声称逐字节复现原 Python 3.6 环境。

当前 `QATest-style` 可以保留为简化消融，但不应作为唯一的外部 QATest
对照组。

## 原始 QATest 的算法组成

原始仓库 `QATest-main/main.py` 包含以下关键环节：

1. 从 seed pool 按同源问题使用次数的倒数加权抽取 batch。
2. 对每个 seed 尝试最多 10 个变异算子。
3. 拒绝与原问题相同的结果。
4. 对同源问题执行 Rouge 重复过滤。
5. 只保留 Rouge-1 F1 大于 `0.5` 的候选。
6. 使用 POS-DTMC 句子概率和 1 至 4-gram 新覆盖评估候选。
7. 将概率或语法覆盖最优的候选放回 seed pool，继续迭代。

证据位置：

- seed batch：`QATest-main/main.py:57`
- 生成与重试：`QATest-main/main.py:74`
- Rouge 质量阈值：`QATest-main/main.py:93`
- 双指标回灌：`QATest-main/main.py:114`
- 主迭代：`QATest-main/main.py:165`
- DTMC 与 n-gram：`QATest-main/question_parse.py`

原始代码提供 10 个变异算子：

1. keyboard mistake
2. OCR mistake
3. spelling mistake
4. synonym replacement
5. adverbial preposition
6. contextual word insertion
7. back translation
8. entity replacement
9. Wh-pronoun contraction
10. double question mark

## 当前实现与原始实现的差异

当前正式 suite builder 位于
`1号机代码/DATA_new/analysis/rq1_error_detection/official_qa_experiment.py`。

它具有以下行为：

- 按 cycle 打乱官方 seed；
- 使用 `cycle % 7` 依次选择七个本地字符串变异；
- 对最终问题文本去重；
- 不计算 POS-DTMC；
- 不计算 1 至 4-gram 覆盖；
- 不使用 Rouge `0.5` 质量阈值；
- 不维护或回灌迭代 seed pool；
- 不执行每个 seed 最多 10 次的候选重试；
- 输出 provenance，并正确保持官方 source ID。

因此它只覆盖 QATest 的“文本扰动”表层，没有复现 QATest 的搜索与反馈核心。

仓库中的另一个旧模块 `selectors_qatest.py` 也不适合作为正式实现：

- 它指向 `baselines/QATest`，与当前原始代码目录 `QATest-main` 不一致；
- 它尝试导入原始算子，但跳过需要模型或在线服务的算子 6、7、8；
- 它按本项目 template family 抽样，这不是原 QATest 的 seed-pool 策略；
- 当前独立 Official-QA pipeline 并未调用它。

## 安全与环境问题

原始 `question_trans.py` 含有一个硬编码的第三方服务令牌。该令牌不得复制、
提交到新代码或用于实验，应视为已暴露并进行轮换。

原始环境固定为：

- Python 3.6
- PyTorch 1.8
- Transformers 4.11
- NLTK 3.6
- nlpaug 1.1.7

三个算子还有不可移植依赖：

- contextual insertion 使用硬编码 Windows BERT 路径；
- back translation 使用硬编码 Windows WMT 路径；
- entity replacement 依赖 TagMe 在线服务和令牌。

直接运行原仓库会引入旧环境、模型路径、外部服务和凭据风险，不应成为默认
正式方案。

## 三种接入路线

### 路线 A：继续当前 QATest-style

优点：

- 已实现；
- 完全离线；
- 生成速度快；
- 容易达到 1000 题。

缺点：

- 缺少原方法的核心搜索逻辑；
- 不能在论文中无修饰地称为 QATest；
- 对比说服力较弱。

用途：保留为简化文本扰动消融。

### 路线 B：QATest-adapted，推荐

实现可移植的 QATest 算法核心：

- 官方 NuScenes-QA 独立 seed；
- deterministic seed batch；
- POS-DTMC 和 1 至 4-gram 反馈；
- Rouge 质量与同源重复过滤；
- 10 次候选重试；
- 迭代 seed 回灌；
- 使用七个无凭据离线算子。

对于原来依赖大模型或在线服务的三个算子，正式报告中明确标为因可复现性与
安全边界而禁用。该方法名必须是 `QATest-adapted`。

优点：

- 保留论文方法的主要算法思想；
- 不依赖泄露令牌或旧 GPU 环境；
- 可纳入现有 Git、manifest 和固定预算体系。

缺点：

- 不是原始十算子环境的逐字节复现；
- 需要新增实现、测试和算子分布审计。

### 路线 C：隔离运行原始 Python 3.6 实现

需要建立旧 Conda 环境、下载 BERT/WMT 模型，并替换 TagMe 凭据或禁用该算子。

优点：最接近原始代码。

缺点：

- 环境陈旧且难以维护；
- 原始硬编码路径不能直接运行；
- 在线实体服务不可复现；
- 即使禁用问题算子，也已经不是未经修改的原版。

不推荐作为主实验路线，可作为补充复现尝试。

## 预算口径

QATest 的题目生成是离线过程，不消耗 VLM-call budget。

正式比较时：

- `generation_budget=1000` 控制生成套件规模；
- 每道生成题在评测阶段消耗一次 VLM call；
- Table B 仍按各方法相同的实际 VLM calls 比较；
- 生成耗时和候选尝试次数作为额外成本报告；
- 被质量过滤拒绝的候选不消耗 VLM call，但计入生成开销。

## 下一步实现边界

下一阶段应新增独立的 `qatest_adapted.py`，不要继续扩张
`official_qa_experiment.py`。

模块边界：

- `QATestSeed`：官方题目及迭代状态；
- `PortableMutationOperators`：七个离线算子；
- `QATestCoverageModel`：POS-DTMC 和 n-gram 反馈；
- `QATestGenerator`：batch、重试、过滤、回灌和预算；
- provenance adapter：输出当前实验协议要求的字段。

必须先用小型确定性测试证明：

- 同一 seed 和配置输出一致；
- Rouge 阈值会拒绝过度变异；
- 重复候选不会进入套件；
- 高语法覆盖候选会被回灌；
- 1000 题预算不会被突破；
- 不读取 ADVTEST candidate pool 或 coverage state。
