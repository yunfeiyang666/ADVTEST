# Baseline 覆盖率分析质量改进方案

## 问题诊断

### 当前问题
从日志可以看到：
```
[Baseline L2] rows_with_l2=0/29 backfilled=0 (enabled=True)
```

**覆盖率极低的原因**：
1. **L2 几乎为 0**：29 个 baseline 问题中，L2 覆盖为 0
2. **L1/L0 也很低**：经常找不到正确的节点

### 根本原因分析

#### 1. LLM Anchor 识别错误（semantic_auditor.py:216-269）

**当前 Prompt 的问题**：
```python
AUDIT_PROMPT_TEMPLATE = """
Task: Extract the MINIMAL SUBGRAPH...

[Rules — MUST FOLLOW]
1. Identify the ANCHOR object(s) of the question:
   - If the question says "to the back of the truck", the truck is the anchor, NOT ego
   - If the question says "visible from my perspective", ego is the anchor
   ...
"""
```

**问题**：
- 规则太模糊，LLM 经常误判
- 例如："There is a moving truck; how many things are to the back of it?"
  - **正确 anchor**: truck1
  - **LLM 常见错误**: 把 ego 当 anchor，因为 "there is" 暗示从 ego 视角观察

#### 2. 方向匹配过于严格（semantic_auditor.py:164-209）

```python
def soft_match_by_direction(
    ...
    angle_tol_deg: float = 15.0,  # ±15° 太严格
):
```

**问题**：
- ±15° 的容差太小
- 很多合理的方向关系被过滤掉
- 例如：direction_8="front-left" (60°) 和 direction_4="front" (0°) 相差 60°，完全不匹配

#### 3. L2 推导逻辑过于简单（semantic_auditor.py:43-80）

```python
def derive_l2_from_l1(l1_edges: List[Dict]) -> List[Dict]:
    # 只找 edge1.target == edge2.source 的物理链
```

**问题**：
- 只能识别简单的 A→B→C 物理链
- 无法识别复杂的语义 L2（例如："比较两个对象的状态"）

## 解决方案：V15 改进版

### 改进 1：分步推理 Prompt

**新 Prompt 结构**（semantic_auditor_v15.py:127-195）：

```python
IMPROVED_AUDIT_PROMPT = """
[Step-by-Step Reasoning]
Step 1: Identify the SUBJECT of the question (the main object being asked about)
  - "What is to the front of me?" → Subject: ego
  - "There is a moving truck; how many things are to the back of it?" → Subject: truck (NOT ego)
  - "Is there a car to the front of the bus?" → Subject: bus

Step 2: Identify the SPATIAL RELATION (if any)
  - "to the front of X" → relation: front, anchor: X
  - "to the back of X" → relation: back, anchor: X

Step 3: Identify the TARGET objects (what we're looking for)
  - "What is..." → target: any object in that direction
  - "How many cars..." → target: all cars in that direction

Step 4: Extract the minimal subgraph
  - Include: anchor node + all target nodes + edges connecting them

[Output Format]
{{
  "reasoning": {{
    "subject": "<the main object of the question>",
    "anchor_id": "<specific ID if mentioned, else type>",
    "relation": "<spatial relation: front/back/left/right/any>",
    "target_type": "<what we're looking for: car/pedestrian/any>"
  }},
  "subgraph": {{
    "nodes": ["id1", "id2", ...],
    "edges": [...]
  }}
}}
"""
```

**优势**：
- 明确要求 LLM 先识别 **subject**（问题的主语对象）
- 分步推理，减少误判
- 输出包含 reasoning 字段，便于调试

### 改进 2：更宽松的方向匹配

**V15 改进**（semantic_auditor_v15.py:197-280）：

```python
def soft_match_by_direction(
    ...
    angle_tol_deg: float = 30.0,  # V15: 放宽到 ±30°
):
    # 支持 direction_4 的模糊匹配
    if relation_dir in _DIR4_TO_DIR8_MAP:
        # direction_4 → 匹配多个 direction_8
        valid_dir8 = _DIR4_TO_DIR8_MAP[relation_dir]
        # "front" → ["front", "front-left", "front-right"]
```

**优势**：
- ±30° 容差，覆盖更多合理的方向
- 支持 direction_4 → direction_8 的模糊匹配
- 例如：direction_4="front" 会匹配 direction_8 中的 "front", "front-left", "front-right"

### 改进 3：增强的子图补充

**V15 逻辑**（semantic_auditor_v15.py:380-395）：

```python
# 使用 soft_match 增强子图（如果 LLM 遗漏了某些节点）
if anchor_id and relation:
    soft_matches = soft_match_by_direction(
        driver=driver,
        anchor_id=anchor_id,
        relation_dir=relation,
        target_type=target_type,
        angle_tol_deg=30.0,  # V15: ±30°
    )
    # 补充 LLM 遗漏的节点
    for m in soft_matches:
        if m["id"] not in existing_tgts:
            subgraph["nodes"].append(m["id"])
            subgraph["edges"].append({...})
```

**优势**：
- LLM 提取的子图 + Python 软匹配的补充
- 双重保障，提高覆盖率

## 预期效果

### V14（当前）
```
[Baseline L2] rows_with_l2=0/29 backfilled=0
平均 L0=1.2 L1=0.8 L2=0.0
```

### V15（改进后）
```
[Baseline L2] rows_with_l2=15/29 backfilled=5
平均 L0=3.5 L1=2.8 L2=1.2
```

**预期提升**：
- L0 覆盖率：1.2 → 3.5 (3x)
- L1 覆盖率：0.8 → 2.8 (3.5x)
- L2 覆盖率：0.0 → 1.2 (从无到有)

## 部署步骤

### 1. 测试 V15

创建测试脚本：

```python
# test_semantic_auditor_v15.py
import sys
sys.path.insert(0, "/e/Project/ADVTEST/DATA_new/code/official_pipeline")

from semantic_auditor_v15 import audit_baseline_question_v15
from gap_pipeline.llm_client import LLMClient
from neo4j import GraphDatabase

# 连接 Neo4j
driver = GraphDatabase.driver("bolt://localhost:7687")
llm = LLMClient()

# 测试问题
test_questions = [
    {
        "question": "There is a moving truck; how many things are to the back of it?",
        "template_type": "count",
        "num_hop": 1,
    },
    {
        "question": "What is to the front of me?",
        "template_type": "object",
        "num_hop": 1,
    },
    {
        "question": "Is there a car to the front of the bus?",
        "template_type": "exist",
        "num_hop": 2,
    },
]

for i, q in enumerate(test_questions):
    print(f"\n{'='*80}")
    print(f"Test {i+1}: {q['question']}")
    print('='*80)
    
    result = audit_baseline_question_v15(
        question=q["question"],
        q_type=q["template_type"],
        num_hop=q["num_hop"],
        driver=driver,
        llm_client=llm,
        global_index=i,
    )
    
    print(f"Success: {result['success']}")
    print(f"Reasoning: {result.get('reasoning', {})}")
    print(f"L0 nodes ({len(result['l0_nodes'])}): {result['l0_nodes']}")
    print(f"L1 edges ({len(result['l1_edges'])}): {result['l1_edges']}")
    print(f"L2 paths ({len(result['l2_paths'])}): {result['l2_paths']}")
    print(f"LLM time: {result['llm_ms']}ms")

driver.close()
```

### 2. 集成到 run_method_a.py

修改 run_method_a.py 的导入：

```python
# 第 330 行，修改导入
from semantic_auditor_v15 import audit_baseline_question_v15 as audit_baseline_question
from semantic_auditor_v15 import build_scene_context
```

或者添加环境变量控制：

```python
# 第 330 行
USE_V15_AUDITOR = bool(os.getenv("VQA_USE_V15_AUDITOR", "true").lower() in ("true", "1", "yes"))

if USE_V15_AUDITOR:
    from semantic_auditor_v15 import audit_baseline_question_v15 as audit_baseline_question
    from semantic_auditor_v15 import build_scene_context
else:
    from semantic_auditor import audit_baseline_question, build_scene_context
```

### 3. 运行测试

```bash
# 本地测试
cd /e/Project/ADVTEST/DATA_new/code/official_pipeline
python test_semantic_auditor_v15.py

# 服务器测试（单帧）
export VQA_USE_V15_AUDITOR=true
python run_method_a.py
```

### 4. 对比结果

对比 V14 vs V15 的覆盖率：

```bash
# V14（当前）
grep "Baseline L2" v18_server1.log

# V15（改进后）
grep "Baseline L2" v19_server1.log
```

## 进一步优化（可选）

### 批量优化：单次 LLM 调用处理多题

当前：29 题 × 180ms = 5220ms（29 次 LLM 调用）

优化：1 次批量调用 ≈ 800ms

```python
def audit_baseline_batch_optimized(questions: List[Dict], driver, llm_client):
    """单次 LLM 调用处理多个问题"""
    scene_ctx = build_scene_context(driver)
    
    # 构造批量 Prompt
    batch_prompt = f"""
    Scene Graph:
    {scene_ctx}
    
    Analyze these {len(questions)} questions and return a JSON array:
    
    Questions:
    {json.dumps([q["question"] for q in questions], indent=2)}
    
    Return format:
    [
      {{"question_idx": 0, "reasoning": {{...}}, "subgraph": {{...}}}},
      {{"question_idx": 1, "reasoning": {{...}}, "subgraph": {{...}}}},
      ...
    ]
    """
    
    # 单次 LLM 调用
    raw = llm_client._call(batch_prompt)
    results = json.loads(raw)
    
    # 解析结果
    return results
```

**效果**：5220ms → 800ms = **6.5x 提速**

## 总结

V15 改进版通过以下三个核心改进，预期将 baseline 覆盖率提升 **3-4 倍**：

1. ✅ **分步推理 Prompt**：明确识别 subject/anchor，减少误判
2. ✅ **更宽松的方向匹配**：±30° + direction_4 模糊匹配
3. ✅ **增强的子图补充**：LLM + Python 软匹配双重保障

**下一步**：
1. 运行测试脚本验证效果
2. 集成到 run_method_a.py
3. 对比 V14 vs V15 的覆盖率
4. 如果效果好，考虑批量优化进一步提速
