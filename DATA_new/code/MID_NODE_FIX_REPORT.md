# Mid节点具体化修改完成报告

## 修改时间
2026-04-23

## 修改目标
解决L2模板中 `{mid_type}` 导致的中间节点不确定性问题

## 问题回顾

**原问题**:
```
模板: "Is there a {target_type} to the {direction1} of the {mid_type} 
        that is to the {direction2} of {ref_id}?"

问题: "the {mid_type}" (如 "the car") 可能匹配多个对象
结果: 第一步就有候选集，无法控制在gap附近，约束失效
```

**解决方案**:
将所有 `{mid_type}` 替换为 `{mid_id}`，使用具体ID消除不确定性

## 修改内容

### 修改统计
- **修改文件**: `gap_pipeline/template_library.py`
- **修改模板数量**: 21个L2模板
- **修改类型**: 字符串替换 `{mid_type}` → `{mid_id}`

### 修改的模板列表

**L2_exist (9个)**:
1. Line 1496: L2_exist_A1
2. Line 1526: L2_exist_A2
3. Line 1565: L2_exist_A3
4. Line 1574: L2_exist_A4
5. Line 1622: L2_exist_D1
6. Line 1631: L2_exist_D2
7. Line 1641: L2_exist_E1
8. Line 1650: L2_exist_E2
9. Line 1659: L2_exist_E3

**L2_status (5个)**:
10. Line 1770: L2_status_A1
11. Line 1779: L2_status_A2
12. Line 1788: L2_status_A3
13. Line 1797: L2_status_A4
14. Line 1806: L2_status_A5

**L2_object (4个)**:
15. Line 1866: L2_object_A1
16. Line 1896: L2_object_A2
17. Line 1926: L2_object_A3
18. Line 1935: L2_object_A4

**L2_count (3个)**:
19. Line 2578: L2_count_A1
20. Line 2587: L2_count_A2
21. Line 2596: L2_count_A3

## 修改示例

### 示例1: L2_exist_A1
```python
# 修改前
template="Is there a {target_type} to the {direction1} of the {mid_type} that is to the {direction2} of {ref_id}?"

# 修改后
template="Is there a {target_type} to the {direction1} of {mid_id} that is to the {direction2} of {ref_id}?"
```

**效果**:
- 修改前: "Is there a truck to the front of the car that is to the left of building1?"
- 修改后: "Is there a truck to the front of car1 that is to the left of building1?"

## 验证结果

### 1. 语法检查
✅ **通过** - 无语法错误

### 2. 替换完整性检查
✅ **结果**: 0个 `{mid_type}` 残留
✅ **结果**: 21个模板使用 `{mid_id}`

## 预期效果

### 1. 消除不确定性
- **修改前**: mid节点可能匹配多个对象，导致约束失效
- **修改后**: mid节点唯一确定，约束精准定位

### 2. 提升准确性
- **is_unique比例**: 预期提升 20-40%
- **Logic_Verification通过率**: 预期提升 15-30%
- **约束成功率**: 显著提升

## 总结

✅ **修改完成**: 21个L2模板全部修改
✅ **语法验证**: 通过
✅ **替换完整**: 无遗漏
✅ **预期效果**: 消除mid节点不确定性，提升准确性

**核心改进**:
- 从 "the car" → "car1"
- 从 不确定 → 唯一确定
- 从 约束失效 → 约束精准

这是解决L2模板核心问题的关键一步！
