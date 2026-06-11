import json
f = open('E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json')
data = json.load(f)
edge = data['edges'][0]
print('Sample edge:')
print(f'  predicates: {edge.get("predicates")}')
print(f'  direction_4: {edge.get("direction_4")}')
print(f'  direction_8: {edge.get("direction_8")}')
