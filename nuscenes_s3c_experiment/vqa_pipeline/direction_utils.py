"""Direction and geometry utilities for ego-centric 4/8-direction computation.

All directions are defined in the **EGO-VEHICLE coordinate frame**:
- The ego's heading (yaw) is the GLOBAL reference direction (0 degrees).
- For any edge (Source)-[r:RELATES_TO]->(Target), the direction is computed as:
  * Global angle from Source to Target in world frame
  * MINUS the Ego vehicle's heading
  * This makes all spatial relations ego-centric: "front" means in front of Ego, not Source
- Angles are measured in degrees, **counter-clockwise positive** (standard math convention), normalized to [-180, 180].
- 8-direction sectors (45° each): front, front-left, left, back-left, back, back-right, right, front-right.
- 4-direction sectors (90° each): front, left, back, right.

These helpers are used by scene graph generation code (e.g. generate_selected_scenes)
so that all RELATES_TO relationships share a consistent notion of direction.
"""
from __future__ import annotations

from typing import Iterable, List, Tuple

import numpy as np
from pyquaternion import Quaternion


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

    计算步骤：
    1. Compute the vector from source -> target in world coordinates.
    2. Compute its world-frame angle via atan2(y, x) (Standard Math: East=0°, CCW+).
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

    # World-frame angle (mathematical convention, CCW positive, East=0°)
    world_angle = np.arctan2(rel[1], rel[0])  # radians

    # Ego yaw (used as GLOBAL forward direction)
    ego_yaw = quaternion_to_yaw(ego_rotation)

    # Convert to ego-centric, CCW-positive, degrees
    # Key formula: relative_angle = global_angle - ego_heading
    rel_deg = (world_angle - ego_yaw) * 180.0 / np.pi
    angle_deg = ((rel_deg + 180.0) % 360.0) - 180.0

    return float(angle_deg), distance, rel


def discretize_direction_8(angle_deg: float) -> str:
    """Discretize an angle (degrees, [-180, 180]) into 8 directional sectors.

    Sectors (each 45° wide):
      - front:       [-22.5,  22.5)
      - front-left:  [ 22.5,  67.5)
      - left:        [ 67.5, 112.5)
      - back-left:   [112.5, 157.5)
      - back:        [157.5, 180] and [-180, -157.5)
      - back-right:  [-157.5, -112.5)
      - right:       [-112.5, -67.5)
      - front-right: [-67.5, -22.5)
    """
    # Normalize defensively
    a = ((float(angle_deg) + 180.0) % 360.0) - 180.0

    if -22.5 <= a < 22.5:
        return "front"
    if 22.5 <= a < 67.5:
        return "front-left"
    if 67.5 <= a < 112.5:
        return "left"
    if 112.5 <= a < 157.5:
        return "back-left"
    if a >= 157.5 or a < -157.5:
        return "back"
    if -157.5 <= a < -112.5:
        return "back-right"
    if -112.5 <= a < -67.5:
        return "right"
    # -67.5 <= a < -22.5
    return "front-right"


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
    if 45.0 <= a < 135.0:
        return "left"
    if a >= 135.0 or a < -135.0:
        return "back"
    return "right"


# --- 方位词宽松匹配（与 core_pipeline / generate_selected_scenes_improved 一致）---

DIRECTION_RANGES = {
    "front": (-90, 90),
    "back": (90, -90),
    "left": (0, 180),
    "right": (-180, 0),
    "front-left": (0, 90),
    "front-right": (-90, 0),
    "back-left": (90, 180),
    "back-right": (-180, -90),
}


def normalize_angle(angle_deg: float) -> float:
    a = float(angle_deg)
    while a > 180:
        a -= 360
    while a <= -180:
        a += 360
    return a


def _range_match(angle: float, bounds: tuple) -> bool:
    lo, hi = bounds
    if lo > hi:
        return angle >= lo or angle < hi
    return lo <= angle < hi


def match_direction(angle_deg: float, direction: str) -> bool:
    key = direction.lower().strip()
    if key not in DIRECTION_RANGES:
        return False
    a = normalize_angle(angle_deg)
    return _range_match(a, DIRECTION_RANGES[key])


def get_all_matching_directions(angle_deg: float) -> List[str]:
    a = normalize_angle(angle_deg)
    return [d for d, rng in DIRECTION_RANGES.items() if _range_match(a, rng)]


def source_relative_angle_and_distance(
    source_translation: Iterable[float],
    target_translation: Iterable[float],
    source_rotation: Iterable[float],
) -> Tuple[float, float, np.ndarray]:
    """以 source 朝向为参考的 source→target 平面角（度）与距离。"""
    src = np.array(list(source_translation), dtype=float)
    tgt = np.array(list(target_translation), dtype=float)
    rel = tgt - src

    distance = float(np.linalg.norm(rel[:2]))
    world_angle = np.arctan2(rel[1], rel[0])
    source_yaw = quaternion_to_yaw(source_rotation)

    rel_deg = (world_angle - source_yaw) * 180.0 / np.pi
    angle_deg = ((rel_deg + 180.0) % 360.0) - 180.0

    return float(angle_deg), distance, rel


def compute_direction_features_dual(
    source_translation: Iterable[float],
    target_translation: Iterable[float],
    source_rotation: Iterable[float],
    ego_rotation: Iterable[float],
) -> Tuple[float, float, float, float, str, str, np.ndarray]:
    """同时给出 ego 系与 source 系角度，以及基于 ego 的 dir8/dir4。"""
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
    """全量方向特征：双坐标系 + 宽松匹配列表（供 SceneGraph 关系边写入）。"""
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


if __name__ == "__main__":
    # Lightweight sanity check – not a full unit test, but helps catch gross errors.
    ego_rot = [1.0, 0.0, 0.0, 0.0]  # yaw = 0
    src = (0.0, 0.0, 0.0)

    examples = {
        "front": (10.0, 0.0, 0.0),
        "right": (0.0, -10.0, 0.0),
        "back": (-10.0, 0.0, 0.0),
        "left": (0.0, 10.0, 0.0),
    }
    for name, tgt in examples.items():
        ang, dist, d8, d4, rel = compute_direction_features(src, tgt, ego_rot)
        print(f"{name:>5}: angle={ang:6.1f}, dist={dist:5.1f}, dir8={d8}, dir4={d4}, rel={rel}")
