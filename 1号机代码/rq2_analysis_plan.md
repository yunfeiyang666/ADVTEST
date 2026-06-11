# 全量数据分析规划 — 对齐论文 6 个 RQ

> 来源: Research Questions Design.pptx + 1号机实验数据

---

## RQ 全景

| RQ | 核心问题 | 当前状态 |
|----|---------|---------|
| **RQ1** | 我们的方法能否自动生成正确答案？ | ⚠️ 需要跑 |
| **RQ2** | 相同预算下能否更快提高覆盖率？ | ✅ 6011帧已完成 |
| **RQ3** | 能否有效检测 ADS 模型错误？ | ❌ 未开始 |
| **RQ4** | 覆盖率提升是否显著带来故障检出提升？ | ❌ 未开始 |
| **RQ5** | 生成的 QA 微调能否提升模型准确率？ | ❌ 未开始 |
| **RQ6** | 能否发现跨帧/跨视角错误？ | ❌ 未开始 |

---

## RQ1: 答案正确性验证

**问题**: Can our method generate correct answers automatically?

### 指标
- Answer accuracy (按 question_type 和 question complexity 分组)
- 跨帧一致性
- 多问一致性

### 需要做的实验
- [ ] 对已有题目，用 NuScenes Ground Truth 验证答案
- [ ] 按 NuScenes 官方分类 (exist/count/status/object/comparison) 分别计算准确率
- [ ] 按复杂度 (zero-hop=L0/L1, one-hop=L2) 分别计算准确率
- [ ] 对不正确的答案进行错误归因: question 本身错误? NL→Cypher 转换错误? 答案计算错误?

### 所需数据
- 生成的 QA 对 (JSONL, 已有)
- NuScenes Ground Truth annotations

### 输出
- Table: accuracy by question_type × complexity
- 错误归因分析表

---

## RQ2: 覆盖效率分析 ✅ (已有数据)

**问题**: 在相同预算下，你的方法能更快地提高覆盖率吗？

### 规模分组

| 分组 | 节点数 | 说明 |
|------|--------|------|
| **Small** (S) | 3–15 | 简单场景 |
| **Medium** (M) | 16–30 | 中等场景 |
| **Large** (L) | ≥31 | 复杂场景 |
| **All** | ≥3 | 全部有效帧 |

### 分析维度 (16个, 每个 × 4 组)

| 维度 | 说明 | 数据源 |
|------|------|--------|
| D1. 覆盖曲线+AUC | 分组 L0/L1/L2 曲线 | 本地 npz |
| D2. 覆盖衰减 | 5段 ΔL2/Q | HDD |
| D3. 题型分类 | NuScenes官方 × L2族 双维度 | HDD |
| D4. 压缩率 | (R1+R2补缺) / total_gaps | HDD |
| D5. 初始覆盖率 | 初始 L0/L1/L2 分布 | 本地 npz |
| D6. R1 vs R2 贡献 | R1结束时覆盖率, R2补缺 | HDD |
| D7. 可扩展性 | Q_to_100% vs nodes log-log 拟合 | 本地 npz |
| D8. 冗余分析 | 1 - Σdelta/Σraw | HDD |
| D9. Timing | 分组 timing 拆解 | HDD |
| D10. 约束质量 | 约束数/类型/过滤率 | HDD JSONL |
| D11. Ego 分析 | ego gap 占比和影响 | HDD |
| D12. 图密度 | edges/nodes vs 效率 | HDD |
| D13. 答案分布 | bool/number/status/object 分布 | HDD JSONL |
| D14. 候选过滤 | candidate_before vs after | HDD JSONL |
| D15. 跨帧分析 | 同 scene 帧间 gap 重叠 | HDD |
| D16. 覆盖饱和 | 95%→100% 长尾代价 | 本地 npz |

### PPT 要求的核心输出
- **Figure**: 覆盖率提升折线图 (Y=覆盖率, X=题数), 含初始覆盖率标注
- **Baselines**: Ours vs Random (Random 暂不做)

---

## RQ3: ADS 模型错误检测

**问题**: Can our method detect ADS model error effectively?

### MUT (Models Under Testing)
| 模型 | 类型 |
|------|------|
| GPT-4V | 通用 LVLM |
| Qwen-VL | 通用 LVLM |
| LLaVA | 通用 LVLM |
| BLIP2 | 通用 LVLM |
| NuScenes-base | 专用微调模型 |
| LingoQA-base | 专用微调模型 |

### 需要做的实验
- [ ] 对每个 MUT, 用生成的 QA 对进行推理
- [ ] 统计每个模型的 error count 和 error rate
- [ ] 按 question_type × complexity 交叉分析
- [ ] Ours vs Random baseline 对比

### 所需数据
- 生成的 QA 对 (已有)
- 各 MUT 的推理输出 (需要跑)

### 输出
- **Figure**: 发现错误数折线图 (Y=错误数, X=题数)
- **Table**: 总错误数分布 (行=模型, 列=question_type × complexity)

---

## RQ4: 覆盖率-故障检出相关性

**问题**: 覆盖率提升是否显著带来故障检出提升？

### 需要做的实验
- [ ] 在不同覆盖率水平 (25%/50%/75%/90%/100%) 下统计检出故障数
- [ ] 绘制覆盖率 vs 故障检出曲线
- [ ] 分析边际递减和拐点

### 前置依赖
- RQ3 的模型推理结果

### 输出
- **Figure**: 折线图 (Y=检出故障数, X=覆盖率%)
- 分析: 边际递减率, 拐点位置

---

## RQ5: 微调效果

**问题**: 用生成 QA 对微调是否提升模型准确率？

### Baselines
| 条件 | 说明 |
|------|------|
| zero-shot | 不微调 |
| few-shot (N) | 用 N 条随机 QA 对 |
| random QA | 随机选题微调 |
| difficult QA | 选困难题微调 |

### 需要做的实验
- [ ] ��数据集微调 vs 不同数据集微调
- [ ] 不同微调量的效果曲线

### 输出
- **Figure**: 柱状图 (各 baseline 准确率对比)
- **Table**: 微调前后准确率

---

## RQ6: 跨帧/跨视角一致性错误

**问题**: 能否发现同场景跨帧错误或跨视角错误？

### 检测逻辑
- 同 scene 不同帧中识别相同 object → 提相同问题 → 比对回答一致性
- 不同视角 (6 相机) 中相同 object → 提相同问题 → 比对回答一致性

### 前置依赖
- RQ3 的推理结果
- 跨帧 object 追踪 (NuScenes annotation token)

### 指标
- cross-frame-error-count
- cross-view-error-count

### 输出
- **Table**: 行=模型, 列=question_type × complexity

---

## 执行优先级

| 阶段 | 内容 | 依赖 |
|------|------|------|
| **现在** | RQ2 全部 16 维度分析 | 1号机恢复 |
| **下一步** | RQ1 答案正确性 | 本地可做 |
| **需要 GPU** | RQ3 模型推理 | 需要部署 6 个 MUT |
| **RQ3 之后** | RQ4 覆盖-故障相关 | RQ3 结果 |
| **最后** | RQ5 微调, RQ6 跨帧 | GPU + RQ3 |

---

## 图表风格 (SE 顶会: ISSTA/ICSE/FSE/ASE)

- **字体**: Times New Roman, 8pt (正文), 9pt (轴标签)
- **分辨率**: 600dpi, PDF 矢量格式
- **尺寸**: 单栏 3.5in, 双栏 7.16in (IEEE/ACM 双栏格式)
- **配色**: 色盲友好 (matplotlib tab10 前 6 色)
- **网格**: 虚线, alpha=0.25
- **图例**: 带框, alpha=0.8
