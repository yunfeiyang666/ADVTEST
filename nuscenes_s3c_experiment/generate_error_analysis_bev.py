"""
为错误分析生成BEV可视化图
为每个测试场景生成清晰的BEV图，便于人工核验错误案例
"""
import json
import math
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyArrowPatch, Circle
import numpy as np
from pathlib import Path

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial']
plt.rcParams['axes.unicode_minus'] = False

def quaternion_to_yaw(q):
    """四元数转yaw角(弧度)"""
    if q is None:
        return 0
    w, x, y, z = q[0], q[1], q[2], q[3]
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return yaw

def get_color_for_type(obj_type):
    """为不同类型分配颜色"""
    colors = {
        'ego': '#FF0000',        # 红色
        'car': '#1f77b4',        # 蓝色
        'truck': '#8B4513',      # 棕色
        'bus': '#FF69B4',        # 粉色
        'pedestrian': '#2ca02c', # 绿色
        'bicycle': '#ff7f0e',    # 橙色
        'motorcycle': '#9467bd', # 紫色
        'trailer': '#DAA520',    # 金色
        'barrier': '#7f7f7f',    # 灰色
    }
    return colors.get(obj_type, '#000000')

def load_scene_graph(json_path):
    """加载场景图数据"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def generate_bev_for_scene(scene_path, output_path, scene_name, highlight_objects=None):
    """
    为单个场景生成BEV图
    
    Args:
        scene_path: 场景图JSON路径
        output_path: 输出图片路径
        scene_name: 场景名称
        highlight_objects: 需要高亮的对象列表（用于错误分析）
    """
    print(f"\n生成 {scene_name} 的BEV图...")
    
    scene_graph = load_scene_graph(scene_path)
    nodes = scene_graph['nodes']
    edges = scene_graph['edges']
    
    # 创建对象索引
    node_dict = {n['unique_id']: n for n in nodes}
    
    # 找到ego位置作为中心
    ego = node_dict.get('ego')
    if ego:
        center_x = ego['translation']['x']
        center_y = ego['translation']['y']
    else:
        # 计算所有对象的中心
        all_x = [n['translation']['x'] for n in nodes]
        all_y = [n['translation']['y'] for n in nodes]
        center_x = np.mean(all_x)
        center_y = np.mean(all_y)
    
    # 创建画布
    fig, ax = plt.subplots(figsize=(20, 16))
    
    # 统计各类型数量
    type_counts = {}
    for n in nodes:
        t = n['type']
        type_counts[t] = type_counts.get(t, 0) + 1
    
    # 绘制所有对象
    for n in nodes:
        uid = n['unique_id']
        obj_type = n['type']
        x = n['translation']['x']
        y = n['translation']['y']
        status = n.get('status', 'unknown')
        category = n.get('category', '')
        
        color = get_color_for_type(obj_type)
        
        # 确定大小
        if obj_type == 'ego':
            size = 300
            marker = 's'
        elif obj_type in ['car', 'truck', 'bus']:
            size = 150
            marker = 's'
        elif obj_type == 'pedestrian':
            size = 80
            marker = 'o'
        elif obj_type in ['bicycle', 'motorcycle']:
            size = 100
            marker = '^'
        elif obj_type == 'trailer':
            size = 180
            marker = 's'
        else:
            size = 60
            marker = 'o'
        
        # 高亮特定对象
        if highlight_objects and uid in highlight_objects:
            ax.scatter(x, y, s=size*2, c=color, marker=marker, alpha=0.9, 
                      edgecolors='red', linewidth=3, zorder=10)
        else:
            ax.scatter(x, y, s=size, c=color, marker=marker, alpha=0.7, 
                      edgecolors='black', linewidth=1, zorder=5)
        
        # 绘制朝向箭头
        if n.get('rotation'):
            yaw = quaternion_to_yaw(n['rotation'])
            arrow_len = 3
            dx = arrow_len * math.cos(yaw)
            dy = arrow_len * math.sin(yaw)
            ax.arrow(x, y, dx, dy, head_width=1, head_length=0.5, 
                    fc=color, ec=color, alpha=0.8, zorder=6)
        
        # 添加标签（显示ID和状态）
        if obj_type != 'barrier':  # barrier太多，不显示标签
            label = f"{uid}\n({status})"
            fontsize = 8 if obj_type == 'ego' else 6
            ax.annotate(label, (x, y), xytext=(3, 3), textcoords='offset points',
                       fontsize=fontsize, ha='left', va='bottom',
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))
    
    # 设置坐标范围
    range_size = 80  # 显示80米范围
    ax.set_xlim(center_x - range_size, center_x + range_size)
    ax.set_ylim(center_y - range_size, center_y + range_size)
    
    # 添加方向指示
    ax.annotate('', xy=(center_x, center_y + range_size * 0.9), 
               xytext=(center_x, center_y + range_size * 0.7),
               arrowprops=dict(arrowstyle='->', color='red', lw=2))
    ax.text(center_x, center_y + range_size * 0.95, 'Front/North', 
           fontsize=12, ha='center', color='red', fontweight='bold')
    
    # 添加图例
    from matplotlib.lines import Line2D
    legend_elements = []
    for obj_type in sorted(type_counts.keys()):
        count = type_counts[obj_type]
        color = get_color_for_type(obj_type)
        legend_elements.append(
            Line2D([0], [0], marker='o', color='w', markerfacecolor=color, 
                  markersize=10, label=f'{obj_type} ({count})')
        )
    ax.legend(handles=legend_elements, loc='upper left', fontsize=9, title='Object Types')
    
    # 标题和标签
    ax.set_title(f'BEV View - {scene_name}\nObjects: {len(nodes)}, Edges: {len(edges)}',
                fontsize=14, fontweight='bold')
    ax.set_xlabel('X (meters)', fontsize=12)
    ax.set_ylabel('Y (meters)', fontsize=12)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"✓ BEV图已保存: {output_path}")
    
    # 返回统计信息
    return {
        'total_nodes': len(nodes),
        'total_edges': len(edges),
        'type_counts': type_counts
    }

def print_scene_objects_summary(scene_path, scene_name):
    """打印场景对象摘要"""
    scene_graph = load_scene_graph(scene_path)
    nodes = scene_graph['nodes']
    
    print(f"\n{'='*60}")
    print(f"  {scene_name} 对象摘要")
    print(f"{'='*60}")
    
    # 按类型分组
    by_type = {}
    for n in nodes:
        t = n['type']
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(n)
    
    for obj_type in sorted(by_type.keys()):
        objs = by_type[obj_type]
        print(f"\n{obj_type} ({len(objs)}):")
        for obj in objs[:10]:  # 最多显示10个
            uid = obj['unique_id']
            status = obj.get('status', 'N/A')
            cat = obj.get('category', 'N/A')
            x = obj['translation']['x']
            y = obj['translation']['y']
            print(f"  {uid}: status={status}, pos=({x:.1f}, {y:.1f})")
        if len(objs) > 10:
            print(f"  ... ({len(objs)-10} more)")

def main():
    """主函数"""
    print("="*70)
    print("  生成错误分析BEV图")
    print("="*70)
    
    # 4个测试场景
    scenes = [
        ('output/coverage_analysis/scene_graphs/scene-0103_frame25_scene_graph.json', 'scene-0103_frame25'),
        ('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json', 'scene-0103_frame38'),
        ('output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json', 'scene-0553_frame8'),
        ('output/coverage_analysis/scene_graphs/scene-0916_frame8_scene_graph.json', 'scene-0916_frame8'),
    ]
    
    # 创建输出目录
    output_dir = Path('output/coverage_analysis/bev_analysis')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 为每个场景生成BEV图
    for scene_path, scene_name in scenes:
        if not Path(scene_path).exists():
            print(f"警告: 找不到场景文件 {scene_path}")
            continue
        
        # 生成BEV图
        output_path = output_dir / f'{scene_name}_bev.png'
        stats = generate_bev_for_scene(scene_path, output_path, scene_name)
        
        # 打印对象摘要
        print_scene_objects_summary(scene_path, scene_name)
    
    print("\n" + "="*70)
    print("✓ 所有BEV图生成完成！")
    print(f"  输出目录: {output_dir}")
    print("="*70)

if __name__ == "__main__":
    main()
