"""
core_universe_filter.py — 核心宇宙过滤器（V21）

筛选目标（按用户要求）：
1) 距离支持双模式：
   - custom20m：全类别统一 20m
   - official：按 nuScenes 官方检测范围（30/40/50m）
2) 可见度与像素阈值按官方口径：
   - 可见度阈值：>= 40%
   - 像素高度阈值：>=10px（lenient）或 >=15px（strict）
3) 边保留规则：
   - 保留“筛选后节点”形成的全量边（诱导子图）
   - 不保留筛选前节点的全量边
"""
from __future__ import annotations

import collections
import json
import logging
import math
import os
import pathlib
import sys
from datetime import datetime as _dt
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("core_filter")

# ─────────────────────────────────────────────────────────────────────────────
# 配置（路径与 unified_site / advtest_paths 一致；入口须先 load_advtest_env）
# ─────────────────────────────────────────────────────────────────────────────
try:
    from advtest_paths import (
        DEFAULT_NEO4J_URI,
        FILTERED_SG_DIR,
        NUSCENES_DATAROOT,
        NUSCENES_DEVKIT_PATH,
        NUSCENES_VERSION,
        RAW_SG_DIR,
        TRAINVAL_META,
    )

    TRAINVAL = TRAINVAL_META
except ImportError:
    DEFAULT_NEO4J_URI = "bolt://localhost:7687"
    _root = pathlib.Path(os.getenv("ADVTEST_ROOT", ".")).resolve()
    FILTERED_SG_DIR = pathlib.Path(
        os.getenv("FILTERED_SG_DIR", str(_root / "filtered_scene_graphs"))
    )
    RAW_SG_DIR = pathlib.Path(
        os.getenv(
            "ADVTEST_RAW_SG_DIR",
            str(
                _root
                / "nuscenes_s3c_experiment"
                / "output"
                / "coverage_analysis"
                / "scene_graphs"
            ),
        )
    )
    NUSCENES_DEVKIT_PATH = os.getenv("NUSCENES_DEVKIT_PATH", "").strip()
    NUSCENES_DATAROOT = pathlib.Path(
        os.getenv("NUSCENES_DATAROOT", str(_root / "data"))
    )
    NUSCENES_VERSION = (
        os.getenv("VQA_NUSCENES_VERSION", "").strip()
        or os.getenv("NUSCENES_VERSION", "").strip()
        or "v1.0-trainval"
    )
    TRAINVAL = NUSCENES_DATAROOT / NUSCENES_VERSION

_DEVKIT_PATH = NUSCENES_DEVKIT_PATH
if _DEVKIT_PATH and _DEVKIT_PATH not in sys.path:
    sys.path.insert(0, _DEVKIT_PATH)

try:
    from nuscenes.nuscenes import NuScenes  # type: ignore
    NUSCENES_AVAILABLE = True
except Exception:
    NuScenes = None  # type: ignore
    NUSCENES_AVAILABLE = False

CORE_TYPES = {
    "car",
    "truck",
    "bus",
    "trailer",
    "construction_vehicle",
    "pedestrian",
    "motorcycle",
    "bicycle",
    "traffic_cone",
    "barrier",
}

OFFICIAL_DETECTION_RANGES = {
    "barrier": 30.0,
    "traffic_cone": 30.0,
    "bicycle": 40.0,
    "motorcycle": 40.0,
    "pedestrian": 40.0,
    "car": 50.0,
    "bus": 50.0,
    "construction_vehicle": 50.0,
    "trailer": 50.0,
    "truck": 50.0,
}
OFFICIAL_DEFAULT_MAX_DIST_M = 50.0
CUSTOM_MAX_DIST_M = 20.0

# 可见度与像素阈值
MIN_VISIBILITY = float(os.getenv("VQA_FILTER_MIN_VISIBILITY", "0.4"))
MIN_PIXEL_HEIGHT_LENIENT = 10.0
MIN_PIXEL_HEIGHT_STRICT = 15.0
CAM_FOCAL_LENGTH_PX = 1266.0

# 默认模式（可由环境变量覆盖）
DISTANCE_MODE_DEFAULT = os.getenv("VQA_DISTANCE_MODE", "official").lower()  # official | custom20m
PIXEL_MODE_DEFAULT = os.getenv("VQA_PIXEL_MODE", "lenient").lower()  # lenient | strict

try:
    FILTERED_SG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

_NUSC = None
_SAMPLE_ANNS_CACHE: Dict[str, List[Dict]] = {}
_VIS_TOKEN_RATIO_CACHE: Dict[str, float] = {}
_VIS_NODE_CACHE: Dict[Tuple[str, int, str], Optional[float]] = {}

_VIS_LEVEL_TO_RATIO = {
    "v0-40": 0.2,
    "v40-60": 0.5,
    "v60-80": 0.7,
    "v80-100": 0.9,
}


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_distance_mode(mode: str) -> str:
    m = (mode or "").strip().lower()
    if m in {"official", "custom20m"}:
        return m
    raise ValueError(f"Unsupported distance_mode={mode}, expected one of: custom20m|official")


def _normalize_pixel_mode(mode: str) -> str:
    m = (mode or "").strip().lower()
    if m in {"lenient", "strict"}:
        return m
    raise ValueError(f"Unsupported pixel_mode={mode}, expected one of: lenient|strict")


def _get_ego_pos(nodes: List[Dict]) -> Optional[Tuple[float, float]]:
    for n in nodes:
        if n.get("unique_id") == "ego" or n.get("type") == "ego":
            t = n.get("translation", {})
            if isinstance(t, dict):
                return float(t.get("x", 0.0)), float(t.get("y", 0.0))
            if isinstance(t, list) and len(t) >= 2:
                return float(t[0]), float(t[1])
    return None


def _dist_xy(t: Dict | List | None, ego_pos: Tuple[float, float]) -> float:
    if isinstance(t, dict):
        dx = float(t.get("x", 0.0)) - ego_pos[0]
        dy = float(t.get("y", 0.0)) - ego_pos[1]
    elif isinstance(t, list) and len(t) >= 2:
        dx = float(t[0]) - ego_pos[0]
        dy = float(t[1]) - ego_pos[1]
    else:
        return 0.0
    return math.sqrt(dx * dx + dy * dy)


def _distance_limit(ntype: str, distance_mode: str) -> float:
    if distance_mode == "official":
        return float(OFFICIAL_DETECTION_RANGES.get(ntype, OFFICIAL_DEFAULT_MAX_DIST_M))
    return CUSTOM_MAX_DIST_M


def _estimate_pixel_height(node: Dict, ego_pos: Optional[Tuple[float, float]]) -> Optional[float]:
    if ego_pos is None:
        return None
    size = node.get("size")
    if not isinstance(size, dict):
        return None
    h3d = float(size.get("height", 0.0) or 0.0)
    if h3d <= 0:
        return None
    d = max(_dist_xy(node.get("translation", {}), ego_pos), 1.0)
    return (h3d * CAM_FOCAL_LENGTH_PX) / d


def _pixel_threshold(pixel_mode: str) -> float:
    return MIN_PIXEL_HEIGHT_STRICT if pixel_mode == "strict" else MIN_PIXEL_HEIGHT_LENIENT


def _category_match(node_category: str, node_type: str, ann_category: str) -> bool:
    if node_category and ann_category == node_category:
        return True
    if node_type:
        if ann_category.endswith("." + node_type) or ann_category == node_type:
            return True
        if node_type == "pedestrian" and "pedestrian" in ann_category:
            return True
    return False


@lru_cache(maxsize=1)
def _scene_frame_to_sample_token() -> Dict[Tuple[str, int], str]:
    mapping: Dict[Tuple[str, int], str] = {}
    scene_file = TRAINVAL / "scene.json"
    sample_file = TRAINVAL / "sample.json"
    if not scene_file.exists() or not sample_file.exists():
        logger.warning("scene/sample metadata missing under %s; visibility query disabled", TRAINVAL)
        return mapping
    scenes = json.loads(scene_file.read_text(encoding="utf-8"))
    samples = json.loads(sample_file.read_text(encoding="utf-8"))
    st2name = {s["token"]: s["name"] for s in scenes}
    s2tok: Dict[str, List[Tuple[str, int]]] = collections.defaultdict(list)
    for samp in samples:
        scene_name = st2name.get(samp["scene_token"], "")
        if not scene_name:
            continue
        s2tok[scene_name].append((samp["token"], int(samp["timestamp"])))
    for scene_name, toks in s2tok.items():
        toks_sorted = sorted(toks, key=lambda x: x[1])
        for idx, (tok, _) in enumerate(toks_sorted):
            mapping[(scene_name, idx)] = tok
    return mapping


def _get_nusc():
    global _NUSC
    if _NUSC is not None:
        return _NUSC
    if not NUSCENES_AVAILABLE:
        logger.warning("nuscenes devkit not available; fallback visibility policy will be used")
        return None
    try:
        _NUSC = NuScenes(version=NUSCENES_VERSION, dataroot=str(NUSCENES_DATAROOT), verbose=False)
    except Exception as exc:
        logger.warning("NuScenes init failed (%s), visibility query disabled", exc)
        _NUSC = None
    return _NUSC


def _get_sample_annotations(sample_token: str) -> List[Dict]:
    if sample_token in _SAMPLE_ANNS_CACHE:
        return _SAMPLE_ANNS_CACHE[sample_token]
    nusc = _get_nusc()
    if nusc is None:
        _SAMPLE_ANNS_CACHE[sample_token] = []
        return []
    try:
        sample = nusc.get("sample", sample_token)
    except Exception:
        _SAMPLE_ANNS_CACHE[sample_token] = []
        return []

    rows: List[Dict] = []
    for ann_token in sample.get("anns", []):
        try:
            ann = nusc.get("sample_annotation", ann_token)
            rows.append(
                {
                    "category_name": ann.get("category_name", ""),
                    "translation": ann.get("translation", [0.0, 0.0, 0.0]),
                    "visibility_token": ann.get("visibility_token", ""),
                }
            )
        except Exception:
            continue
    _SAMPLE_ANNS_CACHE[sample_token] = rows
    return rows


def _get_visibility_ratio_by_token(vis_token: str) -> Optional[float]:
    if not vis_token:
        return None
    if vis_token in _VIS_TOKEN_RATIO_CACHE:
        return _VIS_TOKEN_RATIO_CACHE[vis_token]
    nusc = _get_nusc()
    if nusc is None:
        return None
    try:
        rec = nusc.get("visibility", vis_token)
        level = rec.get("level", "")
        ratio = float(_VIS_LEVEL_TO_RATIO.get(level, 0.5))
        _VIS_TOKEN_RATIO_CACHE[vis_token] = ratio
        return ratio
    except Exception:
        return None


def _query_node_visibility(scene_id: str, frame_id: int, node: Dict) -> Optional[float]:
    node_id = str(node.get("unique_id", ""))
    k = (scene_id, frame_id, node_id)
    if k in _VIS_NODE_CACHE:
        return _VIS_NODE_CACHE[k]

    sample_token = _scene_frame_to_sample_token().get((scene_id, frame_id), "")
    if not sample_token:
        _VIS_NODE_CACHE[k] = None
        return None

    anns = _get_sample_annotations(sample_token)
    if not anns:
        _VIS_NODE_CACHE[k] = None
        return None

    node_t = node.get("translation", {})
    node_x = float(node_t.get("x", 0.0)) if isinstance(node_t, dict) else 0.0
    node_y = float(node_t.get("y", 0.0)) if isinstance(node_t, dict) else 0.0
    node_z = float(node_t.get("z", 0.0)) if isinstance(node_t, dict) else 0.0
    node_category = str(node.get("category", ""))
    node_type = str(node.get("type", ""))

    best = None
    best_dist = float("inf")
    for ann in anns:
        ann_cat = ann.get("category_name", "")
        if not _category_match(node_category, node_type, ann_cat):
            continue
        tr = ann.get("translation", [0.0, 0.0, 0.0])
        if not isinstance(tr, list) or len(tr) < 3:
            continue
        d = math.sqrt((float(tr[0]) - node_x) ** 2 + (float(tr[1]) - node_y) ** 2 + (float(tr[2]) - node_z) ** 2)
        if d < best_dist and d < 2.0:
            best_dist = d
            best = ann

    ratio = None
    if best:
        ratio = _get_visibility_ratio_by_token(best.get("visibility_token", ""))
    _VIS_NODE_CACHE[k] = ratio
    return ratio


def filter_scene_graph(
    sg_data: Dict,
    *,
    distance_mode: str = DISTANCE_MODE_DEFAULT,
    pixel_mode: str = PIXEL_MODE_DEFAULT,
    min_visibility: float = MIN_VISIBILITY,
) -> Dict:
    """
    Apply core-universe filter to a scene graph dict.
    Returns a NEW dict with filtered nodes + induced edges on filtered nodes.
    """
    distance_mode = _normalize_distance_mode(distance_mode)
    pixel_mode = _normalize_pixel_mode(pixel_mode)

    nodes_raw = sg_data.get("nodes", []) or []
    edges_raw = sg_data.get("edges", []) or []
    scene_id = str(sg_data.get("scene_name", "") or "")
    frame_id = int(sg_data.get("frame_idx", -1))

    ego_pos = _get_ego_pos(nodes_raw)
    keep_ids = {"ego"}
    filtered_nodes: List[Dict] = []

    removal = {
        "non_core_type": 0,
        "distance": 0,
        "visibility": 0,
        "pixel_height": 0,
    }

    for n in nodes_raw:
        uid = str(n.get("unique_id", ""))
        ntype = str(n.get("type", ""))
        if uid == "ego" or ntype == "ego":
            filtered_nodes.append(n)
            keep_ids.add(uid or "ego")
            continue

        if ntype not in CORE_TYPES:
            removal["non_core_type"] += 1
            continue

        # 1) 距离过滤
        if ego_pos is not None:
            d = _dist_xy(n.get("translation", {}), ego_pos)
            max_d = _distance_limit(ntype, distance_mode)
            if d > max_d:
                removal["distance"] += 1
                continue

        # 2) 可见度过滤
        vis = None
        if "visibility" in n:
            try:
                vis = float(n.get("visibility", 1.0))
                if vis > 1.0:
                    vis = vis / 4.0
            except Exception:
                vis = None
        if vis is None and scene_id and frame_id >= 0:
            vis = _query_node_visibility(scene_id, frame_id, n)
        if vis is not None and vis < min_visibility:
            removal["visibility"] += 1
            continue

        # 3) 像素高度过滤（官方推荐阈值）
        px = None
        if "pixel_height" in n:
            try:
                px = float(n.get("pixel_height"))
            except Exception:
                px = None
        if px is None:
            px = _estimate_pixel_height(n, ego_pos)
        if px is not None and px < _pixel_threshold(pixel_mode):
            removal["pixel_height"] += 1
            continue

        filtered_nodes.append(n)
        if uid:
            keep_ids.add(uid)

    # 保留筛选后节点的全量边（诱导子图）
    filtered_edges = [
        e for e in edges_raw
        if str(e.get("source", "")) in keep_ids and str(e.get("target", "")) in keep_ids
    ]

    return {
        **sg_data,
        "nodes": filtered_nodes,
        "edges": filtered_edges,
        "core_universe_filter": {
            "applied": True,
            "distance_mode": distance_mode,
            "pixel_mode": pixel_mode,
            "types_kept": sorted(CORE_TYPES),
            "min_visibility": float(min_visibility),
            "pixel_threshold_px": _pixel_threshold(pixel_mode),
            "custom_max_dist_m": CUSTOM_MAX_DIST_M,
            "official_detection_ranges_m": OFFICIAL_DETECTION_RANGES,
            "raw_nodes": len(nodes_raw),
            "filtered_nodes": len(filtered_nodes),
            "raw_edges": len(edges_raw),
            "filtered_edges": len(filtered_edges),
            "edge_scope": "induced_edges_among_filtered_nodes",
            "removal": removal,
            "node_ids_kept": sorted(keep_ids),
        },
    }


def filter_and_save(
    raw_path: pathlib.Path,
    *,
    write_excel: bool = True,
    distance_mode: str = DISTANCE_MODE_DEFAULT,
    pixel_mode: str = PIXEL_MODE_DEFAULT,
    min_visibility: float = MIN_VISIBILITY,
    output_dir: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    """
    Filter one scene graph JSON and save to output directory.
    Optionally writes one row to filter_record Sheet in RQ.xlsx.
    """
    ts_start = _dt.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    sg_data = json.loads(raw_path.read_text(encoding="utf-8"))
    filtered = filter_scene_graph(
        sg_data,
        distance_mode=distance_mode,
        pixel_mode=pixel_mode,
        min_visibility=min_visibility,
    )
    out_dir = output_dir or FILTERED_SG_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / raw_path.name
    out_path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
    ts_end = _dt.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    info = filtered["core_universe_filter"]
    logger.info(
        "%-50s mode=%-9s nodes %d→%d  edges %d→%d",
        raw_path.name,
        info["distance_mode"],
        info["raw_nodes"],
        info["filtered_nodes"],
        info["raw_edges"],
        info["filtered_edges"],
    )

    if write_excel:
        try:
            from rq_tables import write_filter_record
            sname, fidx = _parse_stem(raw_path.stem)
            vex_str = ",".join(sorted(info["node_ids_kept"]))
            ratio = (info["filtered_nodes"] / info["raw_nodes"]) if info["raw_nodes"] > 0 else 0.0
            write_filter_record(
                scene_id=sname,
                frame_id=fidx,
                original_num=info["raw_nodes"],
                filtered_num=info["filtered_nodes"],
                filtered_vex=vex_str,
                ratio=ratio,
                timestamp_start=ts_start,
                timestamp_end=ts_end,
            )
        except Exception as exc:
            logger.warning("filter_record write failed: %s", exc)
    return out_path


def filter_all_existing(
    *,
    distance_mode: str = DISTANCE_MODE_DEFAULT,
    pixel_mode: str = PIXEL_MODE_DEFAULT,
    min_visibility: float = MIN_VISIBILITY,
    output_dir: Optional[pathlib.Path] = None,
    write_excel: bool = False,
) -> Dict[Tuple[str, int], Dict]:
    """Filter all SGs in RAW_SG_DIR and save to output directory."""
    files = sorted(RAW_SG_DIR.glob("*_scene_graph.json"))
    out_dir = output_dir or FILTERED_SG_DIR
    logger.info("Filtering %d scene graphs -> %s (distance_mode=%s)", len(files), out_dir, distance_mode)
    results: Dict[Tuple[str, int], Dict] = {}
    for f in files:
        out = filter_and_save(
            f,
            write_excel=write_excel,
            distance_mode=distance_mode,
            pixel_mode=pixel_mode,
            min_visibility=min_visibility,
            output_dir=out_dir,
        )
        data = json.loads(out.read_text(encoding="utf-8"))
        info = data["core_universe_filter"]
        sname, fidx = _parse_stem(f.stem)
        results[(sname, fidx)] = {
            "n_nodes": info["filtered_nodes"],
            "n_edges": info["filtered_edges"],
            "node_ids": info["node_ids_kept"],
            "out_path": str(out),
            "distance_mode": info["distance_mode"],
        }
    return results


def _parse_stem(stem: str) -> Tuple[str, int]:
    """'scene-0103_frame25_scene_graph' -> ('scene-0103', 25)"""
    s = stem.replace("_scene_graph", "")
    parts = s.rsplit("_frame", 1)
    if len(parts) == 2:
        return parts[0], int(parts[1])
    return s, -1


# ─────────────────────────────────────────────────────────────────────────────
# Import filtered SG to Neo4j
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_angle_deg(angle_deg: float) -> float:
    a = float(angle_deg)
    while a > 180.0:
        a -= 360.0
    while a <= -180.0:
        a += 360.0
    return a


def _paper_direction_8(angle_deg: float) -> str:
    """NuScenes-QA paper direction bins (Eq.(2), 6 labels)."""
    a = _normalize_angle_deg(angle_deg)
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


def _direction_4_from_angle(angle_deg: float) -> str:
    a = _normalize_angle_deg(angle_deg)
    if -45.0 <= a < 45.0:
        return "front"
    if 45.0 <= a < 135.0:
        return "left"
    if a >= 135.0 or a < -135.0:
        return "back"
    return "right"


_LEGACY_DIR8_TO_CENTER = {
    "front": 0.0,
    "front-left": 45.0,
    "left": 90.0,
    "back-left": 135.0,
    "back": 180.0,
    "back-right": -135.0,
    "right": -90.0,
    "front-right": -45.0,
}


def _edge_angle_deg(edge: Dict) -> Optional[float]:
    metrics = edge.get("metrics", {}) or {}
    ang = metrics.get("angle", None)
    try:
        if ang is not None:
            return _normalize_angle_deg(float(ang))
    except Exception:
        pass
    center = _LEGACY_DIR8_TO_CENTER.get(str(edge.get("direction_8", "")))
    if center is not None:
        return float(center)
    return None

def import_filtered_sg_data_to_neo4j(
    data: Dict,
    *,
    neo4j_uri: Optional[str] = None,
    neo4j_user: Optional[str] = None,
    neo4j_pwd: Optional[str] = None,
    source_label: str = "inline",
) -> Dict:
    """
    将已在内存中过滤好的场景图 dict 导入 Neo4j（清空后写入）。
    """
    from neo4j import GraphDatabase

    _uri = neo4j_uri or os.getenv("NEO4J_URI", DEFAULT_NEO4J_URI)
    _user = neo4j_user if neo4j_user is not None else os.getenv("NEO4J_USER", "neo4j")
    _pwd = neo4j_pwd if neo4j_pwd is not None else os.getenv(
        "NEO4J_PASSWORD", os.getenv("NEO4J_PWD", "87017563")
    )

    logger.info(
        "Importing %s: %d nodes, %d edges",
        source_label,
        len(data.get("nodes", [])),
        len(data.get("edges", [])),
    )
    logger.info("Source: %s", source_label)

    driver = GraphDatabase.driver(_uri, auth=(_user, _pwd))
    try:
        with driver.session() as sess:
            sess.run("MATCH (n) DETACH DELETE n")
            n_nodes = 0
            for node in data["nodes"]:
                sess.run(
                    "CREATE (n:Object {unique_id: $uid, type: $type, status: $status})",
                    uid=node["unique_id"],
                    type=node["type"],
                    status=node.get("status", ""),
                )
                n_nodes += 1

            n_edges = 0
            for edge in data["edges"]:
                metrics = edge.get("metrics", {}) or {}
                ang = _edge_angle_deg(edge)
                if ang is not None:
                    d8 = _paper_direction_8(ang)
                    d4 = _direction_4_from_angle(ang)
                else:
                    d8 = edge.get("direction_8", "")
                    d4 = edge.get("direction_4", "")
                pred = list(edge.get("predicates", []) or [])
                if pred:
                    pred[0] = d8
                sess.run(
                    "MATCH (s:Object {unique_id:$src})"
                    " MATCH (t:Object {unique_id:$tgt})"
                    " CREATE (s)-[r:RELATES_TO {"
                    "   direction_4: $d4,"
                    "   direction_8: $d8,"
                    "   predicates:  $pred,"
                    "   distance:    $dist"
                    " }]->(t)",
                    src=edge["source"],
                    tgt=edge["target"],
                    d4=d4,
                    d8=d8,
                    pred=pred,
                    dist=metrics.get("distance", 0.0),
                )
                n_edges += 1

            try:
                sess.run("CREATE INDEX IF NOT EXISTS FOR (n:Object) ON (n.unique_id)")
            except Exception:
                pass

            v_nodes = sess.run("MATCH (n:Object) RETURN count(n) AS c").single()["c"]
            v_edges = sess.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS c").single()["c"]

        logger.info("✅ Neo4j: %d nodes, %d edges (source: %s)", v_nodes, v_edges, source_label)
        return {"n_nodes": v_nodes, "n_edges": v_edges, "source": source_label}
    finally:
        driver.close()


def import_filtered_sg_to_neo4j(
    sg_name: str,
    neo4j_uri: Optional[str] = None,
    neo4j_user: Optional[str] = None,
    neo4j_pwd: Optional[str] = None,
) -> Dict:
    """
    Import a filtered scene graph from FILTERED_SG_DIR into Neo4j.
    Clears existing data first.
    """
    sg_path = FILTERED_SG_DIR / sg_name
    if not sg_path.exists():
        raise FileNotFoundError(f"Filtered SG not found: {sg_path}")

    data = json.loads(sg_path.read_text(encoding="utf-8"))
    return import_filtered_sg_data_to_neo4j(
        data,
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_pwd=neo4j_pwd,
        source_label=str(sg_path.resolve()),
    )


if __name__ == "__main__":
    print("=" * 72)
    print("  Core Universe Filter (V21)")
    print(f"  Input : {RAW_SG_DIR}")
    print(f"  Output: {FILTERED_SG_DIR}")
    print(f"  Distance mode default: {DISTANCE_MODE_DEFAULT}")
    print(f"  Pixel mode default   : {PIXEL_MODE_DEFAULT}")
    print("=" * 72)
    results = filter_all_existing(
        distance_mode=DISTANCE_MODE_DEFAULT,
        pixel_mode=PIXEL_MODE_DEFAULT,
        min_visibility=MIN_VISIBILITY,
        output_dir=FILTERED_SG_DIR,
        write_excel=False,
    )
    print("\nSummary:")
    for (sname, fidx), info in sorted(results.items()):
        print(f"  {sname} frame-{fidx}: {info['n_nodes']} nodes  {info['n_edges']} edges  mode={info['distance_mode']}")
