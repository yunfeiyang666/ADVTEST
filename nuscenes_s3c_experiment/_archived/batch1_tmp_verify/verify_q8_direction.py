"""
验证Q8: trailer到bus的方向关系
问题: "bus to the front of the stopped trailer"
即: trailer的front方向应该有bus
"""
import numpy as np
import json
from pyquaternion import Quaternion

# 加载场景图
scene_graph_path = "E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json"
with open(scene_graph_path, 'r') as f:
    sg = json.load(f)

print("=" * 70)
print("  Q8方向验证: trailer到bus的方向")
print("=" * 70)

# 找到关键对象
ego_node = next(n for n in sg['nodes'] if n['unique_id'] == 'ego')
trailer_node = next(n for n in sg['nodes'] if 'trailer' in n.get('category', ''))
bus_nodes = [n for n in sg['nodes'] if n['type'] == 'bus']

# 提取ego的yaw
ego_q = Quaternion(ego_node['rotation'])
ego_yaw = ego_q.yaw_pitch_roll[0]
ego_yaw_deg = np.degrees(ego_yaw)

# 提取trailer的位置和yaw
trailer_q = Quaternion(trailer_node['rotation'])
trailer_yaw = trailer_q.yaw_pitch_roll[0]
trailer_yaw_deg = np.degrees(trailer_yaw)

tx, ty = trailer_node['translation']['x'], trailer_node['translation']['y']

print(f"\nEgo yaw: {ego_yaw_deg:.1f}°")
print(f"Trailer ({trailer_node['unique_id']}): pos=({tx}, {ty}), yaw={trailer_yaw_deg:.1f}°")

print(f"\nBus位置:")
for bus in bus_nodes:
    bx, by = bus['translation']['x'], bus['translation']['y']
    print(f"  {bus['unique_id']}: ({bx}, {by})")

print("\n" + "=" * 70)
print("  方向计算对比")
print("=" * 70)

print("\n【方法1】使用Ego朝向作为全局参考 (当前实现):")
for bus in bus_nodes:
    bx, by = bus['translation']['x'], bus['translation']['y']
    dx, dy = bx - tx, by - ty
    
    global_angle = np.arctan2(dy, dx)
    relative_angle_rad = -(global_angle - ego_yaw)
    relative_angle_deg = np.degrees(relative_angle_rad)
    relative_angle_deg = ((relative_angle_deg + 180) % 360) - 180
    
    if -22.5 <= relative_angle_deg < 22.5:
        direction = 'front'
    elif 22.5 <= relative_angle_deg < 67.5:
        direction = 'front-left'
    elif 67.5 <= relative_angle_deg < 112.5:
        direction = 'left'
    elif 112.5 <= relative_angle_deg < 157.5:
        direction = 'back-left'
    elif relative_angle_deg >= 157.5 or relative_angle_deg < -157.5:
        direction = 'back'
    elif -157.5 <= relative_angle_deg < -112.5:
        direction = 'back-right'
    elif -112.5 <= relative_angle_deg < -67.5:
        direction = 'right'
    else:
        direction = 'front-right'
    
    print(f"  trailer -> {bus['unique_id']}: global={np.degrees(global_angle):.1f}°, relative={relative_angle_deg:.1f}° → {direction}")

print("\n【方法2】使用Trailer自身朝向作为参考 (旧实现):")
for bus in bus_nodes:
    bx, by = bus['translation']['x'], bus['translation']['y']
    dx, dy = bx - tx, by - ty
    
    global_angle = np.arctan2(dy, dx)
    relative_angle_rad = global_angle - trailer_yaw  # 使用trailer的yaw
    relative_angle_deg = np.degrees(relative_angle_rad)
    relative_angle_deg = ((relative_angle_deg + 180) % 360) - 180
    
    if -22.5 <= relative_angle_deg < 22.5:
        direction = 'front'
    elif 22.5 <= relative_angle_deg < 67.5:
        direction = 'front-left'
    elif 67.5 <= relative_angle_deg < 112.5:
        direction = 'left'
    elif 112.5 <= relative_angle_deg < 157.5:
        direction = 'back-left'
    elif relative_angle_deg >= 157.5 or relative_angle_deg < -157.5:
        direction = 'back'
    elif -157.5 <= relative_angle_deg < -112.5:
        direction = 'back-right'
    elif -112.5 <= relative_angle_deg < -67.5:
        direction = 'right'
    else:
        direction = 'front-right'
    
    print(f"  trailer -> {bus['unique_id']}: global={np.degrees(global_angle):.1f}°, relative={relative_angle_deg:.1f}° → {direction}")

print("\n【方法3】使用Ego朝向+逆时针为正 (另一种约定):")
for bus in bus_nodes:
    bx, by = bus['translation']['x'], bus['translation']['y']
    dx, dy = bx - tx, by - ty
    
    global_angle = np.arctan2(dy, dx)
    relative_angle_rad = global_angle - ego_yaw  # 不取负
    relative_angle_deg = np.degrees(relative_angle_rad)
    relative_angle_deg = ((relative_angle_deg + 180) % 360) - 180
    
    if -22.5 <= relative_angle_deg < 22.5:
        direction = 'front'
    elif 22.5 <= relative_angle_deg < 67.5:
        direction = 'front-left'
    elif 67.5 <= relative_angle_deg < 112.5:
        direction = 'left'
    elif 112.5 <= relative_angle_deg < 157.5:
        direction = 'back-left'
    elif relative_angle_deg >= 157.5 or relative_angle_deg < -157.5:
        direction = 'back'
    elif -157.5 <= relative_angle_deg < -112.5:
        direction = 'back-right'
    elif -112.5 <= relative_angle_deg < -67.5:
        direction = 'right'
    else:
        direction = 'front-right'
    
    print(f"  trailer -> {bus['unique_id']}: global={np.degrees(global_angle):.1f}°, relative={relative_angle_deg:.1f}° → {direction}")

print("\n" + "=" * 70)
print("  关键发现")
print("=" * 70)
print("""
问题: "bus to the front of the stopped trailer"
需要trailer的front方向有bus

如果使用Ego朝向作为参考:
  - 所有对象的方向都是相对于ego的朝向
  - 但问题问的是"trailer的front"，这应该是相对于trailer自身

可能的根本原因:
  官方标注可能使用的是对象自身的朝向，而不是Ego的朝向！
  
  即: 当问"X to the front of Y"时:
    - 我们的实现: 使用Ego朝向计算X相对于Y的方向
    - 官方可能: 使用Y自身的朝向计算X相对于Y的方向

这会导致:
  1. Ego相关的方向正确（因为Ego的朝向就是参考）
  2. 非Ego对象之间的方向可能错误
""")

# 验证Q11是否有这个问题
print("\n" + "=" * 70)
print("  验证Q11: bicycle to front-left of trailer")
print("=" * 70)

bicycle_node = next(n for n in sg['nodes'] if n['type'] == 'bicycle')
bx, by = bicycle_node['translation']['x'], bicycle_node['translation']['y']
print(f"Bicycle: ({bx}, {by})")

dx, dy = bx - tx, by - ty
global_angle = np.arctan2(dy, dx)

print("\n使用Ego朝向:")
relative_angle_rad = -(global_angle - ego_yaw)
relative_angle_deg = np.degrees(relative_angle_rad)
relative_angle_deg = ((relative_angle_deg + 180) % 360) - 180
print(f"  relative_angle = {relative_angle_deg:.1f}°")
if 22.5 <= relative_angle_deg < 67.5:
    print(f"  → front-left ✓")
else:
    print(f"  → NOT front-left")

print("\n使用Trailer自身朝向:")
relative_angle_rad = global_angle - trailer_yaw
relative_angle_deg = np.degrees(relative_angle_rad)
relative_angle_deg = ((relative_angle_deg + 180) % 360) - 180
print(f"  relative_angle = {relative_angle_deg:.1f}°")
if 22.5 <= relative_angle_deg < 67.5:
    print(f"  → front-left ✓")
else:
    print(f"  → NOT front-left")
