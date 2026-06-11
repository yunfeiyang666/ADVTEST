#!/usr/bin/env python
"""测试修复后的覆盖率pipeline"""
import sys
sys.path.insert(0, 'E:\\Project\\ADVTEST\\nuscenes_s3c_experiment')

from core_pipeline.coverage_evaluation.coverage_pipeline import CoveragePipeline

# 测试 scene-0553 frame8
sg_path = 'output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json'
q_path = 'output/coverage_analysis/vqa_results/scene-0553_frame8_official_qa.json'
out_dir = 'output/coverage_verification'

print("开始测试 scene-0553 frame8...")
pipeline = CoveragePipeline(sg_path, q_path, out_dir)
result = pipeline.run()

print("\n" + "="*70)
print("测试完成！")
print("="*70)
