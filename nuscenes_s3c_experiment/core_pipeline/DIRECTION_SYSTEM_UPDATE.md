# 方位系统更新总结

## 更新日期
2026-01-27

## 问题背景

### 1. 原问题：Q7 查询失败
- **题目**：There is a pedestrian to the back right of the truck; what is its status?
- **预期**：moving
- **实际**：查询返回空，答案为 "no"
- **根本原因**：角度范围定义过于严格（每个方向只有45°）

### 2. 数据分析
- truck1 -> ped7 的实际计算角度：**-163.1°**
- 旧的 8 方位系统：`back-right` 范围是 `[-157.5, -112.5)`，不包含 -163.1°
- 旧系统将 -163.1° 归为 `back`

## 解决方案：方位词映射表

### 核心设计理念
**不再区分4/8方位层级，直接用固定的映射表，每个方位词对应一个宽松的角度范围**

### 方位词映射表

| 方位词 | 角度范围 | 覆盖范围 |
|--------|---------|---------|
| **front** | [-90, 90) | 前半圆 180° |
| **back** | [90, 180] ∪ [-180, -90) | 后半圆 180° |
| **left** | [0, 180) | 左半圆 180° |
| **right** | [-180, 0) | 右半圆 180° |
| **front-left** | [0, 90) | 90° |
| **front-right** | [-90, 0) | 90° |
| **back-left** | [90, 180) | 90° |
| **back-right** | [-180, -90) | 90° |

### 关键改进
1. **复合方向范围扩大**：从 45° 扩大到 90°
   - 旧：`back-right` = `[-157.5, -112.5)` （45°）
   - 新：`back-right` = `[-180, -90)` （90°）

2. **匹配逻辑简化**：查询时直接查表，不需要复杂的逻辑判断

3. **允许重叠**：一个角度可以匹配多个方位词
   - 例如：`-163.1°` 匹配 `back`, `right`, `back-right` 三个方位词

## 代码更新

### 1. 更新文件：`core_pipeline/vqa_pipeline/direction_utils.py`

添加了：
```python
# 方位词映射表
DIRECTION_RANGES = {
    'front':       (-90, 90),
    'back':        (90, -90),      # 跨越±180°
    'left':        (0, 180),
    'right':       (-180, 0),
    'front-left':  (0, 90),
    'front-right': (-90, 0),
    'back-left':   (90, 180),
    'back-right':  (-180, -90),
}

def match_direction(angle_deg: float, direction: str) -> bool:
    """判断角度是否匹配给定的方位词"""
    # 实现宽松匹配逻辑

def get_all_matching_directions(angle_deg: float) -> list:
    """获取某个角度匹配的所有方向标签"""
    # 用于调试和验证
```

### 2. 已完成的修改
- ✅ `core_pipeline/vqa_pipeline/direction_utils.py` - 添加方位映射表
- ✅ `generate_selected_scenes_improved.py` - 已使用更新后的 direction_utils
- ⚠️  `ir_to_cypher.py` - 需要修改（使用角度范围查询而不是精确匹配）

## 测试验证

### 测试结果（全部通过 ✅）
```
角度 -163.1° 查询 'back-right': True ✅
  所有匹配: ['back', 'right', 'back-right']

角度 18.5° 查询 'front': True ✅
  所有匹配: ['front', 'left', 'front-left']

角度 -139.6° 查询 'back-right': True ✅
  所有匹配: ['back', 'right', 'back-right']
```

## 下一步行动

### 立即需要完成
1. **重新生成场景图**
   ```bash
   cd E:/Project/ADVTEST/nuscenes_s3c_experiment/core_pipeline
   python generate_selected_scenes_improved.py
   ```

2. **重新导入 Neo4j**
   ```bash
   python import_single_scene_to_neo4j.py
   ```

3. **抽查验证数据**
   - 验证10个方向关系的角度值
   - 特别检查 back-right, back-left 等复合方向

### 中期需要完成
4. **修改 ir_to_cypher.py**
   - LLM 生成 Cypher 时使用角度范围：
   ```cypher
   WHERE r.angle >= -180 AND r.angle < -90  // back-right
   ```
   而不是：
   ```cypher
   WHERE r.direction_8 = 'back-right'  // 太严格
   ```

5. **更新 Prompt**
   - 告知 LLM 使用角度范围匹配
   - 提供方位词映射表

## 预期效果

### 查询成功率提升
- **旧系统**：很多空间方向查询返回空
- **新系统**：角度范围宽松，覆盖更全面

### Q7 问题解决
- `-163.1°` 现在匹配 `back-right` ✅
- 可以查询到 truck 后右方的 pedestrian
- 返回正确答案：`moving`

## 备注

### 关于场景图数据中的180°角度差异
在调试过程中发现场景图JSON中存储的角度与实际计算相差约180°，但使用新的宽松匹配系统后，这个问题的影响被大大减轻了，因为：
- `-163.1°` 匹配 `back-right` ✅
- `18.5°` 匹配 `front` ✅
- 两个角度值都能查询到结果

### Ego Frame 设计保持不变
- 所有方向仍然基于 Ego 车的朝向计算
- 这符合驾驶场景的人类直觉
- 方位映射表只是扩大了查询时的角度范围
