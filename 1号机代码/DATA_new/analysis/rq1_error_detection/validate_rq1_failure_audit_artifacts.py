import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence


VALID_LABELS = {"yes", "no", "uncertain"}
VALID_AGREEMENT = {"yes", "no"}
VALID_ISSUE_TYPES = {
    "valid_visual_or_structural_error",
    "answer_granularity_mismatch",
    "ambiguous_question",
    "mosaic_or_label_artifact",
    "lexical_scoring_artifact",
    "other",
}
HUMAN_FIELDS = [
    "human_valid_failure",
    "human_issue_type",
    "human_agrees_with_assisted",
    "human_notes",
]


def load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value: str) -> str:
    return str(value or "").strip().lower()


def count_field(rows: Sequence[Mapping], field: str) -> dict:
    counter = Counter(str(row.get(field) or "") for row in rows)
    return {key: counter[key] for key in sorted(counter)}


def count_by_fields(rows: Sequence[Mapping], fields: Sequence[str]) -> dict:
    counter = Counter(
        tuple(str(row.get(field) or "") for field in fields) for row in rows
    )
    return {" | ".join(key): counter[key] for key in sorted(counter)}


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise ValueError(f"{message}: expected {expected!r}, got {actual!r}")


def validate_large_audit(rows: Sequence[Mapping], assisted_summary: Mapping) -> dict:
    if not rows:
        raise ValueError("large_manual_review_samples.csv is empty")

    missing_manual = []
    for index, row in enumerate(rows, start=1):
        label = normalize(row.get("manual_valid_failure", ""))
        issue = str(row.get("manual_issue_type") or "").strip()
        notes = str(row.get("manual_notes") or "").strip()
        if label not in VALID_LABELS:
            missing_manual.append(index)
        if issue not in VALID_ISSUE_TYPES:
            missing_manual.append(index)
        if not notes:
            missing_manual.append(index)
    if missing_manual:
        raise ValueError(
            "large_manual_review_samples.csv has invalid manual fields at rows "
            f"{sorted(set(missing_manual))[:10]}"
        )

    assert_equal(len(rows), assisted_summary["total_rows"], "large row count mismatch")
    label_counts = count_field(rows, "manual_valid_failure")
    assert_equal(
        label_counts,
        assisted_summary["overall"]["label_counts"],
        "large assisted label counts mismatch",
    )
    for bucket, bucket_payload in assisted_summary["by_bucket"].items():
        bucket_rows = [row for row in rows if row.get("bucket") == bucket]
        assert_equal(
            len(bucket_rows),
            bucket_payload["sample_rows"],
            f"{bucket} sample_rows mismatch",
        )
        assert_equal(
            count_field(bucket_rows, "manual_valid_failure"),
            bucket_payload["label_counts"],
            f"{bucket} label_counts mismatch",
        )

    return {
        "rows": len(rows),
        "label_counts": label_counts,
        "bucket_counts": count_field(rows, "bucket"),
    }


def has_any_human_field(row: Mapping) -> bool:
    return any(str(row.get(field) or "").strip() for field in HUMAN_FIELDS)


def validate_reviewed_human_row(row: Mapping, row_number: int) -> None:
    human_label = normalize(row.get("human_valid_failure", ""))
    human_issue = str(row.get("human_issue_type") or "").strip()
    human_agreement = normalize(row.get("human_agrees_with_assisted", ""))
    human_notes = str(row.get("human_notes") or "").strip()
    assisted_label = normalize(row.get("manual_valid_failure", ""))

    if human_label not in VALID_LABELS:
        raise ValueError(f"Row {row_number} invalid human_valid_failure: {human_label}")
    if human_issue not in VALID_ISSUE_TYPES:
        raise ValueError(f"Row {row_number} invalid human_issue_type: {human_issue}")
    if human_agreement not in VALID_AGREEMENT:
        raise ValueError(
            f"Row {row_number} invalid human_agrees_with_assisted: {human_agreement}"
        )
    if not human_notes:
        raise ValueError(f"Row {row_number} missing human_notes")
    expected_agreement = "yes" if human_label == assisted_label else "no"
    if human_agreement != expected_agreement:
        raise ValueError(
            f"Row {row_number} human_agrees_with_assisted should be "
            f"{expected_agreement}, got {human_agreement}"
        )


def validate_human_pack(
    rows: Sequence[Mapping],
    manifest: Mapping,
    human_summary: Mapping,
) -> dict:
    if not rows:
        raise ValueError("human_adjudication_pack.csv is empty")

    ids = [str(row.get("adjudication_id") or "") for row in rows]
    if any(not row_id for row_id in ids):
        raise ValueError("human_adjudication_pack.csv has missing adjudication_id")
    if len(set(ids)) != len(ids):
        raise ValueError("human_adjudication_pack.csv has duplicate adjudication_id")

    reviewed = 0
    pending = 0
    for index, row in enumerate(rows, start=1):
        if has_any_human_field(row):
            validate_reviewed_human_row(row, index)
            reviewed += 1
        else:
            pending += 1

    selected = manifest["selected_counts"]
    assert_equal(len(rows), selected["rows"], "human pack row count mismatch")
    assert_equal(len(rows), human_summary["total_rows"], "human summary row count mismatch")
    assert_equal(reviewed, human_summary["reviewed_rows"], "human reviewed count mismatch")
    assert_equal(pending, human_summary["pending_rows"], "human pending count mismatch")

    expected_status = "complete" if pending == 0 else "pending_human_review"
    assert_equal(human_summary["status"], expected_status, "human summary status mismatch")
    assert_equal(count_field(rows, "bucket"), selected["by_bucket"], "human bucket counts mismatch")
    assert_equal(
        count_field(rows, "manual_valid_failure"),
        selected["by_label"],
        "human assisted-label counts mismatch",
    )
    assert_equal(
        count_by_fields(rows, ["bucket", "manual_valid_failure"]),
        selected["by_bucket_label"],
        "human bucket-label counts mismatch",
    )
    assert_equal(
        count_field(rows, "selection_reason"),
        selected["by_selection_reason"],
        "human selection-reason counts mismatch",
    )
    assert_equal(
        human_summary["selected_distribution"]["by_bucket"],
        selected["by_bucket"],
        "human summary selected bucket distribution mismatch",
    )
    assert_equal(
        human_summary["selected_distribution"]["by_assisted_label"],
        selected["by_label"],
        "human summary selected assisted-label distribution mismatch",
    )
    assert_equal(
        human_summary["selected_distribution"]["by_selection_reason"],
        selected["by_selection_reason"],
        "human summary selected reason distribution mismatch",
    )

    return {
        "rows": len(rows),
        "reviewed_rows": reviewed,
        "pending_rows": pending,
        "bucket_counts": count_field(rows, "bucket"),
        "assisted_label_counts": count_field(rows, "manual_valid_failure"),
        "selection_reason_counts": count_field(rows, "selection_reason"),
    }


def validate_artifacts(
    *,
    large_csv: Path,
    assisted_summary_json: Path,
    human_pack_csv: Path,
    human_manifest_json: Path,
    human_summary_json: Path,
) -> dict:
    large_rows = load_csv(large_csv)
    assisted_summary = load_json(assisted_summary_json)
    human_rows = load_csv(human_pack_csv)
    human_manifest = load_json(human_manifest_json)
    human_summary = load_json(human_summary_json)

    return {
        "schema_version": 1,
        "status": "ok",
        "large_audit": validate_large_audit(large_rows, assisted_summary),
        "human_adjudication": validate_human_pack(
            human_rows,
            human_manifest,
            human_summary,
        ),
        "checked_files": {
            "large_csv": str(large_csv),
            "assisted_summary_json": str(assisted_summary_json),
            "human_pack_csv": str(human_pack_csv),
            "human_manifest_json": str(human_manifest_json),
            "human_summary_json": str(human_summary_json),
        },
    }


def write_markdown(path: Path, summary: Mapping) -> None:
    lines = [
        "# RQ1 Failure Audit Artifact Validation",
        "",
        f"- Status: `{summary['status']}`",
        f"- Large audit rows: `{summary['large_audit']['rows']}`",
        f"- Large audit labels: `{summary['large_audit']['label_counts']}`",
        f"- Human adjudication rows: `{summary['human_adjudication']['rows']}`",
        f"- Human reviewed rows: `{summary['human_adjudication']['reviewed_rows']}`",
        f"- Human pending rows: `{summary['human_adjudication']['pending_rows']}`",
        f"- Human assisted labels: `{summary['human_adjudication']['assisted_label_counts']}`",
        "",
        "This validation checks CSV, manifest, and summary count consistency. It does not judge whether pending human rows are correct.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate RQ1 failure-audit CSV, manifest, and summary artifacts."
    )
    base = Path("experiments/rq1_failure_audit_large")
    parser.add_argument("--large-csv", type=Path, default=base / "large_manual_review_samples.csv")
    parser.add_argument(
        "--assisted-summary-json",
        type=Path,
        default=base / "large_assisted_review_summary.json",
    )
    parser.add_argument("--human-pack-csv", type=Path, default=base / "human_adjudication_pack.csv")
    parser.add_argument(
        "--human-manifest-json",
        type=Path,
        default=base / "human_adjudication_manifest.json",
    )
    parser.add_argument(
        "--human-summary-json",
        type=Path,
        default=base / "human_adjudication_summary.json",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=base / "artifact_validation_summary.json",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=base / "artifact_validation_summary.md",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = validate_artifacts(
        large_csv=args.large_csv,
        assisted_summary_json=args.assisted_summary_json,
        human_pack_csv=args.human_pack_csv,
        human_manifest_json=args.human_manifest_json,
        human_summary_json=args.human_summary_json,
    )
    args.output_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_markdown(args.output_md, summary)
    print(
        "[rq1-artifact-validation] status=ok "
        f"large_rows={summary['large_audit']['rows']} "
        f"human_rows={summary['human_adjudication']['rows']} "
        f"human_pending={summary['human_adjudication']['pending_rows']}"
    )


if __name__ == "__main__":
    main()
