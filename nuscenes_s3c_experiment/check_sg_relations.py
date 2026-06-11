import json
sg = json.load(open('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json'))

print("truck -> pedestrian 关系:")
for r in sg.get('relationships', []):
    if r['source'] == 'truck1' and r['target_type'] == 'pedestrian':
        print(f"  {r['target']}: {r['predicates'][0]} ({r['metrics']['angle']})")

print()
print("truck -> bicycle 关系:")
for r in sg.get('relationships', []):
    if r['source'] == 'truck1' and r['target_type'] == 'bicycle':
        print(f"  {r['target']}: {r['predicates'][0]} ({r['metrics']['angle']})")

print()
print("motorcycle -> truck 关系:")
for r in sg.get('relationships', []):
    if r['source'] == 'motorcycle1' and r['target'] == 'truck1':
        print(f"  {r['predicates'][0]} ({r['metrics']['angle']})")

print()
print("ego -> truck 关系:")
for r in sg.get('relationships', []):
    if r['source'] == 'ego' and r['target'] == 'truck1':
        print(f"  {r['predicates'][0]} ({r['metrics']['angle']})")
