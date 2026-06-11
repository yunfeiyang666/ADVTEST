"""
步骤2增强版: 生成知识图谱友好的场景图

功能：
1. 保留S3C的核心谓词信息
2. 增加精确的数值信息（距离、速度、角度）
3. 增加对象属性（尺寸、类别）
4. 增加时间戳和质量指标
5. 便于Neo4j知识图谱查询
"""
import os
import sys
import json
import numpy as np

# 添加本地nuscenes-devkit路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

from tqdm import tqdm
import config
from utils.predicates import calculate_relative_position, evaluate_spatial_predicates
from utils.graph_utils import create_scene_graph, scene_graph_to_dict


def load_raw_data():
    """加载步骤1的原始数据"""
    raw_data_path = os.path.join(config.OUTPUT_DIR, 'raw_scenes_data.json')
    
    if not os.path.exists(raw_data_path):
        raise FileNotFoundError(f"找不到原始数据文件: {raw_data_path}\n请先运行步骤1")
    
    with open(raw_data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data


def simplify_category(category):
    """简化对象类别"""
    mapping = config.CATEGORY_MAPPING
    return mapping.get(category, None)


def process_scene_enhanced(scene_data):
    """
    处理单个场景，生成增强的场景图
    
    增强信息：
    - 精确距离和角度
    - 速度大小和矢量
    - 对象尺寸
    - 时间戳
    - 质量指标（点云数量）
    """
    ego_pose = scene_data['ego_pose']
    annotations = scene_data['annotations']
    timestamp = scene_data['timestamp']
    
    # 处理每个对象
    objects_data = []
    
    for ann in annotations:
        # 简化类别
        obj_type = simplify_category(ann['category'])
        
        # 跳过不需要的类别
        if obj_type is None:
            continue
        
        # 计算相对位置和角度
        rel_pos, rel_angle = calculate_relative_position(ego_pose, ann)
        
        # 计算精确距离
        distance = float(np.linalg.norm(rel_pos[:2]))
        
        # 评估空间谓词
        velocity = ann.get('velocity', [0.0, 0.0, 0.0])
        predicates = evaluate_spatial_predicates(rel_pos, rel_angle, velocity)
        
        # 计算速度大小
        speed = float(np.linalg.norm(velocity[:2]))
        
        # 构建增强的对象信息
        obj_info = {
            # === S3C核心信息 ===
            'type': obj_type,
            'predicates': predicates,
            
            # === 增强：精确数值 ===
            'distance': round(distance, 2),           # 精确距离（米）
            'angle': round(float(rel_angle), 1),      # 精确角度（度）
            'speed': round(speed, 2),                 # 速度大小（米/秒）
            
            # === 增强：相对位置 ===
            'relative_position': {
                'x': round(float(rel_pos[0]), 2),     # 前后方向（米）
                'y': round(float(rel_pos[1]), 2),     # 左右方向（米）
                'z': round(float(rel_pos[2]), 2)      # 高度（米）
            },
            
            # === 增强：速度矢量 ===
            'velocity_vector': {
                'vx': round(float(velocity[0]), 2),
                'vy': round(float(velocity[1]), 2),
                'vz': round(float(velocity[2]), 2)
            },
            
            # === 增强：对象属性 ===
            'size': {
                'width': round(float(ann['size'][0]), 2),
                'length': round(float(ann['size'][1]), 2),
                'height': round(float(ann['size'][2]), 2)
            },
            
            # === 增强：详细类别 ===
            'category': ann['category'],              # NuScenes原始类别
            
            # === 增强：质量指标 ===
            'quality': {
                'num_lidar_pts': ann.get('num_lidar_pts', 0),
                'num_radar_pts': ann.get('num_radar_pts', 0)
            },
            
            # === 增强：原始数据 ===
            'token': ann['token']                     # 对象唯一标识
        }
        
        objects_data.append(obj_info)
    
    # 创建场景图（使用核心信息）
    scene_graph = create_scene_graph({'type': 'ego'}, objects_data)
    scene_graph_dict = scene_graph_to_dict(scene_graph)
    
    # 构建增强的场景图数据
    enhanced_scene_graph = {
        # === 基础信息 ===
        'scene_token': scene_data['scene_token'],
        'scene_name': scene_data['scene_name'],
        'scene_description': scene_data.get('scene_description', ''),
        
        # === 时间信息 ===
        'timestamp': timestamp,
        
        # === Ego车信息 ===
        'ego_pose': {
            'translation': {
                'x': round(float(ego_pose['translation'][0]), 2),
                'y': round(float(ego_pose['translation'][1]), 2),
                'z': round(float(ego_pose['translation'][2]), 2)
            },
            'rotation': [round(float(r), 4) for r in ego_pose['rotation']]
        },
        
        # === 对象统计 ===
        'num_objects': len(objects_data),
        
        # === 场景图结构 ===
        'scene_graph': scene_graph_dict,
        
        # === 增强：详细对象信息 ===
        'objects_detailed': objects_data,
        
        # === 对象摘要（用于快速查询）===
        'objects_summary': {
            'types': [obj['type'] for obj in objects_data],
            'predicates': [obj['predicates'] for obj in objects_data],
            'distances': [obj['distance'] for obj in objects_data],
            'speeds': [obj['speed'] for obj in objects_data]
        },
        
        # === 场景统计 ===
        'scene_statistics': {
            'total_objects': len(objects_data),
            'moving_objects': sum(1 for obj in objects_data if 'moving' in obj['predicates']),
            'stopped_objects': sum(1 for obj in objects_data if 'stopped' in obj['predicates']),
            'min_distance': round(min([obj['distance'] for obj in objects_data]), 2) if objects_data else 0,
            'max_distance': round(max([obj['distance'] for obj in objects_data]), 2) if objects_data else 0,
            'avg_distance': round(sum([obj['distance'] for obj in objects_data]) / len(objects_data), 2) if objects_data else 0,
            'max_speed': round(max([obj['speed'] for obj in objects_data]), 2) if objects_data else 0
        }
    }
    
    return enhanced_scene_graph


def main():
    """主函数"""
    print("=" * 60)
    print("步骤2增强版: 生成知识图谱友好的场景图")
    print("=" * 60)
    
    # 加载原始数据
    print("\n正在加载原始数据...")
    all_scenes_data = load_raw_data()
    print(f"✓ 加载了 {len(all_scenes_data)} 个场景")
    
    # 生成增强场景图
    print("\n正在生成增强场景图...")
    all_scene_graphs = []
    
    for scene_data in tqdm(all_scenes_data, desc="处理场景"):
        try:
            scene_graph_data = process_scene_enhanced(scene_data)
            all_scene_graphs.append(scene_graph_data)
        except Exception as e:
            print(f"\n警告: 场景 {scene_data['scene_name']} 处理失败: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n✓ 增强场景图生成完成")
    print(f"  - 成功处理: {len(all_scene_graphs)} 个场景")
    print(f"  - 总对象数: {sum(sg['num_objects'] for sg in all_scene_graphs)}")
    
    # 统计对象类型
    type_counts = {}
    for sg in all_scene_graphs:
        for obj_type in sg['objects_summary']['types']:
            type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
    
    print(f"\n简化后的对象类型统计:")
    for obj_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {obj_type}: {count}")
    
    # 统计谓词使用
    predicate_counts = {}
    for sg in all_scene_graphs:
        for predicates in sg['objects_summary']['predicates']:
            for pred in predicates:
                predicate_counts[pred] = predicate_counts.get(pred, 0) + 1
    
    print(f"\n谓词使用统计:")
    for pred, count in sorted(predicate_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {pred}: {count}")
    
    # 统计距离分布
    all_distances = []
    for sg in all_scene_graphs:
        all_distances.extend(sg['objects_summary']['distances'])
    
    if all_distances:
        print(f"\n距离统计:")
        print(f"  - 最小距离: {min(all_distances):.2f}m")
        print(f"  - 最大距离: {max(all_distances):.2f}m")
        print(f"  - 平均距离: {sum(all_distances)/len(all_distances):.2f}m")
    
    # 统计速度分布
    all_speeds = []
    for sg in all_scene_graphs:
        all_speeds.extend(sg['objects_summary']['speeds'])
    
    if all_speeds:
        print(f"\n速度统计:")
        print(f"  - 最大速度: {max(all_speeds):.2f}m/s")
        print(f"  - 平均速度: {sum(all_speeds)/len(all_speeds):.2f}m/s")
        print(f"  - 移动对象: {sum(1 for s in all_speeds if s > 0.5)}")
        print(f"  - 静止对象: {sum(1 for s in all_speeds if s <= 0.5)}")
    
    # 保存增强场景图数据
    output_path = os.path.join(config.SCENE_GRAPHS_DIR, 'all_scene_graphs_enhanced.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_scene_graphs, f, indent=2, ensure_ascii=False)
    print(f"\n✓ 增强场景图数据已保存: {output_path}")
    
    # 生成统计摘要
    summary = {
        'total_scenes': len(all_scene_graphs),
        'total_objects': sum(sg['num_objects'] for sg in all_scene_graphs),
        'type_counts': type_counts,
        'predicate_counts': predicate_counts,
        'distance_stats': {
            'min': round(min(all_distances), 2) if all_distances else 0,
            'max': round(max(all_distances), 2) if all_distances else 0,
            'avg': round(sum(all_distances)/len(all_distances), 2) if all_distances else 0
        },
        'speed_stats': {
            'max': round(max(all_speeds), 2) if all_speeds else 0,
            'avg': round(sum(all_speeds)/len(all_speeds), 2) if all_speeds else 0,
            'moving_count': sum(1 for s in all_speeds if s > 0.5),
            'stopped_count': sum(1 for s in all_speeds if s <= 0.5)
        },
        'avg_objects_per_scene': sum(sg['num_objects'] for sg in all_scene_graphs) / len(all_scene_graphs)
    }
    
    summary_path = os.path.join(config.STATISTICS_DIR, 'step2_enhanced_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ 步骤2增强版完成！")
    print(f"  - 增强场景图数据: {output_path}")
    print(f"  - 统计摘要: {summary_path}")
    print(f"\n增强信息包括:")
    print(f"  ✓ 精确距离和角度")
    print(f"  ✓ 速度大小和矢量")
    print(f"  ✓ 相对位置坐标")
    print(f"  ✓ 对象尺寸")
    print(f"  ✓ 详细类别")
    print(f"  ✓ 质量指标（点云数量）")
    print(f"  ✓ 时间戳")
    print(f"  ✓ 场景统计")
    
    return all_scene_graphs


if __name__ == "__main__":
    main()
