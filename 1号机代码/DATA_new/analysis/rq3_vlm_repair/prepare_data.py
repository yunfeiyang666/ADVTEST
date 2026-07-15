import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

from config import (
    ALL_FRAMES_STATS,
    EXPECTED_COUNTS,
    FORMAL_TEST_FRAME_CACHE,
    OUTPUTS_ROOT,
    SCRATCH_ROOT,
    SPLIT_SEED,
    TEST_SCENES,
    VALIDATION_SCENES,
)


SCENE_FRAME_RE = re.compile(r"^(scene-\d+)_frame(\d+)$")


def scene_name(scene_frame: str) -> str:
    match = SCENE_FRAME_RE.fullmatch(scene_frame)
    if not match:
        raise ValueError(f"Invalid scene_frame: {scene_frame}")
    return match.group(1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_effective_frames(stats_path: Path) -> list[dict]:
    with stats_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "scene_frame",
        "filtered_nodes",
        "total_l2_gaps",
        "generated_questions",
        "final_coverage_l2",
    }
    if not rows:
        raise ValueError(f"Frame statistics are empty: {stats_path}")
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Frame statistics lack columns: {sorted(missing)}")
    output = []
    seen = set()
    for row in rows:
        sf = str(row["scene_frame"])
        scene_name(sf)
        if sf in seen:
            raise ValueError(f"Duplicate frame in statistics: {sf}")
        seen.add(sf)
        output.append(
            {
                "scene_frame": sf,
                "scene_name": scene_name(sf),
                "filtered_nodes": int(row["filtered_nodes"]),
                "total_l2_gaps": int(row["total_l2_gaps"]),
                "generated_questions": int(row["generated_questions"]),
                "final_coverage_l2": float(row["final_coverage_l2"]),
            }
        )
    return output


def list_output_frames(outputs_root: Path) -> list[str]:
    frames = []
    for path in outputs_root.iterdir():
        if path.is_dir() and SCENE_FRAME_RE.fullmatch(path.name):
            frames.append(path.name)
    return sorted(frames, key=lambda value: (int(value[6:10]), int(value.rsplit("frame", 1)[1])))


def load_formal_test_frames(path: Path | None) -> list[dict]:
    if path is None:
        return []
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"Formal test frame cache must be a JSON list: {path}")
    seen = set()
    output = []
    for record in records:
        sf = str(record.get("scene_frame") or "")
        scene = scene_name(sf)
        if scene not in TEST_SCENES:
            raise ValueError(f"Formal test cache contains a non-test scene: {sf}")
        if sf in seen:
            raise ValueError(f"Duplicate frame in formal test cache: {sf}")
        seen.add(sf)
        output.append(dict(record))
    return output


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _assert_disjoint(named_sets: dict[str, set[str]]) -> None:
    names = list(named_sets)
    for index, left_name in enumerate(names):
        for right_name in names[index + 1 :]:
            overlap = named_sets[left_name] & named_sets[right_name]
            if overlap:
                raise ValueError(
                    f"Split leakage between {left_name} and {right_name}: "
                    f"{sorted(overlap)[:5]}"
                )


def build_split_manifest(
    stats_path: Path,
    outputs_root: Path,
    formal_test_frame_cache: Path | None = None,
    enforce_expected_counts: bool = True,
) -> tuple[dict, dict[str, list[dict]]]:
    effective_frames = load_effective_frames(stats_path)
    output_frames = list_output_frames(outputs_root)
    formal_test_frames = load_formal_test_frames(formal_test_frame_cache)
    test_scenes = set(TEST_SCENES)
    validation_scenes = set(VALIDATION_SCENES)
    all_effective_scenes = {row["scene_name"] for row in effective_frames}
    train_scenes = all_effective_scenes - test_scenes - validation_scenes
    split_scenes = {
        "train": train_scenes,
        "validation": validation_scenes,
        "test": test_scenes,
    }
    _assert_disjoint(split_scenes)

    split_frames = {
        name: [row for row in effective_frames if row["scene_name"] in scenes]
        for name, scenes in split_scenes.items()
    }
    output_frame_counts = {
        name: sum(scene_name(sf) in scenes for sf in output_frames)
        for name, scenes in split_scenes.items()
    }
    counts = {
        "train_scenes": len(train_scenes),
        "train_effective_frames": len(split_frames["train"]),
        "validation_scenes": len(validation_scenes),
        "validation_effective_frames": len(split_frames["validation"]),
        "test_scenes": len(test_scenes),
        "test_effective_frames": len(split_frames["test"]),
        "test_formal_frames": len(formal_test_frames),
    }
    if enforce_expected_counts and counts != EXPECTED_COUNTS:
        raise ValueError(
            "Unexpected split counts. "
            f"expected={EXPECTED_COUNTS}, actual={counts}"
        )

    frame_sets = {
        name: {row["scene_frame"] for row in rows}
        for name, rows in split_frames.items()
    }
    _assert_disjoint(frame_sets)
    manifest = {
        "schema_version": "rq3_scene_split_v1",
        "split_seed": SPLIT_SEED,
        "source": {
            "frame_statistics": str(stats_path.resolve()),
            "frame_statistics_sha256": sha256_file(stats_path),
            "outputs_root": str(outputs_root.resolve()),
            "output_frame_count": len(output_frames),
            "formal_test_frame_cache": (
                str(formal_test_frame_cache.resolve())
                if formal_test_frame_cache is not None
                else None
            ),
        },
        "test_scenes_frozen": True,
        "splits": {
            name: {
                "scene_count": len(scenes),
                "effective_frame_count": len(split_frames[name]),
                "output_frame_count": output_frame_counts[name],
                "formal_frame_count": (
                    len(formal_test_frames) if name == "test" else None
                ),
                "scenes": sorted(scenes),
            }
            for name, scenes in split_scenes.items()
        },
        "counts": counts,
        "checks": {
            "scene_overlap_count": 0,
            "effective_frame_overlap_count": 0,
            "expected_counts_enforced": enforce_expected_counts,
        },
    }
    return manifest, split_frames


def write_split_artifacts(
    output_dir: Path,
    manifest: dict,
    split_frames: dict[str, list[dict]],
    formal_test_frames: list[dict] | None = None,
) -> None:
    _write_json(output_dir / "split_manifest.json", manifest)
    for name, rows in split_frames.items():
        _write_json(output_dir / f"{name}_frames.json", rows)
    if formal_test_frames is not None:
        _write_json(output_dir / "test_formal_frames.json", formal_test_frames)


def run_split(args: argparse.Namespace) -> None:
    manifest, split_frames = build_split_manifest(
        args.frame_stats,
        args.outputs_root,
        args.formal_test_frame_cache,
        enforce_expected_counts=not args.allow_count_mismatch,
    )
    formal_test_frames = load_formal_test_frames(args.formal_test_frame_cache)
    write_split_artifacts(
        args.output_dir,
        manifest,
        split_frames,
        formal_test_frames,
    )
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    print(f"[rq3-data] split artifacts: {args.output_dir.resolve()}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare RQ3 VLM repair datasets.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    split_parser = subparsers.add_parser("split", help="Freeze scene-disjoint data splits.")
    split_parser.add_argument("--frame-stats", type=Path, default=ALL_FRAMES_STATS)
    split_parser.add_argument("--outputs-root", type=Path, default=OUTPUTS_ROOT)
    split_parser.add_argument(
        "--formal-test-frame-cache",
        type=Path,
        default=FORMAL_TEST_FRAME_CACHE,
    )
    split_parser.add_argument(
        "--output-dir",
        type=Path,
        default=SCRATCH_ROOT / "data" / "splits",
    )
    split_parser.add_argument(
        "--allow-count-mismatch",
        action="store_true",
        help="Only for isolated unit fixtures; formal runs must enforce fixed counts.",
    )
    split_parser.set_defaults(func=run_split)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
