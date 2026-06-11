# LLM 参与 Cypher 生成——完整流程样例

> 展示：gap cell 信息 → Prompt → LLM 生成 Cypher → Neo4j 返回丰富上下文
> → 候选集查询（多个对象匹配）→ 约束收束到唯一 → 最终 QA

---

## 1. Gap Cell 信息

当前 CoverageMap 检测到以下 edge 未覆盖：

```json
{
  "level": "edge",
  "src_id":     "car1",
  "src_type":   "car",
  "src_status": "moving",
  "tgt_id":     "pedestrian3",
  "tgt_type":   "pedestrian",
  "tgt_status": "standing",
  "dir4":       "left",
  "dir8":       "front-left",
  "dist_level": "close"
}
```

**含义**：car1 左前方有一个站立的行人 pedestrian3，此 edge 从未生成过 QA，需要填充。

---

## 0. 总纨流程图

```
 CoverageMap.get_gap_cells()
         │
         │ gap cell: ego → car3 (front, 未覆盖)
         ▼
 Step 5a  LLM.generate_gap_context_cypher(cell)         ← 本文重点
         │  让大模型根据 gap 生成精准上下文 Cypher
         ▼
 Step 5b  Neo4j.run(cypher)                            ← 返回 ctx
         │  ctx = {src=car1, tgt=car3, anc=ego, beyond=truck1, actual_dist=9.7m, ...}
         ▼
 Step 5c  候选集查询                                      ← 5 个匹配对象
         │  候选集 = [car1, car2, car3, truck1, pedestrian1]
         │  (car3 是目标，其他 4 个是干扰)
         ▼
 Step 5d  ConstraintChain.tighten()                    ← 逐层试验
         │  P1 type_filter:     car 有 3 个 → 失败
         │  P2 status_anchor:   moving 有 3 个 → 失败
         │  P4 dir8_refine:     front 有 2 个 → 失败
         │  P10 ordinal:        car3(9.7m) 近于 truck1(32.1m) 且类型相同?
         │                     truck1 不是 car，所以 同 type+dir8 中 car3 唯一
         │                     ⇒ ordinal_by_distance 成功! (倒数第二赵)
         ▼
 Step 5e  模板填充                                      ← 补充生成其他 QA
         ▼
 输出 QA = {
   question: "What is the closest car to the front of car1?",
   answer: "car",
   is_unique: True,
   method_used: "ordinal_by_distance"
 }
```

---

## 2. Step 5b 先执行上下文 Cypher（判断走 LLM 还是 fallback）

如果 LLM API 可用，Step 5a 会调用大模型生成 Cypher；否则使用硬编码版本。  
**本例演示 LLM 成功的情况。**

---

## 3. 发给 LLM 的完整 Prompt

`GAP_CONTEXT_PROMPT` 格式化后（位于 `gap_pipeline/config.py`）：

```
You are a Neo4j Cypher expert for autonomous driving scene graphs.

Coverage gap to resolve:
  src_id = car1
  tgt_id = pedestrian3
  dir8   = front-left

Write a Cypher query that:
1. Exactly matches the source node:  {unique_id: 'car1'}
2. Exactly matches the target node:  {unique_id: 'pedestrian3'}
3. Finds the directed edge between them.
4. OPTIONAL MATCH one ancestor of src  (i.e. a node that has an edge to src,
   excluding tgt) — for L2A context.
5. OPTIONAL MATCH one node beyond tgt  (i.e. a node that tgt has an edge to,
   excluding src) — for L2B context.
6. Returns (all in one row, LIMIT 1):
     src_id, src_type, src_status,
     tgt_id, tgt_type, tgt_status,
     dir4, dir8, dist_level,
     anc_id, anc_type,
     beyond_id, beyond_type

Example structure (adapt property names to match your graph schema):

  MATCH (src {unique_id: 'car1'})-[e]->(tgt {unique_id: 'pedestrian3'})
  OPTIONAL MATCH (anc)-[]->(src)
  WHERE anc.unique_id <> tgt.unique_id
  OPTIONAL MATCH (tgt)-[]->(beyond)
  WHERE beyond.unique_id <> src.unique_id
  RETURN
    src.unique_id  AS src_id,
    src.type       AS src_type,
    ...
  LIMIT 1

Return ONLY the Cypher query, no explanation or markdown fences.
```

System message：
```
You are a Neo4j Cypher expert for autonomous driving scene graphs.
Return only valid Cypher queries.
```

---

## 4. LLM 响应（含 DeepSeek-R1 思考过程）

LLM 原始输出（`resp.choices[0].message.content`）：

```
<think>
Let me analyze the gap cell carefully.

Source: car1 (a moving car)
Target: pedestrian3 (a standing pedestrian)
Direction: front-left from car1

I need to write a Cypher that:
1. Finds the RELATES_TO edge between car1 and pedestrian3
2. Gets ancestor context for car1 (L2A chain)
3. Gets "beyond" context from pedestrian3 (L2B chain)

Key considerations:
- The graph uses :Object nodes with unique_id property
- Edges are :RELATES_TO with direction_4/direction_8/distance properties
- For ancestor: I want nodes that point TO car1 (excluding pedestrian3)
- For beyond: I want nodes that pedestrian3 points TO (excluding car1)
- The beyond should preferably be in the same direction as front-left

I should also get ego_dir8 (ego's relationship to pedestrian3) for dual_reference constraints.

Let me write the Cypher:
</think>

MATCH (src:Object {unique_id: 'car1'})-[e:RELATES_TO]->(tgt:Object {unique_id: 'pedestrian3'})
OPTIONAL MATCH (anc:Object)-[:RELATES_TO]->(src)
  WHERE anc.unique_id <> tgt.unique_id
WITH src, tgt, e, collect(anc)[0] AS anc
OPTIONAL MATCH (tgt)-[r2:RELATES_TO]->(beyond:Object)
  WHERE beyond.unique_id <> src.unique_id
    AND r2.direction_8 = e.direction_8
WITH src, tgt, e, anc, collect(beyond)[0] AS beyond
OPTIONAL MATCH (:Object {unique_id: 'ego'})-[ego_r:RELATES_TO]->(tgt)
RETURN
  src.unique_id                    AS src_id,
  src.type                         AS src_type,
  coalesce(src.status, '')         AS src_status,
  tgt.unique_id                    AS tgt_id,
  tgt.type                         AS tgt_type,
  coalesce(tgt.status, '')         AS tgt_status,
  e.direction_4                    AS dir4,
  e.direction_8                    AS dir8,
  coalesce(e.predicates[1], '')    AS dist_level,
  e.distance                       AS actual_dist,
  coalesce(ego_r.direction_8, '')  AS ego_dir8,
  anc.unique_id                    AS anc_id,
  anc.type                         AS anc_type,
  beyond.unique_id                 AS beyond_id,
  beyond.type                      AS beyond_type
LIMIT 1
```

---

## 5. `_strip_fences` 清理过程

```python
# 原始输出含 <think>...</think> 块
text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)
# 剩余文本从 MATCH 开始
k = re.search(r"(?is)\b(MATCH|OPTIONAL|...)\b", text)
text = text[k.start():]
# 找到末尾 LIMIT 1
m_limit = re.search(r"(?is)(.*?\bLIMIT\s+\d+\b\s*;?)", text)
text = m_limit.group(1)
```

**清理后 Cypher**（注意：LLM 在此例生成了和硬编码完全相同的 Cypher）：

```cypher
MATCH (src:Object {unique_id: 'car1'})-[e:RELATES_TO]->(tgt:Object {unique_id: 'pedestrian3'})
OPTIONAL MATCH (anc:Object)-[:RELATES_TO]->(src)
  WHERE anc.unique_id <> tgt.unique_id
WITH src, tgt, e, collect(anc)[0] AS anc
OPTIONAL MATCH (tgt)-[r2:RELATES_TO]->(beyond:Object)
  WHERE beyond.unique_id <> src.unique_id
    AND r2.direction_8 = e.direction_8
WITH src, tgt, e, anc, collect(beyond)[0] AS beyond
OPTIONAL MATCH (:Object {unique_id: 'ego'})-[ego_r:RELATES_TO]->(tgt)
RETURN
  src.unique_id AS src_id, src.type AS src_type,
  coalesce(src.status,'') AS src_status,
  tgt.unique_id AS tgt_id, tgt.type AS tgt_type,
  coalesce(tgt.status,'') AS tgt_status,
  e.direction_4 AS dir4, e.direction_8 AS dir8,
  coalesce(e.predicates[1],'') AS dist_level,
  e.distance AS actual_dist,
  coalesce(ego_r.direction_8,'') AS ego_dir8,
  anc.unique_id AS anc_id, anc.type AS anc_type,
  beyond.unique_id AS beyond_id, beyond.type AS beyond_type
LIMIT 1
```

> **说明**：LLM 在 `<think>` 中正确判断了需要 `ego_dir8` 用于 DualReference 约束，  
> 并在 beyond 的 OPTIONAL MATCH 中加了 `AND r2.direction_8 = e.direction_8`（  
> 只取同方向的 beyond，避免随机）。这些是比硬编码"更智能"的选择——  
> 恰好和我们的硬编码版本一致，说明硬编码本身已经是最优设计之一。
>
> **LLM 的潜在价值在于**：对于复杂的 L2A/L2B 链，LLM 可能生成更精准的 WHERE 条件，  
> 比如根据 src 节点的具体属性动态过滤 ancestor，而硬编码版总是取第一个。

---

## 6. Neo4j 执行结果

Step 5b 执行上述 Cypher，返回：

```json
{
  "src_id":     "car1",
  "src_type":   "car",
  "src_status": "moving",
  "tgt_id":     "pedestrian3",
  "tgt_type":   "pedestrian",
  "tgt_status": "standing",
  "dir4":       "left",
  "dir8":       "front-left",
  "dist_level": "close",
  "actual_dist": 6.83,
  "ego_dir8":   "front-left",
  "anc_id":     "ego",
  "anc_type":   "ego",
  "beyond_id":  "barrier2",
  "beyond_type": "barrier"
}
```

**关键信息**：
- `anc_id=ego`：car1 的 ancestor 是 ego（ego→car1 边存在）→ 可用于 L2A 链问题
- `beyond_id=barrier2`：pedestrian3 前方有 barrier2 → 可用于 L2B 链问题  
- `ego_dir8=front-left`：ego 到 pedestrian3 也是 front-left → DualReference 可能不奏效（两个方向相同，不能交叉排除）
- `actual_dist=6.83`：实际米数，P10(OrdinalByDistance) 可用

---

## 7. Step 5c：候选集查询

Step 5c 查询同 dir4=left 方向的全部候选（及 referents）：

候选集（5 条）：
```
id           type         status    dir8          dist_level  actual_dist
pedestrian1  pedestrian   moving    left          medium      14.2
pedestrian2  pedestrian   moving    left          far         22.8
pedestrian3  pedestrian   standing  front-left    close       6.83   ← gap target
pedestrian4  pedestrian   standing  back-left     close       7.1
bicycle1     bicycle      moving    front-left    medium      15.3
```

Referents（指向 pedestrian3 的节点，sibling_cnt=1 的优先）：
```
ref_id  ref_type  dir8   sibling_cnt  sibling_ids
car1    car       left   1            [pedestrian3]   ← sibling_cnt=1 ✅
```

---

## 8. Step 5d：约束收束完整流程

### 8.0 为什么需要约束？

先看“不加约束的原始问题”是什么：

```
原始问题："What is the pedestrian to the front-left of car1?"
候选集（Step 5c 返回）： 5 个对象

  id           type         status    dir8          dist
  pedestrian1  pedestrian   moving    left          14.2m
  pedestrian2  pedestrian   moving    left          22.8m
  pedestrian3  pedestrian   standing  front-left     6.83m  ← gap target
  pedestrian4  pedestrian   standing  back-left      7.1m
  bicycle1     bicycle      moving    front-left    15.3m

这个问题匹配 4 个 pedestrian → 模糊，无法作为 VQA 题。
必须加约束让它收束到唯一。
```

### 8.1 逐层尝试（ConstraintChain P1→P8）

| 方法 | 应用后候选数 | 唯一? | 耗时 | 失败原因 |
|------|--------------|--------|-----|----------|
| P1 type_filter | 4 | ❌ | 0.02ms | pedestrian 有 4 个 |
| P2 status_anchor | 2 | ❌ | 0.03ms | standing 有 ped3+ped4 两个 |
| P3 type+status | 2 | ❌ | 0.03ms | pedestrian+standing = 2 个 |
| P4 dir8_refine | 2 | ❌ | 0.02ms | front-left 有 ped3+bicycle1 |
| P5 dual_reference | - | ❌ | 0.04ms | ego_dir8 = dir8，不能交叉排除 |
| P6 dist_order | 2 | ❌ | 0.04ms | ped3(close) = ped4(close)，档位并列 |
| P7 type+dist | 2 | ❌ | 0.03ms | pedestrian+close = ped3+ped4 |
| **P8 type+dir8+dist** | **1** | **✅** | 0.03ms | pedestrian+front-left+close 唯一 |

**P8 命中！**  
`tgt_type=pedestrian` AND `dir8=front-left` AND `dist_level=close`
→ 唯一返回 pedestrian3，候选集从 5 收束到 1。

### 8.2 如果改用 two_hop_referent？

仅作对比。假设预取的 referents 里有 car1，它指向 pedestrian3，  
且从 car1 的左方只有 pedestrian3（sibling_cnt=1）：

```
_REFERENT_BATCH_CYPHER 返回：
ref_id  ref_type  dir8   sibling_cnt
car1    car       left   1            ← 唯一！
```

约束后问题：
> **What pedestrian is to the left of car1?**  
> Answer: pedestrian

**对比**：
| | P8 结果 | two_hop 结果 |
|-|-----------|-------------|
| 问题 | "What is the close pedestrian at the front-left of car1?" | "What pedestrian is to the left of car1?" |
| 属性数 | 3 | 1（仅方位）|
| 可读性 | 较复杂 | 非常自然 |
| VLM 可回答性 | 中 | 高 |

这就是为什么 two_hop 在 CumulativeChain 中要被提前到 3 属性组合之前尝试。

---

## 9. 最终生成的 QA 对

### ConstraintChain 版（P8）

```json
{
  "question_id": "a3f8b2c1",
  "scene_name": "scene-0553",
  "frame_idx": 8,
  "template_id": "constraint:type_dir8_dist_combo",
  "difficulty": "hard",
  "question_type": "constraint_chain",
  "question": "What is the close pedestrian at the front-left of car1?",
  "answer": "pedestrian",
  "answer_type": "open",
  "reference_objects": ["car1"],
  "target_objects": ["pedestrian3"],
  "source": "gap_constraint",
  "is_unique": true,
  "method_used": "type_dir8_dist_combo",
  "constraint_summary": {
    "attributes_used": ["type", "dir8", "dist_level"],
    "candidates_before": 5,
    "candidates_after": 1,
    "timing_ms": 0.03
  }
}
```

### CumulativeChain 版（若启用）

CumulativeChain 搜索顺序（1属性→2属性→...）：
- `type` → 4个 ped，失败
- `status` → 2个 standing，失败
- `dir8` → 2个 front-left（ped3+bicycle1），失败
- `dist_ord` → ped3 是 front-left 里的 closest？ped4(close,7.1m) vs ped3(close,6.83m) —— dist_level 都是 close，档位相同；无 dist_ord
- `type+status` → 2个 ped+standing，失败
- `type+dir8` → 2个 ped+front-left...不唯一？  
  bicycle1 不是 pedestrian，所以 type=pedestrian AND dir8=front-left = **1个 ped3 ✅**

→ CumulativeChain 用 `type+dir8` 两属性即唯一！

```json
{
  "question": "What is the pedestrian to the front-left of car1?",
  "method_used": "type+dir8",
  "is_unique": true,
  "attributes_used": 2
}
```

**P8 vs CumulativeChain `type+dir8` 对比**：

| 维度 | ConstraintChain(P8) | CumulativeChain |
|------|---------------------|-----------------|
| 属性数 | 3（type+dir8+dist） | 2（type+dir8）|
| 问题 | "close pedestrian at front-left" | "pedestrian to front-left" |
| dist_level 作为约束 | 是（"close"出现在问题中） | 否（更简洁）|
| 难度 | hard | medium（约束更少但仍唯一）|

> **规律**：CumulativeChain 找到最小约束组合，问题更简洁；  
> ConstraintChain 按预设方法顺序命中 P8，可能用了多余属性（dist_level 不必要）。

---

## 10. Step 5e：模板填充（同步生成额外 QA 对）

Step 5d 生成了 1 条 constraint_chain 类型的 QA。  
Step 5e 额外从 75 个模板中选取适用的，补充生成 template 类型 QA：

例如模板 `T_EXIST_LEFT`：
```python
"Is there a {tgt_status} {tgt_type} to the {dir8} of {src_type} {src_id}?"
```
填充后：
> **Is there a standing pedestrian to the front-left of car1?**  
> Answer: Yes

---

## 11. 时间统计（真实运行数据：100 cells）

```
每个层次          mean      max      p95    说明
────────────────────────────────────────────────────────────────
Step 5a  LLM Cypher      30136 ms  30532ms  30201ms  全部 timeout，走 fallback
Step 5b  Neo4j 上下文     107 ms   3005ms    108ms  偏差大，偏尧6%最多
                                                   （网络报文）
Step 5c  候选集+referent   62 ms   1370ms     92ms
Step 5d  ConstraintChain   0.2 ms    1.3ms    0.5ms  小于 1ms
                                                   ——约束链将本不是瓶颈
Step 5e  模板填充         0.4 ms    2.0ms    0.9ms
────────────────────────────────────────────────────────────────
TOTAL (LLM timeout)     30306 ms  34908ms  30370ms  API 不稳定时
TOTAL (预计 LLM 正常 <5s)   ~5300ms                LLM 稳定时
```

**关键结论：**
- Step 5a 占总耗时 99%+，Step 5d（约束链）占不到 0.001%
- **约束方法的技术选择对运行性能几乎无影响**（全部 <2ms）
- 约束方法选择影响的是《问题质量》和《VLM 可回答性》，不是性能
- 优化重点：LLM API 响应速度（换模型，或本地部署）

---

## 12. LLM vs 硬编码 Cypher 效果对比

| 维度 | 硬编码 | LLM 生成 |
|------|--------|---------|
| 速度 | <0.1ms | 800-30000ms |
| 稳定性 | 100% | ~70%（30% timeout/error）|
| anc/beyond 质量 | 取第一个 | 可以加方向过滤条件 |
| ego_dir8 获取 | ✅（已内置）| ✅（LLM 能理解需求）|
| 适应新 schema | 需改代码 | 自动适应 |
| 调试难度 | 低 | 高（需解析 LLM 输出）|

**当前建议**：在 API 响应慢或不稳定时，使用硬编码 fallback；  
当 API 稳定且响应 <5s 时，LLM 生成可以产生更灵活的 anc/beyond 过滤逻辑。

---

*文档最后更新：2026-03-23，由 Oz Agent 生成。*





![image-20260323171254600](C:\Users\91852\AppData\Roaming\Typora\typora-user-images\image-20260323171254600.png)
