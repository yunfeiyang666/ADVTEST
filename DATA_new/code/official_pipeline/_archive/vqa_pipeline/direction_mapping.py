"""
方位词到角度范围的映射表

设计：
- 8个方位词，每个词对应一个固定的角度范围
- 不区分粒度，直接查表匹配
- 允许重叠，以保证查询能找到结果
"""

# 方位词到角度范围的映射表
# 格式: (min_angle, max_angle)，范围是 [min, max)，即包含min不包含max
DIRECTION_RANGES = {
    'front':       (-90, 90),       # 前：[-90, 90)  前半圆 180°
    'back':        (90, -90),       # 后：[90, 180] ∪ [-180, -90)  后半圆 180°
    'left':        (0, 180),        # 左：[0, 180)  左半圆 180°
    'right':       (-180, 0),       # 右：[-180, 0)  右半圆 180°
    'front-left':  (0, 90),         # 前左：[0, 90)  90°
    'front-right': (-90, 0),        # 前右：[-90, 0)  90°
    'back-left':   (90, 180),       # 后左：[90, 180)  90°
    'back-right':  (-180, -90),     # 后右：[-180, -90)  90°
}


def normalize_angle(angle_deg: float) -> float:
    """归一化角度到 [-180, 180]"""
    a = float(angle_deg)
    while a > 180:
        a -= 360
    while a <= -180:
        a += 360
    return a


def match_direction(angle_deg: float, direction: str) -> bool:
    """
    判断角度是否匹配给定的方位词
    
    Args:
        angle_deg: ego frame 下的角度，范围 [-180, 180]
        direction: 方位词，如 'back-right', 'front', 'left'
    
    Returns:
        是否匹配
    """
    direction = direction.lower().strip()
    
    if direction not in DIRECTION_RANGES:
        return False
    
    a = normalize_angle(angle_deg)
    min_angle, max_angle = DIRECTION_RANGES[direction]
    
    # 处理跨越 ±180° 的情况（如 back: 90° ~ -90°）
    if min_angle > max_angle:
        # 跨越 ±180°，例如 back: (90, -90) 表示 [90, 180] or [-180, -90)
        return a >= min_angle or a < max_angle
    else:
        # 正常范围
        return min_angle <= a < max_angle


def get_all_matching_directions(angle_deg: float) -> list:
    """
    获取某个角度匹配的所有方向标签
    用于调试和验证
    """
    matches = []
    for direction in DIRECTION_RANGES.keys():
        if match_direction(angle_deg, direction):
            matches.append(direction)
    return matches


def get_direction_label(angle_deg: float, prefer_4way: bool = False) -> str:
    """
    根据角度返回最合适的方向标签
    
    Args:
        angle_deg: ego frame 下的角度
        prefer_4way: 是否优先返回4方向（front/back/left/right）
    
    Returns:
        方向标签
    """
    a = normalize_angle(angle_deg)
    
    if prefer_4way:
        # 优先返回4方向
        if -45 <= a < 45:
            return 'front'
        elif 45 <= a < 135:
            return 'left'
        elif a >= 135 or a < -135:
            return 'back'
        else:
            return 'right'
    else:
        # 返回8方向（更精确）
        if -22.5 <= a < 22.5:
            return 'front'
        elif 22.5 <= a < 67.5:
            return 'front-left'
        elif 67.5 <= a < 112.5:
            return 'left'
        elif 112.5 <= a < 157.5:
            return 'back-left'
        elif a >= 157.5 or a < -157.5:
            return 'back'
        elif -157.5 <= a < -112.5:
            return 'back-right'
        elif -112.5 <= a < -67.5:
            return 'right'
        else:  # -67.5 <= a < -22.5
            return 'front-right'


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("方位词映射表")
    print("=" * 70)
    print("\n方位词 -> 角度范围:")
    for direction, (min_a, max_a) in DIRECTION_RANGES.items():
        if min_a > max_a:
            print(f"  {direction:12s}: [{min_a:6.1f}, 180] or [-180, {max_a:6.1f})")
        else:
            print(f"  {direction:12s}: [{min_a:6.1f}, {max_a:6.1f})")
    
    print("\n" + "=" * 70)
    print("测试案例")
    print("=" * 70)
    
    test_cases = [
        (18.5, "front"),
        (-163.1, "back-right"),
        (-139.6, "back-right"),
        (35.4, "front-left"),
        (170, "back"),
        (-170, "back-right"),
        (0, "front-left"),  # 边界测试
        (-90, "back-right"),  # 边界测试
        (90, "back-left"),   # 边界测试
    ]
    
    for angle, query_dir in test_cases:
        match = match_direction(angle, query_dir)
        all_matches = get_all_matching_directions(angle)
        status = "✅" if match else "❌"
        print(f"\n{status} 角度 {angle:6.1f}° 查询 '{query_dir}'")
        print(f"   所有匹配: {all_matches}")
    
    print("\n" + "=" * 70)
    print("关键验证")
    print("=" * 70)
    
    critical_tests = [
        (-163.1, "back-right", "truck1->ped7 应该匹配"),
        (-163.1, "back", "truck1->ped7 应该匹配"),
        (-163.1, "right", "truck1->ped7 应该匹配"),
        (18.5, "front", "truck1->ped7 在场景图中标记为front"),
    ]
    
    for angle, query_dir, desc in critical_tests:
        match = match_direction(angle, query_dir)
        status = "✅" if match else "❌"
        print(f"{status} {desc}")
        print(f"   {angle:.1f}° 查询 '{query_dir}': {match}")
