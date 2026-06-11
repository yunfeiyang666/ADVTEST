"""
验证假设：官方使用混合方位系统
- 4方位词（front, back, left, right）: 每个方位90度范围
- 8方位词（front-left等）: 每个方位45度范围
"""
import numpy as np
import json
from pyquaternion import Quaternion
from neo4j import GraphDatabase

# 加载场景图
scene_graph_path = "E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json"
with open(scene_graph_path, 'r') as f:
    sg = json.load(f)

# 获取ego yaw
ego_node = next(n for n in sg['nodes'] if n['unique_id'] == 'ego')
ego_q = Quaternion(ego_node['rotation'])
ego_yaw = ego_q.yaw_pitch_roll[0]

print("=" * 70)
print("  假设验证：4方位 vs 8方位系统")
print("=" * 70)

print("""
【假设】
官方问题根据表述使用不同的方位范围：
- 4方位词（front, back, left, right）: 每个方位±45°，共90°
- 8方位词（front-left, back-right等）: 每个方位±22.5°，共45°

【4方位定义】
  front: -45° ~ 45°
  left:   45° ~ 135°
  back:  135° ~ 180° 和 -180° ~ -135°
  right: -135° ~ -45°

【8方位定义】(当前)
  front:       -22.5° ~ 22.5°
  front-left:   22.5° ~ 67.5°
  left:         67.5° ~ 112.5°
  ...以此类推
""")

def get_direction_4(angle):
    """4方位系统"""
    angle = ((angle + 180) % 360) - 180
    if -45 <= angle < 45:
        return 'front'
    elif 45 <= angle < 135:
        return 'left'
    elif angle >= 135 or angle < -135:
        return 'back'
    else:
        return 'right'

def get_direction_8(angle):
    """8方位系统"""
    angle = ((angle + 180) % 360) - 180
    if -22.5 <= angle < 22.5:
        return 'front'
    elif 22.5 <= angle < 67.5:
        return 'front-left'
    elif 67.5 <= angle < 112.5:
        return 'left'
    elif 112.5 <= angle < 157.5:
        return 'back-left'
    elif angle >= 157.5 or angle < -157.5:
        return 'back'
    elif -157.5 <= angle < -112.5:
        return 'back-right'
    elif -112.5 <= angle < -67.5:
        return 'right'
    else:
        return 'front-right'

print("\n" + "=" * 70)
print("  验证各问题")
print("=" * 70)

# 获取各对象
trailer_node = next(n for n in sg['nodes'] if 'trailer' in n.get('category', ''))
bicycle_node = next(n for n in sg['nodes'] if n['type'] == 'bicycle')
bus_nodes = [n for n in sg['nodes'] if n['type'] == 'bus']
truck_nodes = [n for n in sg['nodes'] if n['type'] == 'truck']

def calc_direction(source, target):
    """计算source到target的方向（使用ego朝向+顺时针正）"""
    sx, sy = source['translation']['x'], source['translation']['y']
    tx, ty = target['translation']['x'], target['translation']['y']
    dx, dy = tx - sx, ty - sy
    global_angle = np.arctan2(dy, dx)
    relative_angle = -(global_angle - ego_yaw)
    relative_angle_deg = np.degrees(relative_angle)
    relative_angle_deg = ((relative_angle_deg + 180) % 360) - 180
    return relative_angle_deg

# Q6: "truck to the back of me" - 4方位词"back"
print("\n【Q6】'truck to the back of me'")
print("  问题使用4方位词'back'，应使用4方位系统判断")
ego_pos = {'translation': {'x': ego_node['translation']['x'], 'y': ego_node['translation']['y']}}
for truck in truck_nodes:
    angle = calc_direction(ego_pos, truck)
    dir4 = get_direction_4(angle)
    dir8 = get_direction_8(angle)
    is_trailer = 'trailer' in truck.get('category', '')
    print(f"  ego -> {truck['unique_id']}: angle={angle:.1f}°, 4方位={dir4}, 8方位={dir8}, trailer={is_trailer}")

# Q8: "bus to the front of the stopped trailer" - 4方位词"front"
print("\n【Q8】'bus to the front of the stopped trailer'")
print("  问题使用4方位词'front'，应使用4方位系统判断")
for bus in bus_nodes:
    angle = calc_direction(trailer_node, bus)
    dir4 = get_direction_4(angle)
    dir8 = get_direction_8(angle)
    print(f"  trailer -> {bus['unique_id']}: angle={angle:.1f}°, 4方位={dir4}, 8方位={dir8}")

# Q11: "bicycles to the front left of it" - 8方位词"front left"
print("\n【Q11】'bicycles to the front left of it (trailer)'")
print("  问题使用8方位词'front-left'，应使用8方位系统判断")
angle = calc_direction(trailer_node, bicycle_node)
dir4 = get_direction_4(angle)
dir8 = get_direction_8(angle)
print(f"  trailer -> bicycle1: angle={angle:.1f}°, 4方位={dir4}, 8方位={dir8}")

# Q12/Q13: "truck to the front left of the bicycle" - 8方位词"front left"
print("\n【Q12/Q13】'truck to the front left of the bicycle'")
print("  问题使用8方位词'front-left'，应使用8方位系统判断")
for truck in truck_nodes:
    is_trailer = 'trailer' in truck.get('category', '')
    angle = calc_direction(bicycle_node, truck)
    dir4 = get_direction_4(angle)
    dir8 = get_direction_8(angle)
    print(f"  bicycle -> {truck['unique_id']}: angle={angle:.1f}°, 4方位={dir4}, 8方位={dir8}, trailer={is_trailer}")

print("\n" + "=" * 70)
print("  结论")
print("=" * 70)
print("""
【发现】
1. Q6: ego -> truck2(trailer) 在 'back' 方向 (4方位系统下)
   - 8方位: back
   - 4方位: back ✓
   
2. Q8: trailer -> bus1/bus2 使用4方位应为 'front'
   - 8方位: front-right
   - 4方位: front ✓
   
3. Q11: trailer -> bicycle 使用8方位应为 'front-left'
   - 8方位: front-left ✓
   - 4方位: front

4. Q12/Q13: bicycle -> truck 没有任何truck在 'front-left' 方向
   - 这可能是官方标注问题

【根本原因】
我们只使用了8方位系统，但官方问题混用4方位和8方位表述。
需要根据问题中的方位词动态选择判断标准。

【解决方案】
1. 修改Cypher生成提示，让LLM识别4方位vs8方位表述
2. 或在场景图中同时存储4方位和8方位关系
""")
