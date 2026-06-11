"""
单场景深度剖析 - 演示完整流程

目标：选择一个代表性场景，展示从原始数据到场景图的完整过程
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
import config


def print_section(title):
    """打印分隔线"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def load_single_scene(nusc, scene_idx=0):
    """
    加载单个场景的原始数据
    
    Args:
        nusc: NuScenes实例
        scene_idx: 场景索引（默认0，即第一个场景）
    """
    print_section(f"步骤1：加载场景 #{scene_idx} 的原始数据")
    
    # 获取场景信息
    scene = nusc.scene[scene_idx]
    scene_token = scene['token']
    scene_name = scene['name']
    scene_description = scene['description']
    
    print(f"\n场景基本信息：")
    print(f"  名称: {scene_name}")
    print(f"  描述: {scene_description}")
    print(f"  帧数: {scene['nbr_samples']}")
    
    # 获取第一帧
    sample_token = scene['first_sample_token']
    sample = nusc.get('sample', sample_token)
    timestamp = sample['timestamp']
    
    # 获取Ego车姿态
    lidar_token = sample['data']['LIDAR_TOP']
    lidar_data = nusc.get('sample_data', lidar_token)
    ego_pose = nusc.get('ego_pose', lidar_data['ego_pose_token'])
    
    print(f"\nEgo车位置：")
    print(f"  X: {ego_pose['translation'][0]:.2f}m")
    print(f"  Y: {ego_pose['translation'][1]:.2f}m")
    print(f"  Z: {ego_pose['translation'][2]:.2f}m")
    
    # 获取所有标注对象
    annotations = []
    print(f"\n场景中的对象：")
    
    for ann_token in sample['anns']:
        ann = nusc.get('sample_annotation', ann_token)
        
        # 获取速度
        try:
            velocity = nusc.box_velocity(ann_token)
            if velocity is None or np.any(np.isnan(velocity)):
                velocity = [0.0, 0.0, 0.0]
        except:
            velocity = [0.0, 0.0, 0.0]
        
        annotations.append({
            'token': ann['token'],
            'category': ann['category_name'],
            'translation': ann['translation'],
            'rotation': ann['rotation'],
            'size': ann['size'],
            'velocity': velocity,
            'num_lidar_pts': ann['num_lidar_pts'],
            'num_radar_pts': ann['num_radar_pts']
        })
    
    # 按类别统计
    category_counts = {}
    for ann in annotations:
        cat = ann['category']
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    print(f"  总对象数: {len(annotations)}")
    print(f"  类别分布:")
    for cat, count in sorted(category_counts.items()):
        print(f"    - {cat}: {count}")
    
    # 返回场景数据
    scene_data = {
        'scene_token': scene_token,
        'scene_name': scene_name,
        'scene_description': scene_description,
        'timestamp': timestamp,
        'ego_pose': ego_pose,
        'annotations': annotations,
        'sample_token': sample_token
    }
    
    return scene_data, nusc


def simplify_category(category):
    """简化对象类别"""
    mapping = config.CATEGORY_MAPPING
    return mapping.get(category, None)


def calculate_relative_position(ego_pose, obj_ann):
    """计算对象相对于ego车的位置"""
    # Ego车位置
    ego_translation = np.array(ego_pose['translation'])
    ego_rotation = np.array(ego_pose['rotation'])
    
    # 对象位置
    obj_translation = np.array(obj_ann['translation'])
    
    # 计算相对位置（简化版，直接减法）
    rel_pos = obj_translation - ego_translation
    
    # 计算角度
    angle = np.arctan2(rel_pos[1], rel_pos[0]) * 180 / np.pi
    
    return rel_pos, angle


def quaternion_to_yaw(rotation):
    """从四元数提取yaw角（弧度）"""
    # rotation格式: [w, x, y, z] 或 [x, y, z, w]
    # NuScenes使用 [w, x, y, z]
    w, x, y, z = rotation[0], rotation[1], rotation[2], rotation[3]
    # 计算yaw角
    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = np.arctan2(siny_cosp, cosy_cosp)
    return yaw


def get_direction_predicate(relative_angle):
    """根据相对角度判断方位（相对于源对象朝向）"""
    # 归一化到 [-180, 180]
    angle = ((relative_angle + 180) % 360) - 180
    
    if -45 <= angle < 45:
        return 'front'
    elif 45 <= angle < 135:
        return 'left'
    elif -135 <= angle < -45:
        return 'right'
    else:
        return 'rear'


def get_distance_predicate(distance):
    """根据距离判断距离级别"""
    if distance <= 10:
        return 'near'
    elif distance <= 25:
        return 'mid'
    else:
        return 'far'


def generate_scene_graph_with_unique_ids(scene_data):
    """
    生成带唯一ID的全关系场景图
    
    核心改进：
    1. 为每个对象分配唯一ID（car1, car2等）
    2. 生成所有对象之间的关系
    """
    print_section("步骤2：生成全关系场景图（带唯一ID）")
    
    ego_pose = scene_data['ego_pose']
    annotations = scene_data['annotations']
    
    # === 处理对象，分配唯一ID ===
    objects_list = []
    type_counters = defaultdict(int)
    
    # 添加Ego车
    ego_obj = {
        'id': 'ego',
        'unique_id': 'ego',
        'type': 'ego',
        'translation': ego_pose['translation'],
        'rotation': ego_pose['rotation'],
        'is_ego': True
    }
    objects_list.append(ego_obj)
    
    print(f"\n对象列表（带唯一ID）：")
    print(f"  0. ego (ego车)")
    
    # 处理其他对象
    for idx, ann in enumerate(annotations):
        obj_type = simplify_category(ann['category'])
        if obj_type is None:
            continue
        
        # 分配唯一ID
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
            'is_ego': False
        }
        
        objects_list.append(obj_info)
        
        # 计算相对位置
        rel_pos, _ = calculate_relative_position(ego_pose, ann)
        distance = np.linalg.norm(rel_pos[:2])
        
        print(f"  {len(objects_list)-1}. {unique_id} ({obj_type}) - 距离ego {distance:.1f}m")
    
    print(f"\n简化后的类型统计：")
    for obj_type, count in sorted(type_counters.items()):
        print(f"  - {obj_type}: {count}")
    
    # === 生成全关系 ===
    print(f"\n生成所有对象之间的关系...")
    relationships = []
    
    for i, obj1 in enumerate(objects_list):
        for j, obj2 in enumerate(objects_list):
            if i == j:
                continue
            
            # 计算相对位置
            rel_pos = np.array(obj2['translation']) - np.array(obj1['translation'])
            distance = float(np.linalg.norm(rel_pos[:2]))
            
            # 计算绝对角度（世界坐标系）
            absolute_angle = np.arctan2(rel_pos[1], rel_pos[0])  # 弧度
            
            # 获取源对象的朝向
            source_yaw = quaternion_to_yaw(obj1['rotation'])
            
            # 计算相对角度（相对于源对象朝向）
            relative_angle = (absolute_angle - source_yaw) * 180 / np.pi  # 转换为度
            
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
                        'x': round(float(rel_pos[0]), 2),
                        'y': round(float(rel_pos[1]), 2),
                        'z': round(float(rel_pos[2]), 2)
                    }
                }
            }
            
            relationships.append(relation)
    
    print(f"  总关系数: {len(relationships)}")
    print(f"  每个对象平均关系数: {len(relationships) / len(objects_list):.0f}")
    
    # === 显示部分关系示例 ===
    print(f"\n关系示例（前10条）：")
    print(f"  格式: 源对象 -> 目标对象: [方位, 距离级别] (具体距离)")
    for i, rel in enumerate(relationships[:10]):
        direction = rel['predicates'][0]
        distance_level = rel['predicates'][1]
        actual_distance = rel['metrics']['distance']
        print(f"  {i+1}. {rel['source']} -> {rel['target']}: "
              f"[{direction}, {distance_level}] ({actual_distance}m)")
    
    # 构建完整场景图
    scene_graph = {
        'scene_name': scene_data['scene_name'],
        'scene_description': scene_data['scene_description'],
        'timestamp': scene_data['timestamp'],
        'objects': objects_list,
        'relationships': relationships,
        'statistics': {
            'num_objects': len(objects_list),
            'num_relationships': len(relationships),
            'object_type_counts': dict(type_counters)
        }
    }
    
    return scene_graph


def show_object_details(scene_graph):
    """展示对象的详细JSON信息"""
    print_section("步骤3：展示对象的详细JSON信息")
    
    print(f"\n我们以第一辆车（car1）为例，展示其完整信息：\n")
    
    # 找到car1
    car1 = None
    for obj in scene_graph['objects']:
        if obj['unique_id'] == 'car1':
            car1 = obj
            break
    
    if car1:
        # 格式化显示
        display_obj = {
            'unique_id': car1['unique_id'],
            'type': car1['type'],
            'category': car1['category'],
            'translation': {
                'x': round(car1['translation'][0], 2),
                'y': round(car1['translation'][1], 2),
                'z': round(car1['translation'][2], 2)
            },
            'size': {
                'width': round(car1['size'][0], 2),
                'length': round(car1['size'][1], 2),
                'height': round(car1['size'][2], 2)
            },
            'velocity': {
                'vx': round(car1['velocity'][0], 2),
                'vy': round(car1['velocity'][1], 2),
                'vz': round(car1['velocity'][2], 2)
            },
            'num_lidar_pts': car1['num_lidar_pts']
        }
        
        print(json.dumps(display_obj, indent=2, ensure_ascii=False))
        
        # 计算速度大小
        speed = np.linalg.norm(car1['velocity'][:2])
        print(f"\n派生信息：")
        print(f"  速度大小: {speed:.2f} m/s")
        print(f"  状态: {'移动中' if speed > 0.5 else '静止'}")
    else:
        print("  未找到car1对象")


def show_relationships_analysis(scene_graph):
    """展示关系分析"""
    print_section("步骤4：分析对象之间的关系")
    
    # 分析ego车周围的对象
    print(f"\n1. Ego车周围的对象（按距离排序）：")
    print(f"   格式: 对象 (类型): [方位, 距离级别], 具体距离")
    ego_relations = [r for r in scene_graph['relationships'] if r['source'] == 'ego']
    ego_relations.sort(key=lambda x: x['metrics']['distance'])
    
    for i, rel in enumerate(ego_relations[:8]):
        direction = rel['predicates'][0]
        distance_level = rel['predicates'][1]
        actual_distance = rel['metrics']['distance']
        print(f"  {i+1}. {rel['target']} ({rel['target_type']}): "
              f"[{direction}, {distance_level}], {actual_distance}m")
    
    # 分析car1的关系
    print(f"\n2. Car1周围的对象（展示非ego关系）：")
    print(f"   格式: 对象 (类型): [方位, 距离级别], 具体距离")
    car1_relations = [r for r in scene_graph['relationships'] 
                      if r['source'] == 'car1' and r['target'] != 'ego']
    car1_relations.sort(key=lambda x: x['metrics']['distance'])
    
    for i, rel in enumerate(car1_relations[:5]):
        direction = rel['predicates'][0]
        distance_level = rel['predicates'][1]
        actual_distance = rel['metrics']['distance']
        print(f"  {i+1}. {rel['target']} ({rel['target_type']}): "
              f"[{direction}, {distance_level}], {actual_distance}m")
    
    # 统计方位分布
    print(f"\n3. Ego车四周的对象分布：")
    direction_stats = {'front': 0, 'left': 0, 'rear': 0, 'right': 0}
    for rel in ego_relations:
        direction = rel['predicates'][0]
        direction_stats[direction] = direction_stats.get(direction, 0) + 1
    
    for direction, count in sorted(direction_stats.items()):
        print(f"  {direction}: {count}个对象")
    
    # 统计距离分布
    print(f"\n4. 距离分布：")
    distance_stats = {'near': 0, 'mid': 0, 'far': 0}
    for rel in ego_relations:
        dist_level = rel['predicates'][1]
        distance_stats[dist_level] = distance_stats.get(dist_level, 0) + 1
    
    for dist_level, count in sorted(distance_stats.items()):
        print(f"  {dist_level}: {count}个对象")


def convert_to_serializable(obj):
    """将numpy类型转换为Python原生类型，便于JSON序列化"""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(item) for item in obj]
    else:
        return obj


def save_scene_graph(scene_graph, output_dir):
    """保存场景图数据"""
    print_section("步骤5：保存场景图数据")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 转换为可序列化格式
    scene_graph_serializable = convert_to_serializable(scene_graph)
    
    # 保存完整数据
    full_path = os.path.join(output_dir, 'single_scene_full_graph.json')
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(scene_graph_serializable, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ 完整场景图已保存: {full_path}")
    print(f"  文件大小: {os.path.getsize(full_path) / 1024:.1f} KB")
    
    # 保存简化版（只包含关键信息，便于查看）
    ego_translation = np.array(scene_graph['objects'][0]['translation'])
    
    simplified = {
        'scene_name': scene_graph['scene_name'],
        'objects_summary': [
            {
                'unique_id': obj['unique_id'],
                'type': obj['type'],
                'distance_from_ego': round(float(np.linalg.norm(
                    (np.array(obj['translation']) - ego_translation)[:2]
                )), 2) if obj['unique_id'] != 'ego' else 0
            }
            for obj in scene_graph['objects']
        ],
        'ego_relationships': [
            {
                'target': r['target'],
                'predicates': r['predicates'],
                'distance': r['metrics']['distance']
            }
            for r in scene_graph['relationships'] if r['source'] == 'ego'
        ],
        'statistics': scene_graph['statistics']
    }
    
    simple_path = os.path.join(output_dir, 'single_scene_simplified.json')
    with open(simple_path, 'w', encoding='utf-8') as f:
        json.dump(simplified, f, indent=2, ensure_ascii=False)
    
    print(f"✓ 简化版已保存: {simple_path}")
    print(f"  文件大小: {os.path.getsize(simple_path) / 1024:.1f} KB")
    
    return full_path, simple_path


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("  单场景深度剖析 - 完整流程演示")
    print("=" * 70)
    
    # 初始化NuScenes
    print("\n初始化NuScenes数据集...")
    nusc = NuScenes(version='v1.0-mini', 
                    dataroot=config.NUSCENES_DATAROOT, 
                    verbose=False)
    print(f"✓ 已加载 {len(nusc.scene)} 个场景")
    
    # 步骤1：加载单个场景
    scene_data, nusc = load_single_scene(nusc, scene_idx=0)
    
    # 步骤2：生成全关系场景图
    scene_graph = generate_scene_graph_with_unique_ids(scene_data)
    
    # 步骤3：展示对象详细信息
    show_object_details(scene_graph)
    
    # 步骤4：分析关系
    show_relationships_analysis(scene_graph)
    
    # 步骤5：保存数据
    output_dir = os.path.join(config.OUTPUT_DIR, 'single_scene_demo')
    full_path, simple_path = save_scene_graph(scene_graph, output_dir)
    
    # 总结
    print_section("完成总结")
    print(f"\n✓ 单场景剖析完成！")
    print(f"\n这个场景的关键数据：")
    print(f"  场景名称: {scene_graph['scene_name']}")
    print(f"  对象总数: {scene_graph['statistics']['num_objects']}")
    print(f"  关系总数: {scene_graph['statistics']['num_relationships']}")
    print(f"  对象类型: {list(scene_graph['statistics']['object_type_counts'].keys())}")
    
    print(f"\n下一步：")
    print(f"  1. 查看生成的JSON文件了解数据结构")
    print(f"  2. 可视化这个场景的BEV图")
    print(f"  3. 将这个场景导入Neo4j进行查询")
    
    print("\n" + "=" * 70)
    
    return scene_graph, nusc


if __name__ == "__main__":
    scene_graph, nusc = main()
