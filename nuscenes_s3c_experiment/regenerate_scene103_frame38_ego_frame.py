"""
重新生成 scene-0103 frame38 的场景图
使用修复后的ego frame方位计算方法
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


def quaternion_to_yaw(quaternion):
    """从四元数提取yaw角（弧度）"""
    if isinstance(quaternion, list):
        q = Quaternion(quaternion)
    else:
        q = quaternion
    yaw = q.yaw_pitch_roll[0]
    return yaw


def calculate_relative_position_in_ego_frame(obj1_translation, obj2_translation, ego_rotation):
    """
    计算obj2相对于obj1的位置，统一转换到ego车的坐标系
    """
    # 计算全局坐标系中的相对位置
    rel_x_global = obj2_translation[0] - obj1_translation[0]
    rel_y_global = obj2_translation[1] - obj1_translation[1]
    rel_z_global = obj2_translation[2] - obj1_translation[2]
    
    # 提取ego车的yaw角
    ego_yaw = quaternion_to_yaw(ego_rotation)
    
    # 转换到ego坐标系（旋转矩阵）
    cos_yaw = np.cos(-ego_yaw)
    sin_yaw = np.sin(-ego_yaw)
    
    rel_x_ego = cos_yaw * rel_x_global - sin_yaw * rel_y_global
    rel_y_ego = sin_yaw * rel_x_global + cos_yaw * rel_y_global
    rel_z_ego = rel_z_global
    
    # 在ego坐标系中计算角度（前方为0度）
    angle = np.arctan2(rel_y_ego, rel_x_ego) * 180 / np.pi
    
    return [rel_x_ego, rel_y_ego, rel_z_ego], angle


def get_direction_predicate(angle):
    """
    根据角度判断方位（8方位系统）
    在ego坐标系中：前方为0度，左为正，右为负
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
    else:
        return 'front-right'


def get_distance_predicate(distance):
    """根据距离判断距离级别"""
    if distance <= 10:
        return 'near'
    elif distance <= 25:
        return 'mid'
    else:
        return 'far'


def simplify_category(category):
    """简化对象类别"""
    mapping = config.CATEGORY_MAPPING
    return mapping.get(category, None)


def get_status_from_annotation(ann, velocity):
    """从标注中提取状态信息"""
    attributes = ann.get('attribute_tokens', [])
    
    for attr_token in attributes:
        attr = nusc.get('attribute', attr_token)
        attr_name = attr['name']
        
        # 映射attribute到status
        if 'moving' in attr_name:
            return 'moving'
        elif 'stopped' in attr_name:
            return 'stopped'
        elif 'parked' in attr_name:
            return 'stopped'
        elif 'with_rider' in attr_name:
            return 'with_rider'
        elif 'without_rider' in attr_name:
            return 'without_rider'
        elif 'standing' in attr_name:
            return 'stopped'
        elif 'sitting' in attr_name:
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
    """为指定场景的指定帧生成场景图（使用ego frame）"""
    print(f"正在生成场景图: {scene_name} 帧{frame_idx}")
    
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
    
    print(f"  Ego位置: ({ego_pose['translation'][0]:.2f}, {ego_pose['translation'][1]:.2f})")
    print(f"  Ego朝向: {quaternion_to_yaw(ego_pose['rotation']) * 180 / np.pi:.1f}°")
    
    # 获取所有标注对象
    objects_list = []
    type_counters = defaultdict(int)
    
    # 添加ego车
    ego_obj = {
        'unique_id': 'ego',
        'type': 'ego',
        'category': 'ego',
        'translation': ego_pose['translation'],
        'rotation': ego_pose['rotation'],
        'is_ego': True
    }
    objects_list.append(ego_obj)
    
    # 处理其他对象
    for ann_token in sample['anns']:
        ann = nusc.get('sample_annotation', ann_token)
        
        # 简化类别
        obj_type = simplify_category(ann['category_name'])
        if obj_type is None:
            continue
        
        # 获取速度
        try:
            velocity = nusc.box_velocity(ann_token)
            if velocity is None or np.any(np.isnan(velocity)):
                velocity = [0.0, 0.0, 0.0]
        except:
            velocity = [0.0, 0.0, 0.0]
        
        # 获取状态
        status = get_status_from_annotation(ann, velocity)
        
        # 获取attributes
        attributes = []
        for attr_token in ann.get('attribute_tokens', []):
            attr = nusc.get('attribute', attr_token)
            attributes.append(attr['name'])
        
        type_counters[obj_type] += 1
        unique_id = f"{obj_type}{type_counters[obj_type]}"
        
        obj_info = {
            'unique_id': unique_id,
            'type': obj_type,
            'category': ann['category_name'],
            'translation': ann['translation'],
            'rotation': ann['rotation'],
            'size': ann['size'],
            'velocity': list(velocity),
            'num_lidar_pts': ann.get('num_lidar_pts', 0),
            'status': status,
            'attributes': attributes,
            'is_ego': False
        }
        
        objects_list.append(obj_info)
    
    print(f"  对象数量: {len(objects_list)}")
    
    # === 生成全关系（统一在ego frame中）===
    relationships = []
    
    for i, obj1 in enumerate(objects_list):
        for j, obj2 in enumerate(objects_list):
            if i == j:
                continue
            
            # ✅ 使用ego frame计算相对位置和角度
            rel_pos_ego, rel_angle_ego = calculate_relative_position_in_ego_frame(
                obj1['translation'],
                obj2['translation'],
                ego_pose['rotation']  # 使用ego的朝向作为参考系
            )
            
            # 计算距离
            distance = float(np.linalg.norm(rel_pos_ego[:2]))
            
            # 在ego坐标系中判断方位
            direction = get_direction_predicate(rel_angle_ego)
            distance_level = get_distance_predicate(distance)
            
            relation = {
                'source': obj1['unique_id'],
                'target': obj2['unique_id'],
                'predicates': [direction, distance_level],
                'distance': round(distance, 2),
                'angle': round(rel_angle_ego, 1)
            }
            
            relationships.append(relation)
    
    print(f"  关系数量: {len(relationships)}")
    
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
                'rotation': [round(float(x), 4) for x in obj['rotation']],
                'size': {
                    'width': round(float(obj['size'][0]), 2),
                    'length': round(float(obj['size'][1]), 2),
                    'height': round(float(obj['size'][2]), 2)
                } if 'size' in obj else None,
                'velocity': {
                    'vx': round(float(obj['velocity'][0]), 2),
                    'vy': round(float(obj['velocity'][1]), 2),
                    'vz': round(float(obj['velocity'][2]), 2)
                } if 'velocity' in obj else None,
                'num_lidar_pts': obj.get('num_lidar_pts', 0),
                'status': obj.get('status', 'unknown'),
                'attributes': obj.get('attributes', [])
            }
            for obj in objects_list
        ],
        'edges': relationships
    }
    
    return scene_graph


# 主程序
if __name__ == '__main__':
    print("=" * 80)
    print("重新生成 scene-0103 frame38 场景图（使用ego frame）")
    print("=" * 80)
    print()
    
    # 加载NuScenes数据集
    print("加载NuScenes数据集...")
    nusc = NuScenes(version='v1.0-mini', dataroot=config.NUSCENES_DATAROOT, verbose=False)
    print("✓ 数据集加载完成")
    print()
    
    # 生成场景图
    scene_graph = generate_scene_graph(nusc, 'scene-0103', 38)
    
    if scene_graph:
        # 保存到文件
        output_dir = 'output/coverage_analysis/scene_graphs'
        os.makedirs(output_dir, exist_ok=True)
        
        output_path = os.path.join(output_dir, 'scene-0103_frame38_scene_graph.json')
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(scene_graph, f, indent=2, ensure_ascii=False)
        
        print()
        print("=" * 80)
        print(f"✓ 场景图已保存: {output_path}")
        print()
        print("统计信息:")
        print(f"  - 对象数量: {len(scene_graph['nodes'])}")
        print(f"  - 关系数量: {len(scene_graph['edges'])}")
        print()
        print("下一步：运行QA测试")
        print("  python run_official_qa_enhanced.py")
        print("=" * 80)
    else:
        print("❌ 场景图生成失败")
