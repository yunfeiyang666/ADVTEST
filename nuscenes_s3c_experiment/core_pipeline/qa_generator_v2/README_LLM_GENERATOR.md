# LLM驱动的问答生成系统

## 概述

本系统提供**两种QA生成方式**:

### 1. 模板生成器 (快速、确定性)
- 文件: `generator.py`
- 特点: 直接使用模板填充,速度快,答案准确
- 用途: 大批量生成,需要确定性答案

### 2. LLM生成器 (自然、多样性) ⭐ 新增
- 文件: `llm_qa_generator.py`
- 特点: LLM生成问题+答案,表达自然,问题多样
- 用途: 高质量问答对,更接近真实VQA测试场景

## LLM生成器工作流程

```
场景图 → 模板引导 → LLM生成问题 → LLM根据场景图回答 → 完整QA对
```

### 关键优势

1. **自然表达**: LLM生成的问题更自然流畅,不局限于固定模板
2. **多样性**: 同一模板可以生成多种不同表达方式的问题
3. **真实测试**: 模拟CV模型的实际答题过程(理解场景→回答问题)
4. **可验证**: 可以对比LLM答案与规则答案,验证推理能力

## 快速开始

### 步骤1: 安装依赖

```bash
# 基础依赖
pip install openai anthropic requests

# 或使用requirements.txt
pip install -r requirements.txt
```

### 步骤2: 配置LLM客户端

#### 选项A: OpenAI GPT-4

```python
from llm_client import OpenAIClient

llm_client = OpenAIClient(
    api_key="your-openai-api-key",
    model="gpt-4",  # 或 "gpt-3.5-turbo"
    temperature=0.7,
    max_tokens=500
)
```

#### 选项B: Anthropic Claude

```python
from llm_client import ClaudeClient

llm_client = ClaudeClient(
    api_key="your-anthropic-api-key",
    model="claude-3-5-sonnet-20241022",
    temperature=0.7
)
```

#### 选项C: Ollama (本地模型)

```python
from llm_client import OllamaClient

llm_client = OllamaClient(
    model="llama3",  # 或其他本地模型
    host="http://localhost:11434"
)
```

#### 选项D: Azure OpenAI

```python
from llm_client import AzureOpenAIClient

llm_client = AzureOpenAIClient(
    api_key="your-azure-api-key",
    endpoint="https://your-resource.openai.azure.com",
    deployment_name="your-deployment-name",
    api_version="2024-02-15-preview"
)
```

### 步骤3: 生成问答对

```python
import json
from llm_qa_generator import LLMQAGenerator

# 创建生成器
generator = LLMQAGenerator(llm_client=llm_client)

# 加载场景图
with open("scene_graph.json", 'r', encoding='utf-8') as f:
    scene_data = json.load(f)

# 生成问答对
qa_pairs = generator.generate(
    scene_data,
    difficulties=["L0", "L1", "L2"],  # 选择难度级别
    num_questions_per_template=2  # 每个模板生成几个问题
)

# 保存结果
generator.save_qa_pairs(qa_pairs, "qa_output_llm.json")

print(f"生成了 {len(qa_pairs)} 个问答对")
```

## 完整示例

```python
"""
完整的LLM QA生成示例
"""
import json
from llm_qa_generator import LLMQAGenerator
from llm_client import OpenAIClient

# 1. 配置LLM
llm_client = OpenAIClient(
    api_key="sk-...",  # 你的API key
    model="gpt-4",
    temperature=0.7
)

# 2. 创建生成器
generator = LLMQAGenerator(llm_client=llm_client)

# 3. 加载场景图
scene_graph_path = "E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json"
with open(scene_graph_path, 'r', encoding='utf-8') as f:
    scene_data = json.load(f)

# 4. 生成问答对
# 参数说明:
# - difficulties: 选择生成的难度级别
# - num_questions_per_template: 每个模板生成多少个变体
qa_pairs = generator.generate(
    scene_data,
    difficulties=["L0"],  # 先测试L0级别
    num_questions_per_template=1  # 每个模板生成1个问题
)

# 5. 查看生成的问题
print(f"\n生成了 {len(qa_pairs)} 个问答对\n")
print("示例问答:")
for i, qa in enumerate(qa_pairs[:5], 1):
    print(f"\n{i}. Q: {qa.question}")
    print(f"   A: {qa.answer}")
    print(f"   Template: {qa.template_id}")

# 6. 保存结果
generator.save_qa_pairs(qa_pairs, "qa_output_llm.json")
```

## 模板系统与LLM协作

LLM生成器使用我们的57个模板作为**指导**,而不是硬性约束:

### 模板的作用

1. **类型指导**: 告诉LLM生成什么类型的问题(exist, count, status等)
2. **难度控制**: L0/L1/L2级别的复杂度要求
3. **格式参考**: 模板示例作为风格参考
4. **对象采样**: 根据模板类型采样合适的场景对象

### LLM的自由度

1. **表达方式**: 不局限于模板的确切措辞
2. **问题变体**: 同一模板可以生成多种表达
3. **自然语言**: 使用更自然流畅的问句
4. **创造性**: 在保持问题类型的前提下,创造性地组织语言

## 生成参数配置

### 控制生成数量

```python
# 方式1: 控制每个模板的变体数量
qa_pairs = generator.generate(
    scene_data,
    num_questions_per_template=3  # 每个模板生成3个不同问题
)

# 方式2: 只选择特定难度
qa_pairs = generator.generate(
    scene_data,
    difficulties=["L0", "L1"],  # 只生成L0和L1
    num_questions_per_template=2
)
```

### LLM参数调优

```python
# temperature越高,生成越多样;越低,越确定
llm_client = OpenAIClient(
    api_key="sk-...",
    model="gpt-4",
    temperature=0.9,  # 0.0-1.0,推荐0.7-0.9
    max_tokens=500    # 最大生成token数
)
```

## 质量控制

### 答案验证

由于LLM回答可能不完全准确,建议:

1. **对比规则答案**: 使用模板生成器的答案作为ground truth
2. **人工抽检**: 定期检查生成的QA对质量
3. **答案格式检查**: 确保yes/no、数字等格式正确

```python
# 可以在生成后验证答案
from generator import UnifiedQAGenerator

# 生成LLM版本
llm_generator = LLMQAGenerator(llm_client=llm_client)
llm_qa_pairs = llm_generator.generate(scene_data, difficulties=["L0"])

# 生成规则版本(ground truth)
rule_generator = UnifiedQAGenerator()
rule_qa_pairs = rule_generator.generate(scene_data, difficulties=["L0"])

# 对比答案准确率(需要实现匹配逻辑)
```

## 性能考虑

### 生成速度

- **模板生成器**: ~0.1秒/问题
- **LLM生成器**: ~2-5秒/问题 (取决于LLM API)

### 成本考虑

使用商业API(OpenAI, Claude)会产生费用:

- **GPT-4**: ~$0.03-0.06/问题
- **GPT-3.5-turbo**: ~$0.002-0.004/问题
- **Claude**: ~$0.015-0.075/问题
- **本地模型(Ollama)**: 免费,但需要GPU

### 建议

1. **开发阶段**: 使用小量数据测试 (num_questions_per_template=1)
2. **验证阶段**: 使用GPT-3.5或本地模型
3. **最终生成**: 使用GPT-4或Claude生成高质量数据集

## 批量生成

```python
"""
批量处理多个场景
"""
import json
from pathlib import Path
from llm_qa_generator import LLMQAGenerator
from llm_client import OpenAIClient

# 配置
scene_graphs_dir = Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs")
output_dir = Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/llm_qa_pairs")
output_dir.mkdir(exist_ok=True)

# 创建生成器
llm_client = OpenAIClient(api_key="sk-...")
generator = LLMQAGenerator(llm_client=llm_client)

# 遍历所有场景图
scene_files = list(scene_graphs_dir.glob("*.json"))
print(f"找到 {len(scene_files)} 个场景图文件")

for i, scene_file in enumerate(scene_files, 1):
    print(f"\n[{i}/{len(scene_files)}] 处理: {scene_file.name}")
    
    # 加载场景图
    with open(scene_file, 'r', encoding='utf-8') as f:
        scene_data = json.load(f)
    
    # 生成问答对
    qa_pairs = generator.generate(
        scene_data,
        difficulties=["L0", "L1"],
        num_questions_per_template=1
    )
    
    # 保存
    output_file = output_dir / f"qa_{scene_file.stem}.json"
    generator.save_qa_pairs(qa_pairs, str(output_file))
    
    print(f"  生成了 {len(qa_pairs)} 个问答对")
```

## 对比两种生成器

| 特性 | 模板生成器 | LLM生成器 |
|------|------------|-----------|
| 速度 | ⚡ 非常快 | 🐌 较慢 |
| 成本 | 💰 免费 | 💵 有成本 |
| 准确性 | ✅ 100%准确 | ⚠️ 需要验证 |
| 多样性 | ⭐ 固定模板 | ⭐⭐⭐ 高度多样 |
| 自然度 | ⭐⭐ 可接受 | ⭐⭐⭐ 非常自然 |
| 适用场景 | 大批量生成 | 高质量测试集 |

## 推荐策略

### 混合策略

1. **使用模板生成器**生成大量基础问答对 (快速、准确、免费)
2. **使用LLM生成器**生成少量高质量变体 (自然、多样)
3. **结合使用**: 模板生成答案作为ground truth,LLM生成问题表达

```python
# 混合生成示例
from generator import UnifiedQAGenerator
from llm_qa_generator import LLMQAGenerator

# 1. 模板生成器: 生成大量基础QA
rule_gen = UnifiedQAGenerator()
rule_qa = rule_gen.generate(scene_data)  # 200+ questions

# 2. LLM生成器: 生成少量高质量QA
llm_gen = LLMQAGenerator(llm_client=llm_client)
llm_qa = llm_gen.generate(scene_data, 
                          difficulties=["L1", "L2"],
                          num_questions_per_template=1)  # 40+ questions

# 3. 合并
all_qa = rule_qa + llm_qa
```

## 故障排查

### 问题1: LLM API调用失败

```python
# 检查API key是否正确
# 检查网络连接
# 检查API配额/余额

# 添加错误处理
try:
    qa_pairs = generator.generate(scene_data)
except Exception as e:
    print(f"生成失败: {e}")
```

### 问题2: 生成的问题质量不佳

```python
# 调整temperature (降低以提高一致性)
llm_client = OpenAIClient(
    api_key="sk-...",
    temperature=0.5  # 降低随机性
)

# 或者增加temperature (提高多样性)
llm_client = OpenAIClient(
    api_key="sk-...",
    temperature=0.9  # 增加创造性
)
```

### 问题3: 答案格式不对

- 检查prompt是否清晰
- 增强答案提取逻辑
- 使用answer validation

## 下一步

1. **实现答案验证**: 对比LLM答案与规则答案
2. **批量生成脚本**: 处理整个数据集
3. **质量评估**: 人工评估问题自然度
4. **成本优化**: 使用GPT-3.5或本地模型

## 文件清单

- `llm_qa_generator.py` - LLM QA生成器主文件
- `llm_client.py` - LLM客户端适配器
- `generator.py` - 模板生成器(原有)
- `templates.py` - 57个模板定义
- `README_LLM_GENERATOR.md` - 本文档

## 联系与支持

如有问题,请参考代码注释或联系开发团队。
