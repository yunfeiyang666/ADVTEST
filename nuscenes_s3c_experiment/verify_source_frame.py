"""验证如果用source frame计算，方向是否匹配"""
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

def calc_direction_source_frame(source, target):
    """用source frame计算方向: 以source朝向为0度"""
    sx, sy = source['translation']['x'], source['translation']['y']
    tx, ty = target['translation']['x'], target['translation']['y']
    
    dx = tx - sx
    dy = ty - sy
    
    # 全局角度 (北=0, 东=90)
    global_angle = math.degrees(math.atan2(dx, dy))
    
    # source朝向 (原始是东=0, 转为北=0)
    source_heading = quaternion_to_yaw(source['rotation'])
    source_heading_north = normalize_angle(90 - source_heading)
    
    # source frame: 相对于source朝向
    relative_angle = normalize_angle(global_angle - source_heading_north)
    
    return angle_to_direction(relative_angle), relative_angle, global_angle, source_heading_north

def calc_direction_ego_frame(source, target, ego):
    """用ego frame计算方向: 以ego朝向为0度"""
    sx, sy = source['translation']['x'], source['translation']['y']
    tx, ty = target['translation']['x'], target['translation']['y']
    
    dx = tx - sx
    dy = ty - sy
    
    # 全局角度 (北=0)
    global_angle = math.degrees(math.atan2(dx, dy))
    
    # ego朝向转为北=0
    ego_heading = quaternion_to_yaw(ego['rotation'])
    ego_heading_north = normalize_angle(90 - ego_heading)
    
    # ego frame
    relative_angle = normalize_angle(global_angle - ego_heading_north)
    
    return angle_to_direction(relative_angle), relative_angle

print("=" * 70)
print("验证不同坐标系下的方向计算")
print("=" * 70)

ego = nodes['ego']
truck1 = nodes['truck1']
moto1 = nodes['motorcycle1']

# 打印基本信息
ego_heading = quaternion_to_yaw(ego['rotation'])
truck_heading = quaternion_to_yaw(truck1['rotation'])
moto_heading = quaternion_to_yaw(moto1['rotation'])

print(f"\nego: pos=({ego['translation']['x']:.1f}, {ego['translation']['y']:.1f}), heading={ego_heading:.1f}°")
print(f"motorcycle1: pos=({moto1['translation']['x']:.1f}, {moto1['translation']['y']:.1f}), heading={moto_heading:.1f}°")
print(f"truck1: pos=({truck1['translation']['x']:.1f}, {truck1['translation']['y']:.1f}), heading={truck_heading:.1f}°")

def calc_direction_global(source, target):
    """用全局坐标计算方向: 不做任何旋转, 北=front, 东=right"""
    sx, sy = source['translation']['x'], source['translation']['y']
    tx, ty = target['translation']['x'], target['translation']['y']
    
    dx = tx - sx
    dy = ty - sy
    
    # 全局角度 (北=0, 东=90)
    global_angle = math.degrees(math.atan2(dx, dy))
    
    return angle_to_direction(global_angle), global_angle

print("\n" + "=" * 70)
print("Q1: truck在motorcycle的什么方向? (期望: back-right)")
print("=" * 70)

dir_ego, angle_ego = calc_direction_ego_frame(moto1, truck1, ego)
dir_src, angle_src, global_ang, src_heading = calc_direction_source_frame(moto1, truck1)
dir_global, global_ang2 = calc_direction_global(moto1, truck1)

print(f"  全局角度: {global_ang:.1f}°")
print(f"  motorcycle朝向(北基准): {src_heading:.1f}°")
print(f"  Global (不旋转): {dir_global} ({global_ang2:.1f}°)")
print(f"  Ego frame: {dir_ego} ({angle_ego:.1f}°)")
print(f"  Source frame (motorcycle): {dir_src} ({angle_src:.1f}°)")
print(f"  期望: back-right")
print(f"  >>> {'Global匹配!' if dir_global == 'back-right' else 'Source frame匹配!' if dir_src == 'back-right' else 'Ego frame匹配!' if dir_ego == 'back-right' else '都不匹配'}")

print("\n" + "=" * 70)
print("Q2: truck在ego的什么方向? (期望: front-left)")
print("=" * 70)

dir_ego, angle_ego = calc_direction_ego_frame(ego, truck1, ego)
dir_src, angle_src, global_ang, src_heading = calc_direction_source_frame(ego, truck1)
dir_global, global_ang2 = calc_direction_global(ego, truck1)

print(f"  全局角度: {global_ang:.1f}°")
print(f"  ego朝向(北基准): {src_heading:.1f}°")
print(f"  Global (不旋转): {dir_global} ({global_ang2:.1f}°)")
print(f"  Ego frame: {dir_ego} ({angle_ego:.1f}°)")
print(f"  期望: front-left")
print(f"  >>> {'Global匹配!' if dir_global == 'front-left' else 'Ego frame匹配!' if dir_ego == 'front-left' else '都不匹配'}")

print("\n" + "=" * 70)
print("Q3: 哪些pedestrian在truck的back-right? (期望: 应该有moving的)")
print("=" * 70)

print(f"  truck朝向: {truck_heading:.1f}° (东=0标准)")
truck_heading_north = normalize_angle(90 - truck_heading)
print(f"  truck朝向(北=0标准): {truck_heading_north:.1f}°")

for n in sg['nodes']:
    if 'pedestrian' in n['unique_id']:
        dir_src, angle_src, global_ang, _ = calc_direction_source_frame(truck1, n)
        dir_ego, angle_ego = calc_direction_ego_frame(truck1, n, ego)
        dir_global, global_ang2 = calc_direction_global(truck1, n)
        
        status = n.get('status', '?')
        print(f"  {n['unique_id']}({status}): global={dir_global}({global_ang2:.1f}°), ego_frame={dir_ego}({angle_ego:.1f}°), source_frame={dir_src}({angle_src:.1f}°)")
        if dir_global == 'back-right':
            print(f"    ^ Global匹配back-right!")
        if dir_ego == 'back-right':
            print(f"    ^ Ego frame匹配back-right!")

print("\n" + "=" * 70)
print("Q4: 哪些bicycle在truck的front-left?")
print("=" * 70)

for n in sg['nodes']:
    if 'bicycle' in n['unique_id']:
        dir_src, angle_src, global_ang, _ = calc_direction_source_frame(truck1, n)
        dir_ego, angle_ego = calc_direction_ego_frame(truck1, n, ego)
        dir_global, global_ang2 = calc_direction_global(truck1, n)
        
        status = n.get('status', '?')
        print(f"  {n['unique_id']}({status}): global={dir_global}({global_ang2:.1f}°), ego_frame={dir_ego}({angle_ego:.1f}°), source_frame={dir_src}({angle_src:.1f}°)")
        if dir_global == 'front-left':
            print(f"    ^ Global匹配front-left!")
        if dir_ego == 'front-left':
            print(f"    ^ Ego frame匹配front-left!")
