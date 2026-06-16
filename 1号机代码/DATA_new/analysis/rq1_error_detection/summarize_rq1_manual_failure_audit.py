import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping, Sequence


VALID_LABELS = {"yes", "no", "uncertain"}

ISSUE_TYPES = {
    "valid_visual_or_structural_error",
    "answer_granularity_mismatch",
    "ambiguous_question",
    "mosaic_or_label_artifact",
    "lexical_scoring_artifact",
    "other",
}


def load_review_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _require(value: str, message: str) -> str:
    if not value:
        raise ValueError(message)
    return value


def validate_rows(rows: Sequence[Mapping]) -> None:
    if not rows:
        raise ValueError("Manual review CSV is empty")
    for index, row in enumerate(rows, start=1):
        label = str(row.get("manual_valid_failure") or "").strip().lower()
        issue = str(row.get("manual_issue_type") or "").strip()
        _require(label, f"Row {index} missing manual_valid_failure")
        _require(issue, f"Row {index} missing manual_issue_type")
        _require(
            str(row.get("manual_notes") or "").strip(),
            f"Row {index} missing manual_notes",
        )
        if label not in VALID_LABELS:
            raise ValueError(f"Row {index} has invalid label: {label}")
        if issue not in ISSUE_TYPES:
            raise ValueError(f"Row {index} has invalid issue type: {issue}")


def counter_dict(counter: Counter) -> dict:
    return {key: counter[key] for key in sorted(counter)}


def summarize_rows(rows: Sequence[Mapping]) -> dict:
    validate_rows(rows)
    by_bucket = defaultdict(list)
    by_method = defaultdict(list)
    by_issue_type = Counter()
    label_counts = Counter()

    for row in rows:
        bucket = str(row.get("bucket") or "unknown")
        method = str(row.get("method") or "unknown")
        label = str(row.get("manual_valid_failure") or "").strip().lower()
        issue = str(row.get("manual_issue_type") or "").strip()
        by_bucket[bucket].append(row)
        by_method[method].append(row)
        label_counts[label] += 1
        by_issue_type[issue] += 1

    def summarize_group(group_rows: Sequence[Mapping]) -> dict:
        labels = Counter(
            str(row.get("manual_valid_failure") or "").strip().lower()
            for row in group_rows
        )
        issues = Counter(
            str(row.get("manual_issue_type") or "").strip()
            for row in group_rows
        )
        total = len(group_rows)
        valid = labels["yes"]
        invalid_or_uncertain = total - valid
        return {
            "total": total,
            "valid_yes": valid,
            "valid_no": labels["no"],
            "valid_uncertain": labels["uncertain"],
            "valid_rate": valid / total if total else 0.0,
            "invalid_or_uncertain": invalid_or_uncertain,
            "label_counts": counter_dict(labels),
            "issue_type_counts": counter_dict(issues),
        }

    return {
        "schema_version": 1,
        "total_rows": len(rows),
        "overall": summarize_group(rows),
        "by_bucket": {
            bucket: summarize_group(group_rows)
            for bucket, group_rows in sorted(by_bucket.items())
        },
        "by_method": {
            method: summarize_group(group_rows)
            for method, group_rows in sorted(by_method.items())
        },
        "issue_type_counts": counter_dict(by_issue_type),
        "label_counts": counter_dict(label_counts),
    }


def fmt_pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def markdown_table(rows: Sequence[Mapping], fields: Sequence[str]) -> str:
    lines = [
        "| " + " | ".join(fields) + " |",
        "|" + "|".join("---" for _ in fields) + "|",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join(str(row.get(field, "")) for field in fields) + " |"
        )
    return "\n".join(lines)


def write_summary(output_json: Path, output_md: Path, summary: Mapping) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    bucket_rows = []
    for bucket, payload in summary["by_bucket"].items():
        bucket_rows.append(
            {
                "bucket": bucket,
                "total": payload["total"],
                "valid_yes": payload["valid_yes"],
                "valid_no": payload["valid_no"],
                "uncertain": payload["valid_uncertain"],
                "valid_rate": fmt_pct(payload["valid_rate"]),
            }
        )
    method_rows = []
    for method, payload in summary["by_method"].items():
        method_rows.append(
            {
                "method": method,
                "total": payload["total"],
                "valid_yes": payload["valid_yes"],
                "valid_no": payload["valid_no"],
                "uncertain": payload["valid_uncertain"],
                "valid_rate": fmt_pct(payload["valid_rate"]),
            }
        )

    lines = [
        "# RQ1 Manual Failure Audit Summary",
        "",
        "## Overall",
        "",
        f"- Reviewed rows: {summary['total_rows']}",
        f"- Valid visual/structural failures: "
        f"{summary['overall']['valid_yes']} "
        f"({fmt_pct(summary['overall']['valid_rate'])})",
        f"- Invalid or uncertain rows: "
        f"{summary['overall']['invalid_or_uncertain']}",
        "",
        "## By Bucket",
        "",
        markdown_table(
            bucket_rows,
            ["bucket", "total", "valid_yes", "valid_no", "uncertain", "valid_rate"],
        ),
        "",
        "## By Method",
        "",
        markdown_table(
            method_rows,
            ["method", "total", "valid_yes", "valid_no", "uncertain", "valid_rate"],
        ),
        "",
        "## Issue Types",
        "",
    ]
    for issue_type, count in summary["issue_type_counts"].items():
        lines.append(f"- {issue_type}: {count}")
    lines.extend(
        [
            "",
            "## Paper Use",
            "",
            "Use the valid-rate numbers as a qualitative audit of sampled "
            "failures. Rows marked `answer_granularity_mismatch` should be "
            "reported as a scoring / answer-format boundary, not as strong "
            "visual-model failures.",
            "",
        ]
    )
    output_md.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize completed RQ1 manual failure audit annotations."
    )
    parser.add_argument(
        "--review-csv",
        type=Path,
        default=Path("experiments/rq1_failure_audit/manual_review_samples.csv"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("experiments/rq1_failure_audit/manual_review_summary.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("experiments/rq1_failure_audit/manual_review_summary.md"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = summarize_rows(load_review_rows(args.review_csv))
    write_summary(args.output_json, args.output_md, summary)
    print(
        f"[manual-failure-audit] rows={summary['total_rows']} "
        f"valid={summary['overall']['valid_yes']} "
        f"output={args.output_json}"
    )


if __name__ == "__main__":
    main()
