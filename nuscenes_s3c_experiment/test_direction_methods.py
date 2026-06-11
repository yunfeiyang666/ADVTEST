"""
测试方位计算方法
对比：坐标差向量方法 vs 基于source对象朝向的方法
"""
import numpy as np
import math

def quaternion_to_yaw(quaternion):
    """从四元数提取yaw角"""
    if len(quaternion) == 4:
        w, x, y, z = quaternion
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        return yaw
    return 0.0

def method1_coordinate_based(source_pos, target_pos):
    """
    方法1: 基于坐标差的方位（当前scene graph使用的错误方法）
    """
    rel_x = target_pos[0] - source_pos[0]
    rel_y = target_pos[1] - source_pos[1]
    
    # 直接计算角度（全局坐标系）
    angle = math.atan2(rel_y, rel_x) * 180 / math.pi
    return angle

def method2_orientation_based(source_pos, source_rotation, target_pos):
    """
    方法2: 基于source对象朝向的方位（正确方法）
    """
    # 计算目标相对于source的全局坐标差
    rel_x_global = target_pos[0] - source_pos[0]
    rel_y_global = target_pos[1] - source_pos[1]
    
    # 提取source的yaw角（朝向）
    source_yaw = quaternion_to_yaw(source_rotation)
    
    # 转换到source的局部坐标系
    cos_yaw = math.cos(-source_yaw)
    sin_yaw = math.sin(-source_yaw)
    
    rel_x_local = cos_yaw * rel_x_global - sin_yaw * rel_y_global
    rel_y_local = sin_yaw * rel_x_global + cos_yaw * rel_y_global
    
    # 在局部坐标系中计算角度
    angle = math.atan2(rel_y_local, rel_x_local) * 180 / math.pi
    return angle

def get_direction_from_angle(angle):
    """根据角度判断8方位"""
    # 归一化到[-180, 180]
    angle = ((angle + 180) % 360) - 180
    
    if -22.5 <= angle < 22.5:
        return 'front', angle
    elif 22.5 <= angle < 67.5:
        return 'front-left', angle
    elif 67.5 <= angle < 112.5:
        return 'left', angle
    elif 112.5 <= angle < 157.5:
        return 'back-left', angle
    elif angle >= 157.5 or angle < -157.5:
        return 'back', angle
    elif -157.5 <= angle < -112.5:
        return 'back-right', angle
    elif -112.5 <= angle < -67.5:
        return 'right', angle
    else:  # -67.5 <= angle < -22.5
        return 'front-right', angle

# Scene-0103 frame 38 的真实数据
ego_pos = [688.33, 1575.98, 0.0]
ego_rotation = [-0.9369, -0.01, 0.0059, 0.3493]

car1_pos = [674.87, 1564.0, 1.42]  # stopped/parked
car1_rotation = [0.3244, 0.0, 0.0, 0.9459]

car2_pos = [708.63, 1551.13, 0.98]  # stopped/parked
car2_rotation = [0.9372, 0.0, 0.0, -0.3488]

pedestrian1_pos = [709.22, 1573.98, 0.79]  # moving
pedestrian1_rotation = [0.9375, 0.0, 0.0, -0.3481]

print("=" * 80)
print("Scene-0103 Frame 38 方位计算对比")
print("=" * 80)
print()

# 测试1: ego -> car1
print("【测试1】ego -> car1 (stopped车)")
print("-" * 80)
angle1 = method1_coordinate_based(ego_pos, car1_pos)
dir1, angle1 = get_direction_from_angle(angle1)
print(f"方法1 (坐标差): {dir1:12s} ({angle1:6.1f}°)")

angle2 = method2_orientation_based(ego_pos, ego_rotation, car1_pos)
dir2, angle2 = get_direction_from_angle(angle2)
print(f"方法2 (朝向基): {dir2:12s} ({angle2:6.1f}°)")
print()

# 计算ego的实际朝向
ego_yaw = quaternion_to_yaw(ego_rotation)
ego_yaw_deg = math.degrees(ego_yaw)
print(f"Ego朝向: {ego_yaw_deg:.1f}° (全局坐标系)")
print(f"坐标差: dx={car1_pos[0]-ego_pos[0]:.2f}, dy={car1_pos[1]-ego_pos[1]:.2f}")
print()

# 测试2: ego -> car2
print("【测试2】ego -> car2 (stopped车)")
print("-" * 80)
angle1 = method1_coordinate_based(ego_pos, car2_pos)
dir1, angle1 = get_direction_from_angle(angle1)
print(f"方法1 (坐标差): {dir1:12s} ({angle1:6.1f}°)")

angle2 = method2_orientation_based(ego_pos, ego_rotation, car2_pos)
dir2, angle2 = get_direction_from_angle(angle2)
print(f"方法2 (朝向基): {dir2:12s} ({angle2:6.1f}°)")
print()

# 测试3: ego -> pedestrian1
print("【测试3】ego -> pedestrian1 (moving)")
print("-" * 80)
angle1 = method1_coordinate_based(ego_pos, pedestrian1_pos)
dir1, angle1 = get_direction_from_angle(angle1)
print(f"方法1 (坐标差): {dir1:12s} ({angle1:6.1f}°)")

angle2 = method2_orientation_based(ego_pos, ego_rotation, pedestrian1_pos)
dir2, angle2 = get_direction_from_angle(angle2)
print(f"方法2 (朝向基): {dir2:12s} ({angle2:6.1f}°)")
print()

# 测试4: car1 -> ego (反向关系，测试非ego对象的方位)
print("【测试4】car1 -> ego (测试非ego对象的source)")
print("-" * 80)
angle1 = method1_coordinate_based(car1_pos, ego_pos)
dir1, angle1 = get_direction_from_angle(angle1)
print(f"方法1 (坐标差): {dir1:12s} ({angle1:6.1f}°)")

angle2 = method2_orientation_based(car1_pos, car1_rotation, ego_pos)
dir2, angle2 = get_direction_from_angle(angle2)
print(f"方法2 (朝向基): {dir2:12s} ({angle2:6.1f}°)")
print()

car1_yaw = quaternion_to_yaw(car1_rotation)
car1_yaw_deg = math.degrees(car1_yaw)
print(f"Car1朝向: {car1_yaw_deg:.1f}° (全局坐标系)")
print()

print("=" * 80)
print("结论:")
print("如果两种方法的结果有显著差异，说明:")
print("1. 当前scene graph使用的是方法1（坐标差），不考虑对象朝向")
print("2. 应该使用方法2（朝向基），这样才能正确反映'在我前方/后方'的概念")
print("3. 静止对象也有朝向，应该被使用！")
print("=" * 80)
