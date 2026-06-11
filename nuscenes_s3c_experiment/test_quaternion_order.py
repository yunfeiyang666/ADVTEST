"""
测试 pyquaternion 的四元数顺序
找出为什么角度相差180°
"""
import math

# JSON中存储的ego rotation
json_ego_rot = [-0.9369, -0.01, 0.0059, 0.3493]

print("=== 测试不同的四元数顺序解释 ===\n")

# 方法1: 假设是 [w, x, y, z]
print("方法1: 假设 JSON 存储顺序是 [w, x, y, z]")
w, x, y, z = json_ego_rot
yaw1 = math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
print(f"  w={w}, x={x}, y={y}, z={z}")
print(f"  yaw = {math.degrees(yaw1):.1f}°")

# 方法2: 假设是 [x, y, z, w]
print("\n方法2: 假设 JSON 存储顺序是 [x, y, z, w]")
x, y, z, w = json_ego_rot
yaw2 = math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
print(f"  x={x}, y={y}, z={z}, w={w}")
print(f"  yaw = {math.degrees(yaw2):.1f}°")

# 方法3: 尝试取反
print("\n方法3: yaw 取反")
print(f"  yaw1 取反 = {-math.degrees(yaw1):.1f}°")
print(f"  yaw2 取反 = {-math.degrees(yaw2):.1f}°")

print("\n=== 验证：从已知数据反推 ===")
print("已知: ego->ped5 在场景图中angle=-139.6°, direction_8=back-right")
print("ped5相对ego的全局方向约为 180° (在ego正左方)")
print()
print("ego_frame_angle = global_angle - ego_yaw")
print("-139.6 = 180 - ego_yaw")
print("ego_yaw 应该约= 180 - (-139.6) = 319.6° 或等价于 -40.4°")
print()
print(f"方法1得到的 yaw = {math.degrees(yaw1):.1f}° ✅ 接近!")
print(f"方法2得到的 yaw = {math.degrees(yaw2):.1f}°")

print("\n=== 结论 ===")
print("pyquaternion期待 [w,x,y,z]，JSON确实也是这个顺序")
print("yaw计算本身是正确的")
print()
print("那么问题出在哪里？")
print("让我检查 generate_selected_scenes.py 中 translation 的使用...")
