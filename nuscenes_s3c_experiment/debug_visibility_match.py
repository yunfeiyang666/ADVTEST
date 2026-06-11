#!/usr/bin/env python
"""
调试可见度匹配问题
"""
import os
import sys
import json

# 添加本地路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nuscenes.nuscenes import NuScenes
import config

# 加载数据
print("加载 nuScenes...")
nusc = NuScenes(version='v1.0-mini', dataroot=config.NUSCENES_DATAROOT, verbose=False)

# 加载场景图
scene_graph_file = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\coverage_analysis\scene-0061_frame19_scene_graph.json"
with open(scene_graph_file, 'r', encoding='utf-8') as f:
    scene_graph = json.load(f)

scene_name = scene_graph['scene_name']
frame_idx = scene_graph['frame_idx']

# 获取 sample_token
scene_rec = nusc.get('scene', nusc.field2token('scene', 'name', scene_name)[0])
sample = nusc.get('sample', scene_rec['first_sample_token'])
for _ in range(frame_idx):
    if sample['next']:
        sample = nusc.get('sample', sample['next'])
sample_token = sample['token']

print(f"\n场景: {scene_name}, Frame: {frame_idx}")
print(f"Sample token: {sample_token}")
print(f"场景图节点数: {len(scene_graph['nodes'])}")

# 获取 nuScenes 标注
sample = nusc.get('sample', sample_token)
print(f"nuScenes 标注数: {len(sample['anns'])}")

# 测试匹配：取前5个节点
print("\n" + "=" * 80)
print("测试前5个场景图节点的匹配")
print("=" * 80)

nodes = [n for n in scene_graph['nodes'] if n.get('type') != 'ego'][:5]

for node in nodes:
    node_id = node['unique_id']
    node_type = node['type']
    node_category = node.get('category', '')
    node_trans = node['translation']
    
    print(f"\n节点: {node_id}")
    print(f"  类型: {node_type}, 类别: {node_category}")
    print(f"  位置: ({node_trans['x']:.2f}, {node_trans['y']:.2f}, {node_trans['z']:.2f})")
    
    # 尝试匹配
    best_match = None
    min_dist = float('inf')
    matched_anns = []
    
    for ann_token in sample['anns']:
        ann = nusc.get('sample_annotation', ann_token)
        ann_category = ann['category_name']
        
        # 类别匹配
        category_match = False
        if node_category and ann_category == node_category:
            category_match = True
        elif node_type:
            if ann_category.endswith('.' + node_type) or ann_category == node_type:
                category_match = True
            elif node_type == 'pedestrian' and 'pedestrian' in ann_category:
                category_match = True
        
        if not category_match:
            continue
        
        # 距离匹配
        ann_x, ann_y, ann_z = ann['translation']
        dist = ((ann_x - node_trans['x'])**2 + 
                (ann_y - node_trans['y'])**2 + 
                (ann_z - node_trans['z'])**2) ** 0.5
        
        matched_anns.append((ann_category, dist))
        
        if dist < min_dist:
            min_dist = dist
            best_match = ann
    
    print(f"  匹配到 {len(matched_anns)} 个同类型标注")
    if matched_anns:
        print(f"    最近的: 距离 {min_dist:.2f}m")
        if min_dist < 2.0 and best_match:
            # 获取 visibility
            if best_match.get('visibility_token'):
                vis_token = best_match['visibility_token']
                vis_record = nusc.get('visibility', vis_token)
                print(f"    ✓ 成功匹配! Visibility: {vis_record['level']}")
            else:
                print(f"    ✗ 匹配到但没有 visibility_token")
        else:
            print(f"    ✗ 距离太远 (> 2.0m)")
    else:
        print(f"    ✗ 没有匹配到同类型标注")

print("\n完成!")
