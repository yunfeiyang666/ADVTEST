"""分析Q6, Q7, Q11, Q12, Q13的详细信息"""
import json
import math

# 读取测试结果
with open('output/coverage_analysis/vqa_results/failed_cases_retest_20260121_214131.json', 'r', encoding='utf-8') as f:
    results = json.load(f)

# 读取场景图
with open('output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json', 'r', encoding='utf-8') as f:
    scene_graph = json.load(f)

# 提取关键对象
nodes = {n['unique_id']: n for n in scene_graph['nodes']}
edges = scene_graph['edges']

print("=" * 100)
print("场景中的关键对象")
print("=" * 100)

# Ego
ego = nodes['ego']
print(f"\nEgo: ({ego['translation']['x']:.2f}, {ego['translation']['y']:.2f})")

# Trucks
print("\n卡车 (Trucks):")
for uid, n in nodes.items():
    if n['type'] == 'truck':
        print(f"  {uid}: category={n['category']}, status={n['status']}, pos=({n['translation']['x']:.2f}, {n['translation']['y']:.2f})")

# Bicycle
print("\n自行车 (Bicycles):")
for uid, n in nodes.items():
    if n['type'] == 'bicycle':
        print(f"  {uid}: status={n['status']}, pos=({n['translation']['x']:.2f}, {n['translation']['y']:.2f})")

# Trailer (truck2)
print("\nTrailer (truck2):")
truck2 = nodes['truck2']
print(f"  truck2: category={truck2['category']}, status={truck2['status']}, pos=({truck2['translation']['x']:.2f}, {truck2['translation']['y']:.2f})")

print("\n" + "=" * 100)
print("从Ego出发的方向关系 (只看truck)")
print("=" * 100)
for e in edges:
    if e['source'] == 'ego' and nodes[e['target']]['type'] == 'truck':
        print(f"  ego -[{e['predicates'][0]}]-> {e['target']} ({nodes[e['target']]['category']}, {nodes[e['target']]['status']})")

print("\n" + "=" * 100)
print("从Bicycle出发的方向关系 (只看truck)")
print("=" * 100)
for e in edges:
    if e['source'] == 'bicycle1' and nodes[e['target']]['type'] == 'truck':
        print(f"  bicycle1 -[{e['predicates'][0]}]-> {e['target']} ({nodes[e['target']]['category']}, {nodes[e['target']]['status']})")

print("\n" + "=" * 100)
print("从Trailer(truck2)出发的方向关系 (只看bicycle)")
print("=" * 100)
for e in edges:
    if e['source'] == 'truck2' and nodes[e['target']]['type'] == 'bicycle':
        print(f"  truck2 -[{e['predicates'][0]}]-> {e['target']} ({nodes[e['target']]['status']})")

print("\n" + "=" * 100)
print("从Moving Truck(truck1)出发的方向关系 (只看truck)")
print("=" * 100)
for e in edges:
    if e['source'] == 'truck1' and nodes[e['target']]['type'] == 'truck':
        print(f"  truck1 -[{e['predicates'][0]}]-> {e['target']} ({nodes[e['target']]['category']}, {nodes[e['target']]['status']})")

# 问题分析
print("\n" + "=" * 100)
print("问题详细分析")
print("=" * 100)

questions = [5, 6, 10, 11, 12]
for idx in questions:
    r = results['results'][idx]
    print(f"\n{'='*80}")
    print(f"Q{idx+1}: {r['question']}")
    print(f"预期答案: {r['expected_answer']}")
    print(f"实际答案: {r.get('answer', 'N/A')}")
    print(f"原始失败原因: {r['original_failure_reason']}")
