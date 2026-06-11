"""
统一的覆盖率数据结构

整合 coverage_pipeline 和 qa_generator_v2 的覆盖率格式，
提供统一的接口供闭环控制器使用。
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Set, Tuple, Optional, Any
from pathlib import Path
from collections import defaultdict


@dataclass
class UnifiedCoverageStats:
    """
    统一的覆盖率统计数据结构
    
    整合了两种需求:
    1. coverage_pipeline 的 Set-based 覆盖 (哪些被覆盖了)
    2. qa_generator_v2 的 Count-based 覆盖 (每个被覆盖了多少次)
    """
    
    # 场景信息
    scene_name: str = ""
    frame_idx: int = 0
    
    # === L0: 节点覆盖 ===
    total_nodes: int = 0
    covered_nodes: Set[str] = field(default_factory=set)
    node_coverage_count: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # === L1: 边覆盖 (关系边 + 属性边) ===
    total_edges: int = 0
    covered_edges: Set[Tuple[str, str, str]] = field(default_factory=set)  # (source, direction, target)
    edge_coverage_count: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # === L2: 两跳路径覆盖 ===
    total_2hop_paths: int = 0
    covered_2hop_paths: Set[Tuple[str, str, str]] = field(default_factory=set)  # (node1, node2, node3)
    
    # === 方向覆盖 ===
    direction_coverage: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # === 问题统计 ===
    total_questions: int = 0
    verified_questions: int = 0  # 经过VQA验证的问题数
    failed_questions: int = 0
    
    # === 低覆盖追踪 ===
    low_coverage_threshold: int = 2  # 覆盖次数<2视为低覆盖
    
    def get_coverage_rates(self) -> Dict[str, float]:
        """获取覆盖率 (0.0 ~ 1.0)"""
        return {
            'L0': len(self.covered_nodes) / max(self.total_nodes, 1),
            'L1': len(self.covered_edges) / max(self.total_edges, 1),
            'L2': len(self.covered_2hop_paths) / max(self.total_2hop_paths, 1),
        }
    
    def get_coverage_percentages(self) -> Dict[str, str]:
        """获取覆盖率百分比字符串"""
        rates = self.get_coverage_rates()
        return {k: f"{v*100:.1f}%" for k, v in rates.items()}
    
    def get_low_coverage_nodes(self) -> List[str]:
        """获取低覆盖节点列表"""
        low_cov = []
        for node_id in self.covered_nodes:
            if self.node_coverage_count[node_id] < self.low_coverage_threshold:
                low_cov.append(node_id)
        # 也包括完全未覆盖的节点
        # (需要从外部提供全量节点列表)
        return sorted(low_cov)
    
    def get_uncovered_nodes(self, all_nodes: Set[str]) -> List[str]:
        """获取未覆盖节点"""
        return sorted(all_nodes - self.covered_nodes - {'ego'})
    
    def get_low_coverage_edges(self) -> List[str]:
        """获取低覆盖边列表"""
        low_cov = []
        for edge_key, count in self.edge_coverage_count.items():
            if count < self.low_coverage_threshold:
                low_cov.append(edge_key)
        return sorted(low_cov)
    
    def add_node_coverage(self, node_id: str):
        """添加节点覆盖"""
        if node_id and node_id != 'ego':
            self.covered_nodes.add(node_id)
            self.node_coverage_count[node_id] += 1
    
    def add_edge_coverage(self, source: str, direction: str, target: str):
        """添加边覆盖"""
        if source and target:
            edge = (source, direction, target)
            self.covered_edges.add(edge)
            edge_key = f"{source}-{direction}->{target}"
            self.edge_coverage_count[edge_key] += 1
    
    def add_direction_coverage(self, direction: str):
        """添加方向覆盖"""
        if direction:
            self.direction_coverage[direction] += 1
    
    def add_2hop_path_coverage(self, node1: str, node2: str, node3: str):
        """添加两跳路径覆盖"""
        if node1 and node2 and node3:
            path = (node1, node2, node3)
            self.covered_2hop_paths.add(path)
    
    def merge_from_question(self, question_coverage: Dict):
        """
        从单个问题的覆盖分析结果合并
        
        question_coverage格式:
        {
            'nodes': ['car1', 'pedestrian2'],
            'edges': [('ego', 'front', 'car1')],
            'directions': ['front', 'left'],
            '2hop_paths': [('ego', 'car1', 'pedestrian2')]
        }
        """
        for node_id in question_coverage.get('nodes', []):
            self.add_node_coverage(node_id)
        
        for edge in question_coverage.get('edges', []):
            if len(edge) == 3:
                self.add_edge_coverage(edge[0], edge[1], edge[2])
            elif len(edge) == 2:
                self.add_edge_coverage(edge[0], '', edge[1])
        
        for direction in question_coverage.get('directions', []):
            self.add_direction_coverage(direction)
        
        for path in question_coverage.get('2hop_paths', []):
            if len(path) == 3:
                self.add_2hop_path_coverage(path[0], path[1], path[2])
    
    def to_dict(self) -> Dict:
        """转换为可JSON序列化的字典"""
        rates = self.get_coverage_rates()
        return {
            'scene_name': self.scene_name,
            'frame_idx': self.frame_idx,
            'totals': {
                'nodes': self.total_nodes,
                'edges': self.total_edges,
                '2hop_paths': self.total_2hop_paths,
            },
            'coverage': {
                'L0': {
                    'covered': len(self.covered_nodes),
                    'total': self.total_nodes,
                    'rate': rates['L0'],
                    'nodes': sorted(self.covered_nodes),
                },
                'L1': {
                    'covered': len(self.covered_edges),
                    'total': self.total_edges,
                    'rate': rates['L1'],
                },
                'L2': {
                    'covered': len(self.covered_2hop_paths),
                    'total': self.total_2hop_paths,
                    'rate': rates['L2'],
                },
            },
            'node_coverage_count': dict(self.node_coverage_count),
            'edge_coverage_count': dict(self.edge_coverage_count),
            'direction_coverage': dict(self.direction_coverage),
            'questions': {
                'total': self.total_questions,
                'verified': self.verified_questions,
                'failed': self.failed_questions,
            },
        }
    
    def save(self, path: str):
        """保存到JSON文件"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: str) -> 'UnifiedCoverageStats':
        """从JSON文件加载"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        stats = cls()
        stats.scene_name = data.get('scene_name', '')
        stats.frame_idx = data.get('frame_idx', 0)
        
        totals = data.get('totals', {})
        stats.total_nodes = totals.get('nodes', 0)
        stats.total_edges = totals.get('edges', 0)
        stats.total_2hop_paths = totals.get('2hop_paths', 0)
        
        coverage = data.get('coverage', {})
        if 'L0' in coverage:
            stats.covered_nodes = set(coverage['L0'].get('nodes', []))
        if 'L1' in coverage:
            # 从 edge_coverage_count 恢复 covered_edges
            for edge_key, count in data.get('edge_coverage_count', {}).items():
                if count > 0:
                    parts = edge_key.replace('->', '-').split('-')
                    if len(parts) >= 3:
                        stats.covered_edges.add((parts[0], parts[1], parts[-1]))
        
        stats.node_coverage_count = defaultdict(int, data.get('node_coverage_count', {}))
        stats.edge_coverage_count = defaultdict(int, data.get('edge_coverage_count', {}))
        stats.direction_coverage = defaultdict(int, data.get('direction_coverage', {}))
        
        questions = data.get('questions', {})
        stats.total_questions = questions.get('total', 0)
        stats.verified_questions = questions.get('verified', 0)
        stats.failed_questions = questions.get('failed', 0)
        
        return stats


class CoverageAdapter:
    """
    覆盖率格式适配器
    
    将不同Pipeline的覆盖率格式转换为UnifiedCoverageStats
    """
    
    @staticmethod
    def from_coverage_pipeline_result(result: Dict) -> UnifiedCoverageStats:
        """
        从coverage_pipeline.py的输出结果转换
        
        输入格式 (coverage_pipeline输出):
        {
            'scene': {'name': 'scene-0103', 'frame_idx': 25},
            'totals': {'nodes': 48, 'edges': 1122, '2hop': 5000},
            'coverage': {
                'L0': {'covered': 20, 'total': 48, 'rate': 0.416, 'nodes': [...]},
                'L1': {'covered': 100, 'total': 1122, 'rate': 0.089},
                'L2': {'covered': 50, 'total': 5000, 'rate': 0.01}
            },
            'details': [...]
        }
        """
        stats = UnifiedCoverageStats()
        
        scene = result.get('scene', {})
        stats.scene_name = scene.get('name', '')
        stats.frame_idx = scene.get('frame_idx', 0)
        
        totals = result.get('totals', {})
        stats.total_nodes = totals.get('nodes', 0)
        stats.total_edges = totals.get('edges', totals.get('total_edges', 0))
        stats.total_2hop_paths = totals.get('2hop', totals.get('2hop_paths', 0))
        
        coverage = result.get('coverage', {})
        
        # L0 节点
        l0 = coverage.get('L0', {})
        stats.covered_nodes = set(l0.get('nodes', []))
        for node_id in stats.covered_nodes:
            stats.node_coverage_count[node_id] = 1  # 至少覆盖1次
        
        # 从details提取更详细的覆盖信息
        for detail in result.get('details', []):
            for node_id in detail.get('covered_nodes', []):
                stats.add_node_coverage(node_id)
            for edge in detail.get('covered_edges', []):
                if len(edge) >= 2:
                    src, tgt = edge[0], edge[-1]
                    direction = edge[1] if len(edge) == 3 else ''
                    stats.add_edge_coverage(src, direction, tgt)
            for path in detail.get('covered_2hop_paths', []):
                if len(path) == 3:
                    stats.add_2hop_path_coverage(path[0], path[1], path[2])
        
        questions = result.get('questions', {})
        stats.total_questions = questions.get('total', 0)
        stats.verified_questions = questions.get('analyzed', 0)
        stats.failed_questions = questions.get('failed', 0)
        
        return stats
    
    @staticmethod
    def from_qa_generator_coverage(coverage: Dict, scene_data: Dict = None) -> UnifiedCoverageStats:
        """
        从qa_generator_v2的覆盖率分析转换
        
        输入格式 (integrated_pipeline输出):
        {
            'scene_name': 'scene-0103',
            'frame_idx': 25,
            'object_coverage': {'car1': 3, 'pedestrian2': 1, ...},
            'relation_coverage': {'ego-front->car1': 2, ...},
            'direction_coverage': {'front': 10, 'left': 5, ...}
        }
        """
        stats = UnifiedCoverageStats()
        
        stats.scene_name = coverage.get('scene_name', '')
        stats.frame_idx = coverage.get('frame_idx', 0)
        
        # 对象覆盖
        obj_cov = coverage.get('object_coverage', {})
        for obj_id, count in obj_cov.items():
            if count > 0:
                stats.covered_nodes.add(obj_id)
            stats.node_coverage_count[obj_id] = count
        
        # 关系覆盖
        rel_cov = coverage.get('relation_coverage', {})
        for rel_key, count in rel_cov.items():
            stats.edge_coverage_count[rel_key] = count
            if count > 0:
                # 解析 "ego-front->car1" 格式
                parts = rel_key.replace('->', '-').split('-')
                if len(parts) >= 3:
                    src, direction, tgt = parts[0], parts[1], parts[-1]
                    stats.covered_edges.add((src, direction, tgt))
        
        # 方向覆盖
        dir_cov = coverage.get('direction_coverage', {})
        for direction, count in dir_cov.items():
            stats.direction_coverage[direction] = count
        
        # 从场景图补充总数
        if scene_data:
            nodes = scene_data.get('nodes', [])
            edges = scene_data.get('edges', [])
            stats.total_nodes = len([n for n in nodes if n.get('unique_id', n.get('id')) != 'ego'])
            stats.total_edges = len(edges)
        
        return stats
    
    @staticmethod
    def to_qa_generator_format(stats: UnifiedCoverageStats) -> Dict:
        """
        转换为qa_generator_v2需要的格式
        """
        return {
            'scene_name': stats.scene_name,
            'frame_idx': stats.frame_idx,
            'object_coverage': dict(stats.node_coverage_count),
            'relation_coverage': dict(stats.edge_coverage_count),
            'direction_coverage': dict(stats.direction_coverage),
            'pattern_coverage': {},
            'type_coverage': {},
        }
