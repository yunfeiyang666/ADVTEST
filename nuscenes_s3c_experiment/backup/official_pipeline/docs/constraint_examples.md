# 约束方法详解——实测效果与典型例子

> 实测数据（100 cells，启用 ConstraintChain）：
> 
> | 排名 | 方法 | 成功次数 | 占比 | 评价 |
> |------|------|-----------|------|------|
> | 1 | two_hop_referent | **31** | 31% | ★ 最强，跳进对象参照 |
> | 2 | dual_hop_referent | **20** | 20% | ★★ 当单跳不够时用两个 |
> | 3 | ordinal_by_distance | 13 | 13% | “最近/最远的 X” |
> | 4 | dist_order | 6 | 6% | 档位版距离序 |
> | 5 | type_filter | 5 | 5% | 类型在方向中唯一 |
> | 6 | dir8_refine | 5 | 5% | 8方向细化 |
> | 7 | status_anchor | 3 | 3% | 状态唯一 |
> | — | count_fallback | 8 | 8% | 退化为计数题 |
> 
> **结论：跨对象参照（two_hop+dual_hop）占 51% 的唯一定位成功。**
> 属性组合方法合计只有 26 次（且问题文本较复杂）。
>
> 每个例子使用统一场景背景，展示：应用前候选数 → 施加约束后候选数 → 生成的问题文本。

---

## 公用场景背景

ego 车前方（dir4=front）共有 5 个候选对象：

```
id          tgt_type    tgt_status  dir8          dist_level  actual_dist
──────────────────────────────────────────────────────────────────────────
car1        car         moving      front-left    close       8.2 m
car2        car         stopped     front-right   medium      18.5 m
truck1      truck       moving      front         far         32.1 m
pedestrian1 pedestrian  moving      front-left    very_close  3.4 m
car3        car         moving      front         close       9.7 m
```

gap cell：`ego → car3`（car3 未被任何 QA 覆盖）

应用前（宽泛查询）Cypher：
```cypher
MATCH (src:Object {unique_id: 'ego'})-[r:RELATES_TO]->(tgt:Object)
WHERE r.direction_4 = 'front'
RETURN tgt.unique_id AS id, tgt.type AS tgt_type,
       tgt.status AS tgt_status, r.direction_8 AS dir8,
       r.predicates[1] AS dist_level
```
**返回 5 条**（car1 car2 truck1 pedestrian1 car3）

---

## P1  type_filter — 类型在同方向中唯一

**前提**：gap_target 的类型（truck1=truck）在候选集中唯一。

**本例目标**：car3（类型=car，但 car 有 3 辆，P1 对 car3 失败）  
**改用 truck1 演示**：候选集中 truck 只有 1 辆。

应用约束：`tgt.type = 'truck'`
```cypher
... WHERE tgt.type = 'truck'     -- 返回 1 条：truck1
```
**结果：1 条 ✅ 唯一**

生成问题：
> **What is the truck to the front of ego?**  
> Answer: truck

---

## P2  status_anchor — 状态在同方向中唯一

**前提**：gap_target 的状态在候选集中唯一。  
**目标**：car2（stopped），候选中只有 car2 是 stopped。

应用约束：`tgt.status = 'stopped'`
```cypher
... WHERE tgt.status = 'stopped'    -- 返回 1 条：car2
```
**结果：1 条 ✅ 唯一**

生成问题：
> **What is the stopped thing to the front-right of ego?**  
> Answer: car

---

## P3  type_status_anchor — 类型+状态组合唯一

**前提**：单独用 type 失败（3 辆 car），单独用 status 失败（3 辆 moving），  
但 type=car AND status=stopped 唯一。

应用约束：`tgt.type = 'car' AND tgt.status = 'stopped'`
```cypher
... WHERE tgt.type = 'car' AND tgt.status = 'stopped'   -- 返回 1 条：car2
```
**结果：1 条 ✅ 唯一**

生成问题：
> **What is the stopped car to the front-right of ego?**  
> Answer: car

---

## P4  dir8_refine — 子方向细化（8方向代替4方向）

**前提**：从 dir4=front 分组中，gap_target 的 dir8 唯一。  
**目标**：truck1（dir8=front），候选中只有 truck1 在 front（正前，非 front-left/right）。

应用约束：`r.direction_8 = 'front'`
```cypher
... WHERE r.direction_8 = 'front'    -- 返回 2 条：truck1, car3
```
**结果：2 条 ❌ 不唯一（car3 也在 front）**  
→ P4 对本 gap 失败，需继续下一方法。

若改为查 truck1：候选中只有 truck1 在 `front`。**1 条 ✅**

生成问题（truck1 演示）：
> **What truck is directly to the front of ego?**  
> Answer: truck

---

## P5  dual_reference — 双参考点方向交集

**前提**：需要 ctx 中有 ego_dir8 字段（ego 到目标的方向）。  
**目标**：car3（src=car1, dir8=front; ego→car3 方向=front）。

通过 OPTIONAL MATCH 获取 ego→car3 方向：
```cypher
OPTIONAL MATCH (:Object {unique_id: 'ego'})-[ego_r:RELATES_TO]->(tgt)
```

应用双约束：`from car1 = front` AND `from ego = front`  
候选中同时满足"在 car1 前方 AND 在 ego 前方"的对象：仅 car3

**结果：1 条 ✅ 唯一**

生成问题：
> **What is the car that is both to the front of car1 and the front of ego?**  
> Answer: car

---

## P6  dist_order — 距离档位序（closest/farthest）

**前提**：gap_target 是同类型同方向中距离最近或最远的。  
**目标**：car3（close=8m，同方向 car1 也是 close=8.2m，car2 是 medium）

car 类型，同 dir8=front 中：car3(close 9.7m)，其他 front 方向的 car 没有  
→ 对 car3 单独，前方 car 只有 car3 和 car1(front-left) car2(front-right)，dir8=front 里只有 car3  

**改用 car1 演示**：car1 在 front-left，同方向同类型只有 car1，没有其他 car 在 front-left  
→ P6 直接唯一，但这其实是 P1/P4 更简单，P6 通常用于有多辆同类型同方向时。

**真实 P6 场景（同方向两辆 car）**：假设 car1(close) 和 car4(far) 都在 front-left  
→ 应用 closest：返回 car1 **1 条 ✅**

生成问题：
> **What is the closest car to the front-left of ego?**  
> Answer: car

---

## P7  type_dist_combo — 类型+距离档位联合

**前提**：type 单独不唯一，dist_level 单独不唯一，但 type+dist_level 组合唯一。  
**目标**：car2（type=car, dist_level=medium）

候选中 type=car AND dist_level=medium 只有 car2：
```cypher
... WHERE tgt.type = 'car' AND r.predicates[1] = 'medium'   -- 返回 1 条：car2
```
**结果：1 条 ✅ 唯一**

生成问题：
> **What is the medium car to the front of ego?**  
> Answer: car

---

## P8  type_dir8_dist_combo — 类型+dir8+距离三元组

**前提**：需要三属性联合才能唯一。  
**目标**：car3（type=car, dir8=front, dist_level=close）

候选中 type=car AND dir8=front AND dist_level=close：
```cypher
... WHERE tgt.type='car' AND r.direction_8='front' AND r.predicates[1]='close'
```
**结果：1 条 ✅ 唯一**（car1 是 front-left，car2 是 medium）

生成问题：
> **What is the close car at the front of ego?**  
> Answer: car

---

## P9  all_props_combo — 四属性全组合（最强单跳）

**场景**：type + status + dir8 + dist_level 四个属性全部联合。  
**目标**：car3（car, moving, front, close）

```cypher
... WHERE tgt.type='car' AND tgt.status='moving'
    AND r.direction_8='front' AND r.predicates[1]='close'
```
**结果：1 条 ✅ 唯一**

生成问题：
> **What is the moving close car at the front of ego?**  
> Answer: car

---

## P10  ordinal_by_distance — 按实际米数精确排序

**前提**：需要 ctx 中的 actual_dist 字段（e.g. 9.73m）。  
**目标**：pedestrian1（3.4m，是所有前方对象中最近的）

同类型同方向 pedestrian 只有 pedestrian1，P1 已够；但若有 pedestrian2(7.1m) 共存：
→ actual_dist 3.4 < 7.1 → closest

```python
# 按实际浮点距离排序，gap_d=3.4 < min(other_ds=7.1) → 唯一最近
```
**结果：1 条 ✅ 唯一**（P6 用档位，P10 用实际米数，精度更高）

生成问题：
> **What is the closest pedestrian to the front-left of ego?**  
> Answer: pedestrian

---

## P11  two_hop_referent — 单二跳 referent

**场景**：前方有两辆 car 且所有单跳属性都不唯一。通过第三个节点 R 引用目标。

预取 referents（指向 car3 的节点，其中 sibling_cnt=1 表示从 R 出发该方向只有 car3）：
```cypher
MATCH (ref:Object)-[r:RELATES_TO]->(tgt:Object {unique_id: 'car3'})
WHERE ref.unique_id <> 'ego'
...RETURN ref.unique_id, ref.type, r.direction_8, sibling_cnt
```
| ref_id    | ref_type | dir8  | sibling_cnt |
|-----------|----------|-------|-------------|
| truck1    | truck    | right | 1           |  ← 从 truck1 的右方只有 car3

**结果：sibling_cnt=1 ✅ 通过 truck1 唯一定位**

生成问题：
> **What car is to the right of truck1?**  
> （或若 truck1 有 ego_dir8：**What car is to the right of the truck to the front of ego?**）  
> Answer: car

---

## P12  dual_hop_referent — 双二跳 referent 交集

**场景**：单个 referent 的 sibling_cnt > 1（即从 R 出发该方向有多辆同类车），  
两个 referent 的候选集交集才唯一。

```
car5 → (front) → {car3, car7}   sibling_cnt=2
car6 → (left)  → {car3, car8}   sibling_cnt=2
交集：{car3} → 唯一 ✅
```

生成问题：
> **What car is both to the front of car5 and the left of car6?**  
> Answer: car

---

## P13  anchor_intro — 先引入锚点再问

**场景**：src 节点本身有可识别的唯一状态。  
**目标**：通过描述 src=bus1（唯一的一辆静止 bus）来定位其前方的 car3。

ctx 中 src_status=stopped, src_type=bus：
```
There is a stopped bus; what car is to the front of it?
```
**答案：car**（通过锚点自然唯一定位）

生成问题：
> **There is a stopped bus; what car is to the front of it?**  
> Answer: car

---

## P14  count_fallback — 转为计数题

**场景**：前方存在 3 辆 car，任何约束都无法唯一锁定 car3（所有属性都重复）。  
退化为计数题，答案是 3。

```cypher
MATCH (src)-[r]->(tgt) WHERE r.direction_4='front' AND tgt.type='car'
RETURN count(tgt)   -- 返回 3
```

生成问题：
> **How many cars are to the front of ego?**  
> Answer: 3

---

## P15  yesno_fallback — 兜底存在性问题

**场景**：P14 也不适合（如 tgt_type 未知），最终兜底。

生成问题：
> **Is there a moving car to the front of ego?**  
> Answer: Yes

---

## 约束层级架构设计说明

### 三种“是否保留上一层成果”的模式

```
模式 A  属性+属性 —— 保留，联合放入下一层（已实现）
  type → 3个，不唯一 → 加 status → 1个 ✔
  问题："What stopped car to the front of ego?"   ← type+status

模式 B  属性+two_hop —— 保留（新增）
  type=car 将候选集缩小：5个 → 3辆 car
  在 3辆 car 里重新校验 sibling_ids：
    truck1→right 的 sibling_ids=[car1,car3] ∩ {car1,car2,car3} = {car1,car3} ×
    改用 status=moving：候选集缩小为 {car1,car3}，
    truck1→right 的 sibling_ids=[car1,car3] ∩ {car1,car3} = {car1,car3} ×
    继续用 type+status：{car3} ∨ sibling∩narrowed={car3} ✔
  问题："What car is to the right of truck1?"         ← type+two_hop

模式 C  任意属性+count/yesno —— 不保留
  type → 3个…再加 count → "How many cars" 而不是 "How many things"
  这改变了语义，应该在 type 上直接生成计数题
  而不是先用 type 缩小、再进入 count
```

### 关键区别：A 和 B 在哪里分岔？

**A（属性+属性）**：缩小后继续用属性维度过滤，等价于直接组合试验。

**B（属性+two_hop）**：step 5c 预取的 `sibling_cnt` 是封全集计算的，  
缩小后用 Python 重新投影：`sibling_ids ∩ narrowed_ids`，无额外 Neo4j 查询。  
这一步使得原本 `sibling_cnt > 1`（不唯一）的 referent 在小范围内可能变为 `=1`。

### 实现层级顺序（CumulativeConstraintChain）

```
阶段 1   1-2 属性组合    (type, status, dir8, dist_ord 的所有 1、2 属性子集)
阶段 2a  纯二跳 referent   (sibling_cnt==1 在全集中已唯一)
阶段 2b  属性+two_hop      ← 新增！type/status 小幅收缩后 sibling∩narrowed
阶段 3   3-4 属性组合    (5个超过 3 属性的组合）
阶段 4   双二跳 referent   (dual_hop_referent)
阶段 5   锁点引入        (anchor_intro)
阶段 6   计数题（无属性积累，全集计数）
```

---

## 多重叠加约束（CumulativeConstraintChain）完整示例

### 场景

ego 前方（front）共 6 辆 car，全部 moving，属性高度重复：

```
id    type  status   dir8          dist_level
car1  car   moving   front-left    close
car2  car   moving   front-left    medium
car3  car   moving   front         close      ← gap target
car4  car   moving   front         medium
car5  car   moving   front-right   close
car6  car   moving   front-right   far
```

### 搜索过程（CumulativeConstraintChain）

**1属性组合**（4选1）：

| 组合 | 过滤后数量 | 唯一？ |
|------|-----------|--------|
| type | 6 | ❌ |
| status | 6 | ❌ |
| dir8 | 2（car3+car4 都在 front）| ❌ |
| dist_ord | car3=close 且 car4=medium，car3 是 front 组中最近 → **1** | ✅ |

→ **`dist_ord` 单属性即唯一！**

但若 car3 和 car4 都是 close（并列最近）：  
`dist_ord` 不可用 → 继续 2 属性组合。

**2属性组合**（4选2=6种）：

| 组合 | 过滤后数量 | 唯一？ |
|------|-----------|--------|
| type+status | 6 | ❌ |
| type+dir8 | 2（car3+car4）| ❌ |
| type+dist_ord | 2（car3+car5 都是 close）| ❌ |
| status+dir8 | 2 | ❌ |
| status+dist_ord | 2 | ❌ |
| **dir8+dist_ord** | front AND closest → car3 **1** | ✅ |

→ 最终用 `dir8+dist_ord` 两属性唯一定位。

对应问题：
> **What is the closest car to the front of ego?**  
> Answer: car

### 与 ConstraintChain 的对比

| 方法 | 尝试了哪些 | 最终使用 | 问题文本 |
|------|-----------|---------|---------|
| ConstraintChain | P1→P2→P3→P4→P6→P7→P8→P9 | P8(type+dir8+dist) | "What is the close car at the front of ego?" |
| CumulativeChain | type→status→dir8→dist_ord→type+status→type+dir8→type+dist_ord→status+dir8→status+dist_ord→**dir8+dist_ord** | dir8+dist_ord | "What is the closest car to the front of ego?" |

**关键差异**：
- ConstraintChain 用 P8（type+dir8+dist）= 3 个属性，问题包含 "close car"（档位词）
- CumulativeChain 找到 dir8+dist_ord = 2 个属性（最简），问题更自然："closest car"（相对词，VLM 更容易理解）
- CumulativeChain 不包含 type 是因为"front 方向只有 car"时 type 冗余；若有 truck 混入，会自动升级为 type+dir8+dist_ord 三元组

---

## 关于覆盖率的定义澄清

### 当前机制（CoverageMap）

CoverageMap 初始全为 0（所有 edge 未覆盖），每生成一条 QA 对调用 `cmap.update(qa)` 将该 edge 计数 +1。

**这是正确设计**：覆盖率不是预计算的，而是通过生成 QA 来"挣到"的。初始 0% 覆盖率是正常的。

### 什么算"覆盖"

| 级别 | 定义 | 代码中体现 |
|------|------|-----------|
| **any_qa** | 该 edge 有任意一条 QA（包括 yesno fallback）| `_edge_counts[key] > 0` |
| **unique_qa** | 该 edge 有至少一条 `is_unique=True` 的 QA（约束唯一锁定）| 需要额外计数器 |

### 建议区分两个指标

- `coverage_any`：宽覆盖，表示"这条边被问到过"
- `coverage_unique`：有效覆盖，表示"这条边有高质量唯一性问题"

两者差距越大，说明 fallback（count/yesno）题越多，意味着约束方法需要改进。

目前 `timing_log.jsonl` 中的 `unique_qa_cells` 字段记录了每次运行中 `is_unique=True` 的 cell 数量，可以用来追踪这一比例。
