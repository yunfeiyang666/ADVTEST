import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from jsonschema import Draft202012Validator
from PIL import Image

from config import (
    ALL_FRAMES_STATS,
    DATAROOT,
    EXPECTED_COUNTS,
    FORMAL_TEST_FRAME_CACHE,
    HARD_CANDIDATE_QUOTAS,
    OFFICIAL_QUESTIONS_PATH,
    OUTPUTS_ROOT,
    SCRATCH_ROOT,
    SPLIT_SEED,
    TEST_SCENES,
    TRAINING_QUOTAS,
    VALIDATION_OFFICIAL_QUOTA,
    VALIDATION_STRUCTURAL_QUOTAS,
    VALIDATION_SCENES,
)
from data_ops import (
    assert_no_test_scene,
    build_official_dataset,
    build_structural_pair,
    convert_to_choice,
    dedupe_and_validate_rows,
    family_name,
    file_sha256,
    iter_jsonl,
    load_scene_graph,
    normalize_open_rows,
    preload_camera_records,
    project_visible_ids,
    read_json,
    required_visible_ids,
    row_scene_frame,
    row_source_id,
    select_common_frames,
    select_hard_rows,
    to_sft_record,
    write_json,
    write_jsonl,
)


RQ1_MODULE_DIR = Path(__file__).resolve().parent.parent / "rq1_error_detection"
if str(RQ1_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(RQ1_MODULE_DIR))
import evaluator  # noqa: E402


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


def _dataset_manifest(name: str, rows: list[dict], path: Path) -> dict:
    return {
        "dataset_name": name,
        "path": str(path.resolve()),
        "sha256": file_sha256(path),
        "rows": len(rows),
        "unique_frames": len({row_scene_frame(row) for row in rows}),
        "family_counts": dict(sorted(Counter(family_name(row) for row in rows).items())),
        "test_scene_leakage": 0,
    }


def _smoke_quotas(per_family: int = 2) -> dict[str, int]:
    if per_family < 1:
        raise ValueError("smoke_per_family must be positive")
    return {key: per_family for key in TRAINING_QUOTAS}


def _hard_quotas(path: Path | None) -> dict[str, int]:
    if path is None:
        return dict(HARD_CANDIDATE_QUOTAS)
    raw = read_json(path)
    if not isinstance(raw, dict):
        raise ValueError("Hard quota override must be a JSON object")
    unknown = sorted(set(raw) - set(TRAINING_QUOTAS))
    if unknown:
        raise ValueError(f"Unknown hard quota families: {unknown}")
    quotas = {family: int(raw.get(family, 0)) for family in TRAINING_QUOTAS}
    if any(value < 0 for value in quotas.values()) or sum(quotas.values()) <= 0:
        raise ValueError("Hard quota override must contain a positive total")
    return quotas


def run_build(args: argparse.Namespace) -> None:
    split_manifest = read_json(args.split_dir / "split_manifest.json")
    if split_manifest["checks"]["scene_overlap_count"] != 0:
        raise ValueError("Refusing to build from a split manifest with scene leakage")
    split_name = "validation" if args.kind == "validation" else "train"
    split_frames = read_json(args.split_dir / f"{split_name}_frames.json")
    if args.kind == "validation" and not args.smoke:
        common_frames = split_frames
    else:
        common_frames = select_common_frames(
            split_frames,
            min(args.frame_pool_size, len(split_frames)),
            args.seed,
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "common_train_frames.json", common_frames)

    if args.smoke:
        quotas = _smoke_quotas(args.smoke_per_family)
    elif args.kind == "hard-candidates":
        quotas = _hard_quotas(args.quotas_json)
    elif args.kind == "validation":
        quotas = VALIDATION_STRUCTURAL_QUOTAS
    else:
        quotas = TRAINING_QUOTAS
    structural, assignments = build_structural_pair(
        common_frames,
        quotas,
        args.outputs_root,
        args.dataroot,
        args.seed,
        args.per_frame_candidate_limit,
    )
    manifests = {}
    if args.kind == "hard-candidates":
        datasets = {"advtest_hard_candidates": structural["advtest"]}
    elif args.kind == "validation":
        official_budget = (
            args.smoke_per_family if args.smoke else VALIDATION_OFFICIAL_QUOTA
        )
        official = build_official_dataset(
            common_frames,
            args.official_questions,
            args.outputs_root,
            args.dataroot,
            official_budget,
            args.seed,
            args.official_per_frame_cap,
        )
        datasets = {
            "validation_1000": dedupe_and_validate_rows(
                structural["advtest"] + official,
                sum(quotas.values()) + official_budget,
            )
        }
    else:
        official_budget = sum(quotas.values())
        official = build_official_dataset(
            common_frames if args.smoke else split_frames,
            args.official_questions,
            args.outputs_root,
            args.dataroot,
            official_budget,
            args.seed,
            args.official_per_frame_cap,
        )
        datasets = {
            "advtest_10k": structural["advtest"],
            "random_10k": structural["random"],
            "official_qa_10k": official,
        }
    source_dir = args.output_dir / "sources"
    for name, rows in datasets.items():
        assert_no_test_scene(rows)
        path = source_dir / f"{name}_source.jsonl"
        write_jsonl(path, rows)
        manifests[name] = _dataset_manifest(name, rows, path)
    manifest = {
        "schema_version": "rq3_source_datasets_v1",
        "kind": args.kind,
        "smoke": args.smoke,
        "seed": args.seed,
        "frame_pool_size": args.frame_pool_size,
        "common_frame_manifest": str((args.output_dir / "common_train_frames.json").resolve()),
        "quotas": quotas,
        "per_frame_candidate_limit": args.per_frame_candidate_limit,
        "frame_assignments": assignments,
        "datasets": manifests,
    }
    write_json(args.output_dir / "source_dataset_manifest.json", manifest)
    print(json.dumps({name: value["rows"] for name, value in manifests.items()}))
    print(f"[rq3-data] source datasets: {args.output_dir.resolve()}")


def run_screen_hard(args: argparse.Namespace) -> None:
    raw_results = [
        row for path in args.raw_results for row in iter_jsonl(path)
    ]
    source_rows = [
        row for path in args.source_suite for row in iter_jsonl(path)
    ]
    quotas = (
        _smoke_quotas(args.smoke_per_family) if args.smoke else TRAINING_QUOTAS
    )
    selected, summary = select_hard_rows(
        raw_results,
        source_rows,
        quotas,
        args.seed,
    )
    assert_no_test_scene(selected)
    write_jsonl(args.output_suite, selected)
    manifest = {
        "schema_version": "rq3_hard_screen_v1",
        "source_suites": [str(path.resolve()) for path in args.source_suite],
        "raw_results": [str(path.resolve()) for path in args.raw_results],
        "output_suite": str(args.output_suite.resolve()),
        "output_sha256": file_sha256(args.output_suite),
        "seed": args.seed,
        "quotas": quotas,
        "rows": len(selected),
        **summary,
    }
    write_json(args.output_manifest, manifest)
    print(json.dumps({"rows": len(selected), **summary}, ensure_ascii=False))


def _project_visible_ids(scene_graph: dict, dataroot: Path) -> set[str]:
    return project_visible_ids(scene_graph, dataroot)


def _required_visible_ids(row: dict) -> set[str]:
    return required_visible_ids(row)


def _render_images_and_validate_visibility(
    rows_by_dataset: dict[str, list[dict]],
    output_dir: Path,
    outputs_root: Path,
    dataroot: Path,
) -> tuple[dict[str, str], list[dict], dict[str, set[str]]]:
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    by_frame: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for dataset_name, rows in rows_by_dataset.items():
        for row in rows:
            by_frame[row_scene_frame(row)].append((dataset_name, row))
    image_hashes = {}
    rejected = []
    visible_ids_by_frame = {}
    graphs_by_frame = {
        sf: load_scene_graph(outputs_root, sf) for sf in sorted(by_frame)
    }
    preload_camera_records(
        (evaluator.get_sample_token(graph, dataroot) for graph in graphs_by_frame.values()),
        dataroot,
    )
    for index, (sf, tagged_rows) in enumerate(sorted(by_frame.items()), start=1):
        scene_graph = graphs_by_frame[sf]
        visible_ids = _project_visible_ids(scene_graph, dataroot)
        visible_ids_by_frame[sf] = visible_ids
        image_path = images_dir / f"{sf}_labeled_mosaic.jpg"
        if not image_path.exists():
            if not evaluator.render_labeled_mosaic(scene_graph, dataroot, image_path):
                raise RuntimeError(f"Could not render labeled mosaic for {sf}")
        with Image.open(image_path) as image:
            image.verify()
        image_hashes[sf] = file_sha256(image_path)
        for dataset_name, row in tagged_rows:
            required = _required_visible_ids(row)
            missing = sorted(required - visible_ids)
            if missing:
                rejected.append(
                    {
                        "dataset_name": dataset_name,
                        "scene_frame": sf,
                        "source_question_id": row_source_id(row),
                        "reason": "referenced_object_not_rendered",
                        "missing_object_ids": missing,
                    }
                )
        if index % 50 == 0:
            print(f"[rq3-data] rendered {index}/{len(by_frame)} mosaics", flush=True)
    return image_hashes, rejected, visible_ids_by_frame


def run_export(args: argparse.Namespace) -> None:
    sources = dict(args.source)
    rows_by_dataset = {name: list(iter_jsonl(path)) for name, path in sources.items()}
    for rows in rows_by_dataset.values():
        assert_no_test_scene(rows)
    image_hashes, rejected, visible_ids_by_frame = _render_images_and_validate_visibility(
        rows_by_dataset,
        args.output_dir,
        args.outputs_root,
        args.dataroot,
    )
    write_jsonl(args.output_dir / "visibility_rejected.jsonl", rejected)
    if rejected and not args.allow_visibility_rejections:
        raise ValueError(
            f"Visibility validation rejected {len(rejected)} rows; "
            "source datasets must be backfilled before formal export"
        )
    rejected_keys = {
        (row["dataset_name"], row["scene_frame"], row["source_question_id"])
        for row in rejected
    }
    manifests = {}
    datasets_dir = args.output_dir / "datasets"
    for dataset_name, rows in rows_by_dataset.items():
        valid_rows = [
            row
            for row in rows
            if (dataset_name, row_scene_frame(row), row_source_id(row))
            not in rejected_keys
        ]
        choice_rows = convert_to_choice(
            valid_rows,
            args.outputs_root,
            args.seed,
            visible_ids_by_frame,
        )
        valid_rows = normalize_open_rows(valid_rows, choice_rows)
        open_eval_rows = []
        choice_eval_rows = []
        for row in valid_rows:
            evaluation_row = dict(row)
            evaluation_row["image_path"] = str(
                (args.output_dir / "images" / f"{row_scene_frame(row)}_labeled_mosaic.jpg").resolve()
            )
            open_eval_rows.append(evaluation_row)
        for row in choice_rows:
            evaluation_row = dict(row)
            evaluation_row["image_path"] = str(
                (args.output_dir / "images" / f"{row_scene_frame(row)}_labeled_mosaic.jpg").resolve()
            )
            choice_eval_rows.append(evaluation_row)
        open_records = [
            to_sft_record(
                row,
                dataset_name,
                "open",
                image_hashes[row_scene_frame(row)],
            )
            for row in valid_rows
        ]
        choice_records = [
            to_sft_record(
                row,
                dataset_name,
                "choice",
                image_hashes[row_scene_frame(row)],
            )
            for row in choice_rows
        ]
        open_path = datasets_dir / f"{dataset_name}_open.json"
        choice_path = datasets_dir / f"{dataset_name}_choice.json"
        open_eval_path = args.output_dir / "eval_suites" / f"{dataset_name}_open_suite.jsonl"
        choice_eval_path = args.output_dir / "eval_suites" / f"{dataset_name}_choice_suite.jsonl"
        write_json(open_path, open_records)
        write_json(choice_path, choice_records)
        write_jsonl(open_eval_path, open_eval_rows)
        write_jsonl(choice_eval_path, choice_eval_rows)
        manifests[dataset_name] = {
            "source": str(sources[dataset_name].resolve()),
            "source_rows": len(rows),
            "valid_rows": len(valid_rows),
            "visibility_rejected": len(rows) - len(valid_rows),
            "open_dataset": str(open_path.resolve()),
            "open_sha256": file_sha256(open_path),
            "choice_dataset": str(choice_path.resolve()),
            "choice_sha256": file_sha256(choice_path),
            "open_eval_suite": str(open_eval_path.resolve()),
            "open_eval_sha256": file_sha256(open_eval_path),
            "choice_eval_suite": str(choice_eval_path.resolve()),
            "choice_eval_sha256": file_sha256(choice_eval_path),
            "unique_images": len({row_scene_frame(row) for row in valid_rows}),
            "family_counts": dict(
                sorted(Counter(family_name(row) for row in valid_rows).items())
            ),
        }
    manifest = {
        "schema_version": "rq3_mplug_sft_export_v1",
        "seed": args.seed,
        "image_root": str((args.output_dir / "images").resolve()),
        "image_count": len(image_hashes),
        "image_hashes": image_hashes,
        "datasets": manifests,
    }
    write_json(args.output_dir / "sft_export_manifest.json", manifest)
    print(json.dumps({name: value["valid_rows"] for name, value in manifests.items()}))


def _validate_sft_record(record: dict, image_root: Path) -> list[str]:
    errors = []
    if not str(record.get("id") or ""):
        errors.append("missing_id")
    conversations = record.get("conversations") or []
    if len(conversations) != 2:
        errors.append("conversation_count")
    else:
        if conversations[0].get("from") != "human" or not str(
            conversations[0].get("value") or ""
        ).startswith("<|image|>"):
            errors.append("human_prompt")
        if conversations[1].get("from") != "gpt" or not str(
            conversations[1].get("value") or ""
        ).strip():
            errors.append("gpt_target")
    metadata = record.get("metadata") or {}
    sf = str(metadata.get("scene_frame") or "")
    if sf.split("_frame", 1)[0] in TEST_SCENES:
        errors.append("test_scene_leakage")
    image_path = image_root / str(record.get("image") or "")
    if not image_path.exists():
        errors.append("missing_image")
    elif metadata.get("image_sha256") != file_sha256(image_path):
        errors.append("image_hash_mismatch")
    return errors


def run_validate(args: argparse.Namespace) -> None:
    records = read_json(args.dataset)
    if not isinstance(records, list):
        raise ValueError("SFT dataset must be a JSON list")
    if args.expected_count and len(records) != args.expected_count:
        raise ValueError(
            f"Expected {args.expected_count} rows, found {len(records)}"
        )
    ids = [str(record.get("id") or "") for record in records]
    source_ids = [
        str((record.get("metadata") or {}).get("source_question_id") or "")
        for record in records
    ]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate SFT record IDs")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Duplicate source_question_id values")
    errors = Counter()
    schema = read_json(Path(__file__).resolve().parent / "sft_schema.json")
    schema_validator = Draft202012Validator(schema)
    for record in records:
        for schema_error in schema_validator.iter_errors(record):
            errors[f"schema:{schema_error.validator}"] += 1
        errors.update(_validate_sft_record(record, args.image_root))
    family_counts = Counter(
        str((record.get("metadata") or {}).get("family") or "")
        for record in records
    )
    quota_mode_count = sum(
        bool(value)
        for value in (args.structural, args.validation, args.hard_candidates)
    )
    if quota_mode_count > 1:
        raise ValueError(
            "Choose only one quota mode: --structural, --validation, or "
            "--hard-candidates"
        )
    if args.structural:
        expected_quotas = (
            _smoke_quotas(args.smoke_per_family)
            if args.smoke
            else TRAINING_QUOTAS
        )
        if dict(family_counts) != expected_quotas:
            raise ValueError(
                f"Structural quotas differ: expected={expected_quotas}, "
                f"actual={dict(family_counts)}"
            )
    if args.validation:
        expected_quotas = dict(VALIDATION_STRUCTURAL_QUOTAS)
        expected_quotas["official_qa"] = VALIDATION_OFFICIAL_QUOTA
        if dict(family_counts) != expected_quotas:
            raise ValueError(
                f"Validation quotas differ: expected={expected_quotas}, "
                f"actual={dict(family_counts)}"
            )
    if args.hard_candidates and dict(family_counts) != HARD_CANDIDATE_QUOTAS:
        raise ValueError(
            f"Hard-candidate quotas differ: expected={HARD_CANDIDATE_QUOTAS}, "
            f"actual={dict(family_counts)}"
        )
    paired_summary = None
    if args.paired_dataset:
        paired = read_json(args.paired_dataset)
        if not isinstance(paired, list):
            raise ValueError("Paired SFT dataset must be a JSON list")
        paired_source_ids = [
            str((record.get("metadata") or {}).get("source_question_id") or "")
            for record in paired
        ]
        if len(paired_source_ids) != len(set(paired_source_ids)):
            raise ValueError("Duplicate source IDs in paired SFT dataset")
        if len(records) != len(paired) or set(source_ids) != set(paired_source_ids):
            raise ValueError("Paired open/choice datasets do not contain the same sources")
        paired_by_source = {
            source_id: record for source_id, record in zip(paired_source_ids, paired)
        }
        for source_id, record in zip(source_ids, records):
            other = paired_by_source[source_id]
            for schema_error in schema_validator.iter_errors(other):
                errors[f"paired_schema:{schema_error.validator}"] += 1
            errors.update(
                f"paired_{error}"
                for error in _validate_sft_record(other, args.image_root)
            )
            left_metadata = record.get("metadata") or {}
            right_metadata = other.get("metadata") or {}
            if record.get("image") != other.get("image") or left_metadata.get(
                "image_sha256"
            ) != right_metadata.get("image_sha256"):
                errors["paired_image_mismatch"] += 1
        paired_summary = {"path": str(args.paired_dataset.resolve()), "rows": len(paired)}
    if errors:
        raise ValueError(f"SFT validation failed: {dict(errors)}")
    manifest = {
        "schema_version": "rq3_sft_validation_v1",
        "dataset": str(args.dataset.resolve()),
        "dataset_sha256": file_sha256(args.dataset),
        "rows": len(records),
        "unique_source_questions": len(set(source_ids)),
        "unique_images": len({record["image"] for record in records}),
        "family_counts": dict(sorted(family_counts.items())),
        "test_scene_leakage": 0,
        "validation_errors": {},
        "paired_dataset": paired_summary,
    }
    write_json(args.output_manifest, manifest)
    print(json.dumps(manifest, ensure_ascii=False))


def parse_named_path(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Expected NAME=PATH")
    name, raw_path = value.split("=", 1)
    if not name or not raw_path:
        raise argparse.ArgumentTypeError("Expected non-empty NAME=PATH")
    return name, Path(raw_path)


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

    build_parser = subparsers.add_parser("build", help="Build source QA datasets.")
    build_parser.add_argument(
        "--kind", choices=["main", "hard-candidates", "validation"], default="main"
    )
    build_parser.add_argument(
        "--split-dir", type=Path, default=SCRATCH_ROOT / "data" / "splits"
    )
    build_parser.add_argument("--outputs-root", type=Path, default=OUTPUTS_ROOT)
    build_parser.add_argument("--dataroot", type=Path, default=DATAROOT)
    build_parser.add_argument(
        "--official-questions", type=Path, default=OFFICIAL_QUESTIONS_PATH
    )
    build_parser.add_argument(
        "--output-dir", type=Path, default=SCRATCH_ROOT / "data" / "source_datasets"
    )
    build_parser.add_argument("--frame-pool-size", type=int, default=600)
    build_parser.add_argument("--per-frame-candidate-limit", type=int, default=300)
    build_parser.add_argument("--official-per-frame-cap", type=int, default=10)
    build_parser.add_argument(
        "--quotas-json",
        type=Path,
        help="Hard-candidate-only quota override; use 2000 for a deficient family.",
    )
    build_parser.add_argument("--seed", type=int, default=SPLIT_SEED)
    build_parser.add_argument("--smoke", action="store_true")
    build_parser.add_argument("--smoke-per-family", type=int, default=2)
    build_parser.set_defaults(func=run_build)

    hard_parser = subparsers.add_parser(
        "screen-hard", help="Select genuinely wrong rows from mPLUG choice results."
    )
    hard_parser.add_argument("--raw-results", action="append", type=Path, required=True)
    hard_parser.add_argument("--source-suite", action="append", type=Path, required=True)
    hard_parser.add_argument("--output-suite", type=Path, required=True)
    hard_parser.add_argument("--output-manifest", type=Path, required=True)
    hard_parser.add_argument("--seed", type=int, default=SPLIT_SEED)
    hard_parser.add_argument("--smoke", action="store_true")
    hard_parser.add_argument("--smoke-per-family", type=int, default=2)
    hard_parser.set_defaults(func=run_screen_hard)

    export_parser = subparsers.add_parser(
        "export", help="Render shared mosaics and export paired mPLUG SFT JSON."
    )
    export_parser.add_argument("--source", action="append", type=parse_named_path, required=True)
    export_parser.add_argument("--output-dir", type=Path, default=SCRATCH_ROOT / "data" / "sft")
    export_parser.add_argument("--outputs-root", type=Path, default=OUTPUTS_ROOT)
    export_parser.add_argument("--dataroot", type=Path, default=DATAROOT)
    export_parser.add_argument("--seed", type=int, default=SPLIT_SEED)
    export_parser.add_argument("--allow-visibility-rejections", action="store_true")
    export_parser.set_defaults(func=run_export)

    validate_parser = subparsers.add_parser("validate", help="Validate an exported SFT dataset.")
    validate_parser.add_argument("--dataset", type=Path, required=True)
    validate_parser.add_argument("--paired-dataset", type=Path)
    validate_parser.add_argument("--image-root", type=Path, required=True)
    validate_parser.add_argument("--output-manifest", type=Path, required=True)
    validate_parser.add_argument("--expected-count", type=int, default=0)
    validate_parser.add_argument("--structural", action="store_true")
    validate_parser.add_argument("--validation", action="store_true")
    validate_parser.add_argument("--hard-candidates", action="store_true")
    validate_parser.add_argument("--smoke", action="store_true")
    validate_parser.add_argument("--smoke-per-family", type=int, default=2)
    validate_parser.set_defaults(func=run_validate)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
