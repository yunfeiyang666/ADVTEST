"""
测试 compute_direction_features 函数是否正确
使用实际的场景数据
"""
import sys
import json
sys.path.insert(0, r'E:/Project/ADVTEST/nuscenes_s3c_experiment')

# 读取场景图数据
with open(r'E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json', 'r') as f:
    sg = json.load(f)

# 获取ego, truck1, ped7的数据
ego = truck1 = ped7 = None
for node in sg['nodes']:
    if node['unique_id'] == 'ego':
        ego = node
    elif node['unique_id'] == 'truck1':
        truck1 = node
    elif node['unique_id'] == 'pedestrian7':
        ped7 = node

print("=== 场景图中存储的数据 ===")
print(f"ego: {ego['translation']}, rotation: {ego['rotation']}")
print(f"truck1: {truck1['translation']}")
print(f"ped7: {ped7['translation']}")

# 查找 truck1->ped7 的边
for edge in sg['edges']:
    if edge['source'] == 'truck1' and edge['target'] == 'pedestrian7':
        print(f"\n场景图中 truck1->ped7 的边:")
        print(f"  angle: {edge['metrics']['angle']}")
        print(f"  direction_8: {edge['direction_8']}")
        print(f"  predicates: {edge['predicates']}")
        print(f"  relative_position: {edge['metrics']['relative_position']}")
        stored_angle = edge['metrics']['angle']
        break

print("\n=== 手动计算验证 ===")
import numpy as np
import math

# 简化的计算（不依赖pyquaternion）
ego_trans = (ego['translation']['x'], ego['translation']['y'], ego['translation']['z'])
truck_trans = (truck1['translation']['x'], truck1['translation']['y'], truck1['translation']['z'])
ped_trans = (ped7['translation']['x'], ped7['translation']['y'], ped7['translation']['z'])
ego_rot = ego['rotation']

# 计算 ego yaw
w, x, y, z = ego_rot
ego_yaw = math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
print(f"Ego yaw: {math.degrees(ego_yaw):.1f}°")

# 计算 truck->ped 的全局角度
dx = ped_trans[0] - truck_trans[0]
dy = ped_trans[1] - truck_trans[1]
global_angle = math.atan2(dy, dx)
print(f"Global angle (truck->ped7): {math.degrees(global_angle):.1f}°")

# Ego frame 角度
ego_frame_angle_rad = global_angle - ego_yaw
ego_frame_angle_deg = math.degrees(ego_frame_angle_rad)
# 归一化
while ego_frame_angle_deg > 180:
    ego_frame_angle_deg -= 360
while ego_frame_angle_deg <= -180:
    ego_frame_angle_deg += 360

print(f"Ego frame angle: {ego_frame_angle_deg:.1f}°")
print(f"场景图存储的angle: {stored_angle}°")
print(f"差值: {abs(ego_frame_angle_deg - stored_angle):.1f}°")

if abs(abs(ego_frame_angle_deg - stored_angle) - 180) < 5:
    print("\n❌ 问题确认：角度相差约180°！")
    print("可能原因：")
    print("  1. source和target位置反了")
    print("  2. ego_yaw符号错误")
    print("  3. 坐标轴定义问题")
elif abs(ego_frame_angle_deg - stored_angle) < 5:
    print("\n✅ 角度计算正确")
