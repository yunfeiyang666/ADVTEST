"""
测试实际的 direction_utils.py 计算逻辑
"""
import sys
sys.path.insert(0, r'E:/Project/ADVTEST/nuscenes_s3c_experiment')

# 直接复现 direction_utils.py 的逻辑
import numpy as np
from pyquaternion import Quaternion

def quaternion_to_yaw(rotation):
    q = Quaternion(rotation)
    return float(q.yaw_pitch_roll[0])

def ego_relative_angle_and_distance(source_translation, target_translation, ego_rotation):
    src = np.array(list(source_translation), dtype=float)
    tgt = np.array(list(target_translation), dtype=float)
    rel = tgt - src

    distance = float(np.linalg.norm(rel[:2]))
    world_angle = np.arctan2(rel[1], rel[0])
    ego_yaw = quaternion_to_yaw(ego_rotation)
    
    rel_deg = (world_angle - ego_yaw) * 180.0 / np.pi
    angle_deg = ((rel_deg + 180.0) % 360.0) - 180.0

    return float(angle_deg), distance, rel

def discretize_direction_8(angle_deg):
    a = ((float(angle_deg) + 180.0) % 360.0) - 180.0
    if -22.5 <= a < 22.5:
        return "front"
    if 22.5 <= a < 67.5:
        return "front-left"
    if 67.5 <= a < 112.5:
        return "left"
    if 112.5 <= a < 157.5:
        return "back-left"
    if a >= 157.5 or a < -157.5:
        return "back"
    if -157.5 <= a < -112.5:
        return "back-right"
    if -112.5 <= a < -67.5:
        return "right"
    return "front-right"

# 实际数据
ego_rot = [-0.9369, -0.01, 0.0059, 0.3493]  # 从JSON
truck1_trans = (695.26, 1581.75, 1.17)
ped7_trans = (640.31, 1606.25, 1.26)
ped8_trans = (639.03, 1609.72, 0.98)

print("=== 使用 direction_utils.py 的逻辑 ===")
print(f"Ego rotation (quaternion): {ego_rot}")
ego_yaw = quaternion_to_yaw(ego_rot)
print(f"Ego yaw: {ego_yaw * 180 / np.pi:.1f}°")

print("\n--- truck1 -> ped7 ---")
angle, dist, rel = ego_relative_angle_and_distance(truck1_trans, ped7_trans, ego_rot)
dir8 = discretize_direction_8(angle)
print(f"World angle (atan2): {np.arctan2(ped7_trans[1]-truck1_trans[1], ped7_trans[0]-truck1_trans[0])*180/np.pi:.1f}°")
print(f"Ego-relative angle: {angle:.1f}°")
print(f"Direction 8: {dir8}")
print(f"JSON显示: angle=18.5°, direction='front'")

print("\n--- truck1 -> ped8 ---")
angle, dist, rel = ego_relative_angle_and_distance(truck1_trans, ped8_trans, ego_rot)
dir8 = discretize_direction_8(angle)
print(f"World angle (atan2): {np.arctan2(ped8_trans[1]-truck1_trans[1], ped8_trans[0]-truck1_trans[0])*180/np.pi:.1f}°")
print(f"Ego-relative angle: {angle:.1f}°")
print(f"Direction 8: {dir8}")
print(f"JSON显示: angle=16.0°, direction='front'")

print("\n=== 检查pyquaternion的yaw解释 ===")
print("pyquaternion期望的四元数顺序是 [w, x, y, z]")
print(f"我们传入的: {ego_rot}")
print(f"第一个元素(-0.9369)被解释为w")

# 尝试不同顺序
print("\n=== 尝试调整四元数顺序 ===")
# NuScenes实际存储的可能是 [w, x, y, z]，但值可能是反的？
# 或者JSON存储的顺序不同？
ego_rot_swapped = [ego_rot[3], ego_rot[0], ego_rot[1], ego_rot[2]]  # 假设是xyzw
print(f"如果JSON是[x,y,z,w]格式，调整为[w,x,y,z]: {ego_rot_swapped}")
ego_yaw_swapped = quaternion_to_yaw(ego_rot_swapped)
print(f"调整后Ego yaw: {ego_yaw_swapped * 180 / np.pi:.1f}°")

angle_swapped, _, _ = ego_relative_angle_and_distance(truck1_trans, ped7_trans, ego_rot_swapped)
print(f"truck1->ped7 angle with swapped quat: {angle_swapped:.1f}°")
