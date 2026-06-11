"""
step4_verify_and_pack.py
========================
校验抽出的 JPG 是否齐全, 并可选打包为 tar.gz 供上传服务器。

校验项:
  - 白名单里每个文件都已落盘
  - 每个 sample_token 都有 6 路相机
  - metadata 13 个 JSON 齐全

打包内容 (--pack 时):
  - v1.0-trainval/*.json   (metadata)
  - samples/CAM_*/*.jpg    (6019 帧 × 6 相机)
  - test6019_bundle/*.json (白名单 + 元信息, 服务器端可复用)

用法:
    python step4_verify_and_pack.py                  # 仅校验
    python step4_verify_and_pack.py --pack           # 校验 + 打包
    python step4_verify_and_pack.py --pack --output "E:\\bundle.tar.gz"
"""
from __future__ import annotations

import argparse
import collections
import json
import logging
import sys
import tarfile
import time
from pathlib import Path
from typing import Set

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("step4")

DEFAULT_DATAROOT = Path(r"E:\Project\ADVTEST\dataset\Trainval")
DEFAULT_BUNDLE_DIR = Path(r"E:\Project\ADVTEST\dataset\Trainval\test6019_bundle")
NUSCENES_VERSION = "v1.0-trainval"

REQUIRED_JSONS = [
    "attribute.json", "calibrated_sensor.json", "category.json", "ego_pose.json",
    "instance.json", "log.json", "map.json", "sample.json", "sample_annotation.json",
    "sample_data.json", "scene.json", "sensor.json", "visibility.json",
]


def verify_metadata(meta_dir: Path) -> bool:
    if not meta_dir.exists():
        logger.error("✗ metadata 目录不存在: %s", meta_dir)
        return False
    missing = [n for n in REQUIRED_JSONS if not (meta_dir / n).exists()]
    if missing:
        logger.error("✗ metadata 缺失: %s", missing)
        return False
    logger.info("✓ metadata 13 个 JSON 齐全")
    return True


def verify_jpgs(targets_file: Path, dataroot: Path, jpg_meta_file: Path) -> tuple[bool, list[str]]:
    with open(targets_file, "r", encoding="utf-8") as f:
        targets = [ln.strip().replace("\\", "/") for ln in f if ln.strip()]
    logger.info("校验 %d 个 JPG...", len(targets))

    missing: list[str] = []
    total_size = 0
    for rel in targets:
        p = dataroot / rel
        if not p.exists():
            missing.append(rel)
        else:
            total_size += p.stat().st_size

    if missing:
        logger.error("✗ 缺失 %d 个 JPG (示例: %s)", len(missing), missing[:3])
    else:
        logger.info("✓ 全部 %d 个 JPG 齐全, 总大小 %.2f GB",
                    len(targets), total_size / 1024**3)

    # per sample_token 6 路相机校验
    if jpg_meta_file.exists():
        with open(jpg_meta_file, "r", encoding="utf-8") as f:
            recs = json.load(f)
        per_token = collections.defaultdict(set)
        for r in recs:
            if (dataroot / r["filename"]).exists():
                per_token[r["sample_token"]].add(r["channel"])
        incomplete = [tok for tok, chs in per_token.items() if len(chs) < 6]
        if incomplete:
            logger.warning("⚠ %d 个 sample_token 不足 6 路相机", len(incomplete))
        else:
            logger.info("✓ 全部 %d 个 sample_token 都有完整 6 路相机", len(per_token))

    return (not missing), missing


def write_missing_report(missing: list[str], bundle_dir: Path):
    if not missing:
        return
    p = bundle_dir / "missing_jpgs.txt"
    p.write_text("\n".join(missing), encoding="utf-8")
    logger.info("缺失列表已写入: %s", p)


def pack_bundle(dataroot: Path, bundle_dir: Path, output: Path):
    """打包 metadata + samples/CAM_* + bundle metadata 到 tar.gz."""
    logger.info("=" * 60)
    logger.info("打包 → %s", output)
    output.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    items_to_pack: list[tuple[Path, str]] = []

    # 1. metadata
    meta_dir = dataroot / NUSCENES_VERSION
    for j in REQUIRED_JSONS:
        items_to_pack.append((meta_dir / j, f"{NUSCENES_VERSION}/{j}"))

    # 2. JPG (按白名单, 比 walk samples/ 更可靠)
    targets_file = bundle_dir / "target_jpg_files.txt"
    with open(targets_file, "r", encoding="utf-8") as f:
        for ln in f:
            rel = ln.strip().replace("\\", "/")
            if rel:
                items_to_pack.append((dataroot / rel, rel))

    # 3. bundle 元信息 (服务器端 step2 输出可直接复用)
    for j in ("target_sample_tokens.json", "target_jpg_files.txt", "target_jpg_files.json",
              "sample_token_to_scene.json", "target_summary.json"):
        p = bundle_dir / j
        if p.exists():
            items_to_pack.append((p, f"test6019_bundle/{j}"))

    logger.info("总条目: %d", len(items_to_pack))

    written = 0
    with tarfile.open(output, "w:gz", compresslevel=6) as tf:
        for src, arcname in items_to_pack:
            if not src.exists():
                logger.warning("跳过不存在: %s", src)
                continue
            tf.add(src, arcname=arcname, recursive=False)
            written += 1
            if written % 2000 == 0:
                logger.info("  打包进度 %d / %d", written, len(items_to_pack))

    elapsed = time.time() - t0
    out_size = output.stat().st_size / 1024**3
    logger.info("✓ 打包完成: %.2f GB, 用时 %.1f min", out_size, elapsed / 60)
    logger.info("传输到服务器后, 解压并设置:")
    logger.info("  NUSCENES_DATAROOT=<解压目录>")
    logger.info("  NUSCENES_VERSION=v1.0-trainval")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataroot", type=Path, default=DEFAULT_DATAROOT)
    ap.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    ap.add_argument("--pack", action="store_true", help="校验通过后打包")
    ap.add_argument("--output", type=Path, default=None,
                    help="打包输出路径 (默认 <bundle-dir>/nuscenes_test6019.tar.gz)")
    args = ap.parse_args()

    meta_dir = args.dataroot / NUSCENES_VERSION
    targets_file = args.bundle_dir / "target_jpg_files.txt"
    jpg_meta_file = args.bundle_dir / "target_jpg_files.json"

    if not targets_file.exists():
        logger.error("白名单不存在: %s  (先跑 step2)", targets_file)
        sys.exit(1)

    ok_meta = verify_metadata(meta_dir)
    ok_jpg, missing = verify_jpgs(targets_file, args.dataroot, jpg_meta_file)
    write_missing_report(missing, args.bundle_dir)

    if not (ok_meta and ok_jpg):
        logger.error("✗ 校验失败, 拒绝打包")
        sys.exit(1)

    logger.info("✓ 校验全部通过")

    if args.pack:
        output = args.output or (args.bundle_dir / "nuscenes_test6019.tar.gz")
        pack_bundle(args.dataroot, args.bundle_dir, output)


if __name__ == "__main__":
    main()
