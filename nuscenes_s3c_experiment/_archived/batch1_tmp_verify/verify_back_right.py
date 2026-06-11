"""验证back right方向的truck"""
import json
import numpy as np
from scipy.spatial.transform import Rotation as R
from nuscenes.nuscenes import NuScenes

target_token = "6dabc0fb1df045558f802246dd186b3f"

print("加载NuScenes数据集...")
nusc = NuScenes(version='v1.0-trainval', dataroot='E:/Project/ADVTEST/data/nuscenes', verbose=False)

sample = nusc.get('sample', target_token)

# 找到bicycle和trucks
bicycle_ann = None
truck_anns = []

for ann_token in sample['anns']:
    ann = nusc.get('sample_annotation', ann_token)
    if 'bicycle' in ann['category_name']:
        bicycle_ann = ann
    if 'truck' in ann['category_name']:
        truck_anns.append(ann)

bx, by = bicycle_ann['translation'][0], bicycle_ann['translation'][1]
quat = bicycle_ann['rotation']
r = R.from_quat([quat[1], quat[2], quat[3], quat[0]])
euler = r.as_euler('zyx', degrees=True)
yaw = euler[0]
heading_rad = np.deg2rad(yaw)

print(f"Bicycle位置: ({bx:.2f}, {by:.2f}), 朝向: {yaw:.1f}°")

print("\n=== 基于8方位的相对位置分析 ===")
for ann in truck_anns:
    tx, ty = ann['translation'][0], ann['translation'][1]
    
    rel_x_global = tx - bx
    rel_y_global = ty - by
    
    cos_h = np.cos(-heading_rad)
    sin_h = np.sin(-heading_rad)
    rel_x_local = cos_h * rel_x_global - sin_h * rel_y_global
    rel_y_local = sin_h * rel_x_global + cos_h * rel_y_global
    
    angle_local = np.arctan2(rel_y_local, rel_x_local) * 180 / np.pi
    
    # 8方位判断
    # front: -22.5 ~ 22.5
    # front-right: -67.5 ~ -22.5
    # right: -112.5 ~ -67.5
    # back-right: -157.5 ~ -112.5
    # back: >157.5 or <-157.5
    # back-left: 112.5 ~ 157.5
    # left: 67.5 ~ 112.5
    # front-left: 22.5 ~ 67.5
    
    if -22.5 <= angle_local < 22.5:
        direction = 'front'
    elif -67.5 <= angle_local < -22.5:
        direction = 'front-right'
    elif -112.5 <= angle_local < -67.5:
        direction = 'right'
    elif -157.5 <= angle_local < -112.5:
        direction = 'back-right'
    elif angle_local >= 157.5 or angle_local < -157.5:
        direction = 'back'
    elif 112.5 <= angle_local < 157.5:
        direction = 'back-left'
    elif 67.5 <= angle_local < 112.5:
        direction = 'left'
    else:
        direction = 'front-left'
    
    velocity = nusc.box_velocity(ann['token'])
    speed = np.sqrt(velocity[0]**2 + velocity[1]**2) if not np.isnan(velocity[0]) else 0
    status = "moving" if speed > 0.5 else "stopped"
    
    print(f"\n{ann['category_name']}:")
    print(f"  本地相对位置: ({rel_x_local:.2f}, {rel_y_local:.2f})")
    print(f"  本地角度: {angle_local:.1f}° -> 方位: {direction}")
    print(f"  状态: {status}")

# 验证Q3/Q4
print("\n=== Q3/Q4验证: Is trailer same status as truck to BACK RIGHT of bicycle? ===")
trailer_status = None
back_right_truck_status = None

for ann in truck_anns:
    tx, ty = ann['translation'][0], ann['translation'][1]
    rel_x_global = tx - bx
    rel_y_global = ty - by
    cos_h = np.cos(-heading_rad)
    sin_h = np.sin(-heading_rad)
    rel_x_local = cos_h * rel_x_global - sin_h * rel_y_global
    rel_y_local = sin_h * rel_x_global + cos_h * rel_y_global
    angle_local = np.arctan2(rel_y_local, rel_x_local) * 180 / np.pi
    
    velocity = nusc.box_velocity(ann['token'])
    speed = np.sqrt(velocity[0]**2 + velocity[1]**2) if not np.isnan(velocity[0]) else 0
    status = "moving" if speed > 0.5 else "stopped"
    
    if 'trailer' in ann['category_name']:
        trailer_status = status
        print(f"Trailer: 角度={angle_local:.1f}°, 状态={status}")
    elif -157.5 <= angle_local < -112.5:  # back-right
        back_right_truck_status = status
        print(f"Truck to BACK-RIGHT: 角度={angle_local:.1f}°, 状态={status}")

if back_right_truck_status:
    print(f"\n结论: trailer({trailer_status}) == truck_to_back_right({back_right_truck_status})? {trailer_status == back_right_truck_status}")
else:
    print("\n没有找到back-right方向的truck")
    
# 检查场景图中的边
print("\n=== 场景图中的bicycle与truck关系 ===")
with open('output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json', 'r') as f:
    sg = json.load(f)

for edge in sg['edges']:
    if edge['source'] == 'bicycle1' and 'truck' in edge['target']:
        print(f"  {edge['source']} -[{edge['predicates']}]-> {edge['target']}")
