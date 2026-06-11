#!/usr/bin/env python3
"""
S3C空间分档概念图可视化
展示S3C如何将空间划分为bins
"""

import matplotlib.pyplot as plt
import numpy as np
import argparse
import os

def visualize_s3c_spatial_bins(output_dir, style='polar'):
    """
    可视化S3C的空间分档定义
    
    Args:
        output_dir: 输出目录
        style: 'polar' 或 'cartesian'
    """
    os.makedirs(output_dir, exist_ok=True)
    
    if style == 'polar':
        visualize_polar(output_dir)
    else:
        visualize_cartesian(output_dir)


def visualize_polar(output_dir):
    """
    极坐标图：展示S3C的空间分档
    """
    fig = plt.figure(figsize=(14, 14))
    ax = fig.add_subplot(111, projection='polar')
    
    # S3C的4象限（每个90度）
    sectors = {
        'Direct\nFront': (315, 45),
        'Side\nFront': (45, 135),
        'Direct\nRear': (135, 225),
        'Side\nRear': (225, 315)
    }
    
    # S3C官方的5档距离（单位：米）
    distances = {
        'near_coll': (0, 4, '#d62728'),       # 红色：危险
        'super_near': (4, 7, '#ff7f0e'),      # 橙色
        'very_near': (7, 10, '#ffdd57'),      # 黄色
        'near': (10, 16, '#2ca02c'),          # 绿色
        'visible': (16, 25, '#1f77b4'),       # 蓝色
    }
    
    # 绘制距离环
    for label, (r_min, r_max, color) in distances.items():
        theta = np.linspace(0, 2*np.pi, 100)
        r_outer = np.full_like(theta, r_max)
        r_inner = np.full_like(theta, r_min)
        
        # 填充环形区域
        ax.fill_between(theta, r_inner, r_outer, alpha=0.3, color=color, 
                        label=f'{label}: {r_min}-{r_max}m')
        # 外圈边界
        ax.plot(theta, r_outer, color=color, linewidth=2)
    
    # 绘制扇区分界线
    sector_angles = [315, 45, 135, 225, 315]  # 度
    for angle_deg in sector_angles:
        angle_rad = np.deg2rad(angle_deg)
        ax.plot([angle_rad, angle_rad], [0, 30], 'k-', alpha=0.5, linewidth=2)
    
    # 标注扇区名称
    for label, (start, end) in sectors.items():
        # 计算中心角度
        if start > end:  # Direct Front跨越0度
            mid = ((start + 360 + end) / 2) % 360
        else:
            mid = (start + end) / 2
        
        angle_rad = np.deg2rad(mid)
        ax.text(angle_rad, 32, label, ha='center', va='center', 
                fontsize=14, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.8))
    
    # 设置极坐标
    ax.set_theta_zero_location('N')  # 0度在上方（前方）
    ax.set_theta_direction(-1)       # 顺时针
    ax.set_ylim(0, 35)
    ax.set_rlabel_position(180)      # 径向标签位置
    
    # 标题和图例
    ax.set_title('S3C Spatial Binning\n(4 Angular Sectors × 5 Distance Bins)', 
                 fontsize=16, fontweight='bold', pad=30)
    ax.legend(loc='upper left', bbox_to_anchor=(1.15, 1.0), fontsize=11)
    
    # 添加ego车标记
    ax.plot(0, 0, 'r*', markersize=20, label='Ego Vehicle')
    ax.text(0, -3, 'Ego', ha='center', va='top', fontsize=12, fontweight='bold', color='red')
    
    plt.tight_layout()
    
    # 保存
    output_path = os.path.join(output_dir, 's3c_spatial_bins_polar.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Saved polar plot to {output_path}")
    
    plt.close()


def visualize_cartesian(output_dir):
    """
    笛卡尔坐标图：BEV风格展示S3C分档
    """
    fig, ax = plt.subplots(figsize=(12, 12))
    
    # S3C的5档距离
    distances = {
        'near_coll': (0, 4, '#d62728'),
        'super_near': (4, 7, '#ff7f0e'),
        'very_near': (7, 10, '#ffdd57'),
        'near': (10, 16, '#2ca02c'),
        'visible': (16, 25, '#1f77b4'),
    }
    
    # 绘制同心圆
    for label, (r_min, r_max, color) in distances.items():
        circle_outer = plt.Circle((0, 0), r_max, fill=False, 
                                  color=color, linewidth=2, linestyle='-')
        ax.add_patch(circle_outer)
        
        # 填充环形
        theta = np.linspace(0, 2*np.pi, 100)
        x_outer = r_max * np.cos(theta)
        y_outer = r_max * np.sin(theta)
        x_inner = r_min * np.cos(theta)
        y_inner = r_min * np.sin(theta)
        ax.fill(np.concatenate([x_outer, x_inner[::-1]]),
                np.concatenate([y_outer, y_inner[::-1]]),
                color=color, alpha=0.2, label=f'{label}: {r_min}-{r_max}m')
    
    # 绘制4个扇区的分界线
    angles = [45, 135, 225, 315]  # 度
    max_r = 30
    for angle_deg in angles:
        angle_rad = np.deg2rad(angle_deg)
        x = max_r * np.cos(angle_rad)
        y = max_r * np.sin(angle_rad)
        ax.plot([0, x], [0, y], 'k--', alpha=0.5, linewidth=1.5)
    
    # 标注扇区
    sectors = [
        ('Direct Front', 0, 28),
        ('Side Front', 90, 28),
        ('Direct Rear', 180, 28),
        ('Side Rear', 270, 28)
    ]
    
    for label, angle_deg, r in sectors:
        angle_rad = np.deg2rad(angle_deg)
        x = r * np.cos(angle_rad)
        y = r * np.sin(angle_rad)
        ax.text(x, y, label, ha='center', va='center', fontsize=12, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9))
    
    # Ego车标记
    ax.plot(0, 0, 'r^', markersize=15, label='Ego Vehicle')
    ax.arrow(0, 0, 0, 3, head_width=0.8, head_length=0.5, fc='red', ec='red', linewidth=2)
    
    # 设置
    ax.set_xlim(-30, 30)
    ax.set_ylim(-30, 30)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    ax.set_xlabel('X (Forward, m)', fontsize=12)
    ax.set_ylabel('Y (Left, m)', fontsize=12)
    ax.set_title('S3C Spatial Binning (BEV View)', fontsize=14, fontweight='bold')
    ax.legend(loc='upper right', fontsize=10)
    
    plt.tight_layout()
    
    # 保存
    output_path = os.path.join(output_dir, 's3c_spatial_bins_cartesian.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Saved cartesian plot to {output_path}")
    
    plt.close()


def main():
    parser = argparse.ArgumentParser(description='S3C Spatial Bins Visualizer')
    parser.add_argument('--out_dir', type=str, default='./output',
                        help='Output directory for figures')
    parser.add_argument('--style', type=str, default='both',
                        choices=['polar', 'cartesian', 'both'],
                        help='Visualization style')
    args = parser.parse_args()
    
    if args.style in ['polar', 'both']:
        visualize_polar(args.out_dir)
    
    if args.style in ['cartesian', 'both']:
        visualize_cartesian(args.out_dir)


if __name__ == '__main__':
    main()
