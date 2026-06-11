"""
测试假设: object-to-object 问题需要 left/right 互换

原始 ego_frame 计算可能是以 ego 为观察者，看 source→target 方向
但 NuScenes-QA 的问题是 "X to the Y of Z"，可能是从 Z 的视角看 X

如果站在 source (Z) 面向 ego，那么 left/right 会反转
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
    else:
        return 'front-right'

def swap_left_right(direction):
    """互换 left 和 right"""
    return direction.replace('left', 'TEMP').replace('right', 'left').replace('TEMP', 'right')

def calc_direction_global(source, target):
    sx, sy = source['translation']['x'], source['translation']['y']
    tx, ty = target['translation']['x'], target['translation']['y']
    dx = tx - sx
    dy = ty - sy
    angle = math.degrees(math.atan2(dx, dy))
    return angle_to_direction(angle), angle

def calc_direction_ego_frame(source, target, ego):
    sx, sy = source['translation']['x'], source['translation']['y']
    tx, ty = target['translation']['x'], target['translation']['y']
    dx = tx - sx
    dy = ty - sy
    
    global_angle = math.degrees(math.atan2(dx, dy))
    ego_heading = quaternion_to_yaw(ego['rotation'])
    ego_heading_north = normalize_angle(90 - ego_heading)
    relative_angle = normalize_angle(global_angle - ego_heading_north)
    
    return angle_to_direction(relative_angle), relative_angle

ego = nodes['ego']
truck = nodes['truck1']
moto = nodes['motorcycle1']

print("="*80)
print("测试: Object-to-object 使用 ego_frame + left/right 互换")
print("="*80)

results = []

# Q1: truck 在 motorcycle 的什么方向? (期望: back-right)
print("\n[Q1] truck 在 motorcycle 的什么方向? (期望: back-right)")
dir1_orig, angle1 = calc_direction_ego_frame(moto, truck, ego)
dir1_swap = swap_left_right(dir1_orig)
print(f"     原始: {dir1_orig} ({angle1:.1f}°)")
print(f"     互换: {dir1_swap}")
print(f"     {'✓' if dir1_swap == 'back-right' else '✗'}")
results.append(('Q1', 'back-right', dir1_swap, dir1_swap == 'back-right'))

# Q2: truck 在 ego 的什么方向? (期望: front-left) - Ego相关用Global
print("\n[Q2] truck 在 ego 的什么方向? (期望: front-left)")
print("     [Ego相关 → Global，不需互换]")
dir2, angle2 = calc_direction_global(ego, truck)
print(f"     Global: {dir2} ({angle2:.1f}°)")
print(f"     {'✓' if dir2 == 'front-left' else '✗'}")
results.append(('Q2', 'front-left', dir2, dir2 == 'front-left'))

# Q3: pedestrian 在 truck 的 back-right
print("\n[Q3] pedestrian 在 truck 的 back-right? (期望: moving)")
found = []
for n in sg['nodes']:
    if 'pedestrian' not in n['unique_id']:
        continue
    dir_orig, angle = calc_direction_ego_frame(truck, n, ego)
    dir_swap = swap_left_right(dir_orig)
    status = n.get('status', '?')
    if dir_swap == 'back-right':
        found.append(f"{n['unique_id']}({status})")
        print(f"     ✓ {n['unique_id']}({status}): {dir_orig}→{dir_swap} ({angle:.1f}°)")
match3 = len(found) > 0 and any('moving' in f for f in found)
print(f"     {'✓ 找到moving' if match3 else '✗'}")
results.append(('Q3', 'back-right有moving', str(len(found))+'个', match3))

# Q4: bicycle 在 truck 的 front-left
print("\n[Q4] bicycle 在 truck 的 front-left? (期望: without_rider)")
found = []
for n in sg['nodes']:
    if 'bicycle' not in n['unique_id']:
        continue
    dir_orig, angle = calc_direction_ego_frame(truck, n, ego)
    dir_swap = swap_left_right(dir_orig)
    status = n.get('status', '?')
    if dir_swap == 'front-left':
        found.append(f"{n['unique_id']}({status})")
        print(f"     ✓ {n['unique_id']}({status}): {dir_orig}→{dir_swap} ({angle:.1f}°)")
    else:
        print(f"       {n['unique_id']}({status}): {dir_orig}→{dir_swap} ({angle:.1f}°)")
match4 = any('without_rider' in f for f in found)
print(f"     {'✓ 找到without_rider' if match4 else '✗'}")
results.append(('Q4', 'front-left有without_rider', str(len(found))+'个', match4))

# Q5: car 在 motorcycle 的 back
print("\n[Q5] car 在 motorcycle 的 back? (期望: stopped)")
found = []
for n in sg['nodes']:
    if n['type'] != 'car':
        continue
    dir_orig, angle = calc_direction_ego_frame(moto, n, ego)
    dir_swap = swap_left_right(dir_orig)
    status = n.get('status', '?')
    if dir_swap == 'back':  # back 不含 left/right，不变
        found.append(f"{n['unique_id']}({status})")
        print(f"     ✓ {n['unique_id']}({status}): {angle:.1f}°")
match5 = len(found) > 0
print(f"     {'✓ 找到' + str(len(found)) + '个' if match5 else '✗'}")
results.append(('Q5', 'back有car', str(len(found))+'个', match5))

# 总结
print("\n" + "="*80)
print("总结")
print("="*80)
matched = sum(1 for r in results if r[3])
print(f"匹配率: {matched}/{len(results)} = {matched/len(results)*100:.0f}%")
for q, expected, actual, match in results:
    print(f"  {'✓' if match else '✗'} {q}: 期望={expected}, 实际={actual}")
