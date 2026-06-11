#!/usr/bin/env python
"""汇总所有official_qa问题，准备完整评估"""
import json
import glob
from pathlib import Path

# 查找所有official_qa文件
qa_files = glob.glob("output/coverage_analysis/vqa_results/*_official_qa.json")

all_questions = {}
question_id = 1

for qa_file in sorted(qa_files):
    print(f"Processing: {qa_file}")
    
    with open(qa_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    scene_name = data.get('scene_name', 'unknown')
    frame_idx = data.get('frame_idx', 0)
    
    for result in data.get('results', []):
        question = result['question']
        expected = result['expected_answer']
        qtype = result.get('question_type', 'unknown')
        
        all_questions[f"Q{question_id}"] = {
            'question': question,
            'ground_truth': expected,
            'metadata': {
                'scene_name': scene_name,
                'frame_index': frame_idx,
                'question_type': qtype
            }
        }
        question_id += 1

# 保存汇总结果
output_path = "output/vqa_questions_all_official.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(all_questions, f, indent=2, ensure_ascii=False)

print(f"\n✓ Total questions collected: {len(all_questions)}")
print(f"✓ Saved to: {output_path}")

# 统计
scenes = {}
for qid, q in all_questions.items():
    scene = q['metadata']['scene_name']
    scenes[scene] = scenes.get(scene, 0) + 1

print("\nQuestions per scene:")
for scene, count in sorted(scenes.items()):
    print(f"  {scene}: {count}")
