import json

# 检查scene-0103 frame 38的VQA数据
with open('E:/Project/ADVTEST/nuscenes_s3c_experiment/output/vqa_neo4j/vqa_with_context.json', 'r', encoding='utf-8') as f:
    vqa_data = json.load(f)

q7_data = vqa_data['Q7']
print('Q7 scene info:')
print(f'  Scene name: {q7_data["metadata"]["scene_name"]}')
print(f'  Frame: {q7_data["metadata"]["frame_index"]}')
print(f'  Question: {q7_data["question"]}')
print(f'\nContext preview:')
print(q7_data['graph_context'][:500])
