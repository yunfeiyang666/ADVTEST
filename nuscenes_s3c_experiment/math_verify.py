"""
数学验证 ego frame 方向计算
"""
import math
import numpy as np

# 坐标数据
ego_pos = (688.33, 1575.98)
truck1_pos = (695.26, 1581.75)
ped7_pos = (640.31, 1606.25)
ped8_pos = (639.03, 1609.72)

# ego 的四元数 [-0.9369, -0.01, 0.0059, 0.3493]
# 用简化公式计算 yaw: atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
w, x, y, z = -0.9369, -0.01, 0.0059, 0.3493
ego_yaw = math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
print(f"Ego yaw = {math.degrees(ego_yaw):.1f}°")

# 计算 truck1 -> ped7 的全局角度
dx = ped7_pos[0] - truck1_pos[0]  # -54.95
dy = ped7_pos[1] - truck1_pos[1]  # +24.50
global_angle = math.atan2(dy, dx)  # atan2(y, x)
print(f"\ntruck1 -> ped7:")
print(f"  dx = {dx:.2f}, dy = {dy:.2f}")
print(f"  全局角度 = atan2({dy:.2f}, {dx:.2f}) = {math.degrees(global_angle):.1f}°")

# Ego frame 角度 = 全局角度 - ego_yaw
ego_frame_angle = global_angle - ego_yaw
ego_frame_angle_deg = math.degrees(ego_frame_angle)
# 归一化到 [-180, 180]
while ego_frame_angle_deg > 180:
    ego_frame_angle_deg -= 360
while ego_frame_angle_deg < -180:
    ego_frame_angle_deg += 360
print(f"  Ego frame 角度 = {math.degrees(global_angle):.1f}° - ({math.degrees(ego_yaw):.1f}°) = {ego_frame_angle_deg:.1f}°")

# 判断方向
def get_dir8(a):
    a = ((a + 180) % 360) - 180
    if -22.5 <= a < 22.5: return "front"
    if 22.5 <= a < 67.5: return "front-left"
    if 67.5 <= a < 112.5: return "left"
    if 112.5 <= a < 157.5: return "back-left"
    if a >= 157.5 or a < -157.5: return "back"
    if -157.5 <= a < -112.5: return "back-right"
    if -112.5 <= a < -67.5: return "right"
    return "front-right"

print(f"  方向 = {get_dir8(ego_frame_angle_deg)}")
print(f"  场景图显示: angle=18.5°, direction='front'")

print("\n=== 对比分析 ===")
print(f"计算得到: {ego_frame_angle_deg:.1f}°")
print(f"场景图存储: 18.5°")
print(f"差值: {abs(ego_frame_angle_deg - 18.5):.1f}°")

# 检查是否是坐标轴定义问题
print("\n=== 检查可能的问题 ===")

# 可能1: atan2 参数顺序
global_angle_xy = math.atan2(dx, dy)  # atan2(x, y) 而非 atan2(y, x)
print(f"如果用 atan2(x, y): 全局角度 = {math.degrees(global_angle_xy):.1f}°")
ego_frame_xy = global_angle_xy - ego_yaw
ego_frame_xy_deg = math.degrees(ego_frame_xy)
while ego_frame_xy_deg > 180: ego_frame_xy_deg -= 360
while ego_frame_xy_deg < -180: ego_frame_xy_deg += 360
print(f"  Ego frame 角度 = {ego_frame_xy_deg:.1f}°, 方向 = {get_dir8(ego_frame_xy_deg)}")

# 可能2: ego_yaw 符号或定义不同
print(f"\n如果 ego_yaw 取反: {-math.degrees(ego_yaw):.1f}°")
ego_frame_neg = global_angle + ego_yaw
ego_frame_neg_deg = math.degrees(ego_frame_neg)
while ego_frame_neg_deg > 180: ego_frame_neg_deg -= 360
while ego_frame_neg_deg < -180: ego_frame_neg_deg += 360
print(f"  Ego frame 角度 = {ego_frame_neg_deg:.1f}°, 方向 = {get_dir8(ego_frame_neg_deg)}")

# 验证 ego -> ped5 来确定正确的计算方式
print("\n=== 用 ego->ped5 验证（场景图显示 back-right, -139.6°）===")
ped5_pos = (675.53, 1576.10)
dx5 = ped5_pos[0] - ego_pos[0]
dy5 = ped5_pos[1] - ego_pos[1]
global_angle_5 = math.atan2(dy5, dx5)
print(f"ego -> ped5: dx={dx5:.2f}, dy={dy5:.2f}")
print(f"  全局角度 (atan2(y,x)) = {math.degrees(global_angle_5):.1f}°")

# 用这个来反推 ego_yaw 应该是多少
# ego_frame_angle = global_angle - ego_yaw = -139.6
# ego_yaw = global_angle - (-139.6) = global_angle + 139.6
expected_ego_yaw = global_angle_5 - math.radians(-139.6)
print(f"  要得到 -139.6°, ego_yaw 应该 = {math.degrees(expected_ego_yaw):.1f}°")
print(f"  实际 ego_yaw = {math.degrees(ego_yaw):.1f}°")
