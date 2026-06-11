"""
V17 现场构建场景图：从 nuScenes 元数据生成原始图 → core_universe_filter 过滤 → 内存 dict。

不读写 filtered_scene_graphs/ 目录。需配置 NUSCENES_DATAROOT、NUSCENES_VERSION、NUSCENES_DEVKIT_PATH。
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger("v17_onthefly_sg")


_cached_nusc = None
_cached_key: Optional[tuple] = None


def _get_generator():
    """同一进程内复用 NuScenes + Generator，避免 6011 次重复加载。"""
    global _cached_nusc, _cached_key
    import config as core_config

    devkit = str(getattr(core_config, "NUSCENES_DEVKIT_PATH", "") or "").strip()
    if devkit and devkit not in sys.path:
        sys.path.insert(0, devkit)

    from generate_selected_scenes_improved import (
        SceneGraphConfig,
        SceneGraphGenerator,
        setup_environment,
    )
    try:
        from nuscenes.nuscenes import NuScenes
    except ImportError as exc:
        raise RuntimeError(
            "无法导入 nuscenes（请 pip install nuscenes-devkit 或将 NUSCENES_DEVKIT_PATH 设为 python-sdk 目录）"
        ) from exc

    cfg = SceneGraphConfig.from_config(core_config)
    key = (cfg.nuscenes_version, cfg.nuscenes_dataroot, devkit)
    if _cached_nusc is None or _cached_key != key:
        setup_environment(cfg.devkit_path)
        _cached_nusc = NuScenes(version=cfg.nuscenes_version, dataroot=cfg.nuscenes_dataroot, verbose=False)
        _cached_key = key
    gen = SceneGraphGenerator(_cached_nusc, cfg)
    return gen


def build_filtered_sg_onthefly(scene_id: str, frame_id: int) -> Dict[str, Any]:
    """
    现场生成并过滤（进程内缓存 NuScenes 句柄，适合大批量）。
    返回的 dict 含 nodes/edges/core_universe_filter，可直接导入 Neo4j。
    """
    gen = _get_generator()
    raw = gen.generate(scene_id, frame_id)
    if not raw:
        raise RuntimeError(f"场景图生成失败: {scene_id} frame {frame_id}")

    from core_universe_filter import (
        DISTANCE_MODE_DEFAULT,
        MIN_VISIBILITY,
        PIXEL_MODE_DEFAULT,
        filter_scene_graph,
    )

    distance_mode = os.getenv("VQA_DISTANCE_MODE", DISTANCE_MODE_DEFAULT)
    pixel_mode = os.getenv("VQA_PIXEL_MODE", PIXEL_MODE_DEFAULT)
    min_vis = float(os.getenv("VQA_FILTER_MIN_VISIBILITY", str(MIN_VISIBILITY)))

    filtered = filter_scene_graph(
        raw,
        distance_mode=distance_mode,
        pixel_mode=pixel_mode,
        min_visibility=min_vis,
    )
    logger.info(
        "onthefly %s f%s: raw=%s filtered=%s",
        scene_id,
        frame_id,
        len(raw.get("nodes", [])),
        filtered.get("core_universe_filter", {}).get("filtered_nodes", "?"),
    )
    return filtered
