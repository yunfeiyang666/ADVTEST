# VQA Pipeline 学习文档

## 一、整体流程架构

```
用户自然语言问题
        ↓
┌──────────────────────────────────────────────┐
│ Step 1: 问题 → Cypher查询                     │
│ LLM (DeepSeek-R1) 将自然语言翻译成Cypher      │
│ 耗时：3-10秒                                  │
└──────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────┐
│ Step 2: 执行Cypher查询                        │
│ Neo4j数据库执行查询，返回结构化数据            │
│ 耗时：0.1-1秒                                 │
└──────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────┐
│ Step 3: 查询结果 → 自然语言答案                │
│ LLM将结构化数据翻译成自然语言                  │
│ 耗时：10-20秒                                 │
└──────────────────────────────────────────────┘
        ↓
   自然语言答案
```

---

## 二、核心组件详解

### 2.1 配置文件 (`vqa_pipeline/config.py`)

**作用**：存储API密钥、数据库配置、Prompt模板

**关键内容**：
```python
# API配置
API_BASE_URL = "https://maas-api.ai-yuanjing.com/openapi/compatible-mode/v1"
API_KEY = "sk-xxx"
MODEL_NAME = "deepseek-r1"

# Neo4j配置
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "87017563"

# Schema描述（告诉AI我们的数据结构）
SCENE_GRAPH_SCHEMA = """
节点类型 (Label: Object):
- unique_id: 对象唯一标识符
- type: 对象类型 (ego/car/pedestrian/...)
- translation: 3D坐标 [x, y, z]

关系类型 (Type: RELATES_TO):
- predicates: [方位, 距离级别]
  - predicates[0] = 方位: 'front'/'left'/'rear'/'right'
  - predicates[1] = 距离级别: 'near'/'mid'/'far'
- distance: 精确距离（米）

示例Cypher:
1. 查ego前方对象: MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(obj) 
   WHERE r.predicates[0]='front' RETURN obj.unique_id, obj.type
2. 统计车辆数: MATCH (n:Object) WHERE n.type='car' RETURN count(n)
3. 最近距离: MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(obj) 
   RETURN obj.unique_id, r.distance ORDER BY r.distance LIMIT 1
"""

# Prompt模板
QUESTION_TO_CYPHER_PROMPT = """你是一个专业的Neo4j Cypher查询专家。
场景图数据库Schema: {schema}
用户问题: {question}
要求: 只输出Cypher查询语句，不要其他解释
"""
```

**为什么需要示例Cypher**？
- AI本身会Cypher语言，但不知道我们的具体字段名
- 示例是**Few-shot Prompting**技术，帮助AI理解我们的数据结构
- 避免AI生成错误的查询（如精确匹配数组）

---

### 2.2 LLM客户端 (`vqa_pipeline/llm_client.py`)

**作用**：封装与DeepSeek-R1 API的交互

**核心方法**：

#### `chat(messages, temperature, max_tokens)`
发送聊天请求，返回原始回复

```python
response = self.chat([
    {"role": "system", "content": "你是专家"},
    {"role": "user", "content": "问题"}
])
# 返回: "<think>思维过程</think>实际答案"
```

#### `generate_cypher(question)`
将自然语言问题转换为Cypher查询

```python
cypher = self.llm.generate_cypher("ego车前方有哪些对象？")
# 返回: "MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(obj)..."
```

**关键处理逻辑**：
1. 调用chat获取原始回复
2. 提取`<think>...</think>`标签中的思维过程
3. 去除思维标签，提取Cypher代码块
4. 保存思维过程和耗时到`self.last_thinking`和`self.last_elapsed`

```python
# 提取思维过程
think_match = re.search(r'<think>(.*?)</think>', response, flags=re.DOTALL)
thinking = think_match.group(1).strip() if think_match else None

# 去除思维标签，提取代码块
cypher = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
code_block_match = re.search(r'```(?:cypher)?\s*(.*?)```', cypher, flags=re.DOTALL)
if code_block_match:
    cypher = code_block_match.group(1).strip()
```

#### `generate_answer(question, query_result)`
将Neo4j查询结果转换为自然语言答案

```python
answer = self.llm.generate_answer(
    "ego车前方有哪些对象？",
    '{"count": 30, "data": [...]}'
)
# 返回: "ego车前方共有30个对象，包括19个行人、7辆汽车..."
```

---

### 2.3 Neo4j客户端 (`vqa_pipeline/neo4j_client.py`)

**作用**：连接Neo4j数据库，执行Cypher查询

**核心方法**：

#### `connect()`
建立数据库连接

```python
if not self.neo4j.connect():
    print("连接失败")
```

#### `execute_query(cypher_query)`
执行Cypher查询，返回结果

```python
result = self.neo4j.execute_query(
    "MATCH (n:Object) WHERE n.type='car' RETURN count(n)"
)
# 返回: {
#   "success": True,
#   "count": 1,
#   "data": [{"count(n)": 8}]
# }
```

**结果格式**：
```python
{
    "success": True/False,
    "count": 结果数量,
    "data": [
        {"字段1": 值1, "字段2": 值2},
        ...
    ],
    "error": "错误信息"  # 仅在失败时
}
```

---

### 2.4 Pipeline主流程 (`vqa_pipeline/pipeline.py`)

**作用**：整合LLM和Neo4j，完成完整VQA流程

**核心方法**：

#### `initialize()`
初始化连接，提示用户启动Neo4j

```python
pipeline = VQAPipeline()
if not pipeline.initialize():
    print("初始化失败")
```

#### `process_question(question, verbose=True)`
处理单个问题

```python
result = pipeline.process_question("ego车前方有哪些对象？", verbose=True)

# 返回 VQAResult 对象:
# - question: 原始问题
# - cypher_query: 生成的Cypher
# - query_result: Neo4j查询结果
# - answer: 最终答案
# - success: 是否成功
```

**流程详解**：
```python
# Step 1: 生成Cypher
cypher_query = self.llm.generate_cypher(question)
print(f"⏱️ 耗时: {self.llm.last_elapsed:.2f}秒")
if self.llm.last_thinking:
    print(f"💭 AI思维过程:\n{self.llm.last_thinking}")

# Step 2: 执行查询
step2_start = time.time()
query_result = self.neo4j.execute_query(cypher_query)
step2_elapsed = time.time() - step2_start
print(f"⏱️ 耗时: {step2_elapsed:.3f}秒")

# Step 3: 生成答案
result_json = json.dumps(query_result, ensure_ascii=False)
answer = self.llm.generate_answer(question, result_json)
print(f"⏱️ 耗时: {self.llm.last_elapsed:.2f}秒")
if self.llm.last_thinking:
    print(f"💭 AI思维过程:\n{self.llm.last_thinking}")
```

---

## 三、运行脚本 (`run_vqa_pipeline.py`)

**功能**：提供命令行界面，支持多种运行模式

### 3.1 测试连接
```bash
python run_vqa_pipeline.py --test
```
验证Neo4j和LLM API连接

### 3.2 单个问题
```bash
python run_vqa_pipeline.py -q "ego车前方有哪些对象？"
```

### 3.3 交互模式
```bash
python run_vqa_pipeline.py -i
```
持续输入问题，输入`quit`退出

### 3.4 批量处理
```bash
python run_vqa_pipeline.py --all
```
处理`sample_questions.py`中的所有问题

---

## 四、关键技术点

### 4.1 Few-shot Prompting
**问题**：AI不知道我们的具体数据结构

**解决**：在Prompt中提供示例Cypher查询

```
Schema描述:
- 节点: Object
- 关系: RELATES_TO
- 字段: predicates[0]=方位, predicates[1]=距离级别

示例Cypher:
1. 查ego前方对象: MATCH (ego:Object...)...
2. 统计车辆数: MATCH (n:Object) WHERE n.type='car'...
3. 最近距离: MATCH ... ORDER BY r.distance LIMIT 1

用户问题: {question}
```

AI会参考示例，生成正确的查询。

### 4.2 DeepSeek-R1 思维链
DeepSeek-R1 会输出`<think>思维过程</think>最终答案`

**我们的处理**：
1. 提取思维过程，展示给用户
2. 去除思维标签，获取纯净答案

**好处**：
- 用户可以看到AI的推理过程
- 提高答案可信度
- 便于调试错误查询

### 4.3 计时功能
每个步骤记录耗时：
- Step 1 (LLM生成Cypher): 3-10秒
- Step 2 (Neo4j查询): 0.1-1秒
- Step 3 (LLM生成答案): 10-20秒

**总耗时**：通常15-30秒

---

## 五、数据流示例

### 输入
```
问题: "离ego最近的车辆是哪个？距离多远？"
```

### Step 1 输出
```
AI思维过程:
  要求查找最近的车辆，需要:
  1. 匹配车辆对象 (type='car')
  2. 按距离排序
  3. 返回unique_id和distance

Cypher:
  MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(car:Object)
  WHERE car.type = 'car'
  RETURN car.unique_id, r.distance
  ORDER BY r.distance ASC
  LIMIT 1

耗时: 10.05秒
```

### Step 2 输出
```
查询结果:
{
  "success": true,
  "count": 1,
  "data": [{"car.unique_id": "car2", "r.distance": 20.74}]
}

耗时: 0.089秒
```

### Step 3 输出
```
AI思维过程:
  查询结果显示最近的车辆是car2，距离20.74米
  用户问了两个问题：哪个？多远？
  答案应该直接包含这两个信息

答案:
  离ego最近的车辆是car2，距离为20.74米。

耗时: 13.62秒
```

---

## 六、常见问题

### Q1: 为什么有时查询失败？
**原因**：AI生成的Cypher语法错误或字段名错误

**解决**：
1. 检查Schema描述是否准确
2. 增加更多示例Cypher
3. 调整Prompt温度参数（降低随机性）

### Q2: 如何提高查询准确率？
1. **完善Schema描述**：详细说明字段含义
2. **增加示例**：覆盖常见查询模式
3. **添加约束**：明确禁止某些错误写法

### Q3: 为什么Step 1和Step 3这么慢？
**原因**：DeepSeek-R1 是671B参数的大模型，推理需要时间

**优化方向**：
- 使用更小的模型（如DeepSeek-V3）
- 缓存常见问题的答案
- 并行处理多个问题

### Q4: 数据库连接失败怎么办？
**检查清单**：
1. Neo4j是否启动？
   ```bash
   E:\node4j\neo4j-community-2025.10.1\bin\neo4j console
   ```
2. 端口是否正确？默认7687
3. 用户名密码是否正确？默认neo4j/87017563

---

## 七、扩展方向

### 7.1 对象打标可视化
在BEV图或相机图像上高亮显示查询结果中的对象

### 7.2 多轮对话
支持上下文记忆，如：
```
Q1: ego前方有多少辆车？
A1: 7辆

Q2: 最近的是哪个？  ← 知道"最近的"指的是车
A2: car2
```

### 7.3 查询优化
自动检测低效查询，提供优化建议

### 7.4 结果缓存
对于相同问题，直接返回缓存答案

---

## 八、完整运行示例

```bash
# 1. 启动Neo4j（新终端）
E:\node4j\neo4j-community-2025.10.1\bin\neo4j console

# 2. 激活虚拟环境
E:\Project\ADVTEST\.venv310\Scripts\Activate.ps1

# 3. 运行VQA
python e:\Project\ADVTEST\nuscenes_s3c_experiment\run_vqa_pipeline.py -q "ego车前方有哪些对象？"

# 输出示例:
# ============================================================
#   VQA Pipeline 初始化
# ============================================================
# ⚠️ 请确保Neo4j数据库已启动!
# ✓ Neo4j连接成功: bolt://localhost:7687
# ✓ VQA Pipeline 初始化完成
# 
# ============================================================
# 问题: ego车前方有哪些对象？
# ============================================================
# 
# [Step 1] 生成Cypher查询...
#   ⏱️ 耗时: 4.25秒
#   💭 AI思维过程:
#   --------------------------------------------------
#       查询ego前方对象，使用predicates[0]='front'...
#   --------------------------------------------------
#   📝 Cypher: MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(obj)
#              WHERE r.predicates[0] = 'front'
#              RETURN obj.unique_id, obj.type
# 
# [Step 2] 执行Neo4j查询...
#   ⏱️ 耗时: 0.504秒
#   📊 结果数量: 30
# 
# [Step 3] 生成自然语言答案...
#   ⏱️ 耗时: 19.27秒
#   💭 AI思维过程:
#   --------------------------------------------------
#       结果包含30个对象，需统计各类型数量...
#   --------------------------------------------------
#   ✅ 答案: ego车前方共有30个对象，包括19个行人、7辆汽车、
#            1辆自行车、3辆卡车。
```

---

## 九、代码文件清单

```
nuscenes_s3c_experiment/
├── vqa_pipeline/               # VQA核心模块
│   ├── __init__.py            # 包初始化
│   ├── config.py              # 配置文件（API密钥、Schema、Prompt）
│   ├── llm_client.py          # LLM客户端
│   ├── neo4j_client.py        # Neo4j客户端
│   ├── pipeline.py            # 主流程
│   └── sample_questions.py    # 示例问题集
│
├── run_vqa_pipeline.py        # 运行脚本
└── VQA_Pipeline_学习文档.md   # 本文档
```

---

## 十、学习路径建议

### 第1天：理解整体架构
1. 阅读"一、整体流程架构"
2. 运行几个示例问题，观察输出
3. 理解3个步骤的作用

### 第2天：深入各组件
1. 阅读`config.py`，理解Schema和Prompt
2. 阅读`llm_client.py`，理解思维链提取
3. 阅读`neo4j_client.py`，理解查询执行

### 第3天：实践与调试
1. 修改示例Cypher，观察AI生成的变化
2. 尝试提问，查看Cypher是否正确
3. 修改Prompt，优化AI回答质量

### 第4天：扩展功能
1. 添加新的示例问题
2. 实现对象打标可视化
3. 分析场景覆盖率
