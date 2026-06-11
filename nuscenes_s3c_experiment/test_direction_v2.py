"""
测试三套方位系统（不依赖 pyquaternion）
"""

def normalize_angle(angle_deg):
    a = float(angle_deg)
    while a > 180:
        a -= 360
    while a <= -180:
        a += 360
    return a

def check_direction_2way(angle_deg, direction):
    """2方位系统（前/后各180°）"""
    a = normalize_angle(angle_deg)
    if direction == 'front':
        return -90 <= a < 90
    elif direction == 'back':
        return a >= 90 or a < -90
    elif direction == 'left':
        return 0 <= a < 180
    elif direction == 'right':
        return -180 <= a < 0
    return False

def check_direction_4way(angle_deg, direction):
    """4方位系统（前左/前右/后左/后右各90°）"""
    a = normalize_angle(angle_deg)
    if direction == 'front-left':
        return 0 <= a < 90
    elif direction == 'back-left':
        return 90 <= a < 180
    elif direction == 'back-right':
        return -180 <= a < -90
    elif direction == 'front-right':
        return -90 <= a < 0
    return False

def check_direction_8way(angle_deg, direction):
    """8方位系统（各45°）"""
    a = normalize_angle(angle_deg)
    if direction == 'front':
        return -22.5 <= a < 22.5
    elif direction == 'front-left':
        return 22.5 <= a < 67.5
    elif direction == 'left':
        return 67.5 <= a < 112.5
    elif direction == 'back-left':
        return 112.5 <= a < 157.5
    elif direction == 'back':
        return a >= 157.5 or a < -157.5
    elif direction == 'back-right':
        return -157.5 <= a < -112.5
    elif direction == 'right':
        return -112.5 <= a < -67.5
    elif direction == 'front-right':
        return -67.5 <= a < -22.5
    return False

def match_direction(angle_deg, query_direction):
    """综合匹配函数"""
    direction = query_direction.lower().strip()
    
    if '-' in direction:
        # 复合方向：优先 4way，后备 8way
        if check_direction_4way(angle_deg, direction):
            return True
        if check_direction_8way(angle_deg, direction):
            return True
        return False
    else:
        # 单方向：优先 2way，后备 8way
        if check_direction_2way(angle_deg, direction):
            return True
        if check_direction_8way(angle_deg, direction):
            return True
        return False

def get_all_matching_directions(angle_deg):
    """获取所有匹配的方向"""
    all_directions = [
        'front', 'back', 'left', 'right',
        'front-left', 'front-right', 'back-left', 'back-right'
    ]
    matches = []
    for direction in all_directions:
        if match_direction(angle_deg, direction):
            matches.append(direction)
    return matches

print("=" * 70)
print("三套方位系统测试")
print("=" * 70)

# 测试案例
test_cases = [
    (18.5, "front", "truck1->ped7 场景图角度（应该匹配，在-90~90范围）"),
    (-163.1, "back-right", "truck1->ped7 实际计算角度（关键测试）"),
    (-139.6, "back-right", "ego->ped5"),
    (35.4, "front-left", "ego->ped1"),
    (170, "back", "测试纯后方"),
    (-170, "back-right", "测试后右边界"),
]

for angle, expected_dir, description in test_cases:
    print(f"\n{description}")
    print(f"  角度: {angle:.1f}°")
    print(f"  查询方向: '{expected_dir}'")
    match = match_direction(angle, expected_dir)
    print(f"  ✅ 匹配成功" if match else "  ❌ 匹配失败")
    print(f"  所有匹配方向: {get_all_matching_directions(angle)}")

print("\n" + "=" * 70)
print("关键测试：-163.1° 是否匹配 'back-right'?")
print("=" * 70)
angle = -163.1
print(f"角度: {angle}°")
print(f"\n2way 系统 (180°范围):")
print(f"  back:  {check_direction_2way(angle, 'back')}")
print(f"  right: {check_direction_2way(angle, 'right')}")
print(f"\n4way 系统 (90°范围):")
print(f"  back-right: {check_direction_4way(angle, 'back-right')} <- 关键！")
print(f"\n8way 系统 (45°范围):")
print(f"  back-right: {check_direction_8way(angle, 'back-right')}")
print(f"  back:       {check_direction_8way(angle, 'back')}")
print(f"\n✅ 综合匹配 'back-right': {match_direction(angle, 'back-right')}")

print("\n" + "=" * 70)
print("方位范围总结")
print("=" * 70)
print("back-right 的匹配范围：")
print("  4way系统: [-180, -90)   ← 90°范围，够宽松")
print("  8way系统: [-157.5, -112.5)  ← 45°范围，严格")
print(f"  -163.1° 落在 4way 范围内: {-180 <= angle < -90}")
