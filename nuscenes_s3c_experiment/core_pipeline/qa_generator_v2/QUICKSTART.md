# 快速开始 - 覆盖率驱动的LLM QA生成

## 核心理念

**全部使用LLM** + **覆盖率驱动** = 动态、智能、完善的测试集

```
NuScenesQA原题 → 覆盖率分析 → 识别缺口 → LLM生成针对性问题 → 验证覆盖率提升 → 迭代
```

## 5分钟快速开始

### 步骤1: 安装依赖

```bash
pip install openai anthropic requests
```

### 步骤2: 配置API Key

```python
# 方式1: 环境变量
export OPENAI_API_KEY="sk-..."

# 方式2: 代码中配置（见下面示例）
```

### 步骤3: 运行Pipeline

```python
from integrated_pipeline import IntegratedQAPipeline
from llm_client import OpenAIClient

# 1. 创建LLM客户端
llm_client = OpenAIClient(api_key="sk-...")

# 2. 创建Pipeline
pipeline = IntegratedQAPipeline(llm_client)

# 3. 运行完整流程
pipeline.run_full_pipeline(
    scene_graph_path="E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json",
    nuscenes_qa_path="E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json",
    output_dir="E:/Project/ADVTEST/nuscenes_s3c_experiment/output/llm_qa_generation",
    iterations=3,  # 迭代3次
    questions_per_iter=20  # 每次生成20个问题
)
```

**就这么简单！** Pipeline会自动:
1. 分析覆盖率缺口
2. LLM生成针对性问题
3. 验证覆盖率提升
4. 保存所有结果和报告

## 命令行使用

```bash
python integrated_pipeline.py \
  --scene-graph scene-0103_frame38_scene_graph.json \
  --nuscenes-qa NuScenes_val_questions.json \
  --output-dir ./output \
  --llm-type openai \
  --api-key sk-... \
  --iterations 3 \
  --questions-per-iter 20
```

## 输出文件

运行完成后，在输出目录会生成:

```
output/
├── coverage_iter0.json          # 初始覆盖率
├── qa_iter1.json                # 第1轮生成的问题
├── coverage_iter1.json          # 第1轮后的覆盖率
├── qa_iter2.json                # 第2轮生成的问题
├── coverage_iter2.json          # 第2轮后的覆盖率
├── qa_iter3.json                # 第3轮生成的问题
├── coverage_iter3.json          # 第3轮后的覆盖率
├── qa_final_all.json            # 所有生成的问题汇总
├── coverage_final.json          # 最终覆盖率
├── generation_stats.json        # 生成统计
└── pipeline_report.txt          # 完整报告
```

## 核心优势

### 1. 智能覆盖率分析 🎯

系统自动识别:
- **低覆盖对象**: 很少被问到的对象
- **缺失关系**: 存在但未被测试的空间关系
- **稀有模式**: 特定类型+状态组合、特定方向等

### 2. 针对性问题生成 💡

LLM根据覆盖率缺口动态生成:
- 问题聚焦于低覆盖区域
- 自然流畅的表达
- 符合NuScenesQA风格

### 3. 迭代优化 🔄

```
第1轮: 识别初始缺口 → 生成20个问题 → 覆盖率从0%提升到30%
第2轮: 识别新缺口 → 生成20个问题 → 覆盖率从30%提升到50%
第3轮: 识别剩余缺口 → 生成20个问题 → 覆盖率从50%提升到65%
```

### 4. 可追溯性 📊

每个问题都标记了:
- 生成原因（填补哪个缺口）
- 涉及的对象和关系
- 相机视角信息
- 是否需要时序信息

## 高级使用

### 只生成特定类型的缺口

```python
# 只关注低覆盖对象
qa_pairs = generator.generate_from_coverage_gaps(
    scene_data,
    coverage_analysis,
    target_count=50,
    focus_areas=["low_object"]  # 只生成低覆盖对象的问题
)

# 只关注缺失关系
qa_pairs = generator.generate_from_coverage_gaps(
    scene_data,
    coverage_analysis,
    target_count=50,
    focus_areas=["missing_relations"]  # 只生成空间关系问题
)
```

### 使用不同的LLM

```python
# GPT-4 (最高质量)
from llm_client import OpenAIClient
llm_client = OpenAIClient(api_key="sk-...", model="gpt-4")

# GPT-3.5 (更便宜)
llm_client = OpenAIClient(api_key="sk-...", model="gpt-3.5-turbo")

# Claude (高质量替代)
from llm_client import ClaudeClient
llm_client = ClaudeClient(api_key="sk-...")

# 本地Ollama (免费)
from llm_client import OllamaClient
llm_client = OllamaClient(model="llama3")
```

### 调整生成参数

```python
llm_client = OpenAIClient(
    api_key="sk-...",
    model="gpt-4",
    temperature=0.9,  # 更高的创造性
    max_tokens=800    # 更长的回答
)
```

## 工作流程详解

### 阶段1: 覆盖率分析

```python
coverage = {
    "object_coverage": {
        "car1": 5,      # 被问了5次
        "car2": 2,      # 被问了2次
        "car3": 0,      # 从未被问 ← 低覆盖
    },
    "relation_coverage": {
        "car1-front->car2": 3,
        "car1-left->car3": 0,  # ← 缺失关系
    },
    "pattern_coverage": {
        "moving_car": 10,
        "parked_pedestrian": 1,  # ← 稀有模式
    }
}
```

### 阶段2: LLM生成问题

针对`car3`（低覆盖对象）:
```
Prompt → LLM → {
  "question": "Are there any cars to the front of car3?",
  "answer": "yes",
  "target_objects": ["car3"],
  ...
}
```

针对`car1-left->car3`（缺失关系）:
```
Prompt → LLM → {
  "question": "What is to the left of car1?",
  "answer": "car3",
  "reference_objects": ["car1"],
  "directions": ["left"],
  ...
}
```

### 阶段3: 更新覆盖率

```python
# 生成后更新
coverage["object_coverage"]["car3"] += 1  # 0 → 1
coverage["relation_coverage"]["car1-left->car3"] += 1  # 0 → 1
```

### 阶段4: 迭代

重复步骤1-3，直到覆盖率达标或达到最大迭代次数。

## 与模板生成器对比

| 特性 | 模板生成器 | 覆盖率驱动LLM |
|------|------------|---------------|
| 速度 | ⚡ 极快 | 🐌 较慢(LLM调用) |
| 成本 | 💰 免费 | 💵 有API费用 |
| 问题质量 | ⭐⭐ 固定模板 | ⭐⭐⭐ 自然多样 |
| 覆盖率优化 | ❌ 随机生成 | ✅ 智能针对性 |
| 适用场景 | 快速生成大量基础题 | 完善测试集、填补缺口 |

## 推荐工作流

```
1. 使用coverage pipeline分析NuScenesQA覆盖率
   ↓
2. 使用模板生成器快速生成基础问题集 (可选)
   ↓
3. 使用覆盖率驱动LLM填补缺口
   ↓
4. 迭代优化直到覆盖率达标
   ↓
5. 用完善的测试集测试CV模型
```

## 成本估算

以GPT-4为例:
- 每个问题约需2次API调用（生成问题+答案）
- 每次调用约500 tokens
- GPT-4价格: $0.03/1K input tokens, $0.06/1K output tokens
- **估算**: 每个问题约 $0.03-0.05

生成100个问题约 **$3-5**

使用GPT-3.5可降低90%成本。

## 故障排查

### Q: LLM生成的JSON格式不对？

```python
# 增加重试逻辑
for attempt in range(3):
    qa_json = _llm_generate_qa_pair(prompt)
    if qa_json:
        break
```

### Q: 覆盖率提升不明显？

- 增加每次迭代的问题数
- 调整focus_areas权重
- 使用更强的LLM模型

### Q: 生成的问题答案不准确？

- 实现答案验证逻辑
- 对比规则生成器的答案
- 人工抽检并反馈给LLM

## 下一步

1. **集成你的coverage_analysis pipeline**: 替换`analyze_nuscenes_qa_coverage()`
2. **批量处理**: 处理多个场景
3. **答案验证**: 添加ground truth验证
4. **可视化**: 生成覆盖率提升图表

## 支持

完整代码和文档:
- `coverage_driven_generator.py` - 核心生成器
- `integrated_pipeline.py` - 完整pipeline
- `llm_client.py` - LLM适配器
- `README_LLM_GENERATOR.md` - 详细文档

开始使用吧！🚀
