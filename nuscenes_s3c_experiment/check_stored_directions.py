"""检查场景图中实际存储的方向"""
import json

sg = json.load(open('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json'))

print("=" * 60)
print("检查scene-0103 frame38中的方向关系")
print("=" * 60)

# 建立unique_id到node的映射
nodes = {n['unique_id']: n for n in sg['nodes']}

# 错题涉及的关系:
# 1. motorcycle1 -> truck1 的方向 (期望: back-right)
# 2. truck1 -> pedestrian的方向 (期望: back-right)
# 3. truck1 -> bicycle的方向 (期望: front-left)
# 4. motorcycle1 -> car的方向 (期望: back)

print("\n1. motorcycle1作为source的所有关系:")
for e in sg['edges']:
    if e['source'] == 'motorcycle1':
        print(f"  motorcycle1 -> {e['target']}: {e['predicates'][0]} (angle={e['metrics']['angle']:.1f}°)")

print("\n2. truck1作为source的所有关系:")
for e in sg['edges']:
    if e['source'] == 'truck1':
        target_node = nodes.get(e['target'], {})
        target_type = target_node.get('type', '?')
        if target_type in ['pedestrian', 'bicycle']:
            print(f"  truck1 -> {e['target']}({target_type}): {e['predicates'][0]} (angle={e['metrics']['angle']:.1f}°)")

print("\n3. ego作为source, truck1作为target的关系:")
for e in sg['edges']:
    if e['source'] == 'ego' and e['target'] == 'truck1':
        print(f"  ego -> truck1: {e['predicates'][0]} (angle={e['metrics']['angle']:.1f}°)")

print("\n" + "=" * 60)
print("关键问题分析:")
print("=" * 60)

# 找truck1
truck1 = nodes['truck1']
moto1 = nodes['motorcycle1']
ego = nodes['ego']

print(f"\nego位置: ({ego['translation']['x']:.1f}, {ego['translation']['y']:.1f})")
print(f"motorcycle1位置: ({moto1['translation']['x']:.1f}, {moto1['translation']['y']:.1f})")
print(f"truck1位置: ({truck1['translation']['x']:.1f}, {truck1['translation']['y']:.1f})")

# Q1: truck在motorcycle的back-right吗?
print("\nQ1: truck在motorcycle的什么方向?")
for e in sg['edges']:
    if e['source'] == 'motorcycle1' and e['target'] == 'truck1':
        print(f"  存储的方向: {e['predicates'][0]} (angle={e['metrics']['angle']:.1f}°)")
        print(f"  期望方向: back-right")
        break

# Q2: truck在ego的front-left吗?
print("\nQ2: truck在ego的什么方向?")
for e in sg['edges']:
    if e['source'] == 'ego' and e['target'] == 'truck1':
        print(f"  存储的方向: {e['predicates'][0]} (angle={e['metrics']['angle']:.1f}°)")
        print(f"  期望方向: front-left")
        break

# Q3: pedestrian在truck的back-right?
print("\nQ3: 哪些pedestrian在truck的back-right?")
for e in sg['edges']:
    if e['source'] == 'truck1' and 'pedestrian' in e['target']:
        if 'back-right' in e['predicates'][0]:
            print(f"  {e['target']}: {e['predicates'][0]}")
print("  (如果没有输出，说明没有pedestrian在truck的back-right)")

# Q4: bicycle在truck的front-left?
print("\nQ4: 哪些bicycle在truck的front-left?")
for e in sg['edges']:
    if e['source'] == 'truck1' and 'bicycle' in e['target']:
        print(f"  {e['target']}: {e['predicates'][0]}")
        if 'front-left' in e['predicates'][0]:
            print(f"    ^ 这个匹配front-left!")
