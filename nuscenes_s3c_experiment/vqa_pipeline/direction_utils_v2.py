"""
方向工具 V2: 使用三套方位系统，扩大查询范围

设计理念：
- 不同粒度的方位查询使用不同的角度范围
- 三套系统可以重叠，只要能查到结果即可
- 自动根据查询词选择合适的方位系统
"""
from __future__ import annotations
from typing import Iterable, Tuple, List
import numpy as np
from pyquaternion import Quaternion


def quaternion_to_yaw(rotation: Iterable[float]) -> float:
    """Extract yaw (heading) in radians from a NuScenes quaternion."""
    q = Quaternion(rotation)
    return float(q.yaw_pitch_shallow[0]) if hasattr(q, "yaw_pitch_shallow") else float(q.yaw_pitch_roll[0])


def ego_relative_angle_and_distance(
    source_translation: Iterable[float],
    target_translation: Iterable[float],
    ego_rotation: Iterable[float],
) -> Tuple[float, float, np.ndarray]:
    """计算 ego-centric 相对角度和距离"""
    src = np.array(list(source_translation), dtype=float)
    tgt = np.array(list(target_translation), dtype=float)
    rel = tgt - src

    distance = float(np.linalg.norm(rel[:2]))
    world_angle = np.arctan2(rel[1], rel[0])
    ego_yaw = quaternion_to_yaw(ego_rotation)
    
    rel_deg = (world_angle - ego_yaw) * 180.0 / np.pi
    angle_deg = ((rel_deg + 180.0) % 360.0) - 180.0

    return float(angle_deg), distance, rel


def normalize_angle(angle_deg: float) -> float:
    """归一化角度到 [-180, 180]"""
    a = float(angle_deg)
    while a > 180:
        a -= 360
    while a <= -180:
        a += 360
    return a


# ============================================================================
# 三套方位系统
# ============================================================================

def check_direction_2way(angle_deg: float, direction: str) -> bool:
    """
    第一套：2方位系统（前/后，左/右）
    每个方向占 180°
    
    front: [-90, 90)     前半圆
    back:  [90, 180] and [-180, -90)  后半圆
    
    left:  [0, 180)      左半圆
    right: [-180, 0)     右半圆
    """
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


def check_direction_4way(angle_deg: float, direction: str) -> bool:
    """
    第二套：4方位系统（前左、前右、后左、后右）
    每个方向占 90°
    
    front-left:  [0, 90)
    back-left:   [90, 180)
    back-right:  [-180, -90)
    front-right: [-90, 0)
    """
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


def check_direction_8way(angle_deg: float, direction: str) -> bool:
    """
    第三套：8方位系统（原有的 45° 划分，但作为补充）
    每个方向占 45°
    
    front:       [-22.5, 22.5)
    front-left:  [22.5, 67.5)
    left:        [67.5, 112.5)
    back-left:   [112.5, 157.5)
    back:        [157.5, 180] and [-180, -157.5)
    back-right:  [-157.5, -112.5)
    right:       [-112.5, -67.5)
    front-right: [-67.5, -22.5)
    """
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


def match_direction(angle_deg: float, query_direction: str) -> bool:
    """
    根据查询方向，自动选择合适的方位系统进行匹配
    
    策略：
    1. 单方向词（front/back/left/right）：使用 2way 系统（180°范围）
    2. 复合方向词（front-left等）：优先使用 4way 系统（90°范围），再尝试 8way
    3. 如果任何一个系统匹配成功，返回 True
    
    Args:
        angle_deg: ego frame 下的角度
        query_direction: 查询的方向词（如 'back-right', 'front', 'left'）
    
    Returns:
        是否匹配
    """
    # 归一化方向词
    direction = query_direction.lower().strip()
    
    # 复合方向词
    if '-' in direction:
        # 优先使用 4way（90°范围）
        if check_direction_4way(angle_deg, direction):
            return True
        # 后备使用 8way（45°范围）
        if check_direction_8way(angle_deg, direction):
            return True
        return False
    
    # 单方向词
    else:
        # 使用 2way（180°范围）
        if check_direction_2way(angle_deg, direction):
            return True
        # 后备使用 8way
        if check_direction_8way(angle_deg, direction):
            return True
        return False


def get_all_matching_directions(angle_deg: float) -> List[str]:
    """
    获取某个角度匹配的所有方向标签
    用于调试和理解方位系统
    """
    all_directions = [
        'front', 'back', 'left', 'right',
        'front-left', 'front-right', 'back-left', 'back-right'
    ]
    
    matches = []
    for direction in all_directions:
        if match_direction(angle_deg, direction):
            matches.append(direction)
    
    return matches


def compute_direction_features(
    source_translation: Iterable[float],
    target_translation: Iterable[float],
    ego_rotation: Iterable[float],
) -> Tuple[float, float, str, str, np.ndarray]:
    """
    计算方向特征，但只返回最精确的方向标签用于显示
    实际查询时会使用 match_direction() 进行更宽松的匹配
    
    Returns:
        (angle_deg, distance, dir8, dir4, rel_vec)
        dir8 和 dir4 仍然是精确的标签，但查询时会使用更宽松的匹配规则
    """
    angle_deg, distance, rel = ego_relative_angle_and_distance(
        source_translation, target_translation, ego_rotation
    )
    
    # 为了兼容性，仍然生成 8way 和 4way 的标签
    # 但这些只是"最精确"的标签，查询时会更宽松
    a = normalize_angle(angle_deg)
    
    # 8-way direction (最精确)
    if -22.5 <= a < 22.5:
        dir8 = "front"
    elif 22.5 <= a < 67.5:
        dir8 = "front-left"
    elif 67.5 <= a < 112.5:
        dir8 = "left"
    elif 112.5 <= a < 157.5:
        dir8 = "back-left"
    elif a >= 157.5 or a < -157.5:
        dir8 = "back"
    elif -157.5 <= a < -112.5:
        dir8 = "back-right"
    elif -112.5 <= a < -67.5:
        dir8 = "right"
    else:
        dir8 = "front-right"
    
    # 4-way direction
    if -45.0 <= a < 45.0:
        dir4 = "front"
    elif 45.0 <= a < 135.0:
        dir4 = "left"
    elif a >= 135.0 or a < -135.0:
        dir4 = "back"
    else:
        dir4 = "right"
    
    return angle_deg, distance, dir8, dir4, rel


# ============================================================================
# 测试和演示
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("方向匹配系统测试")
    print("=" * 70)
    
    # 测试案例
    test_cases = [
        (18.5, "front", "truck1->ped7 场景图角度"),
        (-163.1, "back-right", "truck1->ped7 实际计算角度"),
        (-139.6, "back-right", "ego->ped5"),
        (35.4, "front-left", "ego->ped1"),
    ]
    
    for angle, expected_dir, description in test_cases:
        print(f"\n{description}")
        print(f"  角度: {angle:.1f}°")
        print(f"  查询方向: '{expected_dir}'")
        print(f"  是否匹配: {match_direction(angle, expected_dir)}")
        print(f"  所有匹配方向: {get_all_matching_directions(angle)}")
    
    print("\n" + "=" * 70)
    print("关键测试：-163.1° 是否匹配 'back-right'?")
    print("=" * 70)
    angle = -163.1
    print(f"2way 系统:")
    print(f"  back: {check_direction_2way(angle, 'back')}")
    print(f"  right: {check_direction_2way(angle, 'right')}")
    print(f"4way 系统:")
    print(f"  back-right: {check_direction_4way(angle, 'back-right')}")
    print(f"8way 系统:")
    print(f"  back-right: {check_direction_8way(angle, 'back-right')}")
    print(f"  back: {check_direction_8way(angle, 'back')}")
    print(f"\n综合匹配 'back-right': {match_direction(angle, 'back-right')}")
