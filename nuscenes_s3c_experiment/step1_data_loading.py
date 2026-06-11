"""
步骤1: 从NuScenes加载数据

功能：
1. 加载NuScenes数据集
2. 提取每个场景的ego车和对象信息
3. 保存原始数据用于后续处理
"""
import os
import sys
import json

# 添加本地nuscenes-devkit路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

from nuscenes.nuscenes import NuScenes
from tqdm import tqdm
import config


def load_nuscenes_data():
    """加载NuScenes数据集"""
    print("=" * 60)
    print("步骤1: 加载NuScenes数据")
    print("=" * 60)
    
    # 加载NuScenes
    print(f"\n正在加载NuScenes数据集...")
    print(f"  - 数据路径: {config.NUSCENES_DATAROOT}")
    print(f"  - 版本: {config.NUSCENES_VERSION}")
    
    nusc = NuScenes(
        version=config.NUSCENES_VERSION,
        dataroot=config.NUSCENES_DATAROOT,
        verbose=True
    )
    
    print(f"\n✓ 数据集加载完成")
    print(f"  - 场景数: {len(nusc.scene)}")
    print(f"  - 样本数: {len(nusc.sample)}")
    
    return nusc


def get_attribute_names(nusc, attribute_tokens):
    """
    获取attribute的名称列表
    
    Args:
        nusc: NuScenes对象
        attribute_tokens: attribute token列表
    
    Returns:
        attributes: attribute名称列表（如 ['cycle.with_rider']）
    """
    attributes = []
    for token in attribute_tokens:
        try:
            attr = nusc.get('attribute', token)
            attributes.append(attr['name'])
        except:
            pass
    return attributes


def extract_scene_data(nusc, scene):
    """
    提取单个场景的数据
    
    Args:
        nusc: NuScenes对象
        scene: 场景对象
    
    Returns:
        scene_data: 场景数据字典
    """
    # 获取场景的第一个sample
    sample = nusc.get('sample', scene['first_sample_token'])
    
    # 提取ego车位姿
    ego_pose_token = sample['data']['LIDAR_TOP']
    ego_pose = nusc.get('ego_pose', nusc.get('sample_data', ego_pose_token)['ego_pose_token'])
    
    # 提取所有对象标注
    annotations = []
    for ann_token in sample['anns']:
        ann = nusc.get('sample_annotation', ann_token)
        
        # 获取速度
        try:
            velocity = nusc.box_velocity(ann_token)
            if velocity is None or any(v is None for v in velocity):
                velocity = [0.0, 0.0, 0.0]
        except:
            velocity = [0.0, 0.0, 0.0]
        
        # 获取attributes（关键信息，包含with_rider等状态）
        attribute_tokens = ann.get('attribute_tokens', [])
        attribute_names = get_attribute_names(nusc, attribute_tokens)
        
        annotations.append({
            'token': ann_token,
            'category': ann['category_name'],
            'translation': ann['translation'],
            'rotation': ann['rotation'],
            'size': ann['size'],
            'velocity': velocity,
            'num_lidar_pts': ann['num_lidar_pts'],
            'num_radar_pts': ann['num_radar_pts'],
            'attributes': attribute_names  # 新增：保留NuScenes的attributes
        })
    
    scene_data = {
        'scene_token': scene['token'],
        'scene_name': scene['name'],
        'scene_description': scene['description'],
        'sample_token': sample['token'],
        'timestamp': sample['timestamp'],
        'ego_pose': {
            'translation': ego_pose['translation'],
            'rotation': ego_pose['rotation']
        },
        'annotations': annotations
    }
    
    return scene_data


def convert_to_serializable(obj):
    """将numpy数组等转换为可序列化的格式"""
    import numpy as np
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(item) for item in obj]
    else:
        return obj

def save_raw_data(all_scenes_data, output_path):
    """保存原始数据"""
    # 转换为可序列化格式
    serializable_data = convert_to_serializable(all_scenes_data)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(serializable_data, f, indent=2, ensure_ascii=False)
    print(f"\n✓ 原始数据已保存: {output_path}")


def main():
    """主函数"""
    # 加载NuScenes
    nusc = load_nuscenes_data()
    
    # 提取所有场景数据
    print(f"\n正在提取场景数据...")
    all_scenes_data = []
    
    for scene in tqdm(nusc.scene, desc="处理场景"):
        scene_data = extract_scene_data(nusc, scene)
        all_scenes_data.append(scene_data)
    
    print(f"\n✓ 场景数据提取完成")
    print(f"  - 总场景数: {len(all_scenes_data)}")
    print(f"  - 总对象数: {sum(len(s['annotations']) for s in all_scenes_data)}")
    
    # 统计对象类别
    category_counts = {}
    for scene_data in all_scenes_data:
        for ann in scene_data['annotations']:
            category = ann['category']
            category_counts[category] = category_counts.get(category, 0) + 1
    
    print(f"\n对象类别统计:")
    for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {category}: {count}")
    
    # 保存原始数据
    output_path = os.path.join(config.OUTPUT_DIR, 'raw_scenes_data.json')
    save_raw_data(all_scenes_data, output_path)
    
    # 生成摘要报告
    summary = {
        'total_scenes': len(all_scenes_data),
        'total_objects': sum(len(s['annotations']) for s in all_scenes_data),
        'category_counts': category_counts,
        'avg_objects_per_scene': sum(len(s['annotations']) for s in all_scenes_data) / len(all_scenes_data)
    }
    
    summary_path = os.path.join(config.STATISTICS_DIR, 'step1_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ 步骤1完成！")
    print(f"  - 原始数据: {output_path}")
    print(f"  - 统计摘要: {summary_path}")
    
    return all_scenes_data


if __name__ == "__main__":
    main()
