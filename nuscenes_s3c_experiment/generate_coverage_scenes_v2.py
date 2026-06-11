"""
为覆盖率分析生成代表性场景的场景图
基于已验证的 single_scene_demo.py 代码
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

from nuscenes.nuscenes import NuScenes
from pyquaternion import Quaternion
import config


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


def get_status_from_annotation(ann, velocity):
    """从annotation中提取status"""
    # 先看是否有attributes
    for attr in ann.get('attributes', []):
        if 'moving' in attr:
            return 'moving'
        elif 'stopped' in attr or 'parked' in attr:
            return 'stopped'
        elif 'with_rider' in attr:
            return 'with_rider'
        elif 'without_rider' in attr:
            return 'without_rider'
        elif 'standing' in attr or 'sitting' in attr:
            return 'stopped'
    
    # 根据速度判断
    if velocity is not None:
        speed = np.linalg.norm(velocity[:2])
        if speed > 0.5:
            return 'moving'
        else:
            return 'stopped'
    
    return 'unknown'


def generate_scene_graph(nusc, scene_name, frame_idx):
    """
    为指定场景的指定帧生成场景图
    使用已验证的代码逻辑
    """
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
        
        # 获取attributes
        attributes = []
        for attr_token in ann.get('attribute_tokens', []):
            attr = nusc.get('attribute', attr_token)
            attributes.append(attr['name'])
        
        # 获取status
        status = get_status_from_annotation(ann, velocity)
        
        annotations.append({
            'token': ann['token'],
            'category': ann['category_name'],
            'translation': ann['translation'],
            'rotation': ann['rotation'],
            'size': ann['size'],
            'velocity': list(velocity),
            'num_lidar_pts': ann.get('num_lidar_pts', 0),
            'status': status,
            'attributes': attributes
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
        
        obj_info = {
            'id': len(objects_list),
            'unique_id': unique_id,
            'type': obj_type,
            'category': ann['category'],
            'translation': ann['translation'],
            'rotation': ann['rotation'],
            'size': ann['size'],
            'velocity': ann.get('velocity', [0.0, 0.0, 0.0]),
            'token': ann['token'],
            'num_lidar_pts': ann.get('num_lidar_pts', 0),
            'status': ann.get('status', 'unknown'),
            'attributes': ann.get('attributes', []),
            'is_ego': False
        }
        
        objects_list.append(obj_info)
    
    # === 生成全关系（统一在ego frame中）===
    relationships = []
    
    # 提取ego的yaw角
    ego_yaw = quaternion_to_yaw(ego_pose['rotation'])
    
    for i, obj1 in enumerate(objects_list):
        for j, obj2 in enumerate(objects_list):
            if i == j:
                continue
            
            # 计算全局坐标系中的相对位置
            rel_pos_global = np.array(obj2['translation']) - np.array(obj1['translation'])
            
            # ✅ 转换到ego坐标系
            cos_yaw = np.cos(-ego_yaw)
            sin_yaw = np.sin(-ego_yaw)
            
            rel_x_ego = cos_yaw * rel_pos_global[0] - sin_yaw * rel_pos_global[1]
            rel_y_ego = sin_yaw * rel_pos_global[0] + cos_yaw * rel_pos_global[1]
            rel_z_ego = rel_pos_global[2]
            
            # 在ego坐标系中计算角度和距离
            distance = float(np.sqrt(rel_x_ego**2 + rel_y_ego**2))
            relative_angle = np.arctan2(rel_y_ego, rel_x_ego) * 180 / np.pi
            
            # 判断方位和距离
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
                        'x': round(float(rel_x_ego), 2),
                        'y': round(float(rel_y_ego), 2),
                        'z': round(float(rel_z_ego), 2)
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
                'status': obj.get('status', 'unknown'),
                'attributes': obj.get('attributes', [])
            }
            for obj in objects_list
        ],
        
        'relationships': relationships,
        
        'statistics': {
            'total_objects': len(objects_list),
            'total_relationships': len(relationships),
            'object_type_count': dict(type_counters)
        }
    }
    
    return scene_graph


def main():
    print("=" * 70)
    print("  生成代表性场景的场景图（基于已验证代码）")
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
            "description": "停车卡车、施工路口、跟随货车"
        },
        {
            "name": "scene-0796",
            "frame": 39,
            "type": "低密度场景",
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
        scene_graph = generate_scene_graph(
            nusc,
            scene_config['name'],
            scene_config['frame']
        )
        
        if not scene_graph:
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
            "object_count": stats['total_objects'],
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
    
    print("\n生成的场景:")
    for scene in generated_scenes:
        print(f"  - {scene['type']}: {scene['scene_name']} 帧{scene['frame']}")
        print(f"    对象数: {scene['object_count']}")
        print(f"    文件: {scene['filepath']}")
    
    print("\n下一步:")
    print("  1. 导入Neo4j数据库: python import_single_scene_to_neo4j.py")
    print("  2. 测试VQA问题覆盖率")


if __name__ == "__main__":
    main()
