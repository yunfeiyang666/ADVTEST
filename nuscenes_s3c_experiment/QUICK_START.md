# 双坐标系VQA - 快速开始指南

## 📋 当前状态

✅ **数据已就绪**: 10个场景，334对象，13610关系，已导入Neo4j
✅ **双坐标系支持**: 所有关系包含ego和source两套完整数据  
⏳ **VQA评估**: 框架已搭建，等待问题数据和查询逻辑实现

---

## 🚀 验证数据

### 1. 验证场景图数据
```bash
python verify_dual_angles.py
```
**期望输出**: 显示scene-0103中car到pedestrian关系的双坐标系角度

### 2. 验证Neo4j数据
```bash
python verify_neo4j_dual_frame.py
```
**期望输出**:
- 13610条关系包含双坐标系数据
- 示例关系展示
- 方向查询测试

### 3. 在Neo4j Browser中测试

打开 http://localhost:7474 执行：

```cypher
// 查看dual frame数据示例
MATCH (src:Object)-[r:RELATES_TO]->(tgt:Object)
WHERE r.angle_source IS NOT NULL
RETURN src.unique_id, tgt.unique_id,
       r.angle_source, r.direction_8_source, r.angle_matches_source,
       r.angle_ego, r.direction_8_ego, r.angle_matches_ego
LIMIT 5
```

```cypher
// 测试angle_matches查询
MATCH (src:Object)-[r:RELATES_TO]->(tgt:Object)
WHERE 'back-right' IN r.angle_matches_ego
  AND tgt.type = 'pedestrian'
RETURN src.unique_id, tgt.unique_id, r.angle_ego
LIMIT 10
```

---

## 📝 下一步工作

### 你需要做的事情（按优先级）

#### 🔴 高优先级：准备VQA问题文件

创建文件：`vqa_questions_58.json`

格式：
```json
{
  "Q1": {
    "question": "自车前方有多少行人在移动？",
    "ground_truth": "2",
    "metadata": {
      "scene_name": "scene-0103",
      "frame_index": 38
    }
  },
  "Q2": {
    "question": "卡车后右方有行人在移动吗？",
    "ground_truth": "Yes",
    "metadata": {
      "scene_name": "scene-0103",
      "frame_index": 38
    }
  }
}
```

保存到：`output/vqa_questions_58.json`

#### 🟡 中优先级：实现查询逻辑

选择以下方案之一：

**方案A - 集成现有pipeline**（推荐）
```python
# 在evaluate_dual_frame_vqa.py中
from core_pipeline.vqa_pipeline.pipeline import VQAPipeline

def _query_neo4j_ego_frame(self, question_data):
    # 使用现有pipeline，但强制使用ego frame
    with VQAPipeline() as pipeline:
        result = pipeline.process_question(
            question_data['question'],
            verbose=False
        )
        return result.success, result.answer
```

**方案B - 简化实现**（快速原型）
```python
def _query_neo4j_ego_frame(self, question_data):
    # 基于问题模式匹配
    question = question_data['question']
    
    if "多少" in question and "行人" in question:
        # 计数查询
        cypher = """
        MATCH (ego:Object {unique_id: 'scene-0103_ego'})-[r:RELATES_TO]->(p:Object)
        WHERE p.type = 'pedestrian' 
          AND 'front' IN r.angle_matches_ego
        RETURN count(p) as count
        """
        # 执行查询...
```

#### 🟢 低优先级：答案验证

```python
def _check_answer(self, result, ground_truth):
    # 数值答案
    if result.isdigit() and ground_truth.isdigit():
        return int(result) == int(ground_truth)
    
    # Yes/No答案
    if result.lower() in ['yes', 'no']:
        return result.lower() == ground_truth.lower()
    
    # 其他情况，精确匹配
    return result.strip() == ground_truth.strip()
```

---

## 🎯 运行评估（准备好后）

```bash
python evaluate_dual_frame_vqa.py
```

**输出将包含**:
1. Ego Frame Only准确率
2. Source Frame Only准确率  
3. Retry机制准确率
4. 详细结果保存至 `output/vqa_dual_frame_evaluation.json`

---

## 🔍 查看现有数据

### 场景图数据
```bash
# 查看生成的场景图
cat output/scene_graphs/all_scene_graphs_full_relation.json | jq '.[] | select(.scene_name=="scene-0103") | .relationships[0]'
```

### Neo4j统计
```cypher
// 查看数据库统计
MATCH (n:Object) RETURN n.type, count(*) ORDER BY count(*) DESC

// 查看特定场景
MATCH (n:Object) WHERE n.scene_name = 'scene-0103' RETURN n

// 测试双坐标系差异
MATCH (src)-[r:RELATES_TO]->(tgt)
WHERE abs(r.angle_ego - r.angle_source) > 20
RETURN src.unique_id, tgt.unique_id, 
       r.angle_ego, r.angle_source,
       abs(r.angle_ego - r.angle_source) as angle_diff
ORDER BY angle_diff DESC
LIMIT 10
```

---

## 📚 文档参考

- **实施细节**: `DUAL_COORDINATE_IMPLEMENTATION.md`
- **完整进度**: `PROGRESS_REPORT.md`
- **代码注释**: 查看各Python文件中的docstring

---

## ❓ 常见问题

### Q: Neo4j中找不到ego节点？
A: 批量导入时添加了scene_name前缀，应该查询 `scene-0103_ego` 而不是 `ego`

### Q: angle_matches是什么？
A: 是一个列表，包含该角度匹配的所有方向标签，用于提高查询召回率

### Q: 什么时候用ego frame，什么时候用source frame？
A: 
- "我的前方"、"左边的车" → ego frame
- "卡车的后方"、"那辆车的右侧" → source frame
- 不确定？→ 用retry机制，两种都试

### Q: 如何调试Cypher查询？
A: 在Neo4j Browser (http://localhost:7474) 中直接执行查询，可以看到可视化结果

---

## 🎉 成功标准

完成后你应该能够：
- ✅ 运行58道题的完整评估
- ✅ 看到三种策略的准确率对比
- ✅ 证明双坐标系策略相比单一坐标系的优势
- ✅ 生成详细的评估报告

---

祝你顺利完成调研！有问题随时查看代码注释或联系。🚀
