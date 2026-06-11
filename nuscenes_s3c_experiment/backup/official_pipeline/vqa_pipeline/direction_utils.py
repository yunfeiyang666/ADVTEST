"""Direction and geometry utilities for ego-centric direction computation.

All directions are defined in the **EGO-VEHICLE coordinate frame**:
- The ego's heading (yaw) is the GLOBAL reference direction (0 degrees).
- For any edge (Source)-[r:RELATES_TO]->(Target), the direction is computed as:
  * Global angle from Source to Target in world frame
  * MINUS the Ego vehicle's heading
  * This makes all spatial relations ego-centric: "front" means in front of Ego, not Source
- Angles are measured in degrees, **counter-clockwise positive** (standard math convention), normalized to [-180, 180].

**方位词映射表**（NuScenes-QA 论文 Eq.(2), 6 方位）:
- front:       -30° < θ <= 30°
- front-left:   30° < θ <= 90°
- front-right: -90° < θ <= -30°
- back-left:    90° < θ <= 150°
- back-right: -150° < θ <= -90°
- back:         其余角度区间

**坐标系约定**：
- NuScenes使用的是自动驾驶坐标系：X向前（North），Y向左（West），Z向上
- Yaw=0表示朝向+X方向（北）
- 本模块统一使用该坐标系

These helpers are used by scene graph generation code (e.g. generate_selected_scenes)
so that all RELATES_TO relationships share a consistent notion of direction.
"""
from __future__ import annotations

import logging
from typing import Iterable, Tuple

import numpy as np
from pyquaternion import Quaternion

logger = logging.getLogger(__name__)

# ============================================================================
# NuScenes-QA (AAAI 2024) 6 方位扇区映射（论文 Eq.(2)）
# 变量名沿用历史命名（DIRECTION_PREDICATES_8），但值已对齐论文 6 标签。
# ============================================================================

DIRECTION_PREDICATES_8 = {
    'front': (-30.0, 30.0),           # -30° < θ <= 30°
    'front-left': (30.0, 90.0),       # 30° < θ <= 90°
    'front-right': (-90.0, -30.0),    # -90° < θ <= -30°
    'back-left': (90.0, 150.0),       # 90° < θ <= 150°
    'back-right': (-150.0, -90.0),    # -150° < θ <= -90°
    'back': (150.0, -150.0),          # else, wrap across ±180°
}

DIRECTION_RANGES = dict(DIRECTION_PREDICATES_8)


def normalize_angle(angle_deg: float) -> float:
    """归一化角度到 [-180, 180]"""
    a = float(angle_deg)
    while a > 180:
        a -= 360
    while a <= -180:
        a += 360
    return a


def _range_match(angle: float, bounds: tuple) -> bool:
    """兼容跨越180°的区间匹配."""
    lo, hi = bounds
    if lo > hi:  # wrap
        return angle >= lo or angle < hi
    return lo <= angle < hi

def _match_paper_direction(angle: float, direction: str) -> bool:
    """Paper-aligned bins with exact boundary semantics."""
    if direction == 'front':
        return -30.0 < angle <= 30.0
    if direction == 'front-left':
        return 30.0 < angle <= 90.0
    if direction == 'front-right':
        return -90.0 < angle <= -30.0
    if direction == 'back-left':
        return 90.0 < angle <= 150.0
    if direction == 'back-right':
        return -150.0 < angle <= -90.0
    if direction == 'back':
        return not (-150.0 < angle <= 150.0)
    return False


def match_direction(angle_deg: float, direction: str) -> bool:
    """判断角度是否匹配给定方位（允许重叠命中）。"""
    key = direction.lower().strip()
    if key not in DIRECTION_RANGES:
        return False
    a = normalize_angle(angle_deg)
    return _match_paper_direction(a, key)


def get_all_matching_directions(angle_deg: float) -> list:
    """返回同一角度命中的全部方位标签。"""
    a = normalize_angle(angle_deg)
    return [d for d in DIRECTION_RANGES.keys() if _match_paper_direction(a, d)]


def quaternion_to_yaw(rotation: Iterable[float]) -> float:
    """Extract yaw (heading) in radians from a NuScenes quaternion.

    Args:
        rotation: Sequence-like [w, x, y, z] quaternion from NuScenes.

    Returns:
        Yaw angle in radians (range depends on pyquaternion, typically (-pi, pi]).
    """
    q = Quaternion(rotation)
    return float(q.yaw_pitch_shallow[0]) if hasattr(q, "yaw_pitch_shallow") else float(q.yaw_pitch_roll[0])


def ego_relative_angle_and_distance(
    source_translation: Iterable[float],
    target_translation: Iterable[float],
    ego_rotation: Iterable[float],
) -> Tuple[float, float, np.ndarray]:
    """Compute **ego-centric** relative angle and distance from source to target.

    **新语义 (Ego Frame)**：
    - 每条边 (source -> target) 的方向由 **Ego 车的朝向** 统一决定。
    - 自然语言中的 "X to the left/right/front/back of Y" 在图中对应：
      MATCH (Y)-[r:RELATES_TO]->(X) 且 r.direction_8 / r.direction_4 由 **Ego 的 yaw** 决定。
    - 这符合驾驶场景的直觉：不管物体本身朝哪，"左"永远是主车的左边。

    **坐标系说明**：
    - NuScenes坐标系：X向前（North），Y向左（West），Z向上
    - Yaw=0表示朝向+X方向
    - 方向角：0°=前方，90°=左侧，-90°=右侧，±180°=后方

    计算步骤：
    1. Compute the vector from source -> target in world coordinates.
    2. Compute its world-frame angle using NuScenes convention (X=forward=0°, Y=left=90°).
    3. Subtract **Ego yaw** and normalize到 [-180, 180]。

    Args:
        source_translation: (x, y, z) of source object in world frame.
        target_translation: (x, y, z) of target object in world frame.
        ego_rotation: quaternion of **EGO vehicle** pose (w, x, y, z), NOT source object.

    Returns:
        (angle_deg, distance, rel_vec)
        where angle_deg is in degrees in [-180, 180], distance is Euclidean distance in XY,
        and rel_vec is the 3D vector target - source.
    """
    src = np.array(list(source_translation), dtype=float)
    tgt = np.array(list(target_translation), dtype=float)
    rel = tgt - src

    # Distance in the horizontal plane
    distance = float(np.linalg.norm(rel[:2]))

    # 🔧 关键修复：atan2的正确使用
    # NuScenes坐标系: X=forward(0°), Y=left(90°), 逆时针为正
    # atan2(y, x) 标准公式：以X轴为0°，逆时针方向到Y轴为90°
    # 这恰好符合NuScenes：X=forward=0°, Y=left=90°
    world_angle = np.arctan2(rel[1], rel[0])  # radians, standard atan2: X-axis=0°, CCW+

    # Ego yaw (used as GLOBAL forward direction)
    ego_yaw = quaternion_to_yaw(ego_rotation)

    # Convert to ego-centric, CCW-positive, degrees
    # Key formula: relative_angle = global_angle - ego_heading
    rel_deg = (world_angle - ego_yaw) * 180.0 / np.pi
    angle_deg = ((rel_deg + 180.0) % 360.0) - 180.0
    
    # 调试日志（仅在开发时启用）
    # logger.debug(f"source={src[:2]}, target={tgt[:2]}, rel={rel[:2]}, "
    #             f"world_angle={np.degrees(world_angle):.1f}°, "
    #             f"ego_yaw={np.degrees(ego_yaw):.1f}°, angle_deg={angle_deg:.1f}°")

    return float(angle_deg), distance, rel


def discretize_direction_8(angle_deg: float) -> str:
    """Discretize an angle into paper-aligned 6 directional sectors."""
    a = normalize_angle(angle_deg)
    if -30.0 < a <= 30.0:
        return "front"
    if 30.0 < a <= 90.0:
        return "front-left"
    if -90.0 < a <= -30.0:
        return "front-right"
    if 90.0 < a <= 150.0:
        return "back-left"
    if -150.0 < a <= -90.0:
        return "back-right"
    return "back"


def discretize_direction_4(angle_deg: float) -> str:
    """Discretize an angle (degrees, [-180, 180]) into 4 broad directions.

    Sectors (each 90° wide):
      - front: [-45, 45)
      - left:  [45, 135)
      - back:  [135, 180] and [-180, -135)
      - right: [-135, -45)
    """
    a = ((float(angle_deg) + 180.0) % 360.0) - 180.0

    if -45.0 <= a < 45.0:
        return "front"
    elif 45.0 <= a < 135.0:
        return "left"
    elif a >= 135.0 or a < -135.0:
        return "back"
    else:  # -135.0 <= a < -45.0
        return "right"


def source_relative_angle_and_distance(
    source_translation: Iterable[float],
    target_translation: Iterable[float],
    source_rotation: Iterable[float],
) -> Tuple[float, float, np.ndarray]:
    """Compute **source-centric** relative angle and distance from source to target.

    **Source Frame**：
    - 每条边 (source -> target) 的方向由 **source 对象的朝向** 决定。
    - 自然语言中的 "X to the left/right/front/back of Y" 在图中对应：
      MATCH (Y)-[r:RELATES_TO]->(X) 且 r.direction 由 **Y 的朝向** 决定。
    - 这符合以对象为中心的直觉："truck 的后方"是基于 truck 自身的朝向。

    Args:
        source_translation: (x, y, z) of source object in world frame.
        target_translation: (x, y, z) of target object in world frame.
        source_rotation: quaternion of **source object** pose (w, x, y, z).

    Returns:
        (angle_deg, distance, rel_vec)
    """
    src = np.array(list(source_translation), dtype=float)
    tgt = np.array(list(target_translation), dtype=float)
    rel = tgt - src

    distance = float(np.linalg.norm(rel[:2]))
    world_angle = np.arctan2(rel[1], rel[0])
    source_yaw = quaternion_to_yaw(source_rotation)
    
    rel_deg = (world_angle - source_yaw) * 180.0 / np.pi
    angle_deg = ((rel_deg + 180.0) % 360.0) - 180.0

    return float(angle_deg), distance, rel


def compute_direction_features(
    source_translation: Iterable[float],
    target_translation: Iterable[float],
    ego_rotation: Iterable[float],
) -> Tuple[float, float, str, str, np.ndarray]:
    """Convenience helper: from two points + *Ego* pose -> (angle, dist, dir8, dir4, rel_vec).

    **重要**：这里的旋转应当是 **Ego 车** 的朝向，不是 source 对象的朝向。
    所有方向都基于 Ego 的视角计算，符合驾驶场景的人类直觉。
    """
    angle_deg, distance, rel = ego_relative_angle_and_distance(
        source_translation, target_translation, ego_rotation
    )
    dir8 = discretize_direction_8(angle_deg)
    dir4 = discretize_direction_4(angle_deg)
    return angle_deg, distance, dir8, dir4, rel


def compute_direction_features_dual(
    source_translation: Iterable[float],
    target_translation: Iterable[float],
    source_rotation: Iterable[float],
    ego_rotation: Iterable[float],
) -> Tuple[float, float, float, float, str, str, np.ndarray]:
    """旧接口：返回 ego/source 角度 + ego dir4/dir8。"""
    angle_ego, distance, rel = ego_relative_angle_and_distance(
        source_translation, target_translation, ego_rotation
    )
    angle_source, _, _ = source_relative_angle_and_distance(
        source_translation, target_translation, source_rotation
    )
    dir8 = discretize_direction_8(angle_ego)
    dir4 = discretize_direction_4(angle_ego)
    return angle_ego, angle_source, distance, dir8, dir4, rel


def compute_direction_features_full(
    source_translation: Iterable[float],
    target_translation: Iterable[float],
    source_rotation: Iterable[float],
    ego_rotation: Iterable[float],
) -> dict:
    """
    新接口：全量方向特征（双坐标系 + 宽松匹配列表）。
    返回键：angle_ego, angle_source, distance, direction_8_ego, direction_8_source,
           direction_4_ego, angle_matches_ego, angle_matches_source, relative_position
    """
    angle_ego, distance, rel = ego_relative_angle_and_distance(
        source_translation, target_translation, ego_rotation
    )
    angle_source, _, _ = source_relative_angle_and_distance(
        source_translation, target_translation, source_rotation
    )

    direction_8_ego = discretize_direction_8(angle_ego)
    direction_4_ego = discretize_direction_4(angle_ego)
    direction_8_source = discretize_direction_8(angle_source)

    return {
        "distance": distance,
        "angle_ego": angle_ego,
        "angle_source": angle_source,
        "direction_8_ego": direction_8_ego,
        "direction_8_source": direction_8_source,
        "direction_4_ego": direction_4_ego,
        "angle_matches_ego": get_all_matching_directions(angle_ego),
        "angle_matches_source": get_all_matching_directions(angle_source),
        "relative_position": rel,
    }


if __name__ == "__main__":
    # Lightweight sanity check – not a full unit test, but helps catch gross errors.
    print("Testing direction computation with NuScenes coordinate system:")
    print("Coordinate system: X=forward(North), Y=left(West), Z=up")
    print("="*70)
    
    ego_rot = [1.0, 0.0, 0.0, 0.0]  # yaw = 0, ego faces +X direction
    src = (0.0, 0.0, 0.0)

    # 修正：根据NuScenes坐标系（X=forward, Y=left）
    examples = {
        "front": (10.0, 0.0, 0.0),        # +X
        "front-left": (8.0, 6.0, 0.0),    # ~36.9°
        "front-right": (8.0, -6.0, 0.0),  # ~-36.9°
        "back-left": (-6.0, 8.0, 0.0),    # ~126.9°
        "back-right": (-6.0, -8.0, 0.0),  # ~-126.9°
        "back": (-10.0, 0.0, 0.0),        # ±180°
    }
    
    print("\nTest Results:")
    for name, tgt in examples.items():
        ang, dist, d8, d4, rel = compute_direction_features(src, tgt, ego_rot)
        status = "✓" if d8 == name else "✗"
        print(f"{status} {name:>12}: angle={ang:6.1f}°, dist={dist:5.1f}m, dir8={d8:>12}, dir4={d4:>6}")
    
    print("\n" + "="*70)
    print("If all checks pass (✓), the coordinate system is correctly configured.")
