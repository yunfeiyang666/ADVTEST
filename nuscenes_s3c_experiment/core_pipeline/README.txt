==========================================
NuScenes VQA 核心执行代码集 (Ego Frame)
==========================================

【执行顺序】
1. python generate_selected_scenes.py    # 生成场景图
2. python import_single_scene_to_neo4j.py # 导入Neo4j
3. python run_official_qa_enhanced.py     # 运行测试

【核心文件】
├── config.py                      (全局配置)
├── generate_selected_scenes.py    (场景图生成)
├── import_single_scene_to_neo4j.py(Neo4j导入)
├── run_official_qa_enhanced.py    (VQA测试+Retry)
└── vqa_pipeline/                  (核心模块)
    ├── direction_utils.py         ⭐ 方向计算(Ego Frame)
    ├── pipeline.py                (主流程)
    ├── llm_client.py              (LLM调用)
    ├── neo4j_client.py            (Neo4j客户端)
    ├── question_normalizer.py     (问题规范化)
    ├── answer_formatter.py        (答案格式化)
    ├── status_inference.py        (状态推断)
    ├── ir_patterns.py             (IR模式)
    ├── ir_to_cypher.py            (IR转Cypher)
    └── config.py                  (Pipeline配置)

【关键算法】
方向计算: relative_angle = global_angle - ego_heading
所有方向基于Ego车视角(符合驾驶直觉)

【版本】v2.0 - Ego Frame
