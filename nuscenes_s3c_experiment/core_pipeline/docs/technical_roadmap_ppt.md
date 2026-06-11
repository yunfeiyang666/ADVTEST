# 技术路线 PPT 素材 — S3C 覆盖率驱动 VQA 测试生成

> 本文档为技术路线PPT提供层次结构素材，涵盖系统架构、模块关系和数据流。

---

## 一、总体架构（三层）

```
┌─────────────────────────────────────────────────────────────┐
│                   覆盖率驱动闭环系统                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐     │
│  │ 问题生成层    │──▶│ VQA 验证层   │──▶│ 覆盖率评估层  │     │
│  │(模板/LLM)    │   │(Cypher+Neo4j)│   │(L0/L1/L2)    │     │
│  └──────┬───────┘   └──────────────┘   └──────┬───────┘     │
│         │                                      │             │
│         └──────────── 反馈闭环 ◀────────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

### PPT 要点
- **问题生成层**: 模板确定性生成 + LLM增强生成 双通道
- **VQA 验证层**: 自然语言→Cypher→Neo4j→答案，多层Retry策略
- **覆盖率评估层**: L0(节点)/L1(边)/L2(两跳路径) 三级覆盖率
- **闭环**: 覆盖率缺口 → 有针对性的问题生成 → 验证 → 更新覆盖率

---

## 二、模块详细结构

### 2.1 场景图 (Scene Graph)

```
NuScenes 标注数据
      │
      ▼
┌─────────────────────────────┐
│  场景图生成                  │
│  generate_selected_scenes   │
│  import_single_scene_to_neo4j│
└─────────┬───────────────────┘
          │
          ▼
┌─────────────────────────────┐
│  场景图 JSON                 │
│  ├─ nodes: [ego, car1, ...]  │
│  │  ├─ unique_id, type       │
│  │  ├─ status, category      │
│  │  └─ translation, size     │
│  └─ edges: [...]             │
│     ├─ source → target       │
│     ├─ direction_8_ego       │
│     ├─ angle_matches_ego[]   │
│     ├─ distance              │
│     └─ predicates[]          │
└─────────────────────────────┘
```

### 2.2 问题生成层（双通道）

```
            问题生成层
           ┌────┴────┐
     通道A             通道B
  模板确定性生成      LLM增强生成
           │               │
    ┌──────┴──────┐   ┌───┴────────────┐
    │template_    │   │coverage_driven_│
    │library.py   │   │generator.py    │
    │(83模板,4级) │   │(LLM + 缺口分析)│
    └──────┬──────┘   └────────────────┘
           │
    ┌──────┴──────┐
    │template_    │
    │filler.py    │
    │(确定性填充)  │
    └──────┬──────┘
           │
    ┌──────┴──────────┐
    │coverage_driven_ │
    │template_        │
    │generator.py     │
    │(覆盖率目标驱动)  │
    └─────────────────┘
```

#### 模板库四级层次结构 (template_library.py)

```
Level 1: 覆盖率级别 (L0 / L1 / L2)
  │
  └─ Level 2: 问题类型 (exist / count / object / status / comparison)
       │
       └─ Level 3: 大样式 (major pattern)
            │    例: "Is there a {TYPE}?" / "How many {TYPE}s?"
            │
            └─ Level 4: 变体 (variant)
                 例: "Is there a {STATUS} {TYPE}?"
                      "Is there a {TYPE} to the {DIR}?"

统计: L0=24模板, L1=42模板, L2=17模板, 共83模板
```

#### 确定性问题生成流程

```
覆盖率缺口 (CoverageGoal)
      │
      ▼
1. 提取缺口 → 未覆盖节点/边/路径
      │
      ▼
2. 预算分配 → L0:L1:L2 按差距比例分配
      │
      ▼
3. 候选生成 → 模板填充 + 答案计算 (无LLM)
      │
      ▼
4. 贪心选择 → 优先覆盖新元素、保持模板多样性
      │
      ▼
5. 输出 → [{question, answer, template_id, covered_elements}]
```

### 2.3 VQA 验证层 (vqa_pipeline)

```
自然语言问题
      │
      ▼
┌─────────────────┐
│ 问题规范化       │  question_normalizer.py
│ (同义词/格式统一) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Cypher 生成      │  llm_client.py (DeepSeek-R1)
│ ├─ 直接生成      │
│ └─ IR→Cypher    │  ir_patterns.py
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 覆盖率改写       │  cypher_coverage_rewriter.py ★新
│ RETURN追加       │  → _cov_N_id / _cov_N_dir
│ 节点/边元数据    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Neo4j 执行       │  neo4j_client.py
│ (改写版优先,     │
│  失败回退原始版)  │
└────────┬────────┘
         │
         ├─ 覆盖率提取 → CoverageInfo (节点/边/两跳)
         │
         ▼
┌─────────────────┐
│ 答案生成+格式化   │  answer_formatter.py
│ (LLM翻译结果)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 多层Retry策略    │
│ 1. ego+宽松匹配  │
│ 2. 语法修正      │
│ 3. source+宽松   │
│ 4. ego+精确      │
│ 5. source+精确   │
└─────────────────┘
```

### 2.4 覆盖率评估层

```
┌─────────────────────────────────┐
│  覆盖率三级体系                  │
│                                 │
│  L0 节点覆盖                    │
│  ├─ 定义: 问题是否涉及该对象     │
│  ├─ 粒度: unique_id             │
│  └─ 目标: ≥80%                  │
│                                 │
│  L1 边覆盖                      │
│  ├─ 定义: 问题是否涉及该空间关系  │
│  ├─ 粒度: (source, direction,   │
│  │         target)              │
│  └─ 目标: ≥50%                  │
│                                 │
│  L2 两跳路径覆盖                 │
│  ├─ 定义: 问题是否涉及两跳链     │
│  ├─ 粒度: (n1, n2, n3)         │
│  └─ 目标: ≥30%                  │
└─────────────────────────────────┘
```

### 2.5 闭环控制器 (loop_controller.py)

```
┌──────────────────────────────────────────┐
│           CoverageLoopController          │
│                                          │
│  for iteration in 1..max_iterations:     │
│    │                                     │
│    ├─ 1. 评估当前覆盖率                   │
│    │     └─ UnifiedCoverageStats          │
│    │                                     │
│    ├─ 2. 缺口分析                        │
│    │     └─ GapAnalyzer.decide_next()    │
│    │         → focus_level, focus_items   │
│    │                                     │
│    ├─ 3. 问题生成                        │
│    │     └─ CoverageDrivenTemplate-      │
│    │        Generator.generate()  ★新     │
│    │        (模板驱动, 无需LLM)           │
│    │                                     │
│    ├─ 4. VQA验证 (可选)                  │
│    │     └─ VQAPipeline.process_question │
│    │                                     │
│    ├─ 5. 更新覆盖率                      │
│    │     └─ _update_coverage_from_qa()   │
│    │                                     │
│    └─ 6. 检查目标 → 达标则提前退出        │
│                                          │
│  输出:                                   │
│    ├─ all_questions.json                 │
│    ├─ coverage_final.json                │
│    ├─ iteration_history.json             │
│    └─ report.txt                         │
└──────────────────────────────────────────┘
```

---

## 三、关键创新点

### 3.1 Cypher 覆盖率改写 (第二轮改写)

```
原始 Cypher (LLM生成):
  MATCH (ego)-[r]->(obj) WHERE ... RETURN obj.type LIMIT 1

         │  CypherCoverageRewriter.rewrite()
         ▼

改写后 Cypher:
  MATCH (ego)-[r]->(obj) WHERE ...
  RETURN obj.type,
         ego.unique_id AS _cov_0_id,     ← 节点ID
         r.direction_8_ego AS _cov_1_dir, ← 边方向
         obj.unique_id AS _cov_2_id       ← 节点ID
  LIMIT 1

优势:
  ✗ 旧方案: 用regex解析Cypher文本推测涉及的节点/边 → 不准确
  ✓ 新方案: Cypher自身返回涉及元素 → 从查询结果直接提取 → 100%准确
```

### 3.2 确定性模板生成 vs LLM生成

```
┌──────────────────┬──────────────────┐
│   模板确定性生成   │    LLM增强生成    │
├──────────────────┼──────────────────┤
│ 速度: ~0.01s/题  │ 速度: ~3-5s/题   │
│ 答案: 100%正确   │ 答案: 需要验证    │
│ 覆盖: 可精确控制  │ 覆盖: 概率性      │
│ 多样性: 模板数限制│ 多样性: 无限      │
│ 成本: 零API费用  │ 成本: API调用费   │
│ 适用: 批量覆盖   │ 适用: 长尾/特殊   │
└──────────────────┴──────────────────┘
```

### 3.3 覆盖率驱动 vs 随机生成

```
随机生成:
  第1轮: L0=40%, L1=5%,  L2=1%
  第2轮: L0=55%, L1=8%,  L2=2%   ← 提升缓慢，重复覆盖多
  第3轮: L0=60%, L1=10%, L2=3%

覆盖率驱动:
  第1轮: L0=70%, L1=15%, L2=5%   ← 首轮即高覆盖（优先未覆盖元素）
  第2轮: L0=90%, L1=35%, L2=12%  ← 缺口分析精准填补
  第3轮: L0=95%, L1=50%, L2=20%  ← 快速收敛到目标
```

---

## 四、数据流总览

```
NuScenes数据集
      │
      ▼
场景图JSON ──────────────────────────┐
      │                              │
      ▼                              │
Neo4j图数据库                        │
      │                              │
      ▼                              ▼
┌─────────────┐            ┌─────────────────┐
│VQA Pipeline │            │模板驱动生成器     │
│(LLM+Cypher) │            │(确定性, 无LLM)   │
└──────┬──────┘            └────────┬────────┘
       │                            │
       ▼                            ▼
┌──────────────────────────────────────┐
│        覆盖率闭环控制器               │
│  CoverageLoopController              │
│  ├─ 生成 → 验证 → 评估 → 反馈       │
│  └─ 直到 L0≥80%, L1≥50%            │
└──────────────────┬───────────────────┘
                   │
                   ▼
         最终VQA测试集
         + 覆盖率报告
```

---

## 五、文件清单

| 模块 | 文件 | 说明 |
|------|------|------|
| **场景图** | `config.py` | 全局配置（类型/方向/距离） |
| | `generate_selected_scenes_improved.py` | 场景图生成 |
| | `import_single_scene_to_neo4j.py` | 导入Neo4j |
| **问题生成** | `qa_generator_v2/template_library.py` | 83模板四级层次库 |
| | `qa_generator_v2/template_filler.py` | 确定性模板填充+答案 |
| | `qa_generator_v2/coverage_driven_template_generator.py` | 覆盖率驱动模板生成器 |
| | `qa_generator_v2/coverage_driven_generator.py` | LLM增强生成器 |
| **VQA验证** | `vqa_pipeline/pipeline.py` | VQA主流程 |
| | `vqa_pipeline/llm_client.py` | LLM客户端(Cypher生成) |
| | `vqa_pipeline/cypher_coverage_rewriter.py` | Cypher覆盖率改写器 ★新 |
| | `vqa_pipeline/neo4j_client.py` | Neo4j查询执行 |
| | `vqa_pipeline/answer_formatter.py` | 答案格式化 |
| **覆盖率** | `coverage_loop/loop_controller.py` | 闭环控制器 |
| | `coverage_loop/gap_analyzer.py` | 缺口分析 |
| | `coverage_loop/unified_coverage.py` | 统一覆盖率数据结构 |
| | `calculate_coverage_precise.py` | 精确覆盖率计算 |

---

## 六、演示数据参考

- 场景: `scene-0103` frame 25/38
- 场景图节点数: ~48
- 场景图边数: ~1122
- 模板库: 83个 (L0:24, L1:42, L2:17)
- 问题类型: exist/count/object/status/comparison
- 方向系统: 8方向 (front/front-left/left/back-left/back/back-right/right/front-right)
