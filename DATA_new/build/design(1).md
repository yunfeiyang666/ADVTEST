考虑到我们的代码实在不能令人满意。我决定重建代码，在此之前我们一起完整梳理框架，细致到每个环节需要什么样的代码，这个代码的输入是什么，输出是什么。梳理好之后再来一个代码一个代码地构建，每构建一个代码就模块性地检验其正确性。我们先来梳理。我先捋一下你来补充，里面所有变量先用统一变量名定义，确定好之后再统一写一个env来确定每个服务器的具体变量地址。

---

## 与 `rebuild_code` 实现同步的修订说明（以本节为准，2026-04）

本文写于设计阶段，后续在 `E:\Project\ADVTEST\DATA_new\rebuild_code\` 中已实现多处调整。**凡后文与下表矛盾之处，以本节为准。**

**覆盖的底线：追求真实覆盖。** 无论缺口文件如何写回、如何与「一题一维」表对齐，**L0 / L1 / L2 的「覆盖」在语义上仍应以真实为准**：在题目/查询**确实关涉**到对应节点、边、或三连边路径时，才计为有效覆盖。下文中的 `path_key` 校验、无候选时的回退、结构命中等，是**可自动化实现与判定的工程手段**；**不降低**对「是否真实关涉该对象/关系/路径」的要求——能判明题意与查询结果时，应以真实关涉为验收标准，避免把偶然串边、无关节点、或与题意不符的命中算作覆盖。

### 1. 代码与入口

- 主实现目录：`rebuild_code\code\`（如 `frame_processor.py`、`constraint_iteration.py`、`coverage_extractor.py`、`gap_selection.py`、`neo4j_import.py`、`qa_save.py`、`question_generation.py`、`templates.py` 等）；根目录另有 `run_single_gap_pipeline_log.py` 等脚本，便于单帧/单 gap 调试。

### 2. L2 缺口与 gap 状态（重要）

- **不再**区分 **L2A / L2B**；缺口与状态**统一**为 `gap_state['L2']`，键为**三跳路径**的 `path_key`（`a->b->c` 字符串），值为 `covered`、`hit_count` 等。对应代码：`neo4j_import.py` 建缺口、`gap_selection.py` 选 gap、`run_single_gap_pipeline_log.py` 中注释「不再区分 L2A/L2B」。

### 3. 缺口文件（每帧）

- 每场景每帧的缺口/覆盖状态文件名为：`{scene_id}_frame{frame_id}_gap.json`（在配置的 `COVERAGE_STATE_DIR` 下），而非旧文档中 L2A/L2B 分栏结构。

### 4. 环境变量与配置

- `code\config\config.py` 与 `env.rebuild_code.example`：对老命名做了**兼容**（如 `NUSCENES_DATAROOT` ↔ `NUSCENES_DATA_ROOT`，`FILTERED_SG_DIR` ↔ `SCENE_GRAPH_DIR`，VQA/LLM 等前缀可互换）。以示例 env 与代码中的 `_env` 解析为准。

### 5. 约束层（与模块 7 / 17 默认表不一致时）

- **逐跳约束的迭代逻辑**在 `constraint_iteration.py` 的 `CONSTRAINT_LAYERS`：**共 3 层**——`direction`（6 向，与 `RELATES_TO` 的 `direction` 一致）、`distance_range`、`object_type`。
- 模块 17 里 `load_constraint_strategies` 若文件**不存在**时返回的**默认**列表（`direction_8` / 五层等）是**历史占位**；**实际**生成题/约束走 `apply_constraints_iterative` 的上述 **3 层**。

### 6. Cypher 生成与「强绑三节点」

- 生成 Cypher 时可传入 `gap`：`question_generation` / 约束层与初始 Cypher 提示中会要求 **MATCH 覆盖 `path[0/1/2]` 三节点**（见 `constraint_iteration.py` 中 `_build_cypher_generation_prompt` 片段）。
- `apply_constraints_iterative` 可带 **`template`**，用于**答案/槽位**校验（与纯 Neo4j 结果唯一性配合）。

### 7. 覆盖率写回（实现 vs 真实覆盖）

- 由 `extract_coverage_from_query` / `extract_coverage_with_provenance` 等解析查询结果；`update_gap_json_with_generated`（及同类逻辑）在工程上**仅当** `path_key` 已存在于本帧 `gap_state['L2']` 中时才写 `covered` / `hit_count`；**自动写回不单独依赖**「大模型自然语言答句是否人工意义上的正确」。无候选/无历史时，常**回退**到从 `path` / `path_key` 作 L2 计数以保持流水线可用（见 `coverage_extractor.py`）。
- **与底线原则的关系**：上述写回是**可机械执行的规则**；**统计与对外报告时**，仍应优先解释与核对「题目—查询—图结构」是否**真实**覆盖目标对象/边/路径；对可疑命中应做抽检或更严规则，**不**把回退策略等同于放弃真实覆盖。

### 8. 模板

- 见 `code\templates.py`（`TemplateManager`、`AnswerTarget` 等）。如 `VQA_TEMPLATE_MODE=dumb` 为固定最简模板；填槽逻辑可在**无 Neo4j** 时仍填充 `mid_id`、`direction*` 等（见 `_prepare_fill_params` 一类逻辑）。

### 9. 设计备注（与「一题一维」论文口径）

- 若需与 L 表一一**精细计分**（每题一维独立统计），在**不违背「真实覆盖」底线**的前提下，可在现有回写与解析上增加更细规则。当前自动化回写在部分路径上**偏结构可判定**；**扩展规则时不应**为了表格整齐而记「形式上命中、语义上未关涉」的覆盖。本节不展开实现细节。

---

1. 启动程序要检查本地的六千帧nuscenes数据以及针对每台服务器的plan，以及要启动neo4j并检查api连通情况，输出读取的数据地址表示正确读取，输出neo4j和api情况
2. 场景图生成，从六千帧数据中按plan顺序读取一帧场景数据，根据我们的筛选规则进行筛选，筛选后的节点构建场景图，场景图包括所有筛选后节点的完全图
3. 场景图导入数据库，输入场景图信息，将场景图导入neo4j，并创建缺口json放到对应文件夹。 
4. 读取这一帧的nuscenesQA自然语言题目，大模型读取后转换成查询该题目切实覆盖的对象的cypher，传给neo4j得到返回结果，包含覆盖的节点和边，再找一首连另一尾的二连边组合 
5. 覆盖率分析代码，输入刚才得到的查询覆盖信息，将具体覆盖的对象写在初始题分析的csv里，并同步写在缺口json里。初始题分析csv格式待确定，场景编号、帧数、问题题号，具体覆盖的L0、1、2对象
6. L0：节点。L1：两个节点之间的边，以a→b格式保存。L2：三个节点形成的二连边组合，以a→b→c保存

7. 原始题分析完后读取缺口json，找一个L1、0涉及节点都没被覆盖过的L2gap（初始阶段，L0、1覆盖完后再随机选择gap）
8. 问题生成代码，输入刚才抽到的gap，随机选择模板库里的模板，生成一个完整的自然语言问题，gap为其答案
9. 将问题输入给大模型，让其转换为回答这个问题的查询cypher进入neo4j数据库查询，输出得到的查询结果。如果结果唯一，直接形成完整问答对。结果不唯一，将这些包含但大于预设结果的所有对象视作候选集放在内存，用我们的约束方法进行逐层约束，每约束一次就用程序在大模型生成初始cypher基础上加上约束条件并进行查询，如果某种约束方法查询结果唯一就形成完整问答对，写入生成题csv。预设的约束流程走完仍然不唯一就转换成数数问题或存在问题。生成题保存格式，场景号，帧数，生成问题题目、答案，题目等级（L0、1、2），具体覆盖的L0、1、2对象，几个时间戳（精确到ms级别，读取该缺口的起始时间，大模型生成cypher并查询完返回结果的时间，该gap的结束时间，约束的迭代次数
10. 直到该帧缺口全部覆盖完再进入下一帧
11. 与大模型的交互以及写入csv的过程都采用批次法，一批传、写多组数据

---

## 任务拆解与函数设计

### 模块1: 系统初始化与环境检查

#### 1.1 环境配置加载
**函数**: `load_environment_config()`
- **输入**: 无（从环境变量或配置文件读取）
- **输出**: `dict` - 包含所有配置项的字典
  ```python
  {
      'nuscenes_data_root': str,  # nuScenes数据根目录
      'server_plan_path': str,    # 当前服务器的plan文件路径
      'neo4j_uri': str,           # Neo4j连接URI
      'neo4j_user': str,          # Neo4j用户名
      'neo4j_password': str,      # Neo4j密码
      'llm_api_endpoint': str,    # LLM API地址
      'llm_api_key': str,         # LLM API密钥
      'output_dir': str,          # 输出目录
      'coverage_state_dir': str,  # 覆盖状态JSON目录
      'batch_size': int           # 批处理大小
  }
  ```
- **功能**: 读取并验证所有必需的环境变量和配置项

#### 1.2 nuScenes数据验证
**函数**: `validate_nuscenes_data(data_root: str) -> dict`
- **输入**: 
  - `data_root`: nuScenes数据根目录路径
- **输出**: `dict` - 验证结果
  ```python
  {
      'valid': bool,              # 数据是否有效
      'total_scenes': int,        # 总场景数
      'total_frames': int,        # 总帧数（约6000）
      'data_version': str,        # 数据版本
      'missing_files': list       # 缺失的文件列表
  }
  ```
- **功能**: 检查nuScenes数据完整性，统计场景和帧数

#### 1.3 服务器Plan加载
**函数**: `load_server_plan(plan_path: str) -> list`
- **输入**: 
  - `plan_path`: plan JSON文件路径   【question：这个plan JSON怎么生成】
- **输出**: `list` - 帧处理顺序列表
  ```python
  [
      {'scene_id': str, 'frame_id': int},
      {'scene_id': str, 'frame_id': int},
      ...
  ]
  ```
- **功能**: 读取当前服务器分配的帧处理计划

#### 1.4 Neo4j连接检查
**函数**: `check_neo4j_connection(uri: str, user: str, password: str) -> dict`
- **输入**: 
  - `uri`: Neo4j URI
  - `user`: 用户名
  - `password`: 密码
- **输出**: `dict` - 连接状态
  ```python
  {
      'connected': bool,          # 是否连接成功
      'version': str,             # Neo4j版本
      'database': str,            # 数据库名称
      'error': str or None        # 错误信息
  }
  ```
- **功能**: 测试Neo4j连接并获取数据库信息

#### 1.5 LLM API连接检查
**函数**: `check_llm_api(endpoint: str, api_key: str) -> dict`
- **输入**: 
  - `endpoint`: API端点
  - `api_key`: API密钥
- **输出**: `dict` - API状态
  ```python
  {
      'available': bool,          # API是否可用
      'model': str,               # 模型名称
      'latency_ms': float,        # 响应延迟（毫秒）
      'error': str or None        # 错误信息
  }
  ```
- **功能**: 测试LLM API连通性和响应速度

#### 1.6 系统初始化主函数
**函数**: `initialize_system() -> dict`
- **输入**: 无
- **输出**: `dict` - 初始化结果
  ```python
  {
      'success': bool,
      'config': dict,             # 配置信息
      'nuscenes_status': dict,    # nuScenes验证结果
      'plan': list,               # 帧处理计划
      'neo4j_status': dict,       # Neo4j状态
      'llm_status': dict,         # LLM状态
      'errors': list              # 错误列表
  }
  ```
- **功能**: 调用上述所有检查函数，输出完整的系统状态报告

---

### 模块2: 场景图生成

#### 2.1 读取单帧数据
**函数**: `load_frame_data(scene_id: str, frame_id: int, data_root: str) -> dict`
- **输入**: 
  - `scene_id`: 场景ID
  - `frame_id`: 帧ID
  - `data_root`: nuScenes数据根目录 【question：从config中读取，要注意检查代码读取正确值】
- **输出**: `dict` - 帧数据
  ```python
  {
      'scene_id': str,
      'frame_id': int,
      'timestamp': int,           # 时间戳
      'ego_pose': dict,           # ego车位姿
      'objects': list,            # 所有检测到的对象
      'annotations': list         # 标注信息
  }
  ```
- **功能**: 从nuScenes数据集中读取指定帧的完整数据

#### 2.2 对象筛选
**函数**: `filter_objects(objects: list, filter_rules: dict) -> list`
- **输入**: 
  - `objects`: 原始对象列表
  - `filter_rules`: 筛选规则字典
- **输出**: `list` - 筛选后的对象列表
  ```python
  [
      {
          'unique_id': str,       # 对象唯一ID
          'type': str,            # 对象类型（car, pedestrian等）
          'position': tuple,      # 位置坐标
          'attributes': dict      # 其他属性
      },
      ...
  ]
  ```
- **功能**: 根据预定义规则筛选有效对象（距离、可见性等）

#### 2.3 构建完全图
**函数**: `build_complete_graph(filtered_objects: list, ego_pose: dict) -> dict`
- **输入**: 
  - `filtered_objects`: 筛选后的对象列表
  - `ego_pose`: ego车位姿
- **输出**: `dict` - 场景图
  ```python
  {
      'nodes': list,              # 节点列表（包含ego）
      'edges': list,              # 边列表（完全图）
      'node_count': int,          # 节点数量
      'edge_count': int           # 边数量
  }
  ```
- **功能**: 构建包含所有筛选对象的完全图，计算节点间关系

#### 2.4 场景图生成主函数
**函数**: `generate_scene_graph(scene_id: str, frame_id: int, config: dict) -> dict`
- **输入**: 
  - `scene_id`: 场景ID
  - `frame_id`: 帧ID
  - `config`: 配置字典
- **输出**: `dict` - 完整场景图
  ```python
  {
      'scene_id': str,
      'frame_id': int,
      'graph': dict,              # 场景图数据
      'metadata': dict            # 元数据（生成时间等）
  }
  ```
- **功能**: 整合上述函数，生成完整场景图 【question：场景图可以在这里生成完后直接调用import_graph_to_neo4J()导入neo4j】【question：这些其实都可以全部离线处理完】

---

### 模块3: 场景图导入与缺口初始化

#### 3.1 场景图导入Neo4j
**函数**: `import_graph_to_neo4j(scene_graph: dict, neo4j_conn) -> dict`
- **输入**: 
  - `scene_graph`: 场景图数据
  - `neo4j_conn`: Neo4j连接对象
- **输出**: `dict` - 导入结果
  ```python
  {
      'success': bool,
      'nodes_created': int,       # 创建的节点数
      'edges_created': int,       # 创建的边数
      'import_time_ms': float,    # 导入耗时
      'error': str or None
  }
  ```
- **功能**: 将场景图节点和边导入Neo4j数据库

#### 3.2 初始化缺口JSON 【question：最好每个scene一个单独的json文件，避免此文件过大 & 频繁更新】
**函数**: `initialize_gap_json(scene_id: str, frame_id: int, scene_graph: dict, output_dir: str) -> dict`
- **输入**: 
  - `scene_id`: 场景ID
  - `frame_id`: 帧ID
  - `scene_graph`: 场景图数据（包含所有节点和边）
  - `output_dir`: 输出目录
- **输出**: `dict` - 缺口状态
  ```python
  {
      'scene_id': str,
      'frame_id': int,
      'L0': dict,                 # {node_id: {'covered': False, 'hit_count': 0}}
      'L1': dict,                 # {edge_key: {'covered': False, 'hit_count': 0}}
      'L2A': dict,                # {path_key: {'covered': False, 'hit_count': 0}}
      'L2B': dict,                # {path_key: {'covered': False, 'hit_count': 0}}
      'stats': {
          'L0_theory': int,
          'L1_theory': int,
          'L2A_theory': int,
          'L2B_theory': int
      }
  }
  ```
- **功能**: 
  - 从场景图枚举所有L0节点、L1边、L2A路径、L2B路径
  - 确保理论值与实际枚举数量一致
  - 创建初始缺口JSON文件

#### 3.3 枚举所有覆盖项 【question：3.3和3.2的关系？】
**函数**: `enumerate_all_coverage_items(scene_graph: dict) -> dict`
- **输入**: 
  - `scene_graph`: 场景图数据
- **输出**: `dict` - 所有覆盖项
  ```python
  {
      'L0': list,                 # 所有节点ID列表
      'L1': list,                 # 所有边 [(src, tgt), ...]
      'L2A': list,                # 所有L2A路径 [(ego, o2, o3), ...]
      'L2B': list,                # 所有L2B路径 [(o1, o2, o3), ...] 其中o1!=ego
      'counts': {
          'L0': int,
          'L1': int,
          'L2A': int,
          'L2B': int
      }
  }
  ```
- **功能**: 
  - 根据场景图完整枚举所有L0/L1/L2A/L2B项
  - L2B = (n-1) × (n-1) × (n-2)，完整枚举不设上限
  - 确保理论值与枚举数量完全一致

---

### 模块4: 原始题分析

#### 4.1 读取nuScenesQA题目
**函数**: `load_nuscenes_qa(scene_id: str, frame_id: int, qa_data_path: str) -> list`
- **输入**: 
  - `scene_id`: 场景ID
  - `frame_id`: 帧ID
  - `qa_data_path`: nuScenesQA数据路径
- **输出**: `list` - 题目列表
  ```python
  [
      {
          'question_id': str,
          'question': str,        # 自然语言问题
          'answer': str,          # 答案
          'question_type': str    # 题目类型
      },
      ...
  ]
  ```
- **功能**: 读取指定帧的nuScenesQA原始题目

#### 4.2 LLM转换Cypher（逐题处理）
**函数**: `convert_question_to_cypher(question: str, scene_context: dict, llm_client) -> dict`
- **输入**: 
  - `question`: 单个问题
  - `scene_context`: 场景上下文（节点列表等）
  - `llm_client`: LLM客户端
- **输出**: `dict` - Cypher查询
  ```python
  {
      'question_id': str,
      'cypher': str,              # 生成的Cypher查询
      'llm_time_ms': float,       # LLM耗时
      'success': bool,
      'error': str or None
  }
  ```
- **功能**: 
  - 逐题转换，确保质量
  - 原始题不够规范，批量处理容易出错
  - 每题独立处理，失败不影响其他题

#### 4.3 执行Cypher查询
**函数**: `execute_cypher_single(cypher: str, neo4j_conn) -> dict`
- **输入**: 
  - `cypher`: Cypher查询
  - `neo4j_conn`: Neo4j连接
- **输出**: `dict` - 查询结果
  ```python
  {
      'nodes': list,              # 覆盖的节点
      'edges': list,              # 覆盖的边
      'query_time_ms': float,     # 查询耗时
      'success': bool,
      'error': str or None
  }
  ```
- **功能**: 执行单个Cypher查询并返回结果

#### 4.4 提取覆盖信息
**函数**: `extract_coverage_from_result(query_result: dict) -> dict`
- **输入**: 
  - `query_result`: 单个查询结果
- **输出**: `dict` - 覆盖信息
  ```python
  {
      'l0_nodes': list,           # 覆盖的L0节点
      'l1_edges': list,           # 覆盖的L1边（a→b格式）
      'l2_paths': list            # 覆盖的L2路径（a→b→c格式）
  }
  ```
- **功能**: 从查询结果中提取L0/L1/L2覆盖信息

#### 4.5 更新缺口JSON 【question：预估每个scene的缺口json文件大小，可否放入内存中，不然此文件会存在频繁更新，影响效率】
**函数**: `update_gap_json(gap_json_path: str, coverage_info: dict) -> dict`
- **输入**: 
  - `gap_json_path`: 缺口JSON文件路径
  - `coverage_info`: 单题的覆盖信息
- **输出**: `dict` - 更新后的缺口状态
- **功能**: 将单题覆盖信息同步到缺口JSON，标记已覆盖项

#### 4.6 保存原始题分析到全局CSV
**函数**: `append_baseline_to_global_csv(analysis_record: dict, global_csv_path: str) -> bool`
- **输入**: 
  - `analysis_record`: 单题分析记录
  - `global_csv_path`: 全局CSV路径（所有帧共用）
- **输出**: `bool` - 是否成功
- **CSV格式**:
  ```
  scene_id, frame_id, question_id, question, answer, l0_nodes, l1_edges, l2_paths, n_l0, n_l1, n_l2, llm_ms, query_ms, timestamp 【question：这里的question_id和我们后面自动化生成的question_id注意区分】
  ```
- **功能**: 
  - 追加模式写入全局CSV
  - 所有6000帧的原始题分析放在一个文件
  - 便于后续统计分析

#### 4.7 原始题分析主循环
**函数**: `analyze_baseline_questions(scene_id: str, frame_id: int, gap_json_path: str, global_csv_path: str, config: dict) -> dict`
- **输入**: 
  - `scene_id`: 场景ID
  - `frame_id`: 帧ID
  - `gap_json_path`: 缺口JSON路径 【question：看这里是否需要将gap_json存入内存中操作提升效率，另外，这部分也可以提前离线处理完】
  - `global_csv_path`: 全局CSV路径
  - `config`: 配置字典
- **输出**: `dict` - 分析结果
  ```python
  {
      'total_questions': int,
      'success_count': int,
      'failure_count': int,
      'coverage_updated': bool,
      'elapsed_time_s': float
  }
  ```
- **功能**: 
  - 逐题处理原始题目
  - 每题转换、查询、提取覆盖、更新gap、写CSV
  - 失败题目记录但不中断流程

---

### 模块5: Gap选择策略

#### 5.1 读取缺口状态
**函数**: `load_gap_state(gap_json_path: str) -> dict`
- **输入**: 
  - `gap_json_path`: 缺口JSON路径
- **输出**: `dict` - 缺口状态（同3.2格式）
- **功能**: 读取当前缺口覆盖状态

#### 5.2 检查L0/L1覆盖完成情况
**函数**: `check_l0_l1_completion(gap_state: dict) -> dict`
- **输入**: 
  - `gap_state`: 缺口状态
- **输出**: `dict` - 完成情况
  ```python
  {
      'l0_complete': bool,        # L0是否全部覆盖
      'l1_complete': bool,        # L1是否全部覆盖
      'l0_coverage': float,       # L0覆盖率
      'l1_coverage': float,       # L1覆盖率
      'l0_remaining': int,        # L0剩余数量
      'l1_remaining': int         # L1剩余数量
  }
  ```
- **功能**: 检查L0和L1的覆盖完成情况，决定gap选择策略 【question：这里的gap选择策略和生成问题的约束规则，为何不能覆盖更多的l2】

#### 5.3 选择L2 Gap（优先未覆盖L0/L1）
**函数**: `select_l2_gap_priority_uncovered(gap_state: dict) -> dict or None`
- **输入**: 
  - `gap_state`: 缺口状态
- **输出**: `dict or None` - 选中的gap
  ```python
  {
      'gap_type': str,            # 'L2A' or 'L2B'
      'path': tuple,              # (o1, o2, o3)
      'uncovered_l0': list,       # 该gap涉及的未覆盖L0节点
      'uncovered_l1': list,       # 该gap涉及的未覆盖L1边
      'priority_score': int       # 优先级分数（未覆盖L0+L1数量）
  }
  ```
- **功能**: 
  - 在未覆盖的L2 gap中，优先选择涉及最多未覆盖L0/L1的gap
  - 计算每个gap的优先级分数 = 未覆盖L0数 + 未覆盖L1数
  - 选择分数最高的gap

#### 5.4 选择L2 Gap（随机选择）
**函数**: `select_l2_gap_random(gap_state: dict) -> dict or None`
- **输入**: 
  - `gap_state`: 缺口状态
- **输出**: `dict or None` - 选中的gap（同5.3格式）
- **功能**: 
  - 当L0/L1全部覆盖后，从未覆盖的L2 gap中随机选择
  - 确保所有L2 gap都有机会被选中

#### 5.5 Gap选择主函数
**函数**: `select_next_gap(gap_json_path: str) -> dict or None`
- **输入**: 
  - `gap_json_path`: 缺口JSON路径
- **输出**: `dict or None` - 选中的gap（同5.3格式）
- **功能**: 
  1. 读取gap状态
  2. 检查L0/L1完成情况
  3. 如果L0/L1未完成，调用5.3优先选择
  4. 如果L0/L1已完成，调用5.4随机选择
  5. 如果所有gap都已覆盖，返回None

---

### 模块6: 问题生成

#### 6.1 加载模板库
**函数**: `load_question_templates(template_path: str) -> dict`
- **输入**: 
  - `template_path`: 模板文件路径
- **输出**: `dict` - 模板库
  ```python
  {
      'L2A': [
          {'template': str, 'type': str},
          ...
      ],
      'L2B': [
          {'template': str, 'type': str},
          ...
      ]
  }
  ```
- **功能**: 加载问题生成模板

#### 6.2 生成自然语言问题
**函数**: `generate_question_from_gap(gap: dict, templates: dict) -> str`
- **输入**: 
  - `gap`: gap信息
  - `templates`: 模板库
- **输出**: `str` - 自然语言问题
- **功能**: 根据gap和随机选择的模板生成问题

---

### 模块7: 问题约束与答案生成

#### 7.1 LLM生成初始Cypher
**函数**: `generate_initial_cypher(question: str, llm_client) -> dict`
- **输入**: 
  - `question`: 自然语言问题
  - `llm_client`: LLM客户端
- **输出**: `dict` - Cypher查询
  ```python
  {
      'cypher': str,
      'llm_time_ms': float
  }
  ```
- **功能**: 让LLM将问题转换为Cypher查询

#### 7.2 执行Cypher并获取候选集
**函数**: `execute_and_get_candidates(cypher: str, neo4j_conn) -> dict`
- **输入**: 
  - `cypher`: Cypher查询
  - `neo4j_conn`: Neo4j连接
- **输出**: `dict` - 查询结果
  ```python
  {
      'results': list,            # 查询结果
      'count': int,               # 结果数量
      'query_time_ms': float
  }
  ```
- **功能**: 执行Cypher查询，获取候选对象集

#### 7.3 定义约束层级结构
**数据结构**: `CONSTRAINT_LAYERS`
```python
CONSTRAINT_LAYERS = [
    {
        'name': 'direction_8',
        'description': '8方向约束（front, back, left, right等）',
        'cypher_template': 'r.direction_8 = "{value}"'
    },
    {
        'name': 'direction_4', 
        'description': '4方向约束（front, back, left, right）',
        'cypher_template': 'r.direction_4 = "{value}"'
    },
    {
        'name': 'distance_range',
        'description': '距离范围约束',
        'cypher_template': 'r.distance >= {min} AND r.distance <= {max}'
    },
    {
        'name': 'object_type',
        'description': '对象类型约束',
        'cypher_template': 'target.type = "{value}"'
    },
    {
        'name': 'relative_position',
        'description': '相对位置约束（closer/farther）',
        'cypher_template': 'r.relative_position = "{value}"'
    }
]
```
- **说明**: 
  - 约束层数固定为5层（可配置）
  - 每层约束按优先级顺序应用
  - 不需要LLM参与，纯程序化添加约束

#### 7.4 约束迭代（程序化）
**函数**: `apply_constraints_iterative(initial_cypher: str, candidates: list, expected_answer: dict, neo4j_conn) -> dict`
- **输入**: 
  - `initial_cypher`: 初始Cypher
  - `candidates`: 候选集
  - `expected_answer`: 预期答案（gap）
  - `neo4j_conn`: Neo4j连接
- **输出**: `dict` - 约束结果
  ```python
  {
      'success': bool,            # 是否得到唯一结果
      'final_cypher': str,        # 最终Cypher
      'answer': str,              # 答案
      'iterations': int,          # 实际迭代次数（1-5）
      'constraint_history': list, # 每层约束的详情
      'final_count': int          # 最终结果数量
  }
  ```
- **功能**: 
  - 按CONSTRAINT_LAYERS顺序逐层添加约束
  - 每添加一层约束就执行查询
  - 如果结果唯一且匹配预期答案，停止迭代
  - 最多迭代5次（约束层数）
  - 不使用LLM，纯程序化

#### 7.5 转换为数数/存在问题
**函数**: `convert_to_counting_or_existence(question: str, candidates: list, expected_answer: dict) -> dict`
- **输入**: 
  - `question`: 原问题
  - `candidates`: 候选集
  - `expected_answer`: 预期答案
- **输出**: `dict` - 转换后的问题
  ```python
  {
      'question': str,            # 转换后的问题
      'answer': str,              # 答案
      'question_type': str        # 'counting' or 'existence'
  }
  ```
- **功能**: 
  - 当5层约束都无法得到唯一结果时转换
  - 数数问题：How many objects...? 答案为候选集数量
  - 存在问题：Is there a ... ? 答案为yes/no

---

### 模块8: 生成题保存

#### 8.1 构建问答对记录
**函数**: `build_qa_record(gap: dict, question: str, answer: str, coverage: dict, timestamps: dict, iterations: int) -> dict`
- **输入**: 
  - `gap`: gap信息
  - `question`: 问题
  - `answer`: 答案
  - `coverage`: 覆盖信息
  - `timestamps`: 时间戳字典
  - `iterations`: 迭代次数
- **输出**: `dict` - 完整记录
  ```python
  {
      'scene_id': str,
      'frame_id': int,
      'question_id': str,
      'question': str,
      'answer': str,
      'q_type': str,              # 'L2A' or 'L2B'
      'l0_nodes': list,
      'l1_edges': list,
      'l2_paths': list,
      'n_l0': int,
      'n_l1': int,
      'n_l2': int,
      'timestamp_start': str,     # gap选择时间
      'timestamp_llm': str,       # LLM生成cypher时间
      'timestamp_cypher_return': str,  # cypher返回时间
      'timestamp_end': str,       # gap完成时间
      'iteration_count': int,
      'llm_ms': float
  }
  ```
- **功能**: 构建完整的问答对记录

#### 8.2 保存生成题到帧级CSV 【question：8.1和8.2可以合并】
**函数**: `save_generated_qa_to_frame_csv(qa_record: dict, scene_id: str, frame_id: int, output_dir: str) -> bool`
- **输入**: 
  - `qa_record`: 问答对记录
  - `scene_id`: 场景ID
  - `frame_id`: 帧ID
  - `output_dir`: 输出目录
- **输出**: `bool` - 是否成功
- **文件命名**: `{scene_id}_frame{frame_id}_generated.csv`
- **CSV格式**: 同8.1的dict字段
- **功能**: 
  - 每帧一个独立的CSV文件
  - 追加模式写入
  - 内容较多，分帧存储便于管理

#### 8.3 更新缺口JSON（生成题）【question：同理，这里缺口json是否可以存在内存】
**函数**: `update_gap_json_with_generated(gap_json_path: str, qa_record: dict) -> dict`
- **输入**: 
  - `gap_json_path`: 缺口JSON路径
  - `qa_record`: 问答对记录
- **输出**: `dict` - 更新后的缺口状态
- **功能**: 将生成题的覆盖信息同步到缺口JSON

---

### 模块9: 帧级循环控制

#### 9.1 检查帧是否完成
**函数**: `is_frame_complete(gap_json_path: str) -> bool`
- **输入**: 
  - `gap_json_path`: 缺口JSON路径
- **输出**: `bool` - 是否完成
- **功能**: 检查该帧所有缺口是否已覆盖

#### 9.2 帧处理主循环
**函数**: `process_frame(scene_id: str, frame_id: int, config: dict) -> dict`
- **输入**: 
  - `scene_id`: 场景ID
  - `frame_id`: 帧ID
  - `config`: 配置字典
- **输出**: `dict` - 处理结果
  ```python
  {
      'success': bool,
      'scene_id': str,
      'frame_id': int,
      'total_questions': int,     # 生成的总题数
      'baseline_questions': int,  # 原始题数
      'generated_questions': int, # 新生成题数
      'coverage': {
          'L0': float,            # L0覆盖率
          'L1': float,            # L1覆盖率
          'L2A': float,           # L2A覆盖率
          'L2B': float            # L2B覆盖率
      },
      'elapsed_time_s': float
  }
  ```
- **功能**: 
  1. 生成场景图
  2. 导入Neo4j
  3. 分析原始题【question：前面可以离线完成】
  4. 循环生成题直到覆盖完成
  5. 返回处理结果（包含覆盖率信息）

#### 9.3 覆盖率信息的使用说明 【question：不一定要实时计算，流程完全后依据csv文件就可以计算过程覆盖率，并且也方便统计按照题目数和按照时间分别的覆盖率】
- **实时计算**: 在9.2中实时计算覆盖率，作为返回值的一部分
- **不写入文件**: 覆盖率信息不单独写入文件，避免影响流程时间
- **后续分析**: 
  - 可以从gap JSON文件中读取覆盖状态
  - 可以从生成题CSV中统计覆盖信息
  - 单独运行覆盖率分析脚本进行画图
- **设计原则**: 主流程专注于问题生成，覆盖率分析作为独立的后处理步骤

---

### 模块10: 全局主流程

#### 10.1 主程序入口
**函数**: `main()`
- **输入**: 无
- **输出**: 无
- **功能**: 
  1. 调用系统初始化（模块1）
  2. 读取服务器plan【question：每个服务器是否只能同时处理一帧数据，可否并行】
  3. 按plan顺序处理每一帧（模块9）
  4. 输出总体统计信息
  5. 异常处理和日志记录

---

### 模块11: 批处理优化

#### 11.1 LLM批处理包装器
**函数**: `llm_batch_call(prompts: list, llm_client, batch_size: int) -> list`
- **输入**: 
  - `prompts`: prompt列表
  - `llm_client`: LLM客户端
  - `batch_size`: 批大小
- **输出**: `list` - 响应列表
- **功能**: 将多个LLM请求打包成批次调用

#### 11.2 CSV批量写入包装器
**函数**: `csv_batch_write(records: list, output_path: str, buffer_size: int) -> bool`
- **输入**: 
  - `records`: 记录列表
  - `output_path`: 输出路径
  - `buffer_size`: 缓冲区大小
- **输出**: `bool` - 是否成功
- **功能**: 使用缓冲区批量写入CSV，提高IO效率

---

### 统一变量名定义

```python
# 路径相关
NUSCENES_DATA_ROOT = os.getenv('NUSCENES_DATA_ROOT')
SERVER_PLAN_PATH = os.getenv('SERVER_PLAN_PATH')
OUTPUT_DIR = os.getenv('OUTPUT_DIR')
COVERAGE_STATE_DIR = os.getenv('COVERAGE_STATE_DIR')
TEMPLATE_PATH = os.getenv('TEMPLATE_PATH')
CHECKPOINT_DIR = os.getenv('CHECKPOINT_DIR')  # 断点续传目录
LOG_DIR = os.getenv('LOG_DIR')  # 日志目录

# Neo4j相关
NEO4J_URI = os.getenv('NEO4J_URI')
NEO4J_USER = os.getenv('NEO4J_USER')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD')
NEO4J_MAX_CONNECTION_POOL_SIZE = int(os.getenv('NEO4J_MAX_CONNECTION_POOL_SIZE', '50'))
NEO4J_CONNECTION_TIMEOUT = int(os.getenv('NEO4J_CONNECTION_TIMEOUT', '30'))
NEO4J_MAX_TRANSACTION_RETRY_TIME = int(os.getenv('NEO4J_MAX_TRANSACTION_RETRY_TIME', '30'))

# LLM相关
LLM_API_ENDPOINT = os.getenv('LLM_API_ENDPOINT')
LLM_API_KEY = os.getenv('LLM_API_KEY')
LLM_MODEL = os.getenv('LLM_MODEL')
LLM_TIMEOUT = int(os.getenv('LLM_TIMEOUT', '180'))
LLM_MAX_RETRIES = int(os.getenv('LLM_MAX_RETRIES', '3'))
LLM_RETRY_DELAY = int(os.getenv('LLM_RETRY_DELAY', '5'))

# 批处理相关
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '32'))
CSV_BUFFER_SIZE = int(os.getenv('CSV_BUFFER_SIZE', '100'))
MAX_CONSTRAINT_ITERATIONS = int(os.getenv('MAX_CONSTRAINT_ITERATIONS', '10'))

# 筛选规则
FILTER_DISTANCE_THRESHOLD = float(os.getenv('FILTER_DISTANCE_THRESHOLD', '50.0'))
FILTER_VISIBILITY_THRESHOLD = float(os.getenv('FILTER_VISIBILITY_THRESHOLD', '0.4'))

# 容错与监控
MAX_CONSECUTIVE_FAILURES = int(os.getenv('MAX_CONSECUTIVE_FAILURES', '10'))  # 连续失败熔断阈值
CHECKPOINT_INTERVAL = int(os.getenv('CHECKPOINT_INTERVAL', '10'))  # 每N帧保存一次checkpoint
ENABLE_PROGRESS_BAR = os.getenv('ENABLE_PROGRESS_BAR', 'true').lower() == 'true'
```

---

## 模块12: 错误处理与容错机制

### 12.1 LLM调用重试包装器
**函数**: `llm_call_with_retry(prompt: str, llm_client, max_retries: int, retry_delay: int) -> dict`
- **输入**: 
  - `prompt`: 提示词
  - `llm_client`: LLM客户端
  - `max_retries`: 最大重试次数
  - `retry_delay`: 重试延迟（秒）
- **输出**: `dict` - LLM响应
  ```python
  {
      'success': bool,
      'response': str or None,
      'error': str or None,
      'retries': int,
      'elapsed_ms': float
  }
  ```
- **功能**: 
  - 实现指数退避重试策略
  - 处理rate limit、timeout、connection error
  - 记录重试历史

### 12.2 Neo4j查询重试包装器
**函数**: `neo4j_query_with_retry(cypher: str, neo4j_conn, max_retries: int) -> dict`
- **输入**: 
  - `cypher`: Cypher查询
  - `neo4j_conn`: Neo4j连接
  - `max_retries`: 最大重试次数
- **输出**: `dict` - 查询结果
  ```python
  {
      'success': bool,
      'results': list or None,
      'error': str or None,
      'retries': int
  }
  ```
- **功能**: 
  - 处理连接断开、超时、死锁
  - 自动重连机制
  - 事务回滚

### 12.3 批处理失败处理
**函数**: `handle_batch_partial_failure(batch_results: list, batch_data: list) -> dict`
- **输入**: 
  - `batch_results`: 批处理结果列表
  - `batch_data`: 原始批数据
- **输出**: `dict` - 处理结果
  ```python
  {
      'success_count': int,
      'failure_count': int,
      'failed_items': list,       # 失败的项
      'retry_queue': list         # 需要重试的项
  }
  ```
- **功能**: 
  - 识别批处理中的失败项
  - 将失败项加入重试队列
  - 记录失败原因

### 12.4 连续失败熔断器
**函数**: `check_circuit_breaker(consecutive_failures: int, threshold: int) -> bool`
- **输入**: 
  - `consecutive_failures`: 连续失败次数
  - `threshold`: 熔断阈值
- **输出**: `bool` - 是否应该熔断
- **功能**: 
  - 当连续失败超过阈值时触发熔断
  - 防止无效重试浪费资源
  - 记录熔断事件

---

## 模块13: 断点续传与状态恢复

### 13.1 保存Checkpoint
**函数**: `save_checkpoint(checkpoint_data: dict, checkpoint_dir: str) -> bool`
- **输入**: 
  - `checkpoint_data`: checkpoint数据
  - `checkpoint_dir`: checkpoint目录
- **输出**: `bool` - 是否成功
- **Checkpoint格式**:
  ```python
  {
      'timestamp': str,
      'current_frame_index': int,     # 当前处理到第几帧
      'scene_id': str,
      'frame_id': int,
      'completed_frames': list,       # 已完成的帧列表
      'partial_frame': {              # 部分完成的帧信息
          'scene_id': str,
          'frame_id': int,
          'baseline_done': bool,
          'generated_count': int
      },
      'total_questions': int,
      'total_time_s': float
  }
  ```
- **功能**: 定期保存处理进度，支持断点续传

### 13.2 加载Checkpoint
**函数**: `load_checkpoint(checkpoint_dir: str) -> dict or None`
- **输入**: 
  - `checkpoint_dir`: checkpoint目录
- **输出**: `dict or None` - checkpoint数据（同13.1格式）
- **功能**: 
  - 读取最新的checkpoint
  - 验证checkpoint完整性
  - 返回恢复点信息

### 13.3 检查帧是否已完成
**函数**: `is_frame_already_completed(scene_id: str, frame_id: int, checkpoint_data: dict) -> bool`
- **输入**: 
  - `scene_id`: 场景ID
  - `frame_id`: 帧ID
  - `checkpoint_data`: checkpoint数据
- **输出**: `bool` - 是否已完成
- **功能**: 跳过已完成的帧，避免重复处理

### 13.4 恢复部分完成的帧
**函数**: `resume_partial_frame(partial_frame_info: dict, config: dict) -> dict`
- **输入**: 
  - `partial_frame_info`: 部分完成的帧信息
  - `config`: 配置字典
- **输出**: `dict` - 恢复结果
- **功能**: 
  - 从部分完成状态继续处理
  - 跳过已完成的baseline分析
  - 继续gap生成

---

## 模块14: 日志与监控

### 14.1 结构化日志记录器
**函数**: `setup_logger(log_dir: str, log_level: str) -> logging.Logger`
- **输入**: 
  - `log_dir`: 日志目录
  - `log_level`: 日志级别
- **输出**: `logging.Logger` - 日志记录器
- **日志格式**:
  ```
  [2026-04-19 10:30:45.123] [INFO] [module_name] message key1=value1 key2=value2
  ```
- **功能**: 
  - 结构化日志便于分析
  - 按日期轮转日志文件
  - 同时输出到文件和控制台

### 14.2 进度监控
**函数**: `update_progress(current: int, total: int, start_time: float, logger) -> dict`
- **输入**: 
  - `current`: 当前进度
  - `total`: 总数
  - `start_time`: 开始时间
  - `logger`: 日志记录器
- **输出**: `dict` - 进度信息
  ```python
  {
      'percentage': float,        # 完成百分比
      'elapsed_s': float,         # 已用时间
      'eta_s': float,             # 预计剩余时间
      'speed': float              # 处理速度（帧/秒）
  }
  ```
- **功能**: 
  - 实时显示进度百分比
  - 预估剩余时间
  - 计算处理速度

### 14.3 性能指标收集
**函数**: `collect_performance_metrics(frame_result: dict) -> dict`
- **输入**: 
  - `frame_result`: 帧处理结果
- **输出**: `dict` - 性能指标
  ```python
  {
      'llm_avg_time_ms': float,
      'neo4j_avg_time_ms': float,
      'questions_per_second': float,
      'memory_usage_mb': float
  }
  ```
- **功能**: 收集关键性能指标，便于优化

### 14.4 异常事件记录
**函数**: `log_exception(exception: Exception, context: dict, logger) -> None`
- **输入**: 
  - `exception`: 异常对象
  - `context`: 上下文信息
  - `logger`: 日志记录器
- **输出**: 无
- **功能**: 
  - 记录完整的异常堆栈
  - 记录异常发生时的上下文
  - 便于问题诊断

---

## 模块15: 数据一致性保障

### 15.1 原子写入包装器
**函数**: `atomic_write(file_path: str, content: str) -> bool`
- **输入**: 
  - `file_path`: 文件路径
  - `content`: 文件内容
- **输出**: `bool` - 是否成功
- **功能**: 
  - 先写入临时文件
  - 写入成功后原子性重命名
  - 防止写入中断导致文件损坏

### 15.2 数据完整性校验
**函数**: `verify_data_integrity(gap_json_path: str, csv_path: str) -> dict`
- **输入**: 
  - `gap_json_path`: gap JSON路径
  - `csv_path`: CSV路径
- **输出**: `dict` - 校验结果
  ```python
  {
      'consistent': bool,
      'gap_json_valid': bool,
      'csv_valid': bool,
      'mismatches': list          # 不一致的项
  }
  ```
- **功能**: 
  - 校验JSON和CSV数据一致性
  - 检测数据损坏
  - 生成修复建议

### 15.3 事务性更新
**函数**: `transactional_update(gap_json_path: str, csv_path: str, qa_records: list) -> bool`
- **输入**: 
  - `gap_json_path`: gap JSON路径
  - `csv_path`: CSV路径
  - `qa_records`: 问答记录列表
- **输出**: `bool` - 是否成功
- **功能**: 
  - 同时更新JSON和CSV
  - 任一失败则全部回滚
  - 保证数据一致性

---

## 模块16: 边界情况处理

### 16.1 处理小节点帧
**函数**: `handle_small_node_frame(scene_id: str, frame_id: int, node_count: int, config: dict) -> dict`
- **输入**: 
  - `scene_id`: 场景ID
  - `frame_id`: 帧ID
  - `node_count`: 节点数
  - `config`: 配置字典
- **输出**: `dict` - 处理结果
- **功能**: 
  - 节点数<2时跳过
  - 节点数=2时只生成L0/L1
  - 记录跳过原因

### 16.2 处理大节点帧L2B完全覆盖
**函数**: `handle_large_node_frame_l2b(scene_id: str, frame_id: int, node_count: int, gap_state: dict) -> dict`
- **输入**: 
  - `scene_id`: 场景ID
  - `frame_id`: 帧ID
  - `node_count`: 节点数
  - `gap_state`: 缺口状态
- **输出**: `dict` - 处理策略
  ```python
  {
      'l2b_theory': int,          # L2B理论值 = (n-1)*(n-1)*(n-2)
      'strategy': str,            # 'complete_coverage' (完全覆盖)
      'estimated_questions': int, # 预估需要生成的题数
      'estimated_time_hours': float # 预估耗时（小时）
  }
  ```
- **功能**: 
  - 不设置任何上限
  - 完全枚举所有L2B路径
  - 不计代价完成100%覆盖
  - 例如：44节点帧，L2B理论值 = 43*43*42 = 77,658
  - 预估时间并记录日志，但不中断流程

### 16.3 处理无法生成问题的gap
**函数**: `handle_ungenerable_gap(gap: dict, reason: str, logger) -> None`
- **输入**: 
  - `gap`: gap信息
  - `reason`: 无法生成的原因
  - `logger`: 日志记录器
- **输出**: 无
- **功能**: 
  - 记录无法生成的gap
  - 标记为已尝试
  - 避免重复尝试

---

## 模块17: 配置管理

### 17.1 加载筛选规则配置
**函数**: `load_filter_rules(config_path: str) -> dict`
- **输入**: 
  - `config_path`: 配置文件路径
- **输出**: `dict` - 筛选规则
  ```python
  {
      'distance_threshold': float,
      'visibility_threshold': float,
      'min_points': int,
      'allowed_types': list
  }
  ```
- **功能**: 从配置文件加载筛选规则

### 17.2 加载约束策略配置
**函数**: `load_constraint_strategies(config_path: str) -> list`
- **输入**: 
  - `config_path`: 配置文件路径
- **输出**: `list` - 约束策略列表
  ```python
  [
      {'type': 'direction', 'priority': 1},
      {'type': 'distance', 'priority': 2},
      {'type': 'type', 'priority': 3},
      ...
  ]
  ```
- **功能**: 加载约束策略及优先级

### 17.3 热更新配置
**函数**: `reload_config_if_changed(config_path: str, last_mtime: float) -> tuple`
- **输入**: 
  - `config_path`: 配置文件路径
  - `last_mtime`: 上次修改时间
- **输出**: `tuple` - (新配置, 新修改时间)
- **功能**: 
  - 检测配置文件变化
  - 热更新配置无需重启
  - 记录配置变更历史

---

## 模块18: 测试与验证

### 18.1 场景图正确性验证
**函数**: `validate_scene_graph(scene_graph: dict) -> dict`
- **输入**: 
  - `scene_graph`: 场景图
- **输出**: `dict` - 验证结果
  ```python
  {
      'valid': bool,
      'node_count_match': bool,   # 节点数是否匹配
      'edge_count_match': bool,   # 边数是否匹配（完全图）
      'errors': list
  }
  ```
- **功能**: 验证场景图是否为完全图

### 18.2 覆盖率计算验证
**函数**: `validate_coverage_calculation(gap_state: dict, node_count: int) -> dict`
- **输入**: 
  - `gap_state`: 缺口状态
  - `node_count`: 节点数
- **输出**: `dict` - 验证结果
  ```python
  {
      'valid': bool,
      'theory_match': bool,       # 理论值是否正确
      'coverage_sum_match': bool, # 覆盖数是否合理
      'errors': list
  }
  ```
- **功能**: 验证覆盖率计算公式正确性

### 18.3 生成问题质量检查
**函数**: `validate_generated_question(question: str, answer: str, gap: dict) -> dict`
- **输入**: 
  - `question`: 生成的问题
  - `answer`: 答案
  - `gap`: 原始gap
- **输出**: `dict` - 质量评估
  ```python
  {
      'valid': bool,
      'answer_matches_gap': bool,
      'question_well_formed': bool,
      'issues': list
  }
  ```
- **功能**: 
  - 检查答案是否匹配gap
  - 检查问题语法正确性
  - 检查问题可回答性

