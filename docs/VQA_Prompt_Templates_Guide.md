# VQA Prompt模板完整指南

## 📋 目录
1. [NuScenes-QA官方方法](#1-nuscenes-qa官方方法)
2. [业界常用Prompt模板](#2-业界常用prompt模板)
3. [我们的实现](#3-我们的实现)
4. [最佳实践](#4-最佳实践)

---

## 1. NuScenes-QA官方方法

### ❌ **官方不使用Prompt**

**重要发现**：NuScenes-QA官方实现**不使用基于LLM的prompt方法**！

```python
# 官方使用的是传统VQA模型
# 来源: NuScenes-QA/src/models/

支持的模型:
1. MCAN (Modular Co-Attention Network)
   - 基于attention机制的传统VQA模型
   - 输入: 图像特征 + 问题embedding
   - 输出: 答案分类

2. ButD (Bottom-Up Top-Down)
   - 基于检测框特征的VQA模型
   - 使用Faster R-CNN提取对象特征
   - 通过attention融合问题和图像
```

### 📊 **官方模型架构**

```
输入处理:
┌─────────────────────────────────────────────────┐
│ 1. 图像 → Faster R-CNN → 对象特征 (2048维)      │
│ 2. 问题 → GloVe Embedding → 问题向量 (300维)    │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ MCAN/ButD模型                                    │
│ - Multi-head Attention                          │
│ - Co-attention层                                 │
│ - 特征融合                                       │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ 分类器 → softmax → 答案索引                      │
└─────────────────────────────────────────────────┘
```

### 🔍 **为什么官方不用Prompt？**

1. **论文发表时间**：2021年，当时LLM-VQA还未流行
2. **任务性质**：封闭式QA，预定义答案字典更适合分类模型
3. **性能考虑**：传统模型在该数据集上已有较好表现

---

## 2. 业界常用Prompt模板

### 🌟 **现代VLM的Prompt设计**

随着GPT-4V、LLaVA、MiniCPM-V等多模态大模型的出现，业界开始使用prompt-based方法：

#### **模板1: 直接问答（Zero-shot）**

```python
# 最简单的prompt
prompt = f"{question}"

# 示例
question = "Is there a car in the scene?"
prompt = "Is there a car in the scene?"
```

**优点**：简洁，模型负担小  
**缺点**：答案格式不可控

---

#### **模板2: 多选题格式（推荐）**

```python
def construct_mc_prompt(question, options):
    """
    业界标准的多选题prompt
    来源: 我们的实现 eval_minicpm_nuscenes_qa.py
    """
    prompt = f"{question}\n\n"
    for i, option in enumerate(options):
        prompt += f"{chr(65+i)}. {option}\n"
    prompt += "\nPlease answer with only the letter (A, B, C, or D) of the correct option."
    return prompt

# 示例输出:
"""
Is there a car in the scene?

A. Yes
B. No
C. Maybe
D. Unknown

Please answer with only the letter (A, B, C, or D) of the correct option.
"""
```

**优点**：
- ✅ 答案格式可控（A/B/C/D）
- ✅ 容易解析
- ✅ 减少歧义

**缺点**：
- ⚠️ Prompt较长
- ⚠️ 可能引入bias（选项顺序）

---

#### **模板3: Chain-of-Thought（CoT）**

```python
def construct_cot_prompt(question, options):
    """
    思维链prompt，引导模型逐步推理
    """
    prompt = f"""Question: {question}

Options:
A. {options[0]}
B. {options[1]}
C. {options[2]}
D. {options[3]}

Please think step by step:
1. First, identify the relevant objects in the scene
2. Then, analyze their relationships
3. Finally, select the correct answer

Your answer (letter only):"""
    return prompt
```

**优点**：
- ✅ 提高复杂推理能力
- ✅ 可解释性强

**缺点**：
- ⚠️ Prompt很长
- ⚠️ 推理时间增加

---

#### **模板4: Few-shot示例**

```python
def construct_fewshot_prompt(question, options, examples):
    """
    Few-shot学习prompt
    """
    prompt = "Here are some examples:\n\n"
    
    # 添加示例
    for ex in examples:
        prompt += f"Q: {ex['question']}\n"
        prompt += f"A: {ex['answer']}\n\n"
    
    # 添加当前问题
    prompt += f"Now answer this question:\n"
    prompt += f"Q: {question}\n"
    for i, option in enumerate(options):
        prompt += f"{chr(65+i)}. {option}\n"
    prompt += f"A:"
    
    return prompt
```

**优点**：
- ✅ 引导模型理解任务
- ✅ 提高准确率（特别是新任务）

**缺点**：
- ⚠️ 需要精心选择示例
- ⚠️ Prompt token消耗大

---

#### **模板5: 角色扮演（Role-playing）**

```python
def construct_role_prompt(question, options):
    """
    角色扮演prompt，让模型扮演自动驾驶专家
    """
    prompt = f"""You are an autonomous driving perception system expert. 
You are analyzing a bird's-eye view (BEV) image of a driving scene.

Question: {question}

Options:
A. {options[0]}
B. {options[1]}
C. {options[2]}
D. {options[3]}

Based on your expertise in autonomous driving, what is the correct answer?
Answer with only the letter (A, B, C, or D):"""
    return prompt
```

**优点**：
- ✅ 激活模型的领域知识
- ✅ 提高专业性

**缺点**：
- ⚠️ 对通用模型效果有限
- ⚠️ Prompt较长

---

## 3. 我们的实现

### 📝 **当前使用的Prompt模板**

```python
# 文件: eval_minicpm_nuscenes_qa.py

def construct_mc_prompt(question, options):
    """
    构造多选题的 prompt
    
    设计理念:
    1. 简洁明了
    2. 格式规范（A/B/C/D）
    3. 明确指令（only the letter）
    """
    prompt = f"{question}\n\n"
    for i, option in enumerate(options):
        prompt += f"{chr(65+i)}. {option}\n"
    prompt += "\nPlease answer with only the letter (A, B, C, or D) of the correct option."
    return prompt


def parse_answer(model_output, options):
    """
    解析模型输出，提取选择的答案
    
    两层解析策略:
    1. 字母匹配: 优先查找A/B/C/D
    2. 文本匹配: 回退到选项文本匹配
    """
    model_output = model_output.strip().upper()
    
    # 第1层: 字母答案提取
    for i, letter in enumerate(['A', 'B', 'C', 'D']):
        if letter in model_output[:10]:  # 只看前10个字符
            return i
    
    # 第2层: 选项文本匹配
    for i, option in enumerate(options):
        if option.lower() in model_output.lower():
            return i
    
    return -1  # 无法解析
```

### 🎯 **我们的Prompt演化历史**

```
V1 (初版): 直接问答
├─ Prompt: "{question}"
├─ 问题: 答案格式不统一
└─ 准确率: ~45%

V2 (多选题): 添加选项
├─ Prompt: "{question}\nA. {opt1}\nB. {opt2}\n..."
├─ 改进: 格式化输出
└─ 准确率: ~58%

V3 (明确指令): 添加答案要求
├─ Prompt: "...Please answer with only the letter..."
├─ 改进: 减少冗长回答
└─ 准确率: ~62%

V4 (优化解析): 改进答案提取
├─ 改进: 两层解析策略
└─ 准确率: ~65%
```

---

## 4. 最佳实践

### ✅ **DO（推荐做法）**

1. **使用结构化prompt**
   ```python
   # Good
   prompt = f"{question}\n\nA. {opt1}\nB. {opt2}\n..."
   
   # Bad
   prompt = f"{question} {opt1} {opt2} {opt3} {opt4}"
   ```

2. **明确输出格式要求**
   ```python
   # Good
   prompt += "\nPlease answer with only the letter (A, B, C, or D)."
   
   # Bad
   prompt += "\nWhat's the answer?"
   ```

3. **提供清晰的上下文**
   ```python
   # Good (如果是BEV图)
   prompt = "This is a bird's-eye view image.\n" + question
   
   # Bad
   prompt = question  # 没有上下文
   ```

4. **使用鲁棒的答案解析**
   ```python
   # Good: 多层解析
   if 'A' in output[:10]: return 0
   elif opt1 in output: return 0
   else: return -1
   
   # Bad: 单一解析
   return output[0]  # 可能崩溃
   ```

---

### ❌ **DON'T（避免的做法）**

1. **过长的prompt**
   ```python
   # Bad: 超过500 tokens
   prompt = "You are an expert... [长篇描述] ... " + question
   
   # Good: 控制在100 tokens内
   prompt = question + "\n" + options
   ```

2. **模糊的指令**
   ```python
   # Bad
   prompt = "What do you think?"
   
   # Good
   prompt = "Select the correct answer: A, B, C, or D"
   ```

3. **引入bias的prompt**
   ```python
   # Bad: 暗示答案
   prompt = "Obviously there is a car, right? A. Yes B. No"
   
   # Good: 中性表述
   prompt = "Is there a car? A. Yes B. No"
   ```

4. **不可解析的输出**
   ```python
   # Bad: 没有格式约束
   prompt = "Answer the question freely."
   # 可能得到: "Well, I think maybe..."
   
   # Good: 严格格式
   prompt = "Answer with only: A, B, C, or D"
   ```

---

## 5. MetaVQA的Prompt（补充）

### 📝 **MetaVQA特殊性**

MetaVQA数据集已经包含了`options`字段，直接使用：

```python
# MetaVQA数据格式
{
    "question": "Specify the color of object <1>.",
    "options": {
        "A": "White",
        "B": "Blue", 
        "C": "Gray",
        "D": "Orange"
    },
    "answer": "D",
    "type": "identify_color"
}

# 构造prompt
def construct_metavqa_prompt(item):
    prompt = f"{item['question']}\n\n"
    for key, value in item['options'].items():
        prompt += f"{key}. {value}\n"
    prompt += "\nAnswer with only the letter:"
    return prompt
```

---

## 6. 总结

### 🎯 **核心建议**

1. **NuScenes-QA官方评估**：
   - ✅ 使用传统VQA模型（MCAN/ButD）
   - ✅ 不依赖prompt
   - ✅ 使用预定义答案字典

2. **现代VLM评估**：
   - ✅ 使用多选题格式prompt
   - ✅ 明确输出格式要求
   - ✅ 实现鲁棒的答案解析

3. **业界对比**：
   - ⚠️ 如果要与官方基准对比，必须用官方评估
   - ⚠️ 如果使用VLM，需要明确说明是非官方评估
   - ⚠️ 建议同时报告两种评估结果

4. **研究创新**：
   - 💡 可以探索CoT、Few-shot等高级prompt
   - 💡 可以研究prompt对准确率的影响
   - 💡 但必须在论文中明确说明与官方的差异

---

## 📚 **参考资料**

1. NuScenes-QA官方仓库: https://github.com/qiantianwen/NuScenes-QA
2. MCAN论文: Deep Modular Co-Attention Networks (CVPR 2019)
3. ButD论文: Bottom-Up and Top-Down Attention (CVPR 2018)
4. LLaVA Prompt设计: https://github.com/haotian-liu/LLaVA
5. MiniCPM-V文档: https://github.com/OpenBMB/MiniCPM-V

---

**文档版本**: v1.0  
**更新日期**: 2025-11-27  
**作者**: ADVTEST团队
