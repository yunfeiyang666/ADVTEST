"""
精确 L-Level 覆盖率计算器 (覆盖率评估专用版)

统一标准：
- 坐标系: Ego Frame (以ego车辆为参照)
- 方向匹配: angle_matches_ego (宽松匹配，支持8方向词表)

覆盖率定义：
- L=0 (节点覆盖): 题目涉及了哪些对象节点
- L=1 (边覆盖): 题目涉及了哪些边，包括：
  - 对象之间的空间关系边 (RELATES_TO)
  - 对象到属性的边 (如查询 car.status)
- L=2 (两跳路径覆盖): 题目涉及了哪些连续两条边的路径
  - 例: A-[r1]->B-[r2]->C 或 A的属性查询 + A到B的关系

注意：属性不作为独立节点，而是作为边的终点。
这样避免了以status等通用属性为中间点的无意义L=2路径。

输出：
- L=0: 节点覆盖率 = 涉及的唯一节点数 / 场景总节点数
- L=1: 边覆盖率 = 涉及的唯一边数 / 场景总边数 (关系边 + 属性边)
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


# ============ 配置常量 ============
# 统一使用 Ego Frame 的方向属性
DIRECTION_FIELD = 'angle_matches_ego'  # 宽松匹配
DIRECTION_FIELD_PRECISE = 'direction_8_ego'  # 精确匹配 (备用)

# 8方向词表
DIRECTIONS_8 = ['front', 'front-left', 'left', 'back-left', 
                'back', 'back-right', 'right', 'front-right']

# 对象属性列表 (用于计算属性边)
OBJECT_PROPERTIES = ['type', 'status', 'category']


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
        logger.info("  精确 L-Level 覆盖率报告 (Ego Frame)")
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
    """
    场景图数据结构
    
    边的定义:
    1. 关系边: 对象A -> 对象B 的空间关系 (RELATES_TO)
    2. 属性边: 对象 -> 属性值 (如 car_1 -> status:stopped)
    
    两跳路径:
    - A-[r1]->B-[r2]->C (两个关系边)
    - A-[r]->B + B.属性 (关系边 + 属性边)
    - A.属性 + A-[r]->B (属性边 + 关系边)
    """
    
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
        
        # 解析关系边 (RELATES_TO)
        edges_data = scene_data.get('relationships') or scene_data.get('edges', [])
        self.relation_edges: List[Dict] = edges_data  # 关系边
        
        # 构建关系边邻接表
        self.adjacency: Dict[str, List[Tuple[str, Dict]]] = defaultdict(list)
        self.edge_map: Dict[Tuple[str, str], Dict] = {}
        
        for edge in edges_data:
            src = edge['source']
            tgt = edge['target']
            self.adjacency[src].append((tgt, edge))
            self.edge_map[(src, tgt)] = edge
        
        # 计算属性边: 每个对象的每个属性算一条边
        # 属性边用 (node_id, "prop:value") 表示
        self.property_edges: Set[Tuple[str, str]] = set()
        for node_id, node in self.nodes.items():
            for prop in OBJECT_PROPERTIES:
                if prop in node and node[prop]:
                    # 属性边: node_id -> prop:value
                    self.property_edges.add((node_id, f"{prop}:{node[prop]}"))
        
        # 总边数 = 关系边 + 属性边
        self.total_nodes = len(self.nodes)
        self.total_relation_edges = len(self.relation_edges)
        self.total_property_edges = len(self.property_edges)
        self.total_edges = self.total_relation_edges + self.total_property_edges
        
        # 计算两跳路径数
        self.total_2hop_paths = self._compute_2hop_paths_count()
    
    def _compute_2hop_paths_count(self) -> int:
        """
        计算场景中所有两跳路径数量
        
        两跳路径类型:
        1. 关系-关系: A-[r1]->B-[r2]->C
        2. 关系-属性: A-[r]->B, 然后查B的属性
        3. 属性-关系: 查A的属性, 然后A-[r]->B
        """
        count = 0
        
        # 类型1: 关系-关系 (A->B->C)
        for node1 in self.nodes:
            for node2, _ in self.adjacency[node1]:
                for node3, _ in self.adjacency[node2]:
                    if node3 != node1:
                        count += 1
        
        # 类型2: 关系-属性 (A->B, 然后查B.属性)
        # 每条关系边 * 目标节点的属性数
        for edge in self.relation_edges:
            tgt = edge['target']
            tgt_node = self.nodes.get(tgt, {})
            for prop in OBJECT_PROPERTIES:
                if prop in tgt_node and tgt_node[prop]:
                    count += 1
        
        # 类型3: 属性-关系 (查A.属性, 然后A->B)
        # 每个节点的属性数 * 该节点的出边数
        for node_id, node in self.nodes.items():
            prop_count = sum(1 for prop in OBJECT_PROPERTIES if prop in node and node[prop])
            out_edges = len(self.adjacency[node_id])
            count += prop_count * out_edges
        
        return count


class CypherQueryAnalyzer:
    """
    Cypher 查询分析器
    
    统一使用 Ego Frame，支持两种方向语法:
    - 'direction' IN r.angle_matches_ego (宽松匹配)
    - r.direction_8_ego = 'direction' (精确匹配)
    """
    
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
        """
        提取并合并所有 WHERE 条件
        
        统一使用 Ego Frame，支持多种语法:
        - 'dir' IN r.angle_matches_ego (推荐)
        - 'dir' IN r.angle_matches_source (兼容，转换为ego)
        - r.direction_8_ego = 'dir' (精确匹配)
        """
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
        
        # 解析方向 - 格式1: 'dir' IN r.angle_matches_ego/source
        # 统一当作 Ego Frame 处理
        angle_pattern = r"['\"]([^'\"]+)['\"]\s+IN\s+(\w+)\.angle_matches_(?:ego|source)"
        for match in re.finditer(angle_pattern, full_where_str, re.IGNORECASE):
            direction = match.group(1)
            rel_var = match.group(2)
            conditions['directions'][rel_var] = direction
        
        # 解析方向 - 格式2: r.direction_8_ego = 'dir' (精确匹配)
        dir8_pattern = r'(\w+)\.direction_8_(?:ego|source)\s*=\s*[\'"]([^"\']+)[\'"]'
        for match in re.finditer(dir8_pattern, full_where_str, re.IGNORECASE):
            rel_var = match.group(1)
            direction = match.group(2)
            # 精确匹配也存入 directions
            if rel_var not in conditions['directions']:
                conditions['directions'][rel_var] = direction
        
        # 解析方向 - 格式3: r.predicates[0] = 'dir' (兼容旧格式)
        pred_pattern = r'(\w+)\.predicates\[0\]\s*=\s*[\'"]([^"\']+)[\'"]'
        for match in re.finditer(pred_pattern, full_where_str, re.IGNORECASE):
            rel_var = match.group(1)
            direction = match.group(2)
            if rel_var not in conditions['directions']:
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
        
        # 检查状态约束
        for var, status in conditions['statuses'].items():
            if node.get('status') != status:
                return False
        
        return True
    
    def _edge_satisfies_conditions(self, edge: Dict, conditions: Dict) -> bool:
        """
        检查边是否满足条件
        
        统一使用 Ego Frame:
        - 优先: angle_matches_ego (宽松匹配)
        - 备用: direction_8_ego (精确匹配)
        """
        required_directions = set(conditions['directions'].values())
        if not required_directions:
            return True
        
        # 获取边的方向属性 - 统一用 Ego Frame
        edge_dirs = set()
        
        # 优先使用 angle_matches_ego (宽松匹配，覆盖更多方向)
        if edge.get('angle_matches_ego'):
            edge_dirs.update(edge['angle_matches_ego'])
        
        # 备用: direction_8_ego (精确匹配)
        if edge.get('direction_8_ego'):
            edge_dirs.add(edge['direction_8_ego'])
        
        # 兼容: 如果没有 ego frame 字段，尝试 source frame
        if not edge_dirs:
            if edge.get('angle_matches_source'):
                edge_dirs.update(edge['angle_matches_source'])
            if edge.get('direction_8_source'):
                edge_dirs.add(edge['direction_8_source'])
        
        # 最后备用: 旧格式
        if not edge_dirs:
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


def calculate_coverage_single_scene(
    results: List[Dict], 
    scene_graph: SceneGraph,
    only_correct: bool = True
) -> CoverageStats:
    """
    计算单个场景的覆盖率
    
    Args:
        results: 该场景的VQA结果列表
        scene_graph: 场景图对象
        only_correct: 是否只分析答对的题目
    """
    analyzer = CypherQueryAnalyzer(scene_graph)
    
    stats = CoverageStats(
        total_nodes=scene_graph.total_nodes,
        total_edges=scene_graph.total_edges,
        total_2hop_paths=scene_graph.total_2hop_paths
    )
    
    stats.total_questions = len(results)
    
    # 统计答对的题目数
    for result in results:
        if result.get('correct', False):
            stats.correct_questions += 1
    
    # 分析每道题
    for i, result in enumerate(results, 1):
        is_correct = result.get('correct', False)
        if only_correct and not is_correct:
            continue
        
        # 提取 Cypher 查询 - 支持多种格式
        cypher_query = (
            result.get('final_cypher') or 
            result.get('cypher_query') or 
            ''
        )
        if not cypher_query and isinstance(result.get('result'), dict):
            cypher_query = result['result'].get('cypher_query', '')
        
        if not cypher_query:
            continue
        
        try:
            nodes, edges, paths = analyzer.analyze_query(cypher_query)
            
            for node in nodes:
                stats.add_node(node)
            for edge in edges:
                stats.add_edge(*edge)
            for path in paths:
                stats.add_2hop_path(*path)
            
            stats.analyzed_questions += 1
            
        except Exception as e:
            logger.warning(f"  问题 {i} 分析失败: {e}")
    
    return stats


def calculate_coverage(
    vqa_results_path: str, 
    scene_graphs_dir: str,
    only_correct: bool = True,
    output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    计算覆盖率 (支持多场景VQA结果)
    
    Args:
        vqa_results_path: VQA 测试结果 JSON 路径 (enhanced_qa_test_*.json)
        scene_graphs_dir: 场景图目录
        only_correct: 是否只分析答对的题目
        output_dir: 输出目录 (默认与vqa_results同目录)
    
    Returns:
        包含各场景覆盖率的汇总字典
    """
    # 加载VQA结果
    with open(vqa_results_path, 'r', encoding='utf-8') as f:
        vqa_data = json.load(f)
    
    scene_graphs_dir = Path(scene_graphs_dir)
    output_dir = Path(output_dir) if output_dir else Path(vqa_results_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 解析VQA结果结构
    # 格式: {"scenes": [{"scene_name": ..., "frame_idx": ..., "results": [...]}]}
    scenes = vqa_data.get('scenes', [])
    if not scenes:
        # 兼容旧格式
        logger.error("VQA结果文件格式不正确，缺少 'scenes' 字段")
        return {}
    
    logger.info(f"\n{'='*70}")
    logger.info(f"  覆盖率计算 (Ego Frame + angle_matches_ego)")
    logger.info(f"{'='*70}")
    logger.info(f"VQA结果: {vqa_results_path}")
    logger.info(f"场景图目录: {scene_graphs_dir}")
    logger.info(f"分析模式: {'仅答对题目' if only_correct else '所有题目'}")
    logger.info(f"场景数: {len(scenes)}")
    
    # 汇总统计 (各场景独立统计后求和，不跨场景去重)
    all_results = {
        'vqa_results_file': str(vqa_results_path),
        'coordinate_frame': 'ego',
        'direction_matching': 'angle_matches_ego',
        'analysis_mode': 'correct_only' if only_correct else 'all',
        'scenes': [],
        'summary': {
            'total_nodes': 0,
            'total_edges': 0,
            'total_2hop_paths': 0,
            'covered_nodes_count': 0,  # 改为计数，不是set
            'covered_edges_count': 0,
            'covered_2hop_paths_count': 0,
            'total_questions': 0,
            'correct_questions': 0,
            'analyzed_questions': 0,
        }
    }
    
    # 逐场景处理
    for scene_info in scenes:
        scene_name = scene_info.get('scene_name', 'unknown')
        frame_idx = scene_info.get('frame_idx', 0)
        results = scene_info.get('results', [])
        
        # 加载对应场景图
        sg_filename = f"{scene_name}_frame{frame_idx}_scene_graph.json"
        sg_path = scene_graphs_dir / sg_filename
        
        if not sg_path.exists():
            logger.warning(f"\n⚠️ 场景图不存在: {sg_path}，跳过")
            continue
        
        with open(sg_path, 'r', encoding='utf-8') as f:
            scene_data = json.load(f)
        
        scene_graph = SceneGraph(scene_data)
        
        logger.info(f"\n--- {scene_name} 帧{frame_idx} ---")
        logger.info(f"  节点: {scene_graph.total_nodes}, 边: {scene_graph.total_edges}, 2跳路径: {scene_graph.total_2hop_paths}")
        logger.info(f"  问题: {len(results)}")
        
        # 计算该场景覆盖率
        stats = calculate_coverage_single_scene(results, scene_graph, only_correct)
        rates = stats.get_coverage_rates()
        
        logger.info(f"  答对: {stats.correct_questions}, 分析: {stats.analyzed_questions}")
        logger.info(f"  覆盖率: L0={rates['L0']:.1%}, L1={rates['L1']:.1%}, L2={rates['L2']:.1%}")
        
        # 记录该场景结果
        scene_result = {
            'scene_name': scene_name,
            'frame_idx': frame_idx,
            'scene_stats': {
                'total_nodes': stats.total_nodes,
                'total_edges': stats.total_edges,
                'total_2hop_paths': stats.total_2hop_paths,
            },
            'questions': {
                'total': stats.total_questions,
                'correct': stats.correct_questions,
                'analyzed': stats.analyzed_questions,
            },
            'coverage': {
                'L0': {'covered': len(stats.covered_nodes), 'total': stats.total_nodes, 'rate': rates['L0']},
                'L1': {'covered': len(stats.covered_edges), 'total': stats.total_edges, 'rate': rates['L1']},
                'L2': {'covered': len(stats.covered_2hop_paths), 'total': stats.total_2hop_paths, 'rate': rates['L2']},
            }
        }
        all_results['scenes'].append(scene_result)
        
        # 汇总 (各场景独立统计，直接求和)
        all_results['summary']['total_nodes'] += stats.total_nodes
        all_results['summary']['total_edges'] += stats.total_edges
        all_results['summary']['total_2hop_paths'] += stats.total_2hop_paths
        all_results['summary']['covered_nodes_count'] += len(stats.covered_nodes)
        all_results['summary']['covered_edges_count'] += len(stats.covered_edges)
        all_results['summary']['covered_2hop_paths_count'] += len(stats.covered_2hop_paths)
        all_results['summary']['total_questions'] += stats.total_questions
        all_results['summary']['correct_questions'] += stats.correct_questions
        all_results['summary']['analyzed_questions'] += stats.analyzed_questions
    
    # 计算汇总覆盖率
    summary = all_results['summary']
    summary_rates = {
        'L0': summary['covered_nodes_count'] / max(summary['total_nodes'], 1),
        'L1': summary['covered_edges_count'] / max(summary['total_edges'], 1),
        'L2': summary['covered_2hop_paths_count'] / max(summary['total_2hop_paths'], 1),
    }
    summary['coverage_rates'] = summary_rates
    
    # 打印汇总
    logger.info(f"\n{'='*70}")
    logger.info(f"  汇总 (所有场景)")
    logger.info(f"{'='*70}")
    logger.info(f"总节点: {summary['total_nodes']}, 覆盖: {all_results['summary']['covered_nodes_count']}")
    logger.info(f"总边: {summary['total_edges']}, 覆盖: {all_results['summary']['covered_edges_count']}")
    logger.info(f"总2跳路径: {summary['total_2hop_paths']}, 覆盖: {all_results['summary']['covered_2hop_paths_count']}")
    logger.info(f"\n【覆盖率】")
    logger.info(f"  L0 (节点): {summary_rates['L0']:.2%}")
    logger.info(f"  L1 (边): {summary_rates['L1']:.2%}")
    logger.info(f"  L2 (2跳): {summary_rates['L2']:.2%}")
    
    # 保存结果
    output_filename = f"{Path(vqa_results_path).stem}_coverage.json"
    output_path = output_dir / output_filename
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n结果已保存: {output_path}")
    
    return all_results


def main():
    """主函数"""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(
        description='精确 L-Level 覆盖率计算器 (Ego Frame + angle_matches_ego)'
    )
    parser.add_argument(
        'vqa_results', 
        nargs='?',
        default='../output/coverage_analysis/vqa_results/enhanced_qa_test_20260127_233830.json',
        help='VQA测试结果JSON文件路径'
    )
    parser.add_argument(
        '--scene-graphs', '-s',
        default='../output/coverage_analysis/scene_graphs',
        help='场景图目录路径'
    )
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='输出目录 (默认与VQA结果同目录)'
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='分析所有题目 (默认只分析答对的题目)'
    )
    
    args = parser.parse_args()
    
    # 检查文件
    vqa_path = Path(args.vqa_results)
    sg_dir = Path(args.scene_graphs)
    
    if not vqa_path.exists():
        logger.error(f"找不到 VQA 结果文件: {vqa_path}")
        logger.info("\n用法: python calculate_coverage.py <vqa_results.json> -s <scene_graphs_dir> [--all]")
        return
    
    if not sg_dir.exists():
        logger.error(f"找不到场景图目录: {sg_dir}")
        return
    
    # 计算覆盖率
    only_correct = not args.all
    calculate_coverage(
        vqa_results_path=str(vqa_path),
        scene_graphs_dir=str(sg_dir),
        only_correct=only_correct,
        output_dir=args.output
    )


if __name__ == "__main__":
    main()
