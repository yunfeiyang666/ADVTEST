"""快速验证场景图的方向数据"""
import json

sg = json.load(open('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json'))

print("="*60)
print("验证 scene-0103_frame38 场景图 (Source Frame)")
print("="*60)

print(f"\n对象数: {len(sg['nodes'])}")
print(f"关系数: {len(sg['edges'])}")

# 检查关键方向关系
print("\n--- truck -> pedestrian ---")
for e in sg['edges']:
    if e['source'] == 'truck1' and e['target_type'] == 'pedestrian':
        print(f"  {e['target']}: {e['direction_8']} ({e['metrics']['angle']}°)")

print("\n--- truck -> bicycle ---")
for e in sg['edges']:
    if e['source'] == 'truck1' and e['target_type'] == 'bicycle':
        print(f"  {e['target']}: {e['direction_8']} ({e['metrics']['angle']}°)")

print("\n--- motorcycle -> truck ---")
for e in sg['edges']:
    if e['source'] == 'motorcycle1' and e['target'] == 'truck1':
        print(f"  {e['direction_8']} ({e['metrics']['angle']}°)")

print("\n--- ego -> truck ---")
for e in sg['edges']:
    if e['source'] == 'ego' and e['target'] == 'truck1':
        print(f"  {e['direction_8']} ({e['metrics']['angle']}°)")

print("\n--- motorcycle -> car (back方向) ---")
count = 0
for e in sg['edges']:
    if e['source'] == 'motorcycle1' and e['target_type'] == 'car' and 'back' in e['direction_8']:
        count += 1
        if count <= 3:
            print(f"  {e['target']}: {e['direction_8']} ({e['metrics']['angle']}°)")
print(f"  共 {count} 个car在motorcycle的back方向")
