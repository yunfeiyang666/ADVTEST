"""
场景覆盖率计算 - 核心函数
提取关键逻辑，便于集成使用
"""
import json
import re
from typing import List, Dict, Tuple, Set


def calculate_coverage(questions: List[Dict], scene_graph_path: str) -> Tuple[int, int, float]:
    """
    计算问题集对场景图的边覆盖率（核心函数）
    
    Args:
        questions: 问题列表，每个问题需包含 'cypher' 或 'cypher_query' 字段
        scene_graph_path: 场景图JSON文件路径
    
    Returns:
        (covered_edges, total_edges, coverage_rate): 覆盖边数、总边数、覆盖率(%)
    
    Example:
        >>> questions = [{'cypher': "MATCH (n) WHERE n.type='car' RETURN n"}]
        >>> covered, total, rate = calculate_coverage(questions, "scene.json")
        >>> print(f"覆盖率: {rate}%")
    """
    # 1. 加载场景图
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        edges = json.load(f).get('edges', [])
    
    total_edges = len(edges)
    if total_edges == 0:
        return 0, 0, 0.0
    
    # 2. 分析每个问题，收集覆盖的边
    covered_edge_indices = set()
    
    for question in questions:
        # 提取Cypher查询（兼容两种字段名）
        cypher = question.get('cypher_query', question.get('cypher', '')).strip()
        if not cypher:
            continue
        
        # 从Cypher中提取关键信息
        unique_ids = _extract_unique_ids(cypher)
        types = _extract_types(cypher)
        has_ego = 'ego' in cypher.lower()
        
        # 匹配边
        for i, edge in enumerate(edges):
            source = edge.get('source', '')
            target = edge.get('target', '')
            
            # 匹配规则1: unique_id精确匹配
            if unique_ids and any(uid in source or uid in target for uid in unique_ids):
                covered_edge_indices.add(i)
                continue
            
            # 匹配规则2: ego节点匹配
            if has_ego and source == 'ego':
                covered_edge_indices.add(i)
                continue
            
            # 匹配规则3: 类型模糊匹配
            if types and any(t in source.lower() or t in target.lower() for t in types):
                covered_edge_indices.add(i)
    
    # 3. 计算覆盖率
    covered_count = len(covered_edge_indices)
    coverage_rate = (covered_count / total_edges) * 100
    
    return covered_count, total_edges, round(coverage_rate, 2)


def _extract_unique_ids(cypher: str) -> Set[str]:
    """从Cypher中提取unique_id"""
    pattern = r"unique_id\s*[:=]\s*['\"](\w+)['\"]"
    return set(re.findall(pattern, cypher))


def _extract_types(cypher: str) -> Set[str]:
    """从Cypher中提取对象类型"""
    pattern = r"type\s*[:=]\s*['\"](\w+)['\"]"
    return set(t.lower() for t in re.findall(pattern, cypher))


# ========== 便捷函数 ==========

def calculate_from_files(questions_file: str, scene_graph_file: str) -> Dict:
    """
    从文件读取并计算覆盖率（一行调用版本）
    
    Args:
        questions_file: VQA结果JSON文件路径
        scene_graph_file: 场景图JSON文件路径
    
    Returns:
        {
            'covered_edges': 覆盖边数,
            'total_edges': 总边数,
            'coverage_rate': 覆盖率(%),
            'total_questions': 问题数
        }
    """
    # 加载问题
    with open(questions_file, 'r', encoding='utf-8') as f:
        questions = json.load(f).get('results', [])
    
    # 计算覆盖率
    covered, total, rate = calculate_coverage(questions, scene_graph_file)
    
    return {
        'covered_edges': covered,
        'total_edges': total,
        'coverage_rate': rate,
        'total_questions': len(questions)
    }


# ========== 使用示例 ==========

if __name__ == '__main__':
    # 示例1: 直接调用
    print("=" * 60)
    print("示例1: 直接调用核心函数")
    print("=" * 60)
    
    questions = [
        {'cypher': "MATCH (n:Object) WHERE n.type='car' RETURN n"},
        {'cypher': "MATCH (ego:Object)-[r]->(m) RETURN m"}
    ]
    
    scene_graph_file = "output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json"
    
    covered, total, rate = calculate_coverage(questions, scene_graph_file)
    print(f"\n覆盖边数: {covered}/{total}")
    print(f"覆盖率: {rate}%")
    
    # 示例2: 从文件读取
    print("\n" + "=" * 60)
    print("示例2: 从文件读取")
    print("=" * 60)
    
    questions_file = "output/coverage_analysis/vqa_results/scene-0553_frame8_official_qa.json"
    
    stats = calculate_from_files(questions_file, scene_graph_file)
    print(f"\n问题数: {stats['total_questions']}")
    print(f"覆盖边数: {stats['covered_edges']}/{stats['total_edges']}")
    print(f"覆盖率: {stats['coverage_rate']}%")
    
    print("\n" + "=" * 60)
