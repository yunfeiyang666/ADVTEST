# MiniCPM Prompt版本详细功能对比分析

## 📋 版本概览表

| 版本 | Token限制 | 核心功能 | 改进方向 | 准确率影响 | 主要问题 |
|------|-----------|----------|----------|------------|----------|
| **V0 (Baseline)** | 无限制 | 直接问答 | 无结构化 | 38.0% | 无可解释性 |
| **V1 (基础版)** | 128 | 三段式格式 | 结构化输出 | 截断 | 输出不完整 |
| **V2 (强化版)** | 180 | 格式示例 | 答案部分强化 | 部分改善 | 仍有截断 |
| **V3 (扩容版)** | 256 | 完整输出 | Token扩容 | 结构完整 | 准确率低 |
| **V4 (优化版)** | 384 | 稳定输出 | 推理引导 | 15.8% | 内容错误 |
| **V5 (Few-Shot)** | 512 | 示例教学 | 知识注入 | 未完成 | 技术问题 |

---

## 🔍 各版本详细功能分析

### V0 - Baseline (无思维轨迹限制)
```python
# 最简单的直接问答
prompt = f"Question: {question}\nOptions: {options}\nAnswer:"
```

**实现功能**:
- ✅ 直接问答，无格式限制
- ✅ 快速推理 (~3秒/题)
- ✅ 高准确率 (38.0%)

**改进方向**: 无结构化要求
**优势**: 简单高效，准确率最高
**劣势**: 无可解释性，无推理过程

---

### V1 - 基础版 (Token: 128)
```python
prompt = f"""
🎯 You are analyzing a BEV image from autonomous driving.

Question: {question}
Options: {options}

REQUIRED FORMAT:
OBSERVATION: [Describe what you see]
REASONING: [Explain your analysis] 
ANSWER: [Give the exact option]
"""
```

**实现功能**:
- ✅ 引入三段式结构 (OBSERVATION/REASONING/ANSWER)
- ✅ 基础BEV分析指导
- ✅ 明确输出格式要求

**改进方向**: **结构化输出** - 从无结构到有结构
**核心创新**: 首次要求显式推理过程
**主要问题**: Token限制导致输出截断，ANSWER部分经常缺失

---

### V2 - 强化版 (Token: 180)
```python
prompt = f"""
🎯 You are analyzing a BEV image from autonomous driving.

Question: {question}
Options: {options}

🔍 REQUIRED FORMAT:
OBSERVATION: [Describe what you see in 2-3 sentences]
REASONING: [Explain your analysis in 2-3 sentences] 
ANSWER: [Give the exact option text, like "Close (2-10m)"]

⚠️ IMPORTANT: You MUST provide all three sections. 
Example:
OBSERVATION: The car is positioned...
REASONING: Based on the spatial relationship...
ANSWER: Close (2-10m)
"""
```

**实现功能**:
- ✅ 强化ANSWER部分要求
- ✅ 添加具体格式示例
- ✅ 使用emoji增强视觉效果
- ✅ 明确字数限制 (2-3句)

**改进方向**: **答案部分强化** - 解决ANSWER缺失问题
**核心创新**: 
- 添加示例教学
- 强调"MUST provide all three sections"
- 给出具体的答案格式

**主要问题**: Token限制仍然存在，结构化不够完整

---

### V3 - 扩容版 (Token: 256)
```python
prompt = f"""
🎯 You are analyzing a BEV (Bird's Eye View) image from autonomous driving.

📋 TASK: Answer this question with structured reasoning.

❓ Question: {question}
📝 Options: {options}

🔍 REQUIRED FORMAT:
OBSERVATION: [Describe what you see in 2-3 sentences]
REASONING: [Explain your analysis in 2-3 sentences] 
ANSWER: [Give the exact option text]

⚠️ IMPORTANT: You MUST provide all three sections.
"""
```

**实现功能**:
- ✅ 大幅增加Token限制 (128→256)
- ✅ 保持详细的prompt结构
- ✅ 解决输出截断问题
- ✅ 确保完整的三段式输出

**改进方向**: **Token扩容** - 解决输出完整性问题
**核心创新**: 
- 首次实现完整输出不截断
- 保持所有格式要求

**主要问题**: 输出完整但准确率开始下降，内容质量问题显现

---

### V4 - 优化版 (Token: 384) ⭐ **当前最佳**
```python
def construct_prompt_mc(question, options):
    opts = "\n".join([f"{chr(65+i)}. {o}" for i, o in enumerate(options)])
    
    prompt = f"""🎯 You are analyzing a BEV (Bird's Eye View) image from autonomous driving.

📋 **TASK**: Answer this question with structured reasoning.

❓ **Question**: {question}

📝 **Options**:
{opts}

🔍 **REQUIRED FORMAT**:
OBSERVATION: [Describe what you see in 2-3 sentences]
REASONING: [Explain your analysis in 2-3 sentences] 
ANSWER: [Give the exact option text, like "Close (2-10m)"]

⚠️ **IMPORTANT**: You MUST provide all three sections. The ANSWER must be one of the exact option texts above.

💡 **GUIDANCE**:
- For distance questions: Consider spatial relationships and BEV perspective
- For direction questions: Use relative positioning from ego vehicle viewpoint
- For counting questions: Identify and count distinct objects carefully
"""
```

**实现功能**:
- ✅ 进一步增加Token限制 (256→384)
- ✅ 添加题型特定的推理引导
- ✅ 优化格式布局和视觉效果
- ✅ 强化答案格式要求
- ✅ 分类指导 (距离/方向/计数)

**改进方向**: **推理引导优化** - 提供领域特定的分析指导
**核心创新**: 
- 首次添加题型特定指导
- 优化视觉布局 (加粗、分段)
- 强调答案必须是选项原文

**效果**: 结构化得分0.9+，但准确率15.8%
**主要问题**: 内容准确性仍然不足，BEV理解错误

---

### V5 - Few-Shot版 (Token: 512) ❌ **测试失败**
```python
def construct_prompt_mc_fewshot(question, options):
    # 判断题型并选择对应示例
    is_distance = 'how close' in question.lower()
    is_sector = 'where' in question.lower() and 'relative' in question.lower()
    
    if is_distance:
        few_shot = """
📚 **REFERENCE EXAMPLES**:

Example 1 - Distance Estimation:
Question: How close is the car at position x=-20m, y=15m to the ego vehicle?
OBSERVATION: The car is at coordinates (-20, 15). Left side, moderate forward distance.
REASONING: Distance = sqrt((-20)² + 15²) = sqrt(625) = 25m. This is less than 30m, so Medium range.
ANSWER: Medium (10-30m)

Example 2 - Distance Estimation:
Question: How close is the pedestrian at x=-3m, y=1m?
OBSERVATION: Pedestrian at (-3, 1), very close to ego vehicle.
REASONING: Distance = sqrt(9 + 1) = sqrt(10) ≈ 3.2m. Falls in Close range.
ANSWER: Close (2-10m)
"""
    
    prompt = f"""🎯 You are analyzing a BEV (Bird's Eye View) image from autonomous driving.

🗺️ **BEV COORDINATE SYSTEM**:
- Ego vehicle is at origin (0, 0)
- X-axis: negative = LEFT, positive = RIGHT
- Y-axis: negative = BACK, positive = FRONT
- Distance from ego = sqrt(x² + y²)

📏 **DISTANCE RANGES**:
- Very close (0-2m): Almost touching ego vehicle
- Close (2-10m): Nearby, within immediate vicinity
- Medium (10-30m): Moderate distance, clearly separated
- Far (30m+): Distant objects

{few_shot}

📋 **NOW YOUR TASK**:
❓ **Question**: {question}
📝 **Options**: {options}

🔍 **REQUIRED FORMAT**:
OBSERVATION: [Describe object position, try to identify coordinates if visible]
REASONING: [If coordinates visible, calculate distance using sqrt(x²+y²)]
ANSWER: [Give the exact option text]

⚠️ **IMPORTANT**: 
1. Look for coordinate information in the BEV image
2. If you can identify x,y coordinates, calculate actual distance
3. The ANSWER must be one of the exact option texts above
"""
```

**实现功能**:
- ✅ 添加Few-shot示例教学
- ✅ 明确BEV坐标系说明
- ✅ 提供距离计算公式
- ✅ 多步推理引导
- ✅ 题型特定示例

**改进方向**: **知识注入** - 通过示例教授BEV理解和计算方法
**核心创新**: 
- 首次添加具体计算示例
- 明确坐标系定义
- 教授距离计算公式 sqrt(x²+y²)
- 分题型提供不同示例

**状态**: 测试失败 (图像路径配置错误)
**预期效果**: 距离准确率从10%提升到25-35%

---

## 🎯 功能演进路径分析

### 阶段1: 结构化 (V1→V2)
**目标**: 从无结构到有结构
- V1: 引入三段式格式
- V2: 强化答案部分，添加示例

**效果**: 建立了基础的结构化框架

### 阶段2: 完整性 (V2→V3)
**目标**: 解决输出截断问题
- V3: Token扩容到256

**效果**: 实现完整输出，但准确率开始下降

### 阶段3: 优化引导 (V3→V4)
**目标**: 提升推理质量
- V4: 添加题型特定指导，优化布局

**效果**: 结构化质量达到0.9+，准确率稳定在15.8%

### 阶段4: 知识注入 (V4→V5)
**目标**: 解决根本的BEV理解问题
- V5: Few-shot示例，坐标系教学

**效果**: 未完成测试，但理论上应该显著提升距离判断准确率

---

## 📊 各版本对比总结

### 功能实现维度
| 功能 | V1 | V2 | V3 | V4 | V5 |
|------|----|----|----|----|----| 
| **结构化输出** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **格式示例** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **完整输出** | ❌ | ❌ | ✅ | ✅ | ✅ |
| **推理引导** | ❌ | ❌ | ❌ | ✅ | ✅ |
| **Few-shot教学** | ❌ | ❌ | ❌ | ❌ | ✅ |
| **坐标系说明** | ❌ | ❌ | ❌ | ❌ | ✅ |

### 改进方向维度
| 版本 | 主要改进方向 | 解决的问题 | 引入的问题 |
|------|--------------|------------|------------|
| **V1** | 结构化输出 | 无推理过程 | 输出截断 |
| **V2** | 答案强化 | ANSWER缺失 | Token仍不足 |
| **V3** | Token扩容 | 输出截断 | 准确率下降 |
| **V4** | 推理引导 | 格式优化 | 内容错误 |
| **V5** | 知识注入 | BEV理解 | 技术问题 |

### 核心创新点
- **V1**: 首次引入结构化思维轨迹
- **V2**: 首次添加格式示例教学
- **V3**: 首次实现完整输出不截断
- **V4**: 首次添加领域特定推理指导
- **V5**: 首次尝试Few-shot知识注入

---

## 💡 关键洞察

### 1. **渐进式改进路径**
V1→V2→V3→V4 遵循了"结构化→示例化→完整化→优化化"的渐进路径

### 2. **Token与质量的权衡**
- 128 tokens: 不完整但快速
- 384 tokens: 完整但慢速
- 512 tokens: 理论最优但未测试

### 3. **格式vs内容的矛盾**
每个版本都在改善格式，但内容准确性持续下降，说明**结构化要求可能干扰了模型的自然推理**

### 4. **领域知识的重要性**
V5的设计思路（Few-shot + 坐标系教学）可能是解决BEV理解问题的正确方向，但技术实现失败

### 5. **实用性考量**
V0 (38.0%, 3秒) vs V4 (15.8%, 200秒) 的对比表明，**简单直接的方法可能更实用**

这个分析为后续的prompt设计提供了清晰的功能模块化思路和改进方向指导。
