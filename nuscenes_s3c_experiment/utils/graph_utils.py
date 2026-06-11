"""
场景图操作工具
"""
import rustworkx as rx
import copy
from typing import List, Dict, Any


def create_scene_graph(ego_data, objects_data):
    """
    创建场景图
    
    Args:
        ego_data: ego车数据
        objects_data: 对象列表，每个对象包含 {type, predicates}
    
    Returns:
        scene_graph: rustworkx图对象
    """
    sg = rx.PyDAG()
    
    # 添加ego节点
    ego_id = sg.add_node({
        'type': 'ego',
        'id': 'ego'
    })
    
    # 添加对象节点和边
    for i, obj in enumerate(objects_data):
        obj_id = sg.add_node({
            'type': obj['type'],
            'id': f"{obj['type']}_{i}"
        })
        
        # 添加边（ego到对象的关系）
        sg.add_edge(ego_id, obj_id, {
            'predicates': obj['predicates']
        })
    
    return sg


def abstract_scene_graph(scene_graph):
    """
    抽象化场景图（移除ID，保留类型和关系）
    
    Args:
        scene_graph: 原始场景图
    
    Returns:
        abstract_sg: 抽象场景图
    """
    # 创建新图
    abstract_sg = rx.PyDAG()
    
    # 节点映射
    node_mapping = {}
    
    # 复制节点（只保留type）
    for node_idx in scene_graph.node_indices():
        node_data = scene_graph[node_idx]
        new_node_idx = abstract_sg.add_node({
            'type': node_data['type']
        })
        node_mapping[node_idx] = new_node_idx
    
    # 复制边（保留predicates）
    for edge in scene_graph.edge_list():
        src, dst = edge
        edge_data = scene_graph.get_edge_data(src, dst)
        abstract_sg.add_edge(
            node_mapping[src],
            node_mapping[dst],
            edge_data
        )
    
    return abstract_sg


def compare_scene_graphs(sg1, sg2):
    """
    比较两个场景图是否同构
    
    Args:
        sg1, sg2: 两个场景图
    
    Returns:
        is_isomorphic: 是否同构
    """
    def node_matcher(node1, node2):
        """节点匹配器：类型必须相同"""
        return node1['type'] == node2['type']
    
    def edge_matcher(edge1, edge2):
        """边匹配器：谓词集合必须相同"""
        preds1 = set(edge1['predicates'])
        preds2 = set(edge2['predicates'])
        return preds1 == preds2
    
    try:
        return rx.is_isomorphic(
            sg1, sg2,
            node_matcher=node_matcher,
            edge_matcher=edge_matcher
        )
    except Exception as e:
        print(f"图同构检测错误: {e}")
        return False


def scene_graph_to_dict(scene_graph):
    """
    将场景图转换为字典表示（用于保存）
    
    Args:
        scene_graph: rustworkx图对象
    
    Returns:
        graph_dict: 字典表示
    """
    nodes = []
    for idx in scene_graph.node_indices():
        node_data = scene_graph[idx]
        nodes.append({
            'index': idx,
            'data': node_data
        })
    
    edges = []
    for edge in scene_graph.edge_list():
        src, dst = edge
        edge_data = scene_graph.get_edge_data(src, dst)
        edges.append({
            'source': src,
            'target': dst,
            'data': edge_data
        })
    
    return {
        'nodes': nodes,
        'edges': edges
    }


def dict_to_scene_graph(graph_dict):
    """
    从字典表示恢复场景图
    
    Args:
        graph_dict: 字典表示
    
    Returns:
        scene_graph: rustworkx图对象
    """
    sg = rx.PyDAG()
    
    # 添加节点
    node_mapping = {}
    for node in graph_dict['nodes']:
        new_idx = sg.add_node(node['data'])
        node_mapping[node['index']] = new_idx
    
    # 添加边
    for edge in graph_dict['edges']:
        sg.add_edge(
            node_mapping[edge['source']],
            node_mapping[edge['target']],
            edge['data']
        )
    
    return sg


def get_scene_graph_signature(scene_graph):
    """
    获取场景图的签名（用于快速比较）
    
    Args:
        scene_graph: 场景图
    
    Returns:
        signature: 签名字符串
    """
    # 统计节点类型
    node_types = {}
    for idx in scene_graph.node_indices():
        node_type = scene_graph[idx]['type']
        node_types[node_type] = node_types.get(node_type, 0) + 1
    
    # 统计边的谓词
    edge_predicates = []
    for edge in scene_graph.edge_list():
        src, dst = edge
        edge_data = scene_graph.get_edge_data(src, dst)
        preds = '+'.join(sorted(edge_data['predicates']))
        edge_predicates.append(preds)
    
    # 生成签名
    node_sig = ','.join(f"{k}:{v}" for k, v in sorted(node_types.items()))
    edge_sig = '|'.join(sorted(edge_predicates))
    
    return f"{node_sig}#{edge_sig}"
