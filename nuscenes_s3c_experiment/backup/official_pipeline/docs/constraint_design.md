# 约束方法完整设计参考

> 贯穿统一场景，从架构到每个方法，每处都附可执行例子。  
> 对应代码：`gap_pipeline/constraint_methods.py` → `CumulativeConstraintChain`

---

## 一、全局流程与三种"是否保留上层成果"

### 1.1 约束链在整个 pipeline 中的位置

```
Step 5c  Neo4j 候选集查询
         ↓  返回同方向所有对象（5~15个）+ referents
         ↓  这是"宽查询"，目标隐没在一群候选里
Step 5d  ConstraintChain / CumulativeConstraintChain
         ↓  逐层添加约束，把候选集从 N 个收束到 1 个
         ↓  输出唯一限定问题 + 答案
Step 5e  模板补充生成
```

约束链的输入：
- `gap_target`：目标对象（type / status / dir8 / dist_level / actual_dist）
- `candidates`：同方向全部候选（含目标）
- `ctx["referents"]`：预取的"指向目标的其他节点"（含 sibling_ids）

约束链的输出：一条 `TightenResult`（question / answer / is_unique / method_used）

---

### 1.2 三种"保留上层成果"的模式

| 模式 | 上层 | 下层 | 是否保留 | 原因 |
|------|------|------|----------|------|
| **A** | 属性（type/status/...） | 属性（再加一个） | ✅ 保留 | 自然叠加，等价于直接组合试验 |
| **B** | 属性（type/status） | two_hop referent | ✅ 保留 | 属性缩小后 sibling 重投影，无需额外查询 |
| **C** | 属性（任意） | count / yesno | ❌ 不保留 | 语义改变："有几辆车" ≠ "先筛车再计数" |

> **为什么 B 成立而 C 不成立？**
> 
> B：step 5c 预取的 sibling_cnt 是按全集计算的。属性缩小后，在 Python 里过滤：
> `sibling_ids ∩ narrowed_ids`，若结果是 `{target}` 则唯一，无需再查 Neo4j。
>
> C：计数题的语义本身就应该"针对某类对象计数"，这由 type 属性直接参数化，
> 不是"先用 type 缩小候选集，再数剩余个数"的两步走。

---

### 1.3 完整执行层级

```
阶段 1   1-2 属性组合      type / status / dir8 / dist_ord 的所有 1~2 属性子集
阶段 2a  纯二跳 referent   全集中 sibling_cnt == 1 的节点
阶段 2b  属性+two_hop      ← 关键！type/status 收缩后 sibling_ids ∩ narrowed
阶段 3   3-4 属性组合      极少命中，作为属性层兜底
阶段 4   双二跳 referent   两个 referent 交集唯一
阶段 5   锚点引入          src 节点状态作为引导词
阶段 6   计数题（不积累）
```

---

## 二、统一场景（全文均用此场景）

`scene-0553 frame-8`，ego 车前方（dir4=front）共 **6 个候选对象**：

```
id          type        status   dir8          dist_level  actual_dist
──────────────────────────────────────────────────────────────────────
car1        car         moving   front-left    close        8.2 m
car2        car         stopped  front-right   medium      18.5 m
car3        car         moving   front         close        9.7 m  ← gap target
car4        car         moving   front         medium      14.3 m
truck1      truck       moving   front         far         32.1 m
pedestrian1 pedestrian  moving   front-left    very_close   3.4 m
```

预取 referents（step 5c：指向 car3 的节点）：

```
ref_id      ref_type    指向car3的方向  sibling_ids（该方向全部同类对象）  sibling_cnt
──────────────────────────────────────────────────────────────────────────────────
car1        car         right           [car3, truck1]                      2   ← 全集不唯一
car4        car         left            [car3, truck1]                      2   ← 全集不唯一
pedestrian1 pedestrian  right           [car3]                              1   ← 全集唯一！
```

> **car1→right sibling_cnt=2**：意味着从 car1 右方看，有 car3 和 truck1 两个目标，
> 纯二跳不唯一。但如果先用 type=car 缩小，truck1 被排除，car1→right 就唯一了。

---

## 三、各层方法详解（每层附例子）

### 3.1 阶段 1 — 属性组合（1 → 2 个属性）

---

#### P-type：目标类型唯一

**前提**：同方向中目标类型只有一个实例。  
**本例适用目标**：`truck1`（type=truck，场景中唯一）

```
候选集：[car1, car2, car3, car4, truck1, pedestrian1]   — 6 个
约束：  WHERE type = 'truck'
剩余：  [truck1]                                         — 1 个 ✅
```

生成问题：
> **What is the truck to the front of ego?**  
> Answer: truck

---

#### P-status：目标状态唯一

**前提**：同方向中目标状态只有一个实例。  
**本例适用目标**：`car2`（stopped，场景中唯一）

```
候选集：[car1, car2, car3, car4, truck1, pedestrian1]   — 6 个
约束：  WHERE status = 'stopped'
剩余：  [car2]                                           — 1 个 ✅
```

生成问题：
> **What is the stopped thing to the front-right of ego?**  
> Answer: car

---

#### P-dir8：精确 8 方向细化

**前提**：在 dir4 大方向内，目标 dir8 只有一个实例。  
**本例适用目标**：`car2`（dir8=front-right，场景中唯一）

```
候选集：[car1, car2, car3, car4, truck1, pedestrian1]   — 6 个
约束：  WHERE dir8 = 'front-right'
剩余：  [car2]                                           — 1 个 ✅
```

生成问题：
> **What thing is directly to the front-right of ego?**  
> Answer: car

---

#### P-dist_ord：距离排序（closest/farthest）

**前提**：目标是同类型同方向中最近或最远的。  
**本例适用目标**：`car3`

```
dist_ord 提取：
  同 type=car AND dir8=front 的对象：car3(close, 9.7m) 和 car4(medium, 14.3m)
  car3 档位(close) < car4 档位(medium) → car3 是最近的 → dist_ord = 'closest'

候选集过滤（type=car+dir8=front，取 closest）：
  ranks: car3→0(close), car4→1(medium)
  best_rank = 0 → 保留 car3
剩余：  [car3]                                           — 1 个 ✅
```

> **为什么没有直接用 1-属性 dist_ord 成功？**  
> `dist_ord` 单独对全集无效（全集有 6 种类型），必须限定同方向同类型后才有排序意义。  
> 在 `_extract_attrs` 里已预先限定：只在 `type=car AND dir8=front` 子集里计算最近/最远。

生成问题：
> **What is the closest car to the front of ego?**  
> Answer: car

---

#### P-type+dir8：类型+精确方向（2 属性）

**适用目标**：`car3`（当 dist_ord 不可用时）

```
候选集：6 个
约束：  WHERE type = 'car' AND dir8 = 'front'
剩余：  [car3, car4]                                     — 2 个 ❌（还有 car4）
```

→ 单 type+dir8 对 car3 失败，需继续到 `type+dir8+dist_level`（3 属性）或走 two_hop 路线。

---

#### P-type+status：类型+状态（2 属性）

**适用目标**：`car2`（car + stopped 唯一）

```
候选集：6 个
约束：  WHERE type = 'car' AND status = 'stopped'
剩余：  [car2]                                           — 1 个 ✅
```

生成问题：
> **What is the stopped car to the front-right of ego?**  
> Answer: car

---

### 3.2 阶段 2a — 纯二跳 referent（全集 sibling_cnt == 1）

**前提**：`ctx["referents"]` 中存在 `sibling_cnt == 1` 的节点。  
**本例适用目标**：`car3`，通过 `pedestrian1`

```
referents 中 pedestrian1 的数据：
  ref_id   = pedestrian1
  dir8     = right
  sibling_ids  = [car3]
  sibling_cnt  = 1    ← 全集中从 pedestrian1 右方只有 car3 ✅

候选集变化：不直接过滤 candidates，靠 sibling_cnt 保证唯一性
```

生成问题：
> **What car is to the right of the pedestrian to the front-left of ego?**  
> （pedestrian1 有 ego_dir8=front-left，用 ego 方向描述参照物）  
> Answer: car

---

### 3.3 阶段 2b — 属性收缩 + two_hop 异质叠加（关键新层）

**场景**：`pedestrian1` 的 `sibling_cnt=1` 已在 2a 处理；  
此处处理 `car1` 和 `car4`（全集 `sibling_cnt=2`，纯二跳失败，但属性收缩后可唯一）。

**适用目标**：`car3`，通过 `car1`

```
Step 1：尝试属性 type=car 收缩候选集
  narrowed = {car1, car2, car3, car4}   — 从 6 缩到 4，保留

Step 2：在 narrowed 上重新投影 sibling_ids
  car1→right: sibling_ids = [car3, truck1]
  overlap = [car3, truck1] ∩ {car1, car2, car3, car4}
           = {car3}          ← truck1 不是 car，被排除 ✅

候选收束到：{car3}  —  1 个 ✅
联合方法名：type+two_hop
```

生成问题：
> **What car is to the right of car1?**  
> Answer: car

**为什么不需要额外 Neo4j 查询？**  
`sibling_ids` 在 step 5c 已全量预取，Python 做集合交集即可，耗时 < 0.1ms。

**对比纯二跳（全集 sibling_cnt=2，失败）**：

| | 全集 sibling | 属性收缩后 sibling ∩ narrowed |
|-|-------------|------------------------------|
| car1→right | [car3, truck1]（2个） | [car3, truck1] ∩ {car类} = {car3}（1个）✅ |
| car4→left  | [car3, truck1]（2个） | [car3, truck1] ∩ {car类} = {car3}（1个）✅ |

**收缩的属性一定要出现在问题里**（否则语义不完整）：

| 属性收缩 | 联合问题 | 是否完整 |
|----------|---------|---------|
| type=car | "What **car** is to the right of car1?" | ✅ |
| status=moving | "What **moving** thing is to the right of car1?" | ✅ |
| type+status | "What **moving car** is to the right of car1?" | ✅ |
| dir8 | 不用于入口收缩（问题文本和方位混乱） | ❌ |

---

### 3.4 阶段 3 — 3~4 属性组合（兜底）

仅当以上所有层失败时到达。以 `car3` 为例（假设 dist_ord 也不可用）：

```
候选集：6 个
约束：  WHERE type='car' AND dir8='front' AND dist_level='close'
剩余：  [car3]                                           — 1 个 ✅
```

生成问题：
> **What is the close car at the front of ego?**  
> Answer: car

**缺点**：问题中出现 "close"（档位词），不如 "closest"（相对词）自然；  
且约束数多（3 个），VLM 在视觉上难以验证所有维度。

---

### 3.5 阶段 4 — 双二跳 referent

当单个 referent 不能唯一，用两个 referent 的 sibling 交集：

```
假设场景：
  car4 → left:  sibling_ids = [car3, car1]  （从 car4 左方看到 car3 和 car1）
  car1 → right: sibling_ids = [car3, car4]  （从 car1 右方看到 car3 和 car4）

交集：{car3, car1} ∩ {car3, car4} = {car3}  — 唯一 ✅
```

生成问题：
> **What car is both to the left of car4 and to the right of car1?**  
> Answer: car

---

### 3.6 阶段 5 — 锚点引入

通过描述 `src` 节点（非 ego）的状态作为唯一识别词，再问 src 旁边的对象。

```
场景：src = truck1（场景中唯一的 truck，moving 状态）
  ctx: src_type=truck, src_status=moving
```

生成问题：
> **There is a moving truck; what car is to the front of it?**  
> Answer: car

**适用条件**：src 本身在场景中唯一可识别（类型唯一 or 状态唯一）。

---

### 3.7 阶段 6 — 计数题（不积累上层属性）

当所有唯一性约束均失败时，退化为计数题。

```
场景：前方有 4 辆 car，任何约束都无法唯一锁定某辆
约束：type = 'car'   （直接对全集计数，不走"先缩小再计数"的路径）
答案：4
```

生成问题：
> **How many cars are to the front of ego?**  
> Answer: 4

**为什么不保留上层成果？**

```
❌ 错误的"保留"做法：
  先用 status=moving 缩小到 3 辆 → 再计数 → 得到 3
  但这道题问的是"有几辆 moving car"，不是"有几辆 car"。
  如果 status=moving 进入了问题，就不是"退化"而是"换了一道题"。

✅ 正确做法：
  计数题直接用 type（或 type+status）作为计数对象，不依赖先前的缩小路径。
  "How many moving cars are to the front of ego?" 是一道完整的新题，不是降级。
```

---

## 四、跨方法对比：同一 gap target 的五种问题

gap target = `car3`，用不同方法生成的问题：

| 方法 | 问题 | 属性数 | 可读性 | 命中率(实测) |
|------|------|--------|--------|------------|
| dist_ord（1属性） | What is the closest car to the front? | 1 | ⭐⭐⭐⭐⭐ | 13% |
| two_hop（全集） | What car is to the right of pedestrian1? | 1（参照物） | ⭐⭐⭐⭐⭐ | 31% |
| type+two_hop（跨层） | What car is to the right of car1? | type+参照物 | ⭐⭐⭐⭐⭐ | 新增 |
| type+dir8+dist | What is the close car at the front? | 3 | ⭐⭐⭐ | 7% |
| type+status+dir8+dist | What is the moving close car at the front? | 4 | ⭐⭐ | 2% |

> **规律**：属性数越少、使用参照物越多，问题越自然、VLM 越容易回答。

---

## 五、实测数据（100 cells，ConstraintChain，scene-0553 全量边）

```
方法                   成功次数   占比   备注
────────────────────────────────────────────────────
two_hop_referent         31      31%   ← 第一名
dual_hop_referent        20      20%   ← 第二名
ordinal_by_distance      13      13%   最近/最远
dist_order                6       6%   档位版距离序
type_filter               5       5%
dir8_refine               5       5%
status_anchor             3       3%
type_status_anchor        3       3%
其他属性组合              <3      <3%
────────────────────────────────────────────────────
count_fallback            8       8%   不唯一
────────────────────────────────────────────────────
唯一锁定率：92/100 = 92%
```

**每步耗时（100 cells 均值）**：

```
Step 5a  LLM 生成上下文 Cypher   30136 ms  （API timeout fallback）
Step 5b  Neo4j 上下文查询          107 ms
Step 5c  候选集 + referent 预取     62 ms
Step 5d  约束链全部计算              0.2 ms  ← 约束链耗时可忽略不计
Step 5e  模板填充                   0.4 ms
```

> 约束方法的复杂度对 **运行时间** 几乎无影响（全部 <1ms）。  
> 选择方法的唯一标准是：**问题对 VLM 的可回答性与自然度**。

---

## 六、设计决策速查

| 问题 | 决策 |
|------|------|
| 应该用哪几种约束？ | **优先跨对象参照（two_hop/attr+two_hop）+ ordinal；属性组合作兜底** |
| 属性组合结果应保留吗？ | ✅ 保留，传给下一层（A/B 模式均可） |
| 属性缩小后可以接 two_hop 吗？ | ✅ 可以，用 `sibling_ids ∩ narrowed_ids` 重新投影（模式 B） |
| 属性缩小后可以接 count 吗？ | ❌ 不可以，语义改变（模式 C 不保留） |
| referent 预取需要多少条？ | 取 sibling_cnt 最小的前 10 条，attr+two_hop 层会从中筛选 |
| 3-4 属性组合问题自然吗？ | 一般，尽量靠 two_hop 解决，3 属性作最后手段 |
| 计数题和唯一性问题能混用吗？ | 建议分离，count 题单独计入"非唯一覆盖"指标 |

---

## 七、约束质量两级覆盖率指标

```python
coverage_any    = edge_counts[key] > 0        # 任何 QA 都算（含 count/yesno）
coverage_unique = edge_unique_counts[key] > 0 # 至少有一条 is_unique=True 的 QA

quality_rate = coverage_unique / coverage_any
# quality_rate 越接近 1，说明 count/yesno 兜底越少，约束方法效果越好
```

当前 100 cells 实测：`unique_rate = 92%`，`count_fallback = 8%`。

---

*文档最后更新：2026-03-23，整合所有约束设计讨论。*
