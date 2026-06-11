# QA 生成系统 — 关键工作总结（PPT 用）

> 本文档汇总了覆盖率驱动问答生成系统的核心设计，供 PPT 汇报使用。

---

## 一、四级模板架构

### 1.1 NuScenesQA 数值问题处理方式

NuScenesQA 官方题集（83,337题）的核心设计原则：**完全避免精确数值，一切离散化**。

| 属性维度 | NuScenesQA 做法 | 我们的对齐策略 |
|---------|---------------|-------------|
| **速度** | 不问具体速度，用离散状态替代：`moving / stopped / parked` | 已删除 speed_of_obj / fastest_type 等6个精确速度模板 |
| **距离** | 不问"多少米"，用相对关系替代：`nearest / farthest / to the {DIR}` | 已删除 distance_to_type / distance_to_obj 等6个精确距离模板；保留离散化距离桶（within X meters） |
| **尺寸** | 完全不涉及3D尺寸 | 已删除 largest / smallest / compare_size 等9个尺寸模板 |
| **方向** | 离散化为4/8方位：`front / back / left / right / front-left...` | 全量沿用 |
| **状态** | 离散分类：`moving / stopped / parked / with rider...` | 全量沿用 |

**核心原则**：所有问题必须能被CV模型看着6相机标注视图作答，不依赖精确数值查表。

### 1.2 四级结构总览

```
总计 185 模板（全部 CV 可答）
```

#### 第一级：覆盖层级 (Coverage Level)

| 层级 | 含义 | 模板数 | 占比 |
|------|------|--------|------|
| **L0** | 单节点查询（0-hop） | 54 | 29.2% |
| **L1** | 单边/方向查询（1-hop） | 82 | 44.3% |
| **L2** | 双跳/跨属性组合（2-hop） | 49 | 26.5% |

#### 第二级：问题类型 (Question Type)

| 类型 | 说明 | 示例 |
|------|------|------|
| **exist** | 是否存在 | "Are there any moving cars?" |
| **count** | 数量统计 | "How many pedestrians are to the front?" |
| **status** | 状态查询 | "What is the status of car_1?" |
| **object** | 对象识别 | "What is the moving thing to the left?" |
| **comparison** | 属性比较 | "Do car_1 and car_2 have the same status?" |

#### 第三级：提问方向 (Major Pattern) — 共 37 种

| 层级 | 提问方向数 | 其中独有方向 |
|------|----------|------------|
| **L0** | 13 | 0（与官方一致） |
| **L1** | 26 | 6（is_approaching, nearest_type, nearest_in_direction, farthest_type, distance_bin_exist, distance_bin_direction_exist） |
| **L2** | 20 | 9（exist_approaching_direction, object_between, count_approaching, count_status_in_distance, nearest_direction_status, nearest_status, compare_distance, compare_nearest_farthest, count_in_distance_direction） |

#### 第四级：语义变体 (Variants)

每个提问方向下有 2-5 个同义改写变体，保证问题表达多样性。

示例（direct_status 方向，5个变体）：
1. `"What is the status of the {obj_type}?"`
2. `"What status is the {obj_type}?"`
3. `"The {obj_type} is in what status?"`
4. `"There is a {obj_type}; what status is it?"`
5. `"What is the status of {obj_id}?"`

### 1.3 与 NuScenesQA 官方对比

| 维度 | NuScenesQA 官方 | 我们的模板库 |
|------|----------------|------------|
| 总模板模式 | ~23种提问方向 | **37种**提问方向（+14独有） |
| 覆盖层级 | L0 + L1 | **L0 + L1 + L2** |
| 语义变体 | ~4变体/方向 | 2-5变体/方向 |
| 数值处理 | 全离散 | 全离散（已清理数值模板） |
| 独有扩展 | — | 距离桶、接近判断、最近/最远对象、跨属性组合、对象间关系 |
| 歧义保护 | 无 | 多同类型时自动跳过type-only模板 |

### 1.4 数值离散化对照表

| 原始数值 | 离散化方式 | 对应模板方向 |
|---------|-----------|------------|
| 速度 (m/s) | → `moving / stopped / parked` | direct_status, id_status |
| 距离 (m) | → `nearest / farthest / within X meters` | nearest_type, farthest_type, distance_bin_exist |
| 方位角 (°) | → `front / back / left / right / front-left...` | 所有 direction 类模板 |
| 接近趋势 | → `approaching / moving away` (bool) | is_approaching |
| 距离比较 | → `closer / farther` (相对比较) | compare_distance |

---

## 二、覆盖率数据：结构构建与全流程贯穿

### 2.1 核心数据结构：三组 KV Map

```
┌──────────────────────────────────────────────────────────┐
│  CoverageTracker  —  统一覆盖率追踪器                      │
│                                                          │
│  _l0: Dict[node_id → CoverageRecord]      # 节点覆盖     │
│  _l1: Dict["src|dir|tgt" → CoverageRecord] # 边覆盖      │
│  _l2: Dict["n1|n2|n3" → CoverageRecord]    # 两跳覆盖    │
│                                                          │
│  CoverageRecord:                                         │
│    hit_count: int          # 被覆盖次数 (0=未覆盖)         │
│    template_ids: List[str] # 使用的模板ID列表              │
│    question_ids: List[str] # 对应的题目ID列表              │
└──────────────────────────────────────────────────────────┘
```

| 层级 | Key 构成 | 示例 Key | 含义 |
|------|---------|---------|------|
| **L0** | `node_id` | `"car_1"` | 该对象是否被任何问题涉及 |
| **L1** | `"source\|direction\|target"` | `"ego\|front\|car_1"` | 该空间关系是否被问过 |
| **L2** | `"n1\|n2\|n3"` | `"ego\|car_1\|ped_2"` | 该两跳路径是否被覆盖 |

### 2.2 构建流程（6步）

```
1. 建场景图，导入数据库
2. 构建三组KV Map，key为L中的某个对象，value为0/1表示是否已覆盖
3. 对初始L0、L1、L2进行计算
4. 三组KV Map存为JSON文件，后面抽取覆盖率信息可以直接读
5. 后续有新涉及到的对象，根据key找过去value更新为1
6. 算覆盖率：统计value为1的个数 / map.value的长度
```

代码实现：

```python
# 初始化（Step 1-3）
tracker = CoverageTracker.from_scene_graph(scene_data)
# → 遍历 nodes → 注册 _l0 (全部 value=0)
# → 遍历 edges → 提取 direction_8 → 注册 _l1 (全部 value=0)
# → 双重遍历 edges → 枚举两跳路径 → 注册 _l2 (全部 value=0)

# 持久化（Step 4）
tracker.save("coverage.json")

# 更新覆盖（Step 5）
tracker.record_from_qa(qa_dict)  # 自动将涉及的 key 的 value 从 0 → 1

# 计算覆盖率（Step 6）
rates = tracker.coverage_rates()
# → l0_rate = count(hit_count > 0) / len(_l0)
```

### 2.3 Hash 加速查询

```python
# 每条 key 注册时同步建立 hash 反查索引
def _register_l1(self, source, direction, target):
    key = f"{source}|{direction}|{target}"        # 原始 key
    self._l1[key] = CoverageRecord()              # KV map
    h = sha256(key)[:16]                          # 16字符 hash
    self._l1_hash[h] = key                        # hash → 原始key

# 查询时 O(1):
record = tracker.get_l1_by_hash(h)
```

| 操作 | 无 Hash | 有 Hash |
|------|---------|---------|
| 查询单条覆盖 | O(n) 遍历 | **O(1)** 直接定位 |
| L2 十万级 map | 全量扫描慢 | hash 字典秒查 |
| 新 key 插入 | — | 先查 hash 是否已存在，避免重复 |

### 2.4 全流程闭环

```
┌─────────────────────────────────────────────────────────────────┐
│                    覆盖率驱动闭环控制器                           │
│               (CoverageLoopController.run)                      │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │ ① 建场景图 │→ │ ② 初始化   │→ │ ③ 缺口分析 │→ │ ④ 生成问题 │   │
│  │ 导入数据库 │   │ 三组KV Map │   │ GapAnalyzer│   │ TemplateFill│  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
│        ↑                                              │         │
│        │         ┌──────────┐   ┌──────────┐          ↓         │
│        └─────────│ ⑥ 判断终止 │←─│ ⑤ 更新Map  │←── record_from_qa│
│                  │ 覆盖率达标?│   │ value 0→1 │                  │
│                  └──────────┘   └──────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

| 步骤 | 做什么 | 关键代码 | 数据流 |
|------|--------|---------|--------|
| **① 建图导入** | 加载场景图 JSON | `loop_controller._load_scene_graph()` | JSON → scene_data Dict |
| **② 初始化 Map** | 从场景图注册全量 L0/L1/L2 | `CoverageTracker.from_scene_graph()` | scene_data → 三组 KV Map (全0) |
| **③ 缺口分析** | 找出 value=0 的 key，按优先级排序 | `GapAnalyzer.decide_next_generation()` | KV Map → gaps List + strategy |
| **④ 生成问题** | 预算分配→候选集打乱→模板填充→选最优 | `CoverageDrivenTemplateGenerator.generate()` | gaps + templates → QA pairs |
| **⑤ 更新 Map** | 每生成一题，将涉及的 key 的 value 更新为已覆盖 | `tracker.record_from_qa(qa)` | QA → hit_count += 1 |
| **⑥ 判断终止** | 统计 value=1 的个数 / map 总长度 | `tracker.coverage_rates()` | KV Map → L0/L1/L2 覆盖率 |

### 2.5 JSON 持久化结构

```json
{
  "meta": {
    "scene_name": "scene-0103",
    "frame_idx": 25,
    "total_nodes": 48,
    "total_edges": 1122,
    "total_2hop": 5000
  },
  "l0": {
    "car_1": {"hit_count": 3, "template_ids": ["L0_exist_A1", "L0_status_A1"], "question_ids": ["q001", "q002"]},
    "ped_1": {"hit_count": 0, "template_ids": [], "question_ids": []}
  },
  "l1": {
    "ego|front|car_1": {"hit_count": 2, "template_ids": ["L1_exist_A1"], "question_ids": ["q003"]},
    "ego|left|ped_1":  {"hit_count": 0, "template_ids": [], "question_ids": []}
  },
  "l2": {
    "ego|car_1|ped_2": {"hit_count": 0, "template_ids": [], "question_ids": []}
  }
}
```

### 2.6 两层实现的适配关系

系统中存在两个覆盖率实现，通过桥接方法双向转换：

```
UnifiedCoverageStats (coverage_loop/)        CoverageTracker (qa_generator_v2/)
┌──────────────────────────┐                ┌──────────────────────────┐
│ Set-based 覆盖              │   from_unified  │ KV-Map + Hash 索引        │
│ covered_nodes: Set          │ ←──────────→  │ _l0: Dict[str, Record]    │
│ covered_edges: Set          │   to_unified    │ _l1: Dict[str, Record]    │
│ node_coverage_count: Dict   │                │ _l2: Dict[str, Record]    │
│                              │                │ _l0_hash / _l1_hash / ... │
│ 用途: LoopController 闭环   │                │ 用途: 模板生成器 精确追踪   │
└──────────────────────────┘                └──────────────────────────┘
```

### 2.7 动态增长处理

```python
# 新对象出现时的处理策略:
def record_l0(self, node_id, template_id="", question_id=""):
    if node_id not in self._l0:           # 新 key，不在原始 map 中
        self._register_l0(node_id)        # 自动注册（动态增长）
    self._l0[node_id].record(...)         # 更新 value
```

- **L0/L1**：key 空间固定（来自场景图），运行时不会新增
- **L2**：key 空间可能很大（十万级），采用惰性注册 + hash 索引
  - 初始化时：枚举所有两跳路径，预注册
  - 运行时：若遇到新路径，`record_l2` 自动注册并建 hash
  - 查询时：`get_l2_by_hash(h)` → O(1) 命中

### 2.8 一张图总结全流程

```
  NuScenes 数据集
       │
       ▼
  ┌──────────┐     ┌─────────────────┐        ┌───────────────────┐
  │ 场景图 JSON │────→│ 三组 KV Map 初始化 │────→│ JSON 持久化     │
  │ nodes/edges│     │ L0: 48 keys      │     │ coverage.json  │
  └──────────┘     │ L1: 1122 keys    │       └──────┬───────┘
                    │ L2: ~5000 keys   │           │
                    └────────┬────────┘            │ 后续直接读
                             │                     │
                    ┌────────▼────────┐     ┌──────▼───────┐
                    │  GapAnalyzer     │     │ 加载已有覆盖率 │
                    │  找 value=0 的缺口│←────│ (NuScenesQA  │
                    └────────┬────────┘     │  已覆盖部分)  │
                             │               └──────────────┘
                    ┌────────▼────────┐
                    │ 模板生成器          │
                    │ 预算→打乱→选模板    │
                    │ →填充→生成QA       │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ record_from_qa  │
                    │ 更新 value: 0→1  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ coverage_rates  │     覆盖率 = count(v=1) / len(map)
                    │ L0: 85%         │
                    │ L1: 52%         │──→ 达标? → 停止
                    │ L2: 12%         │──→ 未达标? → 回到 GapAnalyzer
                    └─────────────────┘
```

---

## 三、Phase 0 预处理：过滤与清洗

> 核心代码：`scene_filter.py` → `SceneGraphFilter` + `QAFilter`

在进入覆盖率驱动生成之前，需要对数据进行两层过滤预处理：

### 3.1 物体过滤（SceneGraphFilter）

筛掉不符合官方标准的对象，确保场景图中的对象在图像上确实可见、可辨识。

| 筛选项 | 阈值 | 来源 |
|--------|------|------|
| **3D 距离** | barrier/cone: 30m, bicycle/motorcycle/ped: 40m, 车辆类: 50m | nuScenes 官方 |
| **投影像素高度** | ≥10 px (宽松) 或 ≥15 px (严格) | nuImages 标准 |
| **可见度** | ≥40% | nuScenes visibility 分级 |

```
原始 NuScenes 3D 标注
  ↓
1. 按类型检查 3D 距离 (30/40/50m)
  ↓
2. 投影 3D 框到图像平面，估算 2D 高度
   approx_height_px = (height_3d × focal_length) / distance
   焦距 fy ≈ 1266 px (CAM_FRONT)
  ↓
3. 检查可见度 (visibility ≥ 40%)
  ↓
过滤后场景图 (仅保留可见、可辨识对象)
```

### 3.2 错题过滤（QAFilter）

原始 NuScenesQA 中存在答案有误或题目歧义的题目，通过 5 层 retry 机制预先发现并记录到黑名单。

**5 层 retry 策略**（`pipeline.py → process_question_with_retry`）：

| 层级 | 策略 | 方向匹配方式 |
|------|------|-------------|
| 1 | Ego Frame 宽松 | `'DIR' IN r.angle_matches_ego` |
| 2 | 语法错误修正 | 修正上一层 Cypher 语法 |
| 3 | Source Frame 宽松 | `'DIR' IN r.angle_matches_source` |
| 4 | Ego Frame 精确 | `r.direction_8_ego = 'DIR'` |
| 5 | Source Frame 精确 | `r.direction_8_source = 'DIR'` |

**5 层全失败 → 标记为错题**，录入 `skip_questions.json` 黑名单。

```python
qa_filter = QAFilter()  # 加载 skip_questions.json
clean_qa = qa_filter.filter_qa_list(original_qa, scene_name, frame_idx)
# 自动跳过已知错题
```

### 3.3 Phase 0 在整体流程中的位置

```
NuScenes 3D 标注
  ↓
Phase 0a: SceneGraphFilter → 过滤后场景图
Phase 0b: QAFilter → 过滤后原始 QA (可选，用于审计)
  ↓
Phase 1: CoverageTracker Init (基于过滤后场景图)
  ↓
Phase 2: 覆盖率驱动生成循环
  ↓
Phase 3: VLM 评估
```

---

## 四、目标为导向生成（单层级聚焦，5步流程）

> 核心入口：`CoverageDrivenTemplateGenerator.generate_with_tracker()`

### 4.0 设计理念：单层级聚焦

每轮只聚焦一个覆盖层级，预算全部分配给该层级。**不做三级预算分配**。

**原因**：高层级问题会自然附带提升低层级覆盖率（跨级免费覆盖）：

| 聚焦层级 | L0 附带提升 | L1 附带提升 | L2 附带提升 |
|---------|-----------|-----------|-----------|
| **聚焦 L0** | ✅ 直接 | ❌ 无 | ❌ 无 |
| **聚焦 L1** | ✅ 附带 | ✅ 直接 | ❌ 无 |
| **聚焦 L2** | ✅ 附带 | ✅ 附带 | ✅ 直接 |

**建议顺序**：先 L2 → 再 L1 → 最后补 L0（自上而下，效率最高）

```
第1轮: focus="L2", budget=100  →  L2缺口中选100个生成
第2轮: focus="L1", budget=80   →  看L1还剩多少缺口（L2已附带覆盖一部分）
第3轮: focus="L0", budget=50   →  补齐剩余L0缺口
```

### 4.1 流程总览

```
  CoverageTracker (三组KV Map)
       │
       ▼
  ┌──────────────────┐
  │ Step 1: 明确聚焦  │  本轮只做一个层级
  │ focus_level="L2" │  → 目标: 覆盖率达到 50%
  └───────┬──────────┘
          ▼
  ┌──────────────────┐
  │ Step 2: 候选集    │  只从该层级的 KV Map 提取 hit_count=0 的缺口
  │ focus_gaps       │  → [{"level":"L2", "node1":"ego", ...}, ...]
  └───────┬──────────┘
          ▼
  ┌──────────────────┐
  │ Step 3: 定预算    │  min(max_questions, 缺口数)
  │ budget = 100     │  → 全部给聚焦层级，不做三级分配
  └───────┬──────────┘
          ▼
  ┌──────────────────┐
  │ Step 4: 打乱      │  shuffle 后取前 n 个
  │ shuffle + slice  │  → 避免总是从同一方向/对象开始
  └───────┬──────────┘
          ▼
  ┌──────────────────┐
  │ Step 5: 生成问题  │  每个缺口生成一个 QA
  │ one_qa_per_gap   │  → 随机选问题类型 + 优先少用模板
  └───────┬──────────┘
          ▼
     record_from_qa → 同时更新 L0/L1/L2 三组 KV Map (跨级附带覆盖)
```

### 4.2 各步骤详解

#### Step 1: 明确聚焦层级

```python
@dataclass
class CoverageGoal:
    """单层级聚焦模式"""
    focus_level: str = "L0"     # 本轮聚焦: "L0" / "L1" / "L2"
    target: float = 1.0         # 该层级的目标覆盖率
    max_questions: int = 200    # 预算上限
    question_type_weights: Dict = {
        "exist": 0.25, "count": 0.25, "status": 0.20,
        "object": 0.15, "comparison": 0.15
    }
```

用法示例：
```python
# 本轮只做 L2，预算100题，目标50%
goal = CoverageGoal(focus_level="L2", target=0.5, max_questions=100)

# 下一轮做 L0，预算50题，目标100%
goal = CoverageGoal(focus_level="L0", target=1.0, max_questions=50)
```

#### Step 2: 明确候选集

```python
# 从 tracker 提取所有缺口，只保留聚焦层级的
gaps = tracker.gaps_as_list()
focus_gaps = [g for g in gaps if g["level"] == focus]
```

缺口格式：
- L0: `{"level": "L0", "node_id": "car_1"}`
- L1: `{"level": "L1", "source": "ego", "direction": "front", "target": "car_1"}`
- L2: `{"level": "L2", "node1": "ego", "node2": "car_1", "node3": "ped_2"}`

#### Step 3: 定预算

```python
# 简单直接：预算 = min(用户设定上限, 实际缺口数)
budget = min(goal.max_questions, len(focus_gaps))
```

**不做三级分配**，全部给聚焦层级。

#### Step 4: 打乱 candidate

```python
random.shuffle(focus_gaps)       # 打乱
focus_gaps = focus_gaps[:budget]  # 取前 n 个
```

- 打乱目的：避免总是从 car_1 → car_2 → ... 顺序出题
- 保证每次生成的问题分布不同，增加多样性

#### Step 5: 为每个缺口生成一个问题

```python
def _generate_one_qa_for_gap(self, gap, question_types, template_usage):
    # 1. 随机选一个问题类型 (exist/count/status/...)
    qtype = random.choice(question_types)
    
    # 2. 生成该类型的候选 QA
    if level == "L0":
        candidates = filler.fill_for_node_gap(gap["node_id"], [qtype])
    elif level == "L1":
        candidates = filler.fill_for_edge_gap(gap["source"], gap["target"], ...)
    elif level == "L2":
        candidates = filler.fill_for_2hop_gap(gap["node1"], gap["node2"], ...)
    
    # 3. 选使用次数最少的模板 (保证模板多样性)
    candidates.sort(key=lambda qa: template_usage.get(qa.template_id, 0))
    return candidates[0]
```

**设计理念**：每个缺口只生成一个问题，节省预算

- 随机选问题类型 → 保证类型多样性
- 优先选少用模板 → 保证模板多样性
- 不做多候选比较 → 节省计算成本

### 4.3 生成后回写（跨级附带覆盖）

```python
# 每生成一题，同时更新三组 KV Map
for qa in all_qa:
    tracker.record_from_qa(qa)
    # 例: 一题 L2 问题同时覆盖:
    #   L2: "ego|car_1|ped_2" → hit_count: 0→1  (目标)
    #   L1: "ego|left|car_1"  → hit_count: 0→1  (免费)
    #   L1: "car_1|front|ped_2" → hit_count: 0→1 (免费)
    #   L0: "car_1"           → hit_count: 0→1  (免费)
    #   L0: "ped_2"           → hit_count: 0→1  (免费)

tracker.save("coverage.json")
```

### 4.4 一个完整例子（三轮生成）

```
场景: scene-0103, frame 25
  - 48 个节点 (L0), 1122 条边 (L1), ~5000 条两跳路径 (L2)
  - 初始覆盖率: L0=60%, L1=30%, L2=10%

═══ 第1轮: 聚焦 L2 ═══
  goal = CoverageGoal(focus_level="L2", target=0.5, max_questions=100)
  缺口: 4500 个 L2 路径未覆盖
  预算: 100 题 (min(100, 4500))
  结果: L0=72% (+12% 附带), L1=45% (+15% 附带), L2=22% (+12% 直接)

═══ 第2轮: 聚焦 L1 ═══
  goal = CoverageGoal(focus_level="L1", target=0.8, max_questions=80)
  缺口: 617 个 L1 边未覆盖 (第1轮已附带覆盖 168 条)
  预算: 80 题
  结果: L0=85% (+13% 附带), L1=65% (+20% 直接), L2=22% (不变)

═══ 第3轮: 聚焦 L0 ═══
  goal = CoverageGoal(focus_level="L0", target=1.0, max_questions=50)
  缺口: 7 个 L0 节点未覆盖
  预算: 7 题 (min(50, 7))
  结果: L0=100%, L1=65%, L2=22%

总计: 187 题, L0 全覆盖
```

---

## 五、关键代码文件索引

| 文件 | 作用 | 核心类/函数 |
|------|------|-----------|
| `template_library.py` | 185个问题模板定义 + TemplateLibrary 管理 | `TemplateEntry`, `TemplateLibrary`, `ALL_TEMPLATES` |
| `template_filler.py` | 模板占位符填充 + 答案计算 | `TemplateFiller`, `SceneGraphIndex`, `fill_for_node_gap/edge_gap/2hop_gap` |
| `coverage_tracker.py` | 三组KV Map + Hash索引 + JSON持久化 | `CoverageTracker`, `CoverageRecord`, `from_scene_graph`, `record_from_qa` |
| `coverage_driven_template_generator.py` | 覆盖率驱动的生成主流程 | `CoverageDrivenTemplateGenerator`, `generate_with_tracker`, `CoverageGoal` |
| `unified_coverage.py` | 统一覆盖率数据结构（闭环用） | `UnifiedCoverageStats`, `CoverageAdapter` |
| `gap_analyzer.py` | 缺口分析 + 生成策略决策 | `GapAnalyzer`, `decide_next_generation`, `CoverageGap` |
| `loop_controller.py` | 闭环控制器（迭代生成直到达标） | `CoverageLoopController`, `LoopConfig`, `run` |
| `qa_validator.py` | 题目质量验证（断点续跑/查重/VLM） | `QAValidator`, `ValidationRecord` |
| `config.py` | 全局配置（方向/状态/类型名称映射） | `TYPE_NAMES`, `STATUS_DISPLAY_NAMES`, `QA_CONFIG` |
| `scene_filter.py` | Phase 0 物体过滤（距离/像素高度/可见度） | `SceneGraphFilter`, `QAFilter`, `filter_scene_graph_file` |
| `pipeline.py` | VQA Pipeline + 5层retry答题 | `VQAPipeline`, `process_question_with_retry`, `VQAResult` |
| `skip_questions.json` | 错题黑名单（5层retry全失败的题目） | JSON 配置文件 |

---

## 六、已完成工作清单

| # | 工作项 | 状态 |
|---|--------|------|
| 1 | 从NuScenesQA官方题集规整所有问题模式，四级分层统计 | ✅ |
| 2 | 按L0/L1/L2覆盖维度重新映射23个提问方向 | ✅ |
| 3 | 合并官方+自有题库+补充新方向，丰富第三级多样性 | ✅ |
| 4 | 修复模板鲁棒性：ref用{ref_id}替代{ref_status}{ref_type} | ✅ |
| 5 | 调研场景图status值域+官方题库属性类型+颜色信息 | ✅ |
| 6 | 同义改写扩充第四级变体 — 206→185模板（删除21非视觉） | ✅ |
| 7 | 覆盖率数据：三组KV map + JSON持久化 + hash优化 | ✅ |
| 8 | 目标导向生成：预算→候选集→打乱→模板选择→生成 | ✅ |
| 9 | TemplateFiller 补全34个answer_logic处理器 | ✅ |
| 10 | QAValidator完善版（断点续跑/VLM/歧义/查重/Excel） | ✅ |
| 11 | 删除21个非视觉模板 + NuScenesQA离散化分析 | ✅ |
| 12 | L2→L1跨级覆盖传播bug修复（记录两条L1边） | ✅ |
| 13 | Phase 0 物体过滤：像素高度→height_3d，焦距→1266 | ✅ |
| 14 | Phase 0 错题黑名单：QAFilter + skip_questions.json | ✅ |
| 15 | 5层retry答案匹配bug修复（yes/no误判） | ✅ |

## 七、待办工作

| # | 工作项 | 优先级 |
|---|--------|--------|
| 1 | GapResolver + ObjectProfile：统一信息获取接口（方案C） | 高 |
| 2 | 复杂问题生成：Gap分析补充更多细节属性查询 | 中 |
