"""
step3_extract_jpg_from_tarball.py
=================================
流式抽取 nuScenes blob tarball 中 step2 白名单内的相机 JPG 文件。

核心特性:
  - tarfile "r|gz" 流式模式: 不建完整 index, 内存占用极小
  - 命中即抽, 其他 member 直接 skip
  - 持久化已抽文件状态 (extracted.json), 支持断点续跑
  - 全部命中后自动提前退出 (剩余白名单为空)
  - 跑完可选自动删除 tarball

用法 (一次处理一个 tarball):
    python step3_extract_jpg_from_tarball.py --tarball "E:\\...\\v1.0-trainval01_blobs.tgz"
    python step3_extract_jpg_from_tarball.py --tarball "...\\v1.0-trainval02_blobs.tgz" --delete-after
    python step3_extract_jpg_from_tarball.py --all   # 自动遍历目录下 *_blobs.tgz

输出: 文件按原相对路径放进 dataroot 下, e.g.
    E:\\Project\\ADVTEST\\dataset\\Trainval\\samples\\CAM_FRONT\\n008-...jpg
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tarfile
import time
from pathlib import Path
from typing import Set

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("step3")

DEFAULT_DATAROOT = Path(r"E:\Project\ADVTEST\dataset\Trainval")
DEFAULT_BUNDLE_DIR = Path(r"E:\Project\ADVTEST\dataset\Trainval\test6019_bundle")


def load_targets(targets_file: Path) -> Set[str]:
    if not targets_file.exists():
        logger.error("白名单文件不存在: %s  (先跑 step2)", targets_file)
        sys.exit(1)
    with open(targets_file, "r", encoding="utf-8") as f:
        targets = {ln.strip().replace("\\", "/") for ln in f if ln.strip()}
    logger.info("白名单: %d 个目标 JPG", len(targets))
    return targets


def load_state(state_file: Path) -> Set[str]:
    if not state_file.exists():
        return set()
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("extracted", []))
    except Exception as exc:
        logger.warning("state 文件损坏 (%s), 从空状态开始", exc)
        return set()


def save_state(state_file: Path, extracted: Set[str], processed_tarballs: list[str]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_file.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({
            "extracted": sorted(extracted),
            "extracted_count": len(extracted),
            "processed_tarballs": processed_tarballs,
        }, f, indent=2)
    tmp.replace(state_file)


def extract_one_tarball(
    tarball: Path,
    targets: Set[str],
    already_have: Set[str],
    dataroot: Path,
    state_file: Path,
    processed_tarballs: list[str],
) -> int:
    """流式扫一个 tarball, 抽出命中的文件. 返回本次新增数."""
    remaining = targets - already_have
    if not remaining:
        logger.info("白名单已全部抽取完毕, 跳过 %s", tarball.name)
        return 0

    logger.info("=" * 60)
    logger.info("处理 tarball: %s", tarball.name)
    logger.info("  大小: %.2f GB", tarball.stat().st_size / 1024 / 1024 / 1024)
    logger.info("  剩余目标: %d", len(remaining))

    new_count = 0
    scanned = 0
    t0 = time.time()
    last_log = t0
    save_every = 200  # 每抽 200 个落一次盘

    try:
        with tarfile.open(tarball, "r|gz") as tf:
            for member in tf:
                scanned += 1
                if scanned % 5000 == 0:
                    elapsed = time.time() - last_log
                    logger.info("  扫描 %d 条, 已抽 %d, 剩余 %d (近期 %.1f cond/s)",
                                scanned, new_count, len(remaining),
                                5000 / max(elapsed, 0.001))
                    last_log = time.time()

                if not member.isfile():
                    continue
                name = member.name.replace("\\", "/")

                # tarball 内路径可能带前缀 (如 "./samples/..." 或 "trainval/samples/...")
                # 标准化: 找到 'samples/' 起始位置
                norm = name
                if "samples/" in norm:
                    norm = norm[norm.index("samples/"):]
                else:
                    continue  # 非 samples/ 下的全部跳过 (sweeps/maps/...)

                if norm not in remaining:
                    continue

                # 命中! 抽取
                # 安全起见手动写出, 避免 extractall 的路径污染问题
                target_path = dataroot / norm
                target_path.parent.mkdir(parents=True, exist_ok=True)
                f_in = tf.extractfile(member)
                if f_in is None:
                    continue
                with open(target_path, "wb") as f_out:
                    while True:
                        chunk = f_in.read(1024 * 1024)
                        if not chunk:
                            break
                        f_out.write(chunk)

                already_have.add(norm)
                remaining.discard(norm)
                new_count += 1

                if new_count % save_every == 0:
                    save_state(state_file, already_have, processed_tarballs)
                    logger.info("  ✓ 已抽 %d (剩余 %d), 落盘 state",
                                new_count, len(remaining))

                # 提前退出: 全部命中
                if not remaining:
                    logger.info("  🎉 白名单全部命中, 提前结束本 tarball 扫描")
                    break

    except Exception as exc:
        logger.error("处理 tarball 出错: %s", exc)
        save_state(state_file, already_have, processed_tarballs)
        raise

    elapsed = time.time() - t0
    processed_tarballs.append(tarball.name)
    save_state(state_file, already_have, processed_tarballs)

    logger.info("✓ %s 完成: 扫 %d 条, 抽 %d 个 JPG, 用时 %.1f min, 累计已抽 %d / %d",
                tarball.name, scanned, new_count, elapsed / 60,
                len(already_have), len(targets))
    return new_count


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataroot", type=Path, default=DEFAULT_DATAROOT)
    ap.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR,
                    help="step2 输出目录 (含 target_jpg_files.txt)")
    ap.add_argument("--tarball", type=Path, default=None,
                    help="单个 tarball 路径")
    ap.add_argument("--all", action="store_true",
                    help="自动处理 dataroot 下所有 v1.0-trainval*_blobs.tgz")
    ap.add_argument("--delete-after", action="store_true",
                    help="单个 tarball 处理完后立即删除 (慎用!)")
    args = ap.parse_args()

    if not args.tarball and not args.all:
        logger.error("必须指定 --tarball <path> 或 --all")
        sys.exit(2)

    targets_file = args.bundle_dir / "target_jpg_files.txt"
    state_file   = args.bundle_dir / "extracted_state.json"
    targets = load_targets(targets_file)
    extracted = load_state(state_file)
    state_data = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    processed = state_data.get("processed_tarballs", []) if isinstance(state_data, dict) else []

    logger.info("已抽: %d / %d (启动时)", len(extracted), len(targets))

    # 收集要处理的 tarball 列表
    if args.all:
        tars = sorted(args.dataroot.glob("v1.0-trainval*_blobs.tgz"))
        if not tars:
            logger.error("在 %s 没找到 v1.0-trainval*_blobs.tgz", args.dataroot)
            sys.exit(1)
        logger.info("--all 模式: 找到 %d 个 tarball", len(tars))
    else:
        if not args.tarball.exists():
            logger.error("tarball 不存在: %s", args.tarball)
            sys.exit(1)
        tars = [args.tarball]

    for tar in tars:
        if tar.name in processed:
            logger.info("已处理过 %s, 跳过", tar.name)
            continue
        try:
            extract_one_tarball(tar, targets, extracted, args.dataroot, state_file, processed)
        except KeyboardInterrupt:
            logger.warning("用户中断, state 已落盘, 可断点续跑")
            sys.exit(130)

        if args.delete_after:
            logger.warning("⚠ 删除 tarball: %s", tar)
            tar.unlink()

        if len(extracted) >= len(targets):
            logger.info("🎉 全部目标已抽取完毕, 跳过剩余 tarball")
            break

    logger.info("=" * 60)
    logger.info("Step 3 进度: %d / %d (%.1f%%)",
                len(extracted), len(targets), 100 * len(extracted) / max(len(targets), 1))
    if len(extracted) < len(targets):
        miss = len(targets) - len(extracted)
        logger.warning("还缺 %d 个 JPG, 请继续处理后续 tarball", miss)
    else:
        logger.info("✓ 全部抽取完成! 下一步: python step4_verify_and_pack.py")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
