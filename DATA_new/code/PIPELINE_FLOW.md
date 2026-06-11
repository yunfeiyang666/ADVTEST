# Gap到QA对的完整流程

## 概述

本文档记录从Gap选择到QA对生成并落盘的完整流程，包括每个步骤的输入输出、关键函数和性能优化点。

## 流程图

```
[1. 初始化] → [2. Gap选择] → [3. Context查询] → [4. 模板选择] 
    ↓
[5. 约束收束] → [6. 问题生成] → [7. Cypher转换] → [8. 验证与记录] → [9. 批量写入CSV]
```

## 详细步骤

### 1. 初始化 (Initialization)

**目标**: 初始化覆盖追踪器，建立拓扑宇宙

**关键函数**:
- `CoverageTracker.init_from_session(session)`

**操作**:
1. 从Neo4j查询所有节点、边、L2路径
2. 初始化三层覆盖记录：
   - L0: 所有节点 (hit_count=0)
   - L1: 所有边，使用规范化key (hit_count=0)
   - L2: 所有三跳路径，使用规范化key (hit_count=0)
3. 可选：加载baseline原题，标记已覆盖拓扑

**输出**:
- CoverageTracker实例，包含完整的拓扑宇宙
- 统计信息：L0总数、L1总数、L2总数

**性能**: ~1-3秒 (取决于图规模)

---

### 2. Gap选择 (Gap Selection)

**目标**: 使用优先级评分选择最有价值的未覆盖gaps

**关键函数**:
- `CoverageTracker.select_gaps_with_priority(topology, top_k, adaptive)`

**操作**:
1. 获取所有未覆盖的L2路径 (hit_count=0)
2. 对每个gap计算优先级评分：
   ```python
   priority = len(uncovered_l0) × 10 + len(uncovered_l1) × 15
   ```
   - uncovered_l0: 路径中未覆盖的节点数
   - uncovered_l1: 路径中未覆盖的边数
   - L1边权重更高(15 vs 10)，因为边比节点更稀缺
3. 排序并选择top_k个gap
4. 自适应策略：80%高优先级 + 20%随机（避免局部最优）

**输入**:
- topology: "L2"
- top_k: 需要的gap数量 (如50)
- adaptive: True

**输出**:
- List[(gap_key, gap_meta, priority_score)]
- 示例: `[("ego->car1->car2", {...}, 45.0), ...]`

**性能**: ~0.1-0.5秒

---

### 3. Context查询 (Context Query)

**目标**: 为每个gap查询Neo4j获取上下文信息

**关键函数**:
- `generate_context_cypher_batch()` (LLM批量生成)
- `_build_l2_fallback_cypher()` (硬编码fallback)

**操作**:
1. **批量Cypher生成** (BATCH_SIZE=12):
   - 将12个gap打包成一个prompt
   - LLM一次性生成12条Cypher查询
   - 单条失败降级到fallback
2. **执行Cypher查询**:
   ```cypher
   MATCH (ego:Object {unique_id:'ego'})-[r1:RELATES_TO]->(a:Object {unique_id:'car1'})
         -[r2:RELATES_TO]->(b:Object {unique_id:'car2'})
   OPTIONAL MATCH (a)-[r3:RELATES_TO]->(sibling:Object)
     WHERE sibling.unique_id <> 'ego' AND sibling.unique_id <> 'car2'
   RETURN ego, a, b, r1, r2, collect(sibling) as siblings
   ```
3. **解析返回结果**:
   - gap_target: 目标节点 (car2)
   - siblings: 中间节点的其他邻居 [car3, car4, car5]
   - referents: 目标节点的二跳邻居 (用于TwoHopReferent约束)
   - 空间关系: direction_4, direction_8, distance等

**输入**:
- gap_meta: {"n1_id": "ego", "n2_id": "car1", "n3_id": "car2", ...}

**输出**:
- ctx: {
    "gap_target": {...},
    "sibling_ids": ["car3", "car4", "car5"],
    "siblings": [{id, type, dir8, dist}, ...],
    "referents": [{id, type, ...}, ...],
    "r1_dir4": "front", "r2_dir8": "front_left", ...
  }

**性能**: 
- 单条串行: ~9-10秒
- 批量(12)并行(8): ~1-2秒/条

---

### 4. 模板选择 (Template Selection)

**目标**: 从模板库选择适用的模板

**关键函数**:
- `TemplateLibrary.get_applicable_templates(ctx, topology)`

**操作**:
1. 根据topology和ctx筛选模板
2. 检查模板的前置条件：
   - 是否有足够的siblings
   - 是否有referents
   - 空间关系是否满足要求
3. 返回可用模板列表

**输入**:
- ctx: 上下文信息
- topology: "L2"

**输出**:
- List[Template]
- 每个模板包含：
  - template_id: "L2:type_filter"
  - question_template: "What is the {type} to the {dir} of {anchor}?"
  - constraint_methods: [TypeFilter, DirectionFilter, ...]
  - answer_template: "{target_id}"

**性能**: ~0.001秒 (内存操作)

---

### 5. 约束收束 (Constraint Chain)

**目标**: 通过约束方法唯一化答案

**关键函数**:
- `ConstraintChain.tighten(candidates, gap_target, ctx)`

**操作**:
1. **构建候选集**:
   ```python
   candidates = [gap_target] + siblings
   # 示例: [car2(truck), car3(car), car4(car), car5(pedestrian)]
   ```
2. **逐步应用约束**:
   - **TypeFilter**: 过滤出type=truck的对象
     - 结果: [car2]
   - **DirectionFilter**: 过滤出direction=front的对象
     - 结果: [car2]
   - **TwoHopReferent**: 过滤出near building1的对象
     - 结果: [car2]
3. **检查唯一性**:
   ```python
   is_unique = (len(remaining) == 1 and remaining[0].id == gap_target.id)
   ```

**输入**:
- candidates: [gap_target] + siblings
- gap_target: car2
- ctx: 上下文信息

**输出**:
- TightenResult:
  - question: "What is the truck to the front of car1?"
  - answer: "car2"
  - is_unique: True
  - method_used: "TypeFilter"

**性能**: ~0.01秒 (内存操作)

---

### 6. 问题生成 (Question Generation)

**目标**: 渲染模板生成自然语言问题

**关键函数**:
- `Template.render(ctx, gap_target)`

**操作**:
1. 替换模板中的占位符：
   ```python
   question = "What is the {type} to the {dir} of {anchor}?"
   # 替换后:
   question = "What is the truck to the front of car1?"
   ```
2. 生成答案：
   ```python
   answer = gap_target.id  # "car2"
   ```

**输入**:
- template: 问题模板
- ctx: 上下文信息
- gap_target: 目标节点

**输出**:
- question: "What is the truck to the front of car1?"
- answer: "car2"

**性能**: ~0.001秒

---

### 7. Cypher转换 (Cypher Translation)

**目标**: 将自然语言问题转换为Cypher查询

**关键函数**:
- `LLMClient.generate_cypher_from_question(question)`

**操作**:
1. **LLM批量调用** (BATCH_SIZE=12):
   - 将12个问题打包成一个prompt
   - LLM一次性生成12条Cypher查询
2. **解析Cypher**:
   ```cypher
   MATCH (ego:Object {unique_id:'ego'})-[:RELATES_TO]->(a:Object)
         -[:RELATES_TO]->(b:Object {type:'truck'})
   WHERE a.unique_id = 'car1'
   RETURN b.unique_id as answer
   ```

**输入**:
- question: "What is the truck to the front of car1?"

**输出**:
- cypher: Cypher查询字符串

**性能**:
- 单条串行: ~8-9秒
- 批量(12): ~8-9秒 (12条一起)

---

### 8. 验证与记录 (Verification & Recording)

**目标**: 验证Cypher查询结果，记录覆盖

**关键函数**:
- `session.run(cypher)`
- `CoverageTracker.record_from_qa_with_candidates(qa, candidates, ctx)`

**操作**:
1. **执行Cypher验证**:
   ```python
   results = session.run(cypher).data()
   # 检查: len(results) == 1 and results[0]['answer'] == gap_target.id
   ```
2. **记录覆盖** (级联更新):
   - **Gap本身**: `ego->car1->car2` (L2)
   - **Siblings**: `ego->car1->car3`, `ego->car1->car4`, `ego->car1->car5` (L2)
   - **级联L1**: `ego->car1`, `car1->car2`, `car1->car3`, ... (L1)
   - **级联L0**: `ego`, `car1`, `car2`, `car3`, ... (L0)
3. **覆盖真实性**:
   - 只记录约束过程中实际使用的拓扑
   - 包括candidates和referents

**输入**:
- qa: {topology_level, path_pattern, template_id, question_id}
- candidates: [gap_target] + siblings
- ctx: 上下文信息

**输出**:
- 更新CoverageTracker的hit_count
- 覆盖率提升

**性能**: ~0.01秒

---

### 9. 批量写入CSV (Batch CSV Write)

**目标**: 将生成的QA对批量写入CSV文件

**关键函数**:
- `csv.DictWriter.writerows(all_qa)`

**操作**:
1. 收集所有QA对到内存列表
2. 一次性批量写入CSV:
   ```python
   with open(csv_path, "w", encoding="utf-8-sig") as f:
       writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
       writer.writeheader()
       writer.writerows(all_qa)  # 批量写入
   ```

**输入**:
- all_qa: List[Dict] (所有QA对)

**输出**:
- CSV文件，包含字段：
  - question_id, scene_name, frame_idx
  - Path_Structure, Topology_Level, Template_ID
  - Constraint_Trace, Token_Prompt, Token_Completion
  - Logic_Verification, Footprint_Nodes
  - is_unique, n_interference_siblings
  - question, answer

**性能**: ~0.1秒 (50条记录)

---

## 性能关键点

### 1. LLM批量调用
- **瓶颈**: 网络RTT (往返时间)
- **优化**: BATCH_SIZE=12，一次请求处理12个任务
- **效果**: 12× 吞吐提升

### 2. 线程池并行
- **瓶颈**: API QPS限制
- **优化**: N_WORKERS=8，同时发起8组batch请求
- **效果**: 8× 额外提升

### 3. CSV批量写入
- **瓶颈**: 频繁I/O操作
- **优化**: 内存收集 + 一次性写入
- **效果**: 避免每条记录一次I/O

### 4. Gap优先级选择
- **瓶颈**: 随机选择导致覆盖效率低
- **优化**: 优先级评分 (L0×10 + L1×15)
- **效果**: 更快达到高覆盖率

### 5. 覆盖真实性增强
- **瓶颈**: 只记录gap本身，忽略candidates
- **优化**: 记录gap + siblings + referents
- **效果**: 覆盖率显著提升

---

## 总体性能

### V5 (串行)
- 50个问题 × 9.8秒/问题 = 490秒 (~8分钟)

### V6 (批量+并行)
- 50个问题 / (12 × 8) ≈ 1批次 × 9.8秒 ≈ 20-30秒
- **加速比**: ~15-20×

### 目标 (优化后)
- 平均每题时间: ~1秒
- 50个问题: ~50秒

---

## 数据流示例

```
Gap: ego->car1->car2
  ↓
Context: {gap_target: car2(truck), siblings: [car3(car), car4(car), car5(ped)]}
  ↓
Template: "What is the {type} to the {dir} of {anchor}?"
  ↓
Constraint: TypeFilter(type=truck) → [car2]
  ↓
Question: "What is the truck to the front of car1?"
Answer: "car2"
  ↓
Cypher: MATCH (ego)-[:RELATES_TO]->(a)-[:RELATES_TO]->(b {type:'truck'}) ...
  ↓
Verification: ✅ len(results)==1 and results[0]=='car2'
  ↓
Coverage: 
  - L2: ego->car1->car2, ego->car1->car3, ego->car1->car4, ego->car1->car5
  - L1: ego->car1, car1->car2, car1->car3, car1->car4, car1->car5
  - L0: ego, car1, car2, car3, car4, car5
  ↓
CSV: [question_id, scene, frame, path, topology, template, ..., question, answer]
```

---

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| BATCH_SIZE | 12 | LLM批量调用大小 |
| N_WORKERS | 8 | 线程池并发数 |
| l2a_cells | 25 | L2A gap数量 |
| l2b_cells | 25 | L2B gap数量 |
| adaptive | True | 自适应gap选择 |

---

## 监控指标

### 覆盖率
- L0: 节点覆盖率 (covered/total)
- L1: 边覆盖率 (covered/total)
- L2: 路径覆盖率 (covered/total)

### 性能
- total_ms: 总耗时
- wall_ms: 实际墙钟时间
- avg_llm_ms: 平均LLM耗时
- tok_per_sec: 推理速度
- est_rtt_ms: 估算RTT占比

### 质量
- is_unique: 答案唯一性比例
- footprint_ok: 拓扑足迹正确性
- Logic_Verification: 逻辑验证通过率

---

## 故障排查

### 问题1: LLM调用超时
- **原因**: 网络不稳定或API限流
- **解决**: 减小BATCH_SIZE或N_WORKERS

### 问题2: 覆盖率提升缓慢
- **原因**: Gap选择策略不优
- **解决**: 启用优先级选择 (adaptive=True)

### 问题3: is_unique比例低
- **原因**: 约束方法不足或candidates构建错误
- **解决**: 检查_build_l2_candidates是否包含gap_target

### 问题4: CSV写入慢
- **原因**: 逐条写入导致频繁I/O
- **解决**: 使用批量写入 (writerows)

---

## 未来优化方向

1. **离线预处理**:
   - 场景图生成提前完成
   - 原题分析离线化

2. **更智能的Gap选择**:
   - 考虑模板适用性
   - 动态调整优先级权重

3. **更精细的覆盖追踪**:
   - 记录约束方法实际使用的拓扑
   - 区分"结构覆盖"和"语义覆盖"

4. **自适应批处理**:
   - 根据API响应时间动态调整BATCH_SIZE
   - 根据系统负载动态调整N_WORKERS
