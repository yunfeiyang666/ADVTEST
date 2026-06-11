"""
可视化工具
"""
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from config import COLORS, FIGURE_DPI, FIGURE_SIZE_SINGLE, FIGURE_SIZE_DOUBLE


def plot_cluster_distribution(cluster_sizes, output_path, title="Cluster Distribution"):
    """
    绘制聚类分布图（仿S3C论文Figure 3）
    
    Args:
        cluster_sizes: 聚类大小列表
        output_path: 输出路径
        title: 图表标题
    """
    # 按大小降序排列
    cluster_sizes_sorted = sorted(cluster_sizes, reverse=True)
    
    # 计算累积覆盖
    cumulative_coverage = np.cumsum(cluster_sizes_sorted)
    total_scenes = sum(cluster_sizes)
    
    # 创建双Y轴图
    fig, ax1 = plt.subplots(figsize=FIGURE_SIZE_DOUBLE)
    
    # 左Y轴：聚类大小（散点图）
    color = COLORS['primary']
    ax1.set_xlabel('Equivalence Class (sorted by size)', fontsize=12)
    ax1.set_ylabel('Cluster Size', color=color, fontsize=12)
    ax1.scatter(range(len(cluster_sizes_sorted)), cluster_sizes_sorted,
                alpha=0.6, s=30, color=color)
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.set_yscale('log')  # 对数坐标
    ax1.grid(True, alpha=0.3)
    
    # 右Y轴：累积覆盖（曲线图）
    ax2 = ax1.twinx()
    color = COLORS['secondary']
    ax2.set_ylabel('Cumulative Scenarios Covered', color=color, fontsize=12)
    ax2.plot(range(len(cumulative_coverage)), cumulative_coverage,
             color=color, linewidth=2)
    ax2.tick_params(axis='y', labelcolor=color)
    
    # 标注关键信息
    singleton_count = sum(1 for size in cluster_sizes if size == 1)
    singleton_rate = singleton_count / len(cluster_sizes) * 100
    
    ax1.text(0.65, 0.85, 
             f'Total clusters: {len(cluster_sizes)}\n'
             f'Singleton clusters: {singleton_count} ({singleton_rate:.1f}%)\n'
             f'Total scenes: {total_scenes}',
             transform=ax1.transAxes, fontsize=10,
             bbox=dict(boxstyle="round,pad=0.5", facecolor="yellow", alpha=0.7))
    
    plt.title(title, fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path, dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    
    print(f"✓ 聚类分布图已保存: {output_path}")


def plot_dataset_comparison(nuscenes_stats, carla_stats, output_path):
    """
    绘制数据集对比图
    
    Args:
        nuscenes_stats: NuScenes统计数据
        carla_stats: CARLA统计数据
        output_path: 输出路径
    """
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    datasets = ['CARLA\n(S3C Paper)', 'NuScenes\n(Our Experiment)']
    
    # 1. 单例聚类率对比
    singleton_rates = [carla_stats['singleton_rate'], nuscenes_stats['singleton_rate']]
    axes[0].bar(datasets, singleton_rates, color=[COLORS['primary'], COLORS['secondary']])
    axes[0].set_ylabel('Singleton Rate (%)', fontsize=12)
    axes[0].set_title('Singleton Cluster Rate', fontsize=12, fontweight='bold')
    axes[0].set_ylim(0, 100)
    for i, v in enumerate(singleton_rates):
        axes[0].text(i, v + 2, f'{v:.1f}%', ha='center', fontsize=10)
    
    # 2. 覆盖率对比
    coverage_rates = [carla_stats['coverage_rate'], nuscenes_stats['coverage_rate']]
    axes[1].bar(datasets, coverage_rates, color=[COLORS['primary'], COLORS['secondary']])
    axes[1].set_ylabel('Coverage Rate (%)', fontsize=12)
    axes[1].set_title('Scene Diversity (Clusters/Scenes)', fontsize=12, fontweight='bold')
    axes[1].set_ylim(0, 100)
    for i, v in enumerate(coverage_rates):
        axes[1].text(i, v + 2, f'{v:.1f}%', ha='center', fontsize=10)
    
    # 3. 最大聚类占比对比
    max_cluster_rates = [carla_stats['max_cluster_rate'], nuscenes_stats['max_cluster_rate']]
    axes[2].bar(datasets, max_cluster_rates, color=[COLORS['primary'], COLORS['secondary']])
    axes[2].set_ylabel('Max Cluster Rate (%)', fontsize=12)
    axes[2].set_title('Largest Cluster Size', fontsize=12, fontweight='bold')
    axes[2].set_ylim(0, 30)
    for i, v in enumerate(max_cluster_rates):
        axes[2].text(i, v + 0.5, f'{v:.1f}%', ha='center', fontsize=10)
    
    plt.suptitle('Dataset Comparison: CARLA vs NuScenes', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(output_path, dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    
    print(f"✓ 数据集对比图已保存: {output_path}")


def plot_predicate_heatmap(predicate_matrix, predicate_names, output_path):
    """
    绘制谓词共现热力图
    
    Args:
        predicate_matrix: 谓词共现矩阵
        predicate_names: 谓词名称列表
        output_path: 输出路径
    """
    plt.figure(figsize=(10, 8))
    sns.heatmap(predicate_matrix, annot=True, fmt='d',
                xticklabels=predicate_names,
                yticklabels=predicate_names,
                cmap='YlOrRd', cbar_kws={'label': 'Co-occurrence Count'})
    
    plt.title('Predicate Co-occurrence Heatmap', fontsize=14, fontweight='bold')
    plt.xlabel('Predicate', fontsize=12)
    plt.ylabel('Predicate', fontsize=12)
    plt.tight_layout()
    plt.savefig(output_path, dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    
    print(f"✓ 谓词热力图已保存: {output_path}")


def plot_cluster_size_histogram(cluster_sizes, output_path):
    """
    绘制聚类大小直方图
    
    Args:
        cluster_sizes: 聚类大小列表
        output_path: 输出路径
    """
    plt.figure(figsize=FIGURE_SIZE_SINGLE)
    
    plt.hist(cluster_sizes, bins=50, color=COLORS['primary'], alpha=0.7, edgecolor='black')
    plt.xlabel('Cluster Size', fontsize=12)
    plt.ylabel('Frequency', fontsize=12)
    plt.title('Cluster Size Distribution', fontsize=14, fontweight='bold')
    plt.yscale('log')
    plt.grid(True, alpha=0.3)
    
    # 添加统计信息
    mean_size = np.mean(cluster_sizes)
    median_size = np.median(cluster_sizes)
    plt.axvline(mean_size, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean_size:.2f}')
    plt.axvline(median_size, color='green', linestyle='--', linewidth=2, label=f'Median: {median_size:.2f}')
    plt.legend()
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    
    print(f"✓ 聚类大小直方图已保存: {output_path}")
