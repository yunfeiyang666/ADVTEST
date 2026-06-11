# Coverage Evaluation 覆盖率评估模块

独立的覆盖率评估模块，与VQA正确率测试(`vqa_pipeline/`)分开维护。

## 统一标准

| 项目 | 设置 |
|------|------|
| **坐标系** | Ego Frame (以ego车辆为参照) |
| **方向匹配** | `angle_matches_ego` (宽松匹配) |
| **方向词表** | 8方向: front, front-left, left, back-left, back, back-right, right, front-right |

## 文件说明

- `calculate_coverage.py` - 精确L-Level覆盖率计算器
- `__init__.py` - 模块导出

## 使用方法

### 命令行

```bash
# 基本用法 (只分析答对的题目)
python calculate_coverage.py <vqa_results.json> <scene_graph.json>

# 分析所有题目
python calculate_coverage.py <vqa_results.json> <scene_graph.json> --all
```

### 作为模块导入

```python
from coverage_evaluation import calculate_coverage, CoverageStats

stats = calculate_coverage(
    vqa_results_path='path/to/vqa_results.json',
    scene_graph_path='path/to/scene_graph.json',
    only_correct=True  # 只分析答对的题目
)

# 获取覆盖率
rates = stats.get_coverage_rates()
print(f"L0节点覆盖率: {rates['L0']:.2%}")
print(f"L1边覆盖率: {rates['L1']:.2%}")
print(f"L2两跳路径覆盖率: {rates['L2']:.2%}")
```

## 覆盖率定义

- **L=0 节点覆盖率**: 涉及的唯一节点数 / 场景总节点数
- **L=1 边覆盖率**: 涉及的唯一边数 / 场景总边数  
- **L=2 两跳路径覆盖率**: 涉及的唯一两跳路径数 / 场景总两跳路径数

计算的是 "Query Scanning Coverage" (搜索空间覆盖)：
- 即为了得到答案，数据库需要扫描的所有节点/边/路径
- 不考虑 LIMIT/ORDER BY 等后处理

## 与 vqa_pipeline 的区别

| 模块 | 用途 | 方向匹配 |
|------|------|----------|
| `vqa_pipeline/` | VQA正确率测试 | `angle_matches_source` (可切换) |
| `coverage_evaluation/` | 覆盖率评估 | `angle_matches_ego` (固定) |

两个模块独立运行，互不干扰。
