"""
生成PPT所需的所有可视化材料

按照老师要求的顺序：
1. NuScenes单个数据情况（数据统计）
2. 六相机图
3. BEV图（有名称标注）
4. 每个car的json信息
5. car之间的关系
6. 建好的数据库的图
7. 查询操作（文字、函数、结果）
"""
import os
import sys
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.collections import PatchCollection

# 添加本地nuscenes-devkit路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

from nuscenes.nuscenes import NuScenes
from nuscenes.utils.data_classes import LidarPointCloud
from PIL import Image
import config


def setup_matplotlib():
    """设置matplotlib中文显示"""
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
    plt.rcParams['axes.unicode_minus'] = False


def generate_data_statistics(nusc, output_dir):
    """
    1. 生成NuScenes数据情况统计
    """
    print("\n1. 生成数据统计...")
    
    # 统计场景数量
    num_scenes = len(nusc.scene)
    
    # 统计样本数量
    num_samples = len(nusc.sample)
    
    # 统计对象类别
    category_counts = {}
    for sample_ann in nusc.sample_annotation:
        category = sample_ann['category_name']
        category_counts[category] = category_counts.get(category, 0) + 1
    
    # 创建统计可视化
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle('NuScenes v1.0-mini 数据集统计', fontsize=16, fontweight='bold')
    
    # 基本统计
    ax1 = axes[0, 0]
    stats_text = f"""
    数据集版本: v1.0-mini
    
    场景数量: {num_scenes}
    样本数量: {num_samples}
    标注对象总数: {len(nusc.sample_annotation)}
    
    传感器配置:
    - 6个相机 (CAM_FRONT, CAM_BACK, etc.)
    - 5个雷达
    - 1个激光雷达
    """
    ax1.text(0.1, 0.5, stats_text, fontsize=12, verticalalignment='center',
             family='monospace')
    ax1.axis('off')
    ax1.set_title('数据集概览', fontsize=14, fontweight='bold')
    
    # 对象类别分布（前10）
    ax2 = axes[0, 1]
    top_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    categories = [c[0].split('.')[-1] for c in top_categories]
    counts = [c[1] for c in top_categories]
    
    ax2.barh(categories, counts, color='steelblue')
    ax2.set_xlabel('数量', fontsize=12)
    ax2.set_title('对象类别分布（前10）', fontsize=14, fontweight='bold')
    ax2.invert_yaxis()
    
    # 简化类别分布
    ax3 = axes[1, 0]
    simplified_counts = {
        'Car': 0,
        'Pedestrian': 0,
        'Bicycle': 0,
        'Motorcycle': 0,
        'Truck': 0,
        'Bus': 0,
        'Other': 0
    }
    
    for cat, count in category_counts.items():
        if 'car' in cat.lower():
            simplified_counts['Car'] += count
        elif 'pedestrian' in cat.lower() or 'human' in cat.lower():
            simplified_counts['Pedestrian'] += count
        elif 'bicycle' in cat.lower():
            simplified_counts['Bicycle'] += count
        elif 'motorcycle' in cat.lower():
            simplified_counts['Motorcycle'] += count
        elif 'truck' in cat.lower():
            simplified_counts['Truck'] += count
        elif 'bus' in cat.lower():
            simplified_counts['Bus'] += count
        else:
            simplified_counts['Other'] += count
    
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8', '#F7DC6F', '#CCCCCC']
    ax3.pie([v for v in simplified_counts.values() if v > 0],
            labels=[k for k, v in simplified_counts.items() if v > 0],
            autopct='%1.1f%%',
            colors=colors,
            startangle=90)
    ax3.set_title('简化类别分布', fontsize=14, fontweight='bold')
    
    # 场景统计
    ax4 = axes[1, 1]
    scene_lengths = [nusc.get('scene', scene['token'])['nbr_samples'] for scene in nusc.scene]
    ax4.hist(scene_lengths, bins=20, color='coral', edgecolor='black')
    ax4.set_xlabel('场景长度（样本数）', fontsize=12)
    ax4.set_ylabel('场景数量', fontsize=12)
    ax4.set_title('场景长度分布', fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    output_path = os.path.join(output_dir, '1_data_statistics.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"  ✓ 数据统计图已保存: {output_path}")
    
    return {
        'num_scenes': num_scenes,
        'num_samples': num_samples,
        'num_annotations': len(nusc.sample_annotation),
        'category_counts': category_counts,
        'simplified_counts': simplified_counts
    }


def generate_six_camera_view(nusc, sample_token, output_dir):
    """
    2. 生成六相机图
    """
    print("\n2. 生成六相机图...")
    
    sample = nusc.get('sample', sample_token)
    
    # 六个相机的顺序
    camera_channels = [
        'CAM_FRONT',
        'CAM_FRONT_RIGHT',
        'CAM_BACK_RIGHT',
        'CAM_BACK',
        'CAM_BACK_LEFT',
        'CAM_FRONT_LEFT'
    ]
    
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle(f'六相机视图 - {sample["timestamp"]}', fontsize=16, fontweight='bold')
    
    for idx, cam_channel in enumerate(camera_channels):
        row = idx // 3
        col = idx % 3
        ax = axes[row, col]
        
        # 获取相机数据
        cam_token = sample['data'][cam_channel]
        cam_data = nusc.get('sample_data', cam_token)
        
        # 读取图像
        img_path = os.path.join(nusc.dataroot, cam_data['filename'])
        img = Image.open(img_path)
        
        # 显示图像
        ax.imshow(img)
        ax.set_title(cam_channel, fontsize=12, fontweight='bold')
        ax.axis('off')
    
    plt.tight_layout()
    output_path = os.path.join(output_dir, '2_six_camera_view.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"  ✓ 六相机图已保存: {output_path}")


def generate_bev_with_labels(nusc, sample_token, scene_graph_data, output_dir):
    """
    3. 生成BEV图（带名称标注）
    """
    print("\n3. 生成BEV图（带标注）...")
    
    sample = nusc.get('sample', sample_token)
    
    # 创建BEV图
    fig, ax = plt.subplots(figsize=(12, 12))
    ax.set_xlim(-50, 50)
    ax.set_ylim(-50, 50)
    ax.set_xlabel('X (米)', fontsize=12)
    ax.set_ylabel('Y (米)', fontsize=12)
    ax.set_title('鸟瞰图 (BEV) - 对象标注', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal')
    
    # 绘制ego车
    ego_rect = patches.Rectangle((-2, -1), 4, 2, linewidth=2, 
                                   edgecolor='red', facecolor='red', alpha=0.5)
    ax.add_patch(ego_rect)
    ax.text(0, 0, 'EGO', ha='center', va='center', fontsize=10, 
            fontweight='bold', color='white')
    
    # 颜色映射
    color_map = {
        'car': 'blue',
        'pedestrian': 'green',
        'bicycle': 'orange',
        'motorcycle': 'purple',
        'truck': 'brown',
        'bus': 'pink'
    }
    
    # 绘制其他对象
    for obj in scene_graph_data['objects']:
        if obj['unique_id'] == 'ego':
            continue
        
        x = obj['translation']['x']
        y = obj['translation']['y']
        
        # 获取尺寸
        if obj['size']:
            length = obj['size']['length']
            width = obj['size']['width']
        else:
            length = 2
            width = 1
        
        # 获取颜色
        color = color_map.get(obj['type'].lower(), 'gray')
        
        # 绘制对象
        rect = patches.Rectangle((x - length/2, y - width/2), length, width,
                                  linewidth=1, edgecolor=color, 
                                  facecolor=color, alpha=0.3)
        ax.add_patch(rect)
        
        # 添加标签（唯一ID）
        ax.text(x, y, obj['unique_id'], ha='center', va='center',
                fontsize=8, fontweight='bold', color=color)
    
    # 添加图例
    legend_elements = [
        patches.Patch(facecolor='red', alpha=0.5, label='Ego车'),
        patches.Patch(facecolor='blue', alpha=0.3, label='Car'),
        patches.Patch(facecolor='green', alpha=0.3, label='Pedestrian'),
        patches.Patch(facecolor='orange', alpha=0.3, label='Bicycle')
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10)
    
    plt.tight_layout()
    output_path = os.path.join(output_dir, '3_bev_with_labels.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"  ✓ BEV图（带标注）已保存: {output_path}")


def generate_car_json_info(scene_graph_data, output_dir):
    """
    4. 生成每个car的json信息
    """
    print("\n4. 生成car的json信息...")
    
    # 提取所有car对象
    cars = [obj for obj in scene_graph_data['objects'] 
            if obj['type'].lower() == 'car']
    
    # 保存为json
    output_path = os.path.join(output_dir, '4_car_json_info.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cars, f, indent=2, ensure_ascii=False)
    
    print(f"  ✓ Car JSON信息已保存: {output_path}")
    print(f"    - 包含 {len(cars)} 辆车的详细信息")
    
    # 创建可视化的json摘要
    fig, ax = plt.subplots(figsize=(14, 10))
    ax.axis('off')
    
    # 格式化显示前3辆车的信息
    display_text = "Car对象详细信息 (JSON格式)\n\n"
    for i, car in enumerate(cars[:3]):
        display_text += f"=== {car['unique_id']} ===\n"
        display_text += json.dumps(car, indent=2, ensure_ascii=False)
        display_text += "\n\n"
    
    if len(cars) > 3:
        display_text += f"... 还有 {len(cars) - 3} 辆车的信息\n"
    
    ax.text(0.05, 0.95, display_text, fontsize=9, verticalalignment='top',
            family='monospace', transform=ax.transAxes)
    
    plt.tight_layout()
    img_path = os.path.join(output_dir, '4_car_json_info.png')
    plt.savefig(img_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"  ✓ Car JSON可视化已保存: {img_path}")


def generate_relationship_graph(scene_graph_data, output_dir):
    """
    5. 生成car之间的关系图
    """
    print("\n5. 生成关系图...")
    
    # 提取car之间的关系
    car_relations = [
        rel for rel in scene_graph_data['relationships']
        if 'car' in rel['source_type'].lower() or 'car' in rel['target_type'].lower()
    ]
    
    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_title('对象关系图（以Ego为中心）', fontsize=14, fontweight='bold')
    ax.axis('off')
    
    # 显示关系列表
    relation_text = "关系列表 (前20条):\n\n"
    for i, rel in enumerate(car_relations[:20]):
        relation_text += f"{i+1}. {rel['source']} -> {rel['target']}: "
        relation_text += f"{rel['predicates']} "
        relation_text += f"(距离: {rel['metrics']['distance']}m)\n"
    
    if len(car_relations) > 20:
        relation_text += f"\n... 还有 {len(car_relations) - 20} 条关系\n"
    
    relation_text += f"\n总关系数: {len(scene_graph_data['relationships'])}\n"
    relation_text += f"涉及Car的关系: {len(car_relations)}\n"
    
    ax.text(0.05, 0.95, relation_text, fontsize=10, verticalalignment='top',
            family='monospace', transform=ax.transAxes)
    
    plt.tight_layout()
    output_path = os.path.join(output_dir, '5_relationship_graph.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"  ✓ 关系图已保存: {output_path}")


def main():
    """主函数"""
    setup_matplotlib()
    
    print("=" * 60)
    print("生成PPT可视化材料")
    print("=" * 60)
    
    # 创建输出目录
    output_dir = os.path.join(config.OUTPUT_DIR, 'ppt_materials')
    os.makedirs(output_dir, exist_ok=True)
    
    # 初始化NuScenes
    print("\n初始化NuScenes...")
    nusc = NuScenes(version='v1.0-mini', dataroot=config.NUSCENES_DATA_ROOT, verbose=False)
    
    # 选择一个示例场景（第一个场景）
    scene = nusc.scene[0]
    sample_token = scene['first_sample_token']
    
    # 加载对应的场景图数据
    scene_graph_path = os.path.join(config.SCENE_GRAPHS_DIR, 
                                     'all_scene_graphs_full_relation.json')
    
    if not os.path.exists(scene_graph_path):
        print(f"\n错误: 找不到场景图文件: {scene_graph_path}")
        print("请先运行 step2_full_relation_scene_graph.py")
        return
    
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        all_scene_graphs = json.load(f)
    
    scene_graph_data = all_scene_graphs[0]  # 使用第一个场景
    
    # 生成所有可视化材料
    stats = generate_data_statistics(nusc, output_dir)
    generate_six_camera_view(nusc, sample_token, output_dir)
    generate_bev_with_labels(nusc, sample_token, scene_graph_data, output_dir)
    generate_car_json_info(scene_graph_data, output_dir)
    generate_relationship_graph(scene_graph_data, output_dir)
    
    print("\n" + "=" * 60)
    print("✓ 所有PPT材料生成完成！")
    print("=" * 60)
    print(f"\n输出目录: {output_dir}")
    print("\n生成的文件:")
    print("  1. 1_data_statistics.png - 数据统计")
    print("  2. 2_six_camera_view.png - 六相机图")
    print("  3. 3_bev_with_labels.png - BEV图（带标注）")
    print("  4. 4_car_json_info.json - Car的JSON信息")
    print("  5. 4_car_json_info.png - Car的JSON可视化")
    print("  6. 5_relationship_graph.png - 关系图")
    print("\n提示:")
    print("  - 数据库截图需要手动在Neo4j Browser中截取")
    print("  - 查询操作示例将在下一步生成")


if __name__ == "__main__":
    main()
