"""
比较 step2 中的方向计算方法和我们验证过的方法
"""
import json
import numpy as np

sg = json.load(open('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json'))
nodes = {n['unique_id']: n for n in sg['nodes']}

def quaternion_to_yaw(quaternion):
    """和 step2 中完全一样的函数"""
    if len(quaternion) == 4:
        w, x, y, z = quaternion
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = np.arctan2(siny_cosp, cosy_cosp)
        return yaw
    return 0.0

def calculate_relative_position_in_ego_frame_old(obj1_translation, obj2_translation, ego_rotation):
    """原来的step2方法(有左右颠倒问题)"""
    rel_x_global = obj2_translation[0] - obj1_translation[0]
    rel_y_global = obj2_translation[1] - obj1_translation[1]
    rel_z_global = obj2_translation[2] - obj1_translation[2]
    
    ego_yaw = quaternion_to_yaw(ego_rotation)
    
    cos_yaw = np.cos(-ego_yaw)
    sin_yaw = np.sin(-ego_yaw)
    
    rel_x_ego = cos_yaw * rel_x_global - sin_yaw * rel_y_global
    rel_y_ego = sin_yaw * rel_x_global + cos_yaw * rel_y_global
    rel_z_ego = rel_z_global
    
    angle = np.arctan2(rel_y_ego, rel_x_ego) * 180 / np.pi
    
    return [rel_x_ego, rel_y_ego, rel_z_ego], angle

def calculate_relative_position_in_ego_frame(obj1_translation, obj2_translation, ego_rotation):
    """修正后的step2方法"""
    rel_x_global = obj2_translation[0] - obj1_translation[0]
    rel_y_global = obj2_translation[1] - obj1_translation[1]
    rel_z_global = obj2_translation[2] - obj1_translation[2]
    
    ego_yaw = quaternion_to_yaw(ego_rotation)
    
    cos_yaw = np.cos(-ego_yaw)
    sin_yaw = np.sin(-ego_yaw)
    
    rel_x_ego = cos_yaw * rel_x_global - sin_yaw * rel_y_global
    rel_y_ego = sin_yaw * rel_x_global + cos_yaw * rel_y_global
    rel_z_ego = rel_z_global
    
    # 修正后的角度计算
    global_angle = np.arctan2(rel_x_global, rel_y_global) * 180 / np.pi  # 北=0, 东=90
    ego_yaw_deg = ego_yaw * 180 / np.pi
    ego_heading_north = normalize_angle(90 - ego_yaw_deg)
    angle = normalize_angle(global_angle - ego_heading_north)
    
    return [rel_x_ego, rel_y_ego, rel_z_ego], angle

def get_direction_predicate(angle):
    """和 step2 中完全一样的函数"""
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
    else:  # -67.5 <= angle < -22.5
        return 'front-right'

def normalize_angle(angle):
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle

def calc_direction_ego_frame_v2(source, target, ego):
    """我们验证过的方法 (verify_source_frame.py)"""
    sx, sy = source['translation']['x'], source['translation']['y']
    tx, ty = target['translation']['x'], target['translation']['y']
    dx = tx - sx
    dy = ty - sy
    
    global_angle = np.degrees(np.arctan2(dx, dy))
    ego_heading_deg = np.degrees(quaternion_to_yaw(ego['rotation']))
    ego_heading_north = normalize_angle(90 - ego_heading_deg)
    relative_angle = normalize_angle(global_angle - ego_heading_north)
    
    return get_direction_predicate(relative_angle), relative_angle

# 获取数据
ego = nodes['ego']
truck = nodes['truck1']
moto = nodes['motorcycle1']

ego_rotation = ego['rotation']
ego_trans = [ego['translation']['x'], ego['translation']['y'], ego['translation'].get('z', 0)]
truck_trans = [truck['translation']['x'], truck['translation']['y'], truck['translation'].get('z', 0)]
moto_trans = [moto['translation']['x'], moto['translation']['y'], moto['translation'].get('z', 0)]

print("="*80)
print("比较 step2 方法 vs 验证方法")
print("="*80)

ego_yaw_rad = quaternion_to_yaw(ego_rotation)
ego_yaw_deg = np.degrees(ego_yaw_rad)
print(f"\nego yaw: {ego_yaw_deg:.1f}° (东=0)")
print(f"ego heading (北=0): {normalize_angle(90 - ego_yaw_deg):.1f}°")

# 测试 Q1: moto -> truck
print("\n" + "-"*40)
print("Q1: moto -> truck (期望: back-right)")
print("-"*40)

# step2 方法
rel_pos, angle_step2 = calculate_relative_position_in_ego_frame(moto_trans, truck_trans, ego_rotation)
dir_step2 = get_direction_predicate(angle_step2)
print(f"  step2方法: {dir_step2} ({angle_step2:.1f}°)")
print(f"    rel_pos in ego frame: ({rel_pos[0]:.1f}, {rel_pos[1]:.1f})")

# 验证方法
dir_v2, angle_v2 = calc_direction_ego_frame_v2(moto, truck, ego)
print(f"  验证方法: {dir_v2} ({angle_v2:.1f}°)")

# 测试 Q4: truck -> bicycle1
print("\n" + "-"*40)
print("Q4: truck -> bicycle1 (期望: front-left)")
print("-"*40)

bicycle1 = nodes['bicycle1']
bicycle1_trans = [bicycle1['translation']['x'], bicycle1['translation']['y'], bicycle1['translation'].get('z', 0)]

# step2 方法
rel_pos, angle_step2 = calculate_relative_position_in_ego_frame(truck_trans, bicycle1_trans, ego_rotation)
dir_step2 = get_direction_predicate(angle_step2)
print(f"  step2方法: {dir_step2} ({angle_step2:.1f}°)")
print(f"    rel_pos in ego frame: ({rel_pos[0]:.1f}, {rel_pos[1]:.1f})")

# 验证方法
dir_v2, angle_v2 = calc_direction_ego_frame_v2(truck, bicycle1, ego)
print(f"  验证方法: {dir_v2} ({angle_v2:.1f}°)")

# 测试 Q2: ego -> truck
print("\n" + "-"*40)
print("Q2: ego -> truck (期望: front-left)")
print("-"*40)

# step2 方法
rel_pos, angle_step2 = calculate_relative_position_in_ego_frame(ego_trans, truck_trans, ego_rotation)
dir_step2 = get_direction_predicate(angle_step2)
print(f"  step2方法: {dir_step2} ({angle_step2:.1f}°)")
print(f"    rel_pos in ego frame: ({rel_pos[0]:.1f}, {rel_pos[1]:.1f})")

# 验证方法
dir_v2, angle_v2 = calc_direction_ego_frame_v2(ego, truck, ego)
print(f"  验证方法: {dir_v2} ({angle_v2:.1f}°)")

# Global方法
dx = truck_trans[0] - ego_trans[0]
dy = truck_trans[1] - ego_trans[1]
global_angle = np.degrees(np.arctan2(dx, dy))
print(f"  Global方法: {get_direction_predicate(global_angle)} ({global_angle:.1f}°)")

print("\n" + "="*80)
print("分析")
print("="*80)
print("""
step2方法的特点:
1. 使用 ego_yaw 将全局坐标旋转到 ego 坐标系
2. 然后用 atan2(y_ego, x_ego) 计算角度
3. x_ego 是 ego 的前向，y_ego 是 ego 的左侧

验证方法的特点:
1. 用 atan2(dx, dy) 计算全局角度 (北=0)
2. 然后减去 ego_heading_north (ego朝向转到北基准)

两者本质应该是等价的，但符号可能不同。
""")

# 检查两种方法的角度差异
print("角度差异检查:")
rel_pos, angle_s2 = calculate_relative_position_in_ego_frame(moto_trans, truck_trans, ego_rotation)
_, angle_v2 = calc_direction_ego_frame_v2(moto, truck, ego)
print(f"  moto->truck: step2={angle_s2:.1f}°, v2={angle_v2:.1f}°, diff={abs(angle_s2-angle_v2):.1f}°")

rel_pos, angle_s2 = calculate_relative_position_in_ego_frame(truck_trans, bicycle1_trans, ego_rotation)
_, angle_v2 = calc_direction_ego_frame_v2(truck, bicycle1, ego)
print(f"  truck->bike: step2={angle_s2:.1f}°, v2={angle_v2:.1f}°, diff={abs(angle_s2-angle_v2):.1f}°")
