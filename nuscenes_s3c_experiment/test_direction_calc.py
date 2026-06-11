"""
测试方向计算逻辑
"""
import numpy as np
import math

def quaternion_to_yaw(q):
    """从四元数提取yaw角（简化版，假设roll/pitch为0）"""
    w, x, y, z = q
    # Simplified yaw extraction
    yaw = math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
    return yaw

def compute_angle(src, tgt, ego_rot):
    """计算从src到tgt相对于ego的角度"""
    rel = np.array(tgt) - np.array(src)
    distance = np.linalg.norm(rel[:2])
    
    # World frame angle
    world_angle = np.arctan2(rel[1], rel[0])
    
    # Ego yaw
    ego_yaw = quaternion_to_yaw(ego_rot)
    
    # Relative angle
    rel_rad = world_angle - ego_yaw
    rel_deg = rel_rad * 180 / np.pi
    angle_deg = ((rel_deg + 180) % 360) - 180
    
    return angle_deg, distance, rel

# Truck1 和 pedestrians
truck1 = (695.26, 1581.75, 1.17)
truck1_rot = [0.3624, 0.0, 0.0, 0.932]  # truck的朝向
ego_rot = [0.932, 0.0, 0.0, 0.3624]  # ego的朝向

ped7 = (640.31, 1606.25, 1.26)
ped8 = (639.03, 1609.72, 0.98)

print("=== 场景图使用的是 EGO 朝向（错误的设计）===")
ang7, d7, rel7 = compute_angle(truck1, ped7, ego_rot)
print(f"truck1->ped7: angle={ang7:.1f}°, dist={d7:.1f}m, rel={rel7}")

ang8, d8, rel8 = compute_angle(truck1, ped8, ego_rot)
print(f"truck1->ped8: angle={ang8:.1f}°, dist={d8:.1f}m, rel={rel8}")

print("\n8方向分区（-22.5~22.5=front, 22.5~67.5=front-left, etc）:")
print(f"  ped7角度 {ang7:.1f}° -> 应该是: ", end="")
if -22.5 <= ang7 < 22.5:
    print("front")
elif 22.5 <= ang7 < 67.5:
    print("front-left")
else:
    print("其他")

print(f"  ped8角度 {ang8:.1f}° -> 应该是: ", end="")
if -22.5 <= ang8 < 22.5:
    print("front")
elif 22.5 <= ang8 < 67.5:
    print("front-left")
else:
    print("其他")

print("\n=== 如果使用 TRUCK1 自己的朝向（正确的设计）===")
ang7_truck, d7_truck, rel7_truck = compute_angle(truck1, ped7, truck1_rot)
print(f"truck1->ped7: angle={ang7_truck:.1f}°, dist={d7_truck:.1f}m")

ang8_truck, d8_truck, rel8_truck = compute_angle(truck1, ped8, truck1_rot)
print(f"truck1->ped8: angle={ang8_truck:.1f}°, dist={d8_truck:.1f}m")

print("\n方向判断:")
def get_dir8(a):
    if -22.5 <= a < 22.5: return "front"
    if 22.5 <= a < 67.5: return "front-left"
    if 67.5 <= a < 112.5: return "left"
    if 112.5 <= a < 157.5: return "back-left"
    if a >= 157.5 or a < -157.5: return "back"
    if -157.5 <= a < -112.5: return "back-right"
    if -112.5 <= a < -67.5: return "right"
    return "front-right"

print(f"  ped7角度 {ang7_truck:.1f}° -> {get_dir8(ang7_truck)}")
print(f"  ped8角度 {ang8_truck:.1f}° -> {get_dir8(ang8_truck)}")

print("\n=== EGO 和 TRUCK1 的朝向差异 ===")
ego_yaw = quaternion_to_yaw(ego_rot)
truck_yaw = quaternion_to_yaw(truck1_rot)
print(f"ego yaw: {ego_yaw*180/np.pi:.1f}°")
print(f"truck yaw: {truck_yaw*180/np.pi:.1f}°")
print(f"差异: {(ego_yaw - truck_yaw)*180/np.pi:.1f}°")
