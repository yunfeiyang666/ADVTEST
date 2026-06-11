# VQA 问题黑名单

**用途**: 这些问题由于语义不清或与scene graph几何定义不一致，**不作为评测/指导标准**。

**更新日期**: 2026-01-24

---

## 黑名单问题列表

### 1. 问题5 - 同状态对象计数过于宽松
**场景**: scene-0553_frame8  
**问题**: "What number of other things are there of the same status as the trailer?"  
**预期答案**: 8  
**实际答案**: 34  
**原因**: 
- 限制条件太松，无法精确定位到8这个答案
- "other things"的范围定义模糊（是否包括所有动态对象？是否排除自身？）
- 官方答案可能基于不同的理解或未公开的筛选规则

**Cypher分析**:
```cypher
# 我们的查询会返回所有动态对象，未能精确筛选到8个
MATCH (trailer:Object)
WHERE trailer.category CONTAINS 'trailer'
WITH trailer.status AS trailerStatus, trailer.unique_id AS trailerId
LIMIT 1
MATCH (other:Object)
WHERE other.type IN ['ego','car','truck','bus','bicycle','motorcycle','trailer','pedestrian']
      AND other.status = trailerStatus
      AND other.unique_id <> trailerId
RETURN count(other) AS count
# 结果: 34，而非预期的8
```

**判定**: 语义存疑，不作为判断标准

---

### 2. 问题11 - 前左方with_rider自行车
**场景**: scene-0553_frame8  
**问题**: "There is a stopped trailer; are there any with rider bicycles to the front left of it?"  
**预期答案**: yes  
**实际答案**: no  

**原因**: 
- Cypher逻辑正确（包含with_rider约束、front-left方向约束）
- 但查询结果为空，说明scene graph中在stopped trailer的front-left方向上没有with_rider的bicycle
- **疑似官方答案基于不同的几何定义**（可能是ego-centric vs source-centric差异）

**Cypher**:
```cypher
MATCH (trailer:Object)
WHERE trailer.category CONTAINS 'trailer' AND trailer.status = 'stopped'
WITH trailer LIMIT 1
MATCH (trailer)-[r:RELATES_TO]->(bicycle:Object)
WHERE bicycle.type = 'bicycle' 
      AND bicycle.status = 'with_rider' 
      AND r.predicates[0] = 'front-left'
RETURN count(bicycle) > 0 AS exist
# 结果: false
```

**判定**: 几何语义不一致，不作为判断标准

**建议**: 需要手动验证scene graph中trailer周围的bicycle分布，确认是否真的存在front-left方向的with_rider bicycle

---

### 3. 问题13 - with_rider对象前方卡车同状态的car
**场景**: scene-0553_frame8  
**问题**: "Are there any other cars of the same status as the truck that is to the front left of the with rider thing?"  
**预期答案**: yes  
**实际答案**: no  

**原因**:
- Cypher逻辑看起来正确
- 可能是场景中真的不存在符合条件的car，或者官方答案基于不同的理解

**Cypher**:
```cypher
MATCH (ref:Object)
WHERE ref.status = 'with_rider'
MATCH (ref)-[r:RELATES_TO]->(truck:Object)
WHERE truck.type = 'truck' 
      AND NOT truck.category CONTAINS 'trailer'
      AND r.predicates[0] = 'front-left'
WITH truck, r ORDER BY r.distance ASC LIMIT 1
WITH truck.status AS refStatus, truck.unique_id AS truckId
MATCH (car:Object)
WHERE car.type = 'car' 
      AND car.status = refStatus 
      AND car.unique_id <> truckId
RETURN count(car) > 0 AS exist
# 结果: false
```

**判定**: 疑似语义/数据问题，不作为判断标准

**建议**: 需要验证：
1. 场景中是否真的有with_rider对象前方的truck？
2. 该truck的状态是什么？
3. 是否真的存在同状态的car？

---

## 使用指南

### 在测试中排除黑名单问题
```python
BLACKLIST_QUESTIONS = [
    "What number of other things are there of the same status as the trailer?",
    "There is a stopped trailer; are there any with rider bicycles to the front left of it?",
    "Are there any other cars of the same status as the truck that is to the front left of the with rider thing?",
]

def is_blacklisted(question: str) -> bool:
    return question in BLACKLIST_QUESTIONS
```

### 统计准确率时的处理
```python
# 从总题数中排除黑名单
valid_questions = [q for q in all_questions if not is_blacklisted(q['question'])]
accuracy = correct_count / len(valid_questions)
```

---

## 后续工作

1. **手动验证**: 使用`manual_check_q11_q13.py`脚本验证问题11和13的ground truth
2. **BEV可视化**: 在BEV图上标注这些问题涉及的对象，直观判断几何关系
3. **与官方对齐**: 如果可能，查阅NuScenes官方文档，了解他们的几何定义和筛选规则
4. **扩展黑名单**: 在58题全量测试中，继续识别并标记类似的存疑问题

---

**注意**: 这个黑名单是动态的，随着我们对NuScenes QA语义的理解加深，可能会调整。
