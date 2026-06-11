"""验证原始NuScenes数据与场景图是否一致"""
import json
import numpy as np
from nuscenes.nuscenes import NuScenes

target_token = "6dabc0fb1df045558f802246dd186b3f"

print("加载NuScenes数据集...")
nusc = NuScenes(version='v1.0-trainval', dataroot='E:/Project/ADVTEST/data/nuscenes', verbose=False)

sample = nusc.get('sample', target_token)

print(f"\n=== Sample {target_token} 的原始标注 ===\n")

# 获取所有annotations
annotations = []
for ann_token in sample['anns']:
    ann = nusc.get('sample_annotation', ann_token)
    annotations.append(ann)

# 按类别分组
categories = {}
for ann in annotations:
    cat = ann['category_name']
    if cat not in categories:
        categories[cat] = []
    categories[cat].append(ann)

print("=== 对象统计 ===")
for cat, anns in sorted(categories.items()):
    print(f"  {cat}: {len(anns)}")

# 重点检查trailer, truck, bicycle
print("\n=== Trailer详情 ===")
for ann in annotations:
    if 'trailer' in ann['category_name']:
        print(f"  Token: {ann['token'][:16]}...")
        print(f"  Category: {ann['category_name']}")
        print(f"  Translation: ({ann['translation'][0]:.2f}, {ann['translation'][1]:.2f}, {ann['translation'][2]:.2f})")
        # 获取速度
        velocity = nusc.box_velocity(ann['token'])
        speed = np.sqrt(velocity[0]**2 + velocity[1]**2) if not np.isnan(velocity[0]) else 0
        status = "moving" if speed > 0.5 else "stopped"
        print(f"  Velocity: ({velocity[0]:.2f}, {velocity[1]:.2f}) -> speed={speed:.2f} -> status={status}")
        print()

print("\n=== Truck详情 (排除trailer) ===")
for ann in annotations:
    if 'truck' in ann['category_name'] and 'trailer' not in ann['category_name']:
        print(f"  Token: {ann['token'][:16]}...")
        print(f"  Category: {ann['category_name']}")
        print(f"  Translation: ({ann['translation'][0]:.2f}, {ann['translation'][1]:.2f}, {ann['translation'][2]:.2f})")
        velocity = nusc.box_velocity(ann['token'])
        speed = np.sqrt(velocity[0]**2 + velocity[1]**2) if not np.isnan(velocity[0]) else 0
        status = "moving" if speed > 0.5 else "stopped"
        print(f"  Velocity: ({velocity[0]:.2f}, {velocity[1]:.2f}) -> speed={speed:.2f} -> status={status}")
        print()

print("\n=== Bicycle详情 ===")
bicycles = []
for ann in annotations:
    if 'bicycle' in ann['category_name']:
        bicycles.append(ann)
        print(f"  Token: {ann['token'][:16]}...")
        print(f"  Category: {ann['category_name']}")
        print(f"  Translation: ({ann['translation'][0]:.2f}, {ann['translation'][1]:.2f}, {ann['translation'][2]:.2f})")
        velocity = nusc.box_velocity(ann['token'])
        speed = np.sqrt(velocity[0]**2 + velocity[1]**2) if not np.isnan(velocity[0]) else 0
        print(f"  Velocity: ({velocity[0]:.2f}, {velocity[1]:.2f}) -> speed={speed:.2f}")
        print()

# 计算bicycle与各truck的相对位置
print("\n=== Bicycle与Truck的相对位置分析 ===")
if bicycles:
    bicycle = bicycles[0]
    bx, by = bicycle['translation'][0], bicycle['translation'][1]
    print(f"Bicycle位置: ({bx:.2f}, {by:.2f})")
    
    # 获取自车位姿用于坐标转换
    sample_data = nusc.get('sample_data', sample['data']['LIDAR_TOP'])
    ego_pose = nusc.get('ego_pose', sample_data['ego_pose_token'])
    ego_x, ego_y = ego_pose['translation'][0], ego_pose['translation'][1]
    print(f"Ego车位置: ({ego_x:.2f}, {ego_y:.2f})")
    
    print("\nTruck相对于Bicycle的位置:")
    for ann in annotations:
        if 'truck' in ann['category_name']:
            tx, ty = ann['translation'][0], ann['translation'][1]
            rel_x = tx - bx
            rel_y = ty - by
            dist = np.sqrt(rel_x**2 + rel_y**2)
            angle = np.arctan2(rel_y, rel_x) * 180 / np.pi
            
            velocity = nusc.box_velocity(ann['token'])
            speed = np.sqrt(velocity[0]**2 + velocity[1]**2) if not np.isnan(velocity[0]) else 0
            status = "moving" if speed > 0.5 else "stopped"
            
            # 判断方位（基于全局坐标）
            if -45 <= angle < 45:
                direction = 'front'
            elif 45 <= angle < 135:
                direction = 'left'
            elif -135 <= angle < -45:
                direction = 'right'
            else:
                direction = 'rear'
            
            print(f"  {ann['category_name']}: ")
            print(f"    位置: ({tx:.2f}, {ty:.2f})")
            print(f"    相对: ({rel_x:.2f}, {rel_y:.2f}), dist={dist:.2f}m")
            print(f"    角度: {angle:.1f}° -> 方位: {direction}")
            print(f"    状态: {status} (speed={speed:.2f})")
            print()

# 加载场景图进行对比
print("\n=== 场景图数据对比 ===")
with open('output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json', 'r') as f:
    sg = json.load(f)

print("场景图中的truck节点:")
for node in sg['nodes']:
    if 'truck' in node['unique_id']:
        print(f"  {node['unique_id']}: category={node['category']}, status={node['status']}")
        print(f"    位置: ({node['translation']['x']:.2f}, {node['translation']['y']:.2f})")
