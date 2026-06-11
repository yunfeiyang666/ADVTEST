import json

with open(r'E:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline\coverage_evaluation\output\coverage_scene-0103_frame25_20260128_163820.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for i, d in enumerate(data['details'], 1):
    q = d['question']
    print(f'Q{i}: {q[:60]}...')
    cypher = d.get('cypher', 'None')
    if cypher:
        print(f'  Cypher: {cypher[:100]}...')
    print(f'  nodes: {d.get("covered_nodes", [])}')
    print(f'  edges: {d.get("covered_edges", [])}')
    print()
