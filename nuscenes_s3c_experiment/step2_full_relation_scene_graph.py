"""
步骤2改进版: 生成全关系场景图（满足老师要求）

改进点：
1. 为每个对象添加唯一ID（car1, car2, pedestrian1等）
2. 生成全关系图（所有对象之间的关系，不只是ego-其他）
3. 简化谓词为方位+距离
4. 以ego车为参考系
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

from tqdm import tqdm
import config


def quaternion_to_yaw(quaternion):
    """
    从四元数提取yaw角
    """
    if len(quaternion) == 4:
        w, x, y, z = quaternion
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = np.arctan2(siny_cosp, cosy_cosp)
        return yaw
    return 0.0


def normalize_angle(angle):
    """
    归一化角度到 [-180, 180] 范围
    """
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


def calculate_relative_position_in_source_frame(obj1_translation, obj2_translation, source_rotation):
    """
    计算obj2相对于obj1的位置，使用source对象的坐标系 (Source Frame)
    
    说明:
    - 以source对象的朝向为参考，source的前方为0度
    - 这样对于静止物体（如停着的卡车、摩托车），可以使用其朝向作为参考
    
    参数：
        obj1_translation: source对象的全局位置
        obj2_translation: target对象的全局位置
        source_rotation: source对象的旋转四元数
    
    返回：
        相对位置向量和角度（度）
    """
    # 计算全局坐标系中的相对位置
    rel_x_global = obj2_translation[0] - obj1_translation[0]
    rel_y_global = obj2_translation[1] - obj1_translation[1]
    rel_z_global = obj2_translation[2] - obj1_translation[2]
    
    # 提取source对象的yaw角
    source_yaw = quaternion_to_yaw(source_rotation)
    
    # 转换到source坐标系（旋转矩阵）
    cos_yaw = np.cos(-source_yaw)
    sin_yaw = np.sin(-source_yaw)
    
    rel_x_source = cos_yaw * rel_x_global - sin_yaw * rel_y_global
    rel_y_source = sin_yaw * rel_x_global + cos_yaw * rel_y_global
    rel_z_source = rel_z_global
    
    # 计算角度：使用atan2计算全局角度，然后转到source坐标系
    world_angle = np.arctan2(rel_y_global, rel_x_global)
    rel_deg = (world_angle - source_yaw) * 180.0 / np.pi
    angle = normalize_angle(rel_deg)
    
    return [rel_x_source, rel_y_source, rel_z_source], angle


def calculate_relative_position_in_ego_frame(obj1_translation, obj2_translation, ego_rotation):
    """
    计算obj2相对于obj1的位置，使用ego车的坐标系 (Ego Frame)
    
    说明:
    - 以ego车的朝向为参考，ego的前方为0度
    - 所有对象的方向都以ego的视角表示
    
    参数：
        obj1_translation: source对象的全局位置
        obj2_translation: target对象的全局位置
        ego_rotation: ego车的旋转四元数
    
    返回：
        相对位置向量和角度（度）
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
    
    # 计算角度：使用atan2计算全局角度，然后转到ego坐标系
    world_angle = np.arctan2(rel_y_global, rel_x_global)
    rel_deg = (world_angle - ego_yaw) * 180.0 / np.pi
    angle = normalize_angle(rel_deg)
    
    return [rel_x_ego, rel_y_ego, rel_z_ego], angle


def get_direction_labels(angle):
    """
    根据角度判断方位，使用新的重叠角度范围定义
    
    三套方位定义：
    - 2方位：前/后各180度
    - 4方位：前右/前左/后右/后左各90度
    - 8方位：8个方向各45度（传统定义）
    
    参数：
        angle: 角度（度），范围[-180, 180]，前方为0度
    
    返回：
        dict: {
            'direction_2': ['front'] or ['back'],
            'direction_4': ['front-left'] or ['front-right'] or ['back-left'] or ['back-right'],
            'direction_8': 'front' / 'front-left' / 'left' / 'back-left' / 'back' / 'back-right' / 'right' / 'front-right',
            'angle_matches': ['front', 'front-left', ...]  # 所有匹配的方位标签列表
        }
    """
    # 归一化到[-180, 180]
    angle = ((angle + 180) % 360) - 180
    
    # 第一套：2方位（前/后各180度）
    if -90 <= angle < 90:
        direction_2 = ['front']
    else:
        direction_2 = ['back']
    
    # 第二套：4方位（各90度）
    if -45 <= angle < 45:
        direction_4 = ['front-right'] if angle < 0 else (['front-left'] if angle > 0 else ['front-left', 'front-right'])
    elif 45 <= angle < 135:
        direction_4 = ['front-left'] if angle < 90 else (['back-left'] if angle > 90 else ['front-left', 'back-left'])
    elif -135 <= angle < -45:
        direction_4 = ['front-right'] if angle > -90 else (['back-right'] if angle < -90 else ['front-right', 'back-right'])
    else:  # 135 <= angle or angle < -135
        direction_4 = ['back-right'] if angle < 0 else (['back-left'] if angle > 0 else ['back-left', 'back-right'])
    
    # 第三套：8方位（传统45度划分）
    if -22.5 <= angle < 22.5:
        direction_8 = 'front'
    elif 22.5 <= angle < 67.5:
        direction_8 = 'front-left'
    elif 67.5 <= angle < 112.5:
        direction_8 = 'left'
    elif 112.5 <= angle < 157.5:
        direction_8 = 'back-left'
    elif angle >= 157.5 or angle < -157.5:
        direction_8 = 'back'
    elif -157.5 <= angle < -112.5:
        direction_8 = 'back-right'
    elif -112.5 <= angle < -67.5:
        direction_8 = 'right'
    else:  # -67.5 <= angle < -22.5
        direction_8 = 'front-right'
    
    # 合并所有匹配的方位标签
    angle_matches = list(set(direction_2 + direction_4 + [direction_8]))
    
    return {
        'direction_2': direction_2,
        'direction_4': direction_4,
        'direction_8': direction_8,
        'angle_matches': angle_matches
    }


def get_distance_predicate(distance):
    """
    根据距离判断距离级别
    """
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


def load_raw_data():
    """加载步骤1的原始数据"""
    raw_data_path = os.path.join(config.OUTPUT_DIR, 'raw_scenes_data.json')
    
    if not os.path.exists(raw_data_path):
        raise FileNotFoundError(f"找不到原始数据文件: {raw_data_path}\n请先运行步骤1")
    
    with open(raw_data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data


def process_scene_full_relation(scene_data):
    """
    处理单个场景，生成全关系场景图
    
    核心改进：
    1. 为每个对象分配唯一ID（如car1, car2）
    2. 生成所有对象之间的关系（不只是ego-其他）
    3. 使用Source Frame - 以source对象的朝向为参考系
    """
    ego_pose = scene_data['ego_pose']
    annotations = scene_data['annotations']
    timestamp = scene_data['timestamp']
    
    # === 第一步：处理所有对象，分配唯一ID ===
    objects_list = []
    type_counters = defaultdict(int)  # 用于给每种类型的对象编号
    
    # 添加ego车（ID为0）
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
        # 简化类别
        obj_type = simplify_category(ann['category'])
        
        # 跳过不需要的类别
        if obj_type is None:
            continue
        
        # 为该类型对象分配唯一ID
        type_counters[obj_type] += 1
        unique_id = f"{obj_type}{type_counters[obj_type]}"
        
        # 构建对象信息
        obj_info = {
            'id': len(objects_list),  # 数字ID
            'unique_id': unique_id,   # 唯一名称（car1, car2等）
            'type': obj_type,
            'category': ann['category'],  # 原始类别
            'translation': ann['translation'],
            'rotation': ann['rotation'],
            'size': ann['size'],
            'velocity': ann.get('velocity', [0.0, 0.0, 0.0]),
            'token': ann['token'],
            'num_lidar_pts': ann.get('num_lidar_pts', 0),
            'is_ego': False
        }
        
        objects_list.append(obj_info)
    
    # === 第二步：计算所有对象之间的关系（使用Source Frame）===
    relationships = []
    
    for i, obj1 in enumerate(objects_list):
        for j, obj2 in enumerate(objects_list):
            # 跳过自己和自己的关系
            if i == j:
                continue
            
            # ✅ Source Frame: 使用source对象的朝向作为参考系
            rel_pos_source, angle_source = calculate_relative_position_in_source_frame(
                obj1['translation'], 
                obj2['translation'],
                obj1['rotation']  # 使用source对象的朝向作为参考系
            )
            
            # ✅ Ego Frame: 使用ego车的朝向作为参考系
            rel_pos_ego, angle_ego = calculate_relative_position_in_ego_frame(
                obj1['translation'], 
                obj2['translation'],
                ego_pose['rotation']  # 使用ego车的朝向作为参考系
            )
            
            # 计算距离（两种坐标系距离相同）
            distance = float(np.linalg.norm(rel_pos_source[:2]))
            
            # 在两种坐标系中判断方位
            direction_labels_source = get_direction_labels(angle_source)
            direction_labels_ego = get_direction_labels(angle_ego)
            
            # 距离级别
            distance_level = get_distance_predicate(distance)
            
            # 构建关系（使用source frame的方位作为主要predicates，保持兼容性）
            relation = {
                'source': obj1['unique_id'],
                'source_type': obj1['type'],
                'target': obj2['unique_id'],
                'target_type': obj2['type'],
                'predicates': [direction_labels_source['direction_8'], distance_level],
                'metrics': {
                    'distance': round(distance, 2),
                    # Source Frame 数据
                    'angle_source': round(float(angle_source), 1),
                    'direction_source': direction_labels_source,
                    'relative_position_source': {
                        'x': round(float(rel_pos_source[0]), 2),
                        'y': round(float(rel_pos_source[1]), 2),
                        'z': round(float(rel_pos_source[2]), 2)
                    },
                    # Ego Frame 数据
                    'angle_ego': round(float(angle_ego), 1),
                    'direction_ego': direction_labels_ego,
                    'relative_position_ego': {
                        'x': round(float(rel_pos_ego[0]), 2),
                        'y': round(float(rel_pos_ego[1]), 2),
                        'z': round(float(rel_pos_ego[2]), 2)
                    }
                }
            }
            
            relationships.append(relation)
    
    # === 第三步：构建完整的场景图数据 ===
    scene_graph = {
        # 基础信息
        'scene_token': scene_data['scene_token'],
        'scene_name': scene_data['scene_name'],
        'scene_description': scene_data.get('scene_description', ''),
        'timestamp': timestamp,
        
        # 对象列表（带唯一ID）
        'objects': [
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
                    'width': round(float(obj['size'][0]), 2),
                    'length': round(float(obj['size'][1]), 2),
                    'height': round(float(obj['size'][2]), 2)
                } if 'size' in obj else None,
                'velocity': {
                    'vx': round(float(obj['velocity'][0]), 2),
                    'vy': round(float(obj['velocity'][1]), 2),
                    'vz': round(float(obj['velocity'][2]), 2)
                } if 'velocity' in obj else None,
                'token': obj.get('token', None),
                'num_lidar_pts': obj.get('num_lidar_pts', 0)
            }
            for obj in objects_list
        ],
        
        # 全关系列表
        'relationships': relationships,
        
        # Ego车信息
        'ego_pose': {
            'translation': {
                'x': round(float(ego_pose['translation'][0]), 2),
                'y': round(float(ego_pose['translation'][1]), 2),
                'z': round(float(ego_pose['translation'][2]), 2)
            },
            'rotation': [round(float(r), 4) for r in ego_pose['rotation']]
        },
        
        # 统计信息
        'statistics': {
            'num_objects': len(objects_list),
            'num_relationships': len(relationships),
            'object_type_counts': dict(type_counters),
            'ego_relations': sum(1 for r in relationships if r['source'] == 'ego')
        }
    }
    
    return scene_graph


def main():
    """主函数"""
    print("=" * 60)
    print("步骤2改进版: 生成全关系场景图")
    print("=" * 60)
    
    # 加载原始数据
    print("\n正在加载原始数据...")
    all_scenes_data = load_raw_data()
    print(f"✓ 加载了 {len(all_scenes_data)} 个场景")
    
    # 生成全关系场景图
    print("\n正在生成全关系场景图...")
    all_scene_graphs = []
    
    for scene_data in tqdm(all_scenes_data, desc="处理场景"):
        try:
            scene_graph_data = process_scene_full_relation(scene_data)
            all_scene_graphs.append(scene_graph_data)
        except Exception as e:
            print(f"\n警告: 场景 {scene_data['scene_name']} 处理失败: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n✓ 全关系场景图生成完成")
    print(f"  - 成功处理: {len(all_scene_graphs)} 个场景")
    print(f"  - 总对象数: {sum(sg['statistics']['num_objects'] for sg in all_scene_graphs)}")
    print(f"  - 总关系数: {sum(sg['statistics']['num_relationships'] for sg in all_scene_graphs)}")
    
    # 展示一个示例
    if all_scene_graphs:
        example = all_scene_graphs[0]
        print(f"\n示例场景: {example['scene_name']}")
        print(f"  - 对象数量: {example['statistics']['num_objects']}")
        print(f"  - 关系数量: {example['statistics']['num_relationships']}")
        print(f"  - 对象列表:")
        for obj in example['objects'][:5]:  # 只显示前5个
            print(f"    • {obj['unique_id']} ({obj['type']})")
        print(f"  - 关系示例:")
        for rel in example['relationships'][:5]:  # 只显示前5个
            print(f"    • {rel['source']} -> {rel['target']}: {rel['predicates']}")
    
    # 保存全关系场景图数据
    output_path = os.path.join(config.SCENE_GRAPHS_DIR, 'all_scene_graphs_full_relation.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_scene_graphs, f, indent=2, ensure_ascii=False)
    print(f"\n✓ 全关系场景图数据已保存: {output_path}")
    
    # 生成统计摘要
    total_objects = sum(sg['statistics']['num_objects'] for sg in all_scene_graphs)
    total_relations = sum(sg['statistics']['num_relationships'] for sg in all_scene_graphs)
    
    summary = {
        'total_scenes': len(all_scene_graphs),
        'total_objects': total_objects,
        'total_relationships': total_relations,
        'avg_objects_per_scene': round(total_objects / len(all_scene_graphs), 2),
        'avg_relationships_per_scene': round(total_relations / len(all_scene_graphs), 2)
    }
    
    summary_path = os.path.join(config.STATISTICS_DIR, 'step2_full_relation_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ 步骤2改进版完成！")
    print(f"  - 全关系场景图: {output_path}")
    print(f"  - 统计摘要: {summary_path}")
    print(f"\n改进点:")
    print(f"  ✓ 每个对象有唯一ID（car1, car2等）")
    print(f"  ✓ 生成了所有对象之间的关系")
    print(f"  ✓ 谓词简化为方位+距离")
    print(f"  ✓ 以ego车为参考系")
    
    return all_scene_graphs


if __name__ == "__main__":
    main()
