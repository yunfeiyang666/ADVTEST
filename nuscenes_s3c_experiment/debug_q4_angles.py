"""详细分析Q4方向计算"""
import json
import math

# 加载场景图
sg = json.load(open('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json', encoding='utf-8'))

# 获取位置
ego = truck = moto = None
for n in sg['nodes']:
    if n['unique_id'] == 'ego':
        ego = n
    if n['unique_id'] == 'truck1':
        truck = n
    if n['unique_id'] == 'motorcycle1':
        moto = n

print('=== 坐标 (全局坐标系) ===')
print(f"ego: ({ego['translation']['x']:.2f}, {ego['translation']['y']:.2f})")
print(f"motorcycle1: ({moto['translation']['x']:.2f}, {moto['translation']['y']:.2f})")
print(f"truck1: ({truck['translation']['x']:.2f}, {truck['translation']['y']:.2f})")

# 计算全局方向(map coordinates)
dx_moto_truck = truck['translation']['x'] - moto['translation']['x']
dy_moto_truck = truck['translation']['y'] - moto['translation']['y']
angle_moto_truck_global = math.degrees(math.atan2(dy_moto_truck, dx_moto_truck))

dx_ego_truck = truck['translation']['x'] - ego['translation']['x']
dy_ego_truck = truck['translation']['y'] - ego['translation']['y']
angle_ego_truck_global = math.degrees(math.atan2(dy_ego_truck, dx_ego_truck))

print()
print('=== 全局角度 (atan2) ===')
print(f'moto->truck 全局角度: {angle_moto_truck_global:.1f}°')
print(f'ego->truck 全局角度: {angle_ego_truck_global:.1f}°')

# ego heading
def quaternion_to_yaw(q):
    w, x, y, z = q[0], q[1], q[2], q[3]
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return math.degrees(yaw)

ego_heading = quaternion_to_yaw(ego['rotation'])
moto_heading = quaternion_to_yaw(moto['rotation'])
truck_heading = quaternion_to_yaw(truck['rotation'])

print()
print('=== 朝向 ===')
print(f'ego heading: {ego_heading:.1f}°')
print(f'moto heading: {moto_heading:.1f}°')
print(f'truck heading: {truck_heading:.1f}°')

# 相对ego frame的角度
rel_ego_truck = angle_ego_truck_global - ego_heading
rel_moto_truck = angle_moto_truck_global - ego_heading

print()
print('=== 相对ego frame的角度 ===')
print(f'ego->truck (ego frame): {rel_ego_truck:.1f}°')
print(f'moto->truck (ego frame): {rel_moto_truck:.1f}°')

# 相对source frame的角度
rel_moto_truck_src = angle_moto_truck_global - moto_heading
print()
print('=== 相对source frame的角度 ===')
print(f'moto->truck (moto frame): {rel_moto_truck_src:.1f}°')

# 方向映射
def angle_to_direction(angle):
    # 标准化到-180~180
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    
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

print()
print('=== 方向映射 ===')
print(f'ego->truck ego frame: {rel_ego_truck:.1f}° -> {angle_to_direction(rel_ego_truck)}')
print(f'moto->truck ego frame: {rel_moto_truck:.1f}° -> {angle_to_direction(rel_moto_truck)}')
print(f'moto->truck moto frame: {rel_moto_truck_src:.1f}° -> {angle_to_direction(rel_moto_truck_src)}')

print()
print('=== QA期望 ===')
print('ego->truck: front-left')
print('moto->truck: back-right')
