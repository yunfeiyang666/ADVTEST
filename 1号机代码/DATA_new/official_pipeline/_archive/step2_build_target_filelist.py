"""
step2_build_target_filelist.py
==============================
读 NuScenes-QA val 题集 + metadata, 算出:
  1) 6019 个唯一 sample_token
  2) ~36000 个相机 JPG 的相对路径白名单 (供 step3 流式抽取使用)
  3) per-scene 统计 + 健康检查报告

输出文件 (默认写到 ./test6019_bundle/):
  - target_sample_tokens.json    : list[str]   去重后的 sample_token
  - target_jpg_files.txt         : 每行一个相对路径, e.g. samples/CAM_FRONT/xxx.jpg
  - target_jpg_files.json        : 同上但带元信息 {filename, sample_token, channel, scene}
  - target_summary.json          : 统计 + 健康报告
  - sample_token_to_scene.json   : sample_token -> {scene_name, frame_idx}, 供后续脚本复用
"""
from __future__ import annotations

import argparse
import collections
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Set

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("step2")

DEFAULT_DATAROOT = Path(r"E:\Project\ADVTEST\dataset\Trainval")
DEFAULT_QA_PATH = Path(r"E:\Project\ADVTEST\data\nuscenes\qa\NuScenes_val_questions.json")
DEFAULT_OUT_DIR = Path(r"E:\Project\ADVTEST\dataset\Trainval\test6019_bundle")
NUSCENES_VERSION = "v1.0-trainval"

CAM_CHANNELS = {
    "CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT",
    "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT",
}


def load_json(p: Path):
    logger.info("  load %s (%.1f MB)", p.name, p.stat().st_size / 1024 / 1024)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataroot", type=Path, default=DEFAULT_DATAROOT)
    ap.add_argument("--qa-json",  type=Path, default=DEFAULT_QA_PATH,
                    help="NuScenes-QA val questions JSON")
    ap.add_argument("--out-dir",  type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    meta_dir = args.dataroot / NUSCENES_VERSION
    if not meta_dir.exists():
        logger.error("metadata 目录不存在: %s  (先跑 step1)", meta_dir)
        sys.exit(1)
    if not args.qa_json.exists():
        logger.error("QA 文件不存在: %s", args.qa_json)
        sys.exit(1)

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # ─── 1. 读 QA, 抽出 sample_token ───
    logger.info("加载 NuScenes-QA val: %s", args.qa_json)
    qa_data = load_json(args.qa_json)
    questions = qa_data["questions"] if isinstance(qa_data, dict) and "questions" in qa_data else qa_data
    logger.info("  共 %d 道题", len(questions))

    qa_tokens: Set[str] = set()
    for q in questions:
        tok = q.get("sample_token", "")
        if tok:
            qa_tokens.add(tok)
    logger.info("  去重后 %d 个 sample_token", len(qa_tokens))

    # ─── 2. 读 metadata ───
    logger.info("加载 metadata...")
    scenes      = load_json(meta_dir / "scene.json")
    samples     = load_json(meta_dir / "sample.json")
    sample_data = load_json(meta_dir / "sample_data.json")
    calibrated_sensors = load_json(meta_dir / "calibrated_sensor.json")
    sensors = load_json(meta_dir / "sensor.json")
    logger.info("  %d scenes, %d samples, %d sample_data records",
                len(scenes), len(samples), len(sample_data))
    logger.info("  %d calibrated_sensors, %d sensors",
                len(calibrated_sensors), len(sensors))

    scene_token_to_name = {s["token"]: s["name"] for s in scenes}
    calib_token_to_sensor_token = {c["token"]: c["sensor_token"] for c in calibrated_sensors}
    sensor_token_to_channel = {s["token"]: s["channel"] for s in sensors}

    # 构建 sample_token -> {scene_name, frame_idx, scene_token}
    by_scene: Dict[str, List[dict]] = collections.defaultdict(list)
    for samp in samples:
        by_scene[samp["scene_token"]].append(samp)

    sample_to_info: Dict[str, dict] = {}
    for scene_tok, samps in by_scene.items():
        samps_sorted = sorted(samps, key=lambda s: s["timestamp"])
        sname = scene_token_to_name.get(scene_tok, "?")
        for idx, s in enumerate(samps_sorted):
            sample_to_info[s["token"]] = {
                "scene_name": sname,
                "scene_token": scene_tok,
                "frame_idx": idx,
                "timestamp": s["timestamp"],
            }

    # ─── 3. 健康检查: QA 里的 sample_token 都能在 metadata 里找到吗 ───
    qa_unmapped = qa_tokens - set(sample_to_info.keys())
    if qa_unmapped:
        logger.warning("⚠ %d 个 QA sample_token 在 metadata 里找不到 (示例: %s)",
                       len(qa_unmapped), list(qa_unmapped)[:3])
    valid_qa_tokens = qa_tokens & set(sample_to_info.keys())
    logger.info("✓ 有效 QA sample_token: %d / %d", len(valid_qa_tokens), len(qa_tokens))

    # ─── 4. 从 sample_data 里挑出: key_frame + jpg + CAM_* ───
    logger.info("扫描 sample_data 抽相机 JPG...")
    target_records: List[dict] = []
    seen_paths: Set[str] = set()

    cam_hit_per_token: Dict[str, Set[str]] = collections.defaultdict(set)
    for sd in sample_data:
        if sd.get("sample_token") not in valid_qa_tokens:
            continue
        if not sd.get("is_key_frame", False):
            continue
        if sd.get("fileformat", "").lower() != "jpg":
            continue
        calib_tok = sd.get("calibrated_sensor_token", "")
        sensor_tok = calib_token_to_sensor_token.get(calib_tok, "")
        ch = sensor_token_to_channel.get(sensor_tok, "")
        if ch not in CAM_CHANNELS:
            continue
        fname = sd.get("filename", "")
        if not fname or fname in seen_paths:
            continue
        seen_paths.add(fname)
        info = sample_to_info[sd["sample_token"]]
        target_records.append({
            "filename": fname.replace("\\", "/"),
            "sample_token": sd["sample_token"],
            "channel": ch,
            "scene_name": info["scene_name"],
            "frame_idx": info["frame_idx"],
        })
        cam_hit_per_token[sd["sample_token"]].add(ch)

    logger.info("  找到 %d 个相机 JPG", len(target_records))

    # 校验每个 sample_token 是否齐 6 路相机
    incomplete = {tok: chs for tok, chs in cam_hit_per_token.items() if len(chs) < 6}
    if incomplete:
        logger.warning("⚠ %d 个 sample_token 不足 6 路相机 (示例: %s)",
                       len(incomplete), list(incomplete.items())[:2])
    full_6cam = sum(1 for chs in cam_hit_per_token.values() if len(chs) == 6)
    logger.info("✓ %d / %d 个 sample_token 拿到完整 6 路相机",
                full_6cam, len(valid_qa_tokens))

    # ─── 5. 输出 ───
    (out_dir / "target_sample_tokens.json").write_text(
        json.dumps(sorted(valid_qa_tokens), indent=2), encoding="utf-8")

    with open(out_dir / "target_jpg_files.txt", "w", encoding="utf-8") as f:
        for rec in sorted(target_records, key=lambda r: r["filename"]):
            f.write(rec["filename"] + "\n")

    (out_dir / "target_jpg_files.json").write_text(
        json.dumps(target_records, indent=2), encoding="utf-8")

    sub_sample_to_info = {tok: sample_to_info[tok] for tok in valid_qa_tokens}
    (out_dir / "sample_token_to_scene.json").write_text(
        json.dumps(sub_sample_to_info, indent=2), encoding="utf-8")

    # 统计
    per_scene = collections.Counter(rec["scene_name"] for rec in target_records)
    per_channel = collections.Counter(rec["channel"] for rec in target_records)
    summary = {
        "qa_total_questions": len(questions),
        "qa_unique_sample_tokens": len(qa_tokens),
        "qa_unmapped_in_metadata": len(qa_unmapped),
        "valid_sample_tokens": len(valid_qa_tokens),
        "target_jpg_count": len(target_records),
        "sample_tokens_with_full_6cam": full_6cam,
        "sample_tokens_with_incomplete_cam": len(incomplete),
        "per_channel_jpg_count": dict(per_channel),
        "per_scene_jpg_count_top10": dict(per_scene.most_common(10)),
        "scenes_touched": len(per_scene),
        "expected_total_size_gb_estimate": round(len(target_records) * 0.14 / 1024, 2),
    }
    (out_dir / "target_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")

    logger.info("=" * 60)
    logger.info("Step 2 完成, 输出在: %s", out_dir)
    logger.info("  sample_tokens     : %d", len(valid_qa_tokens))
    logger.info("  target jpg files  : %d", len(target_records))
    logger.info("  scenes touched    : %d", len(per_scene))
    logger.info("  预估 JPG 总大小   : ~%.1f GB",
                summary["expected_total_size_gb_estimate"])
    logger.info("  per-channel       : %s", dict(per_channel))
    logger.info("下一步: python step3_extract_jpg_from_tarball.py --tarball <path>")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
