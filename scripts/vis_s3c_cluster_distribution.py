#!/usr/bin/env python3
"""
S3C风格的聚类分布可视化
基于官方仓库的 carla/cluster_figure_generator.py 改编
"""

import json
import matplotlib.pyplot as plt
from collections import Counter
import argparse
import os

def generate_s3c_signature(scene):
    """
    生成场景的S3C签名（用于聚类）
    """
    signature = []
    
    for node in scene['nodes']:
        if node['id'] == 'ego':
            continue
            
        bins = node.get('bins', {})
        s3c_angular = bins.get('s3c_angular', 'unknown')
        s3c_distance = bins.get('s3c_distance', 'unknown')
        
        # 提取类别前缀
        cat = node.get('category_name', 'unknown')
        if '.' in cat:
            cat = cat.split('.')[0]
        
        # 签名格式：类别-角度-距离
        signature.append(f"{cat}-{s3c_angular}-{s3c_distance}")
    
    # 排序以确保相同对象集合生成相同签名
    return tuple(sorted(signature))


def visualize_cluster_distribution(scene_graph_jsonl, output_dir):
    """
    可视化场景图的S3C聚类分布
    """
    print(f"Loading scene graphs from {scene_graph_jsonl}...")
    
    # 1. 加载场景图并聚类
    clusters = Counter()
    total_scenes = 0
    
    with open(scene_graph_jsonl, 'r', encoding='utf-8') as f:
        for line in f:
            scene = json.loads(line)
            signature = generate_s3c_signature(scene)
            clusters[signature] += 1
            total_scenes += 1
    
    print(f"Total scenes: {total_scenes}")
    print(f"Total clusters: {len(clusters)}")
    
    # 2. 排序：按聚类大小降序
    sorted_clusters = sorted(clusters.items(), key=lambda x: x[1], reverse=True)
    sizes = [size for _, size in sorted_clusters]
    
    # 3. 计算累积值
    cumulative = []
    total = 0
    for size in sizes:
        total += size
        cumulative.append(total)
    
    # 4. 统计信息
    print(f"\nCluster Statistics:")
    print(f"  Largest cluster: {sizes[0]} images ({100*sizes[0]/total_scenes:.1f}%)")
    print(f"  Top 10 clusters: {sum(sizes[:10])} images ({100*sum(sizes[:10])/total_scenes:.1f}%)")
    
    # 找到singleton分界线
    singleton_index = -1
    for i, size in enumerate(sizes):
        if size == 1:
            singleton_index = i
            break
    
    if singleton_index > 0:
        print(f"  Non-singleton clusters: {singleton_index} ({100*singleton_index/len(sizes):.1f}%)")
        print(f"  Singleton clusters: {len(sizes)-singleton_index} ({100*(len(sizes)-singleton_index)/len(sizes):.1f}%)")
    
    # 5. 双Y轴可视化
    fig, ax1 = plt.subplots(figsize=(12, 6))
    ax2 = ax1.twinx()
    
    # 左轴：每个聚类的大小
    color = 'tab:blue'
    scatter = ax1.scatter(range(len(sizes)), sizes, color=color, alpha=0.6, s=20,
                          label='Images in Class (left)')
    ax1.set_xlabel('Equivalence Class ID', fontsize=12)
    ax1.set_ylabel('Number of Images in Class', color=color, fontsize=12)
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.set_ylim(bottom=0)
    
    # 右轴：累积覆盖
    color = 'tab:red'
    line, = ax2.plot(range(len(cumulative)), cumulative, color=color, linewidth=2,
                     label='Cumulative Images Covered (right)')
    ax2.set_ylabel('Cumulative Images Covered', color=color, fontsize=12)
    ax2.tick_params(axis='y', labelcolor=color)
    ax2.set_ylim(bottom=0)
    
    # 标注关键点
    if singleton_index > 0:
        ax2.hlines(cumulative[singleton_index-1], singleton_index-1, len(sizes), 
                   colors='k', linestyles='--', alpha=0.5)
        ax2.text(singleton_index + len(sizes)*0.02, cumulative[singleton_index-1] + total_scenes*0.02,
                 f'Remaining {len(sizes)-singleton_index} Images in Singleton Classes\n'
                 f'({100*(total_scenes-cumulative[singleton_index-1])/total_scenes:.1f}% of Images)',
                 fontsize=10)
    
    # 图例
    lines = [scatter, line]
    ax1.legend(lines, [line.get_label() for line in lines], loc='upper right')
    
    # 标题
    fig.suptitle('S3C Cluster Distribution (NuScenes Scene Graphs)', 
                 fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    
    # 保存
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 's3c_cluster_distribution.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nSaved to {output_path}")
    
    plt.close()
    
    return len(clusters), sizes


def main():
    parser = argparse.ArgumentParser(description='S3C Cluster Distribution Visualizer')
    parser.add_argument('--jsonl', type=str, required=True,
                        help='Path to scene graph JSONL file')
    parser.add_argument('--out_dir', type=str, default='./output',
                        help='Output directory for figures')
    args = parser.parse_args()
    
    visualize_cluster_distribution(args.jsonl, args.out_dir)


if __name__ == '__main__':
    main()
