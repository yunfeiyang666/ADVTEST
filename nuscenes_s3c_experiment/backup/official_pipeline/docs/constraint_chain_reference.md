# 约束链完整参考手册

> 版本 v4.0（2026-04-01），覆盖：方法表、架构决策、候选集漏斗、复杂案例逐行解析、难题设计、RQ1 模板

---

## 一、约束方法完整参考表（P1–P15 → CumulativeChain 重构后）

> 注：以下编号对应原 ConstraintChain 的 P1-P15；CumulativeConstraintChain 采用动态搜索，顺序有所不同。

| 编号 | 方法名 | 核心数学思想 | Python 伪代码 | 预期缩减倍率 | 实测命中（L2 50cells） |
|------|--------|------------|--------------|------------|----------------------|
| P1 | type_filter | 目标类型在候选集唯一：∀c∈others, c.type≠gap.type | `[c for c in cands if c.type==gap.type]` | 中（稀有类型高） | 2次（4%）|
| P2 | status_anchor | 目标状态唯一：∀c∈others, c.status≠gap.status | `[c for c in cands if c.status==gap.status]` | 中（状态多样时高）| 1次（2%）|
| P3 | type_status_anchor | type ∩ status 唯一 | `[c for c in cands if c.type==t and c.status==s]` | 中高 | 1次（2%）|
| P4 | dir8_refine | dir4大方向里用dir8细分（8方向→3子方向）| `[c for c in cands if c.dir8==gap.dir8]` | 中（dir4÷3）| 2次（4%）|
| P5 | dual_reference | ego_dir8 × src_dir8 双向交集 | `[c for c in cands if c.dir8==d and c.ego_dir8==e]` | 高（两维正交）| 0次（本次L2未触发）|
| P6 | dist_order | 同type同dir8子集里距离极值 | `min/max` on `dist_level` rank | 中（档位粒度粗）| 0次 |
| P7 | type_dist_combo | type × dist_level 联合 | `type==t and dist_level==d` | 中高 | 0次 |
| P8 | type_dir8_dist_combo | type × dir8 × dist 三元组 | `type==t and dir8==d8 and dist==d` | 高 | 0次 |
| P9 | all_props_combo | 四属性全联合（最强单跳属性约束）| 4-field AND filter | 极高 | 0次 |
| P10| ordinal_by_distance | 同type同dir8里按实际米数排序，1st or last | sort by `actual_dist` | 高（精确距离）| 1次（dist_ord，2%）|
| P11| two_hop_referent | 找 R：sibling_cnt(R, dir_D, tgt_type)==1 | `ref.sibling_cnt == 1` | 极高（31%↑）| 22次（44%）|
| P12| dual_hop_referent | 两referent交集：ids(R1)∩ids(R2)={target} | `set(r1.sibling_ids) & set(r2.sibling_ids)` | 极高（复杂场景）| 9次（18%）|
| P13| anchor_intro | src本身有唯一识别属性，先描述src | 不过滤candidates，靠src唯一性 | 高（src稀有时）| 4次（8%）|
| P14| count_fallback | 退化：计数题（已替换为yesno）| 已移除 | — | — |
| P15| yesno_fallback | 存在性问题（最终兜底，is_unique=False）| 恒返回Yes | 零（兜底）| 0次（本次100%唯一）|

**新增方法（CumulativeChain扩展）**：

| 方法名 | 核心思想 | 实测命中 |
|--------|---------|---------|
| type+two_hop | type属性缩小候选后，在小集合重算sibling_ids∩narrowed | 5次（10%）|
| status+two_hop | status属性缩小后二跳 | 1次（2%）|
| dir8+dist_ord | 方向+距离序叠加 | 1次（2%）|
| type+dir8 | type×dir8双属性 | 1次（2%）|
| type+status | type×status | 1次（2%）|

---

## 二、架构决策：如何自动选择约束方法

### 2.1 整体流程（CumulativeConstraintChain）

```
candidates (N个对象)
    │
    ├─ 阶段1  1属性组合  [type, status, dir8, dist_ord] 各尝试
    │          ↓ 任何一个唯一 → 直接返回
    ├─ 阶段2a 纯二跳 referent  (全集sibling_cnt==1)
    │          ↓ 找到 → 直接返回
    ├─ 阶段2b 属性缩小+二跳   (属性缩小后sibling∩narrowed唯一)
    │          ↓ 找到 → 直接返回
    ├─ 阶段3  2属性组合  [所有2-attr组合]
    │          ↓ 任何唯一 → 直接返回
    ├─ 阶段4  3-4属性组合
    │          ↓ 任何唯一 → 直接返回
    ├─ 阶段5  dual_hop_referent  (两referent交集)
    │          ↓ 找到 → 直接返回
    ├─ 阶段6  anchor_intro  (src唯一性引入)
    │          ↓ 找到 → 直接返回
    └─ 阶段7  yesno_fallback  (存在性，is_unique=False)
```

### 2.2 "第一成功即止"策略的合理性

**为什么不用全局最优搜索？**

- 候选集 N 通常 5~40，Python 过滤每次 < 0.1ms，穷举所有方法总耗时 < 5ms
- 目标是"最简自然问题"，而非"信息量最大问题"
- 早返回 = 问题更简单 = VLM 更容易回答

**为什么 two_hop 排在 3-attr 组合前面？**

实测数据验证：two_hop 命中率 44%，而 3-attr 组合命中率 < 5%；且 two_hop 生成的问题（"car to the right of bicycle1"）比三属性问题（"far stopped car at front-left"）更自然、VLM 可解释性更强。

### 2.3 "联合约束"是否应引入？

**已引入的联合约束**：
- 属性+属性：阶段1的2-attr, 3-attr, 4-attr组合
- 属性+二跳：阶段2b（attr_then_twohop）
- 双二跳交集：阶段5 dual_hop

**暂未引入但可扩展的**：
- dist_ord + two_hop："到 car9 右边最近的 car"
- anchor_intro + 属性：先描述src，再加属性过滤tgt

这些可作为阶段6-7的扩展，优先级低，仅在前述全部失效时尝试。

### 2.4 性能瓶颈分析

从L2 50cells实测数据：
```
Step 5a  LLM     20s mean  ← 99% 时间
Step 5c  Neo4j  49ms mean  ← 第二耗时（候选集+referents）
Step 5d  Python 18ms mean  ← 约束链本身几乎不是瓶颈
```

**Neo4j优化建议**（Step 5c 49ms可降至 <10ms）：
```cypher
-- 当前没有的但应该创建的索引：
CREATE INDEX ON :Object(unique_id);      -- 节点ID查找
CREATE INDEX ON :RELATES_TO(direction_4); -- 方向过滤
CREATE INDEX ON :Object(type);           -- 类型过滤
```

---

## 三、候选集规模解答："为什么不是阶乘级别？"

### 3.1 根本原因

候选集不是"所有对象的排列组合"，而是**"src在特定方向上的直接可见对象"**。

```
step 5c 的 Cypher：
MATCH (src:Object {unique_id: $src_id})-[r:RELATES_TO]->(tgt:Object)
WHERE r.direction_4 = $dir4
```

含义：src → 某方向 → 有直接边的所有对象。
这不是组合，是**图中src的出度子集**，规模由场景密度决定（通常5~40个）。

### 3.2 三个样本的漏斗图（实测数据）

**样本1：car1 → car28（front方向，本文主要案例）**

```
全图节点总数                        64
└─ RELATES_TO 可见对象（全方向）    63（除自身）
   └─ front 方向的对象             37  ← Step 5c 候选集
      └─ type=car                  14
         └─ type=car, status=stopped   11
            └─ type=car,s=stopped,dir8=front  7
               └─ dual_hop交集        1  ✓
```

**样本2：car1 → pedestrian21（front-right方向）**

```
全图节点                            64
└─ RELATES_TO 可见对象              63
   └─ front 方向的对象             37
      └─ 直接精确到 status=sitting   1  ✓ (P2 status_anchor 一步命中)
```

**样本3：car1 → car7（front方向）**

```
全图节点                            64
└─ RELATES_TO 可见对象              63
   └─ front 方向的对象             37
      └─ two_hop: car6→front: sibling_cnt=1  1  ✓
```

### 3.3 为什么不是阶乘

| 误解 | 实际 |
|------|------|
| 需要枚举所有对象的排列组合 | 只关注"src能看见的对象" |
| 任意两个对象都是候选 | 有向图 RELATES_TO 是有限的，约 50-70 个出边/节点 |
| 候选集应该是 C(63,k) | 候选集 = src 在 dir4 方向的出邻域，通常 5-40 |
| 组合爆炸 | 图结构已经编码了空间过滤，Neo4j 直接返回结果 |

**结论：候选集小是设计正确的表现，不是bug。** 场景图中每个对象只与空间相邻的对象有边，天然限制了候选规模。

---

## 四、复杂案例逐行解析：cell 13（car1 → car28）

### 4.1 场景局部结构（ASCII 子图）

```
                  ego
                 /    \
           (front-right) (front)
               /              \
            car1             [众多front方向对象]
              |
         [front方向37个邻居，含car28]

car1 front方向邻居（部分）：
  car28(stopped,26m) car5(stopped,25m) car11(stopped,26m)   ← 距离、状态相近！
  car31(stopped,26m) car35(stopped,25m) pedestrian们...
  
pedestrian20 的back-right方向：{car28, ...5个}
car34        的back方向：{car28, ...5个}
pedestrian20·back-right ∩ car34·back = {car28}  ← dual_hop唯一
```

### 4.2 Step 5a — LLM 生成上下文 Cypher（22s）

```cypher
-- LLM 生成（与硬编码完全一致，字段名正确）
MATCH (src:Object {unique_id: 'car1'})-[e:RELATES_TO]->(tgt:Object {unique_id: 'car28'})
OPTIONAL MATCH (anc:Object)-[:RELATES_TO]->(src)
  WHERE anc.unique_id <> tgt.unique_id
WITH src, tgt, e, collect(anc)[0] AS anc
OPTIONAL MATCH (tgt)-[r2:RELATES_TO]->(beyond:Object)
  WHERE beyond.unique_id <> src.unique_id
    AND r2.direction_8 = e.direction_8   -- ← LLM 加的同方向过滤
WITH src, tgt, e, anc, collect(beyond)[0] AS beyond
OPTIONAL MATCH (:Object {unique_id: 'ego'})-[ego_r:RELATES_TO]->(tgt)  -- ← L2A 链路用
RETURN ... e.direction_4 AS dir4, e.direction_8 AS dir8,
       coalesce(e.predicates[1],'') AS dist_level, e.distance AS actual_dist,
       coalesce(ego_r.direction_8,'') AS ego_dir8,
       anc.unique_id AS anc_id, beyond.unique_id AS beyond_id ...
LIMIT 1
```

**L2A 链路体现**：`ego_r` 关系捕获了 `ego → car28` 的 `ego_dir8=front-right`，
这使得后续可以说"ego front-right方向的那辆car28"。
`anc = ego` 确认了三跳链 `ego → car1 → car28`。

### 4.3 Step 5b — ctx 返回

```
src = car1   (car / stopped)
tgt = car28  (car / stopped)        ← 同type同status！高难度
dir4 = front   dir8 = front         ← 方向也相同
dist_level = far   actual_dist = 26.48m
ego_dir8 = front-right              ← ego对car28的方向
anc  = ego (ego)                    ← L2A: ego → car1 → car28
beyond = car34 (car)               ← L2B: car28 → car34
```

**难度根源**：car28是一辆stopped的car，在car1正前方，和其他6辆stopped car几乎没有属性差异。

### 4.4 Step 5c — 候选集（37个对象的漏斗）

```
car1 前方（dir4=front）共 37 个候选对象：
  car35/car31/car28/car5/car11... (多辆stopped car)
  pedestrian们... (多个moving pedestrian)
  ego, motorcycle1, ...

目标 car28 隐藏在这 37 个里！
```

### 4.5 Step 5c2 — referents（指向car28的节点）

```
referent  →  指向car28的方向    sibling_cnt（该方向同类对象数）
pedestrian20  back-right          5    ← 5辆car在pedestrian20后右
car8          back-right          5
car34         back                5    ← 5辆car在car34后方
...所有referent的sibling_cnt >= 5，单二跳全部失败
```

**关键观察**：每个referent的back方向里都有5+辆car，没有一个能单独唯一定位car28。
必须用两个referent的交集。

### 4.6 Step 5d — 约束链完整尝试过程

```
可用属性: {type: car, status: stopped, dir8: front}

1. 试 type          37→14  ✗  前方有14辆car
2. 试 status        37→11  ✗  前方有11辆stopped对象（含car+其他）
3. 试 dir8          37→23  ✗  front方向有23个对象（dir4=front包含多sub-dir）
                              注：dir8=front是dir4=front的子集，但仍很多
4. 试 type+status   37→11  ✗  stopped car有11辆
5. 试 type+dir8     37→8   ✗  front方向的car有8辆
6. 试 status+dir8   37→7   ✗  front方向stopped有7辆
7. 试 two_hop        ✗  所有referent sibling_cnt>1，单跳无法唯一
8. 试 type+status+dir8  37→7  ✗  三属性联合仍有7辆（car28距离与其他近似）
9. 试 dual_hop ref1=pedestrian20 ref2=car34  ✅ 唯一！

pedestrian20·back-right的car集合 = {car28, car20, car26, car11, car5}
car34·back的car集合             = {car28, car11, car5, ...}
交集 = {car28}  唯一！
```

**约束深度**：8次失败 + 1次成功 = 9层，是本次50cells中的最高复杂度案例。

### 4.7 Step 5d.5 — 验证 Cypher（Python生成）

```cypher
-- Step 5d.5 验证 Cypher (双二跳交集，Python 生成，非LLM)
MATCH (ref1:Object {unique_id: 'pedestrian20'})-[r1:RELATES_TO]->(tgt:Object)
WHERE r1.direction_8 = 'back-right' AND tgt.type = 'car'
WITH collect(tgt.unique_id) AS ids1
MATCH (ref2:Object {unique_id: 'car34'})-[r2:RELATES_TO]->(tgt2:Object)
WHERE r2.direction_8 = 'back' AND tgt2.type = 'car'
WITH ids1, collect(tgt2.unique_id) AS ids2
WITH [x IN ids1 WHERE x IN ids2] AS intersection
RETURN size(intersection) AS n, intersection AS ids
-- 结果: n=1, ids=['car28'] ✅
```

### 4.8 最终 QA 质量评估（修复前→后）

**修复前（有冗余）**：
> Q: What car is both to the back-right of **pedestrian pedestrian20** and to the back of **car car34**?

**修复后（_ref_label修复）**：
> Q: What car is both to the back-right of **pedestrian20** and to the back of **car34**?
> A: car28   is_unique=True   difficulty=hard

**可理解性评分**：
- 逻辑严密性 4/5：双空间约束逻辑清晰，可验证
- 语言流畅性 4/5：结构稍复杂，但语法正确
- 视觉可答性 3/5：需要识别pedestrian20和car34的位置，对VLM有一定挑战

---

## 五、难度提升方案：高阶题型设计

### 5.1 现有问题的局限性

| 问题类型 | 占比 | 思维深度 | 局限 |
|---------|------|---------|------|
| 简单存在/位置 | ~30% | 1跳 | 太简单 |
| 单referent定位 | ~44% | 2跳 | NuScenes-QA标准水平 |
| 双referent定位 | ~18% | 3跳 | 较好 |
| 属性组合 | ~8%  | 1跳+属性 | 较简单 |

### 5.2 三类高难度题型

#### Type A — 多跳链式关系（Multi-hop Chain）
```
设计思路：问题涉及 ≥3 个节点的顺序链
实现：在已有 L2A(ego→src→tgt) 基础上扩展问题格式

示例：
  gap: car1 → car28
  anc: ego → car1
  beyond: car28 → car34
  
  L2A问题："在 ego front-right 方向的那辆 stopped car(car1) 的前方，
            有一辆 stopped car，它前方又是什么类型的车？"
  答案：car34(car)

实现位置：在 ctx 返回 anc_id 和 beyond_id 时，可以生成链式问题
条件：anc_id != None AND beyond_id != None
模板：
  "What {beyond_type} is to the {beyond_dir8} of the car that is 
   to the {dir8} of the {src_type} to the {ego_dir8} of ego?"
```

#### Type B — 比较与计数（Comparison & Count）
```
设计思路：跨方向的数量/状态对比
需要：对多个方向的候选集同时查询

示例：
  "Are there more stopped cars to the front of car1 than moving pedestrians?"
  "Which direction from car1 has the highest density of objects?"
  
实现：
  - 前者：count(stopped car, front) vs count(moving pedestrian, front)
  - 需要对 candidates 按状态分组统计
  - 返回 comparison result (Yes/No/equal)
```

#### Type C — 否定与不存在（Negation & Absence）
```
设计思路：询问某类对象在某方向"不存在"
需要：检查某类型在某方向的候选集为空

示例：
  "Is there any truck to the left of car1?" → No（如果left方向无truck）
  "Which object type is absent to the front-right of car1?"

实现：
  对候选集检查某 type 的 count == 0
  这类题的答案是"No"或具体absent类型
```

### 5.3 实现优先级

| 优先级 | 类型 | 实现难度 | 预计新增题目比例 |
|--------|------|---------|----------------|
| ★★★ | 多跳链式（L2A+L2B扩展）| 中（利用已有anc/beyond）| +15% |
| ★★★ | 否定/不存在 | 中（candidates为空检测）| +10% |
| ★★ | 计数比较 | 高（需跨方向聚合）| +8% |

---

## 六、RQ1 实验数据统计标准（Analysis Template）

### 6.1 设计逻辑

RQ1 核心问题：**Gap-Coverage Pipeline 生成的 QA 在正确率、覆盖效率上是否优于 baseline？**

统计维度：
1. **生成侧**（pipeline内部）：每道题的生成过程
2. **质量侧**（人工/LLM打分）：每道题的语言和逻辑质量
3. **评测侧**（VLM作答）：模型能否答对（预留，RQ1阶段填充）

### 6.2 字段定义

#### 基础信息
| 字段 | 类型 | 说明 |
|------|------|------|
| run_id | str | 运行批次ID（如 20260401_143000）|
| scene_id | str | 场景名（如 scene-0553）|
| frame_idx | int | 帧号（如 8）|
| gap_cell_id | str | src→tgt（如 car1→car28）|
| timestamp | datetime | 生成时间 |
| question_id | str | UUID前8位 |

#### 生成链条
| 字段 | 类型 | 说明 |
|------|------|------|
| llm_cypher_raw | text | LLM生成的原始Cypher文本 |
| llm_cypher_ok | bool | Cypher是否通过语法验证 |
| ctx_src | str | src的 type/status |
| ctx_tgt | str | tgt的 type/status/dir4/dir8 |
| ctx_anc | str | anc_id(L2A链路)，可为空 |
| ctx_beyond | str | beyond_id(L2B链路)，可为空 |
| n_candidates | int | Step 5c候选集大小 |
| n_referents | int | Step 5c2 referent数量 |
| constraint_path | str | 约束链路径，如 `type→status→dir8→two_hop` |
| method_used | str | 最终命中方法名 |
| is_unique | bool | 是否唯一锁定 |

#### 效能指标
| 字段 | 类型 | 说明 |
|------|------|------|
| total_latency_ms | float | 总耗时 |
| llm_time_ms | float | Step 5a LLM耗时 |
| neo4j_ctx_ms | float | Step 5b Neo4j耗时 |
| neo4j_cand_ms | float | Step 5c候选集+referents耗时 |
| tighten_ms | float | Step 5d约束链耗时 |
| verify_ms | float | Step 5d.5验证耗时 |
| llm_used | bool | 是否实际调用LLM（vs hardcoded fallback）|
| n_failed_attempts | int | 约束链失败次数 |

#### 最终 QA
| 字段 | 类型 | 说明 |
|------|------|------|
| question | text | 问题文本 |
| answer | str | 答案（object ID）|
| question_type | enum | constraint_chain/template/existence |
| difficulty | enum | easy/medium/hard |
| verify_n | int | 验证查询返回n（应=1）|
| verify_ids | str | 验证返回的ID列表 |
| verify_confirmed | bool | 验证是否通过 |

#### 质量评分（预留人工/LLM打分列）
| 字段 | 类型 | 说明 |
|------|------|------|
| logical_soundness | int(1-5) | 逻辑是否严密（1=有逻辑错误，5=严密无误）|
| linguistic_fluency | int(1-5) | 语言是否通顺（1=语法错误，5=流畅自然）|
| visual_answerability | int(1-5) | VLM能否从图里验证（1=无法验证，5=可直接确认）|
| uniqueness_human | bool | 人工确认是否真正唯一 |

#### 错误分类
| 字段 | 类型 | 可选值 | 说明 |
|------|------|-------|------|
| error_type | enum | OK/CypherError/LockFailed/Timeout/SemanticRedundant/SpatialConflict/VerifyFailed | 错误类型 |
| error_detail | text | 具体错误信息 | 仅非OK时填写 |

**错误分类定义**：
- `OK`：正常生成，验证通过
- `CypherError`：LLM生成的Cypher语法错误，走fallback
- `LockFailed`：所有约束方法失败，退化为yesno_fallback
- `Timeout`：LLM API超时
- `SemanticRedundant`：问题文本有冗余（如"car car6"，已通过代码修复）
- `SpatialConflict`：验证结果n≠1（数学上唯一，但库里数据不一致）
- `VerifyFailed`：Step 5d.5验证查询返回n>1

### 6.3 RQ1 实验参数设置（待确认后执行）

| 参数 | 建议值 | 理由 |
|------|--------|------|
| 场景数 | 3-5个scene | 覆盖不同密度场景 |
| 每场景gap cells | 50-100 | 足够统计显著性 |
| 固定时间预算 | 30分钟/场景 | 对比不同配置的效率 |
| 对比基线 | 纯template（无约束链）| 体现约束链的增益 |
| 覆盖率步长 | 每10个cell记录一次 | 观察增长曲线 |
| 正确率定义 | VLM在标注图上答对率 | 需要人工标注或GPT-4V评测 |

### 6.4 预期统计指标

```
每次RQ1运行输出：
  coverage_curve: [(n_cells, coverage_rate), ...]   覆盖率增长曲线
  method_dist: {method: count}                      约束方法分布
  unique_rate: unique/total                          唯一锁定率
  error_breakdown: {error_type: count}               错误分类
  avg_latency: {step: mean_ms}                       各步骤耗时
  difficulty_dist: {easy/medium/hard: count}         难度分布
  
对比指标（constraint_chain vs baseline_template）：
  Δcoverage = coverage(chain) - coverage(template)
  Δquality  = quality_score(chain) - quality_score(template)
```

---

*文档版本 v4.0，2026-04-01，Oz Agent 生成。*
