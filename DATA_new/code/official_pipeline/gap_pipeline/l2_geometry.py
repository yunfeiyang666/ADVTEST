"""
Geometry helpers for the L2 refactor side path.

Conventions follow the official NuScenesQA ego-forward angular relation:
  0° = front, positive = left, negative = right, normalized to (-180, 180].

Public direction labels use the official 6-way set with underscores:
  front, front_left, back_left, back, back_right, front_right

No pipeline code imports this module yet.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

Point = Tuple[float, float]

OFFICIAL_DIR6 = (
    "front",
    "front_left",
    "front_right",
    "back_left",
    "back_right",
    "back",
)


def normalize_angle(angle: float) -> float:
    a = float(angle)
    while a > 180.0:
        a -= 360.0
    while a <= -180.0:
        a += 360.0
    return a


def point_from_obj(obj: Dict[str, Any]) -> Optional[Point]:
    """Extract xy from common object/candidate shapes."""
    if obj is None:
        return None
    if obj.get("tx") is not None and obj.get("ty") is not None:
        return (float(obj["tx"]), float(obj["ty"]))
    if obj.get("x") is not None and obj.get("y") is not None:
        return (float(obj["x"]), float(obj["y"]))
    tr = obj.get("translation") if isinstance(obj, dict) else None
    if isinstance(tr, dict) and "x" in tr and "y" in tr:
        return (float(tr["x"]), float(tr["y"]))
    return None


def angle_between(src: Point, tgt: Point) -> float:
    dx, dy = tgt[0] - src[0], tgt[1] - src[1]
    return normalize_angle(math.degrees(math.atan2(dy, dx)))


def distance(src: Point, tgt: Point) -> float:
    return math.hypot(tgt[0] - src[0], tgt[1] - src[1])


def official_dir6_from_angle(angle: float, *, boundary_margin: float = 0.0) -> Optional[str]:
    """
    Convert angle to the official 6-way direction set:
      front       : -30° < a <= 30°
      front_left  :  30° < a <= 90°
      front_right : -90° < a <= -30°
      back_left   :  90° < a <= 150°
      back_right  : -150° < a <= -90°
      back        : otherwise
    """
    a = normalize_angle(angle)
    if boundary_margin > 0:
        for b in (-150.0, -90.0, -30.0, 30.0, 90.0, 150.0):
            if abs(a - b) < boundary_margin:
                return None
    if -30.0 < a <= 30.0:
        return "front"
    if 30.0 < a <= 90.0:
        return "front_left"
    if -90.0 < a <= -30.0:
        return "front_right"
    if 90.0 < a <= 150.0:
        return "back_left"
    if -150.0 < a <= -90.0:
        return "back_right"
    return "back"


def official_dir6(src: Point, tgt: Point, *, boundary_margin: float = 0.0) -> Optional[str]:
    return official_dir6_from_angle(angle_between(src, tgt), boundary_margin=boundary_margin)


def official_dir6_between_objs(
    src_obj: Dict[str, Any],
    tgt_obj: Dict[str, Any],
    *,
    boundary_margin: float = 0.0,
) -> Optional[str]:
    src, tgt = point_from_obj(src_obj), point_from_obj(tgt_obj)
    if src is None or tgt is None:
        return None
    return official_dir6(src, tgt, boundary_margin=boundary_margin)


def direction_text(label: str) -> str:
    """Human-readable direction phrase."""
    return (label or "").replace("_", " ").replace("-", " ")


def rank_label(index: int, n: int) -> Optional[str]:
    """Natural label for zero-based distance rank."""
    if n <= 0 or index < 0 or index >= n:
        return None
    if index == 0:
        return "nearest"
    if index == 1:
        return "2nd-nearest"
    if index == n - 1:
        return "farthest"
    if index == n - 2:
        return "2nd-farthest"
    return f"{index + 1}th-nearest"


def distance_rank(target_id: str, candidates: Iterable[Dict[str, Any]]) -> Optional[str]:
    rows: List[Tuple[str, float]] = []
    for c in candidates:
        cid = str(c.get("id") or c.get("unique_id") or "")
        if not cid:
            return None
        if c.get("actual_dist") is not None:
            dist = float(c["actual_dist"])
        elif c.get("distance") is not None:
            dist = float(c["distance"])
        else:
            return None
        rows.append((cid, dist))
    rows.sort(key=lambda x: x[1])
    for i, (cid, _) in enumerate(rows):
        if cid == str(target_id):
            return rank_label(i, len(rows))
    return None


def viewpoint_left_right(
    a: Point,
    b: Point,
    c: Point,
    *,
    ambiguity_margin_deg: float = 10.0,
) -> Optional[str]:
    """If facing from a toward b, determine whether c is left or right."""
    ab = (b[0] - a[0], b[1] - a[1])
    ac = (c[0] - a[0], c[1] - a[1])
    if math.hypot(*ab) < 1e-9 or math.hypot(*ac) < 1e-9:
        return None
    cross = ab[0] * ac[1] - ab[1] * ac[0]
    dot = ab[0] * ac[0] + ab[1] * ac[1]
    angle = abs(math.degrees(math.atan2(cross, dot)))
    if angle < ambiguity_margin_deg or abs(180.0 - angle) < ambiguity_margin_deg:
        return None
    return "left" if cross > 0 else "right"

