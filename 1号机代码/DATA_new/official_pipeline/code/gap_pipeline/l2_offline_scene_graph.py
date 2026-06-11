"""Offline filtered scene-graph export for the clean v7 L2 pipeline."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from gap_pipeline.l2_artifacts import write_json
from gap_pipeline.l2_geometry import official_dir6_from_angle


def _node(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "unique_id": row.get("id"),
        "type": row.get("type"),
        "category": row.get("category"),
        "status": row.get("status"),
        "is_ego": bool(row.get("is_ego", False)),
        "translation_x": row.get("tx"),
        "translation_y": row.get("ty"),
        "translation_z": row.get("tz"),
    }


def _edge(row: Dict[str, Any]) -> Dict[str, Any]:
    angle = row.get("angle")
    raw_direction = row.get("direction_6") or row.get("direction_official")
    direction = str(raw_direction).replace("-", "_") if raw_direction else (official_dir6_from_angle(float(angle)) if angle is not None else None)
    predicates = list(row.get("predicates") or [])
    if direction:
        predicates = [direction] + [str(p).replace("-", "_") for p in predicates[1:]]
    return {
        "source": row.get("src"),
        "target": row.get("dst"),
        "type": "RELATES_TO",
        "distance": row.get("distance"),
        "angle": angle,
        "direction_6": direction,
        "predicates": predicates,
    }


def fetch_filtered_scene_graph(session, *, limit_objects: Optional[int] = None) -> Dict[str, Any]:
    node_limit = "LIMIT $limit" if limit_objects else ""
    nodes_q = f"""
MATCH (n:Object)
WHERE n.unique_id IS NOT NULL AND n.translation_x IS NOT NULL AND n.translation_y IS NOT NULL
RETURN n.unique_id AS id, n.type AS type, n.category AS category, n.status AS status,
       n.is_ego AS is_ego, n.translation_x AS tx, n.translation_y AS ty, n.translation_z AS tz
{node_limit}
"""
    node_rows = session.run(nodes_q, limit=limit_objects) if limit_objects else session.run(nodes_q)
    ids = [r["id"] for r in node_rows]
    rel_q = """
MATCH (a:Object)-[r:RELATES_TO]->(b:Object)
WHERE a.unique_id IN $ids AND b.unique_id IN $ids
RETURN a.unique_id AS src, b.unique_id AS dst, r.distance AS distance, r.angle AS angle,
       r.direction_6 AS direction_6, r.direction_official AS direction_official, r.predicates AS predicates
"""
    rel_rows = session.run(rel_q, ids=ids)
    return {
        "schema": "v7_filtered_scene_graph",
        "objects": [_node(r) for r in node_rows],
        "relationships": [_edge(r) for r in rel_rows],
        "meta": {"num_objects": len(ids), "num_relationships": len(rel_rows)},
    }


def export_filtered_scene_graph(session, path, *, limit_objects: Optional[int] = None) -> Dict[str, Any]:
    graph = fetch_filtered_scene_graph(session, limit_objects=limit_objects)
    write_json(path, graph)
    return graph

