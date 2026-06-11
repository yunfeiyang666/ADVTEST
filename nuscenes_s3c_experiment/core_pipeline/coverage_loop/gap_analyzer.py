"""
覆盖率缺口分析器

根据当前覆盖率数据，分析缺口并决定下一步生成什么难度/类型的问题
"""

import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
from pathlib import Path


@dataclass
class CoverageGap:
    """覆盖率缺口"""
    level: str           # L0, L1, L2
    gap_type: str        # uncovered, low_coverage
    items: List[str]     # 具体的节点/边/路径
    priority: float      # 优先级 (0-1, 越高越优先)
    suggested_count: int # 建议生成的问题数


class GapAnalyzer:
    """
    覆盖率缺口分析器
    
    分析当前覆盖率状态，决定下一步应该生成什么类型的问题
    """
    
    def __init__(self, scene_data: Dict):
        """
        Args:
            scene_data: 场景图数据
        """
        self.scene_data = scene_data
        self.nodes = {n.get('unique_id', n.get('id', '')): n 
                      for n in scene_data.get('nodes', [])}
        self.edges = scene_data.get('edges', [])
        
        # 构建边索引
        self._build_edge_index()
    
    def _build_edge_index(self):
        """构建边索引，便于查找"""
        self.edge_by_source = defaultdict(list)
        self.edge_by_target = defaultdict(list)
        self.edge_by_direction = defaultdict(list)
        
        for edge in self.edges:
            src = edge.get('source', '')
            tgt = edge.get('target', '')
            direction = self._get_direction(edge)
            
            self.edge_by_source[src].append(edge)
            self.edge_by_target[tgt].append(edge)
            if direction:
                self.edge_by_direction[direction].append(edge)
    
    def _get_direction(self, edge: Dict) -> str:
        """从边提取方向"""
        if 'predicates' in edge and isinstance(edge['predicates'], list):
            return edge['predicates'][0] if edge['predicates'] else ''
        if 'direction_8' in edge:
            return edge['direction_8']
        metrics = edge.get('metrics', {})
        if isinstance(metrics, dict):
            ds = metrics.get('direction_source', {})
            if isinstance(ds, dict):
                return ds.get('direction_8', '')
        return ''
    
    def analyze(self, coverage_stats) -> Dict[str, CoverageGap]:
        """
        分析覆盖率缺口
        
        Args:
            coverage_stats: UnifiedCoverageStats对象
        
        Returns:
            按优先级排序的缺口列表
        """
        gaps = {}
        
        # 1. 分析L0缺口（节点覆盖）
        l0_gap = self._analyze_l0_gap(coverage_stats)
        if l0_gap:
            gaps['L0'] = l0_gap
        
        # 2. 分析L1缺口（边覆盖）
        l1_gap = self._analyze_l1_gap(coverage_stats)
        if l1_gap:
            gaps['L1'] = l1_gap
        
        # 3. 分析L2缺口（两跳路径覆盖）
        l2_gap = self._analyze_l2_gap(coverage_stats)
        if l2_gap:
            gaps['L2'] = l2_gap
        
        return gaps
    
    def _analyze_l0_gap(self, stats) -> Optional[CoverageGap]:
        """分析L0节点覆盖缺口"""
        uncovered = []
        low_coverage = []
        
        for node_id, count in stats.node_coverage_count.items():
            if node_id == 'ego':
                continue
            if count == 0:
                uncovered.append(node_id)
            elif count < stats.low_coverage_threshold:
                low_coverage.append(node_id)
        
        if not uncovered and not low_coverage:
            return None
        
        # 计算优先级：未覆盖节点数 / 总节点数
        coverage_rate = len(stats.covered_nodes) / max(stats.total_nodes, 1)
        priority = 1.0 - coverage_rate
        
        return CoverageGap(
            level='L0',
            gap_type='uncovered' if uncovered else 'low_coverage',
            items=uncovered if uncovered else low_coverage,
            priority=priority,
            suggested_count=min(len(uncovered) + len(low_coverage), 20)
        )
    
    def _analyze_l1_gap(self, stats) -> Optional[CoverageGap]:
        """分析L1边覆盖缺口"""
        uncovered_edges = []
        low_coverage_edges = []
        
        for edge_key, count in stats.edge_coverage_count.items():
            if count == 0:
                uncovered_edges.append(edge_key)
            elif count < stats.low_coverage_threshold:
                low_coverage_edges.append(edge_key)
        
        # 分析方向覆盖
        uncovered_directions = []
        all_directions = ['front', 'front-left', 'left', 'back-left', 
                         'back', 'back-right', 'right', 'front-right']
        for direction in all_directions:
            if stats.direction_coverage.get(direction, 0) == 0:
                uncovered_directions.append(direction)
        
        if not uncovered_edges and not uncovered_directions:
            return None
        
        # 计算优先级
        coverage_rate = len(stats.covered_edges) / max(stats.total_edges, 1)
        priority = 1.0 - coverage_rate
        
        # 优先处理未覆盖的方向
        items = uncovered_directions[:4] if uncovered_directions else uncovered_edges[:20]
        
        return CoverageGap(
            level='L1',
            gap_type='uncovered_direction' if uncovered_directions else 'uncovered_edge',
            items=items,
            priority=priority * 0.8,  # L1优先级略低于L0
            suggested_count=min(len(items), 15)
        )
    
    def _analyze_l2_gap(self, stats) -> Optional[CoverageGap]:
        """分析L2两跳路径覆盖缺口"""
        # L2覆盖率通常很低，需要生成涉及两个关系的问题
        coverage_rate = len(stats.covered_2hop_paths) / max(stats.total_2hop_paths, 1)
        
        if coverage_rate >= 0.01:  # 1%以上认为可以
            return None
        
        # 找出可以构成两跳路径的节点组合
        potential_paths = self._find_potential_2hop_paths()
        
        return CoverageGap(
            level='L2',
            gap_type='uncovered_2hop',
            items=potential_paths[:10],
            priority=0.5,  # L2优先级较低
            suggested_count=min(len(potential_paths), 10)
        )
    
    def _find_potential_2hop_paths(self) -> List[str]:
        """找出可以构成两跳路径的节点组合"""
        paths = []
        
        # 从ego出发的两跳路径
        ego_edges = self.edge_by_source.get('ego', [])
        for edge1 in ego_edges[:10]:
            mid_node = edge1.get('target', '')
            if mid_node and mid_node != 'ego':
                mid_edges = self.edge_by_source.get(mid_node, [])
                for edge2 in mid_edges[:5]:
                    end_node = edge2.get('target', '')
                    if end_node and end_node not in ['ego', mid_node]:
                        path = f"ego->{mid_node}->{end_node}"
                        paths.append(path)
        
        return paths
    
    def decide_next_generation(self, coverage_stats, 
                               target_l0: float = 0.8,
                               target_l1: float = 0.5,
                               target_l2: float = 0.1) -> Dict:
        """
        决定下一步应该生成什么类型的问题
        
        Args:
            coverage_stats: 当前覆盖率统计
            target_l0: L0目标覆盖率
            target_l1: L1目标覆盖率
            target_l2: L2目标覆盖率
        
        Returns:
            生成策略字典
        """
        rates = coverage_stats.get_coverage_rates()
        gaps = self.analyze(coverage_stats)
        
        # 计算各级别的差距
        l0_gap = target_l0 - rates['L0']
        l1_gap = target_l1 - rates['L1']
        l2_gap = target_l2 - rates['L2']
        
        strategy = {
            'current_rates': rates,
            'target_rates': {'L0': target_l0, 'L1': target_l1, 'L2': target_l2},
            'gaps': {'L0': l0_gap, 'L1': l1_gap, 'L2': l2_gap},
            'focus_level': None,
            'focus_items': [],
            'question_types': [],
            'suggested_count': 0,
            'reasoning': '',
        }
        
        # 决策逻辑：采用混合策略，按比例分配各级别问题
        # 避免只生成L0问题导致L1/L2覆盖率始终很低
        
        # 计算各级别的权重（基于差距大小）
        total_gap = max(l0_gap, 0) + max(l1_gap, 0) + max(l2_gap, 0)
        if total_gap == 0:
            total_gap = 1  # 避免除零
        
        l0_weight = max(l0_gap, 0) / total_gap
        l1_weight = max(l1_gap, 0) / total_gap
        l2_weight = max(l2_gap, 0) / total_gap
        
        # 混合策略：即使L0差距大，也分配部分问题给L1
        # 基础比例: L0占60%, L1占30%, L2占10%，然后根据差距调整
        if l0_gap > 0.2:  # L0差距很大时
            strategy['focus_level'] = 'mixed_l0_l1'
            l0_items = gaps.get('L0', CoverageGap('L0', '', [], 0, 0)).items[:10]
            l1_items = gaps.get('L1', CoverageGap('L1', '', [], 0, 0)).items[:5]
            strategy['focus_items'] = l0_items + l1_items
            strategy['question_types'] = ['exist', 'status', 'count', 'position', 'direction']
            strategy['suggested_count'] = 15
            strategy['reasoning'] = f"混合策略: L0({rates['L0']:.1%})需要提升，同时生成L1空间关系问题"
            strategy['level_distribution'] = {'L0': 10, 'L1': 5}
        
        elif l0_gap > 0.1:  # L0差距中等
            strategy['focus_level'] = 'mixed_balanced'
            l0_items = gaps.get('L0', CoverageGap('L0', '', [], 0, 0)).items[:7]
            l1_items = gaps.get('L1', CoverageGap('L1', '', [], 0, 0)).items[:7]
            strategy['focus_items'] = l0_items + l1_items
            strategy['question_types'] = ['exist', 'status', 'position', 'direction', 'relation']
            strategy['suggested_count'] = 14
            strategy['reasoning'] = f"平衡策略: L0({rates['L0']:.1%})/L1({rates['L1']:.1%})同步提升"
            strategy['level_distribution'] = {'L0': 7, 'L1': 7}
        
        elif l1_gap > 0.1:  # L0已接近目标，重点L1
            strategy['focus_level'] = 'L1'
            strategy['focus_items'] = gaps.get('L1', CoverageGap('L1', '', [], 0, 0)).items[:15]
            strategy['question_types'] = ['position', 'direction', 'relation', 'comparison']
            strategy['suggested_count'] = min(15, len(strategy['focus_items']))
            strategy['reasoning'] = f"L0已达标({rates['L0']:.1%})，重点提升L1覆盖率({rates['L1']:.1%})"
        
        elif l2_gap > 0.05:  # L2差距大于5%，补充L2
            strategy['focus_level'] = 'L2'
            strategy['focus_items'] = gaps.get('L2', CoverageGap('L2', '', [], 0, 0)).items[:10]
            strategy['question_types'] = ['chain', 'multi_hop', 'complex_relation']
            strategy['suggested_count'] = min(10, len(strategy['focus_items']))
            strategy['reasoning'] = f"L0/L1已达标，补充L2两跳路径覆盖({rates['L2']:.1%} -> {target_l2:.0%})"
        
        else:
            strategy['focus_level'] = 'balanced'
            strategy['question_types'] = ['mixed']
            strategy['suggested_count'] = 10
            strategy['reasoning'] = "所有级别已接近目标，生成混合难度问题保持平衡"
        
        return strategy
    
    def get_generation_prompt_hints(self, strategy: Dict) -> str:
        """
        根据策略生成给LLM的提示
        
        Args:
            strategy: decide_next_generation返回的策略
        
        Returns:
            给LLM的额外提示
        """
        focus_level = strategy['focus_level']
        items = strategy['focus_items']
        
        if focus_level == 'L0':
            return f"""
【生成要求】本轮重点提升L0节点覆盖率
- 目标对象: {', '.join(items[:10])}
- 问题类型: 存在性(exist)、状态(status)、计数(count)、属性(object)
- 难度级别: L0 (单节点问题)
- 示例: "What is the status of {items[0] if items else 'carX'}?"
"""
        
        elif focus_level == 'L1':
            return f"""
【生成要求】本轮重点提升L1边覆盖率（空间关系）
- 目标方向/关系: {', '.join(items[:8])}
- 问题类型: 位置(position)、方向(direction)、关系(relation)、比较(comparison)
- 难度级别: L1 (涉及空间关系)
- 必须包含方向词: front, left, right, back, front-left等
- 示例: "What is to the front-left of the ego vehicle?"
- 示例: "Is there a pedestrian to the right of car1?"
"""
        
        elif focus_level == 'L2':
            return f"""
【生成要求】本轮重点提升L2两跳路径覆盖率
- 目标路径: {', '.join(items[:5])}
- 问题类型: 链式推理(chain)、多跳(multi_hop)
- 难度级别: L2 (涉及两个空间关系)
- 示例: "What is the status of the car that is in front of the truck?"
- 示例: "Is the pedestrian to the left of car1 moving?"
"""
        
        elif focus_level in ['mixed_l0_l1', 'mixed_balanced']:
            level_dist = strategy.get('level_distribution', {'L0': 10, 'L1': 5})
            return f"""
【生成要求】本轮混合生成L0和L1问题
- L0问题数: {level_dist.get('L0', 10)}个（节点属性查询）
- L1问题数: {level_dist.get('L1', 5)}个（空间关系查询）

L0问题要求:
- 问题类型: 状态(status)、存在性(exist)、计数(count)
- 示例: "What is the status of car5?"

L1问题要求（重要！必须包含空间方向词）:
- 问题类型: 位置(position)、方向(direction)
- 必须包含方向词: front, left, right, back, front-left等
- 示例: "What is to the front of ego?"
- 示例: "Are there any cars to the left of ego?"
- 示例: "How many pedestrians are to the front-left of ego?"
"""
        
        else:
            return """
【生成要求】生成混合难度问题
- 包含L0/L1/L2各级别问题
- 保持问题多样性
"""


def print_gap_analysis(analyzer: GapAnalyzer, coverage_stats, 
                       target_l0=0.8, target_l1=0.5, target_l2=0.1):
    """打印缺口分析结果"""
    strategy = analyzer.decide_next_generation(
        coverage_stats, target_l0, target_l1, target_l2
    )
    
    print("\n" + "=" * 60)
    print("  覆盖率缺口分析")
    print("=" * 60)
    
    rates = strategy['current_rates']
    targets = strategy['target_rates']
    
    print(f"\n当前覆盖率 vs 目标:")
    print(f"  L0: {rates['L0']:.1%} / {targets['L0']:.0%} (差距: {strategy['gaps']['L0']:.1%})")
    print(f"  L1: {rates['L1']:.1%} / {targets['L1']:.0%} (差距: {strategy['gaps']['L1']:.1%})")
    print(f"  L2: {rates['L2']:.1%} / {targets['L2']:.0%} (差距: {strategy['gaps']['L2']:.1%})")
    
    print(f"\n决策:")
    print(f"  重点级别: {strategy['focus_level']}")
    print(f"  问题类型: {', '.join(strategy['question_types'])}")
    print(f"  建议数量: {strategy['suggested_count']}")
    print(f"  理由: {strategy['reasoning']}")
    
    if strategy['focus_items']:
        print(f"\n目标项目 (前10):")
        for item in strategy['focus_items'][:10]:
            print(f"  - {item}")
    
    return strategy
