from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from gap_pipeline.l2_geometry import official_dir6_from_angle

OLD_DIR8 = "direction" + "_8"
OLD_DIR4 = "direction" + "_4"


def _norm_label(value: Any) -> str:
    return str(value or "").replace("-", "_")


def _dir_from_edge(edge: Dict[str, Any]) -> str:
    metrics = edge.get("metrics") or {}
    angle = edge.get("angle") if edge.get("angle") is not None else metrics.get("angle")
    if angle is not None:
        try:
            return official_dir6_from_angle(float(angle)) or ""
        except Exception:
            pass
    return _norm_label(edge.get("direction_6") or edge.get("direction_official"))


def normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    edges = payload.get("edges") or payload.get("relationships") or []
    for edge in edges:
        direction = _dir_from_edge(edge)
        edge["direction_6"] = direction
        edge.pop(OLD_DIR8, None)
        edge.pop(OLD_DIR4, None)
        edge.pop("direction_official", None)

        predicates = list(edge.get("predicates") or [])
        edge["predicates"] = [direction] + [_norm_label(p) for p in predicates[1:]] if direction else [_norm_label(p) for p in predicates]

        metrics = edge.get("metrics")
        if isinstance(metrics, dict):
            for key in ("direction_ego", "direction_source"):
                sub = metrics.get(key)
                if isinstance(sub, dict):
                    sub.pop(OLD_DIR8, None)
                    sub.pop(OLD_DIR4, None)
                    sub.pop("angle_matches", None)
                    sub["direction_6"] = direction
    payload["schema"] = "v7_filtered_scene_graph_direction6"
    return payload


def normalize_file(path: Path) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return False
    if not (payload.get("edges") or payload.get("relationships")):
        return False
    normalize_payload(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def main(argv: list[str]) -> None:
    paths = [Path(a) for a in argv[1:]]
    if not paths:
        paths = list(Path("outputs/v7_formal_test").glob("*/offline/scene_graphs/*.json")) + list(Path("filtered_scene_graphs").glob("*.json"))
    for path in paths:
        if path.exists() and normalize_file(path):
            print(f"normalized {path}")


if __name__ == "__main__":
    main(sys.argv)

