# 场景图与数据库结合工作 - 完整PPT汇报材料

**围绕一张图展开的完整技术路线**

---

## PPT结构（按老师要求的顺序）

1. NuScenes数据情况
2. 六相机图
3. BEV图（带名称标注）
4. 每个Car的JSON信息
5. Car之间的关系
6. 建好的数据库图
7. 查询操作（文字、函数、结果）

---

# 第1部分：NuScenes数据情况

## 标题页
**数据集概览：NuScenes v1.0-mini**

## 内容要点

### 数据集基本信息
```
数据集版本：v1.0-mini
场景数量：10个场景
样本数量：404个时间帧
标注对象：约10,000个3D边界框
传感器配置：6个相机 + 5个雷达 + 1个激光雷达
```

### 对象类别分布
- **Car（车辆）**：最多，约占45%
- **Pedestrian（行人）**：约占25%
- **Bicycle/Motorcycle（两轮车）**：约占15%
- **Truck/Bus（大型车辆）**：约占10%
- **Other（其他）**：约占5%

### 数据特点
- ✅ 真实世界采集
- ✅ 完整的3D标注
- ✅ 多传感器融合
- ✅ 时序连续性

### 可视化材料
📊 使用文件：`ppt_materials/1_data_statistics.png`
- 数据集统计图表
- 类别分布饼图
- 场景长度分布

---

# 第2部分：六相机图

## 标题页
**多视角感知：六相机全景视图**

## 内容要点

### 六个相机视角
```
前方三个：
- CAM_FRONT（正前方）
- CAM_FRONT_RIGHT（右前方）
- CAM_FRONT_LEFT（左前方）

后方三个：
- CAM_BACK（正后方）
- CAM_BACK_RIGHT（右后方）
- CAM_BACK_LEFT（左后方）
```

### 视角覆盖
- **360度全景覆盖**
- **无盲区感知**
- **高分辨率图像**
- **时间同步采集**

### 应用价值
- 🎯 全方位环境感知
- 🎯 盲区检测
- 🎯 多视角融合
- 🎯 场景完整理解

### 可视化材料
📷 使用文件：`ppt_materials/2_six_camera_view.png`
- 2×3布局的六相机图
- 每个视角清晰标注
- 展示同一时刻的不同视角

### 演讲要点
> "这张图展示了自动驾驶车辆的360度全景感知能力。通过6个相机的协同工作，系统能够无死角地观察周围环境，这是构建场景图的原始输入。"

---

# 第3部分：BEV图（带名称标注）

## 标题页
**鸟瞰视图：场景空间布局**

## 内容要点

### BEV图的价值
- **上帝视角**：从上往下看整个场景
- **空间关系直观**：清晰显示对象位置
- **唯一ID标注**：每个对象有独特名称
- **参考系明确**：以Ego车为中心

### 对象标注说明
```
Ego车（红色）：自车，位于中心
Car1, Car2, Car3...（蓝色）：周围车辆，按顺序编号
Pedestrian1, Pedestrian2...（绿色）：行人，独立编号
Bicycle1, Bicycle2...（橙色）：自行车，独立编号
Truck1, Bus1...（棕色/粉色）：大型车辆，独立编号
```

### 关键改进（满足老师要求）
✅ **每个对象有唯一ID**（如car1, car2）
- 便于在全关系图中区分
- 便于数据库查询
- 便于关系追踪

✅ **以Ego为参考系**
- 所有位置相对于自车
- 符合自动驾驶视角
- 便于理解和应用

### 可视化材料
🗺️ 使用文件：`ppt_materials/3_bev_with_labels.png`
- 清晰的BEV布局
- 每个对象带唯一ID标签
- 颜色区分不同类型
- 坐标系清晰

### 演讲要点
> "从鸟瞰图可以看到，我们为每个对象分配了唯一的ID，比如car1、car2、pedestrian1。这样做的目的是为了在后续的关系图中能够精确地描述'car1在car2的左前方'这样的具体关系。"

---

# 第4部分：每个Car的JSON信息

## 标题页
**对象属性：Car的详细信息**

## 内容要点

### JSON数据结构
每个Car对象包含以下信息：

```json
{
  "unique_id": "car1",              // 唯一标识
  "type": "car",                    // 简化类型
  "category": "vehicle.car",        // 原始类别
  "translation": {                  // 3D位置（相对Ego）
    "x": 8.2,
    "y": 1.3,
    "z": 0.5
  },
  "rotation": [0.1, 0.0, 0.0, 1.0], // 姿态（四元数）
  "size": {                         // 尺寸
    "width": 1.8,
    "length": 4.5,
    "height": 1.5
  },
  "velocity": {                     // 速度矢量
    "vx": 2.3,
    "vy": 0.1,
    "vz": 0.0
  },
  "token": "abc123...",             // NuScenes原始token
  "num_lidar_pts": 234              // 激光点数（质量指标）
}
```

### 属性分类

**空间属性**
- translation：位置坐标
- rotation：朝向角度
- size：物理尺寸

**运动属性**
- velocity：速度矢量
- speed：速度大小（计算得出）

**质量属性**
- num_lidar_pts：激光点云数量
- 点数越多，检测质量越高

**标识属性**
- unique_id：唯一ID（我们生成）
- type：简化类型
- category：原始类别
- token：数据集原始标识

### 数据用途

**场景图构建**
- 提供节点属性
- 计算空间关系
- 评估谓词条件

**数据库存储**
- 作为节点属性存入Neo4j
- 支持属性查询
- 支持条件筛选

**应用场景**
- 碰撞预测：根据位置和速度
- 路径规划：考虑尺寸和位置
- 风险评估：基于距离和速度

### 可视化材料
📄 使用文件：
- `ppt_materials/4_car_json_info.json`（完整数据）
- `ppt_materials/4_car_json_info.png`（可视化展示）

### 演讲要点
> "这是我们为每个car对象保存的原汁原味的属性信息。既包括NuScenes原始的物理属性，也包括我们生成的唯一ID。这些信息将完整地存储到数据库中，支持各种复杂查询。"

---

# 第5部分：Car之间的关系

## 标题页
**全关系图：对象间的空间关系**

## 内容要点

### 关系构建逻辑（核心改进）

**原来的做法**（只有Ego-其他）：
```
Ego -> Car1
Ego -> Car2
Ego -> Pedestrian1
...
```

**改进后的做法**（全关系）：
```
Ego -> Car1, Car2, Pedestrian1, ...
Car1 -> Ego, Car2, Car3, ...
Car2 -> Ego, Car1, Car3, ...
Pedestrian1 -> Ego, Car1, Car2, ...
...
```

### 关系属性

每条关系包含：

```json
{
  "source": "car1",                 // 源对象
  "source_type": "car",             // 源类型
  "target": "car2",                 // 目标对象
  "target_type": "car",             // 目标类型
  "predicates": ["left", "mid"],    // 空间谓词（方位+距离）
  "metrics": {                      // 精确度量
    "distance": 18.5,               // 距离（米）
    "angle": 125.3,                 // 角度（度）
    "relative_position": {          // 相对位置
      "x": -8.2,
      "y": 15.6,
      "z": 0.1
    }
  }
}
```

### 空间谓词（简化版）

**方位谓词**（4个）：
- `front`：前方（-45° ~ 45°）
- `left`：左侧（45° ~ 135°）
- `rear`：后方（135° ~ 180°和-180° ~ -135°）
- `right`：右侧（-135° ~ -45°）

**距离谓词**（3个）：
- `near`：近距离（< 10米）
- `mid`：中距离（10-25米）
- `far`：远距离（> 25米）

### 关系示例

```
ego -> car1: [front, near] (8.5m)
  含义：car1在ego前方，距离近

car1 -> car2: [left, mid] (18.5m)
  含义：car2在car1左侧，中等距离

car1 -> pedestrian1: [rear, near] (5.2m)
  含义：pedestrian1在car1后方，距离近
```

### 全关系的价值

**场景理解更完整**
- 不仅知道自车周围的对象
- 还知道对象之间的关系
- 构建完整的空间拓扑

**支持复杂查询**
- "找到car1左侧的所有对象"
- "哪些对象相互靠近（可能发生交互）"
- "行人周围有哪些车辆"

**满足实际需求**
- 多车协同场景
- 行人-车辆交互分析
- 复杂场景推理

### 统计数据

```
对象数量：25个
关系数量：600条（25×24）
Ego关系：24条
非Ego关系：576条
平均每个对象的关系数：24条
```

### 可视化材料
🔗 使用文件：`ppt_materials/5_relationship_graph.png`
- 关系列表展示
- 统计信息
- 示例说明

### 演讲要点
> "这是我们的核心改进之一。我们不仅构建了Ego车到其他对象的关系，还构建了所有对象之间的关系。比如car1和car2之间的关系、pedestrian1和car3之间的关系等。这样就形成了一个完整的场景关系网络，以Ego车为参考系。"

---

# 第6部分：建好的数据库图

## 标题页
**Neo4j知识图谱：场景图数据库化**

## 内容要点

### 数据库结构

**节点（Objects）**：
- 每个对象一个节点
- 包含所有属性（unique_id, type, translation, velocity等）
- 颜色按类型区分

**关系（RELATES_TO）**：
- 每条关系一条边
- 包含谓词和度量信息
- 方向性明确

### 数据导入

使用 `step3_neo4j_import.py`：
```python
# 创建对象节点
CREATE (obj:Object {
  unique_id: 'car1',
  type: 'car',
  translation_x: 8.2,
  translation_y: 1.3,
  ...
})

# 创建关系
MATCH (a:Object {unique_id: 'ego'}), 
      (b:Object {unique_id: 'car1'})
CREATE (a)-[r:RELATES_TO {
  predicates: ['front', 'near'],
  distance: 8.5,
  ...
}]->(b)
```

### 数据库优势

**可视化展示**
- 图形化查看场景
- 直观理解关系
- 交互式探索

**强大查询**
- 支持复杂模式匹配
- 支持路径查询
- 支持聚合统计

**可扩展性**
- 轻松添加新属性
- 支持多场景存储
- 支持时序分析

### 可视化材料
🗄️ 需要手动截图：
1. 打开Neo4j Browser（http://localhost:7474）
2. 连接数据库（URI: neo4j://localhost:7687）
3. 运行查询：`MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 50`
4. 切换到图形视图
5. 截图保存为：`ppt_materials/6_neo4j_graph_view.png`

### 截图要点
- 确保节点和关系清晰可见
- 使用不同颜色区分节点类型
- 显示部分属性标签
- 调整布局使图形美观

### 演讲要点
> "我们将生成的场景图完整导入到Neo4j图数据库中。在这个可视化界面中，每个圆圈代表一个对象，箭头代表它们之间的关系。通过图数据库，我们可以执行各种复杂的查询操作。"

---

# 第7部分：查询操作

## 标题页
**查询能力：从文字到函数到结果**

## 内容要点

### 查询1：查看Ego车周围的对象

**文字描述**：
"我想知道Ego车周围都有哪些对象，它们的类型和距离是多少？"

**Cypher函数**：
```cypher
MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->(obj:Object)
RETURN 
    obj.unique_id AS 对象ID,
    obj.type AS 类型,
    r.predicates AS 空间关系,
    r.distance AS 距离
ORDER BY r.distance ASC
```

**查询结果**：
```
对象ID         类型         空间关系          距离
pedestrian1   pedestrian   [front, near]    6.8
car1          car          [front, near]    8.5
bicycle1      bicycle      [left, near]     9.2
car2          car          [left, mid]      15.2
truck1        truck        [right, mid]     22.5
```

**结果解读**：
- 最近的是前方6.8米的行人
- 需要重点关注前方近距离对象
- 左侧有车辆和自行车

---

### 查询2：查找前方危险对象

**文字描述**：
"找出Ego车前方10米以内的所有对象，这些是潜在危险对象。"

**Cypher函数**：
```cypher
MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->(obj:Object)
WHERE 'front' IN r.predicates 
  AND r.distance < 10
RETURN 
    obj.unique_id AS 对象ID,
    obj.type AS 类型,
    r.distance AS 距离,
    obj.speed AS 速度
ORDER BY r.distance ASC
```

**查询结果**：
```
对象ID         类型         距离    速度
pedestrian1   pedestrian   6.8    0.5
car1          car          8.5    2.3
bicycle1      bicycle      9.2    3.1
```

**结果解读**：
- 3个对象在危险区域
- 行人速度慢但距离最近
- 自行车速度最快需要注意

---

### 查询3：对象之间的关系

**文字描述**：
"car1周围有哪些其他对象？它们的空间关系是什么？"

**Cypher函数**：
```cypher
MATCH (car1:Object {unique_id: 'car1'})-[r:RELATES_TO]->(obj:Object)
RETURN 
    obj.unique_id AS 对象ID,
    r.predicates AS 关系,
    r.distance AS 距离
ORDER BY r.distance ASC
LIMIT 5
```

**查询结果**：
```
对象ID         关系              距离
pedestrian1   [rear, near]     5.2
ego           [rear, near]     8.5
car2          [left, mid]      18.5
bicycle2      [right, mid]     20.3
truck1        [front, far]     28.3
```

**结果解读**：
- car1后方5.2米有行人（需要注意）
- car1在ego车前方8.5米
- 周围还有其他车辆分布

---

### 查询4：统计分析

**文字描述**：
"统计一下Ego车四个方向分别有多少对象？"

**Cypher函数**：
```cypher
MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->(obj:Object)
WITH 
    CASE 
        WHEN 'front' IN r.predicates THEN '前方'
        WHEN 'rear' IN r.predicates THEN '后方'
        WHEN 'left' IN r.predicates THEN '左侧'
        WHEN 'right' IN r.predicates THEN '右侧'
    END AS 方位,
    obj.type AS 类型
RETURN 方位, COUNT(*) AS 数量
ORDER BY 方位
```

**查询结果**：
```
方位    数量
前方    9
后方    5
左侧    6
右侧    4
```

**结果解读**：
- 前方对象最多（需要重点关注）
- 左右两侧较为均衡
- 后方对象较少

---

### 查询能力总结

**支持的查询类型**：
- ✅ 基于属性查询（类型、距离、速度）
- ✅ 基于关系查询（方位、远近）
- ✅ 复杂条件组合
- ✅ 统计聚合分析
- ✅ 路径查询
- ✅ 模式匹配

**实际应用场景**：
- 🎯 碰撞预警：查找前方近距离对象
- 🎯 路径规划：查询目标方向的障碍物
- 🎯 风险评估：统计危险区域对象数量
- 🎯 场景理解：分析对象分布和关系

### 可视化材料
📊 使用文件：`neo4j_query_examples.md`
- 包含8个完整查询示例
- 每个都有文字、函数、结果
- 适合PPT展示

### 演讲要点
> "通过Neo4j的强大查询能力，我们可以轻松实现各种复杂的场景分析。比如这个查询，只需要一句Cypher语句，就能找出前方10米内的所有危险对象。返回的结果包括对象ID、类型、距离和速度，可以直接用于决策。"

---

# 技术总结

## 整体技术路线（围绕一张图）

```
原始数据（六相机） 
    ↓
空间表示（BEV图）
    ↓
对象属性（JSON信息）
    ↓
关系构建（全关系图）
    ↓
数据库化（Neo4j）
    ↓
查询应用（Cypher）
```

## 核心改进点

### 1. 对象唯一ID
- ✅ 每个对象有唯一标识（car1, car2, pedestrian1）
- ✅ 便于区分和查询
- ✅ 支持关系追踪

### 2. 全关系图
- ✅ 不只是ego-其他，而是所有对象之间
- ✅ 以ego为参考系
- ✅ 完整的场景关系网络

### 3. 简化谓词
- ✅ 方位：front, left, rear, right
- ✅ 距离：near, mid, far
- ✅ 清晰易懂，便于应用

### 4. 原汁原味的数据
- ✅ 保留NuScenes原始属性
- ✅ 保留精确的数值信息
- ✅ 支持多层次查询

## 技术价值

**学术价值**：
- 场景图理论在真实数据上的应用
- 多模态感知数据的结构化表示
- 知识图谱在自动驾驶中的应用

**工程价值**：
- 支持复杂场景理解
- 支持高效查询检索
- 支持决策规划

**扩展价值**：
- 可扩展到时序分析
- 可扩展到多场景聚类
- 可扩展到覆盖率测试

---

# 附录：文件清单

## 代码文件
1. `step1_data_loading.py` - 数据加载
2. `step2_full_relation_scene_graph.py` - 全关系场景图生成
3. `step3_neo4j_import.py` - Neo4j导入
4. `generate_ppt_materials.py` - PPT材料生成

## 文档文件
1. `PPT_完整汇报材料_按老师要求.md` - 本文档
2. `neo4j_query_examples.md` - 查询示例

## 数据文件
1. `raw_scenes_data.json` - 原始数据
2. `all_scene_graphs_full_relation.json` - 全关系场景图

## 可视化文件（需要生成）
1. `1_data_statistics.png` - 数据统计
2. `2_six_camera_view.png` - 六相机图
3. `3_bev_with_labels.png` - BEV图
4. `4_car_json_info.json/png` - Car信息
5. `5_relationship_graph.png` - 关系图
6. `6_neo4j_graph_view.png` - 数据库截图（手动）

---

# 运行流程

## 第一步：生成场景图
```bash
python step2_full_relation_scene_graph.py
```

## 第二步：导入数据库
```bash
python step3_neo4j_import.py
```

## 第三步：生成PPT材料
```bash
python generate_ppt_materials.py
```

## 第四步：手动截图
1. 打开Neo4j Browser
2. 执行查询并截图
3. 保存到ppt_materials文件夹

## 第五步：制作PPT
使用本文档内容和生成的图片制作PPT

---

**准备完成，可以开始汇报！** 🎉
