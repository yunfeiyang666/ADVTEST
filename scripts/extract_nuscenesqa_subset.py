import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List, Set


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load_question_sample_tokens(question_json: Path) -> Set[str]:
    data = _load_json(question_json)
    if isinstance(data, dict) and "questions" in data:
        questions = data["questions"]
    elif isinstance(data, list):
        questions = data
    else:
        raise ValueError(f"Unsupported question file format: {question_json}")

    tokens = set()
    for q in questions:
        token = q.get("sample_token")
        if token:
            tokens.add(token)
    if not tokens:
        raise ValueError("No sample_token found in question file.")
    return tokens


def _index_by_token(rows: List[Dict]) -> Dict[str, Dict]:
    return {row["token"]: row for row in rows}


def _copy_file_if_needed(src_root: Path, dst_root: Path, rel_path: str) -> bool:
    src = src_root / rel_path
    dst = dst_root / rel_path
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
    return True


def _channel_allowed(channel: str, keep_channels: Set[str]) -> bool:
    if not keep_channels:
        return True
    return channel in keep_channels


def _parse_channels(raw: str) -> Set[str]:
    raw = (raw or "").strip()
    if not raw or raw.lower() == "all":
        return set()
    return {c.strip() for c in raw.split(",") if c.strip()}


def extract_subset(
    dataroot: Path,
    version: str,
    question_json: Path,
    output_root: Path,
    channels: Set[str],
    include_sweeps: bool,
) -> Dict:
    version_dir = dataroot / version
    if not version_dir.exists():
        raise FileNotFoundError(f"Version directory not found: {version_dir}")

    sample_tokens = _load_question_sample_tokens(question_json)

    scene_rows = _load_json(version_dir / "scene.json")
    sample_rows = _load_json(version_dir / "sample.json")
    sample_data_rows = _load_json(version_dir / "sample_data.json")
    ego_pose_rows = _load_json(version_dir / "ego_pose.json")
    calibrated_sensor_rows = _load_json(version_dir / "calibrated_sensor.json")
    sensor_rows = _load_json(version_dir / "sensor.json")
    log_rows = _load_json(version_dir / "log.json")
    map_rows = _load_json(version_dir / "map.json")

    sample_by_token = _index_by_token(sample_rows)
    sample_data_by_token = _index_by_token(sample_data_rows)
    scene_by_token = _index_by_token(scene_rows)
    ego_pose_by_token = _index_by_token(ego_pose_rows)
    calib_by_token = _index_by_token(calibrated_sensor_rows)
    sensor_by_token = _index_by_token(sensor_rows)
    log_by_token = _index_by_token(log_rows)
    map_by_token = _index_by_token(map_rows)

    kept_sample_tokens: Set[str] = set()
    kept_scene_tokens: Set[str] = set()
    kept_sample_data_tokens: Set[str] = set()
    kept_ego_pose_tokens: Set[str] = set()
    kept_calib_tokens: Set[str] = set()
    kept_sensor_tokens: Set[str] = set()
    kept_log_tokens: Set[str] = set()
    kept_map_tokens: Set[str] = set()

    copied_files = 0
    missing_files = 0

    for st in sample_tokens:
        sample = sample_by_token.get(st)
        if sample is None:
            continue
        kept_sample_tokens.add(st)
        kept_scene_tokens.add(sample["scene_token"])

        for sd_token in sample["data"].values():
            sd = sample_data_by_token.get(sd_token)
            if sd is None:
                continue
            channel = sd.get("channel", "")
            if not _channel_allowed(channel, channels):
                continue
            kept_sample_data_tokens.add(sd_token)
            kept_ego_pose_tokens.add(sd["ego_pose_token"])
            kept_calib_tokens.add(sd["calibrated_sensor_token"])
            copied = _copy_file_if_needed(dataroot, output_root, sd["filename"])
            if copied:
                copied_files += 1
            else:
                missing_files += 1

            if include_sweeps:
                next_token = sd.get("next", "")
                while next_token:
                    next_sd = sample_data_by_token.get(next_token)
                    if next_sd is None:
                        break
                    if next_sd.get("is_key_frame", True):
                        break
                    if not _channel_allowed(next_sd.get("channel", ""), channels):
                        break
                    kept_sample_data_tokens.add(next_token)
                    kept_ego_pose_tokens.add(next_sd["ego_pose_token"])
                    kept_calib_tokens.add(next_sd["calibrated_sensor_token"])
                    copied = _copy_file_if_needed(dataroot, output_root, next_sd["filename"])
                    if copied:
                        copied_files += 1
                    else:
                        missing_files += 1
                    next_token = next_sd.get("next", "")

    for ct in kept_calib_tokens:
        calib = calib_by_token.get(ct)
        if calib is not None:
            kept_sensor_tokens.add(calib["sensor_token"])

    for sct in kept_scene_tokens:
        scene = scene_by_token.get(sct)
        if scene is not None:
            kept_log_tokens.add(scene["log_token"])

    for lt in kept_log_tokens:
        for m in map_rows:
            if m.get("log_tokens") and lt in m["log_tokens"]:
                kept_map_tokens.add(m["token"])

    # Copy map assets used by retained logs.
    for mt in kept_map_tokens:
        m = map_by_token.get(mt)
        if m and m.get("filename"):
            copied = _copy_file_if_needed(dataroot, output_root, m["filename"])
            if copied:
                copied_files += 1
            else:
                missing_files += 1

    out_version = output_root / version
    out_version.mkdir(parents=True, exist_ok=True)

    _dump_json(out_version / "scene.json", [scene_by_token[t] for t in kept_scene_tokens if t in scene_by_token])
    _dump_json(out_version / "sample.json", [sample_by_token[t] for t in kept_sample_tokens if t in sample_by_token])
    _dump_json(
        out_version / "sample_data.json",
        [sample_data_by_token[t] for t in kept_sample_data_tokens if t in sample_data_by_token],
    )
    _dump_json(out_version / "ego_pose.json", [ego_pose_by_token[t] for t in kept_ego_pose_tokens if t in ego_pose_by_token])
    _dump_json(
        out_version / "calibrated_sensor.json",
        [calib_by_token[t] for t in kept_calib_tokens if t in calib_by_token],
    )
    _dump_json(out_version / "sensor.json", [sensor_by_token[t] for t in kept_sensor_tokens if t in sensor_by_token])
    _dump_json(out_version / "log.json", [log_by_token[t] for t in kept_log_tokens if t in log_by_token])
    _dump_json(out_version / "map.json", [map_by_token[t] for t in kept_map_tokens if t in map_by_token])

    # Keep compatibility: copy small static tables if present.
    for name in [
        "attribute.json",
        "category.json",
        "visibility.json",
        "instance.json",
        "sample_annotation.json",
    ]:
        src = version_dir / name
        if src.exists():
            _dump_json(out_version / name, _load_json(src))

    summary = {
        "version": version,
        "question_file": str(question_json),
        "requested_sample_tokens": len(sample_tokens),
        "kept_samples": len(kept_sample_tokens),
        "kept_scenes": len(kept_scene_tokens),
        "kept_sample_data": len(kept_sample_data_tokens),
        "kept_ego_pose": len(kept_ego_pose_tokens),
        "kept_calibrated_sensor": len(kept_calib_tokens),
        "kept_sensor": len(kept_sensor_tokens),
        "kept_logs": len(kept_log_tokens),
        "kept_maps": len(kept_map_tokens),
        "copied_files": copied_files,
        "missing_files": missing_files,
        "channels": sorted(channels) if channels else "all",
        "include_sweeps": include_sweeps,
    }
    _dump_json(output_root / "subset_summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Extract a deployable nuScenes subset linked to NuScenes-QA sample tokens."
    )
    parser.add_argument("--dataroot", required=True, help="nuScenes dataroot, e.g. E:/Project/ADVTEST/data/nuscenes")
    parser.add_argument("--version", default="v1.0-test", help="nuScenes version folder, e.g. v1.0-test")
    parser.add_argument("--question-json", required=True, help="NuScenes_*_questions.json path")
    parser.add_argument("--output-root", required=True, help="output subset root")
    parser.add_argument(
        "--channels",
        default="all",
        help="Comma-separated channels to keep, e.g. LIDAR_TOP,CAM_FRONT or all",
    )
    parser.add_argument(
        "--include-sweeps",
        action="store_true",
        help="Also include non-keyframe sweeps by following sample_data.next for selected channels.",
    )
    args = parser.parse_args()

    summary = extract_subset(
        dataroot=Path(args.dataroot),
        version=args.version,
        question_json=Path(args.question_json),
        output_root=Path(args.output_root),
        channels=_parse_channels(args.channels),
        include_sweeps=args.include_sweeps,
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
