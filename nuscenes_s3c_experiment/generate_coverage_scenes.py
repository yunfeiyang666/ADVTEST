"""
为覆盖率分析生成代表性场景的场景图
场景1: scene-0061 帧19 (高密度，156个对象)
场景2: scene-0796 帧39 (低密度，8个对象)
"""
import os
import sys
import json

# 添加本地nuscenes-devkit路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nuscenes.nuscenes import NuScenes
from pyquaternion import Quaternion
import numpy as np
from collections import defaultdict
import config

# 导入场景图生成函数
from step2_full_relation_scene_graph import (
    process_scene_full_relation,
    simplify_category
)


def generate_scene_graph_for_frame(nusc, scene_name, frame_idx):
    """为指定场景的指定帧生成场景图"""
    # 找到场景
    scene = None
    for s in nusc.scene:
        if s['name'] == scene_name:
            scene = s
            break
    
    if not scene:
        print(f"❌ 未找到场景: {scene_name}")
        return None
    
    # 找到指定帧
    sample_token = scene['first_sample_token']
    current_frame = 0
    
    while sample_token and current_frame < frame_idx:
        sample = nusc.get('sample', sample_token)
        sample_token = sample['next']
        current_frame += 1
    
    if not sample_token:
        print(f"❌ 帧索引超出范围: {frame_idx}")
        return None
    
    # 生成场景图
    sample = nusc.get('sample', sample_token)
    
    # 获取ego pose
    sample_data = nusc.get('sample_data', sample['data']['LIDAR_TOP'])
    ego_pose_record = nusc.get('ego_pose', sample_data['ego_pose_token'])
    
    # 获取所有标注
    annotations = []
    for ann_token in sample['anns']:
        ann = nusc.get('sample_annotation', ann_token)
        # 修正字段名：category_name -> category
        ann['category'] = ann.get('category_name', ann.get('category', ''))
        annotations.append(ann)
    
    # 构建场景数据
    scene_data = {
        'scene_name': scene_name,
        'sample_token': sample['token'],
        'timestamp': sample['timestamp'],
        'ego_pose': {
            'translation': ego_pose_record['translation'],
            'rotation': ego_pose_record['rotation']
        },
        'annotations': annotations
    }
    
    # 使用step2的函数生成场景图
    scene_graph = process_scene_full_relation(scene_data)
    
    return scene_graph


def main():
    print("=" * 70)
    print("  生成代表性场景的场景图")
    print("=" * 70)
    
    # 加载NuScenes
    print("\n加载NuScenes数据集...")
    nusc = NuScenes(
        version='v1.0-mini',
        dataroot=config.NUSCENES_DATAROOT,
        verbose=False
    )
    print(f"✓ 已加载 {len(nusc.scene)} 个场景")
    
    # 定义要生成的场景
    scenes_to_generate = [
        {
            "name": "scene-0061",
            "frame": 19,
            "type": "高密度场景",
            "expected_objects": 156,
            "description": "停车卡车、施工路口、跟随货车"
        },
        {
            "name": "scene-0796",
            "frame": 39,
            "type": "低密度场景",
            "expected_objects": 8,
            "description": "踏板车、行人、公交、过路口"
        }
    ]
    
    # 创建输出目录
    output_dir = os.path.join(config.OUTPUT_DIR, "coverage_analysis")
    os.makedirs(output_dir, exist_ok=True)
    
    generated_scenes = []
    
    # 为每个场景生成场景图
    for scene_config in scenes_to_generate:
        print(f"\n{'=' * 70}")
        print(f"  处理 {scene_config['type']}: {scene_config['name']} 帧{scene_config['frame']}")
        print(f"  描述: {scene_config['description']}")
        print("=" * 70)
        
        # 生成场景图
        scene_graph = generate_scene_graph_for_frame(
            nusc,
            scene_config['name'],
            scene_config['frame']
        )
        
        if not scene_graph:
            continue
        
        # 统计对象
        obj_count = len(scene_graph['nodes'])
        print(f"\n✓ 场景图生成完成")
        print(f"  对象数量: {obj_count}")
        
        # 统计对象类型
        type_count = {}
        for node in scene_graph['nodes']:
            obj_type = node['type']
            type_count[obj_type] = type_count.get(obj_type, 0) + 1
        
        print(f"  对象类型分布:")
        for obj_type, count in sorted(type_count.items(), key=lambda x: -x[1]):
            print(f"    {obj_type}: {count}")
        
        # 保存场景图
        filename = f"{scene_config['name']}_frame{scene_config['frame']}_scene_graph.json"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(scene_graph, f, indent=2, ensure_ascii=False)
        
        file_size = os.path.getsize(filepath) / 1024
        print(f"\n✓ 场景图已保存: {filepath}")
        print(f"  文件大小: {file_size:.1f} KB")
        
        generated_scenes.append({
            "scene_name": scene_config['name'],
            "frame": scene_config['frame'],
            "type": scene_config['type'],
            "description": scene_config['description'],
            "object_count": obj_count,
            "filepath": filepath
        })
    
    # 保存场景清单
    manifest_path = os.path.join(output_dir, "scenes_manifest.json")
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(generated_scenes, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'=' * 70}")
    print("  生成完成")
    print("=" * 70)
    print(f"\n✓ 共生成 {len(generated_scenes)} 个场景的场景图")
    print(f"✓ 场景清单已保存: {manifest_path}")
    
    print("\n下一步:")
    print("  1. 导入Neo4j数据库")
    print("  2. 测试VQA问题覆盖率")


if __name__ == "__main__":
    main()
