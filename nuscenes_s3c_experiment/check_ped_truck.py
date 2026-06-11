"""详细检查所有pedestrian相对于truck的位置"""
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

ego = nodes['ego']
truck = nodes['truck1']

ego_heading = quaternion_to_yaw(ego['rotation'])  # -40.9
truck_heading = quaternion_to_yaw(truck['rotation'])  # 137.5

print("="*80)
print("基本信息")
print("="*80)
print(f"ego: pos=({ego['translation']['x']:.1f}, {ego['translation']['y']:.1f}), heading={ego_heading:.1f}° (东=0)")
print(f"truck: pos=({truck['translation']['x']:.1f}, {truck['translation']['y']:.1f}), heading={truck_heading:.1f}° (东=0)")

# 计算各种参考方向
ego_heading_north = normalize_angle(90 - ego_heading)  # ~131
truck_heading_north = normalize_angle(90 - truck_heading)  # ~-47.5

print(f"\nego朝向(北=0基准): {ego_heading_north:.1f}°")
print(f"truck朝向(北=0基准): {truck_heading_north:.1f}°")

print("\n" + "="*80)
print("所有pedestrian相对于truck的位置")
print("="*80)

tx, ty = truck['translation']['x'], truck['translation']['y']

print(f"\n{'ID':<15} {'位置':<25} {'dx,dy':<20} {'Global°':<12} {'EgoFrame°':<12} {'TruckFrame°':<12}")
print("-"*100)

for n in sg['nodes']:
    if 'pedestrian' not in n['unique_id']:
        continue
    
    px, py = n['translation']['x'], n['translation']['y']
    dx = px - tx
    dy = py - ty
    dist = math.sqrt(dx*dx + dy*dy)
    
    # 全局角度 (北=0, 顺时针为正)
    # atan2(dx,dy) 给出北=0的角度
    global_angle = math.degrees(math.atan2(dx, dy))
    
    # Ego frame: 相对于ego车朝向
    ego_frame_angle = normalize_angle(global_angle - ego_heading_north)
    
    # Truck frame: 相对于truck朝向
    truck_frame_angle = normalize_angle(global_angle - truck_heading_north)
    
    print(f"{n['unique_id']:<15} ({px:.1f},{py:.1f}) d={dist:.1f}m {f'({dx:.1f},{dy:.1f})':<20} {global_angle:>8.1f}° {ego_frame_angle:>10.1f}° {truck_frame_angle:>10.1f}°")

print("\n" + "="*80)
print("方向定义 (以0°为front)")
print("="*80)
print("front:       -22.5° ~ 22.5°")
print("front-left:   22.5° ~ 67.5°")
print("left:         67.5° ~ 112.5°")
print("back-left:   112.5° ~ 157.5°")
print("back:        157.5° ~ -157.5° (或 157.5° ~ 180° + -180° ~ -157.5°)")
print("back-right: -157.5° ~ -112.5°")
print("right:      -112.5° ~ -67.5°")
print("front-right: -67.5° ~ -22.5°")

print("\n" + "="*80)
print("分析: 哪个pedestrian在truck的back-right?")
print("="*80)
print("back-right 需要角度在 -157.5° ~ -112.5° 范围内")
print()

# 检查每个坐标系
for method, angles in [
    ("Global", []),
    ("Ego frame", []),
    ("Truck frame", [])
]:
    print(f"\n{method}:")
    found = False
    for n in sg['nodes']:
        if 'pedestrian' not in n['unique_id']:
            continue
        
        px, py = n['translation']['x'], n['translation']['y']
        dx = px - tx
        dy = py - ty
        
        global_angle = math.degrees(math.atan2(dx, dy))
        ego_frame_angle = normalize_angle(global_angle - ego_heading_north)
        truck_frame_angle = normalize_angle(global_angle - truck_heading_north)
        
        if method == "Global":
            angle = global_angle
        elif method == "Ego frame":
            angle = ego_frame_angle
        else:
            angle = truck_frame_angle
        
        # back-right: -157.5 ~ -112.5
        if -157.5 <= angle < -112.5:
            print(f"  {n['unique_id']}: {angle:.1f}° -> back-right ✓")
            found = True
    
    if not found:
        print("  没有找到任何pedestrian在back-right方向")

# 额外测试：尝试另一种可能的坐标系统
print("\n" + "="*80)
print("额外测试: 检查是否使用了不同的角度定义")
print("="*80)

# 可能NuScenes-QA使用的是 (东=0, 北=90, 逆时针) 或其他系统
print("\n尝试: 以ego视角, 使用不同的前向定义...")
print("假设: front = ego的行驶方向, right = ego的右手边")
print()

for n in sg['nodes']:
    if 'pedestrian' not in n['unique_id']:
        continue
    
    px, py = n['translation']['x'], n['translation']['y']
    
    # 从truck到pedestrian的向量
    dx = px - tx
    dy = py - ty
    
    # ego的前向向量 (heading=-40.9° 东=0基准)
    # 在NuScenes中，heading是逆时针为正，从东轴开始
    ego_front_x = math.cos(math.radians(ego_heading))
    ego_front_y = math.sin(math.radians(ego_heading))
    
    # ego的右向向量 (前向顺时针旋转90°)
    ego_right_x = math.cos(math.radians(ego_heading - 90))
    ego_right_y = math.sin(math.radians(ego_heading - 90))
    
    # 将truck→pedestrian向量投影到ego的坐标系
    forward_comp = dx * ego_front_x + dy * ego_front_y
    right_comp = dx * ego_right_x + dy * ego_right_y
    
    # 计算角度 (前=0, 右为负, 左为正)
    angle_in_ego = math.degrees(math.atan2(-right_comp, forward_comp))
    
    print(f"{n['unique_id']}: forward={forward_comp:.1f}, right={right_comp:.1f}, angle={angle_in_ego:.1f}°")

print("\n" + "="*80)
print("BEV可视化")
print("="*80)
print("(基于全局坐标，北朝上，东朝右)")
print()

# 简单ASCII BEV
# 找出范围
all_x = [n['translation']['x'] for n in sg['nodes']]
all_y = [n['translation']['y'] for n in sg['nodes']]
min_x, max_x = min(all_x) - 5, max(all_x) + 5
min_y, max_y = min(all_y) - 5, max(all_y) + 5

# 只打印truck和pedestrians的相对位置
print(f"Truck (T): ({tx:.1f}, {ty:.1f})")
print(f"Ego (E): ({ego['translation']['x']:.1f}, {ego['translation']['y']:.1f})")
print()
print("Pedestrians relative to truck:")
for n in sg['nodes']:
    if 'pedestrian' not in n['unique_id']:
        continue
    px, py = n['translation']['x'], n['translation']['y']
    dx = px - tx
    dy = py - ty
    print(f"  {n['unique_id']}: dx={dx:+.1f}, dy={dy:+.1f} (相对于truck)")
