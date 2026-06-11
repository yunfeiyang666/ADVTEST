#!/usr/bin/env python
"""调试筛选器问题"""
import sys
sys.path.insert(0, 'E:\\Project\\ADVTEST\\nuscenes_s3c_experiment')

from core_pipeline.coverage_evaluation.scene_filter import SceneGraphFilter
import json

# 加载场景图
sg_path = 'output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json'
with open(sg_path, 'r', encoding='utf-8') as f:
    sg_data = json.load(f)

print("="*70)
print("调试筛选器")
print("="*70)

# 查看ego节点坐标
ego = [n for n in sg_data['nodes'] if n['type'] == 'ego'][0]
ego_trans = ego.get('translation', {})
ego_x, ego_y = ego_trans.get('x', 0), ego_trans.get('y', 0)
print(f"\nego节点坐标: ({ego_x:.2f}, {ego_y:.2f})")

# 查看几个节点的相对距离
print("\n前5个非ego节点（使用相对距离）:")
nodes = [n for n in sg_data['nodes'] if n['type'] != 'ego'][:5]

for node in nodes:
    trans = node.get('translation', {})
    x, y = trans.get('x', 0), trans.get('y', 0)
    
    # 相对距离
    dx = x - ego_x
    dy = y - ego_y
    rel_distance = (dx**2 + dy**2) ** 0.5
    
    # 绝对距离（错误的方式）
    abs_distance = (x**2 + y**2) ** 0.5
    
    threshold = SceneGraphFilter.DETECTION_RANGES.get(node['type'], 50)
    
    print(f"\n{node['unique_id']} ({node['type']}):")
    print(f"  全局坐标: ({x:.2f}, {y:.2f})")
    print(f"  相对坐标: ({dx:.2f}, {dy:.2f})")
    print(f"  相对距离: {rel_distance:.2f} m (正确)")
    print(f"  绝对距离: {abs_distance:.2f} m (错误)")
    print(f"  阈值: {threshold} m")
    print(f"  是否保留: {'✅' if rel_distance <= threshold else '❌'}")
