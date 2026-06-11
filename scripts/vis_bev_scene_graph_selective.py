#!/usr/bin/env python3

import json
import argparse
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import os

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jsonl', type=str, required=True)
    parser.add_argument('--out_dir', type=str, required=True)
    parser.add_argument('--max_frames', type=int, default=10)
    parser.add_argument('--range_x', type=float, default=80.0)
    parser.add_argument('--range_y', type=float, default=80.0)
    parser.add_argument('--show_velocity', action='store_true')
    parser.add_argument('--edge_filter', type=str, default='important', 
                       choices=['all', 'important', 'close', 'ego_only'],
                       help='Edge filtering strategy')
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    with open(args.jsonl, 'r', encoding='utf-8') as f:
        for frame_idx, line in enumerate(f):
            if frame_idx >= args.max_frames:
                break
            
            frame = json.loads(line)
            sample_token = frame['sample_token']
            
            fig, ax = plt.subplots(figsize=(12, 12))
            ax.set_xlim(-args.range_x/2, args.range_x/2)
            ax.set_ylim(-args.range_y/2, args.range_y/2)
            ax.set_xlabel('x (forward, m)')
            ax.set_ylabel('y (left, m)')
            ax.grid(True, alpha=0.3)
            ax.set_aspect('equal')
            
            # 定义颜色映射
            color_map = {
                'vehicle': 'red',
                'human': 'blue', 
                'animal': 'green',
                'movable_object': 'purple',
                'static_object': 'orange',
                'flat': 'brown',
                'vehicle.ego': 'darkblue'
            }
            
            # 绘制边（选择性显示）
            edges_to_draw = []
            
            if args.edge_filter == 'all':
                edges_to_draw = frame['edges']
            elif args.edge_filter == 'ego_only':
                # 只显示与ego相关的边
                edges_to_draw = [e for e in frame['edges'] if 'ego' in [e['from'], e['to']]]
            elif args.edge_filter == 'close':
                # 只显示近距离边（< 15m）
                edges_to_draw = [e for e in frame['edges'] if e['distance'] < 15.0]
            elif args.edge_filter == 'important':
                # 显示重要边：近距离 OR 与ego相关 OR 高TTC风险
                edges_to_draw = []
                for e in frame['edges']:
                    is_important = False
                    
                    # 与ego相关
                    if 'ego' in [e['from'], e['to']]:
                        is_important = True
                    
                    # 近距离（< 20m）
                    elif e['distance'] < 20.0:
                        is_important = True
                    
                    # 高TTC风险（< 5秒）
                    elif e.get('ttc') and e['ttc'] < 5.0:
                        is_important = True
                    
                    if is_important:
                        edges_to_draw.append(e)
            
            # 创建节点位置映射
            node_positions = {}
            for node in frame['nodes']:
                pos = node['pose']['ego']['center']
                node_positions[node['id']] = (pos[0], pos[1])
            
            # 绘制选中的边
            for edge in edges_to_draw:
                from_pos = node_positions.get(edge['from'])
                to_pos = node_positions.get(edge['to'])
                
                if from_pos and to_pos:
                    # 根据边的类型选择颜色和样式
                    if 'ego' in [edge['from'], edge['to']]:
                        color = 'red'
                        alpha = 0.8
                        linewidth = 2
                    elif edge['distance'] < 10.0:
                        color = 'orange'
                        alpha = 0.6
                        linewidth = 1.5
                    elif edge.get('ttc') and edge['ttc'] < 5.0:
                        color = 'purple'
                        alpha = 0.7
                        linewidth = 1.5
                    else:
                        color = 'gray'
                        alpha = 0.3
                        linewidth = 0.5
                    
                    ax.plot([from_pos[0], to_pos[0]], [from_pos[1], to_pos[1]], 
                           color=color, alpha=alpha, linewidth=linewidth)
            
            # 绘制节点
            for node in frame['nodes']:
                pos = node['pose']['ego']['center']
                x, y = pos[0], pos[1]
                
                # 确定节点类型和颜色
                category = node['category_name']
                main_cat = category.split('.')[0] if '.' in category else category
                color = color_map.get(main_cat, 'gray')
                
                if node['id'] == 'ego':
                    # Ego车辆 - 特殊显示
                    rect = patches.Rectangle((x-2, y-1), 4, 2, 
                                           linewidth=3, edgecolor='darkblue', 
                                           facecolor='lightblue', alpha=0.8)
                    ax.add_patch(rect)
                    ax.text(x, y, 'EGO', ha='center', va='center', 
                           fontweight='bold', fontsize=10)
                
                elif 'vehicle' in category:
                    # 车辆 - 矩形
                    size = node.get('size', {}).get('wlh', [4, 2, 1.5])
                    rect = patches.Rectangle((x-size[0]/2, y-size[1]/2), 
                                           size[0], size[1],
                                           linewidth=2, edgecolor=color, 
                                           facecolor=color, alpha=0.6)
                    ax.add_patch(rect)
                
                elif 'human' in category:
                    # 行人 - 圆点
                    circle = patches.Circle((x, y), 0.5, 
                                          linewidth=2, edgecolor=color,
                                          facecolor=color, alpha=0.7)
                    ax.add_patch(circle)
                
                else:
                    # 其他对象 - 小方块
                    rect = patches.Rectangle((x-0.5, y-0.5), 1, 1,
                                           linewidth=1, edgecolor=color,
                                           facecolor=color, alpha=0.5)
                    ax.add_patch(rect)
                
                # 显示速度向量（可选）
                if args.show_velocity and node['id'] != 'ego':
                    vel = node['velocity']['ego']
                    if abs(vel[0]) > 0.1 or abs(vel[1]) > 0.1:
                        ax.arrow(x, y, vel[0]*2, vel[1]*2, 
                               head_width=1, head_length=1, 
                               fc='black', ec='black', alpha=0.7)
            
            # 添加图例
            legend_elements = []
            for cat, color in color_map.items():
                legend_elements.append(plt.Line2D([0], [0], marker='s', color='w', 
                                                markerfacecolor=color, markersize=10, 
                                                label=cat))
            ax.legend(handles=legend_elements, loc='upper right')
            
            # 添加统计信息
            stats_text = f"Nodes: {len(frame['nodes'])}\n"
            stats_text += f"Edges (shown): {len(edges_to_draw)}/{len(frame['edges'])}\n"
            stats_text += f"Filter: {args.edge_filter}"
            ax.text(-args.range_x/2 + 2, args.range_y/2 - 5, stats_text, 
                   fontsize=10, bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
            
            plt.title(f'sample: {sample_token[:32]} t: {frame["timestamp"]}', fontsize=12)
            
            # 保存图像
            filename = f"{frame_idx:06d}_{sample_token}.png"
            filepath = os.path.join(args.out_dir, filename)
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close()
            
            print(f"Processed frame {frame_idx+1}/{args.max_frames}: {len(edges_to_draw)}/{len(frame['edges'])} edges shown")
    
    print(f"Saved selective BEV images to {args.out_dir}")


if __name__ == '__main__':
    main()
