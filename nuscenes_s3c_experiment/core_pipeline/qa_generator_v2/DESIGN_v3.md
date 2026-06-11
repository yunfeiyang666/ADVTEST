# QA Generator v3 设计文档

## 核心变更

### 1. 砍掉 count 类问题
count 问题（"How many X?"）的答案是聚合数字，不对应具体场景图元素，
违反"缺口 = 未覆盖元素 = 答案"的核心模型。

**删除**: 所有 question_type="count" 的模板（47个）

### 2. 砍掉非 CV 可见属性
CV 模型看真实图片答题，以下属性从图片无法判断：
- ❌ 精确速度 (m/s)
- ❌ 精确距离 (meters)
- ❌ TTC (碰撞时间)
- ❌ 速度比较 (哪个更快)
- ❌ 运动方向 (精确朝向角)

**保留的 CV 可见属性**:
- ✅ type (车/人/自行车 — 图片可见)
- ✅ status (moving/stopped/parked — 图片可判断)
- ✅ heading_class (facing_ego/away_ego/lateral — 图片可见车头朝向)
- ✅ direction_8 (front/front-left/... — 图片可见空间位置)
- ✅ distance_bin (near/medium/far — 图片可大致判断)
- ✅ visibility (occluded/visible — 图片可见遮挡)
- ✅ size_class (small/medium/large — 图片可比较大小)

**删除**: L1_VELOCITY_TEMPLATES (15个), distance_threshold精确米数模板

### 3. L2 子图模式：严格 "A的B的C"

L2 的核心结构是**首尾相连两连边**:
```
(A) --[edge1]--> (B) --[edge2]--> (C)
```
- edge1 的尾(B) = edge2 的头(B)
- A, B, C 可以带属性约束 (type, status, heading, ...)
- status 算作双向边 (给 status 更多空间)

#### 3.1 严格模式 (我们的模板)

| 模式ID | 结构 | 示例 |
|--------|------|------|
| chain_dir_dir | A→[dir1]→B→[dir2]→C | "ego前方的car的左边有什么?" |
| chain_dir_status | A→[dir]→B→[status]→B | "ego前方的car是什么状态?" (L1, 但从其他ref出发就是L2) |
| chain_dir_dir+attr | A→[dir1]→B{attr}→[dir2]→C | "ego前方的moving car的左边有什么?" |

#### 3.2 复杂情境变体 (从 NuScenesQA 引入)

NuScenesQA 中有些复杂问题不完全是链式，但**包含**两连边子图。
为增加题集高度，可适当引入:
- 双锚点交集: "What is to the left of A AND the front of B?" → 内含 A→[left]→C 和 B→[front]→C
- 属性约束链: "Is the moving car to the left of the stopped truck to the front of ego?" → 链+双属性约束

### 4. Cypher 查询架构

#### 4.1 为什么必须用 Cypher

参数解析只能做 JSON 点查 (单节点属性)，无法:
- 遍历空间关系边找到满足条件的对象
- 枚举所有两跳路径来计算初始覆盖率
- 评估 L2 问题对 L0/L1 的覆盖贡献

#### 4.2 Cypher 介入的 3 个位置

1. **初始覆盖率计算**: MATCH 所有路径模式，统计已覆盖/未覆盖
2. **缺口采集**: 查询场景图中是否存在满足缺口条件的实例
3. **L2→L0/L1 覆盖贡献**: 执行 Cypher 返回完整路径，自动提取涉及的节点和边

#### 4.3 Neo4j Schema

```cypher
// 节点
(:Object {
    unique_id: "car1",
    type: "car",
    status: "moving",        // moving / stopped / parked
    heading_class: "facing_ego",  // facing_ego / away_ego / lateral
    visibility: "v80-100",   // v0-40 / v40-60 / v60-80 / v80-100
    size_class: "medium",    // small / medium / large
    x: 10.5, y: 3.2          // ego坐标系下的位置
})

// 边 (空间关系)
[:SPATIAL {
    direction_8: "front-left",
    distance_bin: "near",     // near_coll / super_near / very_near / near / visible / far
    angle: 45.2
}]
```

#### 4.4 Cypher 模板示例

```cypher
// L0: 某类型是否存在
MATCH (o:Object {type: $target_type})
RETURN o.unique_id, o.status

// L1: 某方向是否有某类型
MATCH (ref:Object {unique_id: $ref_id})-[r:SPATIAL {direction_8: $direction}]->(obj:Object {type: $target_type})
RETURN obj.unique_id, obj.status, r.distance_bin

// L2: 两跳链式查询
MATCH (ref:Object {unique_id: $ref_id})-[r1:SPATIAL {direction_8: $dir1}]->(mid:Object {type: $mid_type})
      -[r2:SPATIAL {direction_8: $dir2}]->(target:Object)
RETURN ref, r1, mid, r2, target

// 覆盖率: 枚举所有两跳路径
MATCH p = (a:Object)-[r1:SPATIAL]->(b:Object)-[r2:SPATIAL]->(c:Object)
RETURN a.unique_id, r1.direction_8, b.unique_id, r2.direction_8, c.unique_id
```

#### 4.5 LLM→Cypher 流程

```
自然语言问题 → LLM (DeepSeek-R1) → Cypher 查询
                                        ↓
                                   Neo4j 执行
                                        ↓
                                   结果解析 → 答案
```

LLM prompt 包含:
- Neo4j schema 描述
- 几个 few-shot 示例
- 场景图中有哪些节点和关系 (summary)

---

## 实际代码变更清单

### 已修改文件

| 文件 | 变更内容 |
|------|----------|
| `template_library.py` | 移除 count(47)/velocity(15)/approaching/精确米数模板; 新增 L0/L1/L2 heading 模板(13个); L2 模板加 [CHAIN]/[STATUS]/[COMPLEX] 子图结构注释 |
| `config.py` | QUESTION_TYPES 去掉 "count"; 新增 HEADING_CLASSES, VISIBILITY_LEVELS, SIZE_CLASSES; L2 比例从 20%→30% |
| `coverage_driven_template_generator.py` | CoverageGoal.question_type_weights 去掉 count, 权重重分配 (exist:0.30, status:0.30, object:0.20, comparison:0.20) |
| `template_filler.py` | fill_for_*_gap 默认 question_types 去掉 "count"; 新增 heading answer_logic: L0(3分支) + L1(5分支) + L2(7分支) |

### 新建文件

| 文件 | 职责 |
|------|------|
| `cypher_integration.py` | Neo4j schema定义, 场景图→Cypher导入, 查询模板(L0/L1/L2), LLM→Cypher prompt, 结果解析 |
| `cypher_executor.py` | CypherExecutor统一接口(memory/neo4j双后端), InMemoryGraphEngine纯Python图查询, LLM→Cypher Oracle |
| `test_v3_changes.py` | 6项验证测试: 模板清理/heading模板/L2分类/内存引擎/执行器/场景摘要 |

### 模板统计 (v3)

```
总计: 179 模板 (从 ~230+ 精简)
L0: 53  (exist:15, status:15, object:10, comparison:13)
L1: 69  (exist:19, status:15, object:20, comparison:15)
L2: 57  (exist:19, status:16, object:12, comparison:10)

L2 子图模式分类:
  [CHAIN]   严格链式 A→B→C: 18 模板
  [STATUS]  同状态双向边:     9 模板
  [COMPLEX] 复杂情境变体:    19 模板
  其他(nearest/between等):  11 模板

Heading 模板: 13 (L0:4, L1:6, L2:3)
```

### Pipeline 中 Cypher 介入的 3 个位置

```
① 初始覆盖率计算
   CypherExecutor.enumerate_nodes/edges/2hop_paths()
   → 枚举场景图全部 L0/L1/L2 元素，初始化 CoverageTracker

② 缺口采集
   CypherExecutor.query_gap(gap)
   → 查询满足缺口条件的实例，验证缺口是否有对应场景实例

③ L2→L0/L1 覆盖贡献
   CypherExecutor.compute_l2_coverage_contribution(n1, n2, n3)
   → 返回 CoverageContribution{l0_nodes, l1_edges, l2_paths}
   → CoverageTracker 同时更新三层覆盖
```
