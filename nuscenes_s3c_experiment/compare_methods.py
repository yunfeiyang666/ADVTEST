"""比较两种计算方法，找出差异"""
import json
import math

sg = json.load(open('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json'))
nodes = {n['unique_id']: n for n in sg['nodes']}

def quaternion_to_yaw(q):
    w, x, y, z = q[0], q[1], q[2], q[3]
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return math.degrees(yaw)

def normalize_angle(angle):
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle

def angle_to_direction(angle):
    angle = normalize_angle(angle)
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
    else:  # -67.5 ~ -22.5
        return 'front-right'

ego = nodes['ego']
truck = nodes['truck1']
bicycle1 = nodes['bicycle1']

ex, ey = ego['translation']['x'], ego['translation']['y']
tx, ty = truck['translation']['x'], truck['translation']['y']
bx, by = bicycle1['translation']['x'], bicycle1['translation']['y']

# truck → bicycle1
dx = bx - tx
dy = by - ty

print("="*80)
print("从 truck 到 bicycle1 的方向计算")
print("="*80)
print(f"truck: ({tx:.1f}, {ty:.1f})")
print(f"bicycle1: ({bx:.1f}, {by:.1f})")
print(f"delta: dx={dx:.1f}, dy={dy:.1f}")

ego_heading_deg = quaternion_to_yaw(ego['rotation'])
print(f"\nego heading: {ego_heading_deg:.1f}° (东=0, 逆时针正)")

# 方法1: verify_source_frame.py 的 ego_frame
print("\n" + "-"*40)
print("方法1: ego_frame (verify_source_frame.py)")
print("-"*40)
global_angle = math.degrees(math.atan2(dx, dy))
ego_heading_north = normalize_angle(90 - ego_heading_deg)
relative_angle1 = normalize_angle(global_angle - ego_heading_north)
print(f"  global_angle (atan2(dx,dy), 北=0): {global_angle:.1f}°")
print(f"  ego_heading_north (90 - heading): {ego_heading_north:.1f}°")
print(f"  relative_angle = global - ego_heading_north: {relative_angle1:.1f}°")
print(f"  direction: {angle_to_direction(relative_angle1)}")

# 方法2: verify_ego_perspective.py 的向量投影
print("\n" + "-"*40)
print("方法2: ego_perspective (verify_ego_perspective.py)")
print("-"*40)
ego_heading_rad = math.radians(ego_heading_deg)
ego_front_x = math.cos(ego_heading_rad)
ego_front_y = math.sin(ego_heading_rad)
ego_right_x = math.cos(ego_heading_rad - math.pi/2)
ego_right_y = math.sin(ego_heading_rad - math.pi/2)

print(f"  ego前向向量: ({ego_front_x:.3f}, {ego_front_y:.3f})")
print(f"  ego右向向量: ({ego_right_x:.3f}, {ego_right_y:.3f})")

forward_comp = dx * ego_front_x + dy * ego_front_y
right_comp = dx * ego_right_x + dy * ego_right_y
print(f"  forward分量: {forward_comp:.1f}")
print(f"  right分量: {right_comp:.1f}")

angle2 = math.degrees(math.atan2(-right_comp, forward_comp))
print(f"  angle = atan2(-right, forward): {angle2:.1f}°")
print(f"  direction: {angle_to_direction(angle2)}")

# 现在来理解差异
print("\n" + "="*80)
print("分析差异")
print("="*80)
print(f"方法1结果: {relative_angle1:.1f}° -> {angle_to_direction(relative_angle1)}")
print(f"方法2结果: {angle2:.1f}° -> {angle_to_direction(angle2)}")
print(f"差值: {relative_angle1 - angle2:.1f}°")

# 问题出在哪里？
# 方法1: 用北为0度，然后减去ego朝向（也是北基准）
# 方法2: 直接投影到ego坐标系

# 让我检查是否有180度旋转
print("\n如果取反:")
print(f"  -angle2 = {-angle2:.1f}° -> {angle_to_direction(-angle2)}")

# 或者left/right符号问题
print("\n如果 atan2(right, forward) 而不是 atan2(-right, forward):")
angle2_alt = math.degrees(math.atan2(right_comp, forward_comp))
print(f"  angle = atan2(right, forward): {angle2_alt:.1f}° -> {angle_to_direction(angle2_alt)}")
