import os
import sys
import urllib.request

# Auto-detect system proxy (especially Clash on Windows)
system_proxies = urllib.request.getproxies()
if "http" in system_proxies:
    os.environ["HTTP_PROXY"] = system_proxies["http"]
if "https" in system_proxies:
    os.environ["HTTPS_PROXY"] = system_proxies["https"]

# Set HF environment variables before any Hugging Face imports
os.environ["HF_ENDPOINT"] = "https://huggingface.co"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["HF_HOME"] = "E:\\hf_cache"

import ssl
import mmap

# urllib3 is only needed to silence SSL warnings for the remote API mode.
# Importing it on Windows has proven flaky (slow DLL/file reads that can be
# interrupted), so it is opt-in via ADVTEST_ENABLE_URLLIB3=1 and never blocks
# local/offline evaluator startup.
urllib3 = None
if os.environ.get("ADVTEST_ENABLE_URLLIB3") == "1":
    try:
        import urllib3
    except Exception:
        urllib3 = None

# Global patch to force TLS 1.2 and bypass SSL checks
original_init = ssl.SSLContext.__init__
def patched_ssl_context_init(self, *args, **kwargs):
    try:
        original_init(self, *args, **kwargs)
    except TypeError:
        try:
            original_init(self)
        except Exception:
            pass
    self.options |= ssl.OP_NO_TLSv1_3
    self.check_hostname = False
    self.verify_mode = ssl.CERT_NONE

ssl.SSLContext.__init__ = patched_ssl_context_init
if urllib3 is not None:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import re
import json
import math
import hashlib
import copy
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Any, List, Tuple, Optional

# Workspace root. Use absolute() instead of resolve() to avoid slow Windows
# final-path resolution on large/synced workspaces.
WORKSPACE_ROOT = Path(__file__).absolute().parents[4]

# --- PIL Mosaic Rendering Setup (derived from render_mosaic_from_sg.py) ---
CAM_ORDER = [
    'CAM_FRONT_LEFT', 'CAM_FRONT', 'CAM_FRONT_RIGHT',
    'CAM_BACK_LEFT', 'CAM_BACK', 'CAM_BACK_RIGHT'
]

def color_for(cat: str):
    CAT_COLORS = {
        'vehicle': (228, 26, 28),
        'human': (55, 126, 184),
        'movable_object': (152, 78, 163),
        'static_object': (255, 127, 0),
        'flat': (166, 86, 40),
    }
    prefix = cat.split('.')[0] if cat and '.' in cat else cat
    return CAT_COLORS.get(prefix, (80, 80, 80))

def draw_box(draw: ImageDraw.ImageDraw, bbox, color, width=2):
    x1, y1, x2, y2 = bbox
    draw.rectangle([(x1, y1), (x2, y2)], outline=color, width=width)

_SCENE_FRAME_MAP_CACHE = None

def get_sample_token(scene_graph: Dict[str, Any], dataroot: Path) -> Optional[str]:
    """Retrieve sample_token from scene graph or look it up in NuScenes metadata."""
    sample_token = scene_graph.get("sample_token")
    if sample_token:
        return sample_token

    scene_name = scene_graph.get("scene_name")
    frame_idx = scene_graph.get("frame_idx")
    if scene_name is None or frame_idx is None:
        return None

    global _SCENE_FRAME_MAP_CACHE
    if _SCENE_FRAME_MAP_CACHE is None:
        _SCENE_FRAME_MAP_CACHE = {}
        # Search for scene.json and sample.json under dataroot
        meta_dirs = [
            dataroot / "v1.0-mini",
            dataroot / "v1.0-trainval",
            dataroot / "v1.0-trainval02",
            dataroot / "v1.0-test",
            dataroot / "nuscenes" / "v1.0-mini",
            dataroot / "nuscenes" / "v1.0-trainval",
        ]
        scene_file = None
        sample_file = None
        for d in meta_dirs:
            if (d / "scene.json").exists() and (d / "sample.json").exists():
                scene_file = d / "scene.json"
                sample_file = d / "sample.json"
                break

        if not scene_file or not sample_file:
            # Recursive fallback
            for f in dataroot.rglob("scene.json"):
                if (f.parent / "sample.json").exists():
                    scene_file = f
                    sample_file = f.parent / "sample.json"
                    break

        if scene_file and sample_file:
            try:
                with open(scene_file, "r", encoding="utf-8") as f:
                    scenes = json.load(f)
                with open(sample_file, "r", encoding="utf-8") as f:
                    samples = json.load(f)

                st2name = {s["token"]: s["name"] for s in scenes}
                import collections
                s2tok = collections.defaultdict(list)
                for samp in samples:
                    s_name = st2name.get(samp["scene_token"], "")
                    if not s_name:
                        continue
                    s2tok[s_name].append((samp["token"], int(samp["timestamp"])))

                for s_name, toks in s2tok.items():
                    toks_sorted = sorted(toks, key=lambda x: x[1])
                    for idx, (tok, _) in enumerate(toks_sorted):
                        _SCENE_FRAME_MAP_CACHE[(s_name, idx)] = tok
            except Exception as e:
                print(f"Error mapping scene frame to sample token: {e}")

    return _SCENE_FRAME_MAP_CACHE.get((scene_name, frame_idx))

_SAMPLE_TOKEN_TO_CAM_FILES = None
_METADATA_RECORD_CACHE: Dict[Tuple[str, str], Dict[str, dict]] = {}



def _find_metadata_file(dataroot: Path, filename: str) -> Optional[Path]:
    meta_dirs = [
        dataroot / "v1.0-mini",
        dataroot / "v1.0-trainval",
        dataroot / "v1.0-trainval02",
        dataroot / "v1.0-test",
        dataroot / "nuscenes" / "v1.0-mini",
        dataroot / "nuscenes" / "v1.0-trainval",
    ]
    for directory in meta_dirs:
        candidate = directory / filename
        if candidate.exists():
            return candidate
    for candidate in dataroot.rglob(filename):
        return candidate
    return None


def _sample_images_index_cache_path(dataroot: Path) -> Path:
    safe_name = str(dataroot.absolute()).replace(":", "").replace("\\", "_").replace("/", "_")
    return WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "analysis" / "data_cache" / f"sample_images_{safe_name}.json"


def _load_sample_images_index(cache_path: Path) -> Optional[Dict[str, Dict[str, Path]]]:
    if not cache_path.exists():
        return None
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return {
            sample_token: {camera: Path(path) for camera, path in cameras.items()}
            for sample_token, cameras in cached.items()
        }
    except Exception as exc:
        print(f"Error loading sample image index cache: {exc}")
        return None


def _write_sample_images_index(cache_path: Path, mapping: Dict[str, Dict[str, Path]]) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            sample_token: {camera: str(path) for camera, path in cameras.items()}
            for sample_token, cameras in mapping.items()
        }
        cache_path.write_text(json.dumps(serializable, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        print(f"Error writing sample image index cache: {exc}")

def get_sample_images_map(dataroot: Path) -> Dict[str, Dict[str, Path]]:
    """Build or load a cached mapping from sample_token to 6 camera image paths."""
    global _SAMPLE_TOKEN_TO_CAM_FILES
    if _SAMPLE_TOKEN_TO_CAM_FILES is not None:
        return _SAMPLE_TOKEN_TO_CAM_FILES

    cache_path = _sample_images_index_cache_path(dataroot)
    cached = _load_sample_images_index(cache_path)
    if cached is not None:
        _SAMPLE_TOKEN_TO_CAM_FILES = cached
        return _SAMPLE_TOKEN_TO_CAM_FILES

    _SAMPLE_TOKEN_TO_CAM_FILES = {}
    sample_data_file = _find_metadata_file(dataroot, "sample_data.json")
    if not sample_data_file:
        return {}

    try:
        decoder = json.JSONDecoder()
        buffer = ""
        with sample_data_file.open("r", encoding="utf-8") as handle:
            handle.read(1)  # opening '['
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk and not buffer.strip():
                    break
                buffer += chunk
                while True:
                    buffer = buffer.lstrip(" \r\n\t,")
                    if not buffer or buffer[0] == "]":
                        break
                    try:
                        record, index = decoder.raw_decode(buffer)
                    except json.JSONDecodeError:
                        break
                    buffer = buffer[index:]
                    s_tok = record.get("sample_token")
                    filename = record.get("filename")
                    is_key = record.get("is_key_frame", True)
                    if not s_tok or not filename or not is_key:
                        continue
                    filename_clean = filename.replace("\\", "/")
                    if "samples/CAM_" not in filename_clean:
                        continue
                    matched_ch = None
                    for ch in CAM_ORDER:
                        if f"/{ch}/" in filename_clean:
                            matched_ch = ch
                            break
                    if matched_ch:
                        if s_tok not in _SAMPLE_TOKEN_TO_CAM_FILES:
                            _SAMPLE_TOKEN_TO_CAM_FILES[s_tok] = {}
                        abs_path = dataroot / filename
                        if not abs_path.exists():
                            abs_path = dataroot.parent / filename
                        _SAMPLE_TOKEN_TO_CAM_FILES[s_tok][matched_ch] = abs_path
                if not chunk:
                    break
        _write_sample_images_index(cache_path, _SAMPLE_TOKEN_TO_CAM_FILES)
    except Exception as e:
        print(f"Error loading sample_data mapping: {e}")

    return _SAMPLE_TOKEN_TO_CAM_FILES



def get_sample_camera_files(sample_token: str, dataroot: Path) -> Dict[str, Path]:
    """Find camera files for one sample_token without loading all sample_data.json."""
    cached_map = get_sample_images_map(dataroot) if _SAMPLE_TOKEN_TO_CAM_FILES else None
    if cached_map and sample_token in cached_map:
        return cached_map[sample_token]

    sample_data_file = _find_metadata_file(dataroot, "sample_data.json")
    if not sample_data_file:
        return {}
    camera_files: Dict[str, Path] = {}
    token_bytes = f'"sample_token": "{sample_token}"'.encode("utf-8")
    try:
        with sample_data_file.open("rb") as handle:
            with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                pos = 0
                while True:
                    hit = mm.find(token_bytes, pos)
                    if hit < 0:
                        break
                    start = mm.rfind(b"{", 0, hit)
                    end = mm.find(b"\n}", hit)
                    if start < 0 or end < 0:
                        break
                    block = mm[start : end + 2].decode("utf-8", errors="ignore")
                    record = json.loads(block)
                    filename = record.get("filename")
                    if filename and record.get("is_key_frame", True):
                        filename_clean = filename.replace("\\", "/")
                        if "samples/CAM_" in filename_clean:
                            for ch in CAM_ORDER:
                                if f"/{ch}/" in filename_clean:
                                    abs_path = dataroot / filename
                                    if not abs_path.exists():
                                        abs_path = dataroot.parent / filename
                                    camera_files[ch] = abs_path
                                    break
                    if len(camera_files) == len(CAM_ORDER):
                        break
                    pos = end + 2
    except Exception as exc:
        print(f"Error scanning camera files for {sample_token}: {exc}")
    return camera_files


def _records_by_token(dataroot: Path, filename: str) -> Dict[str, dict]:
    """Load a nuScenes metadata table keyed by token."""
    cache_key = (str(dataroot.absolute()), filename)
    if cache_key in _METADATA_RECORD_CACHE:
        return _METADATA_RECORD_CACHE[cache_key]
    table_path = _find_metadata_file(dataroot, filename)
    if not table_path:
        _METADATA_RECORD_CACHE[cache_key] = {}
        return {}
    try:
        records = json.loads(table_path.read_text(encoding="utf-8"))
        keyed = {str(row.get("token")): row for row in records if row.get("token")}
    except Exception as exc:
        print(f"Error loading {filename}: {exc}")
        keyed = {}
    _METADATA_RECORD_CACHE[cache_key] = keyed
    return keyed


def _sample_camera_records(sample_token: str, dataroot: Path) -> Dict[str, dict]:
    """Find sample_data records for the six key-frame cameras of one sample."""
    sample_data_file = _find_metadata_file(dataroot, "sample_data.json")
    if not sample_data_file:
        return {}
    records: Dict[str, dict] = {}
    token_bytes = f'"sample_token": "{sample_token}"'.encode("utf-8")
    try:
        with sample_data_file.open("rb") as handle:
            with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                pos = 0
                while True:
                    hit = mm.find(token_bytes, pos)
                    if hit < 0:
                        break
                    start = mm.rfind(b"{", 0, hit)
                    end = mm.find(b"\n}", hit)
                    if start < 0 or end < 0:
                        break
                    block = mm[start : end + 2].decode("utf-8", errors="ignore")
                    record = json.loads(block)
                    filename = str(record.get("filename") or "").replace("\\", "/")
                    if record.get("is_key_frame", True) and "samples/CAM_" in filename:
                        for ch in CAM_ORDER:
                            if f"/{ch}/" in filename:
                                records[ch] = record
                                break
                    if len(records) == len(CAM_ORDER):
                        break
                    pos = end + 2
    except Exception as exc:
        print(f"Error scanning camera metadata for {sample_token}: {exc}")
    return records


def _ensure_projected_visibility(
    scene_graph: Dict[str, Any],
    dataroot: Path,
    sample_token: str,
    image_sizes: Dict[str, Tuple[int, int]],
    min_corner_vis: int = 2,
) -> Dict[str, Any]:
    """Add visibility/bbox2d fields when a filtered scene graph lacks them."""
    nodes = scene_graph.get("nodes") or scene_graph.get("objects") or []
    if any((node.get("visibility") or {}) for node in nodes):
        return scene_graph

    try:
        import numpy as np
        from nuscenes.utils.data_classes import Box
        from nuscenes.utils.geometry_utils import view_points
        from pyquaternion import Quaternion
    except Exception as exc:
        print(f"[mosaic] nuScenes projection dependencies unavailable: {exc}")
        return scene_graph

    camera_records = _sample_camera_records(sample_token, dataroot)
    calibrated = _records_by_token(dataroot, "calibrated_sensor.json")
    ego_poses = _records_by_token(dataroot, "ego_pose.json")
    if not camera_records or not calibrated or not ego_poses:
        return scene_graph

    enriched = copy.deepcopy(scene_graph)
    enriched_nodes = enriched.get("nodes") or enriched.get("objects") or []
    for node in enriched_nodes:
        nid = node.get("id") or node.get("unique_id")
        node.setdefault("visibility", {})
        if nid == "ego":
            continue

        translation = node.get("translation")
        size = node.get("size")
        rotation = node.get("rotation")
        if not translation or not size or not rotation:
            continue
        try:
            center = [
                float(translation["x"]),
                float(translation["y"]),
                float(translation.get("z", 0.0)),
            ]
            wlh = [
                float(size["width"]),
                float(size["length"]),
                float(size.get("height", 1.0)),
            ]
            orientation = Quaternion(rotation)
            box = Box(center, wlh, orientation, name=str(node.get("type") or ""))
        except Exception:
            continue

        for ch in CAM_ORDER:
            sd = camera_records.get(ch)
            if not sd:
                continue
            cs = calibrated.get(str(sd.get("calibrated_sensor_token")))
            pose = ego_poses.get(str(sd.get("ego_pose_token")))
            if not cs or not pose:
                continue
            try:
                box_cam = box.copy()
                box_cam.translate(-np.array(pose["translation"], dtype=float))
                box_cam.rotate(Quaternion(pose["rotation"]).inverse)
                box_cam.translate(-np.array(cs["translation"], dtype=float))
                box_cam.rotate(Quaternion(cs["rotation"]).inverse)
                corners = box_cam.corners()
                if np.any(corners[2, :] <= 0):
                    continue
                corners_2d = view_points(
                    corners,
                    np.array(cs["camera_intrinsic"], dtype=float),
                    normalize=True,
                )[:2, :].T
                width, height = image_sizes.get(
                    ch,
                    (
                        int(sd.get("width") or 1600),
                        int(sd.get("height") or 900),
                    ),
                )
                xs = corners_2d[:, 0]
                ys = corners_2d[:, 1]
                inside = int(
                    np.sum((xs >= 0) & (xs < width) & (ys >= 0) & (ys < height))
                )
                if inside < min_corner_vis:
                    continue
                xmin = max(0.0, float(np.min(xs)))
                ymin = max(0.0, float(np.min(ys)))
                xmax = min(float(width - 1), float(np.max(xs)))
                ymax = min(float(height - 1), float(np.max(ys)))
                if xmax <= xmin or ymax <= ymin:
                    continue
                center_uv = view_points(
                    box_cam.center.reshape(3, 1),
                    np.array(cs["camera_intrinsic"], dtype=float),
                    normalize=True,
                )[:2, 0]
                node["visibility"][ch] = {
                    "visible": True,
                    "bbox2d": [xmin, ymin, xmax, ymax],
                    "center_uv": [float(center_uv[0]), float(center_uv[1])],
                    "depth": float(box_cam.center[2]),
                }
            except Exception:
                continue

    return enriched


def _label_rect(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[float, float],
    text: str,
    font,
    pad: int,
) -> Tuple[float, float, float, float]:
    x, y = xy
    try:
        bbox = draw.textbbox((x, y), text, font=font)
    except Exception:
        bbox = (x, y, x + 8 * len(text), y + 16)
    return (
        float(bbox[0] - pad),
        float(bbox[1] - pad),
        float(bbox[2] + pad),
        float(bbox[3] + pad),
    )


def _rect_intersection_area(
    a: Tuple[float, float, float, float],
    b: Tuple[float, float, float, float],
) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return (x2 - x1) * (y2 - y1)


def _clamp_label_xy(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[float, float],
    text: str,
    font,
    pad: int,
    canvas_size: Tuple[int, int],
) -> Tuple[float, float]:
    x, y = xy
    rect = _label_rect(draw, (x, y), text, font, pad)
    canvas_w, canvas_h = canvas_size
    if rect[0] < 0:
        x -= rect[0]
    if rect[1] < 0:
        y -= rect[1]
    rect = _label_rect(draw, (x, y), text, font, pad)
    if rect[2] > canvas_w:
        x -= rect[2] - canvas_w
    if rect[3] > canvas_h:
        y -= rect[3] - canvas_h
    return max(0.0, x), max(0.0, y)


def draw_label(
    draw: ImageDraw.ImageDraw,
    bbox: Tuple[float, float, float, float],
    text: str,
    color: Tuple[int, int, int],
    font,
    occupied: List[Tuple[float, float, float, float]],
    canvas_size: Tuple[int, int],
) -> None:
    x1, y1, x2, y2 = bbox
    pad = 3
    margin = 8
    try:
        tb = draw.textbbox((0, 0), text, font=font)
        label_w = tb[2] - tb[0] + pad * 2
        label_h = tb[3] - tb[1] + pad * 2
    except Exception:
        label_w = 8 * len(text) + pad * 2
        label_h = 16 + pad * 2

    # Try multiple positions around the box. This keeps labels readable when
    # many close objects appear in the same camera view.
    raw_candidates = [
        (x1, y1 - label_h - margin),                 # above-left
        (x2 - label_w, y1 - label_h - margin),       # above-right
        (x1, y2 + margin),                           # below-left
        (x2 - label_w, y2 + margin),                 # below-right
        (x1 - label_w - margin, y1),                 # left
        (x2 + margin, y1),                           # right
        (x1 + margin, y1 + margin),                  # inside-left
        (x2 - label_w - margin, y1 + margin),        # inside-right
    ]

    best_xy = None
    best_rect = None
    best_score = None
    for xy in raw_candidates:
        candidate_xy = _clamp_label_xy(draw, xy, text, font, pad, canvas_size)
        rect = _label_rect(draw, candidate_xy, text, font, pad)
        overlap = sum(_rect_intersection_area(rect, prev) for prev in occupied)
        box_overlap = _rect_intersection_area(rect, bbox) * 0.15
        # Prefer less overlap, then labels closer to their object.
        cx = (rect[0] + rect[2]) / 2.0
        cy = (rect[1] + rect[3]) / 2.0
        bx = (x1 + x2) / 2.0
        by = (y1 + y2) / 2.0
        distance_penalty = math.hypot(cx - bx, cy - by) * 0.01
        score = overlap + box_overlap + distance_penalty
        if best_score is None or score < best_score:
            best_xy = candidate_xy
            best_rect = rect
            best_score = score

    if best_xy is None or best_rect is None:
        best_xy = _clamp_label_xy(draw, (x1, y1), text, font, pad, canvas_size)
        best_rect = _label_rect(draw, best_xy, text, font, pad)

    bg = (
        max(0, color[0] // 4),
        max(0, color[1] // 4),
        max(0, color[2] // 4),
    )
    draw.rectangle(
        [(best_rect[0], best_rect[1]), (best_rect[2], best_rect[3])],
        fill=bg,
        outline=color,
        width=2,
    )
    draw.text(best_xy, text, fill=(255, 255, 255), font=font)

    # Draw a short pointer if the adaptive placement moves the label away.
    lx = (best_rect[0] + best_rect[2]) / 2.0
    ly = (best_rect[1] + best_rect[3]) / 2.0
    bx = min(max(lx, x1), x2)
    by = min(max(ly, y1), y2)
    if math.hypot(lx - bx, ly - by) > 12:
        draw.line([(lx, ly), (bx, by)], fill=color, width=2)

    occupied.append(best_rect)

def render_labeled_mosaic(scene_graph: Dict[str, Any], dataroot: Path, out_path: Path) -> bool:
    """Stitch 6 cameras and label bounding boxes with unique IDs (e.g. car17)."""
    sample_token = get_sample_token(scene_graph, dataroot)
    if not sample_token:
        return False

    cam_files = get_sample_camera_files(sample_token, dataroot)

    # Find sample images
    imgs = []
    image_sizes: Dict[str, Tuple[int, int]] = {}
    for ch in CAM_ORDER:
        img_path = cam_files.get(ch)
        if img_path and img_path.exists():
            image = Image.open(img_path).convert('RGB')
            image_sizes[ch] = image.size
            imgs.append(image)
        else:
            imgs.append(None)

    # Check if we have at least one image
    if not any(imgs):
        return False

    # Standardize dimensions
    widths = [im.width for im in imgs if im]
    heights = [im.height for im in imgs if im]
    W = max(widths) if widths else 1600
    H = max(heights) if heights else 900

    grid = []
    for im in imgs:
        if im is None:
            grid.append(Image.new('RGB', (W, H), (30, 30, 30)))
        else:
            grid.append(im.resize((W, H)) if im.size != (W, H) else im)

    mosaic = Image.new('RGB', (W*3, H*2), (0, 0, 0))
    positions = [(0,0), (W,0), (2*W,0), (0,H), (W,H), (2*W,H)]
    for (x,y), im in zip(positions, grid):
        mosaic.paste(im, (x,y))

    draw = ImageDraw.Draw(mosaic)
    try:
        font = ImageFont.truetype("arial.ttf", 56)
    except Exception:
        font = ImageFont.load_default()

    ch_to_offset = {CAM_ORDER[i]: positions[i] for i in range(len(CAM_ORDER))}
    scene_graph = _ensure_projected_visibility(
        scene_graph, dataroot, sample_token, image_sizes
    )

    # Draw boxes labeled with unique IDs (e.g. car17)
    nodes = scene_graph.get('nodes') or scene_graph.get('objects') or []
    occupied_labels: List[Tuple[float, float, float, float]] = []
    for n in nodes:
        nid = n.get('id') or n.get('unique_id')
        if not nid or nid == 'ego':
            continue
        vis = n.get('visibility') or {}
        cat = n.get('category_name') or n.get('category') or ''
        color = color_for(cat)
        draw_candidates = []
        for ch in CAM_ORDER:
            v = vis.get(ch)
            if not v or not v.get('visible'):
                continue
            bbox = v.get('bbox2d')
            if not bbox:
                continue
            (ox, oy) = ch_to_offset[ch]
            x1, y1, x2, y2 = bbox
            original_w, original_h = image_sizes.get(ch, (W, H))
            if original_w and original_h:
                sx = W / original_w
                sy = H / original_h
                x1, x2 = x1 * sx, x2 * sx
                y1, y2 = y1 * sy, y2 * sy
            mosaic_bbox = (ox+x1, oy+y1, ox+x2, oy+y2)
            area = max(0.0, (x2 - x1) * (y2 - y1))
            depth = float(v.get("depth") or 1e9)
            draw_candidates.append((-area, depth, mosaic_bbox))

        if not draw_candidates:
            continue
        _, _, mosaic_bbox = min(draw_candidates)
        draw_box(draw, mosaic_bbox, color, width=6)

        # Label box with unique ID
        draw_label(
            draw,
            mosaic_bbox,
            str(nid),
            color,
            font,
            occupied_labels,
            mosaic.size,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    mosaic.save(out_path)
    return True


# --- Answer Normalization and Evaluation logic ---
def normalize_answer(text: str) -> str:
    """Normalize VLM response text for matching."""
    if text is None:
        return ""
    text = str(text).lower().strip()
    text = text.replace("front left", "front-left")
    text = text.replace("front right", "front-right")
    text = text.replace("back left", "back-left")
    text = text.replace("back right", "back-right")
    # remove punctuation
    text = re.sub(r"[?.,\/#!$%\^&\*;:{}=\-_`~()]", "", text)
    # collapse multiple spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def check_correctness(predicted: str, ground_truth: str) -> bool:
    """Check if VLM prediction matches the ground truth answer."""
    pred_norm = normalize_answer(predicted)
    gt_norm = normalize_answer(ground_truth)

    if not gt_norm or not pred_norm:
        return False

    # Boolean comparison
    if gt_norm in ('true', 'yes'):
        return bool(re.search(r"\b(?:true|yes)\b", pred_norm))
    if gt_norm in ('false', 'no'):
        return bool(re.search(r"\b(?:false|no)\b", pred_norm))

    # Number comparison
    if gt_norm.isdigit():
        numbers = re.findall(r'\b\d+\b', pred_norm)
        return gt_norm in numbers

    # Keyword or phrase comparison (e.g. left, right, car2, truck4).
    # Match the complete normalized answer, not a substring of another token.
    return bool(
        re.search(
            rf"(?<!\w){re.escape(gt_norm)}(?!\w)",
            pred_norm,
        )
    )


def _matches_choice_label(predicted: str, label: str) -> bool:
    """Return True when the model clearly selects a multiple-choice label."""
    if not label:
        return False
    label_norm = str(label).lower().strip()
    pred = str(predicted or "").lower().strip()
    if not pred:
        return False
    return bool(
        re.match(
            rf"^(?:option\s*)?{re.escape(label_norm)}(?:\s*[\).:,-]|\s*$)",
            pred,
        )
    )


def check_question_correctness(predicted: str, question: Dict[str, Any]) -> bool:
    """Check correctness with optional multiple-choice metadata."""
    if check_correctness(predicted, str(question.get("answer", ""))):
        return True

    if not question.get("choices"):
        return False

    choice_text = str(question.get("choice_answer_text") or "")
    if choice_text and check_correctness(predicted, choice_text):
        return True

    return _matches_choice_label(
        predicted,
        str(question.get("choice_answer_label") or ""),
    )


def build_vlm_prompt(question: Dict[str, Any]) -> str:
    return str(question.get("question", ""))


# --- Evaluator Classes ---
class MockVLMEvaluator:
    """Deterministic failure simulation based on question complexity and metamorphic mutations."""
    def __init__(self, seed: int = 42):
        pass

    def evaluate(self, question: Dict) -> Tuple[str, bool]:
        """
        Simulate VLM failure. Returns (predicted_answer, is_correct).
        Fails probabilistically based on path length (hops) and constraint count.
        Also penalizes text-level mutations (QATest) and models simpler QAAskeR follow-ups.
        """
        q_id = str(question.get("question_id", ""))
        q_text = question.get("question", "")
        gt = str(question.get("answer", ""))
        family = str(question.get("l2_family") or question.get("template_id", "")).lower()

        # Deterministic hash seed based on question content (using MD5)
        h_str = f"{q_id}_{q_text}"
        h_digest = hashlib.md5(h_str.encode('utf-8')).hexdigest()
        score = int(h_digest[:8], 16) / 4294967295.0  # Normalized float in [0, 1)

        # Calculate base error rate
        hops = 2 if question.get("topology_level") == "L2" else 1
        constraints = int(question.get("constraint_count") or 0)

        # Base error probability: more hops and more constraints increase error probability
        # 1 hop, 0 constraints: ~10% error
        # 2 hops, 0 constraints: ~19% error
        # 2 hops, 1 constraint: ~23% error
        error_prob = 1.0 - (0.9 ** hops) * (0.95 ** constraints)

        # Viewpoint transfer has coordinate changes, making it harder for VLMs
        if "viewpoint" in family:
            error_prob += 0.15

        # Typos/Fuzzing penalty (QATest)
        if question.get("is_fuzzed") or question.get("qatest_mutated"):
            error_prob += 0.15  # increase error chance due to typos/fuzzing noise

        # Simpler follow-up question model (QAAskeR)
        if question.get("is_qaasker_followup"):
            error_prob = max(0.05, error_prob - 0.1)  # easier to answer simple binary verification

        is_correct = score >= error_prob
        predicted = gt if is_correct else "incorrect_prediction"
        return predicted, is_correct


class MPLUGEvaluator:
    """mPLUG-Owl2 VLM Evaluator for GPU deployment."""
    def __init__(self, model_path: str = "models/mplug-owl2-llama2-7b"):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.image_processor = None
        self.device = "cuda"

        # Dynamically inject mPLUG-Owl2 package path
        mplug_path = str(WORKSPACE_ROOT / "baselines" / "mPLUG-Owl" / "mPLUG-Owl2")
        if mplug_path not in sys.path:
            sys.path.insert(0, mplug_path)

        self._load_model()

    def _load_model(self):
        try:
            import torch
            from mplug_owl2.model.builder import load_pretrained_model
            from mplug_owl2.mm_utils import get_model_name_from_path

            # Check if there is a ModelScope cache first
            modelscope_path = Path("E:/hf_cache/modelscope/iic/mPLUG-Owl2")
            model_path_to_use = self.model_path
            if modelscope_path.exists():
                print(f"Using local ModelScope path: {modelscope_path}")
                model_path_to_use = str(modelscope_path)
            elif not Path(model_path_to_use).exists():
                print(f"Local path {self.model_path} not found. Using Hugging Face repo ID 'MAGAer13/mplug-owl2-llama2-7b'...")
                model_path_to_use = "MAGAer13/mplug-owl2-llama2-7b"

            print(f"Loading mPLUG-Owl2 model from {model_path_to_use}...")
            model_name = get_model_name_from_path(model_path_to_use)

            # Use 4-bit quantization to load successfully on local 8GB GPU (e.g. RTX 3070)
            self.tokenizer, self.model, self.image_processor, self.context_len = load_pretrained_model(
                model_path_to_use,
                model_base=None,
                model_name=model_name,
                device_map="auto",
                load_4bit=True
            )
            print("mPLUG-Owl2 model loaded successfully.")
        except Exception as e:
            self.model = None
            raise RuntimeError(
                f"Could not load mPLUG-Owl2 from {self.model_path}"
            ) from e

    def evaluate(self, question: Dict, image_path: Path) -> Tuple[str, bool]:
        if not self.model:
            raise RuntimeError("mPLUG-Owl2 model is not loaded")
        if not image_path.exists():
            raise FileNotFoundError(f"mPLUG-Owl2 input image does not exist: {image_path}")

        try:
            import torch
            from PIL import Image
            from mplug_owl2.constants import IMAGE_TOKEN_INDEX, DEFAULT_IMAGE_TOKEN
            from mplug_owl2.conversation import conv_templates, SeparatorStyle
            from mplug_owl2.mm_utils import tokenizer_image_token, KeywordsStoppingCriteria

            q_text = build_vlm_prompt(question)
            gt = str(question.get("answer", ""))

            prompt = DEFAULT_IMAGE_TOKEN + "\n" + q_text

            conv = conv_templates["mplug_owl2"].copy()
            conv.append_message(conv.roles[0], prompt)
            conv.append_message(conv.roles[1], None)
            prompt_formatted = conv.get_prompt()

            input_ids = tokenizer_image_token(prompt_formatted, self.tokenizer, IMAGE_TOKEN_INDEX, return_tensors='pt').unsqueeze(0).to(self.device)

            image = Image.open(image_path).convert('RGB')
            image_tensor = self.image_processor.preprocess(image, return_tensors='pt')['pixel_values'][0].half().to(self.device).unsqueeze(0)

            stop_str = conv.sep if conv.sep_style == SeparatorStyle.SINGLE else conv.sep2
            stopping_criteria = KeywordsStoppingCriteria([stop_str], self.tokenizer, input_ids)

            with torch.inference_mode():
                output_ids = self.model.generate(
                    input_ids,
                    images=image_tensor,
                    do_sample=False,
                    temperature=0.0,
                    max_new_tokens=int(question.get("max_new_tokens", 50)),
                    stopping_criteria=[stopping_criteria],
                    use_cache=True
                )

            input_token_len = input_ids.shape[1]
            outputs = self.tokenizer.batch_decode(output_ids[:, input_token_len:], skip_special_tokens=True)[0]
            outputs = outputs.strip()

            if outputs.endswith(stop_str):
                outputs = outputs[:-len(stop_str)]
            outputs = outputs.strip()

            is_correct = check_correctness(outputs, gt)
            return outputs, is_correct

        except Exception as e:
            raise RuntimeError("mPLUG-Owl2 inference failed") from e


class LocalGPUEvaluator:
    """Local Qwen2-VL-2B-Instruct VLM Evaluator."""
    def __init__(self, model_path: str = "models/Qwen2-VL-2B-Instruct"):
        self.model_path = model_path
        self.model = None
        self.processor = None
        self.device = "cuda"
        self._load_model()

    def _load_model(self):
        try:
            import torch
            from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
            print(f"Loading Qwen2-VL model from {self.model_path}...")
            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16,
                device_map="auto"
            )
            self.processor = AutoProcessor.from_pretrained(self.model_path)
            print("Qwen2-VL loaded successfully on CUDA.")
        except Exception as e:
            print(f"Error loading local GPU model: {e}. Falling back to MOCK mode.")
            self.model = None

    def evaluate(self, question: Dict, image_path: Path) -> Tuple[str, bool]:
        if not self.model or not image_path.exists():
            return MockVLMEvaluator().evaluate(question)

        try:
            from transformers import Qwen2VLForConditionalGeneration
            import torch

            q_text = build_vlm_prompt(question)
            gt = str(question.get("answer", ""))

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": str(image_path)},
                        {"type": "text", "text": q_text}
                    ]
                }
            ]
            text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

            inputs = self.processor(
                text=[text],
                images=Image.open(image_path),
                padding=True,
                return_tensors="pt"
            ).to(self.device)

            with torch.no_grad():
                generated_ids = self.model.generate(**inputs, max_new_tokens=50)

            generated_ids_trimmed = [
                out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            output_text = self.processor.batch_decode(
                generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0]

            is_correct = check_correctness(output_text, gt)
            return output_text, is_correct
        except Exception as e:
            print(f"Inference error: {e}. Falling back to MOCK.")
            return MockVLMEvaluator().evaluate(question)


class MiniCPMOEvaluator:
    """MiniCPM-o-2_6 VLM Evaluator for local GPU."""
    def __init__(self, model_path: str = "openbmb/MiniCPM-o-2_6"):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.device = "cuda"
        self._load_model()

    def _load_model(self):
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer, BitsAndBytesConfig

            # Check if there is a ModelScope cache first
            modelscope_path = Path("E:/hf_cache/modelscope/openbmb/MiniCPM-o-2_6")
            model_path_to_use = self.model_path
            if modelscope_path.exists():
                print(f"Using local ModelScope path: {modelscope_path}")
                model_path_to_use = str(modelscope_path)

            print(f"Loading MiniCPM-o-2_6 model from {model_path_to_use}...")

            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True
            )

            self.model = AutoModel.from_pretrained(
                model_path_to_use,
                trust_remote_code=True,
                quantization_config=quantization_config,
                device_map="auto",
                init_vision=True,
                init_audio=False,
                init_tts=False
            )
            self.model.eval()
            self.tokenizer = AutoTokenizer.from_pretrained(model_path_to_use, trust_remote_code=True)
            print("MiniCPM-o-2_6 model loaded successfully.")
        except Exception as e:
            print(f"Warning: Could not load MiniCPM-o-2_6 from {self.model_path}: {e}")
            print("Graceful fallback to MockVLMEvaluator.")
            self.model = None

    def evaluate(self, question: Dict, image_path: Path) -> Tuple[str, bool]:
        if not self.model or not image_path.exists():
            return MockVLMEvaluator().evaluate(question)

        try:
            from PIL import Image
            q_text = build_vlm_prompt(question)
            gt = str(question.get("answer", ""))

            image = Image.open(image_path).convert('RGB')
            msgs = [{'role': 'user', 'content': f"<image>\n{q_text}"}]

            outputs = self.model.chat(
                image=image,
                msgs=msgs,
                tokenizer=self.tokenizer
            )
            outputs = str(outputs).strip()
            is_correct = check_correctness(outputs, gt)
            return outputs, is_correct
        except Exception as e:
            print(f"MiniCPM-o inference error: {e}. Falling back to MOCK.")
            return MockVLMEvaluator().evaluate(question)


class APIEvaluator:
    """API-based VLM Evaluator (GPT-4o-mini)."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                print("openai package not installed. API Mode unavailable.")

    def evaluate(self, question: Dict, image_path: Path) -> Tuple[str, bool]:
        if not self.client or not image_path.exists():
            return MockVLMEvaluator().evaluate(question)

        try:
            import base64
            q_text = build_vlm_prompt(question)
            gt = str(question.get("answer", ""))

            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": q_text},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{encoded_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=50
            )
            output_text = response.choices[0].message.content
            is_correct = check_correctness(output_text, gt)
            return output_text, is_correct
        except Exception as e:
            print(f"API inference error: {e}. Falling back to MOCK.")
            return MockVLMEvaluator().evaluate(question)
