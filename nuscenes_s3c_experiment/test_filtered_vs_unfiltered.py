#!/usr/bin/env python
"""
对比测试：筛选 vs 未筛选
测试 nuScenes 官方标准筛选对覆盖率的影响
"""
import sys
sys.path.insert(0, 'E:\\Project\\ADVTEST\\nuscenes_s3c_experiment')

from core_pipeline.coverage_evaluation.coverage_pipeline import CoveragePipeline
from core_pipeline.coverage_evaluation.scene_filter import SceneGraphFilter
from pathlib import Path
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def run_comparison_test(scene_name: str, sg_path: str, q_path: str, output_dir: str):
    """
    对单个场景运行对比测试
    
    Args:
        scene_name: 场景名称
        sg_path: 原始场景图路径
        q_path: 问题文件路径
        output_dir: 输出目录
    """
    logger.info("="*80)
    logger.info(f"对比测试: {scene_name}")
    logger.info("="*80)
    
    # 加载原始场景图
    with open(sg_path, 'r', encoding='utf-8') as f:
        original_sg = json.load(f)
    
    results = {}
    
    # 测试1: 未筛选模式
    logger.info(f"\n{'='*80}")
    logger.info("模式1: 未筛选（保留所有对象）")
    logger.info("="*80)
    
    unfiltered_dir = Path(output_dir) / 'unfiltered'
    unfiltered_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存未筛选的场景图
    unfiltered_sg_path = unfiltered_dir / f"{scene_name}_unfiltered.json"
    with open(unfiltered_sg_path, 'w', encoding='utf-8') as f:
        json.dump(original_sg, f, indent=2, ensure_ascii=False)
    
    # 运行覆盖率测试
    pipeline_unfiltered = CoveragePipeline(
        str(unfiltered_sg_path),
        q_path,
        str(unfiltered_dir)
    )
    result_unfiltered = pipeline_unfiltered.run()
    results['unfiltered'] = result_unfiltered
    
    # 测试2: 筛选模式
    logger.info(f"\n{'='*80}")
    logger.info("模式2: 筛选（nuScenes + nuImages 标准）")
    logger.info("="*80)
    
    filtered_dir = Path(output_dir) / 'filtered'
    filtered_dir.mkdir(parents=True, exist_ok=True)
    
    # 应用筛选
    filter_obj = SceneGraphFilter(mode='filtered')
    filtered_sg = filter_obj.filter_scene_graph(original_sg)
    
    # 保存筛选后的场景图
    filtered_sg_path = filtered_dir / f"{scene_name}_filtered.json"
    with open(filtered_sg_path, 'w', encoding='utf-8') as f:
        json.dump(filtered_sg, f, indent=2, ensure_ascii=False)
    
    # 获取筛选统计
    filter_stats = filter_obj.get_filter_stats(original_sg, filtered_sg)
    
    # 运行覆盖率测试
    pipeline_filtered = CoveragePipeline(
        str(filtered_sg_path),
        q_path,
        str(filtered_dir)
    )
    result_filtered = pipeline_filtered.run()
    results['filtered'] = result_filtered
    results['filter_stats'] = filter_stats
    
    return results


def print_comparison(scene_name: str, results: dict):
    """打印对比结果"""
    print("\n" + "="*80)
    print(f"对比报告: {scene_name}")
    print("="*80)
    
    unf = results['unfiltered']
    filt = results['filtered']
    stats = results['filter_stats']
    
    print(f"\n{'指标':<20} {'未筛选':<25} {'筛选后':<25} {'变化':<15}")
    print("-"*85)
    
    # 场景规模
    print(f"{'场景节点数':<20} {unf['totals']['nodes']:<25} "
          f"{filt['totals']['nodes']:<25} "
          f"{stats['removed']['node_ratio']*-100:>+6.1f}%")
    
    print(f"{'场景边数':<20} {unf['totals']['edges']:<25} "
          f"{filt['totals']['edges']:<25} "
          f"{stats['removed']['edge_ratio']*-100:>+6.1f}%")
    
    print(f"{'二跳路径数':<20} {unf['totals']['2hop']:<25} "
          f"{filt['totals']['2hop']:<25} "
          f"{(filt['totals']['2hop']-unf['totals']['2hop'])/max(unf['totals']['2hop'],1)*100:>+6.1f}%")
    
    # 题目成功率
    unf_success = unf['questions']['analyzed']
    unf_total = unf['questions']['total']
    filt_success = filt['questions']['analyzed']
    filt_total = filt['questions']['total']
    
    print(f"\n{'题目成功率':<20} {unf_success}/{unf_total} ({unf_success/max(unf_total,1)*100:.1f}%)"
          f"{'':<10} {filt_success}/{filt_total} ({filt_success/max(filt_total,1)*100:.1f}%)"
          f"{'':<10} {(filt_success-unf_success):>+3}")
    
    # 覆盖率对比
    print(f"\n{'覆盖率指标':<20} {'未筛选':<25} {'筛选后':<25} {'变化':<15}")
    print("-"*85)
    
    # L0
    unf_l0 = unf['coverage']['L0']
    filt_l0 = filt['coverage']['L0']
    print(f"{'L0 (节点)':<20} "
          f"{unf_l0['covered']}/{unf_l0['total']} ({unf_l0['rate']*100:.2f}%)"
          f"{'':<8} "
          f"{filt_l0['covered']}/{filt_l0['total']} ({filt_l0['rate']*100:.2f}%)"
          f"{'':<8} "
          f"{(filt_l0['rate']-unf_l0['rate'])*100:>+6.2f}%")
    
    # L1
    unf_l1 = unf['coverage']['L1']
    filt_l1 = filt['coverage']['L1']
    print(f"{'L1 (边)':<20} "
          f"{unf_l1['covered']}/{unf_l1['total']} ({unf_l1['rate']*100:.2f}%)"
          f"{'':<8} "
          f"{filt_l1['covered']}/{filt_l1['total']} ({filt_l1['rate']*100:.2f}%)"
          f"{'':<8} "
          f"{(filt_l1['rate']-unf_l1['rate'])*100:>+6.2f}%")
    
    # L2
    unf_l2 = unf['coverage']['L2']
    filt_l2 = filt['coverage']['L2']
    print(f"{'L2 (二跳)':<20} "
          f"{unf_l2['covered']}/{unf_l2['total']} ({unf_l2['rate']*100:.4f}%)"
          f"{'':<5} "
          f"{filt_l2['covered']}/{filt_l2['total']} ({filt_l2['rate']*100:.4f}%)"
          f"{'':<5} "
          f"{(filt_l2['rate']-unf_l2['rate'])*100:>+6.4f}%")
    
    print("\n" + "="*80)


def main():
    """主函数"""
    # 测试场景配置
    test_scenes = [
        {
            'name': 'scene-0553_frame8',
            'sg_path': 'output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json',
            'q_path': 'output/coverage_analysis/vqa_results/scene-0553_frame8_official_qa.json'
        }
    ]
    
    output_base = 'output/coverage_comparison'
    
    print("="*80)
    print("筛选 vs 未筛选 对比测试")
    print("="*80)
    print(f"\n筛选标准:")
    print(f"  1. nuScenes 距离: barrier/cone≤30m, bicycle/motorcycle/pedestrian≤40m, car/bus/truck≤50m")
    print(f"  2. nuScenes 可见度: ≥40%")
    print(f"  3. nuImages 像素: ≥10 pixels (宽度)")
    
    all_results = []
    
    for scene in test_scenes:
        output_dir = Path(output_base) / scene['name']
        results = run_comparison_test(
            scene['name'],
            scene['sg_path'],
            scene['q_path'],
            str(output_dir)
        )
        all_results.append({
            'scene': scene['name'],
            'results': results
        })
        
        # 打印对比报告
        print_comparison(scene['name'], results)
    
    # 保存汇总结果
    summary_path = Path(output_base) / 'comparison_summary.json'
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 对比测试完成！")
    print(f"详细结果保存在: {output_base}/")
    print(f"汇总报告: {summary_path}")


if __name__ == '__main__':
    main()
