# 流程图技术说明文档

> 对应文件：`docs/full_pipeline_flowchart.tex` (v2, March 2026)
> 流程图中每个模块标有编号 ①-㉖，本文档按编号逐一解释。

---

## Phase 0: Data Input & Filtering（数据输入与过滤）

### ① NuScenes Dataset

| 项目 | 说明 |
|------|------|
| **是什么** | 原始数据来源：nuScenes v1.0 — 1000个场景，1.4M 3D标注框，6路相机 + LiDAR |
| **每帧提供** | ego\_pose、sample\_annotation（category, translation, rotation, size, velocity, visibility, attributes） |
| **数据规模** | mini版10场景、trainval版850场景，每帧含数十个标注对象 |

### ② StatusInference

| 项目 | 说明 |
|------|------|
| **做什么** | 把NuScenes的连续速度值转成离散状态标签 |
| **文件** | `core_pipeline/vqa_pipeline/status_inference.py` |
| **输入** | NuScenes attributes列表 + velocity向量 |
| **输出** | 离散状态：`moving / stopped / with_rider / without_rider / standing / sitting / parked / unknown` |
| **逻辑** | **优先级1**：扫描attributes关键词（`moving`→moving, `with_rider`→with\_rider 等）；**优先级2**：若无匹配，按 ‖v‖ > 0.5 m/s → moving，否则 → stopped |
| **设计理由** | NuScenes仅有8个运动/姿态attribute，无颜色等视觉属性；离散化后才能出VLM可答的题目 |

### ③ Object Filter

| 项目 | 说明 |
|------|------|
| **做什么** | 过滤掉相机看不清的对象，只保留能出题的 |
| **文件** | `core_pipeline/coverage_evaluation/scene_filter.py` → `SceneGraphFilter` |
| **三门过滤** | (a) 欧氏距离 ≤ 50 m (b) 投影像素高 ≥ 10 px (c) NuScenes visibility ≥ 40% |
| **效果** | 典型场景：过滤前 60+ 对象 → 过滤后 10-30 个有效对象 |
| **意义** | 确保保留的对象在相机图像中可辨认，生成的问题确实CV-可答 |

### ④ QA Filter

| 项目 | 说明 |
|------|------|
| **做什么** | 跳过已知的错题（黑名单），避免浪费评测时间 |
| **文件** | `core_pipeline/coverage_evaluation/skip_questions.json` |
| **格式** | JSON数组，每条：`[scene_name, frame_idx, q_idx, reason]` |
| **来源** | 经5层retry仍失败的题目（NuScenesQA原始标注错误或题目歧义） |
| **当前规模** | 9条错题记录（最新3/9更新，含demo验证新增的2条） |
| **反馈闭环** | Phase 4的Blacklist → 红色虚线箭头 → 回到此处，下次自动跳过 |

---

## Phase 1: Scene Graph Construction（场景图构建）

### ⑤ Scene Graph Builder

| 项目 | 说明 |
|------|------|
| **做什么** | 把NuScenes标注转成结构化的场景图（节点+边） |
| **文件** | `core_pipeline/generate_selected_scenes_improved.py` |
| **节点** | ego + 所有过滤后对象，属性：type, status, attributes |
| **边** | 成对空间关系，**双坐标系**：Ego Frame（以ego朝向为基准）+ Source Frame（以源对象朝向为基准） |
| **8方位** | front / front-left / left / back-left / back / back-right / right / front-right（每个45°扇区） |
| **3距离桶** | near (≤10 m)、mid (10-25 m)、far (>25 m) |
| **方向属性** | `direction_8_ego/source`（精确方位）+ `angle_matches_ego/source`（宽松匹配列表，边界对象可匹配相邻方位） |

### ⑥ Scene Graph JSON

| 项目 | 说明 |
|------|------|
| **是什么** | 场景图的JSON文件，存储所有节点和边的完整信息 |
| **路径** | `output/coverage_analysis/scene_graphs/scene-XXXX_frameYY_scene_graph.json` |
| **节点结构** | `{ unique_id, type, category, status, attributes, translation, size, velocity }` |
| **边结构** | `{ source, target, direction_8_ego, direction_8_source, angle_matches_ego, angle_matches_source, distance_bin, distance, angle }` |
| **当前数据** | 6个场景图文件 — scene-0103×2, scene-0553, scene-0757, scene-0916, scene-1077 |

### ⑦ Neo4j Graph DB

| 项目 | 说明 |
|------|------|
| **做什么** | 把场景图导入图数据库，支持用Cypher语句查询验证答案 |
| **版本** | Neo4j Community 2025.10.1，Bolt端口 7600 |
| **Schema** | 节点 `:Object` {unique\_id, type, status, …}；关系 `[:RELATES_TO]` {direction\_8\_ego, angle\_matches\_ego, distance\_bin, …} |
| **当前数据** | 64 个 Object 节点，4032 条 RELATES\_TO 关系 |
| **作用** | Phase 4 的 LLM Oracle 生成 Cypher 后在此执行，返回结构化结果 |
| **约束** | 不存储 translation/rotation/size/velocity 等连续数值 — 全部已离散化 |

---

## Phase 2: Coverage Model（覆盖率模型）

### ⑧ Template Library

| 项目 | 说明 |
|------|------|
| **是什么** | 预定义的问题模板库，用来批量生成自然语言QA |
| **文件** | `core_pipeline/qa_generator_v2/template_library.py` (99 KB) |
| **规模** | **185个模板**，全部 CV-friendly（已删除精确数值模板） |
| **4级层次** | **Level** (L0/L1/L2) → **Type** (exist/count/status/object/comparison, 共5种) → **Pattern** (语义模式) → **Variant** (措辞变体) |
| **分布** | L0: 54, L1: 82, L2: 49；exist: 45, count: 42, object: 37, status: 36, comparison: 25 |
| **选择策略** | 为每个gap选 **least-used** 模板，确保模板分布均匀 |

### ⑨ SceneGraphIndex

| 项目 | 说明 |
|------|------|
| **做什么** | 在内存中建立场景图的索引，方便快速查节点属性 |
| **文件** | `core_pipeline/qa_generator_v2/template_filler.py` → `SceneGraphIndex` |
| **核心结构** | `node_by_id: Dict[str, Dict]` — O(1) HashMap 查找任意节点的完整属性 |
| **功能** | 模板填充时直接内存查找 type/status/attributes，无需 Cypher 查询 |
| **枚举** | 遍历所有节点(L0)、边(L1)、两跳路径(L2) 以初始化覆盖率元素 |

### ⑩ CoverageTracker

| 项目 | 说明 |
|------|------|
| **做什么** | 记录场景图中哪些元素已经被题目覆盖、哪些还没有 |
| **文件** | `core_pipeline/qa_generator_v2/coverage_tracker.py` |
| **L0 (Node)** | 63 个节点元素，每个 = 一个 unique\_id |
| **L1 (Edge)** | 3886 条有向边元素，每条 = `(source_id, target_id)` |
| **L2 (Path)** | 232K 条两跳路径元素，每条 = `(A_id → B_id → C_id)` |
| **KV存储** | 每个元素维护 `hit_count`（命中次数），初始=0 |
| **跨级传播** | L2 命中 → L1 + L0 附带覆盖；L1 命中 → L0 附带覆盖 |
| **API** | `coverage_rates()` → `{"L0": 0.048, "L1": 0.0, "L2": 0.0, "L0_detail": {"covered": 3, "total": 63}, ...}` |

### ⑪ JSON Persistence

| 项目 | 说明 |
|------|------|
| **做什么** | 把覆盖率状态保存到文件，下次可以接着上次继续 |
| **文件** | `coverage.json`（与场景图同目录） |
| **功能** | 序列化 CoverageTracker 状态，支持增量 save/load |
| **意义** | 多轮生成可累积覆盖率，不必每次从零开始 |

---

## Phase 3: Coverage-Driven Generation Loop（覆盖率驱动生成循环）

### ⑫ Set Focus Level

| 项目 | 说明 |
|------|------|
| **优先级** | L2 → L1 → L0（高层级优先，因为高层级题目附带覆盖低层级） |
| **模式** | 单层级聚焦：每轮只处理一个层级的 gap |
| **理由** | 一道L2题涉及两跳路径，天然覆盖其中的L1边和L0节点 |

### ⑬ Extract Gaps

| 项目 | 说明 |
|------|------|
| **条件** | `hit_count == 0` 的元素 = gap（未覆盖） |
| **输入** | CoverageTracker 中当前 focus level 的所有元素 |
| **输出** | 未覆盖元素列表 |

### ⑭ Budget & Shuffle

| 项目 | 说明 |
|------|------|
| **预算** | `min(max_questions, len(gaps))`，避免一次生成过多 |
| **随机化** | 随机排列 gap 列表，确保每次运行结果不同 |

### ⑮ Fill Template

| 项目 | 说明 |
|------|------|
| **文件** | `core_pipeline/qa_generator_v2/template_filler.py` |
| **流程** | ① 根据gap元素确定可用模板集 → ② 选 least-used 模板 → ③ SceneGraphIndex 查属性 → ④ 填充占位符 → 输出 (Q, GT\_answer) |
| **占位符** | `{obj_type}`, `{status}`, `{direction}`, `{ref_type}`, `{count}` 等 |
| **答案** | 直接从场景图数据确定性计算，不依赖 LLM，100% 准确 |

### ⑯ Record & Propagate

| 项目 | 说明 |
|------|------|
| **记录** | 对应元素 `hit_count += 1` |
| **跨级传播** | L2题 → 覆盖2条L1边 + 3个L0节点；L1题 → 覆盖2个L0节点 |
| **效果** | 大幅减少所需题数（一道L2题可同时填补多个低层级gap） |
| **循环** | Coverage OK? → **No**: 回到⑫继续；**Yes**: 结束生成 |

### ⑰ Generated QA Set

| 项目 | 说明 |
|------|------|
| **是什么** | 最终输出的问答集，每条含问题、答案、模板ID、覆盖的元素 |
| **内容** | 每条：question, answer, question\_type, template\_id, coverage\_element |
| **存储** | `output/qa_generated/scene-XXXX_frameYY_qa_full.json` |
| **下游** | 送入 Phase 4 (Oracle评测) 和 Phase 5 (VLM测试) |

---

## Phase 4: LLM + Neo4j Oracle Evaluation（Oracle评测 + 5层Retry）

### ⑱ LLM Cypher Oracle

| 项目 | 说明 |
|------|------|
| **做什么** | 用LLM把自然语言问题翻译成Cypher查询，在Neo4j上执行得到答案 |
| **模型** | DeepSeek-R1 (API: maas-api.ai-yuanjing.com) |
| **文件** | `core_pipeline/vqa_pipeline/pipeline.py` → `process_question_with_retry()` |
| **输入** | 自然语言问题 + Neo4j Schema + 方向匹配提示 + 上一次错误反馈(如有) |
| **输出** | 可执行 Cypher 查询字符串 |
| **Prompt** | 包含硬性规则（trailer处理、方位语义）、禁止使用velocity等连续属性、3个示例查询 |

### ⑲ Neo4j Query Exec

| 项目 | 说明 |
|------|------|
| **做什么** | 执行LLM生成的Cypher查询，返回结构化结果 |
| **文件** | `core_pipeline/vqa_pipeline/neo4j_client.py` |
| **功能** | 接收 Cypher → 在 Neo4j 执行 → 返回 `{success, data, error}` |
| **连接** | `bolt://localhost:7600`，用户 neo4j |

### ⑳ Answer Compare

| 项目 | 说明 |
|------|------|
| **做什么** | 把Oracle查出的答案和预计算的GT答案做比对 |
| **文件** | `pipeline.py` → `_check_answer_match()` |
| **匹配方式** | **精确匹配**（字符串完全相同）+ **语义匹配**（"1"="one", "stopped"="parked"）+ **类型敏感**（yes/no检查布尔, count比较数字） |
| **决策** | Correct? → **Yes**: 记录通过 → ㉓ Analysis Report；**No**: 进入 ㉑ Retry |

### ㉑ 5-Layer Retry

| 项目 | 说明 |
|------|------|
| **做什么** | 答案不对时，换不同的方向匹配策略让LLM重新生成Cypher |
| **文件** | `pipeline.py` → `process_question_with_retry()` |
| **Layer 1** | `ego_angle_matches` — `'DIR' IN r.angle_matches_ego`（Ego坐标系，宽松匹配） |
| **Layer 2** | `syntax_fix` — 修正Cypher语法错误后重试 |
| **Layer 3** | `source_angle_matches` — `'DIR' IN r.angle_matches_source`（Source坐标系，宽松匹配） |
| **Layer 4** | `ego_direction_8` — `r.direction_8_ego = 'DIR'`（Ego，精确45°匹配） |
| **Layer 5** | `source_direction_8` — `r.direction_8_source = 'DIR'`（Source，精确45°匹配） |
| **反馈** | 每层向LLM提供不同 direction hint，指导修改Cypher策略 |
| **统计** | 实测约30%题目需retry，大部分前3层解决 |
| **5x fail** | 全部失败 → ㉒ Update Blacklist |

### ㉒ Update Blacklist

| 项目 | 说明 |
|------|------|
| **文件** | `core_pipeline/coverage_evaluation/skip_questions.json` |
| **记录** | `[scene_name, frame_idx, q_idx, failure_reason]` |
| **反馈** | 红色虚线箭头 → Phase 0 的④ QA Filter，下次评测自动跳过 |

### ㉓ Analysis Report

| 项目 | 说明 |
|------|------|
| **是什么** | Oracle评测的汇总报告，含准确率、retry统计、分类统计 |
| **文件** | `output/coverage_analysis/vqa_results/enhanced_qa_test_*.json` |
| **内容** | 总题数、有效题数、跳过数、正确数、准确率、retry成功数 |
| **统计维度** | 按 question\_type, 按 scene, 按覆盖率层级 |
| **最新结果** | 33题，有效6题，准确率50%，retry成功2题 |

---

## Phase 5: VLM Testing（VLM图像测试）

### ㉔ VLM Under Test

| 项目 | 说明 |
|------|------|
| **是什么** | 被测试的视觉语言模型，接收图像+问题，输出回答 |
| **支持模型** | MiniCPM-V 2.6 (本地) / GPT-4V (API) |
| **输入** | 6路相机图像 + 自然语言问题 |
| **输出** | VLM 自然语言回答 |
| **意义** | 用覆盖率驱动的问题集，系统性测试VLM在不同空间区域、对象类型上的表现 |

### ㉕ VLM Answer Check

| 项目 | 说明 |
|------|------|
| **比对** | VLM回答 vs. 预计算GT答案 |
| **处理** | VLM回答可能含冗余描述，需提取核心答案；支持多选项匹配 |
| **维度** | 按空间区域(前/后/左/右)、按对象类型分类统计准确率 |

### ㉖ VLM Test Report

| 项目 | 说明 |
|------|------|
| **内容** | 空间区域准确率分布、对象类型准确率、覆盖率热力图 |
| **典型发现** | 弱区域：远距离对象(>30m)、后方对象、高遮挡对象 |
| **应用** | 指导VLM训练数据增强方向，识别系统性盲区 |

---

## 数据流总结

```
NuScenes ──→ StatusInference ──→ Object Filter ──→ QA Filter
    ①              ②                   ③               ④
                                       │                ▲
                                       ▼                │ (blacklist feedback)
                              Scene Graph Builder       │
                                       ⑤               │
                                    ╱      ╲            │
                                   ▼        ▼           │
                            SG JSON ──→ Neo4j          │
                               ⑥          ⑦            │
                               │                        │
                    ┌──────────┼──────────┐             │
                    ▼          ▼          ▼             │
              Template    SGIndex → CoverageTracker → Persist
              Library        ⑨          ⑩            ⑪
                 ⑧           │
                 │           ▼
                 └──→ Generation Loop (⑫→⑬→⑭→⑮→⑯)
                              │
                              ▼
                       Generated QA Set ⑰
                          ╱          ╲
                         ▼            ▼
                   LLM Oracle ⑱   VLM Test ㉔
                       │              │
                       ▼              ▼
                  Neo4j Exec ⑲   VLM Check ㉕
                       │              │
                       ▼              ▼
                 Answer Cmp ⑳    VLM Report ㉖
                       │
                  5-Layer Retry ㉑
                    ╱        ╲
                   ▼          ▼
             Blacklist ㉒  Report ㉓
                   │
                   └──→ QA Filter ④ (feedback)
```

---

## 关键设计决策

| 决策 | 理由 |
|------|------|
| 双坐标系 (Ego+Source) | NuScenesQA方位描述可能基于ego或参照对象，双坐标系覆盖两种语义 |
| 宽松匹配优先 | `angle_matches` 列表允许边界对象匹配相邻方位，提高查询召回率 |
| L2优先生成 | 一道L2题免费覆盖L1+L0，最大化覆盖效率 |
| 5层retry | 方位歧义是主要错误源，系统性切换坐标系+精度级别探索所有可能 |
| 错题黑名单 | 区分"模型错误"和"标注错误"，避免标注问题污染评测结果 |
| Neo4j图数据库 | 场景图天然适合图DB，Cypher表达力强，支持多跳路径查询 |
| 确定性模板生成 | 不依赖LLM生成QA，100%答案准确，快速可重复 |
| 三级覆盖率 | L0/L1/L2递进式覆盖，从单对象到关系到路径，系统性暴露VLM弱点 |
