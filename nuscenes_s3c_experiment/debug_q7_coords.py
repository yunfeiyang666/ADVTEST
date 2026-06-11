"""
检查 truck1 和 pedestrian 的实际坐标
"""
import json

# 读取场景图
with open(r'E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json', 'r') as f:
    sg = json.load(f)

print('=== 查找 truck1 ===')
for node in sg['nodes']:
    if node['unique_id'] == 'truck1':
        print(f"truck1: {node}")
        truck_x = node['translation']['x']
        truck_y = node['translation']['y']
        truck_rot = node['rotation']  # quaternion
        print(f"  位置: x={truck_x}, y={truck_y}")
        print(f"  朝向: {truck_rot}")

print('\n=== 查找所有 pedestrian ===')
pedestrians = []
for node in sg['nodes']:
    if node['type'] == 'pedestrian':
        ped_x = node['translation']['x']
        ped_y = node['translation']['y']
        print(f"{node['unique_id']}: x={ped_x}, y={ped_y}, status={node.get('status','N/A')}")
        pedestrians.append(node)

print('\n=== 检查 truck1 -> pedestrian 的边 ===')
for edge in sg['edges']:
    if edge['source'] == 'truck1' and 'pedestrian' in edge['target']:
        print(f"\ntruck1 -> {edge['target']}:")
        print(f"  predicates: {edge.get('predicates', [])}")
        print(f"  direction_4: {edge.get('direction_4', 'N/A')}")
        print(f"  direction_8: {edge.get('direction_8', 'N/A')}")
        print(f"  distance: {edge.get('metrics', {}).get('distance', 'N/A')}")

print('\n=== 根据 BEV 图标注，检查 pedestrian7 和 pedestrian8 ===')
print('BEV图显示: 41(pedestrian7), 44(pedestrian8) 在 38(truck1) 的后右方')
print('\n从场景图数据中查找这些对象的信息:')
for node in sg['nodes']:
    if node['unique_id'] in ['pedestrian7', 'pedestrian8', 'truck1']:
        print(f"\n{node['unique_id']}:")
        print(f"  位置: {node['translation']}")
        if 'rotation' in node:
            print(f"  朝向: {node['rotation']}")

print('\n=== 检查 truck1 -> pedestrian7 的关系 ===')
for edge in sg['edges']:
    if edge['source'] == 'truck1' and edge['target'] == 'pedestrian7':
        print(f"找到边: {edge}")

print('\n=== 检查 truck1 -> pedestrian8 的关系 ===')
for edge in sg['edges']:
    if edge['source'] == 'truck1' and edge['target'] == 'pedestrian8':
        print(f"找到边: {edge}")
