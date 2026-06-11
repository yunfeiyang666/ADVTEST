# 两帧完整测试指南

## 完整流程

步骤1: 场景图生成 (从nuScenes原始数据)
步骤2: 场景图筛选 (应用官方筛选策略)
步骤3: 导入Neo4j
步骤4: 原题集分析 (Baseline审计)
步骤5: Gap检测
步骤6: 增量生成 (持续生成直到覆盖完成)
步骤7: 保存到Excel

## 执行命令

### 步骤1: 生成场景图
```bash
cd E:\Project\ADVTEST\DATA_new\code
python generate_two_frames_scene_graphs.py
```

输出: scene-0916_frame8_scene_graph.json, scene-0916_frame10_scene_graph.json

### 步骤2-7: 运行完整流程
```bash
python run_two_frames_complete.py
```

输出: RQ.xlsx (filter_record, raw_coverage, question-answer-our sheets)

## 前提条件

1. Neo4j运行中 (端口7687, 密码87017563)
2. nuScenes trainval数据集
3. RQ.xlsx存在且未锁定
4. LLM API配置正确

## 验证点

1. Mid节点具体化: 问题使用"car1"而不是"car"
2. is_unique比例: 60-80%
3. 覆盖完成: 所有L0/L1/L2 gap标记为covered
