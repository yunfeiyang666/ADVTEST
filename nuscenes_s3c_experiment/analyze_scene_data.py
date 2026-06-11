"""分析场景图数据，验证失败问题的根本原因"""
import json

with open('E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json', 'r') as f:
    data = json.load(f)

print("=" * 60)
print("  场景数据分析 - scene-0553 frame8")
print("=" * 60)

# 1. 查看trailer的信息
print('\n=== 1. Trailer信息 ===')
trailer_id = None
trailer_status = None
for node in data['nodes']:
    if 'trailer' in node.get('category', ''):
        trailer_id = node['unique_id']
        trailer_status = node['status']
        print(f"  ID: {node['unique_id']}")
        print(f"  type: {node['type']}")
        print(f"  status: {node['status']}")
        print(f"  category: {node['category']}")

# 2. 查看所有truck的状态
print('\n=== 2. Truck信息 (排除trailer) ===')
trucks = []
for node in data['nodes']:
    if node['type'] == 'truck' and 'trailer' not in node.get('category', ''):
        trucks.append(node)
        print(f"  {node['unique_id']}: status={node['status']}")

# 3. 查看bicycle信息
print('\n=== 3. Bicycle信息 ===')
bicycles = []
for node in data['nodes']:
    if node['type'] == 'bicycle':
        bicycles.append(node)
        print(f"  {node['unique_id']}: status={node['status']}")

# 4. 统计trailer状态相同的对象
print(f'\n=== 4. 与Trailer状态({trailer_status})相同的对象 ===')
same_status = []
for node in data['nodes']:
    if node['status'] == trailer_status and node['unique_id'] != trailer_id:
        same_status.append(node)
print(f"总数: {len(same_status)}")
by_type = {}
for node in same_status:
    t = node['type']
    by_type[t] = by_type.get(t, 0) + 1
for t, c in sorted(by_type.items()):
    print(f"  {t}: {c}")

# 5. 查看bicycle和truck之间的关系
print('\n=== 5. Bicycle与Truck之间的关系 ===')
bicycle_ids = [b['unique_id'] for b in bicycles]
truck_ids = [t['unique_id'] for t in trucks]

for edge in data['edges']:
    src = edge['source']
    tgt = edge['target']
    pred = edge.get('predicates', [])
    if (src in bicycle_ids and tgt in truck_ids) or (src in truck_ids and tgt in bicycle_ids):
        print(f"  {src} -[{pred}]-> {tgt}")

# 6. 验证 Q4: trailer vs truck to back of bicycle
print('\n=== 6. Q4验证: trailer vs truck to back of bicycle ===')
print(f"Trailer status: {trailer_status}")
# 找bicycle后方(rear)的truck
for edge in data['edges']:
    src = edge['source']
    tgt = edge['target']
    pred = edge.get('predicates', [])
    if src in bicycle_ids and tgt in truck_ids and len(pred) > 0 and pred[0] == 'rear':
        truck_node = next((t for t in trucks if t['unique_id'] == tgt), None)
        if truck_node:
            print(f"  找到: {src} -[rear]-> {tgt}, truck status={truck_node['status']}")
            print(f"  比较: trailer({trailer_status}) == truck({truck_node['status']}) ? {trailer_status == truck_node['status']}")

# 7. 查看moving truck
print('\n=== 7. Moving Truck验证 ===')
moving_trucks = [t for t in trucks if t['status'] == 'moving']
print(f"Moving trucks (排除trailer): {len(moving_trucks)}")
for t in moving_trucks:
    print(f"  {t['unique_id']}")

# 8. 验证pedestrian信息
print('\n=== 8. Pedestrian信息 ===')
for node in data['nodes']:
    if node['type'] == 'pedestrian':
        print(f"  {node['unique_id']}: status={node['status']}")

# 9. Truck之间的关系
print('\n=== 9. Truck之间的关系 ===')
truck_ids_all = ['truck1', 'truck2', 'truck3']  # 包含trailer
for edge in data['edges']:
    src = edge['source']
    tgt = edge['target']
    pred = edge.get('predicates', [])
    if src in truck_ids_all and tgt in truck_ids_all:
        print(f"  {src} -[{pred}]-> {tgt}")

# 10. 验证Q7: truck to back of moving truck
print('\n=== 10. Q7验证: truck to back of moving truck ===')
print('Moving truck (truck1) 后方的关系:')
for edge in data['edges']:
    if edge['source'] == 'truck1' and edge['predicates'][0] == 'rear':
        print(f"  truck1 -[{edge['predicates']}]-> {edge['target']}")

# 11. Bus信息
print('\n=== 11. Bus信息 ===')
for node in data['nodes']:
    if node['type'] == 'bus':
        print(f"  {node['unique_id']}: status={node['status']}")

# 12. Q13验证: cars same status as truck to front of bicycle
print('\n=== 12. Q13验证 ===')
print('Bicycle前方(front)的truck:')
for edge in data['edges']:
    if edge['source'] == 'bicycle1' and edge['predicates'][0] == 'front':
        tgt = edge['target']
        if 'truck' in tgt:
            tgt_node = next((n for n in data['nodes'] if n['unique_id'] == tgt), None)
            if tgt_node and 'trailer' not in tgt_node.get('category', ''):
                print(f"  {tgt}: status={tgt_node['status']}")
                # 统计同状态的car
                same_cars = [n for n in data['nodes'] if n['type'] == 'car' and n['status'] == tgt_node['status']]
                print(f"  同状态({tgt_node['status']})的car数量: {len(same_cars)}")

# 13. 位置分析验证
import math
print('\n=== 13. Bicycle与Truck的位置分析 ===')
nodes = {n['unique_id']: n for n in data['nodes']}
bicycle = nodes['bicycle1']
trucks_data = {k:v for k,v in nodes.items() if 'truck' in k}

print(f"Bicycle1: ({bicycle['translation']['x']:.2f}, {bicycle['translation']['y']:.2f})")
for tid, t in trucks_data.items():
    print(f"{tid} ({t['category']}): ({t['translation']['x']:.2f}, {t['translation']['y']:.2f}) - status={t['status']}")

print()
print('相对位置和角度:')
bx, by = bicycle['translation']['x'], bicycle['translation']['y']
for tid, t in trucks_data.items():
    tx, ty = t['translation']['x'], t['translation']['y']
    rel_x = tx - bx
    rel_y = ty - by
    dist = math.sqrt(rel_x**2 + rel_y**2)
    angle = math.atan2(rel_y, rel_x) * 180 / math.pi
    # 判断方位
    if -45 <= angle < 45:
        direction = 'front'
    elif 45 <= angle < 135:
        direction = 'left'
    elif -135 <= angle < -45:
        direction = 'right'
    else:
        direction = 'rear'
    print(f"  Bicycle -> {tid}: rel=({rel_x:.2f}, {rel_y:.2f}), dist={dist:.2f}m, angle={angle:.1f}° -> {direction}")

print()
print('场景图中bicycle与truck的关系:')
for edge in data['edges']:
    if edge['source'] == 'bicycle1' and 'truck' in edge['target']:
        print(f"  {edge['source']} -[{edge['predicates']}]-> {edge['target']}")
