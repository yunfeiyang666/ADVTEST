"""
批量测试所有场景的覆盖率
"""
import json
import os
from calculate_coverage import calculate_coverage_offline


def test_all_scene_coverage():
    """测试所有6个场景的覆盖率"""
    
    print("=" * 70)
    print("  批量测试场景覆盖率")
    print("=" * 70)
    
    # 加载场景清单
    manifest_path = "output/coverage_analysis/scene_graphs/manifest.json"
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    print(f"\n加载了 {len(manifest)} 个场景")
    
    all_results = []
    
    for scene_info in manifest:
        scene_name = scene_info['scene_name']
        frame_idx = scene_info['frame_idx']
        scene_id = f"{scene_name}_frame{frame_idx}"
        
        print(f"\n" + "=" * 70)
        print(f"  测试场景: {scene_id}")
        print("=" * 70)
        
        # 文件路径
        scene_graph_file = f"output/coverage_analysis/scene_graphs/{scene_id}_scene_graph.json"
        vqa_result_file = f"output/coverage_analysis/vqa_results/{scene_id}_official_qa.json"
        
        # 检查文件是否存在
        if not os.path.exists(scene_graph_file):
            print(f"  ⚠️  场景图文件不存在: {scene_graph_file}")
            continue
        
        if not os.path.exists(vqa_result_file):
            print(f"  ⚠️  VQA结果文件不存在: {vqa_result_file}")
            continue
        
        # 加载场景图信息
        with open(scene_graph_file, 'r', encoding='utf-8') as f:
            scene_graph = json.load(f)
        
        print(f"  场景描述: {scene_graph.get('description', 'N/A')}")
        print(f"  节点数: {len(scene_graph.get('nodes', []))}")
        print(f"  边数: {len(scene_graph.get('edges', []))}")
        
        # 加载问题
        with open(vqa_result_file, 'r', encoding='utf-8') as f:
            vqa_data = json.load(f)
            questions = vqa_data.get('results', [])
        
        # 计算覆盖率
        try:
            covered_edges, total_edges, coverage_rate = calculate_coverage_offline(questions, scene_graph_file)
            
            print(f"\n  📊 覆盖率统计:")
            print(f"    问题数: {len(questions)}")
            print(f"    总边数: {total_edges}")
            print(f"    覆盖边数: {covered_edges}")
            print(f"    覆盖率: {coverage_rate}%")
            
            # 保存结果
            all_results.append({
                'scene_id': scene_id,
                'scene_name': scene_name,
                'frame_idx': frame_idx,
                'description': scene_graph.get('description', 'N/A'),
                'nodes': len(scene_graph.get('nodes', [])),
                'edges': total_edges,
                'questions': len(questions),
                'covered_edges': covered_edges,
                'coverage_rate': coverage_rate
            })
            
        except Exception as e:
            print(f"  ❌ 计算失败: {e}")
            continue
    
    # 生成汇总报告
    print("\n\n" + "=" * 70)
    print("  所有场景覆盖率汇总")
    print("=" * 70)
    
    if not all_results:
        print("没有成功计算的场景")
        return
    
    # 按覆盖率排序
    all_results_sorted = sorted(all_results, key=lambda x: x['coverage_rate'], reverse=True)
    
    print(f"\n共测试 {len(all_results)} 个场景\n")
    
    # 表格输出
    print(f"{'场景ID':<25} {'节点':<6} {'边数':<8} {'问题':<6} {'覆盖边':<8} {'覆盖率':<8}")
    print("-" * 70)
    
    for result in all_results_sorted:
        print(f"{result['scene_id']:<25} "
              f"{result['nodes']:<6} "
              f"{result['edges']:<8} "
              f"{result['questions']:<6} "
              f"{result['covered_edges']:<8} "
              f"{result['coverage_rate']:.1f}%")
    
    # 统计分析
    total_edges = sum(r['edges'] for r in all_results)
    total_covered = sum(r['covered_edges'] for r in all_results)
    avg_coverage = sum(r['coverage_rate'] for r in all_results) / len(all_results)
    
    print("-" * 70)
    print(f"{'总计':<25} "
          f"{sum(r['nodes'] for r in all_results):<6} "
          f"{total_edges:<8} "
          f"{sum(r['questions'] for r in all_results):<6} "
          f"{total_covered:<8} "
          f"{(total_covered/total_edges*100):.1f}%")
    
    print(f"\n📊 统计分析:")
    print(f"  平均覆盖率: {avg_coverage:.1f}%")
    print(f"  最高覆盖率: {all_results_sorted[0]['coverage_rate']:.1f}% ({all_results_sorted[0]['scene_id']})")
    print(f"  最低覆盖率: {all_results_sorted[-1]['coverage_rate']:.1f}% ({all_results_sorted[-1]['scene_id']})")
    print(f"  总边数: {total_edges}")
    print(f"  总覆盖边数: {total_covered}")
    print(f"  总体覆盖率: {(total_covered/total_edges*100):.1f}%")
    
    # 保存结果
    output_file = "output/coverage_analysis/vqa_results/all_scenes_coverage.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_scenes': len(all_results),
            'total_edges': total_edges,
            'total_covered_edges': total_covered,
            'overall_coverage_rate': round(total_covered/total_edges*100, 2),
            'average_coverage_rate': round(avg_coverage, 2),
            'scenes': all_results_sorted
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ 结果已保存: {output_file}")
    
    print("\n" + "=" * 70)
    print("  测试完成")
    print("=" * 70)
    
    return all_results


if __name__ == '__main__':
    test_all_scene_coverage()
