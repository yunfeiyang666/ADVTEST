# 覆盖率驱动问题生成闭环模块

## 概述

该模块实现了**覆盖率驱动的问题生成闭环**，自动化完成：

1. **计算覆盖率** - 分析当前问题集的L0/L1/L2覆盖率
2. **识别缺口** - 找出低覆盖/未覆盖的节点、边、方向
3. **生成问题** - 针对性生成问题填补覆盖缺口
4. **验证答案** - (可选) 使用VQA Pipeline验证答案正确性
5. **更新统计** - 更新覆盖率，判断是否达标
6. **循环迭代** - 未达标则继续，直到满足目标或达到最大迭代次数

## 快速开始

```bash
cd e:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline

# 运行默认配置
python -m coverage_loop.run_loop

# 指定场景图
python -m coverage_loop.run_loop --scene-graph output/scene_graphs/scene-0103_frame25_scene_graph.json

# 自定义参数
python -m coverage_loop.loop_controller \
    --scene-graph output/scene_graphs/scene-0103_frame25_scene_graph.json \
    --output coverage_loop/output/my_test \
    --target-l0 0.8 \
    --max-iterations 10
```

## 模块结构

```
coverage_loop/
├── __init__.py              # 模块导出
├── unified_coverage.py      # 统一覆盖率数据结构
├── loop_controller.py       # 闭环控制器
├── run_loop.py              # 快速启动脚本
├── README.md                # 本文档
└── output/                  # 输出目录
    └── loop_results/
```

## 核心类

### UnifiedCoverageStats

统一的覆盖率数据结构，兼容`coverage_pipeline`和`qa_generator_v2`的格式。

```python
from coverage_loop import UnifiedCoverageStats

stats = UnifiedCoverageStats()
stats.scene_name = "scene-0103"
stats.frame_idx = 25

# 添加覆盖
stats.add_node_coverage("car1")
stats.add_edge_coverage("ego", "front", "car1")
stats.add_direction_coverage("front")

# 获取覆盖率
rates = stats.get_coverage_rates()
print(f"L0: {rates['L0']:.1%}, L1: {rates['L1']:.1%}")

# 保存/加载
stats.save("coverage.json")
loaded = UnifiedCoverageStats.load("coverage.json")
```

### CoverageAdapter

格式适配器，在不同Pipeline的覆盖率格式之间转换。

```python
from coverage_loop import CoverageAdapter

# 从coverage_pipeline结果转换
stats = CoverageAdapter.from_coverage_pipeline_result(result)

# 从qa_generator_v2格式转换
stats = CoverageAdapter.from_qa_generator_coverage(coverage, scene_data)

# 转换回qa_generator格式
qa_format = CoverageAdapter.to_qa_generator_format(stats)
```

### CoverageLoopController

闭环控制器，协调三个Pipeline完成闭环。

```python
from coverage_loop import CoverageLoopController
from coverage_loop.loop_controller import LoopConfig

config = LoopConfig(
    target_l0_coverage=0.80,    # L0目标80%
    target_l1_coverage=0.50,    # L1目标50%
    max_iterations=10,          # 最多迭代10次
    questions_per_iteration=20, # 每次生成20题
    verify_answers=True,        # 开启VQA验证
)

controller = CoverageLoopController(config)
result = controller.run(
    scene_graph_path="path/to/scene_graph.json",
    output_dir="output/loop_results",
)

print(f"生成问题: {result['total_questions']}")
print(f"最终覆盖率: {result['final_coverage']}")
```

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `target_l0_coverage` | 0.80 | L0节点覆盖率目标 |
| `target_l1_coverage` | 0.50 | L1边覆盖率目标 |
| `max_iterations` | 10 | 最大迭代次数 |
| `questions_per_iteration` | 20 | 每次迭代生成的问题数 |
| `min_coverage_gain` | 0.02 | 最小覆盖率增益(低于此值停止) |
| `verify_answers` | True | 是否使用VQA验证答案 |
| `save_intermediate` | True | 是否保存中间结果 |

## 输出文件

运行完成后，输出目录包含：

```
output/loop_results/
├── all_questions_YYYYMMDD_HHMMSS.json    # 所有生成的问题
├── coverage_final_YYYYMMDD_HHMMSS.json   # 最终覆盖率统计
├── iteration_history_YYYYMMDD_HHMMSS.json # 迭代历史
├── report_YYYYMMDD_HHMMSS.txt            # 文本报告
├── iteration_01.json                      # 第1轮迭代结果
├── iteration_02.json                      # 第2轮迭代结果
└── ...
```

## 与现有Pipeline的集成

该模块设计为与现有代码无缝集成：

```
┌─────────────────────────────────────────────────────────────────┐
│                    CoverageLoopController                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────┐    ┌──────────────────────┐          │
│  │ coverage_evaluation/ │    │ qa_generator_v2/     │          │
│  │ coverage_pipeline.py │◄──►│ coverage_driven_     │          │
│  │                      │    │ generator.py         │          │
│  └──────────────────────┘    └──────────────────────┘          │
│            │                           │                        │
│            │    UnifiedCoverageStats   │                        │
│            └───────────┬───────────────┘                        │
│                        │                                        │
│                        ▼                                        │
│               ┌──────────────────┐                              │
│               │ vqa_pipeline/    │                              │
│               │ pipeline.py      │                              │
│               │ (答案验证)       │                              │
│               └──────────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

## 注意事项

1. **Neo4j需要运行**: 覆盖率计算和VQA验证都需要Neo4j
2. **LLM API需要配置**: QA生成需要有效的DeepSeek API配置
3. **首次运行建议关闭验证**: 使用`verify_answers=False`加快测试
4. **场景图格式**: 需要包含`nodes`和`edges`字段

## 版本

- **v1.0** - 2026-02-12 - 初始版本
