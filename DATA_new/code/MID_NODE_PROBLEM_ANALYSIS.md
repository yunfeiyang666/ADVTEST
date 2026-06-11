# L2复杂模板的Mid节点问题分析与解决方案

## 问题描述

**模板示例**:
```
"Is there a {target_type} to the {direction1} of the {mid_type} 
 that is to the {direction2} of {ref_id}?"
```

**核心矛盾**:
- 如果`mid`不给具体id → 退化成L1问题
- 如果`ref→mid`有候选集 → 无法控制在gap附近
- 第一步不确定 → 后续约束失效

**示例**:
```
Gap: ego→car1→car2
模板: "Is there a truck to the front of the car that is to the left of building1?"

问题: 
- "the car that is to the left of building1" 可能匹配多个car
- 如果匹配到car5（不在gap附近），后续约束就偏离了
```

---

## 解决方案1: 强制Mid具体化（推荐）

### 思路
在模板中直接给出`mid`的具体id，避免第一步的不确定性

### 修改后的模板
```
"Is there a {target_type} to the {direction1} of {mid_id} 
 that is to the {direction2} of {ref_id}?"
```

### 示例
```
Gap: ego→car1→car2
模板: "Is there a truck to the front of car1 that is to the left of building1?"
                                        ^^^^
                                      具体id
```

### 优点
- 完全消除mid的不确定性
- 约束精准定位在gap附近
- 不会退化成L1问题

### 缺点
- 问题中出现具体id（如car1），可能不够自然
- 需要修改模板库

### 实现
```python
# template_library.py
L2_TEMPLATES = [
    {
        "template_id": "L2:referent_with_mid_id",
        "question_template": "Is there a {target_type} to the {direction1} of {mid_id} that is to the {direction2} of {ref_id}?",
        "constraint_methods": ["TypeFilter", "DirectionFilter", "TwoHopReferent"],
        "variables": {
            "target_type": "gap_target.type",
            "direction1": "r2.direction_4",
            "mid_id": "n2_id",  # 直接使用mid的id
            "direction2": "ref.direction_4",
            "ref_id": "ref.id"
        }
    }
]
```

---

## 解决方案2: 两阶段约束

### 思路
先用强约束锁定mid，再约束target

### 模板设计
```
"Is there a {target_type} to the {direction1} of the {mid_type} 
 that is {mid_constraint} and to the {direction2} of {ref_id}?"
```

### 示例
```
Gap: ego→car1→car2
模板: "Is there a truck to the front of the car that is near ego and to the left of building1?"
                                                      ^^^^^^^^^
                                                   强约束锁定mid
```

### 约束链
1. **Mid约束**: `near ego` → 锁定car1（唯一）
2. **Target约束**: `truck` + `to the front` → 锁定car2

---

## 解决方案3: Gap-Aware模板选择

### 思路
只在mid已经被gap确定的情况下使用这类模板

### 策略
```python
def select_template(gap, ctx):
    n1, n2, n3 = gap
    
    # 检查n2是否足够"特殊"（容易被唯一化）
    if is_unique_enough(n2, ctx):
        # 可以使用mid_type模板
        return "L2:referent_with_mid_type"
    else:
        # 必须使用mid_id模板
        return "L2:referent_with_mid_id"
```

---

## 解决方案4: 混合策略（最佳实践）

### 决策树
```
if gap.n2 is ego:
    use "L2:referent_with_mid_id"  # ego总是唯一
    
elif is_unique_enough(gap.n2):
    use "L2:referent_with_mid_type_and_constraint"  # 可唯一化
    
else:
    use "L2:referent_with_mid_id"  # 必须用id
```

---

## 推荐方案

### 短期方案（立即可用）
**方案1: 强制Mid具体化**

**实施步骤**:
1. 修改 `template_library.py` 中的L2模板
2. 将 `{mid_type}` 替换为 `{mid_id}`
3. 更新变量映射

### 中期方案（优化体验）
**方案4: 混合策略**

**实施步骤**:
1. 实现 `is_unique_enough()` 启发式函数
2. 扩展模板库，提供多种变体
3. 在模板选择时应用决策树

---

## 实现示例

### 方案1实现（推荐立即采用）

```python
# 修改前
OLD_TEMPLATE = {
    "question": "Is there a {target_type} to the {dir1} of the {mid_type} that is to the {dir2} of {ref_id}?",
    "variables": {"mid_type": "n2.type"}
}

# 修改后
NEW_TEMPLATE = {
    "question": "Is there a {target_type} to the {dir1} of {mid_id} that is to the {dir2} of {ref_id}?",
    "variables": {"mid_id": "n2_id"}
}
```

---

## 总结

| 方案 | 准确性 | 自然性 | 实现难度 | 推荐度 |
|------|--------|--------|----------|--------|
| 方案1: 强制Mid具体化 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| 方案2: 两阶段约束 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| 方案3: Gap-Aware选择 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 方案4: 混合策略 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**建议路线**:
1. **立即**: 采用方案1，修改模板使用`{mid_id}`
2. **1-2周**: 实现方案4的基础版本
3. **1-2月**: 完善智能选择逻辑
