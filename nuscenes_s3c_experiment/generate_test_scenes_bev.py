"""
生成测试场景的BEV图 - 显示所有对象及其朝向和status状态，不画关系线
"""
import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path
import numpy as np


def quaternion_to_yaw(q):
    """四元数转偏航角"""
    w, x, y, z = q
    yaw = np.arctan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return yaw


def draw_bev_scene(scene_graph_path, output_path):
    """绘制BEV场景图"""
    
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    
    scene_name = scene_graph.get('scene_name', 'unknown')
    frame_idx = scene_graph.get('frame_idx', 0)
    nodes = scene_graph.get('nodes', [])
    
    # 创建图形 - 分为主图和信息表
    fig = plt.figure(figsize=(18, 10))
    # 左侧BEV图占75%，右侧信息表占23%
    ax = fig.add_axes([0.05, 0.08, 0.70, 0.88])  # [left, bottom, width, height]
    
    # 对象类型的颜色和大小
    type_colors = {
        'ego': '#FF0000',
        'car': '#1f77b4',
        'truck': '#ff7f0e',
        'bus': '#2ca02c',
        'bicycle': '#d62728',
        'motorcycle': '#9467bd',
        'pedestrian': '#8c564b',
        'trailer': '#e377c2',
        'barrier': '#7f7f7f',
    }
    
    type_sizes = {
        'ego': (4.5, 2.0),
        'car': (4.5, 2.0),
        'truck': (6.0, 2.5),
        'bus': (10.0, 2.8),
        'bicycle': (1.8, 0.6),
        'motorcycle': (2.0, 0.8),
        'pedestrian': (0.6, 0.6),
        'trailer': (7.0, 2.5),
        'barrier': (1.0, 0.5),
    }
    
    # 收集所有坐标用于设置图形范围
    all_x = []
    all_y = []
    
    # 收集对象信息用于右侧表格
    object_info = []
    
    # 绘制每个对象
    for idx, node in enumerate(nodes, 1):
        uid = node.get('unique_id', 'unknown')
        obj_type = node.get('type', 'unknown')
        translation = node.get('translation', {})
        rotation = node.get('rotation', [1, 0, 0, 0])
        status = node.get('status', 'unknown')
        
        x = translation.get('x', 0)
        y = translation.get('y', 0)
        all_x.append(x)
        all_y.append(y)
        
        # 计算朝向
        yaw = quaternion_to_yaw(rotation)
        
        # 获取颜色和大小
        color = type_colors.get(obj_type, '#cccccc')
        length, width = type_sizes.get(obj_type, (2.0, 1.0))
        
        # 绘制矩形（车辆/对象）
        rect = patches.Rectangle(
            (x - length/2, y - width/2),
            length, width,
            linewidth=2,
            edgecolor=color,
            facecolor=color,
            alpha=0.6,
            angle=np.degrees(yaw),
            rotation_point='center'
        )
        ax.add_patch(rect)
        
        # 绘制朝向箭头
        arrow_length = length * 0.6
        dx = arrow_length * np.cos(yaw)
        dy = arrow_length * np.sin(yaw)
        ax.arrow(x, y, dx, dy, 
                head_width=width*0.5, 
                head_length=length*0.3,
                fc=color, ec='black', 
                linewidth=1.5, 
                alpha=0.9,
                zorder=10)
        
        # 对象上标注序号 + unique_id
        # 序号在圆圈中
        ax.text(x, y, str(idx),
               fontsize=12,
               ha='center',
               va='center',
               color='white',
               fontweight='bold',
               bbox=dict(boxstyle='circle,pad=0.3', 
                        facecolor='black', 
                        edgecolor='white',
                        linewidth=2,
                        alpha=0.8),
               zorder=15)
        
        # unique_id 在序号下方（小字体）
        ax.text(x, y - width*0.8, uid,
               fontsize=7,
               ha='center',
               va='top',
               color='white',
               fontweight='normal',
               bbox=dict(boxstyle='round,pad=0.2', 
                        facecolor=color, 
                        edgecolor='white',
                        linewidth=1,
                        alpha=0.9),
               zorder=14)
        
        # 收集对象信息
        object_info.append({
            'idx': idx,
            'id': uid,
            'type': obj_type,
            'status': status if status != 'unknown' else '-',
            'color': color
        })
    
    # 设置坐标轴范围
    if all_x and all_y:
        x_min, x_max = min(all_x) - 20, max(all_x) + 20
        y_min, y_max = min(all_y) - 20, max(all_y) + 20
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)
    
    # 网格和标签
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_xlabel('X (meters)', fontsize=12)
    ax.set_ylabel('Y (meters)', fontsize=12)
    ax.set_title(f'BEV View: {scene_name} Frame {frame_idx}\n(Objects with Orientations & Status)', 
                fontsize=14, fontweight='bold')
    ax.set_aspect('equal')
    
    # 在右侧添加对象信息表（两列布局）
    info_ax = fig.add_axes([0.77, 0.08, 0.21, 0.88])
    info_ax.axis('off')
    
    # 表格标题
    info_ax.text(0.5, 0.98, 'Objects', 
                fontsize=12, fontweight='bold', ha='center', va='top')
    
    # 计算每列显示多少个对象
    num_objects = len(object_info)
    col1_count = (num_objects + 1) // 2  # 第一列
    
    # 绘制两列
    y_start = 0.93
    line_height = 0.022
    
    for col_idx in range(2):
        # 列位置
        if col_idx == 0:
            x_base = 0.05
            obj_list = object_info[:col1_count]
        else:
            x_base = 0.52
            obj_list = object_info[col1_count:]
        
        y_pos = y_start
        
        for obj in obj_list:
            # 序号（带颜色圆圈）
            circle = patches.Circle((x_base + 0.06, y_pos + 0.005), 0.012, 
                                   facecolor=obj['color'], 
                                   edgecolor='black', 
                                   linewidth=1,
                                   alpha=0.8,
                                   transform=info_ax.transAxes)
            info_ax.add_patch(circle)
            info_ax.text(x_base + 0.06, y_pos, str(obj['idx']), 
                        fontsize=6, fontweight='bold', ha='center', va='center',
                        color='white')
            
            # ID + Type
            info_text = f"{obj['id']}"
            info_ax.text(x_base + 0.13, y_pos, info_text, fontsize=7, ha='left', va='center')
            
            # Status (带颜色标记)
            status_text = obj['status']
            if status_text in ['moving', 'with_rider']:
                status_color = 'green'
            elif status_text in ['stopped', 'parked', 'standing', 'without_rider']:
                status_color = 'red'
            else:
                status_color = 'gray'
            
            # 简化status显示
            status_short = status_text.replace('with_rider', 'w/rider').replace('without_rider', 'w/o rider')
            info_ax.text(x_base + 0.13, y_pos - 0.009, f"[{status_short}]",
                        fontsize=6, ha='left', va='center',
                        color=status_color, fontweight='bold', style='italic')
            
            y_pos -= line_height
    
    # 保存
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"✓ 已生成: {output_path}")


def main():
    """生成4个测试场景的BEV图"""
    
    scene_files = [
        'output/coverage_analysis/scene_graphs/scene-0103_frame25_scene_graph.json',
        'output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json',
        'output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json',
        'output/coverage_analysis/scene_graphs/scene-0916_frame8_scene_graph.json',
    ]
    
    output_dir = Path('output/coverage_analysis/bev_test_scenes')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("="*70)
    print("  生成测试场景BEV图（含朝向和status状态）")
    print("="*70)
    
    for scene_file in scene_files:
        scene_path = Path(scene_file)
        if not scene_path.exists():
            print(f"⚠️  文件不存在: {scene_file}")
            continue
        
        # 生成输出文件名
        scene_name = scene_path.stem  # 如 scene-0103_frame25_scene_graph
        output_file = output_dir / f"{scene_name}_bev.png"
        
        print(f"\n处理: {scene_path.name}")
        draw_bev_scene(scene_path, output_file)
    
    print(f"\n{'='*70}")
    print(f"  所有BEV图已保存到: {output_dir}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
