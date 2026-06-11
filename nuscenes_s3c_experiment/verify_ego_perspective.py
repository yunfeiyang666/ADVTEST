"""
验证: NuScenes-QA 使用 ego 视角来判断所有方向

假设: 无论是 ego→X 还是 A→B 的方向，都是以 ego 车的朝向为参考
- front = ego 的前进方向
- right = ego 的右手边
"""
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
    """角度转方向 (0°=front, 右为负)"""
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

def calc_direction_ego_perspective(source, target, ego):
    """
    以 ego 视角计算 source → target 的方向
    使用向量投影法：将方向向量投影到 ego 的坐标系
    """
    sx, sy = source['translation']['x'], source['translation']['y']
    tx, ty = target['translation']['x'], target['translation']['y']
    dx = tx - sx
    dy = ty - sy
    
    # ego 的朝向 (东=0, 逆时针为正)
    ego_heading = math.radians(quaternion_to_yaw(ego['rotation']))
    
    # ego 的前向和右向向量
    ego_front_x = math.cos(ego_heading)
    ego_front_y = math.sin(ego_heading)
    ego_right_x = math.cos(ego_heading - math.pi/2)  # 顺时针90°
    ego_right_y = math.sin(ego_heading - math.pi/2)
    
    # 投影
    forward_comp = dx * ego_front_x + dy * ego_front_y
    right_comp = dx * ego_right_x + dy * ego_right_y
    
    # 角度 (前=0, 左为正, 右为负)
    angle = math.degrees(math.atan2(-right_comp, forward_comp))
    
    return angle_to_direction(angle), angle

def calc_direction_global(source, target):
    """
    全局坐标系计算方向 (北=front, 东=right)
    """
    sx, sy = source['translation']['x'], source['translation']['y']
    tx, ty = target['translation']['x'], target['translation']['y']
    dx = tx - sx
    dy = ty - sy
    
    # 全局角度 (北=0, 东=90)
    # atan2(dx, dy) 给出以北为0的角度
    angle = math.degrees(math.atan2(dx, dy))
    
    return angle_to_direction(angle), angle

ego = nodes['ego']
truck = nodes['truck1']
moto = nodes['motorcycle1']

print("="*80)
print("混合方法验证")
print("- Ego相关问题: 使用 Global (北=front)")
print("- Object-to-object: 使用 Ego视角 (ego前向=front)")
print("="*80)

# Q1: truck 在 motorcycle 的什么方向? (期望: back-right)
# Object-to-object → 用 Ego视角
print("\nQ1: truck 在 motorcycle 的什么方向? (期望: back-right)")
print("    [Object-to-object → Ego视角]")
dir1, angle1 = calc_direction_ego_perspective(moto, truck, ego)
print(f"  Ego视角: {dir1} ({angle1:.1f}°)")
print(f"  {'✓ 匹配!' if dir1 == 'back-right' else '✗ 不匹配'}")

# Q2: truck 在 ego 的什么方向? (期望: front-left)
# Ego相关 → 用 Global
print("\nQ2: truck 在 ego 的什么方向? (期望: front-left)")
print("    [Ego相关 → Global]")
dir2g, angle2g = calc_direction_global(ego, truck)
dir2e, angle2e = calc_direction_ego_perspective(ego, truck, ego)
print(f"  Global: {dir2g} ({angle2g:.1f}°) {'✓' if dir2g == 'front-left' else '✗'}")
print(f"  Ego视角: {dir2e} ({angle2e:.1f}°) {'✓' if dir2e == 'front-left' else '✗'}")

# Q3: pedestrian 在 truck 的 back-right (期望: 应有 moving 的)
print("\nQ3: 哪些 pedestrian 在 truck 的 back-right? (期望: 应有 moving 的)")
for n in sg['nodes']:
    if 'pedestrian' not in n['unique_id']:
        continue
    dir3, angle3 = calc_direction_ego_perspective(truck, n, ego)
    status = n.get('status', '?')
    if dir3 == 'back-right':
        print(f"  {n['unique_id']}({status}): {dir3} ({angle3:.1f}°) ✓")
    else:
        print(f"  {n['unique_id']}({status}): {dir3} ({angle3:.1f}°)")

# Q4: bicycle 在 truck 的 front-left (期望: without rider)
print("\nQ4: 哪些 bicycle 在 truck 的 front-left? (期望: without rider)")
for n in sg['nodes']:
    if 'bicycle' not in n['unique_id']:
        continue
    dir4, angle4 = calc_direction_ego_perspective(truck, n, ego)
    status = n.get('status', '?')
    if dir4 == 'front-left':
        print(f"  {n['unique_id']}({status}): {dir4} ({angle4:.1f}°) ✓")
    else:
        print(f"  {n['unique_id']}({status}): {dir4} ({angle4:.1f}°)")

# Q5: car 在 motorcycle 的 back (期望: yes - parked cars)
print("\nQ5: 哪些 car 在 motorcycle 的 back? (期望: parked)")
for n in sg['nodes']:
    if n['type'] != 'car':
        continue
    dir5, angle5 = calc_direction_ego_perspective(moto, n, ego)
    status = n.get('status', '?')
    if 'back' in dir5:
        print(f"  {n['unique_id']}({status}): {dir5} ({angle5:.1f}°) ✓")

print("\n" + "="*80)
print("结论")
print("="*80)
