"""Utility functions for object-level operations on NuScenes scene graphs.

This module is meant to support:
- Distance-based filtering of far objects (for question generation).
- Building stable integer indices for objects (for options / visualization).
- Re‑usable helpers that work with our coverage scene_graph format
  (nodes/edges, not the older single_scene_demo format).

Scene graph assumptions (coverage version):
- scene_graph["nodes"]: list of nodes, each with at least:
    {
      "unique_id": "car1",
      "type": "car",
      "translation": {"x": ..., "y": ..., "z": ...},
      ...
    }
- There is exactly one node with unique_id == "ego".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Tuple
import math


@dataclass
class ObjectInfo:
    unique_id: str
    obj_type: str
    distance_from_ego: float
    status: str | None


def _extract_xy(translation: Any) -> Tuple[float, float]:
    """Extract (x, y) from a translation field that can be dict or list.

    NuScenes coverage scene_graph uses a dict with keys x/y/z, but we
    keep this helper robust to list/tuple as well.
    """
    if isinstance(translation, dict):
        return float(translation.get("x", 0.0)), float(translation.get("y", 0.0))
    # list / tuple / other indexable
    return float(translation[0]), float(translation[1])


def get_ego_node(scene_graph: Dict[str, Any]) -> Dict[str, Any]:
    """Return the ego node from a coverage scene_graph.

    Raises ValueError if not found.
    """
    for node in scene_graph.get("nodes", []):
        if node.get("unique_id") == "ego":
            return node
    raise ValueError("No node with unique_id == 'ego' found in scene_graph['nodes']")


def compute_node_distances(scene_graph: Dict[str, Any]) -> Dict[str, float]:
    """Compute Euclidean distance (XY plane) from ego to every node.

    Returns:
        dict: {unique_id: distance_in_meters}
    """
    ego = get_ego_node(scene_graph)
    ego_x, ego_y = _extract_xy(ego["translation"])

    distances: Dict[str, float] = {}
    for node in scene_graph.get("nodes", []):
        uid = node.get("unique_id")
        if not uid:
            continue
        x, y = _extract_xy(node["translation"])
        dx, dy = x - ego_x, y - ego_y
        distances[uid] = math.hypot(dx, dy)
    return distances


def filter_nodes_by_distance(
    scene_graph: Dict[str, Any],
    max_distance: float = 40.0,
    include_ego: bool = False,
) -> List[Dict[str, Any]]:
    """Return nodes whose distance from ego is <= max_distance.

    Args:
        scene_graph: coverage scene_graph dict.
        max_distance: maximum allowed distance (meters). Objects further
            than this are considered "far" and filtered out. NuScenes
           官方检测常用 30~50m 作为可见范围，这里默认取 40m。
        include_ego: whether to keep the ego node in the result.

    Returns:
        List of node dicts.
    """
    distances = compute_node_distances(scene_graph)
    nodes: List[Dict[str, Any]] = []

    for node in scene_graph.get("nodes", []):
        uid = node.get("unique_id")
        if uid == "ego" and not include_ego:
            continue
        if uid is None:
            continue
        d = distances.get(uid, float("inf"))
        if d <= max_distance:
            nodes.append(node)
    return nodes


def build_indexed_objects(
    scene_graph: Dict[str, Any],
    max_distance: float = 40.0,
) -> Tuple[List[ObjectInfo], Dict[str, int]]:
    """Build a distance‑sorted indexed list of objects for options / visualization.

    Args:
        scene_graph: coverage scene_graph dict.
        max_distance: only objects within this distance from ego are kept.

    Returns:
        (objects, id_to_index):
            - objects: List[ObjectInfo] where index in this list (0-based)
              corresponds to a human‑facing index (1-based).
            - id_to_index: mapping from unique_id -> 1-based index.
    """
    distances = compute_node_distances(scene_graph)

    # Collect candidates (exclude ego, filter by distance)
    candidates: List[ObjectInfo] = []
    for node in scene_graph.get("nodes", []):
        uid = node.get("unique_id")
        if not uid or uid == "ego":
            continue
        d = distances.get(uid, float("inf"))
        if d > max_distance:
            continue
        obj_type = node.get("type", "unknown")
        status = node.get("status")
        candidates.append(ObjectInfo(unique_id=uid, obj_type=obj_type, distance_from_ego=d, status=status))

    # Sort by distance, then type/name for stability
    candidates.sort(key=lambda o: (o.distance_from_ego, o.obj_type, o.unique_id))

    id_to_index: Dict[str, int] = {}
    for idx, obj in enumerate(candidates, start=1):
        id_to_index[obj.unique_id] = idx

    return candidates, id_to_index


def pretty_options_from_indexed(objects: List[ObjectInfo]) -> List[str]:
    """Render human‑readable option strings like "[1] car1 (car, 12.3m)".

    This is mainly for logging / question authoring, not for the model.
    """
    lines: List[str] = []
    for i, obj in enumerate(objects, start=1):
        d = f"{obj.distance_from_ego:.1f}m"
        status = f", {obj.status}" if obj.status else ""
        lines.append(f"[{i}] {obj.unique_id} ({obj.obj_type}, {d}{status})")
    return lines
