import json
import sys

result_file = sys.argv[1] if len(sys.argv) > 1 else r'E:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline\output\coverage_analysis\vqa_results\enhanced_qa_test_20260128_195158.json'
data = json.load(open(result_file, 'r', encoding='utf-8'))

failed = []
for s in data['scenes']:
    scene_name = s['scene_name']
    frame_idx = s.get('frame_idx', '?')
    for idx, q in enumerate(s['results'], 1):
        if not q.get('correct'):
            q['scene_name'] = scene_name
            q['frame_idx'] = frame_idx
            q['question_idx'] = idx
            failed.append(q)

print(f"Total: {data.get('total_questions')} | Correct: {data.get('correct_count')} | Failed: {len(failed)}")
for q in failed:
    print(f"{q['scene_name']} 帧{q['frame_idx']} Q{q['question_idx']}: {q.get('expected')} vs {q.get('actual')} | {q['question'][:50]}")
