"""
step1_unpack_metadata.py
========================
解压 nuScenes v1.0-trainval metadata 包，并校验 13 个 JSON 是否齐全。

用法：
    python step1_unpack_metadata.py
    python step1_unpack_metadata.py --meta-tgz "E:\\path\\to\\v1.0-trainval_meta.tgz"
    python step1_unpack_metadata.py --dataroot "E:\\Project\\ADVTEST\\dataset\\Trainval"

默认假设 meta tgz 与 blob tarball 同目录：
    E:\\Project\\ADVTEST\\dataset\\Trainval\\v1.0-trainval_meta.tgz
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tarfile
from pathlib import Path
from typing import List

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("step1")

DEFAULT_DATAROOT = Path(r"E:\Project\ADVTEST\dataset\Trainval")
NUSCENES_VERSION = "v1.0-trainval"

REQUIRED_JSONS: List[str] = [
    "attribute.json",
    "calibrated_sensor.json",
    "category.json",
    "ego_pose.json",
    "instance.json",
    "log.json",
    "map.json",
    "sample.json",
    "sample_annotation.json",
    "sample_data.json",
    "scene.json",
    "sensor.json",
    "visibility.json",
]


def find_meta_tgz(dataroot: Path, override: Path | None) -> Path:
    if override is not None:
        if not override.exists():
            raise FileNotFoundError(f"--meta-tgz 不存在: {override}")
        return override
    candidates = [
        dataroot / "v1.0-trainval_meta.tgz",
        dataroot / "v1.0-trainval-meta.tgz",
        dataroot / "v1.0-trainval_metadata.tgz",
    ]
    for c in candidates:
        if c.exists():
            return c
    # 模糊搜索
    matches = list(dataroot.glob("*meta*.tgz")) + list(dataroot.glob("*meta*.tar.gz"))
    if matches:
        return matches[0]
    raise FileNotFoundError(
        f"在 {dataroot} 没找到 metadata 包。\n"
        f"请用 --meta-tgz 显式指定，或确认文件名包含 'meta'。"
    )


def already_extracted(meta_dir: Path) -> bool:
    if not meta_dir.exists():
        return False
    have = {p.name for p in meta_dir.glob("*.json")}
    return set(REQUIRED_JSONS).issubset(have)


def unpack(meta_tgz: Path, dataroot: Path) -> None:
    logger.info("解压 %s -> %s", meta_tgz.name, dataroot)
    dataroot.mkdir(parents=True, exist_ok=True)
    # metadata tgz 内部结构是 v1.0-trainval/*.json，直接解到 dataroot 即可
    with tarfile.open(meta_tgz, "r:gz") as tf:
        members = tf.getmembers()
        logger.info("  archive 含 %d 个条目", len(members))
        tf.extractall(path=dataroot)
    logger.info("✓ 解压完成")


def verify(meta_dir: Path) -> bool:
    logger.info("校验 metadata: %s", meta_dir)
    if not meta_dir.exists():
        logger.error("✗ 目录不存在: %s", meta_dir)
        return False

    missing: List[str] = []
    sizes = {}
    for name in REQUIRED_JSONS:
        p = meta_dir / name
        if not p.exists():
            missing.append(name)
        else:
            sizes[name] = p.stat().st_size

    if missing:
        logger.error("✗ 缺失 %d 个 JSON: %s", len(missing), missing)
        return False

    # 抽样解析最关键的几个，确认不是损坏文件
    for critical in ("scene.json", "sample.json", "sample_data.json"):
        try:
            with open(meta_dir / critical, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("  %-26s OK  records=%d  size=%.1f MB",
                        critical, len(data), sizes[critical] / 1024 / 1024)
        except Exception as exc:
            logger.error("✗ %s 解析失败: %s", critical, exc)
            return False

    # 其余只报大小
    for name in REQUIRED_JSONS:
        if name in ("scene.json", "sample.json", "sample_data.json"):
            continue
        logger.info("  %-26s OK  size=%.1f MB", name, sizes[name] / 1024 / 1024)

    total_mb = sum(sizes.values()) / 1024 / 1024
    logger.info("✓ 全部 13 个 metadata JSON 齐全, 总大小 %.1f MB", total_mb)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataroot", type=Path, default=DEFAULT_DATAROOT,
                    help=f"NUSCENES_DATAROOT 路径 (default: {DEFAULT_DATAROOT})")
    ap.add_argument("--meta-tgz", type=Path, default=None,
                    help="metadata 包路径（不指定则在 dataroot 下自动找）")
    ap.add_argument("--force", action="store_true",
                    help="即使 v1.0-trainval/ 已存在也重新解压")
    args = ap.parse_args()

    dataroot: Path = args.dataroot
    meta_dir = dataroot / NUSCENES_VERSION

    if already_extracted(meta_dir) and not args.force:
        logger.info("v1.0-trainval/ 已存在且 13 个 JSON 齐全, 跳过解压")
    else:
        meta_tgz = find_meta_tgz(dataroot, args.meta_tgz)
        logger.info("metadata 包: %s (%.1f MB)", meta_tgz, meta_tgz.stat().st_size / 1024 / 1024)
        unpack(meta_tgz, dataroot)

    ok = verify(meta_dir)
    if not ok:
        logger.error("校验失败, 请检查或重新下载 metadata 包")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Step 1 完成")
    logger.info("  NUSCENES_DATAROOT = %s", dataroot)
    logger.info("  NUSCENES_VERSION  = %s", NUSCENES_VERSION)
    logger.info("下一步: python step2_build_target_filelist.py")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
