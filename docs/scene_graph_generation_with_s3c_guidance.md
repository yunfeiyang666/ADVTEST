# NuScenes 场景图生成：融合 S3C 论文指导的完整讲解

## 目录
1. [S3C 核心思想概览](#1-s3c-核心思想概览)
2. [为什么需要场景图？S3C 的动机](#2-为什么需要场景图s3c-的动机)
3. [场景图的构成：从 S3C 视角解读](#3-场景图的构成从-s3c-视角解读)
4. [生成流程：S3C 原则的具体实现](#4-生成流程s3c-原则的具体实现)
5. [覆盖率驱动：S3C 的测试指导策略](#5-覆盖率驱动s3c-的测试指导策略)
6. [从场景图到测试：QA 生成](#6-从场景图到测试qa-生成)
7. [实战：一键生成与验证](#7-实战一键生成与验证)

---

## 1. S3C 核心思想概览

### 1.1 S3C 是什么？
**S3C (Spatial Semantic Scene Coverage)** 是一种**空间语义覆盖率**指标，用于量化自动驾驶测试在**场景空间**上的覆盖程度。

### 1.2 S3C 解决什么问题？
传统的 VLM 测试（如 QATest）存在两大局限：

1. **语义盲点（Semantic Blindness）**
   - QATest 只能对"种子集"中已有的问题进行同义变换
   - 如果种子集没有"锥桶"相关问题，QATest **永远无法**自动生成关于锥桶的测试
   - **结果**：测试覆盖受限于初始种子集的语义范围

2. **空间盲点（Spatial Blindness）**
   - 缺乏对"高风险空间区域"（如近距离、前方扇区、路口）的定向测试
   - 无法量化"我们是否充分测试了所有关键空间配置"
   - **结果**：Corner Case（边缘场景）漏测

### 1.3 S3C 的解决方案
**核心策略：将测试从"文本空间"拓展到"场景空间"**

```
旧方法（QATest）：     新方法（S3C）：
问题A → 变体A'          场景S → 提取事实F → 生成问题Q(F)
   ↓                      ↓
只测"语言鲁棒性"      测"语义覆盖率"
```

**S3C 的三个支柱：**
1. **场景图（Scene Graph）**：将驾驶场景结构化为"节点-边"图
2. **覆盖率指标（Coverage Metrics）**：量化"哪些空间配置"被测试了
3. **引导式生成（Guided Generation）**：优先为"低覆盖区域"生成新测试

---

## 2. 为什么需要场景图？S3C 的动机

### 2.1 场景图 = 自动驾驶的"标准答案"

在自动驾驶测试中，我们面临的核心挑战是：
> **如何判断 VLM 的回答是否正确？**

举例：
- **问题**："前方 10 米内有几辆车？"
- **VLM 回答**："2 辆"
- **如何验证？** → 需要"标准答案"（Ground Truth）

**场景图的价值**：
- 它从**原始标注数据**（nuScenes annotations）出发，通过**严格几何计算**得到每帧场景的"客观事实"
- 这些事实包括：每个对象的位置、速度、与自车的关系（距离、方位、车道关系等）
- 这些事实可以直接用于生成"带标准答案"的测试问题

### 2.2 S3C 视角：场景图是覆盖率的"度量空间"

S3C 论文强调：测试覆盖率不应该只看"问了多少不同句式"，而应该看**"测了多少不同场景配置"**。

**场景图的结构化表示使得以下覆盖率维度可量化：**

| 覆盖率维度 | 场景图字段 | S3C 指导意义 |
|-----------|-----------|-------------|
| **对象类别覆盖** | `category_name` | 是否测试了所有交通参与者（车、人、锥桶）？ |
| **空间扇区覆盖** | `bins.sector8` | 前/后/左/右8个方向是否均衡测试？ |
| **距离分档覆盖** | `bins.distance` | 近距离（0-2m）、中距离（10-30m）等是否都测试？ |
| **关系类型覆盖** | `relation_type` | 纵向跟驰、横向并行、路口交叉是否都测试？ |
| **地图拓扑覆盖** | `on_lane_id`, `in_intersection` | 直道、路口、车道变更场景是否都测试？ |

---

## 3. 场景图的构成：从 S3C 视角解读

### 3.1 场景图的数据结构

```json
{
  "sample_token": "ca9a282c9e77460f8360f564131a8af5",
  "timestamp": 1532402927647951,
  "prev_sample_token": "...",  // 时间链：支持多帧分析
  "next_sample_token": "...",
  "nodes": [
    {
      "id": "ego",
      "category_name": "ego_vehicle",
      "bins": {
        "sector8": "center",
        "distance": "very_close"
      },
      "map": {
        "on_layer": "lane",
        "on_lane_id": "lane_123",
        "in_intersection": false
      }
    },
    {
      "id": "ped_01",
      "category_name": "human.pedestrian.adult",
      "pose": { "ego": { "center": [10.5, -2.3, 0.0] } },
      "velocity": { "ego": [0.8, 0.0, 0.0] },
      "attributes": { "moving": true },
      "bins": {
        "sector8": "front",
        "distance": "close"
      }
    }
  ],
  "edges": [
    {
      "from": "ego",
      "to": "ped_01",
      "distance": 10.8,
      "bearing_ego": 0.12,
      "front_of": true,
      "left_of": false,
      "ttc": 3.5,
      "relation_type": "longitudinal",
      "same_lane": true
    }
  ]
}
```

### 3.2 S3C 的"三层覆盖"策略

根据 S3C 论文，测试覆盖应该在三个层次上进行：

#### **Level 1: 对象级覆盖（Node Coverage）**
- **定义**：场景中的"交通参与者"是否被全面测试？
- **场景图支持**：
  - `category_name`：车、人、自行车、卡车等
  - `attributes.moving/standing`：动态/静态对象
  - `bins.sector8`：空间分布（前方行人 vs 侧方行人）

**S3C 指导原则**：
> "高风险对象"（如行人、自行车）应该被**过采样**（Over-sampling），即生成更多针对这些对象的测试用例。

#### **Level 2: 关系级覆盖（Edge Coverage）**
- **定义**：对象之间的"空间关系"是否被全面测试？
- **场景图支持**：
  - `relation_type`：纵向（跟车）、横向（并行）、交叉（路口）
  - `same_lane`：同车道关系（车道保持测试）
  - `adjacent_lane`：邻接车道（变道测试）
  - `ttc`：碰撞风险（Time-to-Collision < 2秒 = 高危）

**S3C 指导原则**：
> "高风险关系"（如 TTC < 2秒、路口交叉）应该被**优先测试**（Priority Testing）。

#### Level 3: 场景级覆盖（Scene Configuration Coverage）**
- **定义**：不同的"地图拓扑 + 空间配置"组合是否被全面测试？
- **场景图支持**：
  - `map.on_lane_id`：当前车道
  - `map.in_intersection`：是否在路口
  - 组合查询：前方10米有2个行人 + 在路口 + 雨天（视觉变换）

**S3C 指导原则**：
> 测试应该覆盖"高风险场景配置矩阵"，例如：
> - [路口] × [行人] × [TTC<2秒]
> - [变道] × [侧方车辆] × [相对速度>5m/s]

---

## 4. 生成流程：S3C 原则的具体实现

### 4.1 坐标系选择：为什么以自车为中心？

**S3C 论文强调**：测试应该从"自车视角"（Ego-Centric）出发，因为：
1. **这是决策的参考系**：自动驾驶系统的所有决策都基于"相对于自车"的位置/速度
2. **空间语义可理解**："前方10米"比"全局坐标(x=1234.5, y=5678.9)"更有测试意义

**实现**：
- 自车坐标系：x=前方，y=左侧，z=上方
- 所有对象的 `pose.ego.center` 都是在自车系中的坐标
- 所有几何关系（距离、方位、扇区）都在自车系中计算

```python
# 全局坐标 → 自车坐标的变换
def world_to_ego(p_world, ego_pose):
    """
    p_world: [x, y, z] 全局坐标
    ego_pose: {'translation': [x,y,z], 'rotation': [w,x,y,z]}
    返回: p_ego [x, y, z] 自车系坐标
    """
    R_ge = Quaternion(ego_pose['rotation']).rotation_matrix
    t_ge = np.array(ego_pose['translation'])
    p_ego = R_ge.T @ (p_world - t_ge)
    return p_ego
```

### 4.2 节点生成：S3C 的"属性完备性"要求

**S3C 论文要求**：场景图的节点必须包含**所有可能影响测试设计的属性**。

#### 4.2.1 基础几何属性
```python
node = {
    "id": annotation_token,
    "category_name": ann['category_name'],
    "pose": {
        "ego": {
            "center": [x_ego, y_ego, z_ego],
            "yaw": yaw_ego  # 自车系下的朝向
        },
        "global": {
            "center": ann['translation']  # 保留全局坐标供调试
        }
    },
    "velocity": {
        "ego": [vx_ego, vy_ego, 0],  # 中心差分估计
        "global": [vx_w, vy_w, 0]
    },
    "size": {
        "wlh": ann['size']  # [width, length, height]
    },
    "corners_ego": corners_8x3  # 8个角点在自车系的坐标
}
```

#### 4.2.2 地图语义属性（S3C 的"上下文增强"）

**S3C 指导**：仅有几何信息不足以构建"语义丰富"的测试，必须融合地图信息。

```python
# 使用 NuScenesMap API 查询地图
from nuscenes.map_expansion.map_api import NuScenesMap

nusc_map = NuScenesMap(dataroot, map_name='singapore-onenorth')

# 查询对象所在的地图图层
layers_hit = nusc_map.layers_on_point(x_global, y_global)
if 'lane' in layers_hit:
    # 查询具体车道 ID
    lane_record = nusc_map.record_on_point(x_global, y_global, 'lane')
    node['map'] = {
        "on_layer": "lane",
        "on_lane_id": lane_record['token'],
        "in_intersection": False
    }
elif 'lane_connector' in layers_hit:
    # lane_connector = 路口连接段
    node['map'] = {
        "on_layer": "lane_connector",
        "on_lane_id": lane_record['token'],
        "in_intersection": True  # 标记为路口场景
    }
```

**测试应用**：
- 可以生成针对"路口场景"的专项测试
- 可以量化"路口覆盖率" vs "直道覆盖率"

#### 4.2.3 运动属性（S3C 的"动态风险评估"）

**S3C 指导**：静态对象和动态对象的风险等级不同，测试应该区分对待。

```python
# 解析 nuScenes 的属性标注
attributes = []
for attr_token in ann['attribute_tokens']:
    attr = nusc.get('attribute', attr_token)
    attr_name = attr['name']
    if 'moving' in attr_name:
        node['attributes']['moving'] = True
    elif 'standing' in attr_name or 'stopped' in attr_name:
        node['attributes']['standing'] = True
    elif 'with_rider' in attr_name:
        node['attributes']['with_rider'] = True
```

**测试应用**：
- "移动中的行人" 比 "静止的行人" 风险更高
- 可以生成："Is the pedestrian ahead moving?" (是非题)

#### 4.2.4 空间分档（S3C 的"分层覆盖"策略）

**S3C 论文核心创新**：将连续的空间离散化为"bins"（分档），便于统计覆盖率。

```python
def get_sector8(x, y):
    """8扇区划分"""
    angle = np.arctan2(y, x)  # [-pi, pi]
    if -np.pi/8 <= angle < np.pi/8:
        return "front"
    elif np.pi/8 <= angle < 3*np.pi/8:
        return "front_left"
    elif 3*np.pi/8 <= angle < 5*np.pi/8:
        return "left"
    # ... 其他扇区
    return sector

def get_distance_bin(dist):
    """距离分档"""
    if dist < 2:
        return "very_close"  # 高危区域
    elif dist < 10:
        return "close"
    elif dist < 30:
        return "medium"
    else:
        return "far"

node['bins'] = {
    "sector8": get_sector8(x_ego, y_ego),
    "distance": get_distance_bin(np.linalg.norm([x_ego, y_ego]))
}
```

**测试应用**：
```python
# 覆盖率统计示例
coverage_report = {
    "sector8_coverage": {
        "front": 450,      # 前方扇区有450个对象被测试
        "front_left": 320,
        "left": 180,
        "rear": 50         # ⚠️ 后方扇区测试不足！
    },
    "distance_coverage": {
        "very_close": 80,  # ⚠️ 近距离场景测试不足！
        "close": 600,
        "medium": 1200,
        "far": 800
    }
}
```

### 4.3 边生成：S3C 的"关系语义化"

**S3C 论文要求**：边不应该只是"两个节点之间的连线"，而应该是"具有语义的空间关系"。

#### 4.3.1 几何关系计算
```python
def compute_edge_geometry(node_i, node_j):
    """计算自车系下的几何关系"""
    pos_i = np.array(node_i['pose']['ego']['center'])
    pos_j = np.array(node_j['pose']['ego']['center'])
    
    delta = pos_j - pos_i
    distance = np.linalg.norm(delta)
    
    # 方位角（从 i 看 j）
    bearing = np.arctan2(delta[1], delta[0])
    
    # 前后/左右判定（相对于 i 的朝向）
    yaw_i = node_i['pose']['ego']['yaw']
    R_i = Rotation.from_euler('z', yaw_i).as_matrix()[:2, :2]
    delta_local = R_i.T @ delta[:2]  # 转到 i 的局部坐标系
    
    front_of = delta_local[0] > 0  # i 前方
    left_of = delta_local[1] > 0   # i 左侧
    
    return {
        "distance": distance,
        "bearing_ego": bearing,
        "front_of": front_of,
        "left_of": left_of
    }
```

#### 4.3.2 碰撞风险（TTC）

**S3C 指导**：TTC (Time-to-Collision) 是最重要的安全指标，必须计算。

```python
def compute_ttc(node_i, node_j):
    """
    沿两点连线方向的 TTC（简化版）
    如果两者正在靠近且速度>0.5m/s，返回 TTC；否则返回 None
    """
    pos_i = np.array(node_i['pose']['ego']['center'])
    pos_j = np.array(node_j['pose']['ego']['center'])
    vel_i = np.array(node_i['velocity']['ego'])
    vel_j = np.array(node_j['velocity']['ego'])
    
    delta_pos = pos_j - pos_i
    delta_vel = vel_j - vel_i
    
    distance = np.linalg.norm(delta_pos)
    direction = delta_pos / distance
    
    # 沿连线方向的相对速度（闭合速度）
    closing_speed = -np.dot(delta_vel, direction)
    
    if closing_speed > 0.5 and distance > 0.5:
        ttc = distance / closing_speed
        return ttc
    return None
```

**测试应用**：
```python
# 生成高危场景专项测试
high_risk_edges = [e for e in edges if e['ttc'] is not None and e['ttc'] < 2.0]
for edge in high_risk_edges:
    qa_questions.append({
        "type": "yesno_ttc",
        "question": f"Will {edge['from']} collide with {edge['to']} within 2 seconds?",
        "answer": "yes",
        "source_mr": "S3C.Safety.TTC",  # 可解释性标签
        "metadata": edge
    })
```

#### 4.3.3 关系类型语义化（S3C 的"场景分类"）

**S3C 论文强调**：不同类型的空间关系对应不同的测试场景。

```python
def classify_relation_type(node_i, node_j, edge):
    """
    根据运动方向和位置关系分类
    - longitudinal: 纵向（跟车、迎面）
    - lateral: 横向（并行）
    - intersecting: 交叉（路口）
    """
    # 如果任一方在 lane_connector（路口连接段），判定为交叉
    if node_i['map']['in_intersection'] or node_j['map']['in_intersection']:
        return "intersecting"
    
    # 否则根据相对位置与 x 轴夹角判断
    bearing = edge['bearing_ego']
    if abs(bearing) < np.pi/4 or abs(bearing) > 3*np.pi/4:
        return "longitudinal"
    else:
        return "lateral"

edge['relation_type'] = classify_relation_type(node_i, node_j, edge)
```

**测试应用**：
```python
# 按关系类型生成不同的测试模板
if edge['relation_type'] == 'longitudinal':
    # 跟车场景：距离、TTC、是否在同车道
    qa = generate_following_test(edge)
elif edge['relation_type'] == 'lateral':
    # 并行场景：左右位置、相对速度、是否在邻接车道
    qa = generate_lane_change_test(edge)
elif edge['relation_type'] == 'intersecting':
    # 路口场景：碰撞风险、优先权、红绿灯（如有）
    qa = generate_intersection_test(edge)
```

#### 4.3.4 车道关系（S3C 的"拓扑约束"）

**S3C 论文指出**：仅靠几何关系不足以刻画"车道级"的安全场景。

```python
def compute_lane_relations(node_i, node_j):
    """判断车道关系"""
    lane_i = node_i['map']['on_lane_id']
    lane_j = node_j['map']['on_lane_id']
    
    same_lane = (lane_i == lane_j) if lane_i and lane_j else False
    
    # 邻接车道近似判定（严格版本需要查询地图拓扑）
    pos_i = np.array(node_i['pose']['ego']['center'])
    pos_j = np.array(node_j['pose']['ego']['center'])
    dx = abs(pos_j[0] - pos_i[0])  # 纵向距离
    dy = abs(pos_j[1] - pos_i[1])  # 横向距离
    
    # 如果横向距离 < 5m 且纵向距离 < 20m，近似判定为邻接车道
    adjacent_lane = (dy < 5.0 and dx < 20.0 and not same_lane)
    
    return {
        "same_lane": same_lane,
        "adjacent_lane": adjacent_lane
    }
```

**测试应用**：
- 同车道：车道保持、跟车距离
- 邻接车道：变道安全、盲区检测

---

## 5. 覆盖率驱动：S3C 的测试指导策略

### 5.1 S3C 的"测试循环"

**S3C 论文提出的核心流程**：

```
1. 生成场景图（Scene Graph Generation）
   ↓
2. 计算覆盖率（Coverage Computation）
   ↓
3. 识别低覆盖区域（Gap Identification）
   ↓
4. 引导式测试生成（Guided Test Generation）
   ↓
5. 执行测试（Test Execution）
   ↓
6. 更新覆盖率 → 回到步骤2
```

### 5.2 覆盖率统计实现

```python
# scripts/coverage_from_sg.py 核心逻辑
def compute_coverage_stats(sg_jsonl_path):
    """
    统计场景图的覆盖率
    """
    stats = {
        "node_category": defaultdict(int),  # 对象类别分布
        "node_sector8": defaultdict(int),   # 空间扇区分布
        "node_distance": defaultdict(int),  # 距离分档分布
        "edge_relation_type": defaultdict(int),  # 关系类型分布
        "edge_ttc_bins": defaultdict(int),  # TTC 分布
        "scene_intersection": 0,  # 路口场景数
        "scene_straight": 0       # 直道场景数
    }
    
    for line in open(sg_jsonl_path):
        scene = json.loads(line)
        
        # 统计节点
        for node in scene['nodes']:
            if node['id'] == 'ego':
                continue
            stats['node_category'][node['category_name']] += 1
            stats['node_sector8'][node['bins']['sector8']] += 1
            stats['node_distance'][node['bins']['distance']] += 1
        
        # 统计边
        for edge in scene['edges']:
            stats['edge_relation_type'][edge['relation_type']] += 1
            if edge.get('ttc') is not None:
                if edge['ttc'] < 2:
                    stats['edge_ttc_bins']['high_risk'] += 1
                elif edge['ttc'] < 5:
                    stats['edge_ttc_bins']['medium_risk'] += 1
        
        # 统计场景类型
        if any(n['map'].get('in_intersection') for n in scene['nodes']):
            stats['scene_intersection'] += 1
        else:
            stats['scene_straight'] += 1
    
    return stats
```

### 5.3 S3C 的"优先级队列"策略

**S3C 论文建议**：测试生成应该优先为"低覆盖 + 高风险"区域生成新用例。

```python
def prioritize_test_generation(coverage_stats, risk_weights):
    """
    根据覆盖率和风险权重计算测试优先级
    """
    priority_scores = {}
    
    # 计算每个类别的"欠采样分数"（低覆盖 = 高优先级）
    total_nodes = sum(coverage_stats['node_category'].values())
    for category, count in coverage_stats['node_category'].items():
        coverage_ratio = count / total_nodes
        risk_weight = risk_weights.get(category, 1.0)
        
        # 优先级 = 风险权重 / 覆盖率
        priority_scores[category] = risk_weight / (coverage_ratio + 0.01)
    
    # 排序：优先级高的类别应该生成更多测试
    sorted_priorities = sorted(priority_scores.items(), 
                               key=lambda x: x[1], 
                               reverse=True)
    
    return sorted_priorities

# 示例：定义风险权重
risk_weights = {
    "human.pedestrian.adult": 10.0,  # 行人高风险
    "vehicle.bicycle": 8.0,           # 自行车高风险
    "vehicle.car": 1.0,               # 车辆中等风险
    "movable_object.trafficcone": 5.0  # 锥桶（施工区）高风险
}

priorities = prioritize_test_generation(coverage_stats, risk_weights)
# 输出：[('human.pedestrian.adult', 50.3), ('movable_object.trafficcone', 38.7), ...]
```

### 5.4 自适应采样策略

**S3C 论文的"自适应生成"算法**：

```python
def adaptive_qa_generation(sg_jsonl_path, target_qa_count=1000):
    """
    根据覆盖率动态调整 QA 生成的采样策略
    """
    # 步骤1：统计当前覆盖率
    coverage_stats = compute_coverage_stats(sg_jsonl_path)
    
    # 步骤2：计算优先级
    priorities = prioritize_test_generation(coverage_stats, risk_weights)
    
    # 步骤3：动态分配 QA 数量
    qa_budget = {}
    total_priority = sum(p[1] for p in priorities)
    for category, priority in priorities:
        qa_budget[category] = int(target_qa_count * (priority / total_priority))
    
    # 步骤4：按预算生成 QA
    generated_qas = []
    for line in open(sg_jsonl_path):
        scene = json.loads(line)
        for node in scene['nodes']:
            category = node['category_name']
            if qa_budget.get(category, 0) > 0:
                qa = generate_qa_for_node(scene, node)
                generated_qas.append(qa)
                qa_budget[category] -= 1
    
    return generated_qas
```

---

## 6. 从场景图到测试：QA 生成

### 6.1 S3C 的"模板驱动生成"原则

**S3C 论文指出**：测试问题的生成应该：
1. **基于事实（Fact-Grounded）**：每个问题都对应场景图中的一个"事实"
2. **多样性（Diverse）**：同一事实应该用多种题型测试
3. **可溯源（Traceable）**：每个问题应该标记其"来源"（source_mr），便于可解释性分析

### 6.2 题型设计：S3C 的"多维度测试"

```python
# scripts/gen_qa_from_sg.py 核心逻辑

def generate_qa_for_scene(scene, ttc_threshold=2.0):
    """
    为一帧场景生成多种类型的 QA
    """
    qas = []
    
    # 题型1：距离分档选择题（测试空间定位能力）
    for node in scene['nodes']:
        if node['id'] == 'ego':
            continue
        qa = {
            "sample_token": scene['sample_token'],
            "type": "distance_bin_mc",
            "question": f"How far is the {node['category_name']} from the ego vehicle?",
            "options": ["very close (0-2m)", "close (2-10m)", "medium (10-30m)", "far (30m+)"],
            "answer": node['bins']['distance'],
            "source_mr": "S3C.Spatial.Distance",
            "metadata": {"node_id": node['id'], "category": node['category_name']}
        }
        qas.append(qa)
    
    # 题型2：扇区位置选择题（测试方位感知能力）
    for node in scene['nodes']:
        if node['id'] == 'ego':
            continue
        qa = {
            "type": "sector_mc",
            "question": f"In which direction is the {node['category_name']} relative to ego?",
            "options": ["front", "front_left", "left", "rear_left", "rear", "rear_right", "right", "front_right"],
            "answer": node['bins']['sector8'],
            "source_mr": "S3C.Spatial.Sector"
        }
        qas.append(qa)
    
    # 题型3：运动属性判断（测试动态理解能力）
    for node in scene['nodes']:
        if node['id'] == 'ego':
            continue
        is_moving = node['attributes'].get('moving', False)
        qa = {
            "type": "yesno_attr",
            "question": f"Is the {node['category_name']} moving?",
            "answer": "yes" if is_moving else "no",
            "source_mr": "S3C.Dynamic.Movement"
        }
        qas.append(qa)
    
    # 题型4：碰撞风险判断（测试安全评估能力）
    for edge in scene['edges']:
        if edge.get('ttc') is not None and edge['ttc'] < ttc_threshold:
            from_node = next(n for n in scene['nodes'] if n['id'] == edge['from'])
            to_node = next(n for n in scene['nodes'] if n['id'] == edge['to'])
            qa = {
                "type": "yesno_ttc",
                "question": f"Will {from_node['category_name']} collide with {to_node['category_name']} within {ttc_threshold} seconds?",
                "answer": "yes",
                "source_mr": "S3C.Safety.TTC",
                "metadata": {"ttc": edge['ttc'], "relation": edge['relation_type']}
            }
            qas.append(qa)
    
    # 题型5：前方对象计数（测试多对象理解能力）
    front_objects = [n for n in scene['nodes'] 
                     if n['id'] != 'ego' and n['bins']['sector8'] == 'front']
    if front_objects:
        qa = {
            "type": "count_mc",
            "question": "How many objects are in front of the ego vehicle?",
            "options": ["0", "1", "2", "3", "4+"],
            "answer": str(min(len(front_objects), 4)),
            "source_mr": "S3C.Counting.Front"
        }
        qas.append(qa)
    
    return qas
```

### 6.3 S3C 的"标签化"设计

**关键创新**：每个生成的 QA 都带有元数据标签，便于后续分析。

```json
{
  "sample_token": "ca9a282c9e77460f8360f564131a8af5",
  "type": "yesno_ttc",
  "question": "Will the ego vehicle collide with the pedestrian ahead within 2 seconds?",
  "answer": "yes",
  "source_mr": "S3C.Safety.TTC",  // ← 可解释性标签
  "metadata": {
    "ttc": 1.8,
    "relation_type": "longitudinal",
    "pedestrian_category": "human.pedestrian.adult",
    "distance": 5.2,
    "sector": "front"
  }
}
```

**测试报告示例**：
```python
# 当测试完成后，按 source_mr 分组统计
test_results = load_test_results()
failure_report = defaultdict(list)

for result in test_results:
    if result['is_correct'] == False:
        failure_report[result['source_mr']].append(result)

# 输出可解释的失败报告
print("=== Test Failure Analysis ===")
for source_mr, failures in sorted(failure_report.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"\n{source_mr}: {len(failures)} failures")
    print(f"  - Most common error pattern: ...")
    print(f"  - Affected scenarios: {set(f['metadata']['relation_type'] for f in failures)}")
```

输出示例：
```
=== Test Failure Analysis ===

S3C.Safety.TTC: 85 failures
  - Most common error pattern: Model underestimates collision risk in high-speed scenarios
  - Affected scenarios: {'longitudinal', 'intersecting'}

S3C.Spatial.Distance: 42 failures
  - Most common error pattern: Confuses "close" and "medium" distance bins
  - Affected scenarios: {'lateral'}

S3C.Counting.Front: 18 failures
  - Most common error pattern: Misses small objects (traffic cones) in crowded scenes
  - Affected scenarios: {'front'}
```

---

## 7. 实战：一键生成与验证

### 7.1 完整流程命令

在项目根目录 `e:\Project\ADVTEST`：

```powershell
# 步骤1：生成场景图 v2（mini数据集）
python .\scripts\build_nuscenes_scene_graph.py `
  --dataroot .\data\nuscenes `
  --version v1.0-mini `
  --out_path .\data\sg_mini_v2.jsonl

# 步骤2：计算覆盖率统计
python .\scripts\coverage_from_sg.py `
  --jsonl .\data\sg_mini_v2.jsonl `
  --out_dir .\data\coverage_mini_v2

# 步骤3：根据覆盖率生成 QA（自适应采样）
python .\scripts\gen_qa_from_sg.py `
  --jsonl .\data\sg_mini_v2.jsonl `
  --out_path .\data\qa_mini_v2.jsonl `
  --max_frames 404

# 步骤4：添加相机可见性（可选，用于多模态测试）
python .\scripts\add_visibility_to_sg.py `
  --dataroot .\data\nuscenes `
  --version v1.0-mini `
  --jsonl_in .\data\sg_mini_v2.jsonl `
  --jsonl_out .\data\sg_mini_v2_vis.jsonl

# 步骤5：可视化验证（BEV 俯视图）
python .\scripts\vis_bev_scene_graph.py `
  --jsonl .\data\sg_mini_v2.jsonl `
  --out_dir .\data\bev_vis `
  --max_frames 24 `
  --only_ego_edges `
  --draw_vel

# 步骤6：可视化验证（六相机马赛克）
python .\scripts\render_mosaic_from_sg.py `
  --dataroot .\data\nuscenes `
  --version v1.0-mini `
  --jsonl .\data\sg_mini_v2_vis.jsonl `
  --out_dir .\data\mosaic_vis `
  --max_frames 24
```

### 7.2 结果验证：S3C 覆盖率报告

查看生成的覆盖率报告：

```powershell
# 查看总览
cat .\data\coverage_mini_v2\overview.json

# 查看类别分布
cat .\data\coverage_mini_v2\node_category_dist.csv

# 查看扇区分布
cat .\data\coverage_mini_v2\node_sector8_dist.csv

# 查看关系类型分布
cat .\data\coverage_mini_v2\edge_relation_type_dist.csv
```

示例输出（`overview.json`）：
```json
{
  "total_scenes": 404,
  "total_nodes": 15234,
  "total_edges": 8765,
  "node_coverage": {
    "vehicle.car": 8923,
    "human.pedestrian.adult": 2341,
    "vehicle.bicycle": 876,
    "movable_object.trafficcone": 543
  },
  "sector8_coverage": {
    "front": 3421,
    "front_left": 2987,
    "left": 1876,
    "rear_left": 1234,
    "rear": 987,
    "rear_right": 1098,
    "right": 1765,
    "front_right": 1866
  },
  "distance_coverage": {
    "very_close": 234,  // ⚠️ 近距离场景不足
    "close": 1987,
    "medium": 8765,
    "far": 4248
  },
  "relation_type_coverage": {
    "longitudinal": 5432,
    "lateral": 2876,
    "intersecting": 457  // ⚠️ 路口场景不足
  }
}
```

**S3C 分析结论**：
1. **近距离场景（0-2m）测试不足**：只有 234 个节点，建议增加"近距离行人/车辆"的专项测试
2. **路口场景测试不足**：只有 457 条交叉关系，建议过采样路口帧
3. **后方扇区测试偏少**：rear 只有 987 个对象，建议增加"后视镜/盲区"测试

### 7.3 迭代优化：S3C 的闭环测试

根据覆盖率报告，执行第二轮"定向生成"：

```python
# 定向生成脚本示例
def targeted_generation(sg_jsonl, coverage_report):
    """
    根据覆盖率报告定向生成测试
    """
    # 识别低覆盖区域
    low_coverage_sectors = [s for s, count in coverage_report['sector8_coverage'].items() 
                            if count < 1000]  # 后方、侧方
    
    low_coverage_distances = [d for d, count in coverage_report['distance_coverage'].items() 
                              if count < 500]  # 近距离
    
    # 过滤符合条件的场景
    target_scenes = []
    for line in open(sg_jsonl):
        scene = json.loads(line)
        # 选择包含"近距离后方对象"的场景
        has_target = any(
            n['bins']['sector8'] in low_coverage_sectors and 
            n['bins']['distance'] in low_coverage_distances
            for n in scene['nodes'] if n['id'] != 'ego'
        )
        if has_target:
            target_scenes.append(scene)
    
    # 为这些场景生成更多 QA（过采样）
    targeted_qas = []
    for scene in target_scenes:
        qas = generate_qa_for_scene(scene)
        # 每个场景生成 3 倍数量的 QA
        targeted_qas.extend(qas * 3)
    
    return targeted_qas
```

---

## 总结：S3C 的核心价值

### 1. 从"盲测"到"精准打击"
- **旧方法（QATest）**：随机变换种子集，希望"碰到" Corner Case
- **新方法（S3C）**：量化覆盖率，主动识别"高风险低覆盖"区域，定向测试

### 2. 从"黑盒评分"到"白盒诊断"
- **旧方法**：只知道"模型得了20分"
- **新方法**：知道"模型在路口场景失败了85次，在行人检测上失败了42次"

### 3. 从"语言鲁棒性"到"安全可靠性"
- **旧方法**：测试"模型是否认识 what's"
- **新方法**：测试"模型在 TTC < 2秒时是否能正确预警"

### 4. S3C 的局限与未来方向
- **当前局限**：
  - 车道邻接关系为几何近似，严格版本需查询地图拓扑
  - TTC 为 LOS（Line-of-Sight）简化，未考虑转向/制动
  - 缺少视觉遮挡模拟（Z-buffer）
  
- **改进方向**：
  - 融合视觉变换（晴天→雨天）进行跨模态测试
  - 引入多帧序列分析（轨迹预测）
  - 集成红绿灯状态、道路标识等高级语义

---

**参考文献**：
- S3C (Spatial Semantic Scene Coverage): 论文核心思想来自用户提供的课题框架文档
- QATest: Metamorphic Testing for Question Answering Systems
- NuScenes Dataset: A. Caesar et al., 2020
- Traffic Scene Graphs: Ridel et al., 2022

**项目位置**：`e:\Project\ADVTEST`

**核心脚本**：
- `scripts/build_nuscenes_scene_graph.py`（S3C 场景图生成）
- `scripts/coverage_from_sg.py`（S3C 覆盖率统计）
- `scripts/gen_qa_from_sg.py`（S3C 引导式测试生成）
