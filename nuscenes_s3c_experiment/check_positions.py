import json
sg = json.load(open('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json'))

print("=== Truck ===")
for n in sg['nodes']:
    if 'truck' in n['unique_id']:
        print(f"{n['unique_id']}: pos=({n['translation']['x']:.1f}, {n['translation']['y']:.1f})")

print("\n=== Ego ===")
for n in sg['nodes']:
    if n['unique_id'] == 'ego':
        print(f"ego: pos=({n['translation']['x']:.1f}, {n['translation']['y']:.1f})")

print("\n=== Pedestrians ===")
for n in sg['nodes']:
    if 'pedestrian' in n['unique_id']:
        print(f"{n['unique_id']}: pos=({n['translation']['x']:.1f}, {n['translation']['y']:.1f}), status={n.get('status','?')}")

print("\n=== Motorcycle ===")
for n in sg['nodes']:
    if 'motorcycle' in n['unique_id']:
        print(f"{n['unique_id']}: pos=({n['translation']['x']:.1f}, {n['translation']['y']:.1f}), status={n.get('status','?')}")

print("\n=== Bicycle ===")
for n in sg['nodes']:
    if 'bicycle' in n['unique_id']:
        print(f"{n['unique_id']}: pos=({n['translation']['x']:.1f}, {n['translation']['y']:.1f}), status={n.get('status','?')}")
