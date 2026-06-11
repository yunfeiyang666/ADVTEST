"""分析Q8: There is a pedestrian to the back right of the truck"""
import json
import math

sg = json.load(open('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json'))

# 获取对象
truck1 = None
ego = None
pedestrians = []

for n in sg['nodes']:
    if n['unique_id'] == 'truck1':
        truck1 = n
    if n['unique_id'] == 'ego':
        ego = n
    if 'pedestrian' in n['unique_id']:
        pedestrians.append(n)

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

print("=== Q8: pedestrian to the back right of the truck ===")
print(f"期望方向: back-right")
print()

truck_pos = (truck1['translation']['x'], truck1['translation']['y'])
truck_heading = quaternion_to_yaw(truck1['rotation'])
ego_pos = (ego['translation']['x'], ego['translation']['y'])
ego_heading = quaternion_to_yaw(ego['rotation'])

print(f"Truck1: pos={truck_pos}, heading={truck_heading:.1f}°")
print(f"Ego: pos={ego_pos}, heading={ego_heading:.1f}°")
print()

# 计算每个pedestrian相对于truck的方向
print("=== 各pedestrian相对于truck的方向 ===")
for ped in pedestrians:
    ped_pos = (ped['translation']['x'], ped['translation']['y'])
    dx = ped_pos[0] - truck_pos[0]
    dy = ped_pos[1] - truck_pos[1]
    dist = math.sqrt(dx*dx + dy*dy)
    
    # Global (北=0)
    global_angle = math.degrees(math.atan2(dx, dy))
    
    # Ego frame
    ego_heading_north = normalize_angle(90 - ego_heading)
    ego_frame_angle = normalize_angle(global_angle - ego_heading_north)
    
    # Source frame (truck)
    truck_heading_north = normalize_angle(90 - truck_heading)
    source_frame_angle = normalize_angle(global_angle - truck_heading_north)
    
    print(f"{ped['unique_id']}: pos={ped_pos}, dist={dist:.1f}m")
    print(f"  global:       {angle_to_direction(global_angle)} ({global_angle:.1f}°)")
    print(f"  ego_frame:    {angle_to_direction(ego_frame_angle)} ({ego_frame_angle:.1f}°)")
    print(f"  source_frame: {angle_to_direction(source_frame_angle)} ({source_frame_angle:.1f}°)")
    
    # 检查哪个匹配back-right
    matches = []
    if angle_to_direction(global_angle) == 'back-right':
        matches.append('global')
    if angle_to_direction(ego_frame_angle) == 'back-right':
        matches.append('ego_frame')
    if angle_to_direction(source_frame_angle) == 'back-right':
        matches.append('source_frame')
    
    if matches:
        print(f"  >>> 匹配back-right: {matches}")
    print()
