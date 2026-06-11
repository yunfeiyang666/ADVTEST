"""
选择2组代表性场景（低-中-高密度）
详细统计每个场景的对象组成特征
避开scene-0061
"""
import os
import sys
from collections import defaultdict

# 添加本地nuscenes-devkit路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nuscenes.nuscenes import NuScenes
import config


def get_category_group(category):
    """将详细类别归类为大类"""
    if 'vehicle.car' in category:
        return 'car'
    elif 'vehicle.truck' in category:
        return 'truck'
    elif 'vehicle.bus' in category:
        return 'bus'
    elif 'vehicle.bicycle' in category:
        return 'bicycle'
    elif 'vehicle.motorcycle' in category:
        return 'motorcycle'
    elif 'human.pedestrian' in category:
        return 'pedestrian'
    elif 'movable_object' in category:
        return 'movable_object'
    else:
        return 'other'


def analyze_frame_detail(nusc, scene, frame_idx):
    """详细分析单帧的对象组成"""
    # 找到指定帧
    sample_token = scene['first_sample_token']
    current_frame = 0
    
    while sample_token and current_frame < frame_idx:
        sample = nusc.get('sample', sample_token)
        sample_token = sample['next']
        current_frame += 1
    
    if not sample_token:
        return None
    
    sample = nusc.get('sample', sample_token)
    
    # 统计对象
    annotations = sample['anns']
    total_count = len(annotations)
    
    # 按类型统计
    type_count = defaultdict(int)
    category_detail = defaultdict(list)
    
    for ann_token in annotations:
        ann = nusc.get('sample_annotation', ann_token)
        category = ann['category_name']
        group = get_category_group(category)
        
        type_count[group] += 1
        category_detail[group].append(category)
    
    # 统计子类型
    subtype_count = {}
    for group, categories in category_detail.items():
        subtype_count[group] = {}
        for cat in categories:
            subtype_count[group][cat] = subtype_count[group].get(cat, 0) + 1
    
    return {
        'scene_name': scene['name'],
        'scene_description': scene['description'],
        'frame_idx': frame_idx,
        'total_objects': total_count,
        'type_count': dict(type_count),
        'subtype_count': subtype_count
    }


def analyze_all_scenes(nusc, exclude_scenes=None):
    """分析所有场景的每一帧"""
    if exclude_scenes is None:
        exclude_scenes = []
    
    frame_stats = []
    
    for scene in nusc.scene:
        # 跳过排除的场景
        if scene['name'] in exclude_scenes:
            continue
        
        sample_token = scene['first_sample_token']
        frame_idx = 0
        
        while sample_token:
            sample = nusc.get('sample', sample_token)
            
            # 统计对象
            annotations = sample['anns']
            obj_count = len(annotations)
            
            # 按类型统计
            type_count = defaultdict(int)
            for ann_token in annotations:
                ann = nusc.get('sample_annotation', ann_token)
                group = get_category_group(ann['category_name'])
                type_count[group] += 1
            
            frame_stats.append({
                'scene_name': scene['name'],
                'scene_description': scene['description'],
                'frame_idx': frame_idx,
                'total_objects': obj_count,
                'type_count': dict(type_count)
            })
            
            sample_token = sample['next']
            frame_idx += 1
    
    return frame_stats


def find_density_groups(frame_stats):
    """找出低-中-高密度的场景组"""
    # 按对象数量排序
    sorted_frames = sorted(frame_stats, key=lambda x: x['total_objects'])
    
    # 计算分位数
    total = len(sorted_frames)
    low_threshold = sorted_frames[int(total * 0.2)]['total_objects']  # 20%分位
    mid_low = sorted_frames[int(total * 0.35)]['total_objects']       # 35%分位
    mid_high = sorted_frames[int(total * 0.65)]['total_objects']      # 65%分位
    high_threshold = sorted_frames[int(total * 0.8)]['total_objects'] # 80%分位
    
    # 分类
    low_density = [f for f in frame_stats if f['total_objects'] <= low_threshold]
    mid_density = [f for f in frame_stats if mid_low <= f['total_objects'] <= mid_high]
    high_density = [f for f in frame_stats if f['total_objects'] >= high_threshold]
    
    return low_density, mid_density, high_density, {
        'low': low_threshold,
        'mid_low': mid_low,
        'mid_high': mid_high,
        'high': high_threshold
    }


def select_representative_scenes(frame_stats, count=2):
    """选择代表性场景（低-中-高密度各count组）"""
    low_density, mid_density, high_density, thresholds = find_density_groups(frame_stats)
    
    print("\n" + "=" * 70)
    print("  对象密度阈值")
    print("=" * 70)
    print(f"  低密度: ≤ {thresholds['low']} 个对象")
    print(f"  中密度: {thresholds['mid_low']} - {thresholds['mid_high']} 个对象")
    print(f"  高密度: ≥ {thresholds['high']} 个对象")
    
    # 选择场景：优先选择类型多样的
    def diversity_score(frame):
        """计算场景多样性得分"""
        type_count = frame['type_count']
        # 类型数量 + 对象总数的平衡
        num_types = len(type_count)
        return num_types * 10 + frame['total_objects'] * 0.1
    
    # 按场景分组
    scene_groups = defaultdict(list)
    for frame in frame_stats:
        scene_groups[frame['scene_name']].append(frame)
    
    # 为每个密度选择count个不同场景
    selected = {
        'low': [],
        'mid': [],
        'high': []
    }
    
    # 选择低密度场景
    low_by_scene = defaultdict(list)
    for frame in low_density:
        low_by_scene[frame['scene_name']].append(frame)
    
    # 每个场景选最多样的帧
    scene_best = []
    for scene_name, frames in low_by_scene.items():
        best_frame = max(frames, key=diversity_score)
        scene_best.append(best_frame)
    
    # 按多样性排序，选top count
    scene_best.sort(key=diversity_score, reverse=True)
    selected['low'] = scene_best[:count]
    
    # 选择中密度场景
    mid_by_scene = defaultdict(list)
    for frame in mid_density:
        mid_by_scene[frame['scene_name']].append(frame)
    
    scene_best = []
    for scene_name, frames in mid_by_scene.items():
        best_frame = max(frames, key=diversity_score)
        scene_best.append(best_frame)
    
    scene_best.sort(key=diversity_score, reverse=True)
    selected['mid'] = scene_best[:count]
    
    # 选择高密度场景
    high_by_scene = defaultdict(list)
    for frame in high_density:
        high_by_scene[frame['scene_name']].append(frame)
    
    scene_best = []
    for scene_name, frames in high_by_scene.items():
        best_frame = max(frames, key=diversity_score)
        scene_best.append(best_frame)
    
    scene_best.sort(key=diversity_score, reverse=True)
    selected['high'] = scene_best[:count]
    
    return selected


def print_scene_details(nusc, scene_info):
    """打印场景详细信息"""
    print(f"\n{'=' * 70}")
    print(f"  {scene_info['scene_name']} 帧{scene_info['frame_idx']}")
    print("=" * 70)
    print(f"  场景描述: {scene_info['scene_description']}")
    print(f"  总对象数: {scene_info['total_objects']}")
    
    # 获取详细统计
    for scene in nusc.scene:
        if scene['name'] == scene_info['scene_name']:
            detail = analyze_frame_detail(nusc, scene, scene_info['frame_idx'])
            break
    
    if detail:
        print(f"\n  对象类型分布:")
        for obj_type, count in sorted(detail['type_count'].items(), key=lambda x: -x[1]):
            print(f"    {obj_type}: {count}")
        
        print(f"\n  详细子类型:")
        for group, subtypes in detail['subtype_count'].items():
            print(f"    {group}:")
            for subtype, count in sorted(subtypes.items(), key=lambda x: -x[1]):
                subtype_short = subtype.split('.')[-1]
                print(f"      - {subtype_short}: {count}")


def main():
    print("=" * 70)
    print("  选择2组代表性场景（低-中-高密度）")
    print("=" * 70)
    
    # 加载NuScenes
    print("\n加载NuScenes数据集...")
    nusc = NuScenes(
        version='v1.0-mini',
        dataroot=config.NUSCENES_DATAROOT,
        verbose=False
    )
    print(f"✓ 已加载 {len(nusc.scene)} 个场景")
    
    # 分析所有场景（排除scene-0061）
    print("\n分析所有场景（排除scene-0061）...")
    exclude_scenes = ['scene-0061']
    frame_stats = analyze_all_scenes(nusc, exclude_scenes=exclude_scenes)
    print(f"✓ 分析了 {len(frame_stats)} 帧")
    
    # 选择代表性场景
    print("\n选择代表性场景...")
    selected = select_representative_scenes(frame_stats, count=2)
    
    # 打印选择结果
    print("\n" + "#" * 70)
    print("#  选择结果：2组场景（低-中-高密度）")
    print("#" * 70)
    
    # 组1：低-中-高
    print("\n【组1：低-中-高密度场景】")
    print_scene_details(nusc, selected['low'][0])
    print_scene_details(nusc, selected['mid'][0])
    print_scene_details(nusc, selected['high'][0])
    
    # 组2：低-中-高
    print("\n【组2：低-中-高密度场景】")
    print_scene_details(nusc, selected['low'][1])
    print_scene_details(nusc, selected['mid'][1])
    print_scene_details(nusc, selected['high'][1])
    
    # 保存选择结果
    import json
    output_dir = os.path.join(config.OUTPUT_DIR, "coverage_analysis")
    os.makedirs(output_dir, exist_ok=True)
    
    selection_file = os.path.join(output_dir, "selected_scenes.json")
    
    # 获取详细信息
    selected_scenes = []
    for density in ['low', 'mid', 'high']:
        for scene_info in selected[density]:
            for scene in nusc.scene:
                if scene['name'] == scene_info['scene_name']:
                    detail = analyze_frame_detail(nusc, scene, scene_info['frame_idx'])
                    selected_scenes.append(detail)
                    break
    
    with open(selection_file, 'w', encoding='utf-8') as f:
        json.dump(selected_scenes, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'=' * 70}")
    print("  选择完成")
    print("=" * 70)
    print(f"✓ 已选择 {len(selected_scenes)} 个场景")
    print(f"✓ 场景信息已保存: {selection_file}")
    
    print("\n下一步:")
    print("  1. 生成场景图: python generate_selected_scenes.py")
    print("  2. 导入Neo4j测试")


if __name__ == "__main__":
    main()
