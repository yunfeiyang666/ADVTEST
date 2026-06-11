"""快速重新生成scene-0103 frame38"""
import sys
sys.path.insert(0, r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk")

from generate_coverage_scenes_v2 import *
import json
import os
import config

# 加载NuScenes
print("加载NuScenes...")
print(f"数据路径: {config.NUSCENES_DATAROOT}")
nusc = NuScenes(version=config.NUSCENES_VERSION, dataroot=config.NUSCENES_DATAROOT, verbose=False)

# 生成scene-0103 frame38
print("生成scene-0103 frame38...")
sg = generate_scene_graph(nusc, 'scene-0103', 38)

if sg:
    output_dir = 'output/coverage_analysis/scene_graphs'
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, 'scene-0103_frame38_scene_graph.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sg, f, indent=2, ensure_ascii=False)
    
    print(f"✓ 已保存: {output_path}")
    print(f"  对象数: {len(sg['nodes'])}")
    print(f"  关系数: {len(sg['relationships'])}")
else:
    print("❌ 生成失败")
