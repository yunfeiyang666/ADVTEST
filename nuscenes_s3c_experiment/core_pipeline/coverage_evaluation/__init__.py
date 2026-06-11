"""
覆盖率评估模块 (独立于VQA正确率测试)

统一标准：
- 坐标系: Ego Frame (以ego车辆为参照)
- 方向匹配: angle_matches_ego (宽松匹配，8方向词表)

主要功能：
- calculate_coverage.py: 精确L-Level覆盖率计算
"""

from .calculate_coverage import (
    CoverageStats,
    SceneGraph,
    CypherQueryAnalyzer,
    calculate_coverage,
    calculate_coverage_single_scene,
    DIRECTION_FIELD,
    DIRECTIONS_8,
)

__all__ = [
    'CoverageStats',
    'SceneGraph', 
    'CypherQueryAnalyzer',
    'calculate_coverage',
    'calculate_coverage_single_scene',
    'DIRECTION_FIELD',
    'DIRECTIONS_8',
]
