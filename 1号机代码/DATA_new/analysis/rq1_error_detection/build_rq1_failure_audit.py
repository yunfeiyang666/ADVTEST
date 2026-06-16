import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DEFAULT_RESULTS_DIR = Path(
    "scratch/rq1_mplug_call1000/runs/"
    "mplug-four-methods-call1000/results"
)

MANUAL_REVIEW_FIELDS = [
    "audit_group",
    "bucket",
    "method",
    "l2_key",
    "scene_frame",
    "l2_item",
    "family",
    "question_index",
    "question_id",
    "question",
    "answer",
    "predicted",
    "image_path",
    "manual_valid_failure",
    "manual_issue_type",
    "manual_notes",
]


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def raw_prediction(row: Mapping) -> str:
    if row.get("raw_model_output") is not None:
        return str(row["raw_model_output"])
    return str(row.get("predicted") or "")


def frame_qualified_l2_items(row: Mapping) -> list[str]:
    scene_frame = str(row.get("scene_frame") or "unknown")
    return sorted(f"{scene_frame}::{item}" for item in (row.get("l2_items") or []))


def structural_failure_signature(row: Mapping) -> str:
    l2_keys = frame_qualified_l2_items(row)
    if l2_keys:
        return "l2|" + "|".join(l2_keys)
    return (
        f"semantic|{row.get('scene_frame') or 'unknown'}|"
        f"{row.get('family') or 'unknown'}|{row.get('answer') or ''}"
    )


def split_l2_key(l2_key: str) -> tuple[str, str]:
    if "::" not in l2_key:
        return "unknown", l2_key
    scene_frame, item = l2_key.split("::", 1)
    return scene_frame, item


def compact_failure_record(row: Mapping) -> dict:
    l2_keys = frame_qualified_l2_items(row)
    return {
        "method": str(row.get("method") or ""),
        "question_index": int(row.get("question_index") or 0),
        "scene_frame": str(row.get("scene_frame") or "unknown"),
        "question_id": str(row.get("question_id") or ""),
        "source_question_id": str(row.get("source_question_id") or ""),
        "question_source": str(row.get("question_source") or ""),
        "family": str(row.get("family") or "unknown"),
        "question": str(row.get("question") or row.get("prompt") or ""),
        "answer": row.get("answer"),
        "predicted": raw_prediction(row),
        "image_path": str(row.get("image_path") or ""),
        "l2_items": list(row.get("l2_items") or []),
        "l2_keys": l2_keys,
        "failure_signature": structural_failure_signature(row),
    }


def load_failures(path: Path) -> list[dict]:
    failures = []
    for row in iter_jsonl(path):
        if row.get("is_correct") is False:
            failures.append(compact_failure_record(row))
    return failures


def first_by_signature(records: Sequence[Mapping]) -> dict[str, Mapping]:
    result = {}
    for record in records:
        result.setdefault(str(record["failure_signature"]), record)
    return result


def first_by_l2_key(records: Sequence[Mapping]) -> dict[str, Mapping]:
    result = {}
    for record in records:
        for l2_key in record.get("l2_keys") or []:
            result.setdefault(str(l2_key), record)
    return result


def family_counts(records: Sequence[Mapping]) -> dict[str, int]:
    return dict(Counter(str(record.get("family") or "unknown") for record in records))


def stratified_l2_keys(
    keys: Iterable[str],
    index: Mapping[str, Mapping],
    *,
    limit: int,
) -> list[str]:
    groups = defaultdict(list)
    for key in sorted(keys):
        family = str(index[key].get("family") or "unknown")
        groups[family].append(key)

    selected = []
    while len(selected) < limit and groups:
        progressed = False
        for family in sorted(list(groups)):
            if not groups[family]:
                del groups[family]
                continue
            selected.append(groups[family].pop(0))
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def sample_for_l2_key(record: Mapping, l2_key: str) -> dict:
    scene_frame, l2_item = split_l2_key(l2_key)
    return {
        "l2_key": l2_key,
        "scene_frame": scene_frame,
        "l2_item": l2_item,
        "method": record["method"],
        "family": record["family"],
        "question_index": record["question_index"],
        "question_id": record["question_id"],
        "question": record["question"],
        "answer": record["answer"],
        "predicted": record["predicted"],
        "image_path": record["image_path"],
        "failure_signature": record["failure_signature"],
    }


def build_l2_samples(
    *,
    adv_l2: set[str],
    random_l2: set[str],
    adv_l2_index: Mapping[str, Mapping],
    random_l2_index: Mapping[str, Mapping],
    sample_per_bucket: int,
) -> dict:
    adv_only = adv_l2 - random_l2
    random_only = random_l2 - adv_l2
    shared = adv_l2 & random_l2

    adv_only_keys = stratified_l2_keys(
        adv_only, adv_l2_index, limit=sample_per_bucket
    )
    random_only_keys = stratified_l2_keys(
        random_only, random_l2_index, limit=sample_per_bucket
    )
    shared_keys = stratified_l2_keys(
        shared, adv_l2_index, limit=sample_per_bucket
    )

    return {
        "advtest_only_l2": [
            sample_for_l2_key(adv_l2_index[key], key) for key in adv_only_keys
        ],
        "random_only_l2": [
            sample_for_l2_key(random_l2_index[key], key)
            for key in random_only_keys
        ],
        "shared_l2_pairs": [
            {
                "l2_key": key,
                "advtest": sample_for_l2_key(adv_l2_index[key], key),
                "random": sample_for_l2_key(random_l2_index[key], key),
            }
            for key in shared_keys
        ],
    }


def build_failure_audit(
    advtest_raw: Path,
    random_raw: Path,
    *,
    sample_per_bucket: int = 12,
) -> dict:
    adv_records = load_failures(advtest_raw)
    random_records = load_failures(random_raw)

    adv_signatures = set(first_by_signature(adv_records))
    random_signatures = set(first_by_signature(random_records))
    adv_l2_index = first_by_l2_key(adv_records)
    random_l2_index = first_by_l2_key(random_records)
    adv_l2 = set(adv_l2_index)
    random_l2 = set(random_l2_index)

    return {
        "schema_version": 1,
        "audit_basis": "frame_qualified_failed_l2_and_structural_failure_signature",
        "source_paths": {
            "advtest": str(advtest_raw),
            "random": str(random_raw),
        },
        "summary": {
            "advtest": {
                "failed_questions": len(adv_records),
                "unique_failure_signatures": len(adv_signatures),
                "failed_unique_l2": len(adv_l2),
                "family_counts": family_counts(adv_records),
            },
            "random": {
                "failed_questions": len(random_records),
                "unique_failure_signatures": len(random_signatures),
                "failed_unique_l2": len(random_l2),
                "family_counts": family_counts(random_records),
            },
            "signature_overlap": {
                "advtest_only": len(adv_signatures - random_signatures),
                "random_only": len(random_signatures - adv_signatures),
                "shared": len(adv_signatures & random_signatures),
            },
            "failed_l2_overlap": {
                "advtest_only": len(adv_l2 - random_l2),
                "random_only": len(random_l2 - adv_l2),
                "shared": len(adv_l2 & random_l2),
            },
        },
        "samples": build_l2_samples(
            adv_l2=adv_l2,
            random_l2=random_l2,
            adv_l2_index=adv_l2_index,
            random_l2_index=random_l2_index,
            sample_per_bucket=sample_per_bucket,
        ),
        "manual_review_protocol": {
            "goal": (
                "Manually inspect whether sampled failures are real VLM "
                "perception/reasoning errors rather than scoring or wording artifacts."
            ),
            "recommended_labels": [
                "valid_visual_or_structural_error",
                "answer_granularity_mismatch",
                "ambiguous_question",
                "mosaic_or_label_artifact",
                "lexical_scoring_artifact",
                "other",
            ],
        },
    }


def flatten_manual_review_rows(audit: Mapping) -> list[dict]:
    rows = []

    def add_row(group: str, bucket: str, sample: Mapping) -> None:
        rows.append(
            {
                "audit_group": group,
                "bucket": bucket,
                "method": sample["method"],
                "l2_key": sample["l2_key"],
                "scene_frame": sample["scene_frame"],
                "l2_item": sample["l2_item"],
                "family": sample["family"],
                "question_index": sample["question_index"],
                "question_id": sample["question_id"],
                "question": sample["question"],
                "answer": sample["answer"],
                "predicted": sample["predicted"],
                "image_path": sample["image_path"],
                "manual_valid_failure": "",
                "manual_issue_type": "",
                "manual_notes": "",
            }
        )

    for index, sample in enumerate(
        audit["samples"]["advtest_only_l2"], start=1
    ):
        add_row(f"advtest_only_l2_{index:03d}", "advtest_only_l2", sample)
    for index, sample in enumerate(
        audit["samples"]["random_only_l2"], start=1
    ):
        add_row(f"random_only_l2_{index:03d}", "random_only_l2", sample)
    for index, pair in enumerate(audit["samples"]["shared_l2_pairs"], start=1):
        group = f"shared_l2_{index:03d}"
        add_row(group, "shared_l2_advtest", pair["advtest"])
        add_row(group, "shared_l2_random", pair["random"])
    return rows


def write_csv(path: Path, rows: Sequence[Mapping], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def markdown_table(rows: Sequence[Mapping], fields: Sequence[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(fields) + " |",
        "|" + "|".join("---" for _ in fields) + "|",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join(str(row.get(field, "")) for field in fields) + " |"
        )
    return "\n".join(lines)


def overlap_rows(audit: Mapping) -> list[dict]:
    summary = audit["summary"]
    return [
        {
            "level": "question_failure_signature",
            "advtest_count": summary["advtest"]["unique_failure_signatures"],
            "random_count": summary["random"]["unique_failure_signatures"],
            "advtest_only": summary["signature_overlap"]["advtest_only"],
            "random_only": summary["signature_overlap"]["random_only"],
            "shared": summary["signature_overlap"]["shared"],
        },
        {
            "level": "frame_qualified_failed_l2",
            "advtest_count": summary["advtest"]["failed_unique_l2"],
            "random_count": summary["random"]["failed_unique_l2"],
            "advtest_only": summary["failed_l2_overlap"]["advtest_only"],
            "random_only": summary["failed_l2_overlap"]["random_only"],
            "shared": summary["failed_l2_overlap"]["shared"],
        },
    ]


def write_readme(output_dir: Path, audit: Mapping) -> None:
    fields = [
        "level",
        "advtest_count",
        "random_count",
        "advtest_only",
        "random_only",
        "shared",
    ]
    rows = overlap_rows(audit)
    lines = [
        "# RQ1 Failure Audit Pack",
        "",
        "This directory samples concrete call1000 mPLUG failures for manual "
        "inspection. It focuses on ADVTEST vs Random because this is the "
        "coverage-comparable internal ablation.",
        "",
        "## Overlap Summary",
        "",
        markdown_table(rows, fields),
        "",
        "## Interpretation",
        "",
        "- `question_failure_signature` compares failed questions after "
        "frame-qualifying structural L2 items.",
        "- `frame_qualified_failed_l2` compares the structural L2 items touched "
        "by failed questions. This is the better lens for checking whether "
        "ADVTEST finds broader structural error space.",
        "- Manual review should focus first on `advtest_only_l2` samples, then "
        "inspect `shared_l2` pairs to compare how the two methods expose the "
        "same structural miss.",
        "",
        "## Manual Review Protocol",
        "",
        "Open `manual_review_samples.csv` and fill:",
        "",
        "- `manual_valid_failure`: yes / no / uncertain",
        "- `manual_issue_type`: one of "
        "`valid_visual_or_structural_error`, `answer_granularity_mismatch`, "
        "`ambiguous_question`, `mosaic_or_label_artifact`, "
        "`lexical_scoring_artifact`, `other`",
        "- `manual_notes`: short evidence from the image and text",
        "",
        "## Generated Files",
        "",
        "- `failure_audit.json`: complete structured audit payload.",
        "- `failure_overlap_summary.csv`: overlap counts.",
        "- `manual_review_samples.csv`: deterministic samples for human review.",
        "",
        "## Reproduction",
        "",
        "Run from repository root:",
        "",
        "```powershell",
        "$codeRoot = (Get-ChildItem -Directory | Where-Object Name -Like '1*' | Select-Object -First 1).FullName",
        "$script = Join-Path $codeRoot 'DATA_new\\analysis\\rq1_error_detection\\build_rq1_failure_audit.py'",
        "python $script",
        "```",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def write_failure_audit(output_dir: Path, audit: Mapping) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "failure_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_csv(
        output_dir / "failure_overlap_summary.csv",
        overlap_rows(audit),
        [
            "level",
            "advtest_count",
            "random_count",
            "advtest_only",
            "random_only",
            "shared",
        ],
    )
    write_csv(
        output_dir / "manual_review_samples.csv",
        flatten_manual_review_rows(audit),
        MANUAL_REVIEW_FIELDS,
    )
    write_readme(output_dir, audit)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an RQ1 failure sample audit pack from call1000 raw outputs."
    )
    parser.add_argument(
        "--advtest-raw",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "advtest_suite_raw_results.jsonl",
    )
    parser.add_argument(
        "--random-raw",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "random_suite_raw_results.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/rq1_failure_audit"),
    )
    parser.add_argument("--sample-per-bucket", type=int, default=12)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    audit = build_failure_audit(
        args.advtest_raw,
        args.random_raw,
        sample_per_bucket=args.sample_per_bucket,
    )
    write_failure_audit(args.output_dir, audit)
    print(
        f"[rq1-failure-audit] wrote {args.output_dir} "
        f"samples={len(flatten_manual_review_rows(audit))}"
    )


if __name__ == "__main__":
    main()
