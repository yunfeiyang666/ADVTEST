"""
为选定的6个场景生成场景图
基于已验证的代码
"""
import os
import sys
import json
import numpy as np
from collections import defaultdict

# 添加本地nuscenes-devkit路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nuscenes.nuscenes import NuScenes
from pyquaternion import Quaternion
import config
from vqa_pipeline.status_inference import StatusInferenceEngine
from vqa_pipeline.direction_utils import (
    quaternion_to_yaw,
    compute_direction_features,
)


def simplify_category(category):
    """简化对象类别"""
    mapping = config.CATEGORY_MAPPING
    return mapping.get(category, None)


def get_distance_predicate(distance):
    """根据距离判断距离级别"""
    if distance <= 10:
        return 'near'
    elif distance <= 25:
        return 'mid'
    else:
        return 'far'


def get_attribute_names(nusc, attribute_tokens):
    """获取attribute的名称列表"""
    attributes = []
    for token in attribute_tokens:
        try:
            attr = nusc.get('attribute', token)
            attributes.append(attr['name'])
        except:
            pass
    return attributes


def generate_scene_graph(nusc, scene_name, frame_idx):
    """为指定场景的指定帧生成场景图"""
    # 初始化状态推断引擎
    status_engine = StatusInferenceEngine()
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
    
    sample = nusc.get('sample', sample_token)
    
    # 获取Ego车姿态
    lidar_token = sample['data']['LIDAR_TOP']
    lidar_data = nusc.get('sample_data', lidar_token)
    ego_pose = nusc.get('ego_pose', lidar_data['ego_pose_token'])
    
    # 获取所有标注对象
    annotations = []
    for ann_token in sample['anns']:
        ann = nusc.get('sample_annotation', ann_token)
        
        # 获取速度
        try:
            velocity = nusc.box_velocity(ann_token)
            if velocity is None or np.any(np.isnan(velocity)):
                velocity = [0.0, 0.0, 0.0]
        except:
            velocity = [0.0, 0.0, 0.0]
        
        # 获取attributes（包含with_rider等状态）
        attribute_tokens = ann.get('attribute_tokens', [])
        attribute_names = get_attribute_names(nusc, attribute_tokens)
        
        annotations.append({
            'token': ann['token'],
            'category': ann['category_name'],
            'translation': ann['translation'],
            'rotation': ann['rotation'],
            'size': ann['size'],
            'velocity': list(velocity),
            'num_lidar_pts': ann.get('num_lidar_pts', 0),
            'attributes': attribute_names  # 新增：保留attributes
        })
    
    # === 生成对象列表（带唯一ID）===
    objects_list = []
    type_counters = defaultdict(int)
    
    # 添加ego车
    ego_obj = {
        'id': 'ego',
        'unique_id': 'ego',
        'type': 'ego',
        'translation': ego_pose['translation'],
        'rotation': ego_pose['rotation'],
        'is_ego': True
    }
    objects_list.append(ego_obj)
    
    # 处理其他对象
    for ann in annotations:
        obj_type = simplify_category(ann['category'])
        if obj_type is None:
            continue
        
        type_counters[obj_type] += 1
        unique_id = f"{obj_type}{type_counters[obj_type]}"
        
        # 推断状态
        attributes = ann.get('attributes', [])
        velocity = ann.get('velocity', [0.0, 0.0, 0.0])
        inferred_status = status_engine.infer_status({
            'type': obj_type,
            'attributes': attributes,
            'velocity': velocity
        })
        
        obj_info = {
            'id': len(objects_list),
            'unique_id': unique_id,
            'type': obj_type,
            'category': ann['category'],
            'translation': ann['translation'],
            'rotation': ann['rotation'],
            'size': ann['size'],
            'velocity': velocity,
            'token': ann['token'],
            'num_lidar_pts': ann.get('num_lidar_pts', 0),
            'attributes': attributes,  # 新增：保留attributes
            'status': status_engine.format_for_neo4j(inferred_status),  # 新增：推断的状态
            'is_ego': False
        }
        
        objects_list.append(obj_info)
    
    # === 生成全关系 ===
    relationships = []
    
    # 获取Ego的朝向（作为全局参考系）
    # 🔄 重要改动：所有方向关系都基于 Ego 的朝向计算（Ego Frame）
    ego_rotation = ego_obj['rotation']
    ego_yaw = quaternion_to_yaw(ego_rotation)  # 保留以便调试/一致性
    
    for i, obj1 in enumerate(objects_list):
        for j, obj2 in enumerate(objects_list):
            if i == j:
                continue
            
            # 🔄 核心改动：使用 Ego 的朝向而非 source 的朝向
            # 这样所有方向都是相对于 Ego 车的视角，符合驾驶场景直觉
            norm_angle, distance, direction_8, direction_4, rel_pos = compute_direction_features(
                obj1['translation'], obj2['translation'], ego_rotation  # 使用 ego_rotation！
            )
            distance_level = get_distance_predicate(distance)
            
            relation = {
                'source': obj1['unique_id'],
                'source_type': obj1['type'],
                'target': obj2['unique_id'],
                'target_type': obj2['type'],
                'predicates': [direction_8, distance_level],  # 主要方向仍用8方位
                'direction_4': direction_4,  # 4方位方向
                'direction_8': direction_8,  # 8方位方向
                'metrics': {
                    'distance': round(distance, 2),
                    'angle': round(float(norm_angle), 1),
                    'relative_position': {
                        'x': round(float(rel_pos[0]), 2),
                        'y': round(float(rel_pos[1]), 2),
                        'z': round(float(rel_pos[2]), 2)
                    }
                }
            }
            
            relationships.append(relation)
    
    # === 构建场景图 ===
    scene_graph = {
        'scene_name': scene_name,
        'frame_idx': frame_idx,
        'timestamp': sample['timestamp'],
        'description': scene['description'],
        
        'nodes': [
            {
                'unique_id': obj['unique_id'],
                'type': obj['type'],
                'category': obj.get('category', obj['type']),
                'translation': {
                    'x': round(float(obj['translation'][0]), 2),
                    'y': round(float(obj['translation'][1]), 2),
                    'z': round(float(obj['translation'][2]), 2)
                },
                'rotation': [round(float(r), 4) for r in obj['rotation']],
                'size': {
                    'width': round(float(obj['size'][0]), 2) if not obj['is_ego'] else 0,
                    'length': round(float(obj['size'][1]), 2) if not obj['is_ego'] else 0,
                    'height': round(float(obj['size'][2]), 2) if not obj['is_ego'] else 0
                } if not obj['is_ego'] else None,
                'velocity': {
                    'vx': round(float(obj['velocity'][0]), 2) if not obj['is_ego'] else 0,
                    'vy': round(float(obj['velocity'][1]), 2) if not obj['is_ego'] else 0,
                    'vz': round(float(obj['velocity'][2]), 2) if not obj['is_ego'] else 0
                } if not obj['is_ego'] else None,
                'num_lidar_pts': obj.get('num_lidar_pts', 0) if not obj['is_ego'] else 0,
                # 🆕 新增：保存status和attributes字段
                'status': obj.get('status', 'unknown'),
                'attributes': obj.get('attributes', [])
            }
            for obj in objects_list
        ],
        
        'edges': relationships,
        
        'statistics': {
            'total_objects': len(objects_list),
            'total_relationships': len(relationships),
            'object_type_count': dict(type_counters)
        }
    }
    
    return scene_graph


def main():
    print("=" * 70)
    print("  生成选定场景的场景图")
    print("=" * 70)
    
    # 加载NuScenes
    print("\n加载NuScenes数据集...")
    nusc = NuScenes(
        version='v1.0-mini',
        dataroot=config.NUSCENES_DATAROOT,
        verbose=False
    )
    print(f"✓ 已加载 {len(nusc.scene)} 个场景")
    
    # 加载选定的场景
    selection_file = os.path.join(config.OUTPUT_DIR, "coverage_analysis", "selected_scenes.json")
    with open(selection_file, 'r', encoding='utf-8') as f:
        selected_scenes = json.load(f)
    
    print(f"✓ 加载了 {len(selected_scenes)} 个选定场景")
    
    # 创建输出目录
    output_dir = os.path.join(config.OUTPUT_DIR, "coverage_analysis", "scene_graphs")
    os.makedirs(output_dir, exist_ok=True)
    
    # 为每个场景生成场景图
    generated = []
    
    for i, scene_info in enumerate(selected_scenes, 1):
        scene_name = scene_info['scene_name']
        frame_idx = scene_info['frame_idx']
        
        print(f"\n{'=' * 70}")
        print(f"  [{i}/{len(selected_scenes)}] {scene_name} 帧{frame_idx}")
        print(f"  描述: {scene_info['scene_description']}")
        print(f"  预期对象数: {scene_info['total_objects']}")
        print("=" * 70)
        
        # 生成场景图
        scene_graph = generate_scene_graph(nusc, scene_name, frame_idx)
        
        if not scene_graph:
            print("❌ 场景图生成失败")
            continue
        
        # 统计信息
        stats = scene_graph['statistics']
        print(f"\n✓ 场景图生成完成")
        print(f"  对象数量: {stats['total_objects']}")
        print(f"  关系数量: {stats['total_relationships']}")
        print(f"  对象类型分布:")
        for obj_type, count in sorted(stats['object_type_count'].items(), key=lambda x: -x[1]):
            print(f"    {obj_type}: {count}")
        
        # 保存场景图
        filename = f"{scene_name}_frame{frame_idx}_scene_graph.json"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(scene_graph, f, indent=2, ensure_ascii=False)
        
        file_size = os.path.getsize(filepath) / 1024
        print(f"\n✓ 场景图已保存")
        print(f"  文件: {filepath}")
        print(f"  大小: {file_size:.1f} KB")
        
        generated.append({
            'scene_name': scene_name,
            'frame_idx': frame_idx,
            'description': scene_info['scene_description'],
            'total_objects': scene_info['total_objects'],
            'type_count': scene_info['type_count'],
            'filepath': filepath
        })
    
    # 保存生成清单
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(generated, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'=' * 70}")
    print("  生成完成")
    print("=" * 70)
    print(f"\n✓ 共生成 {len(generated)} 个场景的场景图")
    print(f"✓ 清单已保存: {manifest_path}")
    
    # 分组显示
    print("\n【生成的场景】")
    print("\n组1:")
    for scene in generated[:3]:
        print(f"  - {scene['scene_name']} 帧{scene['frame_idx']}")
        print(f"    对象数: {scene['total_objects']}")
        print(f"    描述: {scene['description']}")
    
    print("\n组2:")
    for scene in generated[3:]:
        print(f"  - {scene['scene_name']} 帧{scene['frame_idx']}")
        print(f"    对象数: {scene['total_objects']}")
        print(f"    描述: {scene['description']}")
    
    print("\n下一步:")
    print("  python test_coverage_vqa_v2.py")


if __name__ == "__main__":
    main()
