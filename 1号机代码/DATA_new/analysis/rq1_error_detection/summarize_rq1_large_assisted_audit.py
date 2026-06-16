import argparse
import csv
import json
import math
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


def load_csv(path: Path) -> tuple[list[dict], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path: Path, rows: Sequence[Mapping], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_label(value: str) -> str:
    return str(value or "").strip().lower()


def assisted_label_for_row(row: Mapping) -> tuple[str, str, str]:
    auto_label = normalize_label(row.get("auto_valid_failure", ""))
    auto_issue = str(row.get("auto_issue_type") or "other").strip()
    auto_confidence = str(row.get("auto_confidence") or "unknown").strip()
    auto_notes = str(row.get("auto_notes") or "").strip()

    if auto_label not in VALID_LABELS:
        auto_label = "uncertain"
    if auto_issue not in ISSUE_TYPES:
        auto_issue = "other"

    if auto_label == "uncertain":
        notes = (
            "ASSISTED_REVIEW: retained as uncertain because auto-prefill "
            f"confidence is {auto_confidence}. {auto_notes}"
        ).strip()
        return "uncertain", auto_issue, notes

    notes = (
        "ASSISTED_REVIEW: copied from auto-prefill "
        f"(confidence={auto_confidence}). {auto_notes}"
    ).strip()
    return auto_label, auto_issue, notes


def fill_assisted_labels(rows: Sequence[Mapping], *, overwrite: bool = False) -> list[dict]:
    filled = []
    for row in rows:
        next_row = dict(row)
        has_manual = bool(normalize_label(next_row.get("manual_valid_failure", "")))
        if overwrite or not has_manual:
            label, issue, notes = assisted_label_for_row(next_row)
            next_row["manual_valid_failure"] = label
            next_row["manual_issue_type"] = issue
            next_row["manual_notes"] = notes
        filled.append(next_row)
    return filled


def validate_rows(rows: Sequence[Mapping]) -> None:
    if not rows:
        raise ValueError("Review CSV is empty")
    for index, row in enumerate(rows, start=1):
        label = normalize_label(row.get("manual_valid_failure", ""))
        issue = str(row.get("manual_issue_type") or "").strip()
        notes = str(row.get("manual_notes") or "").strip()
        if label not in VALID_LABELS:
            raise ValueError(f"Row {index} invalid manual_valid_failure: {label}")
        if issue not in ISSUE_TYPES:
            raise ValueError(f"Row {index} invalid manual_issue_type: {issue}")
        if not notes:
            raise ValueError(f"Row {index} missing manual_notes")


def wilson_interval(successes: int, total: int, z: float = 1.96) -> dict:
    if total == 0:
        return {"lower": None, "upper": None}
    phat = successes / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    half = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denom
    return {"lower": max(0.0, center - half), "upper": min(1.0, center + half)}


def count_dict(counter: Counter) -> dict:
    return {key: counter[key] for key in sorted(counter)}


def bucket_universe(bucket: str, manifest: Mapping) -> int:
    universe = manifest["universe"]
    if bucket == "advtest_only_l2":
        return int(universe["advtest_only_l2"])
    if bucket == "random_only_l2":
        return int(universe["random_only_l2"])
    if bucket in {"shared_l2_advtest", "shared_l2_random"}:
        return int(universe["shared_l2"])
    raise ValueError(f"Unknown bucket: {bucket}")


def summarize_group(rows: Sequence[Mapping], universe_total: int | None = None) -> dict:
    labels = Counter(normalize_label(row.get("manual_valid_failure", "")) for row in rows)
    issues = Counter(str(row.get("manual_issue_type") or "").strip() for row in rows)
    confidence = Counter(str(row.get("auto_confidence") or "unknown") for row in rows)
    total = len(rows)
    valid_yes = labels["yes"]
    interval = wilson_interval(valid_yes, total)
    payload = {
        "sample_rows": total,
        "valid_yes": valid_yes,
        "valid_no": labels["no"],
        "valid_uncertain": labels["uncertain"],
        "valid_rate": valid_yes / total if total else 0.0,
        "wilson_95_rate_lower": interval["lower"],
        "wilson_95_rate_upper": interval["upper"],
        "label_counts": count_dict(labels),
        "issue_type_counts": count_dict(issues),
        "auto_confidence_counts": count_dict(confidence),
    }
    if universe_total is not None:
        payload["universe_total"] = universe_total
        payload["estimated_valid_total"] = universe_total * payload["valid_rate"]
        payload["estimated_valid_total_lower"] = (
            universe_total * interval["lower"] if interval["lower"] is not None else None
        )
        payload["estimated_valid_total_upper"] = (
            universe_total * interval["upper"] if interval["upper"] is not None else None
        )
    return payload


def summarize_assisted_review(rows: Sequence[Mapping], manifest: Mapping) -> dict:
    validate_rows(rows)
    by_bucket = defaultdict(list)
    by_method = defaultdict(list)
    for row in rows:
        by_bucket[str(row.get("bucket") or "unknown")].append(row)
        by_method[str(row.get("method") or "unknown")].append(row)

    bucket_payload = {
        bucket: summarize_group(group_rows, bucket_universe(bucket, manifest))
        for bucket, group_rows in sorted(by_bucket.items())
    }
    method_payload = {
        method: summarize_group(group_rows)
        for method, group_rows in sorted(by_method.items())
    }
    adv = bucket_payload["advtest_only_l2"]
    rnd = bucket_payload["random_only_l2"]
    return {
        "schema_version": 1,
        "label_source": "assisted_review_from_auto_prefill",
        "review_caveat": (
            "Labels are assisted by deterministic auto-prefill heuristics. "
            "Rows marked uncertain require further human adjudication."
        ),
        "total_rows": len(rows),
        "overall": summarize_group(rows),
        "by_bucket": bucket_payload,
        "by_method": method_payload,
        "exclusive_effect": {
            "advtest_only_estimated_valid_total": adv["estimated_valid_total"],
            "random_only_estimated_valid_total": rnd["estimated_valid_total"],
            "advtest_minus_random_estimated_valid_total": (
                adv["estimated_valid_total"] - rnd["estimated_valid_total"]
            ),
            "conservative_lower_minus_upper": (
                adv["estimated_valid_total_lower"] - rnd["estimated_valid_total_upper"]
            ),
        },
    }


def pct(value: float | None) -> str:
    if value is None:
        return "n/a"
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


def write_summary_md(path: Path, summary: Mapping) -> None:
    bucket_rows = []
    for bucket, payload in summary["by_bucket"].items():
        bucket_rows.append(
            {
                "bucket": bucket,
                "sample_rows": payload["sample_rows"],
                "valid_yes": payload["valid_yes"],
                "no": payload["valid_no"],
                "uncertain": payload["valid_uncertain"],
                "valid_rate": pct(payload["valid_rate"]),
                "wilson_95": (
                    f"[{pct(payload['wilson_95_rate_lower'])}, "
                    f"{pct(payload['wilson_95_rate_upper'])}]"
                ),
                "est_valid_total": f"{payload['estimated_valid_total']:.1f}",
            }
        )
    effect = summary["exclusive_effect"]
    lines = [
        "# RQ1 Large Assisted Failure Audit Summary",
        "",
        "## Caveat",
        "",
        summary["review_caveat"],
        "",
        "## Overall",
        "",
        f"- Rows: {summary['total_rows']}",
        f"- Assisted valid rows: {summary['overall']['valid_yes']} "
        f"({pct(summary['overall']['valid_rate'])})",
        f"- Assisted uncertain rows: {summary['overall']['valid_uncertain']}",
        "",
        "## By Bucket",
        "",
        markdown_table(
            bucket_rows,
            [
                "bucket",
                "sample_rows",
                "valid_yes",
                "no",
                "uncertain",
                "valid_rate",
                "wilson_95",
                "est_valid_total",
            ],
        ),
        "",
        "## Exclusive L2 Estimate",
        "",
        f"- ADVTEST-only estimated valid total: "
        f"{effect['advtest_only_estimated_valid_total']:.1f}",
        f"- Random-only estimated valid total: "
        f"{effect['random_only_estimated_valid_total']:.1f}",
        f"- Difference: "
        f"{effect['advtest_minus_random_estimated_valid_total']:.1f}",
        f"- Conservative lower-minus-upper: "
        f"{effect['conservative_lower_minus_upper']:.1f}",
        "",
        "Use the conservative lower-minus-upper value as the quick stress test: "
        "if it stays positive, ADVTEST's larger exclusive L2 space remains "
        "larger even after Wilson uncertainty on assisted labels.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fill and summarize large RQ1 assisted failure audit labels."
    )
    parser.add_argument(
        "--review-csv",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/large_manual_review_samples.csv"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/large_sampling_manifest.json"),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/large_manual_review_samples.csv"),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/large_assisted_review_summary.json"),
    )
    parser.add_argument(
        "--summary-md",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/large_assisted_review_summary.md"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows, fieldnames = load_csv(args.review_csv)
    filled = fill_assisted_labels(rows, overwrite=args.overwrite)
    manifest = load_json(args.manifest)
    summary = summarize_assisted_review(filled, manifest)
    write_csv(args.output_csv, filled, fieldnames)
    args.summary_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_summary_md(args.summary_md, summary)
    print(
        f"[large-assisted-audit] rows={summary['total_rows']} "
        f"valid={summary['overall']['valid_yes']} "
        f"uncertain={summary['overall']['valid_uncertain']}"
    )


if __name__ == "__main__":
    main()
