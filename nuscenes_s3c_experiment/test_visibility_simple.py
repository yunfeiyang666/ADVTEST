#!/usr/bin/env python
"""
简化的可见度筛选测试
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
from core_pipeline.coverage_evaluation.scene_filter import SceneGraphFilter

# 加载数据
print("=" * 80)
print("测试 nuImages 可见度筛选（简化版）")
print("=" * 80)

print("\n1. 加载 nuScenes...")
nusc = NuScenes(version='v1.0-mini', dataroot=config.NUSCENES_DATAROOT, verbose=False)

# 加载场景图
scene_graph_file = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\coverage_analysis\scene-0061_frame19_scene_graph.json"
with open(scene_graph_file, 'r', encoding='utf-8') as f:
    scene_graph = json.load(f)

scene_name = scene_graph['scene_name']
frame_idx = scene_graph['frame_idx']

print(f"\n2. 场景信息")
print(f"   场景: {scene_name}, Frame: {frame_idx}")
print(f"   节点数: {len(scene_graph['nodes'])}")

# 获取 sample_token
scene_rec = nusc.get('scene', nusc.field2token('scene', 'name', scene_name)[0])
sample = nusc.get('sample', scene_rec['first_sample_token'])
for _ in range(frame_idx):
    if sample['next']:
        sample = nusc.get('sample', sample['next'])
sample_token = sample['token']

print(f"   Sample token: {sample_token}")

# 创建筛选器
print(f"\n3. 创建筛选器（带 nuScenes 支持）")
filter_obj = SceneGraphFilter(
    mode='filtered',
    nusc=nusc,
    sample_token=sample_token
)

print(f"   nusc 是否为 None: {filter_obj.nusc is None}")
print(f"   sample_token: {filter_obj.sample_token}")

# 测试单个节点
print(f"\n4. 测试单个节点筛选")
test_node = [n for n in scene_graph['nodes'] if n.get('type') == 'pedestrian'][0]
print(f"   节点: {test_node['unique_id']}")
print(f"   类型: {test_node['type']}")

# 获取 visibility
vis = filter_obj._get_visibility_from_nuscenes(test_node)
print(f"   查询到的 visibility: {vis}")

if vis is not None:
    print(f"   ✓ 成功查询到 visibility")
    print(f"   visibility >= 阈值 ({filter_obj.MIN_VISIBILITY}): {vis >= filter_obj.MIN_VISIBILITY}")
else:
    print(f"   ✗ 未查询到 visibility")

# 检查缓存
print(f"\n5. 检查缓存")
print(f"   缓存大小: {len(filter_obj._visibility_cache)}")
if filter_obj._visibility_cache:
    for node_id, v in list(filter_obj._visibility_cache.items())[:3]:
        print(f"     {node_id}: {v:.2f}")

print("\n完成!")
