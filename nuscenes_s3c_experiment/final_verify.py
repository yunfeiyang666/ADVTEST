"""
最终验证: 使用正确的方向计算方法

结论:
- Ego相关问题: 使用 Global (北=front)
- Object-to-object问题: 使用 ego_frame (以ego北基准朝向为参考)
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
    else:  # -67.5 ~ -22.5
        return 'front-right'

def calc_direction_global(source, target):
    """全局坐标 (北=front, 东=right)"""
    sx, sy = source['translation']['x'], source['translation']['y']
    tx, ty = target['translation']['x'], target['translation']['y']
    dx = tx - sx
    dy = ty - sy
    angle = math.degrees(math.atan2(dx, dy))
    return angle_to_direction(angle), angle

def calc_direction_ego_frame(source, target, ego):
    """
    Ego frame: 相对于ego朝向
    修正后的计算方法：用全局角度(北=0)减去ego朝向
    """
    sx, sy = source['translation']['x'], source['translation']['y']
    tx, ty = target['translation']['x'], target['translation']['y']
    dx = tx - sx
    dy = ty - sy
    
    # 全局角度 (北=0, 东=90)
    global_angle = math.degrees(math.atan2(dx, dy))
    ego_heading = quaternion_to_yaw(ego['rotation'])
    ego_heading_north = normalize_angle(90 - ego_heading)
    relative_angle = normalize_angle(global_angle - ego_heading_north)
    
    return angle_to_direction(relative_angle), relative_angle

ego = nodes['ego']
truck = nodes['truck1']
moto = nodes['motorcycle1']

print("="*80)
print("最终验证 - 混合方法")
print("- Ego相关问题: Global (北=front)")  
print("- Object-to-object: ego_frame (相对于ego北基准朝向)")
print("="*80)

results = []

# Q1: truck 在 motorcycle 的什么方向? (期望: back-right)
# Object-to-object → ego_frame
print("\n[Q1] truck 在 motorcycle 的什么方向? (期望: back-right)")
print("     类型: Object-to-object → 用 ego_frame")
dir1, angle1 = calc_direction_ego_frame(moto, truck, ego)
match1 = dir1 == 'back-right'
print(f"     结果: {dir1} ({angle1:.1f}°)")
print(f"     {'✓ 匹配!' if match1 else '✗ 不匹配'}")
results.append(('Q1', 'back-right', dir1, match1))

# Q2: truck 在 ego 的什么方向? (期望: front-left)
# Ego相关 → Global
print("\n[Q2] truck 在 ego 的什么方向? (期望: front-left)")
print("     类型: Ego相关 → 用 Global")
dir2, angle2 = calc_direction_global(ego, truck)
match2 = dir2 == 'front-left'
print(f"     结果: {dir2} ({angle2:.1f}°)")
print(f"     {'✓ 匹配!' if match2 else '✗ 不匹配'}")
results.append(('Q2', 'front-left', dir2, match2))

# Q3: pedestrian 在 truck 的 back-right (期望: 应有 moving 的)
# Object-to-object → ego_frame
print("\n[Q3] pedestrian 在 truck 的 back-right? (期望: 应有 moving 的)")
print("     类型: Object-to-object → 用 ego_frame")
found_q3 = []
for n in sg['nodes']:
    if 'pedestrian' not in n['unique_id']:
        continue
    dir3, angle3 = calc_direction_ego_frame(truck, n, ego)
    dir3_neg, angle3_neg = angle_to_direction(-angle3), -angle3  # 尝试取反
    status = n.get('status', '?')
    print(f"       {n['unique_id']}({status}): ego_frame={dir3}({angle3:.1f}°), 取反={dir3_neg}({angle3_neg:.1f}°)")
    if dir3 == 'back-right':
        found_q3.append(f"{n['unique_id']}({status})")
match3 = len(found_q3) > 0
print(f"     {'✓ 找到 ' + str(len(found_q3)) + ' 个' if match3 else '✗ 没找到'}")
results.append(('Q3', 'back-right有moving', f'{len(found_q3)}个', match3))

# Q4: bicycle 在 truck 的 front-left (期望: without rider)
# Object-to-object → ego_frame  
print("\n[Q4] bicycle 在 truck 的 front-left? (期望: without rider)")
print("     类型: Object-to-object → 用 ego_frame")
found_q4 = []
for n in sg['nodes']:
    if 'bicycle' not in n['unique_id']:
        continue
    dir4, angle4 = calc_direction_ego_frame(truck, n, ego)
    status = n.get('status', '?')
    if dir4 == 'front-left':
        found_q4.append(f"{n['unique_id']}({status})")
        print(f"     ✓ {n['unique_id']}({status}): {angle4:.1f}°")
    else:
        print(f"       {n['unique_id']}({status}): {dir4} ({angle4:.1f}°)")
match4 = any('without_rider' in x for x in found_q4)
print(f"     {'✓ 找到 without_rider' if match4 else '✗ 没找到 without_rider'}")
results.append(('Q4', 'front-left有without_rider', f'{len(found_q4)}个', match4))

# Q5: car 在 motorcycle 的 back (期望: yes - parked/stopped cars)
# Object-to-object → ego_frame
print("\n[Q5] car 在 motorcycle 的 back? (期望: 应有 parked/stopped)")
print("     类型: Object-to-object → 用 ego_frame")
found_q5 = []
for n in sg['nodes']:
    if n['type'] != 'car':
        continue
    dir5, angle5 = calc_direction_ego_frame(moto, n, ego)
    status = n.get('status', '?')
    if dir5 == 'back':
        found_q5.append(f"{n['unique_id']}({status})")
        print(f"     ✓ {n['unique_id']}({status}): {angle5:.1f}°")
match5 = len(found_q5) > 0
print(f"     {'✓ 找到 ' + str(len(found_q5)) + ' 个' if match5 else '✗ 没找到'}")
results.append(('Q5', 'back有car', f'{len(found_q5)}个', match5))

# 总结
print("\n" + "="*80)
print("总结")
print("="*80)
total = len(results)
matched = sum(1 for r in results if r[3])
print(f"匹配率: {matched}/{total} = {matched/total*100:.0f}%")
print()
for q, expected, actual, match in results:
    status = "✓" if match else "✗"
    print(f"  {status} {q}: 期望={expected}, 实际={actual}")
