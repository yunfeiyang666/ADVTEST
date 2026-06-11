"""
生成带ego朝向箭头的BEV图，帮助理解"前方"的含义
"""
import os
import sys
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

import config


def setup_matplotlib():
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
    plt.rcParams['axes.unicode_minus'] = False


def quaternion_to_yaw(rotation):
    """从四元数提取yaw角（弧度）"""
    w, x, y, z = rotation[0], rotation[1], rotation[2], rotation[3]
    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = np.arctan2(siny_cosp, cosy_cosp)
    return yaw


def load_scene_graph():
    json_path = os.path.join(config.OUTPUT_DIR, 'single_scene_demo', 'single_scene_full_graph.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def visualize_with_ego_direction(scene_graph, output_dir):
    """生成带ego朝向箭头的BEV图"""
    
    # 颜色映射
    color_map = {
        'ego': '#e74c3c',       # 红色
        'car': '#3498db',       # 蓝色
        'pedestrian': '#2ecc71', # 绿色
        'truck': '#f39c12',     # 橙色
        'bus': '#9b59b6',       # 紫色
        'bicycle': '#1abc9c'    # 青色
    }
    
    fig, ax = plt.subplots(figsize=(16, 14))
    
    # 找到ego
    ego_data = None
    for obj in scene_graph['objects']:
        if obj['unique_id'] == 'ego':
            ego_data = obj
            break
    
    ego_x = ego_data['translation'][0]
    ego_y = ego_data['translation'][1]
    ego_yaw = quaternion_to_yaw(ego_data['rotation'])
    ego_yaw_deg = np.degrees(ego_yaw)
    
    # 绘制所有对象（带朝向箭头）
    for obj in scene_graph['objects']:
        x = obj['translation'][0]
        y = obj['translation'][1]
        obj_type = obj['type']
        color = color_map.get(obj_type, 'gray')
        
        # 获取对象朝向
        obj_yaw = quaternion_to_yaw(obj['rotation'])
        
        if obj_type == 'ego':
            # 绘制ego（大一些）
            ax.scatter(x, y, c=color, s=400, zorder=10, edgecolors='black', linewidths=2)
            ax.annotate('EGO', (x, y), fontsize=10, ha='center', va='center', 
                       fontweight='bold', color='white', zorder=11)
            # ego的朝向箭头单独绘制（更长更明显）
        else:
            ax.scatter(x, y, c=color, s=100, alpha=0.7, zorder=5)
            ax.annotate(obj['unique_id'], (x, y), fontsize=7, ha='center', va='bottom',
                       xytext=(0, 5), textcoords='offset points')
            
            # 绘制对象朝向箭头（短箭头）
            arrow_len = 5  # 箭头长度
            dx = arrow_len * np.cos(obj_yaw)
            dy = arrow_len * np.sin(obj_yaw)
            ax.arrow(x, y, dx, dy, head_width=1.5, head_length=1, 
                    fc=color, ec=color, alpha=0.8, zorder=6)
    
    # 绘制ego的朝向箭头（前方）
    arrow_length = 30
    front_x = ego_x + arrow_length * np.cos(ego_yaw)
    front_y = ego_y + arrow_length * np.sin(ego_yaw)
    
    ax.annotate('', xy=(front_x, front_y), xytext=(ego_x, ego_y),
                arrowprops=dict(arrowstyle='->', color='red', lw=4))
    ax.text(front_x, front_y + 5, f'FRONT\n(ego朝向: {ego_yaw_deg:.1f}°)', 
            ha='center', fontsize=12, color='red', fontweight='bold')
    
    # 绘制四个方向的扇形区域
    # 前方: yaw-45° ~ yaw+45°
    # 左侧: yaw+45° ~ yaw+135°
    # 后方: yaw+135° ~ yaw-135°
    # 右侧: yaw-135° ~ yaw-45°
    
    radius = 80
    for direction, (start_offset, end_offset, color, alpha) in {
        'FRONT': (-45, 45, '#2ecc71', 0.15),
        'LEFT': (45, 135, '#3498db', 0.1),
        'REAR': (135, 225, '#95a5a6', 0.1),
        'RIGHT': (-135, -45, '#f39c12', 0.1)
    }.items():
        theta1 = ego_yaw_deg + start_offset
        theta2 = ego_yaw_deg + end_offset
        wedge = mpatches.Wedge((ego_x, ego_y), radius, theta1, theta2, 
                               alpha=alpha, color=color, zorder=1)
        ax.add_patch(wedge)
    
    # 绘制距离圈（以ego为中心）
    for r in [20, 40, 60, 80]:
        circle = plt.Circle((ego_x, ego_y), r, fill=False, color='gray', 
                            linestyle=':', alpha=0.5, zorder=2)
        ax.add_patch(circle)
    
    # 添加世界坐标系方向标注
    ax.annotate('', xy=(ego_x + 100, ego_y), xytext=(ego_x + 70, ego_y),
                arrowprops=dict(arrowstyle='->', color='black', lw=2))
    ax.text(ego_x + 105, ego_y, 'X (东)', fontsize=10)
    
    ax.annotate('', xy=(ego_x, ego_y + 100), xytext=(ego_x, ego_y + 70),
                arrowprops=dict(arrowstyle='->', color='black', lw=2))
    ax.text(ego_x, ego_y + 105, 'Y (北)', fontsize=10, ha='center')
    
    # 图例
    legend_elements = [
        mpatches.Patch(color='#2ecc71', alpha=0.3, label='前方 (front)'),
        mpatches.Patch(color='#3498db', alpha=0.3, label='左侧 (left)'),
        mpatches.Patch(color='#95a5a6', alpha=0.3, label='后方 (rear)'),
        mpatches.Patch(color='#f39c12', alpha=0.3, label='右侧 (right)'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='#e74c3c', 
                   markersize=15, label='Ego车'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='#3498db', 
                   markersize=10, label='车辆'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='#2ecc71', 
                   markersize=10, label='行人'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='#f39c12', 
                   markersize=10, label='卡车'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10)
    
    # 设置坐标轴
    ax.set_xlim(ego_x - 100, ego_x + 120)
    ax.set_ylim(ego_y - 100, ego_y + 120)
    ax.set_aspect('equal')
    ax.set_xlabel('X (世界坐标)', fontsize=12)
    ax.set_ylabel('Y (世界坐标)', fontsize=12)
    ax.set_title(f'场景BEV图 - 带Ego朝向标注\nEgo朝向: {ego_yaw_deg:.1f}° (绿色扇形为"前方"区域)', 
                fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    
    # 保存
    output_path = os.path.join(output_dir, 'bev_with_ego_direction.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"✓ 带ego朝向的BEV图已保存: {output_path}")
    return output_path


def main():
    setup_matplotlib()
    
    print("=" * 60)
    print("  生成带Ego朝向标注的BEV图")
    print("=" * 60)
    
    output_dir = os.path.join(config.OUTPUT_DIR, 'single_scene_demo')
    
    print("\n加载场景图...")
    scene_graph = load_scene_graph()
    
    visualize_with_ego_direction(scene_graph, output_dir)
    
    print("\n" + "=" * 60)
    print("✓ 完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
