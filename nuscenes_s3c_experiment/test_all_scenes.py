#!/usr/bin/env python
"""批量测试4个场景的覆盖率"""
import sys
sys.path.insert(0, 'E:\\Project\\ADVTEST\\nuscenes_s3c_experiment')

from core_pipeline.coverage_evaluation.coverage_pipeline import CoveragePipeline
from pathlib import Path
import json

# 4个测试场景
test_scenes = [
    {
        'name': 'scene-0553_frame8',
        'sg_path': 'output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json',
        'q_path': 'output/coverage_analysis/vqa_results/scene-0553_frame8_official_qa.json'
    },
    {
        'name': 'scene-0103_frame38',
        'sg_path': 'output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json',
        'q_path': 'output/coverage_analysis/vqa_results/scene-0103_frame38_official_qa.json'
    },
    {
        'name': 'scene-0916_frame8',
        'sg_path': 'output/coverage_analysis/scene_graphs/scene-0916_frame8_scene_graph.json',
        'q_path': 'output/coverage_analysis/vqa_results/scene-0916_frame8_official_qa.json'
    },
    {
        'name': 'scene-0103_frame25',
        'sg_path': 'output/coverage_analysis/scene_graphs/scene-0103_frame25_scene_graph.json',
        'q_path': 'output/coverage_analysis/vqa_results/scene-0103_frame25_official_qa.json'
    }
]

output_dir = 'output/coverage_final_fixed'
Path(output_dir).mkdir(parents=True, exist_ok=True)

print("="*80)
print("批量覆盖率测试 - 4个场景")
print("="*80)

all_results = []

for i, scene in enumerate(test_scenes, 1):
    print(f"\n{'='*80}")
    print(f"[{i}/4] 测试场景: {scene['name']}")
    print("="*80)
    
    try:
        pipeline = CoveragePipeline(
            scene['sg_path'],
            scene['q_path'],
            output_dir
        )
        result = pipeline.run()
        all_results.append({
            'scene': scene['name'],
            'result': result
        })
        print(f"✅ {scene['name']} 完成")
    except Exception as e:
        print(f"❌ {scene['name']} 失败: {e}")
        import traceback
        traceback.print_exc()

# 生成汇总报告
print("\n" + "="*80)
print("汇总报告")
print("="*80)

summary = []
for item in all_results:
    scene_name = item['scene']
    result = item['result']
    
    if result:
        summary.append({
            'scene': scene_name,
            'nodes': f"{result['coverage']['L0']['covered']}/{result['coverage']['L0']['total']} = {result['coverage']['L0']['rate']*100:.2f}%",
            'edges': f"{result['coverage']['L1']['covered']}/{result['coverage']['L1']['total']} = {result['coverage']['L1']['rate']*100:.2f}%",
            '2hop': f"{result['coverage']['L2']['covered']}/{result['coverage']['L2']['total']} = {result['coverage']['L2']['rate']*100:.5f}%",
            'questions': f"{result['questions']['analyzed']}/{result['questions']['total']}"
        })

# 打印表格
print(f"\n{'场景':<25} {'L0 节点':<20} {'L1 边':<20} {'L2 二跳':<25} {'题目':<10}")
print("-"*110)
for s in summary:
    print(f"{s['scene']:<25} {s['nodes']:<20} {s['edges']:<20} {s['2hop']:<25} {s['questions']:<10}")

print("\n✅ 所有测试完成！")
print(f"详细结果保存在: {output_dir}/")
