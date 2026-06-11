import json
from pathlib import Path

scene_path = Path('output/coverage_analysis/scene_graphs/scene-0916_frame8_scene_graph.json')
with open(scene_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

print('Nodes (unique_id, type, status, attributes) for ego/bus/pedestrian:')
for n in data.get('nodes', []):
    if n.get('type') in ['pedestrian', 'bus', 'ego']:
        print(n.get('unique_id'), n.get('type'), n.get('status'), n.get('attributes'))

print('\nEdges from ego or bus (source, target, predicates, distance, angle):')
for e in data.get('edges', []):
    if e.get('source') in ['ego', 'bus1', 'bus']:
        print(e)
