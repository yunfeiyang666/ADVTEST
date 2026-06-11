# 双坐标系VQA实现总结

## 已完成工作

### 1. 方向计算函数更新 ✅
**文件**: `core_pipeline/vqa_pipeline/direction_utils.py`

- 新增 `source_relative_angle_and_distance()` - 基于source对象朝向
- 新增 `compute_direction_features_dual()` - 同时计算ego和source坐标系
- 更新方向映射系统：三套重叠定义（2方位/4方位/8方位）

### 2. 场景图生成更新 ✅
**文件**: `step2_full_relation_scene_graph.py`

- 每条关系同时存储双坐标系数据：
  - `angle_source` / `angle_ego`
  - `direction_source` (含direction_8, angle_matches) 
  - `direction_ego` (含direction_8, angle_matches)
  - `relative_position_source` / `relative_position_ego`

**生成的场景图**:
- 文件: `output/scene_graphs/all_scene_graphs_full_relation.json`
- 包含10个场景，334个对象，13610条关系

### 3. Neo4j导入脚本更新 ✅
**文件**: `core_pipeline/import_single_scene_to_neo4j.py`

- `_extract_relationship_properties()` 方法更新以存储双坐标系属性
- 支持以下关系属性：
  ```
  - angle_source, direction_8_source, angle_matches_source
  - angle_ego, direction_8_ego, angle_matches_ego
  - relative_x/y/z_source 和 relative_x/y/z_ego
  ```
- 兼容旧数据格式

### 4. 数据验证 ✅

**验证场景**: scene-0103（24个对象，552条关系）

**示例数据**:
```
car1 -> pedestrian1:
  Source Frame: angle=134.7°, direction_8=back-left
  Ego Frame: angle=112.6°, direction_8=back-left
  
car1 -> pedestrian2:
  Source Frame: angle=-156.1°, direction_8=back-right
  Ego Frame: angle=-178.3°, direction_8=back
```

## 下一步工作

### A. 批量导入所有场景到Neo4j
```bash
# 需要创建批量导入脚本
python import_all_scenes_to_neo4j.py
```

### B. 实现双坐标系VQA查询策略

#### B1. 修改Cypher查询生成
需要修改LLM生成的Cypher，支持两种查询模式：

**Ego Frame查询**（当前默认）:
```cypher
MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->(p:Object)
WHERE p.type = 'pedestrian' 
  AND 'back-right' IN r.angle_matches_ego  // 使用ego坐标系
  AND 'moving' IN p.status
RETURN p
```

**Source Frame查询**（新增）:
```cypher
MATCH (source:Object {unique_id: 'car1'})-[r:RELATES_TO]->(p:Object)
WHERE p.type = 'pedestrian'
  AND 'back-right' IN r.angle_matches_source  // 使用source坐标系
  AND 'moving' IN p.status
RETURN p
```

#### B2. 实现Retry机制
当ego frame查询失败时，自动切换到source frame重试：

```python
def query_with_retry(question, graph_context):
    # 1. 尝试ego frame
    result_ego = query_with_ego_frame(question, graph_context)
    if result_ego.success:
        return result_ego
    
    # 2. 失败则尝试source frame
    result_source = query_with_source_frame(question, graph_context)
    return result_source
```

#### B3. 评估对比实验

在58道VQA题目上分别测试：
1. 仅使用ego frame的正确率
2. 仅使用source frame的正确率
3. 使用retry切换机制的正确率

### C. 更新VQA Pipeline

需要修改的文件：
- `core_pipeline/vqa_pipeline/vqa_executor.py` - 添加retry逻辑
- `core_pipeline/vqa_pipeline/cypher_generator.py` - 支持双坐标系查询生成
- Prompt模板 - 告知LLM可以选择坐标系

## 关键设计决策

### 为什么需要两套坐标系？

1. **Ego Frame**: 适合以自车为中心的问题
   - "我的前方有什么？"
   - "左边最近的车是什么？"

2. **Source Frame**: 适合以特定对象为中心的问题
   - "卡车后面有什么？"
   - "那辆车的右侧有行人吗？"

3. **问题**: 有些对象（如静止的车辆）的朝向与ego不同，导致ego frame不准确

### 新的方向匹配系统

**旧系统**: 每个方向占45°，边界严格
- 问题: 角度差1°可能导致查询失败

**新系统**: 三套重叠定义
- 2方位: 前/后各180° 
- 4方位: 前左/前右/后左/后右各90°
- 8方位: 传统8方向各45°

- 优势: `angle_matches` 包含多个可能的方向标签，提高召回率

## 测试命令

### 测试Neo4j中的双坐标系数据
```cypher
// 在Neo4j Browser中运行
MATCH (car1:Object {unique_id: 'car1'})-[r:RELATES_TO]->(p:Object)
WHERE p.type = 'pedestrian'
RETURN car1.unique_id, p.unique_id, r.distance,
       r.angle_source, r.direction_8_source, r.angle_matches_source,
       r.angle_ego, r.direction_8_ego, r.angle_matches_ego
LIMIT 5
```

### 验证场景图数据
```bash
python verify_dual_angles.py
```

## 文件清单

### 核心代码
- ✅ `core_pipeline/vqa_pipeline/direction_utils.py`
- ✅ `step2_full_relation_scene_graph.py`
- ✅ `core_pipeline/import_single_scene_to_neo4j.py`

### 生成的数据
- ✅ `output/scene_graphs/all_scene_graphs_full_relation.json`

### 测试脚本
- ✅ `verify_dual_angles.py`
- ✅ `test_neo4j_import.py`

### 待实现
- ⏳ `import_all_scenes_to_neo4j.py` - 批量导入
- ⏳ `core_pipeline/vqa_pipeline/dual_frame_vqa.py` - 双坐标系VQA
- ⏳ `evaluate_dual_frame_vqa.py` - 评估对比实验
