# NuScenes S3C实验项目

## 项目目标
使用S3C方法分析NuScenes数据集的场景覆盖率和多样性

## 项目结构
```
nuscenes_s3c_experiment/
├── README.md                    # 项目说明
├── requirements.txt             # 依赖包
├── config.py                    # 配置文件
├── step1_data_loading.py        # 步骤1: 数据加载
├── step2_scene_graph_generation.py  # 步骤2: 场景图生成
├── step3_s3c_clustering.py      # 步骤3: S3C聚类
├── step4_visualization.py       # 步骤4: 可视化分析
├── run_full_experiment.py       # 完整实验运行脚本
├── utils/                       # 工具函数
│   ├── __init__.py
│   ├── predicates.py           # 谓词评估
│   ├── graph_utils.py          # 图操作
│   └── visualization.py        # 可视化工具
└── output/                      # 输出结果
    ├── scene_graphs/           # 场景图数据
    ├── clusters/               # 聚类结果
    ├── statistics/             # 统计数据
    └── figures/                # 可视化图表
```

## 实验步骤
1. 数据加载：从NuScenes提取场景信息
2. 场景图生成：转换为S3C场景图
3. S3C聚类：抽象化和图同构聚类
4. 可视化分析：生成统计图表

## 预期成果
- 404个场景的完整场景图
- 聚类分布统计
- 与CARLA数据的对比分析
- 长尾场景识别
