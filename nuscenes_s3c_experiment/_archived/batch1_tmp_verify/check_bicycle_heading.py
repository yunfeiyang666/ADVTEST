"""检查bicycle的朝向，分析基于朝向的相对位置"""
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

print(f"\n=== Bicycle朝向分析 ===")
print(f"Bicycle位置: ({bicycle_ann['translation'][0]:.2f}, {bicycle_ann['translation'][1]:.2f})")
print(f"Bicycle四元数: {bicycle_ann['rotation']}")

# 将四元数转换为欧拉角
quat = bicycle_ann['rotation']  # [w, x, y, z]
# scipy expects [x, y, z, w]
r = R.from_quat([quat[1], quat[2], quat[3], quat[0]])
euler = r.as_euler('zyx', degrees=True)
yaw = euler[0]  # z轴旋转即为朝向
print(f"Bicycle朝向(yaw): {yaw:.1f}°")

# 计算bicycle的速度方向作为朝向参考
velocity = nusc.box_velocity(bicycle_ann['token'])
if not np.isnan(velocity[0]):
    vel_angle = np.arctan2(velocity[1], velocity[0]) * 180 / np.pi
    print(f"Bicycle速度: ({velocity[0]:.2f}, {velocity[1]:.2f})")
    print(f"Bicycle速度方向: {vel_angle:.1f}°")

print(f"\n=== 基于Bicycle朝向的相对位置 ===")
bx, by = bicycle_ann['translation'][0], bicycle_ann['translation'][1]

# Bicycle朝向角度（弧度）
heading_rad = np.deg2rad(yaw)

for ann in truck_anns:
    tx, ty = ann['translation'][0], ann['translation'][1]
    
    # 全局坐标系下的相对位置
    rel_x_global = tx - bx
    rel_y_global = ty - by
    
    # 转换到bicycle本地坐标系（前方为x正方向）
    # 旋转矩阵：将全局坐标转到本地坐标
    cos_h = np.cos(-heading_rad)
    sin_h = np.sin(-heading_rad)
    rel_x_local = cos_h * rel_x_global - sin_h * rel_y_global
    rel_y_local = sin_h * rel_x_global + cos_h * rel_y_global
    
    # 计算角度（本地坐标系）
    angle_local = np.arctan2(rel_y_local, rel_x_local) * 180 / np.pi
    
    # 基于本地坐标系判断方位
    # front: -45 ~ 45, left: 45 ~ 135, back: >135 or <-135, right: -135 ~ -45
    if -45 <= angle_local < 45:
        direction = 'front'
    elif 45 <= angle_local < 135:
        direction = 'left'
    elif -135 <= angle_local < -45:
        direction = 'right'
    else:
        direction = 'back'
    
    velocity = nusc.box_velocity(ann['token'])
    speed = np.sqrt(velocity[0]**2 + velocity[1]**2) if not np.isnan(velocity[0]) else 0
    status = "moving" if speed > 0.5 else "stopped"
    
    print(f"\n{ann['category_name']}:")
    print(f"  全局相对位置: ({rel_x_global:.2f}, {rel_y_global:.2f})")
    print(f"  本地相对位置: ({rel_x_local:.2f}, {rel_y_local:.2f})")
    print(f"  本地角度: {angle_local:.1f}° -> 方位: {direction}")
    print(f"  状态: {status}")

print(f"\n=== 验证Q3/Q4: Is trailer same status as truck to back of bicycle? ===")
trailer_status = None
back_truck_status = None
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
    else:
        if angle_local > 135 or angle_local < -135:  # back
            back_truck_status = status
            print(f"Truck to BACK: 角度={angle_local:.1f}°, 状态={status}")
        else:
            print(f"Truck (not back): 角度={angle_local:.1f}°, 状态={status}")

print(f"\n结论: trailer({trailer_status}) == truck_to_back({back_truck_status})? {trailer_status == back_truck_status}")
