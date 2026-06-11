# 双坐标系VQA实施进度报告

## ✅ 已完成任务

### 1. 数据生成和导入（100%完成）

#### 1.1 方向计算系统更新
- ✅ 新增`source_relative_angle_and_distance()`函数
- ✅ 新增`compute_direction_features_dual()`函数
- ✅ 实现三层重叠方向映射系统（2方位/4方位/8方位）
- **文件**: `core_pipeline/vqa_pipeline/direction_utils.py`

#### 1.2 场景图生成
- ✅ 修改`step2_full_relation_scene_graph.py`同时生成双坐标系数据
- ✅ 成功生成10个场景的完整数据
  - 334个对象
  - 13610条关系
  - 每条关系包含ego和source两套完整的角度/方向/位置数据
- **输出**: `output/scene_graphs/all_scene_graphs_full_relation.json`

#### 1.3 Neo4j导入
- ✅ 更新导入脚本支持双坐标系属性
- ✅ 批量导入所有10个场景到Neo4j
- ✅ 验证数据完整性：所有13610条关系都包含双坐标系数据
- **文件**: `core_pipeline/import_single_scene_to_neo4j.py`, `import_all_scenes_to_neo4j.py`

**关系属性示例**:
```
car1 -> pedestrian1:
  Source Frame: 
    angle_source: 134.7°
    direction_8_source: back-left
    angle_matches_source: ['back-left', 'back']
  Ego Frame:
    angle_ego: 112.6°
    direction_8_ego: back-left
    angle_matches_ego: ['back-left', 'back']
```

---

### 2. 评估框架搭建（50%完成）

#### 2.1 框架结构 ✅
- ✅ 创建`DualFrameEvaluator`类
- ✅ 定义三种评估策略：
  1. 仅Ego Frame
  2. 仅Source Frame
  3. Retry机制（Ego失败切换Source）
- ✅ 实现批量评估和结果保存逻辑
- **文件**: `evaluate_dual_frame_vqa.py`

#### 2.2 待实现部分 ⏳
- ⏳ `_query_neo4j_ego_frame()` - 具体的Ego Frame查询实现
- ⏳ `_query_neo4j_source_frame()` - 具体的Source Frame查询实现  
- ⏳ VQA问题文件准备（58道题目）
- ⏳ 答案匹配和验证逻辑

---

## 📊 数据统计

### Neo4j数据库状态
```
总场景数: 10
总对象数: 334
总关系数: 13610

对象类型分布:
- pedestrian: 130
- car: 117
- barrier: 41
- truck: 17
- bus: 9
- bicycle: 7
- motorcycle: 2
- trailer: 1
- ego: 10
```

### 双坐标系数据覆盖率
- 包含`angle_source`和`angle_ego`的关系: **13610/13610 (100%)**
- 包含`angle_matches_source`的关系: **13610/13610 (100%)**
- 包含`angle_matches_ego`的关系: **13610/13610 (100%)**

---

## 🔧 关键技术细节

### 方向匹配系统

#### 旧系统问题
- 每个方向占45°，边界严格
- 角度差1°可能导致查询失败
- 示例：`back-right`范围 [-157.5°, -112.5°]，-158°就不匹配

#### 新系统优势
三层重叠定义：
- **2方位**: 前/后各180°
- **4方位**: 前左/前右/后左/后右各90°  
- **8方位**: 传统8方向各45°

使用`angle_matches`列表包含多个方向标签，提高召回率：
```python
# 示例：angle=-156.1°
{
  'direction_8': 'back-right',
  'angle_matches': ['back', 'back-right']  # 同时匹配多个方向
}
```

### Cypher查询示例

**使用angle_matches查询**（推荐）:
```cypher
MATCH (src:Object)-[r:RELATES_TO]->(tgt:Object)
WHERE 'back-right' IN r.angle_matches_ego
  AND tgt.type = 'pedestrian'
RETURN src, tgt, r.angle_ego
```

**Ego Frame vs Source Frame对比**:
```cypher
// Ego Frame（以自车为参考）
MATCH (ego:Object {unique_id: 'scene-0103_ego'})-[r:RELATES_TO]->(obj)
WHERE 'front' IN r.angle_matches_ego
RETURN obj

// Source Frame（以source对象为参考）
MATCH (src:Object {unique_id: 'scene-0103_car1'})-[r:RELATES_TO]->(obj)
WHERE 'back-right' IN r.angle_matches_source
RETURN obj
```

---

## 📝 下一步工作

### 立即需要完成

#### A. 准备VQA问题数据
1. 收集或创建58道VQA测试题
2. 标注每题的ground truth答案
3. 准备问题文件格式：
```json
{
  "Q1": {
    "question": "...",
    "ground_truth": "...",
    "metadata": {
      "scene_name": "scene-0103",
      "frame_index": 38
    }
  }
}
```

#### B. 实现查询逻辑
需要实现两个核心函数的具体逻辑：

**1. `_query_neo4j_ego_frame()`**
- 解析问题提取关键信息（对象类型、方向、距离等）
- 生成使用`angle_matches_ego`的Cypher查询
- 执行查询并返回结果

**2. `_query_neo4j_source_frame()`**  
- 类似逻辑但使用`angle_matches_source`
- 需要识别问题中的source对象（如"卡车的后方"中的"卡车"）

**实现方式选项**:
- **方式1**: 集成现有LLM生成Cypher的pipeline
- **方式2**: 基于问题模式的规则匹配
- **方式3**: 混合方式（规则+LLM fallback）

#### C. 答案验证
实现`_check_answer()`逻辑：
- 精确匹配（Yes/No类问题）
- 数值比较（计数类问题）
- 对象ID匹配（识别类问题）
- 模糊匹配或LLM判断（复杂答案）

---

## 🔍 测试和验证

### 验证脚本
```bash
# 验证场景图数据
python verify_dual_angles.py

# 验证Neo4j导入
python verify_neo4j_dual_frame.py

# 测试Neo4j查询
# 在Neo4j Browser执行：
MATCH (src:Object)-[r:RELATES_TO]->(tgt:Object)
WHERE 'back-right' IN r.angle_matches_ego
RETURN src.unique_id, tgt.unique_id, r.angle_ego
LIMIT 10
```

### 预期评估流程
```bash
# 准备好VQA问题文件后
python evaluate_dual_frame_vqa.py

# 输出将包含：
# 1. Ego Frame准确率
# 2. Source Frame准确率
# 3. Retry机制准确率
# 4. 详细结果JSON
```

---

## 📁 文件清单

### 核心代码
- ✅ `core_pipeline/vqa_pipeline/direction_utils.py` - 方向计算
- ✅ `step2_full_relation_scene_graph.py` - 场景图生成
- ✅ `core_pipeline/import_single_scene_to_neo4j.py` - 单场景导入
- ✅ `import_all_scenes_to_neo4j.py` - 批量导入
- ⏳ `evaluate_dual_frame_vqa.py` - 评估框架（待完善）

### 数据文件
- ✅ `output/scene_graphs/all_scene_graphs_full_relation.json` - 场景图数据

### 测试脚本
- ✅ `verify_dual_angles.py` - 验证场景图
- ✅ `verify_neo4j_dual_frame.py` - 验证Neo4j数据
- ✅ `test_neo4j_import.py` - 测试导入

### 文档
- ✅ `DUAL_COORDINATE_IMPLEMENTATION.md` - 实施总结
- ✅ `PROGRESS_REPORT.md` - 本报告

---

## 💡 关键设计决策说明

### 为什么需要两套坐标系？

**问题场景**:
- 问题："卡车后方有行人在移动吗？"
- 如果卡车朝向与ego不同，用ego frame计算"后方"会不准确
- 应该用卡车自身朝向（source frame）来判断"后方"

**解决方案**:
- 同时存储两套坐标系数据
- Ego Frame: 适合"我的前方"、"左边的车"
- Source Frame: 适合"卡车的后方"、"那辆车的右侧"
- Retry机制: 先尝试ego，失败则切换source

### angle_matches的作用

传统系统：
```cypher
WHERE r.direction_8 = 'back-right'  // 严格匹配，角度-158°不匹配
```

新系统：
```cypher
WHERE 'back-right' IN r.angle_matches_ego  // 模糊匹配，提高召回率
```

`angle_matches`包含多个可能的方向标签，例如angle=-156.1°时：
- `direction_8`: 'back-right' （主方向）
- `angle_matches`: ['back', 'back-right'] （所有匹配的方向）

这样查询"后方"或"后右方"都能命中该关系。

---

## 🎯 成功标准

评估完成后，我们期望看到：

1. **Ego Frame准确率**: 基线性能
2. **Source Frame准确率**: 对比性能
3. **Retry准确率**: 应该 ≥ max(Ego, Source)

如果Retry准确率明显高于单独使用任一坐标系，说明双坐标系策略有效。

---

## 联系和支持

如有问题请查看：
- 代码中的注释和文档字符串
- Neo4j Browser测试查询
- 验证脚本输出

祝调研顺利！🚀
