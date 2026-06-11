# L2 Gap Question Generation Refactor Plan

目标：从图论定义重构 L2 `a|b|c` 问题生成，统一模板族、候选集、约束链、verify 和 coverage。

## 1. L2 底盘

```text
L2 gap = a|b|c
b = pivot
edge(a,b) exists, edge(b,c) exists
a/c 可交换，coverage key = min(a,c)|b|max(a,c)
```

真 L2 问题必须让回答过程使用两条空间关系边。只用一条边是 L1，只问节点属性是 L0。代码中可用有向边读取方向属性，但不能把 gap 语义改成 `a→b→c`。

## 2. 有效 L2 模板族

### 2.1 Converge 汇聚型：`a -> x <- c`

目标槽位是 pivot `x`，对应原 gap 的 `b`。

```text
What car is to the front of a and to the right of c?
What is the status of the car to the front of a and to the right of c?
Is there a car to the front of a and to the right of c?
How many cars are to the front of a and to the right of c?
```

真 L2；a/c 是 ID；x 可能不唯一，需约束链；count/exist 返回多个 x 时 coverage 为 `a|x_i|c`。

### 2.2 Diverge Compare 发散比较型：`x <- b -> y`

两侧对象都必须通过 pivot `b` 的空间关系描述，不能一侧直接给 ID。

```text
Do the car to the left of b and the truck in front of b have the same status?
```

真 L2；语义复杂，低占比；需要 A/C 两份候选集和双分支约束链。若 ego 做 a/c，不生成发散；ego 做 b 时可生成发散。

### 2.3 Distance Chain

```text
Is b closer to a or to c?
Is a closer to b than c is to b?
```

三个 ID 已知；比较两条边距离；真 L2；不需约束链。

### 2.4 Direction Chain

```text
Is c in the same direction from b as b is from a?
```

覆盖链式 `a-b-c`；使用 nuScenesQA 官方方位定义；不需约束链。

### 2.5 Viewpoint Transfer

```text
If you face from a toward b, is c on your left or on your right?
```

真 L2；需要局部几何计算；角度接近边界时判不可用。

### 2.6 暂不使用

```text
Path existence       -> 太简单
Between              -> 模糊抽象
三节点状态一致性     -> 更像 L0/L1
发散单侧             -> 退化 L1
发散 count/exist     -> coverage 边界未完全稳定，暂缓
```

## 3. 题型选择

不能先随机后验证。采用：`枚举题型 -> dry-run 可行性检查 -> 可行题型中加权选择`。

保守权重：`Converge 50%, Diverge 10%, Distance Chain 20%, Direction Chain 10%, Viewpoint Transfer 10%`。

不可行题型从本 gap 移除。最终分数：`base_weight * feasibility_score * diversity_factor`。

## 4. Candidate Set

Converge：

```text
candidates = nodes x such that edge(a,x) and edge(c,x)
base filter: x.type=b_type, dir(a->x)=dir(a->b), dir(c->x)=dir(c->b)
```

Diverge：

```text
A_candidates = nodes x such that edge(b,x), x.type=a_type, dir(b->x)=dir(b->a)
C_candidates = nodes y such that edge(b,y), y.type=c_type, dir(b->y)=dir(b->c)
```

两侧必须各自唯一。不能直接用 a_id/c_id 替代 branch 描述。Chain templates 使用固定 a/b/c ID，不需要 candidate set。

## 5. Constraint Planner

本质是 Referring Expression Generation。

输入：`target, candidate_set, available_refs, max_ref=2, allow_dist_rank=true`

输出示例：

```json
{"unique": true, "clauses": [{"kind":"ref_dir","ref_id":"ped3","dir":"front"}, {"kind":"dist_rank","rank":"nearest"}], "remaining_ids":["target"]}
```

约束层次：

```text
base: type + official direction + status(optional)
ref1: 最大淘汰 distractors 的参照对象
ref2: 仍不唯一时再选一个参照对象
dist_rank: nearest/farthest/2nd-nearest/2nd-farthest
limit: 最多 2 个 ref + 1 个 distance rank
```

参照评分：`gain(ref) = |C| - |candidates satisfying same relation to ref as target|`。第一版参照来源：当前候选集内部对象 + pivot 邻域对象；跨分支/全图对象后续实验。

## 6. Question Realizer

程序拼接，不让 LLM 润色。

Converge：

```text
What {type} is to the {dir_from_a} of {a_id} and to the {dir_from_c} of {c_id}{extra}?
What is the status of the {type} to the {dir_from_a} of {a_id} and to the {dir_from_c} of {c_id}{extra}?
How many {type_plural} are to the {dir_from_a} of {a_id} and to the {dir_from_c} of {c_id}{extra}?
```

Diverge：

```text
Do the {a_desc} and the {c_desc} have the same status?
a_desc = "{a_type} to the {dir_ba} of {b_id}" + branch constraints
c_desc = "{c_type} to the {dir_bc} of {b_id}" + branch constraints
```



## 7. Verify Cypher

verify 必须程序生成，不能由 LLM 自由生成。原则：与模板结构对应、与 constraint clauses 对应、返回 distinct ids、count/exist 返回结构槽位对象。

Converge verify：

```cypher
MATCH (a:Object {unique_id:$a_id})-[ra:RELATES_TO]-(x:Object)
MATCH (c:Object {unique_id:$c_id})-[rc:RELATES_TO]-(x)
WHERE x.type = $target_type
  AND ra.direction_official = $dir_from_a
  AND rc.direction_official = $dir_from_c
  /* constraint clauses */
RETURN count(DISTINCT x) AS n, collect(DISTINCT x.unique_id) AS ids
```

Diverge verify：两侧分别 verify，且两侧都唯一命中目标 a/c，才算有效。Chain verify：直接读取 `dist(a,b), dist(b,c)` 或 `dir(a,b), dir(b,c)`，再程序判断答案。

## 8. Coverage Footprint

coverage 从显式 `question_graph` 抽取，而不是从所有出现过的对象两两组合，也不是从全局 scene graph 补边。

统一规则：

```text
L0 = question_graph 中显式节点
L1 = question_graph 中显式空间关系边
L2 = question_graph 中所有长度为 2 的 simple paths: u - pivot - v
```

`dist_rank` 不新增节点/边，只作为唯一性限定；`ref_dir` 会新增一个显式空间边，因此可能新增 L1/L2 coverage。

Converge + ref 示例：

```text
question: x is to the front of a, to the right of c, and behind ref1
question_graph: a-x, c-x, ref1-x
L2: a|x|c, a|x|ref1, c|x|ref1
```

若加入 ref1/ref2，则 `ref1|x|ref2` 也计入 coverage，因为它是问题显式子图中的二跳路径。

Converge count/exist：若返回 `x1,x2`，分别为每个 `x_i` 构造同构 question_graph。例如有 ref1 时：

```text
L2: a|x_i|c, a|x_i|ref1, c|x_i|ref1
L1: a|x_i, c|x_i, ref1|x_i
L0: a,c,ref1,x_i
```

严禁扩展 `x1|a|x2` 或 `x1|c|x2`，因为这些不是问题显式子图中的二跳路径。

Diverge + branch ref 示例：

```text
question_graph: refA-a, a-b, b-c, c-refC
L2: refA|a|b, a|b|c, b|c|refC
```

不计 `refA|b|c` 或 `a|b|refC`，因为缺少对应显式边。

Chain templates：question_graph 为原始 `a-b-c`，覆盖 L2 `a|b|c`，L1 `a|b,b|c`，L0 `a,b,c`。

## 9. ego 槽位规则

```text
ego 做 b pivot：允许发散型，不生成汇聚型。
ego 做 a/c branch：允许汇聚型和 chain templates，不生成发散型。
```

## 10. LLM 使用边界

待与老师确认。建议折中：自由自然语言到 Cypher 保留 LLM；固定 L2 模板候选集查询优先程序生成；若保留 LLM 特色，必须 schema validate + fallback；verify Cypher 永远程序生成。

固定模板用 LLM 的风险：发散两分支被混成一个结果集、方向参考系反转、返回字段不稳定、候选集不可用于约束链。

## 11. 方位系统

全局采用 nuScenesQA 官方方位定义，不自行扩展。需要统一 scene graph edge、constraint planner、question text、verify Cypher、VLM instruction。Viewpoint Transfer 是局部视角几何问题，模板中必须明确 “If you face from a toward b”。

## 12. 实施阶段

Phase 0：冻结旧逻辑并补文档，标记 `_render_l2_question` deprecated。

Phase 1：新建核心模块：`l2_taxonomy.py`, `l2_candidate_builder.py`, `l2_constraint_planner.py`, `l2_question_realizer.py`, `l2_verifier.py`, `l2_coverage_mapper.py`。

Phase 2：实现不需约束链的题型：Distance Chain、Direction Chain、Viewpoint Transfer。

Phase 3：实现 Converge + constraint planner：含 unique/status/object/count/exist，coverage 按结构槽位扩展。

Phase 4：实现 Diverge Compare：双分支 candidate builder、双分支 constraint planner，低占比启用。

Phase 5：Feasibility-aware sampler：dry-run all template families → filter infeasible → score feasible templates → weighted sample。

Phase 6：回归测试：scene-0103 frame-3 dense pedestrian case、coverage correctness、wrong-target、non-unique、question length、template distribution。

## 13. 必须避免的旧问题

```text
1. 把 a|b|c 误写成 a→b→c。
2. 用单侧发散题冒充 L2。
3. 用 ID 直接给一侧 branch，导致发散退化。
4. candidates 全量入 coverage，造成虚高。
5. coverage 只记 target，造成少覆盖。
6. count/exist 按返回 ids 两两组合扩展 L2。
7. degree 约束用于完全图，语义无效。
8. LLM verify Cypher 导致方向和去重不稳定。
```

