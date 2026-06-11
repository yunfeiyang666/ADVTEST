"""
详细调试 ego frame 方向计算
"""
import numpy as np
import math

def quaternion_to_yaw(q):
    """从四元数提取yaw角"""
    w, x, y, z = q
    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return yaw

def calculate_relative_position_in_ego_frame(obj1_trans, obj2_trans, ego_rotation):
    """
    复现 regenerate_scene103_frame38_ego_frame.py 的计算逻辑
    """
    # 全局相对位置
    rel_x_global = obj2_trans[0] - obj1_trans[0]
    rel_y_global = obj2_trans[1] - obj1_trans[1]
    rel_z_global = obj2_trans[2] - obj1_trans[2]
    
    # Ego yaw
    ego_yaw = quaternion_to_yaw(ego_rotation)
    
    # 转换到ego坐标系
    cos_yaw = np.cos(-ego_yaw)
    sin_yaw = np.sin(-ego_yaw)
    
    rel_x_ego = cos_yaw * rel_x_global - sin_yaw * rel_y_global
    rel_y_ego = sin_yaw * rel_x_global + cos_yaw * rel_y_global
    rel_z_ego = rel_z_global
    
    # 角度（前方为0度）
    angle = np.arctan2(rel_y_ego, rel_x_ego) * 180 / np.pi
    
    return [rel_x_ego, rel_y_ego, rel_z_ego], angle

def get_direction_predicate(angle):
    """方位判断"""
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
    else:
        return 'front-right'

# 实际数据（来自场景图JSON）
ego_trans = (688.33, 1575.98, 0.0)
ego_rot = [-0.9369, -0.01, 0.0059, 0.3493]  # 注意：这个顺序可能有问题

truck1_trans = (695.26, 1581.75, 1.17)
truck1_rot = [0.3624, 0.0, 0.0, 0.932]

ped7_trans = (640.31, 1606.25, 1.26)
ped8_trans = (639.03, 1609.72, 0.98)

print("=== 数据 ===")
print(f"Ego 位置: {ego_trans}")
print(f"Ego 朝向(四元数): {ego_rot}")
ego_yaw = quaternion_to_yaw(ego_rot)
print(f"Ego yaw: {ego_yaw * 180 / np.pi:.1f}°")
print()
print(f"Truck1 位置: {truck1_trans}")
print(f"Ped7 位置: {ped7_trans}")
print(f"Ped8 位置: {ped8_trans}")

print("\n=== truck1 -> ped7 关系（使用ego frame）===")
rel_pos, angle = calculate_relative_position_in_ego_frame(truck1_trans, ped7_trans, ego_rot)
direction = get_direction_predicate(angle)
print(f"全局相对位置: dx={ped7_trans[0]-truck1_trans[0]:.2f}, dy={ped7_trans[1]-truck1_trans[1]:.2f}")
print(f"ego frame 相对位置: x={rel_pos[0]:.2f}, y={rel_pos[1]:.2f}")
print(f"角度: {angle:.1f}°")
print(f"方向: {direction}")
print(f"场景图中的值: direction_8='front', angle=18.5")

print("\n=== truck1 -> ped8 关系（使用ego frame）===")
rel_pos, angle = calculate_relative_position_in_ego_frame(truck1_trans, ped8_trans, ego_rot)
direction = get_direction_predicate(angle)
print(f"全局相对位置: dx={ped8_trans[0]-truck1_trans[0]:.2f}, dy={ped8_trans[1]-truck1_trans[1]:.2f}")
print(f"ego frame 相对位置: x={rel_pos[0]:.2f}, y={rel_pos[1]:.2f}")
print(f"角度: {angle:.1f}°")
print(f"方向: {direction}")
print(f"场景图中的值: direction_8='front', angle=16.0")

print("\n=== 检查四元数顺序 ===")
print("NuScenes四元数格式通常是 [w, x, y, z]")
print("但场景图JSON中存储的顺序是什么？")

# 尝试不同的四元数解释
print("\n=== 测试四元数顺序 ===")
# 假设JSON中是 [w, x, y, z]
ego_wxyz = ego_rot  # [-0.9369, -0.01, 0.0059, 0.3493]
print(f"如果 [w,x,y,z]={ego_wxyz}: yaw = {quaternion_to_yaw(ego_wxyz)*180/np.pi:.1f}°")

# 假设JSON中是 [x, y, z, w]
ego_xyzw = [ego_rot[3], ego_rot[0], ego_rot[1], ego_rot[2]]  # [0.3493, -0.9369, -0.01, 0.0059]
print(f"如果 [x,y,z,w]->[w,x,y,z]={ego_xyzw}: yaw = {quaternion_to_yaw(ego_xyzw)*180/np.pi:.1f}°")

print("\n=== 检查场景图JSON中边的angle值 ===")
print("truck1->ped7: angle=18.5° (JSON中)")
print("truck1->ped8: angle=16.0° (JSON中)")
print("这个角度值是怎么来的？")
