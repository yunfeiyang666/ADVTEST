# 覆盖真实性问题分析

## 问题描述

用户提出的核心问题：**约束过程中用到的其他对象、边是否被正确记录为已覆盖？**

## 当前流程

### 1. Gap选择
```python
gap = "ego→car1→car2"  # 从tracker中选择一个未覆盖的L2路径
```

### 2. Context查询
```cypher
MATCH (ego:Object {unique_id:'ego'})-[r1:RELATES_TO]->(a:Object {unique_id:'car1'})
      -[r2:RELATES_TO]->(b:Object {unique_id:'car2'})
OPTIONAL MATCH (a)-[r3:RELATES_TO]->(sibling:Object)
  WHERE sibling.unique_id <> 'ego' AND sibling.unique_id <> 'car2'
RETURN ... siblings ...
```

返回结果：
- gap_target: `car2`
- siblings: `[car3, car4, car5]` (car1的其他邻居)

### 3. 约束收束 (ConstraintChain)

假设使用 `TypeFilter` 方法：
- 候选集: `[car2, car3, car4, car5]`
- 约束: "type = truck"
- 过滤后: `[car2]` (唯一)
- 生成问题: "What is the truck to the front of car1?"

**关键点**：这个问题的正确回答**依赖于**对 `car3, car4, car5` 的理解（它们不是truck）

### 4. 当前覆盖记录

```python
tracker.record_from_qa({
    "topology_level": "L2",
    "path_pattern": "ego→car1→car2",  # 只记录gap本身
    "template_id": "L2:type_filter",
    "question_id": "xxx"
})
```

**结果**：
- ✅ 记录: `ego→car1→car2` (L2)
- ✅ 级联记录: `ego→car1` (L1), `car1→car2` (L1)
- ✅ 级联记录: `ego`, `car1`, `car2` (L0)
- ❌ **未记录**: `ego→car1→car3`, `ego→car1→car4`, `ego→car1→car5`
- ❌ **未记录**: `car1→car3`, `car1→car4`, `car1→car5`
- ❌ **未记录**: `car3`, `car4`, `car5`

## 问题的严重性

### 场景1：TypeFilter约束

```
Gap: ego→car1→car2 (car2是truck)
Siblings: car3(car), car4(car), car5(pedestrian)

问题: "What is the truck to the front of car1?"
答案: car2

这个问题的正确性依赖于：
1. car3不是truck ← 需要知道car3的类型
2. car4不是truck ← 需要知道car4的类型  
3. car5不是truck ← 需要知道car5的类型
```

**当前记录**：只记录了car2被覆盖
**应该记录**：car2, car3, car4, car5都被覆盖（因为问题涉及它们的类型）

### 场景2：TwoHopReferent约束

```
Gap: ego→car1→car2
Referents: [building1, building2] (car2的二跳邻居)

问题: "What is the object to the front of car1 that is near building1?"
答案: car2

这个问题涉及：
- L2路径: ego→car1→car2
- L2路径: car2→building1 (二跳referent)
- L1边: car2→building1
```

**当前记录**：只记录了 `ego→car1→car2`
**应该记录**：`ego→car1→car2` + `car2→building1`

## 解决方案

### 方案1：在ConstraintChain中追踪使用的拓扑

修改 `TightenResult` 返回额外的覆盖信息：

```python
@dataclass
class TightenResult:
    question: str
    answer: str
    is_unique: bool
    method_used: str
    # 新增：约束过程中涉及的额外拓扑
    additional_coverage: Dict[str, List[str]] = field(default_factory=dict)
    # {
    #   "L0": ["car3", "car4", "car5"],
    #   "L1": ["car1->car3", "car1->car4", "car1->car5"],
    #   "L2": ["ego->car1->car3", "ego->car1->car4", "ego->car1->car5"]
    # }
```

### 方案2：从candidates推断覆盖

在 `record_from_qa` 时，根据约束方法推断涉及的拓扑：

```python
def record_from_qa_with_candidates(
    self,
    qa: Dict[str, Any],
    candidates: List[Dict],  # 约束前的候选集
    method_used: str,
) -> None:
    """记录覆盖，包括约束过程中涉及的候选对象"""
    
    # 1. 记录gap本身
    self.record_from_qa(qa)
    
    # 2. 记录候选集中的其他对象
    path_parts = qa.get("path_pattern", "").split("→")
    if len(path_parts) == 3:
        n1, n2, n3 = path_parts
        
        # 记录所有候选对象的L2路径
        for candidate in candidates:
            cand_id = candidate.get("id")
            if cand_id and cand_id != n3:
                # 记录 n1→n2→cand_id
                self._hit(self._L2, _l2_key_normalized(n1, n2, cand_id))
                self._hit(self._L1, _l1_key_normalized(n2, cand_id))
                self._hit(self._L0, _l0_key(cand_id))
```

### 方案3：从Cypher查询结果推断

分析Context Cypher的返回结果，提取所有涉及的节点和边：

```python
def extract_coverage_from_context(
    ctx: Dict,
    gap_path: str,
) -> Dict[str, List[str]]:
    """从context查询结果中提取所有涉及的拓扑"""
    
    n1, n2, n3 = gap_path.split("→")
    coverage = {
        "L0": [n1, n2, n3],
        "L1": [f"{n1}->{n2}", f"{n2}->{n3}"],
        "L2": [gap_path]
    }
    
    # 添加siblings
    sibling_ids = ctx.get("sibling_ids", []) or []
    for sib in sibling_ids:
        coverage["L0"].append(sib)
        coverage["L1"].append(f"{n2}->{sib}")
        coverage["L2"].append(f"{n1}->{n2}->{sib}")
    
    # 添加referents
    referents = ctx.get("referents", []) or []
    for ref in referents:
        ref_id = ref.get("id")
        if ref_id:
            coverage["L0"].append(ref_id)
            coverage["L1"].append(f"{n3}->{ref_id}")
            # L2: n2→n3→ref_id
            coverage["L2"].append(f"{n2}->{n3}->{ref_id}")
    
    return coverage
```

## 推荐方案

**方案3（从Cypher结果推断）+ 方案1（TightenResult追踪）的组合**：

1. **在Context查询后**：立即从ctx中提取所有siblings和referents，记录为"潜在覆盖"
2. **在ConstraintChain中**：追踪实际使用的约束信息，返回在 `TightenResult.additional_coverage`
3. **在record_from_qa时**：同时记录gap本身 + additional_coverage

### 实现优先级

1. **Phase 1（高优先级）**：实现方案3，记录siblings覆盖
   - 修改 `run_gap_pipeline_v6.py` 中的覆盖记录逻辑
   - 从 `ctx["sibling_ids"]` 提取并记录

2. **Phase 2（中优先级）**：实现referents覆盖
   - 从 `ctx["referents"]` 提取并记录

3. **Phase 3（低优先级）**：精细化追踪
   - 修改 `TightenResult` 添加 `additional_coverage`
   - 只记录约束方法**实际使用**的拓扑

## 预期效果

修改后，一个使用TypeFilter的L2问题将记录：
- ✅ Gap路径: `ego→car1→car2`
- ✅ Sibling路径: `ego→car1→car3`, `ego→car1→car4`, `ego→car1→car5`
- ✅ 级联L1: `car1→car2`, `car1→car3`, `car1→car4`, `car1→car5`
- ✅ 级联L0: `car2`, `car3`, `car4`, `car5`

**覆盖率将显著提升**，因为每个问题实际覆盖的拓扑比之前记录的多得多！

## 下一步

1. 确认方案选择
2. 实现Phase 1（siblings覆盖）
3. 测试验证覆盖率提升
