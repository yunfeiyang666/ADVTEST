"""
测试: 全部使用 Global 坐标系 (北=front)
"""
import json
import math

sg = json.load(open('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json'))
nodes = {n['unique_id']: n for n in sg['nodes']}

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

def calc_direction_global(source, target):
    sx, sy = source['translation']['x'], source['translation']['y']
    tx, ty = target['translation']['x'], target['translation']['y']
    dx = tx - sx
    dy = ty - sy
    angle = math.degrees(math.atan2(dx, dy))
    return angle_to_direction(angle), angle

ego = nodes['ego']
truck = nodes['truck1']
moto = nodes['motorcycle1']

print("="*80)
print("测试: 全部使用 Global 坐标系")
print("="*80)

results = []

# Q1: truck 在 motorcycle 的什么方向? (期望: back-right)
print("\n[Q1] truck 在 motorcycle 的什么方向? (期望: back-right)")
dir1, angle1 = calc_direction_global(moto, truck)
print(f"     Global: {dir1} ({angle1:.1f}°)")
print(f"     {'✓' if dir1 == 'back-right' else '✗'}")
results.append(('Q1', 'back-right', dir1, dir1 == 'back-right'))

# Q2: truck 在 ego 的什么方向? (期望: front-left)
print("\n[Q2] truck 在 ego 的什么方向? (期望: front-left)")
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
    dir3, angle3 = calc_direction_global(truck, n)
    status = n.get('status', '?')
    if dir3 == 'back-right':
        found.append(f"{n['unique_id']}({status})")
        print(f"     ✓ {n['unique_id']}({status}): {dir3} ({angle3:.1f}°)")
    else:
        pass  # print(f"       {n['unique_id']}({status}): {dir3} ({angle3:.1f}°)")
match3 = len(found) > 0 and any('moving' in f for f in found)
print(f"     {'✓ 找到moving' if match3 else '✗ 没找到'}")
results.append(('Q3', 'back-right有moving', str(len(found))+'个', match3))

# Q4: bicycle 在 truck 的 front-left
print("\n[Q4] bicycle 在 truck 的 front-left? (期望: without_rider)")
found = []
for n in sg['nodes']:
    if 'bicycle' not in n['unique_id']:
        continue
    dir4, angle4 = calc_direction_global(truck, n)
    status = n.get('status', '?')
    if dir4 == 'front-left':
        found.append(f"{n['unique_id']}({status})")
        print(f"     ✓ {n['unique_id']}({status}): {dir4} ({angle4:.1f}°)")
    else:
        print(f"       {n['unique_id']}({status}): {dir4} ({angle4:.1f}°)")
match4 = any('without_rider' in f for f in found)
print(f"     {'✓ 找到without_rider' if match4 else '✗'}")
results.append(('Q4', 'front-left有without_rider', str(len(found))+'个', match4))

# Q5: car 在 motorcycle 的 back
print("\n[Q5] car 在 motorcycle 的 back? (期望: stopped)")
found = []
for n in sg['nodes']:
    if n['type'] != 'car':
        continue
    dir5, angle5 = calc_direction_global(moto, n)
    status = n.get('status', '?')
    if dir5 == 'back':
        found.append(f"{n['unique_id']}({status})")
        print(f"     ✓ {n['unique_id']}({status}): {angle5:.1f}°")
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
