import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping, Sequence


SOURCE_LABEL_FIELD = "manual_valid_failure"
SOURCE_ISSUE_FIELD = "manual_issue_type"
BUCKETS = [
    "advtest_only_l2",
    "random_only_l2",
    "shared_l2_advtest",
    "shared_l2_random",
]

ADJUDICATION_FIELDS = [
    "adjudication_id",
    "selection_reason",
    "human_valid_failure",
    "human_issue_type",
    "human_agrees_with_assisted",
    "human_notes",
]


def load_csv(path: Path) -> tuple[list[dict], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path: Path, rows: Sequence[Mapping], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize(value: str) -> str:
    return str(value or "").strip().lower()


def row_key(row: Mapping) -> str:
    parts = [
        str(row.get("bucket") or ""),
        str(row.get("method") or ""),
        str(row.get("audit_group") or ""),
        str(row.get("l2_key") or ""),
    ]
    return "||".join(parts)


def validate_source_rows(rows: Sequence[Mapping]) -> None:
    if not rows:
        raise ValueError("Source CSV is empty")
    seen = set()
    for index, row in enumerate(rows, start=1):
        key = row_key(row)
        if not key:
            raise ValueError(f"Row {index} is missing audit_group/l2_key")
        if key in seen:
            raise ValueError(f"Duplicate source row key: {key}")
        seen.add(key)
        bucket = str(row.get("bucket") or "")
        if bucket not in BUCKETS:
            raise ValueError(f"Row {index} has unknown bucket: {bucket}")
        label = normalize(row.get(SOURCE_LABEL_FIELD, ""))
        if label not in {"yes", "no", "uncertain"}:
            raise ValueError(f"Row {index} has invalid assisted label: {label}")
        if not str(row.get(SOURCE_ISSUE_FIELD) or "").strip():
            raise ValueError(f"Row {index} is missing assisted issue type")


def balanced_bucket_targets(target_total: int, bucket_names: Sequence[str]) -> dict[str, int]:
    base = target_total // len(bucket_names)
    remainder = target_total % len(bucket_names)
    return {
        bucket: base + (1 if index < remainder else 0)
        for index, bucket in enumerate(bucket_names)
    }


def deterministic_sample(
    candidates: Sequence[Mapping],
    count: int,
    rng: random.Random,
    *,
    scene_counts: Counter | None = None,
    max_per_scene: int | None = None,
) -> list[Mapping]:
    if count <= 0:
        return []
    shuffled = sorted(candidates, key=row_key)
    rng.shuffle(shuffled)
    selected = []
    skipped_by_scene = []
    for row in shuffled:
        scene = str(row.get("scene_frame") or "")
        if scene_counts is not None and max_per_scene is not None:
            if scene_counts[scene] >= max_per_scene:
                skipped_by_scene.append(row)
                continue
            scene_counts[scene] += 1
        selected.append(row)
        if len(selected) == count:
            return selected

    for row in skipped_by_scene:
        if len(selected) == count:
            break
        selected.append(row)
    return selected


def select_bucket_rows(
    rows: Sequence[Mapping],
    *,
    bucket: str,
    target: int,
    max_no_per_bucket: int,
    max_per_scene: int,
    rng: random.Random,
) -> list[dict]:
    bucket_rows = [row for row in rows if row.get("bucket") == bucket]
    uncertain = [
        row for row in bucket_rows if normalize(row.get(SOURCE_LABEL_FIELD, "")) == "uncertain"
    ]
    selected = []
    selected_keys = set()
    scene_counts = Counter()

    for row in sorted(uncertain, key=row_key):
        next_row = dict(row)
        next_row["selection_reason"] = "all_uncertain"
        selected.append(next_row)
        selected_keys.add(row_key(row))
        scene_counts[str(row.get("scene_frame") or "")] += 1

    remaining = max(0, target - len(selected))
    no_candidates = [
        row
        for row in bucket_rows
        if normalize(row.get(SOURCE_LABEL_FIELD, "")) == "no"
        and row_key(row) not in selected_keys
    ]
    yes_candidates = [
        row
        for row in bucket_rows
        if normalize(row.get(SOURCE_LABEL_FIELD, "")) == "yes"
        and row_key(row) not in selected_keys
    ]

    no_quota = min(max_no_per_bucket, remaining)
    chosen_no = deterministic_sample(
        no_candidates,
        no_quota,
        rng,
        scene_counts=scene_counts,
        max_per_scene=max_per_scene,
    )
    for row in chosen_no:
        next_row = dict(row)
        next_row["selection_reason"] = "stratified_assisted_no"
        selected.append(next_row)
        selected_keys.add(row_key(row))

    remaining = max(0, target - len(selected))
    chosen_yes = deterministic_sample(
        yes_candidates,
        remaining,
        rng,
        scene_counts=scene_counts,
        max_per_scene=max_per_scene,
    )
    for row in chosen_yes:
        next_row = dict(row)
        next_row["selection_reason"] = "stratified_assisted_yes"
        selected.append(next_row)
        selected_keys.add(row_key(row))

    if len(selected) < target:
        leftovers = [
            row
            for row in bucket_rows
            if row_key(row) not in selected_keys
            and normalize(row.get(SOURCE_LABEL_FIELD, "")) in {"yes", "no"}
        ]
        for row in deterministic_sample(leftovers, target - len(selected), rng):
            next_row = dict(row)
            next_row["selection_reason"] = "stratified_backfill"
            selected.append(next_row)

    return selected


def add_adjudication_fields(rows: Sequence[Mapping]) -> list[dict]:
    output = []
    for index, row in enumerate(rows, start=1):
        next_row = dict(row)
        next_row["adjudication_id"] = f"rq1_adjudication_{index:03d}"
        next_row["human_valid_failure"] = ""
        next_row["human_issue_type"] = ""
        next_row["human_agrees_with_assisted"] = ""
        next_row["human_notes"] = ""
        output.append(next_row)
    return output


def counter_by(rows: Sequence[Mapping], fields: Sequence[str]) -> dict:
    counter = Counter(
        tuple(str(row.get(field) or "") for field in fields) for row in rows
    )
    return {" | ".join(key): counter[key] for key in sorted(counter)}


def build_manifest(
    *,
    source_csv: Path,
    output_csv: Path,
    rows: Sequence[Mapping],
    source_rows: Sequence[Mapping],
    seed: int,
    target_total: int,
    max_no_per_bucket: int,
    max_per_scene: int,
) -> dict:
    return {
        "schema_version": 1,
        "seed": seed,
        "source_csv": str(source_csv),
        "output_csv": str(output_csv),
        "sampling_policy": {
            "target_total": target_total,
            "bucket_targets": balanced_bucket_targets(target_total, BUCKETS),
            "include_all_uncertain": True,
            "max_no_per_bucket": max_no_per_bucket,
            "max_per_scene_per_bucket_after_uncertain": max_per_scene,
            "source_label_field": SOURCE_LABEL_FIELD,
            "source_issue_field": SOURCE_ISSUE_FIELD,
        },
        "source_counts": {
            "rows": len(source_rows),
            "by_bucket_label_confidence": counter_by(
                source_rows, ["bucket", SOURCE_LABEL_FIELD, "auto_confidence"]
            ),
        },
        "selected_counts": {
            "rows": len(rows),
            "by_bucket": counter_by(rows, ["bucket"]),
            "by_label": counter_by(rows, [SOURCE_LABEL_FIELD]),
            "by_bucket_label": counter_by(rows, ["bucket", SOURCE_LABEL_FIELD]),
            "by_bucket_label_confidence": counter_by(
                rows, ["bucket", SOURCE_LABEL_FIELD, "auto_confidence"]
            ),
            "by_selection_reason": counter_by(rows, ["selection_reason"]),
        },
        "review_columns": {
            "human_valid_failure": "Fill with yes/no/uncertain after human review.",
            "human_issue_type": "Use the same issue taxonomy as manual_issue_type.",
            "human_agrees_with_assisted": "Fill yes/no after comparing with manual_valid_failure.",
            "human_notes": "Brief adjudication rationale.",
        },
    }


def write_markdown_summary(path: Path, manifest: Mapping) -> None:
    selected = manifest["selected_counts"]
    lines = [
        "# RQ1 Human Adjudication Pack",
        "",
        "This file describes the calibration subset for checking the 400-row assisted failure audit.",
        "",
        "## Sampling Policy",
        "",
        f"- Seed: `{manifest['seed']}`",
        f"- Target rows: `{manifest['sampling_policy']['target_total']}`",
        "- Include all rows whose assisted label is `uncertain`.",
        f"- Per bucket, sample up to `{manifest['sampling_policy']['max_no_per_bucket']}` assisted `no` rows, then fill with assisted `yes` rows.",
        f"- Scene cap after uncertain rows: `{manifest['sampling_policy']['max_per_scene_per_bucket_after_uncertain']}` per bucket.",
        "",
        "## Selected Counts",
        "",
        f"- Rows: `{selected['rows']}`",
        f"- By label: `{selected['by_label']}`",
        f"- By selection reason: `{selected['by_selection_reason']}`",
        f"- By bucket and label: `{selected['by_bucket_label']}`",
        "",
        "## Human Review Instructions",
        "",
        "Fill only the `human_*` columns. Treat the existing `manual_*` columns as assisted labels from auto-prefill, not final human labels.",
        "",
        "- `human_valid_failure`: `yes`, `no`, or `uncertain`.",
        "- `human_issue_type`: reuse the existing issue taxonomy.",
        "- `human_agrees_with_assisted`: `yes` if the human label matches `manual_valid_failure`, otherwise `no`.",
        "- `human_notes`: short reason, especially for disagreements.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_adjudication_pack(
    source_rows: Sequence[Mapping],
    *,
    seed: int,
    target_total: int,
    max_no_per_bucket: int,
    max_per_scene: int,
) -> list[dict]:
    validate_source_rows(source_rows)
    bucket_targets = balanced_bucket_targets(target_total, BUCKETS)
    rng = random.Random(seed)
    selected = []
    for bucket in BUCKETS:
        selected.extend(
            select_bucket_rows(
                source_rows,
                bucket=bucket,
                target=bucket_targets[bucket],
                max_no_per_bucket=max_no_per_bucket,
                max_per_scene=max_per_scene,
                rng=rng,
            )
        )
    selected = sorted(selected, key=lambda row: (str(row.get("bucket")), row_key(row)))
    return add_adjudication_fields(selected)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a human adjudication subset for the RQ1 large assisted audit."
    )
    parser.add_argument(
        "--source-csv",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/large_manual_review_samples.csv"),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/human_adjudication_pack.csv"),
    )
    parser.add_argument(
        "--manifest-json",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/human_adjudication_manifest.json"),
    )
    parser.add_argument(
        "--summary-md",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/human_adjudication_pack.md"),
    )
    parser.add_argument("--seed", type=int, default=20260616)
    parser.add_argument("--target-total", type=int, default=100)
    parser.add_argument("--max-no-per-bucket", type=int, default=8)
    parser.add_argument("--max-per-scene", type=int, default=4)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows, source_fields = load_csv(args.source_csv)
    selected = build_adjudication_pack(
        rows,
        seed=args.seed,
        target_total=args.target_total,
        max_no_per_bucket=args.max_no_per_bucket,
        max_per_scene=args.max_per_scene,
    )
    output_fields = ADJUDICATION_FIELDS + [
        field for field in source_fields if field not in ADJUDICATION_FIELDS
    ]
    write_csv(args.output_csv, selected, output_fields)
    manifest = build_manifest(
        source_csv=args.source_csv,
        output_csv=args.output_csv,
        rows=selected,
        source_rows=rows,
        seed=args.seed,
        target_total=args.target_total,
        max_no_per_bucket=args.max_no_per_bucket,
        max_per_scene=args.max_per_scene,
    )
    args.manifest_json.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_markdown_summary(args.summary_md, manifest)
    print(
        f"[human-adjudication-pack] rows={len(selected)} "
        f"output={args.output_csv}"
    )


if __name__ == "__main__":
    main()
