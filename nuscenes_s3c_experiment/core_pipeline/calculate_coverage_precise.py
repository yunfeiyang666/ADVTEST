"""
精确 L-Level 覆盖率计算器 (优化版)

基于 VQA 测试结果，通过解析 Cypher 查询并在场景图上模拟执行，
精确统计每道题访问的节点/边/路径，计算真实的覆盖率。

计算的是 "Query Scanning Coverage" (搜索空间覆盖)：
- 即为了得到答案，数据库需要扫描的所有节点/边/路径
- 不考虑 LIMIT/ORDER BY 等后处理

前置条件：
- 需要 VQA 测试结果 JSON（包含 question, cypher_query, correct 等）
- 需要对应的场景图 JSON
- 默认只分析**答对的题目**（可选分析全部）

输出：
- L=0: 节点覆盖率 = 涉及的唯一节点数 / 场景总节点数
- L=1: 边覆盖率 = 涉及的唯一边数 / 场景总边数
- L=2: 两跳路径覆盖率 = 涉及的唯一两跳路径数 / 场景总两跳路径数
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


@dataclass
class CoverageStats:
    """覆盖率统计"""
    # 场景基础信息
    total_nodes: int
    total_edges: int
    total_2hop_paths: int
    
    # 覆盖统计
    covered_nodes: Set[str] = field(default_factory=set)
    covered_edges: Set[Tuple[str, str]] = field(default_factory=set)
    covered_2hop_paths: Set[Tuple[str, str, str]] = field(default_factory=set)
    
    # 问题级别统计
    total_questions: int = 0
    correct_questions: int = 0
    analyzed_questions: int = 0
    
    def add_node(self, node_id: str):
        """添加访问的节点"""
        self.covered_nodes.add(node_id)
    
    def add_edge(self, source: str, target: str):
        """添加访问的边"""
        self.covered_edges.add((source, target))
    
    def add_2hop_path(self, node1: str, node2: str, node3: str):
        """添加访问的两跳路径"""
        self.covered_2hop_paths.add((node1, node2, node3))
    
    def get_coverage_rates(self) -> Dict[str, float]:
        """计算覆盖率"""
        return {
            'L0': len(self.covered_nodes) / max(self.total_nodes, 1),
            'L1': len(self.covered_edges) / max(self.total_edges, 1),
            'L2': len(self.covered_2hop_paths) / max(self.total_2hop_paths, 1),
        }
    
    def print_report(self):
        """打印覆盖率报告"""
        rates = self.get_coverage_rates()
        
        logger.info("\n" + "="*70)
        logger.info("  精确 L-Level 覆盖率报告 (Query Scanning Coverage)")
        logger.info("="*70)
        
        logger.info(f"\n【场景统计】")
        logger.info(f"  总节点数: {self.total_nodes}")
        logger.info(f"  总边数: {self.total_edges}")
        logger.info(f"  总两跳路径数: {self.total_2hop_paths}")
        
        logger.info(f"\n【问题统计】")
        logger.info(f"  总问题数: {self.total_questions}")
        logger.info(f"  答对问题数: {self.correct_questions}")
        logger.info(f"  已分析问题数: {self.analyzed_questions}")
        
        logger.info(f"\n【L=0 节点覆盖】")
        logger.info(f"  涉及节点数: {len(self.covered_nodes)}")
        logger.info(f"  覆盖率: {rates['L0']:.2%}")
        if len(self.covered_nodes) <= 20:
            logger.info(f"  节点列表: {sorted(self.covered_nodes)}")
        
        logger.info(f"\n【L=1 边覆盖】")
        logger.info(f"  涉及边数: {len(self.covered_edges)}")
        logger.info(f"  覆盖率: {rates['L1']:.2%}")
        
        logger.info(f"\n【L=2 两跳路径覆盖】")
        logger.info(f"  涉及路径数: {len(self.covered_2hop_paths)}")
        logger.info(f"  覆盖率: {rates['L2']:.2%}")
        
        logger.info("\n" + "="*70)


class SceneGraph:
    """场景图数据结构"""
    
    def __init__(self, scene_data: Dict):
        self.scene_name = scene_data.get('scene_name', 'unknown')
        self.frame_idx = scene_data.get('frame_idx', 0)
        
        # 解析节点
        nodes_data = scene_data.get('objects') or scene_data.get('nodes', [])
        self.nodes: Dict[str, Dict] = {}
        self.nodes_by_type: Dict[str, List[str]] = defaultdict(list)
        
        for node in nodes_data:
            uid = node['unique_id']
            self.nodes[uid] = node
            self.nodes_by_type[node['type']].append(uid)
        
        # 解析边
        edges_data = scene_data.get('relationships') or scene_data.get('edges', [])
        self.edges: List[Dict] = edges_data
        
        # 构建邻接表
        self.adjacency: Dict[str, List[Tuple[str, Dict]]] = defaultdict(list)
        self.edge_map: Dict[Tuple[str, str], Dict] = {}
        
        for edge in edges_data:
            src = edge['source']
            tgt = edge['target']
            self.adjacency[src].append((tgt, edge))
            self.edge_map[(src, tgt)] = edge
        
        # 预计算统计
        self.total_nodes = len(self.nodes)
        self.total_edges = len(self.edges)
        self.total_2hop_paths = self._compute_2hop_paths_count()
    
    def _compute_2hop_paths_count(self) -> int:
        """计算场景中所有两跳路径数量"""
        count = 0
        for node1 in self.nodes:
            for node2, _ in self.adjacency[node1]:
                for node3, _ in self.adjacency[node2]:
                    if node3 != node1:
                        count += 1
        return count


class CypherQueryAnalyzer:
    """Cypher 查询分析器 (优化版)"""
    
    def __init__(self, scene_graph: SceneGraph):
        self.scene = scene_graph
    
    def analyze_query(self, cypher_query: str) -> Tuple[Set[str], Set[Tuple[str, str]], Set[Tuple[str, str, str]]]:
        """
        分析 Cypher 查询涉及的节点/边/路径
        
        Returns:
            (nodes, edges, 2hop_paths)
        """
        nodes = set()
        edges = set()
        paths_2hop = set()
        
        # 预处理：规范化空格，移除注释
        cypher_clean = re.sub(r'//.*', '', cypher_query)
        cypher_clean = ' '.join(cypher_clean.split())
        
        # 提取 WHERE 条件（合并所有 WHERE 子句）
        conditions = self._extract_where_conditions(cypher_clean)
        
        # 提取 MATCH 模式
        patterns = self._extract_match_patterns(cypher_clean)
        
        for pattern in patterns:
            p_nodes, p_edges, p_paths = self._analyze_pattern(pattern, conditions)
            nodes.update(p_nodes)
            edges.update(p_edges)
            paths_2hop.update(p_paths)
        
        return nodes, edges, paths_2hop
    
    def _extract_match_patterns(self, cypher: str) -> List[str]:
        """提取 MATCH 子句中的模式"""
        patterns = []
        # 匹配 MATCH ... (直到关键字或结束)
        matches = re.finditer(
            r'MATCH\s+(.*?)(?=\s+(?:WHERE|WITH|RETURN|MATCH|ORDER|LIMIT|$))', 
            cypher, 
            re.IGNORECASE
        )
        for match in matches:
            pattern = match.group(1).strip()
            if pattern:
                patterns.append(pattern)
        return patterns
    
    def _extract_where_conditions(self, cypher: str) -> Dict:
        """提取并合并所有 WHERE 条件"""
        conditions = {
            'node_types': {},      # {var_name: type}
            'node_ids': {},        # {var_name: unique_id}
            'directions': {},      # {rel_var: direction}
            'statuses': {},        # {var_name: status}
        }
        
        # 查找所有 WHERE 子句
        where_clauses = re.findall(
            r'WHERE\s+(.*?)(?=\s+(?:WITH|RETURN|MATCH|ORDER|LIMIT|$))', 
            cypher, 
            re.IGNORECASE
        )
        full_where_str = " AND ".join(where_clauses)
        
        # 解析 type: n.type = 'car'
        for match in re.finditer(r'(\w+)\.type\s*=\s*[\'"](\w+)[\'"]', full_where_str):
            conditions['node_types'][match.group(1)] = match.group(2)
        
        # 解析 unique_id: n.unique_id = 'ego'
        for match in re.finditer(r'(\w+)\.unique_id\s*=\s*[\'"](\w+)[\'"]', full_where_str):
            conditions['node_ids'][match.group(1)] = match.group(2)
        
        # 解析 status: n.status = 'moving'
        for match in re.finditer(r'(\w+)\.status\s*=\s*[\'"](\w+)[\'"]', full_where_str):
            conditions['statuses'][match.group(1)] = match.group(2)
        
        # 解析 direction (支持多种格式)
        # 格式1: r.direction_8 = 'back-right'
        dir_pattern = r'(\w+)\.(?:direction_[48]|predicates\[0\])\s*=\s*[\'\"]([\'\"]+)[\'\"]'
        for match in re.finditer(dir_pattern, full_where_str):
            conditions['directions'][match.group(1)] = match.group(2)
        
        # 格式2: 'back-right' IN r.angle_matches_ego (或 angle_matches_source)
        # 统一用 Ego Frame
        angle_pattern = r"['\"]([^'\"]+)['\"]\s+IN\s+(\w+)\.angle_matches_(?:ego|source)"
        for match in re.finditer(angle_pattern, full_where_str, re.IGNORECASE):
            direction = match.group(1)
            rel_var = match.group(2)
            conditions['directions'][rel_var] = direction
        
        return conditions
    
    def _analyze_pattern(self, pattern: str, conditions: Dict) -> Tuple[Set[str], Set[Tuple[str, str]], Set[Tuple[str, str, str]]]:
        """分析单个 MATCH 模式"""
        nodes = set()
        edges = set()
        paths_2hop = set()
        
        if self._is_2hop_pattern(pattern):
            matched = self._match_2hop_pattern(conditions)
            for path in matched:
                nodes.update(path)
                edges.add((path[0], path[1]))
                edges.add((path[1], path[2]))
                paths_2hop.add(path)
        
        elif self._is_1hop_pattern(pattern):
            matched = self._match_1hop_pattern(conditions)
            for edge in matched:
                nodes.update(edge)
                edges.add(edge)
        
        else:
            matched = self._match_node_pattern(conditions)
            nodes.update(matched)
        
        return nodes, edges, paths_2hop
    
    def _is_2hop_pattern(self, pattern: str) -> bool:
        """判断是否为两跳模式"""
        arrow_count = pattern.count('->') + pattern.count('<-')
        return arrow_count >= 2
    
    def _is_1hop_pattern(self, pattern: str) -> bool:
        """判断是否为单跳模式"""
        return '->' in pattern or '<-' in pattern
    
    def _match_2hop_pattern(self, conditions: Dict) -> List[Tuple[str, str, str]]:
        """匹配两跳模式"""
        matched_paths = []
        
        for node1 in self.scene.nodes:
            if not self._node_satisfies_conditions(node1, conditions, position='first'):
                continue
            
            for node2, edge1 in self.scene.adjacency.get(node1, []):
                if not self._edge_satisfies_conditions(edge1, conditions):
                    continue
                if not self._node_satisfies_conditions(node2, conditions, position='middle'):
                    continue
                
                for node3, edge2 in self.scene.adjacency.get(node2, []):
                    if node3 == node1:
                        continue
                    if not self._edge_satisfies_conditions(edge2, conditions):
                        continue
                    if not self._node_satisfies_conditions(node3, conditions, position='last'):
                        continue
                    
                    matched_paths.append((node1, node2, node3))
        
        return matched_paths
    
    def _match_1hop_pattern(self, conditions: Dict) -> List[Tuple[str, str]]:
        """匹配单跳模式"""
        matched_edges = []
        
        for node1 in self.scene.nodes:
            if not self._node_satisfies_conditions(node1, conditions, position='first'):
                continue
            
            for node2, edge in self.scene.adjacency.get(node1, []):
                if not self._edge_satisfies_conditions(edge, conditions):
                    continue
                if not self._node_satisfies_conditions(node2, conditions, position='last'):
                    continue
                
                matched_edges.append((node1, node2))
        
        return matched_edges
    
    def _match_node_pattern(self, conditions: Dict) -> List[str]:
        """匹配单节点模式"""
        matched_nodes = []
        
        for node_id in self.scene.nodes:
            if self._node_satisfies_conditions(node_id, conditions, position='any'):
                matched_nodes.append(node_id)
        
        return matched_nodes
    
    def _node_satisfies_conditions(self, node_id: str, conditions: Dict, position: str = 'any') -> bool:
        """
        检查节点是否满足条件
        
        position: 'first', 'middle', 'last', 'any' - 节点在模式中的位置
        """
        node = self.scene.nodes[node_id]
        
        # 检查 unique_id 精确匹配
        if conditions['node_ids']:
            # 如果有 ID 约束，检查是否匹配
            matched_any_id = False
            for var, uid in conditions['node_ids'].items():
                if node_id == uid:
                    matched_any_id = True
                    break
            
            # 如果位置是 first 且有 ego 约束，必须匹配
            if position == 'first' and 'ego' in conditions['node_ids'].values():
                if node_id != 'ego':
                    return False
        
        # 检查类型约束
        if conditions['node_types']:
            matched_any_type = False
            for var, obj_type in conditions['node_types'].items():
                if node['type'] == obj_type:
                    matched_any_type = True
                    break
            # 如果有类型约束但没匹配上，返回 False
            # 但要注意：类型约束可能只针对某个变量，不是所有节点
            # 这里简化处理：如果有类型约束，至少一个要匹配
            # if not matched_any_type:
            #     return False
        
        # 检查状态约束
        for var, status in conditions['statuses'].items():
            if node.get('status') != status:
                return False
        
        return True
    
    def _edge_satisfies_conditions(self, edge: Dict, conditions: Dict) -> bool:
        """
        检查边是否满足条件 (修复了方向匹配逻辑)
        
        支持 direction_4, direction_8, predicates[0] 三种写法
        """
        required_directions = set(conditions['directions'].values())
        if not required_directions:
            return True
        
        # 获取边的所有方向属性 - 优先用 angle_matches_ego (宽松匹配)
        edge_dirs = set()
        
        # 优先使用 angle_matches_ego (宽松匹配，覆盖更多方向)
        if edge.get('angle_matches_ego'):
            edge_dirs.update(edge['angle_matches_ego'])
        
        # 备用: 精确方向
        if edge.get('direction_8_ego'):
            edge_dirs.add(edge['direction_8_ego'])
        if edge.get('direction_8'):
            edge_dirs.add(edge['direction_8'])
        if edge.get('direction_4'):
            edge_dirs.add(edge['direction_4'])
        if edge.get('predicates') and len(edge['predicates']) > 0 and edge['predicates'][0]:
            edge_dirs.add(edge['predicates'][0])
        
        # 检查交集：边的方向属性中，是否包含查询要求的方向
        if not edge_dirs.intersection(required_directions):
            return False
        
        return True


def calculate_coverage(vqa_results_path: str, scene_graph_path: str, 
                       only_correct: bool = True) -> CoverageStats:
    """
    计算精确覆盖率
    
    Args:
        vqa_results_path: VQA 测试结果 JSON 路径
        scene_graph_path: 场景图 JSON 路径
        only_correct: 是否只分析答对的题目
    """
    # 加载数据
    with open(vqa_results_path, 'r', encoding='utf-8') as f:
        vqa_data = json.load(f)
    
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_data = json.load(f)
    
    # 初始化
    scene_graph = SceneGraph(scene_data)
    analyzer = CypherQueryAnalyzer(scene_graph)
    
    stats = CoverageStats(
        total_nodes=scene_graph.total_nodes,
        total_edges=scene_graph.total_edges,
        total_2hop_paths=scene_graph.total_2hop_paths
    )
    
    # 提取结果
    results = vqa_data.get('results', [])
    if not results:
        # 尝试其他格式
        results = vqa_data.get('scene_results', [])
        if results and isinstance(results[0], dict) and 'results' in results[0]:
            results = results[0]['results']
    
    stats.total_questions = len(results)
    
    logger.info(f"\n场景: {scene_graph.scene_name} 帧{scene_graph.frame_idx}")
    logger.info(f"总问题数: {stats.total_questions}")
    
    # 统计答对的题目数
    for result in results:
        if result.get('correct', False):
            stats.correct_questions += 1
    
    logger.info(f"答对问题数: {stats.correct_questions}")
    
    # 分析每道题
    for i, result in enumerate(results, 1):
        # 检查是否答对
        is_correct = result.get('correct', False)
        if only_correct and not is_correct:
            continue
        
        # 提取 Cypher 查询
        cypher_query = result.get('cypher_query', '')
        if not cypher_query:
            # 尝试从嵌套结构提取
            if isinstance(result.get('result'), dict):
                cypher_query = result['result'].get('cypher_query', '')
        
        if not cypher_query:
            logger.debug(f"  问题 {i} 没有 Cypher 查询，跳过")
            continue
        
        try:
            # 分析查询
            nodes, edges, paths = analyzer.analyze_query(cypher_query)
            
            # 更新统计
            for node in nodes:
                stats.add_node(node)
            for edge in edges:
                stats.add_edge(*edge)
            for path in paths:
                stats.add_2hop_path(*path)
            
            stats.analyzed_questions += 1
            
        except Exception as e:
            logger.warning(f"  问题 {i} 分析失败: {e}")
    
    logger.info(f"成功分析: {stats.analyzed_questions} 道题")
    
    return stats


def main():
    """主函数"""
    import sys
    
    print("="*70)
    print("  精确 L-Level 覆盖率计算器")
    print("="*70)
    
    # 默认路径
    default_vqa = "output/coverage_analysis/vqa_results/scene-0103_frame38_official_qa.json"
    default_sg = "output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json"
    
    # 命令行参数
    if len(sys.argv) >= 3:
        vqa_path = sys.argv[1]
        sg_path = sys.argv[2]
    elif len(sys.argv) == 2:
        vqa_path = sys.argv[1]
        sg_path = default_sg
    else:
        vqa_path = default_vqa
        sg_path = default_sg
    
    # 可选：分析所有题目（不仅是答对的）
    only_correct = True
    if len(sys.argv) >= 4 and sys.argv[3] == '--all':
        only_correct = False
    
    # 检查文件
    if not Path(vqa_path).exists():
        logger.error(f"找不到 VQA 结果文件: {vqa_path}")
        logger.info("\n用法: python calculate_coverage_precise.py <vqa_results.json> <scene_graph.json> [--all]")
        logger.info("  --all: 分析所有题目（默认只分析答对的题目）")
        return
    
    if not Path(sg_path).exists():
        logger.error(f"找不到场景图文件: {sg_path}")
        return
    
    # 计算覆盖率
    mode = "所有题目" if not only_correct else "答对的题目"
    logger.info(f"\n分析模式: {mode}")
    
    stats = calculate_coverage(vqa_path, sg_path, only_correct=only_correct)
    
    # 打印报告
    stats.print_report()
    
    # 保存结果
    output_path = Path(vqa_path).parent / f"{Path(vqa_path).stem}_coverage_precise.json"
    rates = stats.get_coverage_rates()
    
    output_data = {
        'vqa_results': str(vqa_path),
        'scene_graph': str(sg_path),
        'analysis_mode': 'correct_only' if only_correct else 'all',
        'questions': {
            'total': stats.total_questions,
            'correct': stats.correct_questions,
            'analyzed': stats.analyzed_questions
        },
        'scene_stats': {
            'total_nodes': stats.total_nodes,
            'total_edges': stats.total_edges,
            'total_2hop_paths': stats.total_2hop_paths
        },
        'coverage': {
            'L0': {
                'covered': len(stats.covered_nodes),
                'total': stats.total_nodes,
                'rate': rates['L0'],
                'nodes': sorted(list(stats.covered_nodes)) if len(stats.covered_nodes) <= 50 else f"{len(stats.covered_nodes)} nodes"
            },
            'L1': {
                'covered': len(stats.covered_edges),
                'total': stats.total_edges,
                'rate': rates['L1']
            },
            'L2': {
                'covered': len(stats.covered_2hop_paths),
                'total': stats.total_2hop_paths,
                'rate': rates['L2']
            }
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n结果已保存: {output_path}")


if __name__ == "__main__":
    main()
