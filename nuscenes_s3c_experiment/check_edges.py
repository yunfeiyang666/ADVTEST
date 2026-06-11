import json

with open(r'E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json', 'r', encoding='utf-8') as f:
    sg = json.load(f)

print("=== ego -> pedestrian edges ===")
for e in sg['edges']:
    if e['source'] == 'ego' and 'pedestrian' in e['target']:
        print(f"{e['target']}: angle={e['metrics']['angle']}, dir8={e['direction_8']}, predicates={e['predicates']}")

print("\n=== truck1 -> pedestrian edges ===")
for e in sg['edges']:
    if e['source'] == 'truck1' and 'pedestrian' in e['target']:
        print(f"{e['target']}: angle={e['metrics']['angle']}, dir8={e['direction_8']}, predicates={e['predicates']}")
