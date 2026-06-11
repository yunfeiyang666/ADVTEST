"""
单场景BEV可视化 - 带唯一ID标注

从生成的场景图数据创建鸟瞰视图，清晰展示每个对象的唯一ID
"""
import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from pathlib import Path

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial']
plt.rcParams['axes.unicode_minus'] = False


def load_scene_graph(json_path):
    """加载场景图数据"""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_color_for_type(obj_type):
    """为不同类型分配颜色"""
    colors = {
        'ego': '#FF0000',        # 红色
        'car': '#1f77b4',        # 蓝色
        'truck': '#8B4513',      # 棕色
        'bus': '#FF69B4',        # 粉色
        'pedestrian': '#2ca02c', # 绿色
        'bicycle': '#ff7f0e',    # 橙色
        'motorcycle': '#9467bd'  # 紫色
    }
    return colors.get(obj_type, '#7f7f7f')


def visualize_bev(scene_graph, output_path):
    """
    生成BEV鸟瞰图
    
    特点：
    - 每个对象标注唯一ID
    - 不同类型不同颜色
    - 显示对象尺寸（如果有）
    - 清晰的图例
    """
    print("\n生成BEV可视化...")
    
    # 创建画布
    fig, ax = plt.subplots(figsize=(16, 16))
    
    objects = scene_graph['objects']
    
    # 收集所有位置用于设置坐标范围
    all_x = []
    all_y = []
    
    # 绘制每个对象
    for obj in objects:
        obj_type = obj['type']
        unique_id = obj['unique_id']
        
        # 获取位置
        translation = obj['translation']
        if isinstance(translation, dict):
            x, y = translation['x'], translation['y']
        else:
            x, y = translation[0], translation[1]
        
        all_x.append(x)
        all_y.append(y)
        
        # 获取颜色
        color = get_color_for_type(obj_type)
        
        # 获取尺寸（如果有）
        if 'size' in obj and obj['size'] is not None:
            size = obj['size']
            if isinstance(size, dict):
                width, length = size['width'], size['length']
            else:
                width, length = size[0], size[1]
        else:
            # 默认尺寸
            if obj_type == 'ego':
                width, length = 1.8, 4.5
            elif obj_type == 'car':
                width, length = 1.8, 4.5
            elif obj_type == 'truck':
                width, length = 2.5, 6.0
            elif obj_type == 'bus':
                width, length = 2.5, 10.0
            elif obj_type == 'pedestrian':
                width, length = 0.6, 0.6
            elif obj_type == 'bicycle':
                width, length = 0.6, 1.7
            else:
                width, length = 1.0, 1.0
        
        # 绘制对象（用矩形表示）
        if obj_type == 'ego':
            # Ego车用更大更醒目的标记
            rect = patches.Rectangle(
                (x - length/2, y - width/2), length, width,
                linewidth=3, edgecolor=color, facecolor=color, alpha=0.6
            )
            ax.add_patch(rect)
            
            # Ego标签更大
            ax.text(x, y, unique_id, fontsize=14, fontweight='bold',
                   ha='center', va='center', color='white',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7))
        else:
            # 其他对象
            rect = patches.Rectangle(
                (x - length/2, y - width/2), length, width,
                linewidth=1.5, edgecolor=color, facecolor=color, alpha=0.4
            )
            ax.add_patch(rect)
            
            # 对象标签
            ax.text(x, y, unique_id, fontsize=9,
                   ha='center', va='center', color='black',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))
    
    # 设置坐标范围（以ego为中心，扩展一定范围）
    ego_x = objects[0]['translation']['x'] if isinstance(objects[0]['translation'], dict) else objects[0]['translation'][0]
    ego_y = objects[0]['translation']['y'] if isinstance(objects[0]['translation'], dict) else objects[0]['translation'][1]
    
    range_size = 100  # 显示ego周围100米范围
    ax.set_xlim(ego_x - range_size, ego_x + range_size)
    ax.set_ylim(ego_y - range_size, ego_y + range_size)
    
    # 绘制坐标轴
    ax.axhline(y=ego_y, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    ax.axvline(x=ego_x, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    
    # 添加方向标注
    arrow_len = range_size * 0.15
    ax.arrow(ego_x, ego_y + range_size * 0.7, 0, arrow_len,
            head_width=3, head_length=2, fc='red', ec='red', linewidth=2)
    ax.text(ego_x, ego_y + range_size * 0.9, 'North (前方)', 
           fontsize=12, ha='center', color='red', fontweight='bold')
    
    # 设置标题和标签
    ax.set_title(f'BEV View - {scene_graph["scene_name"]}\n{scene_graph.get("scene_description", "")}',
                fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('X (meters)', fontsize=12)
    ax.set_ylabel('Y (meters)', fontsize=12)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    
    # 创建图例
    from matplotlib.lines import Line2D
    legend_elements = []
    
    # 统计对象类型
    type_counts = {}
    for obj in objects:
        obj_type = obj['type']
        type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
    
    # 为每种类型创建图例项
    for obj_type, count in sorted(type_counts.items()):
        color = get_color_for_type(obj_type)
        legend_elements.append(
            Line2D([0], [0], marker='s', color='w', 
                  markerfacecolor=color, markersize=10,
                  label=f'{obj_type} ({count})')
        )
    
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10,
             title='Object Types', title_fontsize=12)
    
    # 添加统计信息
    stats_text = f"Total Objects: {len(objects)}\n"
    stats_text += f"Total Relationships: {len(scene_graph['relationships'])}"
    ax.text(0.02, 0.98, stats_text,
           transform=ax.transAxes, fontsize=10,
           verticalalignment='top',
           bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    # 保存图片
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ BEV图已保存: {output_path}")
    
    plt.close()


def visualize_relationships(scene_graph, output_path, max_relations=None):
    """
    可视化关系网络（显示所有关系）
    """
    print("\n生成完整关系网络图...")
    
    fig, ax = plt.subplots(figsize=(20, 20))
    
    objects = scene_graph['objects']
    relationships = scene_graph['relationships']
    
    # 绘制对象位置
    positions = {}
    for obj in objects:
        unique_id = obj['unique_id']
        translation = obj['translation']
        if isinstance(translation, dict):
            x, y = translation['x'], translation['y']
        else:
            x, y = translation[0], translation[1]
        positions[unique_id] = (x, y)
    
    # 先绘制所有关系线（在节点下层）
    print(f"  绘制 {len(relationships)} 条关系...")
    relations_to_draw = relationships if max_relations is None else sorted(relationships, key=lambda r: r['metrics']['distance'])[:max_relations]
    
    for rel in relations_to_draw:
        source_id = rel['source']
        target_id = rel['target']
        
        if source_id in positions and target_id in positions:
            x1, y1 = positions[source_id]
            x2, y2 = positions[target_id]
            
            # 根据距离级别设置线条样式
            distance_level = rel['predicates'][1]
            if distance_level == 'near':
                alpha, linewidth = 0.4, 1.0
            elif distance_level == 'mid':
                alpha, linewidth = 0.25, 0.7
            else:
                alpha, linewidth = 0.15, 0.4
            
            # 绘制连线
            ax.plot([x1, x2], [y1, y2], 'gray', alpha=alpha, linewidth=linewidth, zorder=1)
    
    # 在关系线上层绘制节点
    for obj in objects:
        unique_id = obj['unique_id']
        x, y = positions[unique_id]
        
        # 绘制节点
        color = get_color_for_type(obj['type'])
        ax.scatter(x, y, s=300, c=color, alpha=0.7, edgecolors='black', linewidth=2, zorder=2)
        ax.text(x, y+2, unique_id, fontsize=9, ha='center', va='bottom',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9), zorder=3)
    
    # 设置坐标范围
    ego_pos = positions['ego']
    range_size = 100
    ax.set_xlim(ego_pos[0] - range_size, ego_pos[0] + range_size)
    ax.set_ylim(ego_pos[1] - range_size, ego_pos[1] + range_size)
    
    title = f'Complete Relationship Network - {scene_graph["scene_name"]}'
    if max_relations is None:
        title += f'\n(All {len(relationships)} relationships)'
    else:
        title += f'\n(Showing closest {max_relations} relationships)'
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('X (meters)', fontsize=12)
    ax.set_ylabel('Y (meters)', fontsize=12)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ 关系网络图已保存: {output_path}")
    
    plt.close()


def main():
    """主函数"""
    print("=" * 70)
    print("  单场景BEV可视化")
    print("=" * 70)
    
    # 加载数据
    data_path = Path('output/single_scene_demo/single_scene_full_graph.json')
    if not data_path.exists():
        print(f"✗ 错误：找不到场景图数据文件: {data_path}")
        print("  请先运行 single_scene_demo.py 生成数据")
        return
    
    print(f"\n加载场景图数据: {data_path}")
    scene_graph = load_scene_graph(data_path)
    
    print(f"✓ 已加载场景: {scene_graph['scene_name']}")
    print(f"  对象数: {len(scene_graph['objects'])}")
    print(f"  关系数: {len(scene_graph['relationships'])}")
    
    # 创建输出目录
    output_dir = Path('output/single_scene_demo/visualizations')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成BEV图
    bev_path = output_dir / 'bev_with_labels.png'
    visualize_bev(scene_graph, bev_path)
    
    # 生成关系网络图
    network_path = output_dir / 'relationship_network.png'
    visualize_relationships(scene_graph, network_path)
    
    print("\n" + "=" * 70)
    print("✓ 可视化完成！")
    print(f"\n生成的文件：")
    print(f"  1. BEV图（带标注）: {bev_path}")
    print(f"  2. 关系网络图: {network_path}")
    print("\n下一步：")
    print("  1. 查看生成的图片")
    print("  2. 将场景导入Neo4j数据库")
    print("  3. 执行查询操作")
    print("=" * 70)


if __name__ == "__main__":
    main()
