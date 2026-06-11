"""
生成car1为中心的相对位置可视化图
展示car1与周围对象的真实空间关系
"""
import os
import sys
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# 添加本地nuscenes-devkit路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

import config


def setup_matplotlib():
    """设置matplotlib中文显示"""
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
    plt.rcParams['axes.unicode_minus'] = False


def load_scene_graph():
    """加载场景图JSON"""
    json_path = os.path.join(config.OUTPUT_DIR, 'single_scene_demo', 'single_scene_full_graph.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_car1_center_view(scene_graph):
    """
    以car1为中心，计算所有对象的相对位置
    """
    # 找到car1
    car1_data = None
    for obj in scene_graph['objects']:
        if obj['unique_id'] == 'car1':
            car1_data = obj
            break
    
    if not car1_data:
        print("未找到car1")
        return None
    
    car1_x = car1_data['translation'][0]
    car1_y = car1_data['translation'][1]
    
    # 计算car1的朝向（从四元数转换）
    rotation = car1_data['rotation']
    # 简化：使用yaw角
    car1_yaw = 2 * np.arctan2(rotation[3], rotation[0])
    
    # 获取car1的关系
    car1_relations = []
    for rel in scene_graph['relationships']:
        if rel['source'] == 'car1':
            car1_relations.append(rel)
    
    # 计算相对位置（以car1为中心，car1朝向为正前方）
    objects_relative = []
    for rel in car1_relations:
        target_id = rel['target']
        # 找到目标对象
        target_data = None
        for obj in scene_graph['objects']:
            if obj['unique_id'] == target_id:
                target_data = obj
                break
        
        if target_data:
            # 计算相对位置
            dx = target_data['translation'][0] - car1_x
            dy = target_data['translation'][1] - car1_y
            
            # 旋转到car1坐标系（car1朝向为正Y轴）
            cos_yaw = np.cos(-car1_yaw)
            sin_yaw = np.sin(-car1_yaw)
            rel_x = dx * cos_yaw - dy * sin_yaw
            rel_y = dx * sin_yaw + dy * cos_yaw
            
            objects_relative.append({
                'unique_id': target_id,
                'type': target_data['type'],
                'rel_x': rel_x,
                'rel_y': rel_y,
                'distance': rel['metrics']['distance'],
                'direction': rel['predicates'][0],
                'distance_level': rel['predicates'][1]
            })
    
    return objects_relative


def visualize_car1_front(objects_relative, output_dir):
    """
    可视化car1前方的对象（真实相对位置）
    """
    # 只选择前方的对象
    front_objects = [obj for obj in objects_relative if obj['direction'] == 'front']
    
    # 颜色映射
    color_map = {
        'car': '#3498db',      # 蓝色
        'pedestrian': '#e74c3c', # 红色
        'truck': '#f39c12',    # 橙色
        'bus': '#9b59b6',      # 紫色
        'bicycle': '#2ecc71',  # 绿色
        'ego': '#1abc9c'       # 青色
    }
    
    fig, ax = plt.subplots(figsize=(14, 12))
    
    # 绘制car1（在原点）
    car1_rect = plt.Rectangle((-1, -2), 2, 4.6, color='#27ae60', alpha=0.8, zorder=10)
    ax.add_patch(car1_rect)
    ax.annotate('car1', (0, 0), fontsize=12, ha='center', va='center', 
                fontweight='bold', color='white', zorder=11)
    
    # 绘制car1的朝向箭头
    ax.annotate('', xy=(0, 8), xytext=(0, 3),
                arrowprops=dict(arrowstyle='->', color='#27ae60', lw=3))
    ax.text(0, 9, '前方 (front)', ha='center', fontsize=11, color='#27ae60', fontweight='bold')
    
    # 绘制前方对象
    for obj in front_objects:
        x, y = obj['rel_x'], obj['rel_y']
        color = color_map.get(obj['type'], 'gray')
        
        # 绘制对象点
        ax.scatter(x, y, c=color, s=200, alpha=0.8, zorder=5, edgecolors='black', linewidths=1)
        
        # 标注对象ID和距离
        label = f"{obj['unique_id']}\n({obj['distance']:.1f}m)"
        ax.annotate(label, (x, y), fontsize=8, ha='center', va='bottom',
                    xytext=(0, 8), textcoords='offset points')
        
        # 绘制到car1的连线
        ax.plot([0, x], [0, y], '--', color=color, alpha=0.3, linewidth=1)
    
    # 绘制距离圈
    for r in [10, 20, 30, 50]:
        circle = plt.Circle((0, 0), r, fill=False, color='gray', linestyle=':', alpha=0.5)
        ax.add_patch(circle)
        ax.text(r * 0.7, r * 0.7, f'{r}m', fontsize=9, color='gray', alpha=0.7)
    
    # 绘制方位扇形（前方区域：-45° ~ 45°）
    theta1, theta2 = 45, 135  # 在car1坐标系中，前方是90°方向
    wedge = mpatches.Wedge((0, 0), 60, theta1, theta2, alpha=0.1, color='green')
    ax.add_patch(wedge)
    
    # 图例
    legend_elements = [
        mpatches.Patch(color=color_map['car'], label='车辆 (car)'),
        mpatches.Patch(color=color_map['pedestrian'], label='行人 (pedestrian)'),
        mpatches.Patch(color=color_map['truck'], label='卡车 (truck)'),
        mpatches.Patch(color=color_map['bus'], label='公交 (bus)'),
        mpatches.Patch(color=color_map['bicycle'], label='自行车 (bicycle)'),
        mpatches.Patch(color='#27ae60', label='car1 (中心)'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10)
    
    # 设置坐标轴
    ax.set_xlim(-70, 70)
    ax.set_ylim(-20, 80)
    ax.set_aspect('equal')
    ax.set_xlabel('横向距离 (米)', fontsize=12)
    ax.set_ylabel('纵向距离 (米)', fontsize=12)
    ax.set_title(f'car1 前方对象的真实相对位置\n(共 {len(front_objects)} 个对象)', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='gray', linewidth=0.5)
    ax.axvline(x=0, color='gray', linewidth=0.5)
    
    # 保存
    output_path = os.path.join(output_dir, 'car1_front_objects_spatial.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"✓ car1前方对象空间位置图已保存: {output_path}")
    return output_path


def visualize_car1_all_directions(objects_relative, output_dir):
    """
    可视化car1所有方向的对象（真实相对位置）
    """
    # 颜色映射
    color_map = {
        'car': '#3498db',
        'pedestrian': '#e74c3c',
        'truck': '#f39c12',
        'bus': '#9b59b6',
        'bicycle': '#2ecc71',
        'ego': '#1abc9c'
    }
    
    direction_colors = {
        'front': '#2ecc71',  # 绿色
        'left': '#3498db',   # 蓝色
        'rear': '#e74c3c',   # 红色
        'right': '#f39c12'   # 橙色
    }
    
    fig, ax = plt.subplots(figsize=(16, 16))
    
    # 绘制car1（在原点）
    car1_rect = plt.Rectangle((-1, -2), 2, 4.6, color='#27ae60', alpha=0.8, zorder=10)
    ax.add_patch(car1_rect)
    ax.annotate('car1', (0, 0), fontsize=12, ha='center', va='center', 
                fontweight='bold', color='white', zorder=11)
    
    # 绘制方向标注
    ax.annotate('', xy=(0, 50), xytext=(0, 10), arrowprops=dict(arrowstyle='->', color='#2ecc71', lw=2))
    ax.text(0, 55, 'FRONT', ha='center', fontsize=10, color='#2ecc71', fontweight='bold')
    
    ax.annotate('', xy=(0, -50), xytext=(0, -10), arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=2))
    ax.text(0, -55, 'REAR', ha='center', fontsize=10, color='#e74c3c', fontweight='bold')
    
    ax.annotate('', xy=(-50, 0), xytext=(-10, 0), arrowprops=dict(arrowstyle='->', color='#3498db', lw=2))
    ax.text(-55, 0, 'LEFT', ha='center', fontsize=10, color='#3498db', fontweight='bold')
    
    ax.annotate('', xy=(50, 0), xytext=(10, 0), arrowprops=dict(arrowstyle='->', color='#f39c12', lw=2))
    ax.text(55, 0, 'RIGHT', ha='center', fontsize=10, color='#f39c12', fontweight='bold')
    
    # 绘制所有对象
    for obj in objects_relative:
        x, y = obj['rel_x'], obj['rel_y']
        type_color = color_map.get(obj['type'], 'gray')
        dir_color = direction_colors.get(obj['direction'], 'gray')
        
        # 绘制对象点（按类型着色）
        ax.scatter(x, y, c=type_color, s=150, alpha=0.8, zorder=5, 
                   edgecolors=dir_color, linewidths=2)
        
        # 只标注近距离对象的ID
        if obj['distance'] < 40:
            ax.annotate(obj['unique_id'], (x, y), fontsize=7, ha='center', va='bottom',
                        xytext=(0, 5), textcoords='offset points')
    
    # 绘制距离圈
    for r in [10, 30, 50, 70]:
        circle = plt.Circle((0, 0), r, fill=False, color='gray', linestyle=':', alpha=0.5)
        ax.add_patch(circle)
        ax.text(r + 2, 2, f'{r}m', fontsize=9, color='gray')
    
    # 绘制方位扇形
    for direction, (theta1, theta2, color) in {
        'front': (45, 135, '#2ecc71'),
        'left': (135, 225, '#3498db'),
        'rear': (225, 315, '#e74c3c'),
        'right': (-45, 45, '#f39c12')
    }.items():
        wedge = mpatches.Wedge((0, 0), 80, theta1, theta2, alpha=0.05, color=color)
        ax.add_patch(wedge)
    
    # 统计各方向数量
    dir_counts = {}
    for obj in objects_relative:
        d = obj['direction']
        dir_counts[d] = dir_counts.get(d, 0) + 1
    
    # 图例
    legend_elements = [
        mpatches.Patch(color=color_map['car'], label='车辆 (car)'),
        mpatches.Patch(color=color_map['pedestrian'], label='行人 (pedestrian)'),
        mpatches.Patch(color=color_map['truck'], label='卡车 (truck)'),
        mpatches.Patch(color=color_map['bus'], label='公交 (bus)'),
        mpatches.Patch(color=color_map['bicycle'], label='自行车 (bicycle)'),
        mpatches.Patch(color=color_map['ego'], label='ego'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10)
    
    # 添加统计信息
    stats_text = f"前方(front): {dir_counts.get('front', 0)}个\n"
    stats_text += f"左侧(left): {dir_counts.get('left', 0)}个\n"
    stats_text += f"后方(rear): {dir_counts.get('rear', 0)}个\n"
    stats_text += f"右侧(right): {dir_counts.get('right', 0)}个"
    ax.text(-75, 75, stats_text, fontsize=10, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    # 设置坐标轴
    ax.set_xlim(-85, 85)
    ax.set_ylim(-85, 85)
    ax.set_aspect('equal')
    ax.set_xlabel('横向距离 (米)', fontsize=12)
    ax.set_ylabel('纵向距离 (米)', fontsize=12)
    ax.set_title(f'car1 周围所有对象的真实相对位置\n(共 {len(objects_relative)} 个对象)', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    
    # 保存
    output_path = os.path.join(output_dir, 'car1_all_objects_spatial.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"✓ car1所有方向对象空间位置图已保存: {output_path}")
    return output_path


def main():
    setup_matplotlib()
    
    print("=" * 60)
    print("  生成car1相对位置可视化图")
    print("=" * 60)
    
    output_dir = os.path.join(config.OUTPUT_DIR, 'single_scene_demo')
    
    # 加载场景图
    print("\n加载场景图...")
    scene_graph = load_scene_graph()
    
    # 计算相对位置
    print("计算相对位置...")
    objects_relative = get_car1_center_view(scene_graph)
    
    if objects_relative:
        print(f"找到 {len(objects_relative)} 个与car1相关的对象")
        
        # 生成前方对象图
        visualize_car1_front(objects_relative, output_dir)
        
        # 生成所有方向图
        visualize_car1_all_directions(objects_relative, output_dir)
        
        print("\n" + "=" * 60)
        print("✓ 完成！")
        print("=" * 60)


if __name__ == "__main__":
    main()
