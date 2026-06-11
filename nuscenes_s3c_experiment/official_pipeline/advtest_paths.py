"""
统一站点路径与 Neo4j 连接参数（单文件，避免漏拷子模块）

服务器通常只需设置 **ADVTEST_ROOT**；其余由环境变量覆盖，见下方列表。

**推荐**
  ADVTEST_ROOT            数据包根目录（未设置时 Windows 默认 E:\\Project\\ADVTEST）

**常用覆盖**
  NUSCENES_DATAROOT       默认 $ADVTEST_ROOT/data
  NUSCENES_VERSION        默认 v1.0-trainval
  VQA_NUSCENES_VERSION    若设置则优先于 NUSCENES_VERSION
  VQA_TRAINVAL_META       默认 $NUSCENES_DATAROOT/$NUSCENES_VERSION
  VQA_QA_JSON             默认 $ADVTEST_ROOT/data/NuScenes_val_questions.json
  ADVTEST_EXCEL_PATH      默认 $ADVTEST_ROOT/RQ(1).xlsx
  ADVTEST_GEN_QA_DIR      默认 $ADVTEST_ROOT/generated_qa
  FILTERED_SG_DIR         默认 $ADVTEST_ROOT/filtered_scene_graphs
  ADVTEST_RAW_SG_DIR      可选
  NUSCENES_DEVKIT_PATH    Linux 常留空，用 pip install nuscenes-devkit
  NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD（或 NEO4J_PWD）

**请先** ``load_advtest_env()`` **再首次依赖本模块**（或由 load_advtest_env 内刷新）。

**PYTHONPATH（可选）**：若不在 ``official_pipeline`` 目录下运行，可设
``export PYTHONPATH=/path/to/DATA_new/code/official_pipeline:/path/to/DATA_new/code``
（第二段用于 ``import vqa_pipeline``；``advtest_env`` 也会自动插入 ``code``）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── Neo4j 默认 ───────────────────────────────────────────────────────────────
FALLBACK_NEO4J_URI = "bolt://localhost:7687"
DEFAULT_NEO4J_URI = FALLBACK_NEO4J_URI

_DEFAULT_WIN_ROOT = r"E:\Project\ADVTEST"


@dataclass(frozen=True)
class SiteConfig:
    advtest_root: Path
    nuscenes_dataroot: Path
    nuscenes_version: str
    trainval_meta: Path
    vqa_qa_json: Path
    excel_path: Path
    gen_qa_dir: Path
    filtered_sg_dir: Path
    raw_sg_dir: Path
    nuscenes_devkit_path: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str

    def summary_lines(self) -> list[str]:
        return [
            f"ADVTEST_ROOT        = {self.advtest_root}",
            f"NUSCENES_DATAROOT   = {self.nuscenes_dataroot}",
            f"NUSCENES_VERSION    = {self.nuscenes_version}",
            f"TRAINVAL_META       = {self.trainval_meta}",
            f"VQA_QA_JSON         = {self.vqa_qa_json}",
            f"ADVTEST_EXCEL_PATH  = {self.excel_path}",
            f"ADVTEST_GEN_QA_DIR  = {self.gen_qa_dir}",
            f"FILTERED_SG_DIR     = {self.filtered_sg_dir}",
            f"NEO4J_URI           = {self.neo4j_uri}",
        ]


_site_cache: Optional[SiteConfig] = None


def _looks_like_windows_abs_path(s: str) -> bool:
    """识别从 Windows .env 误拷的盘符路径（在 Linux 上不可用）。"""
    t = (s or "").strip().replace("\\", "/")
    return len(t) >= 2 and t[0].isalpha() and t[1] == ":"


def _path_from_env(key: str, fallback: Path) -> Path:
    """
    读环境变量为路径；在 POSIX 上若值为 Windows 盘符路径则忽略并退回 fallback，
    避免 advtest_runtime.env 从本机复制后把 E:/... 带到服务器。
    """
    raw = os.getenv(key, "").strip()
    if not raw:
        return Path(fallback).expanduser()
    if os.name != "nt" and _looks_like_windows_abs_path(raw):
        import warnings

        warnings.warn(
            f"忽略环境变量 {key}={raw!r}（在 Linux 上为 Windows 路径），改用 {fallback}",
            UserWarning,
            stacklevel=2,
        )
        return Path(fallback).expanduser()
    return Path(raw).expanduser()


def _default_advtest_root() -> Path:
    return Path(os.getenv("ADVTEST_ROOT", _DEFAULT_WIN_ROOT)).expanduser().resolve()


def _build_site() -> SiteConfig:
    root = _default_advtest_root()

    nuscenes_dataroot = _path_from_env("NUSCENES_DATAROOT", root / "data")
    nuscenes_version = (
        os.getenv("VQA_NUSCENES_VERSION", "").strip()
        or os.getenv("NUSCENES_VERSION", "").strip()
        or "v1.0-trainval"
    )
    trainval_meta = _path_from_env(
        "VQA_TRAINVAL_META",
        nuscenes_dataroot / nuscenes_version,
    )

    vqa_qa_json = _path_from_env(
        "VQA_QA_JSON",
        root / "data" / "NuScenes_val_questions.json",
    )

    # 默认与 DATA_new 部署一致；若仍用根目录 RQ(1).xlsx 请设 ADVTEST_EXCEL_PATH
    excel_path = _path_from_env(
        "ADVTEST_EXCEL_PATH", root / "data" / "RQ_nuscenesqa_val_full.xlsx"
    )
    gen_qa_dir = _path_from_env("ADVTEST_GEN_QA_DIR", root / "generated_qa")
    filtered_sg_dir = _path_from_env(
        "FILTERED_SG_DIR", root / "filtered_scene_graphs"
    )
    raw_sg_dir = _path_from_env(
        "ADVTEST_RAW_SG_DIR",
        root
        / "nuscenes_s3c_experiment"
        / "output"
        / "coverage_analysis"
        / "scene_graphs",
    )

    win = os.name == "nt"
    devkit_default = (
        r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
        if win
        else ""
    )
    _dk = os.getenv("NUSCENES_DEVKIT_PATH", devkit_default).strip()
    if os.name != "nt" and _looks_like_windows_abs_path(_dk):
        import warnings

        warnings.warn(
            f"忽略 NUSCENES_DEVKIT_PATH={_dk!r}（Windows 路径）；Linux 请用 pip nuscenes-devkit 或留空",
            UserWarning,
            stacklevel=2,
        )
        nuscenes_devkit_path = ""
    else:
        nuscenes_devkit_path = _dk

    neo4j_uri = os.getenv("NEO4J_URI", FALLBACK_NEO4J_URI).strip() or FALLBACK_NEO4J_URI
    neo4j_user = os.getenv("NEO4J_USER", "neo4j").strip() or "neo4j"
    neo4j_password = (
        os.getenv("NEO4J_PASSWORD", os.getenv("NEO4J_PWD", "87017563")) or ""
    )

    return SiteConfig(
        advtest_root=root,
        nuscenes_dataroot=nuscenes_dataroot,
        nuscenes_version=nuscenes_version,
        trainval_meta=trainval_meta,
        vqa_qa_json=vqa_qa_json,
        excel_path=excel_path,
        gen_qa_dir=gen_qa_dir,
        filtered_sg_dir=filtered_sg_dir,
        raw_sg_dir=raw_sg_dir,
        nuscenes_devkit_path=nuscenes_devkit_path,
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
    )


def invalidate_site_cache() -> None:
    global _site_cache
    _site_cache = None


def get_site(*, force_reload: bool = False) -> SiteConfig:
    global _site_cache
    if _site_cache is not None and not force_reload:
        return _site_cache
    _site_cache = _build_site()
    return _site_cache


def print_site_banner(title: str = "[SiteConfig]") -> None:
    print(title)
    for line in get_site().summary_lines():
        print(" ", line)


# ── 模块级别名（refresh 后更新）──────────────────────────────────────────────
ADVTEST_ROOT: Path = Path(".")
NUSCENES_DATAROOT: Path = Path(".")
NUSCENES_VERSION: str = ""
TRAINVAL_META: Path = Path(".")
VQA_QA_JSON: Path = Path(".")
EXCEL_PATH: Path = Path(".")
GEN_QA_DIR: Path = Path(".")
FILTERED_SG_DIR: Path = Path(".")
RAW_SG_DIR: Path = Path(".")
NUSCENES_DEVKIT_PATH: str = ""
NEO4J_URI: str = FALLBACK_NEO4J_URI
NEO4J_USER: str = "neo4j"
NEO4J_PASSWORD: str = ""


def refresh_module_paths() -> None:
    """在 load_advtest_env 之后调用，使本模块全局变量与当前 os.environ 一致。"""
    invalidate_site_cache()
    s = get_site()
    global ADVTEST_ROOT, NUSCENES_DATAROOT, NUSCENES_VERSION, TRAINVAL_META
    global VQA_QA_JSON, EXCEL_PATH, GEN_QA_DIR, FILTERED_SG_DIR, RAW_SG_DIR
    global NUSCENES_DEVKIT_PATH, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    ADVTEST_ROOT = s.advtest_root
    NUSCENES_DATAROOT = s.nuscenes_dataroot
    NUSCENES_VERSION = s.nuscenes_version
    TRAINVAL_META = s.trainval_meta
    VQA_QA_JSON = s.vqa_qa_json
    EXCEL_PATH = s.excel_path
    GEN_QA_DIR = s.gen_qa_dir
    FILTERED_SG_DIR = s.filtered_sg_dir
    RAW_SG_DIR = s.raw_sg_dir
    NUSCENES_DEVKIT_PATH = s.nuscenes_devkit_path
    NEO4J_URI = s.neo4j_uri
    NEO4J_USER = s.neo4j_user
    NEO4J_PASSWORD = s.neo4j_password
    try:
        FILTERED_SG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


refresh_module_paths()


def require_trainval_meta() -> None:
    if not TRAINVAL_META.is_dir():
        raise FileNotFoundError(
            f"Trainval 元数据目录不存在: {TRAINVAL_META}\n"
            f"请确认 NUSCENES_DATAROOT={NUSCENES_DATAROOT} 下含 {NUSCENES_VERSION}/"
        )
    for name in ("scene.json", "sample.json"):
        p = TRAINVAL_META / name
        if not p.is_file():
            raise FileNotFoundError(f"缺少 {p}")


def require_qa_json() -> None:
    if not VQA_QA_JSON.is_file():
        raise FileNotFoundError(f"NuScenes-QA val JSON 不存在: {VQA_QA_JSON}")
