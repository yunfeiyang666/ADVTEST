"""
使用8方位系统重新生成scene-0553 frame 8的场景图
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


def simplify_category(category):
    """简化对象类别"""
    mapping = config.CATEGORY_MAPPING
    return mapping.get(category, None)


def quaternion_to_yaw(rotation):
    """从四元数提取yaw角（弧度）"""
    q = Quaternion(rotation)
    yaw = q.yaw_pitch_roll[0]
    return yaw


def get_direction_predicate(angle):
    """
    根据角度判断方位（8方位系统）
    
    8方位定义（每个方位45度）：
    - front: -22.5° ~ 22.5°
    - front-left: 22.5° ~ 67.5°
    - left: 67.5° ~ 112.5°
    - back-left: 112.5° ~ 157.5°
    - back: 157.5° ~ 180° 和 -180° ~ -157.5°
    - back-right: -157.5° ~ -112.5°
    - right: -112.5° ~ -67.5°
    - front-right: -67.5° ~ -22.5°
    """
    angle = ((angle + 180) % 360) - 180
    
    if -22.5 <= angle < 22.5:
        return 'front'
    elif 22.5 <= angle < 67.5:
        return 'front-left'
    elif 67.5 <= angle < 112.5:
        return 'left'
    elif 112.5 <= angle < 157.5:
        return 'back-left'
    elif angle >= 157.5 or angle < -157.5:
        return 'back'
    elif -157.5 <= angle < -112.5:
        return 'back-right'
    elif -112.5 <= angle < -67.5:
        return 'right'
    else:  # -67.5 <= angle < -22.5
        return 'front-right'


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
    print(f"Sample token: {sample_token}")
    
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
        
        # 获取attributes
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
            'attributes': attribute_names
        })
    
    # 生成对象列表
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
            'attributes': attributes,
            'status': status_engine.format_for_neo4j(inferred_status),
            'is_ego': False
        }
        
        objects_list.append(obj_info)
    
    # 生成全关系
    relationships = []
    
    for i, obj1 in enumerate(objects_list):
        for j, obj2 in enumerate(objects_list):
            if i == j:
                continue
            
            # 计算相对位置
            rel_pos = np.array(obj2['translation']) - np.array(obj1['translation'])
            distance = float(np.linalg.norm(rel_pos[:2]))
            
            # 计算绝对角度
            absolute_angle = np.arctan2(rel_pos[1], rel_pos[0])
            
            # 获取源对象朝向
            source_yaw = quaternion_to_yaw(obj1['rotation'])
            
            # 计算相对角度
            relative_angle = (absolute_angle - source_yaw) * 180 / np.pi
            
            # 判断方位和距离（使用8方位系统）
            direction = get_direction_predicate(relative_angle)
            distance_level = get_distance_predicate(distance)
            
            relation = {
                'source': obj1['unique_id'],
                'source_type': obj1['type'],
                'target': obj2['unique_id'],
                'target_type': obj2['type'],
                'predicates': [direction, distance_level],
                'metrics': {
                    'distance': round(distance, 2),
                    'angle': round(float(relative_angle), 1),
                    'relative_position': {
                        'x': round(float(rel_pos[0]), 2),
                        'y': round(float(rel_pos[1]), 2),
                        'z': round(float(rel_pos[2]), 2)
                    }
                }
            }
            
            relationships.append(relation)
    
    # 构建场景图
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
    print("  使用8方位系统重新生成 scene-0553 frame 8 场景图")
    print("=" * 70)
    
    # 加载NuScenes (trainval完整版)
    print("\n加载NuScenes数据集 (v1.0-trainval)...")
    nusc = NuScenes(
        version='v1.0-trainval',
        dataroot='E:/Project/ADVTEST/data/nuscenes',
        verbose=False
    )
    print(f"✓ 已加载 {len(nusc.scene)} 个场景")
    
    # 生成场景图
    scene_name = 'scene-0553'
    frame_idx = 8
    
    print(f"\n生成 {scene_name} 帧{frame_idx} 场景图...")
    scene_graph = generate_scene_graph(nusc, scene_name, frame_idx)
    
    if not scene_graph:
        print("❌ 场景图生成失败")
        return
    
    # 统计信息
    stats = scene_graph['statistics']
    print(f"\n✓ 场景图生成完成")
    print(f"  对象数量: {stats['total_objects']}")
    print(f"  关系数量: {stats['total_relationships']}")
    
    # 验证8方位
    direction_counts = defaultdict(int)
    for edge in scene_graph['edges']:
        direction_counts[edge['predicates'][0]] += 1
    
    print(f"\n方位分布（8方位系统）:")
    for direction, count in sorted(direction_counts.items()):
        print(f"  {direction}: {count}")
    
    # 验证bicycle与truck的关系
    print(f"\n=== Bicycle与Truck的关系验证 ===")
    for edge in scene_graph['edges']:
        if edge['source'] == 'bicycle1' and 'truck' in edge['target']:
            target_node = next((n for n in scene_graph['nodes'] if n['unique_id'] == edge['target']), None)
            if target_node:
                print(f"  {edge['source']} -[{edge['predicates']}]-> {edge['target']} (status={target_node['status']})")
    
    # 保存场景图
    output_dir = os.path.join(config.OUTPUT_DIR, "coverage_analysis", "scene_graphs")
    os.makedirs(output_dir, exist_ok=True)
    
    filename = f"{scene_name}_frame{frame_idx}_scene_graph.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(scene_graph, f, indent=2, ensure_ascii=False)
    
    file_size = os.path.getsize(filepath) / 1024
    print(f"\n✓ 场景图已保存: {filepath}")
    print(f"  文件大小: {file_size:.1f} KB")
    
    print("\n下一步:")
    print("  1. 重新导入Neo4j: python vqa_pipeline/import_to_neo4j.py")
    print("  2. 重新测试VQA")


if __name__ == "__main__":
    main()
