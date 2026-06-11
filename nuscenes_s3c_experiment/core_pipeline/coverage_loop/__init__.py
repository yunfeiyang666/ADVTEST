"""
覆盖率驱动的问题生成闭环模块

核心组件:
- UnifiedCoverageStats: 统一的覆盖率数据结构
- CoverageLoopController: 闭环控制器
- CoverageAdapter: 适配现有Pipeline的覆盖率格式
- GapAnalyzer: 覆盖率缺口分析器
"""

from .unified_coverage import UnifiedCoverageStats, CoverageAdapter
from .loop_controller import CoverageLoopController
from .gap_analyzer import GapAnalyzer

__all__ = [
    'UnifiedCoverageStats',
    'CoverageAdapter', 
    'CoverageLoopController',
    'GapAnalyzer',
]
