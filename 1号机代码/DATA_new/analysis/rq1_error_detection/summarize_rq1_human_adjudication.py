import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping, Sequence


VALID_LABELS = {"yes", "no", "uncertain"}
AGREEMENT_LABELS = {"yes", "no"}
ISSUE_TYPES = {
    "valid_visual_or_structural_error",
    "answer_granularity_mismatch",
    "ambiguous_question",
    "mosaic_or_label_artifact",
    "lexical_scoring_artifact",
    "other",
}
BUCKETS = [
    "advtest_only_l2",
    "random_only_l2",
    "shared_l2_advtest",
    "shared_l2_random",
]


def load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value: str) -> str:
    return str(value or "").strip().lower()


def count_dict(counter: Counter) -> dict:
    return {key: counter[key] for key in sorted(counter)}


def counter_by(rows: Sequence[Mapping], fields: Sequence[str]) -> dict:
    counter = Counter(
        tuple(str(row.get(field) or "") for field in fields) for row in rows
    )
    return {" | ".join(key): counter[key] for key in sorted(counter)}


def has_any_human_field(row: Mapping) -> bool:
    return any(
        str(row.get(field) or "").strip()
        for field in [
            "human_valid_failure",
            "human_issue_type",
            "human_agrees_with_assisted",
            "human_notes",
        ]
    )


def validate_and_split_rows(rows: Sequence[Mapping]) -> tuple[list[dict], list[dict]]:
    reviewed = []
    pending = []
    for index, row in enumerate(rows, start=1):
        if not has_any_human_field(row):
            pending.append(dict(row))
            continue

        human_label = normalize(row.get("human_valid_failure", ""))
        assisted_label = normalize(row.get("manual_valid_failure", ""))
        issue_type = str(row.get("human_issue_type") or "").strip()
        agreement = normalize(row.get("human_agrees_with_assisted", ""))
        notes = str(row.get("human_notes") or "").strip()

        if human_label not in VALID_LABELS:
            raise ValueError(f"Row {index} invalid human_valid_failure: {human_label}")
        if assisted_label not in VALID_LABELS:
            raise ValueError(f"Row {index} invalid assisted label: {assisted_label}")
        if issue_type not in ISSUE_TYPES:
            raise ValueError(f"Row {index} invalid human_issue_type: {issue_type}")
        if not notes:
            raise ValueError(f"Row {index} missing human_notes")

        derived_agreement = "yes" if human_label == assisted_label else "no"
        if agreement:
            if agreement not in AGREEMENT_LABELS:
                raise ValueError(
                    f"Row {index} invalid human_agrees_with_assisted: {agreement}"
                )
            if agreement != derived_agreement:
                raise ValueError(
                    f"Row {index} agreement field conflicts with labels: "
                    f"{agreement} vs derived {derived_agreement}"
                )
        next_row = dict(row)
        next_row["_derived_agreement"] = derived_agreement
        reviewed.append(next_row)
    return reviewed, pending


def summarize_reviewed_rows(reviewed: Sequence[Mapping]) -> dict:
    total = len(reviewed)
    if total == 0:
        return {
            "reviewed_rows": 0,
            "agreement_yes": 0,
            "agreement_no": 0,
            "agreement_rate": None,
            "human_label_counts": {},
            "assisted_label_counts": {},
            "human_issue_type_counts": {},
        }
    agreement_counts = Counter(row["_derived_agreement"] for row in reviewed)
    return {
        "reviewed_rows": total,
        "agreement_yes": agreement_counts["yes"],
        "agreement_no": agreement_counts["no"],
        "agreement_rate": agreement_counts["yes"] / total,
        "human_label_counts": count_dict(
            Counter(normalize(row.get("human_valid_failure", "")) for row in reviewed)
        ),
        "assisted_label_counts": count_dict(
            Counter(normalize(row.get("manual_valid_failure", "")) for row in reviewed)
        ),
        "human_issue_type_counts": count_dict(
            Counter(str(row.get("human_issue_type") or "").strip() for row in reviewed)
        ),
    }


def group_summary(reviewed: Sequence[Mapping], field: str) -> dict:
    grouped = defaultdict(list)
    for row in reviewed:
        grouped[str(row.get(field) or "unknown")].append(row)
    return {
        key: summarize_reviewed_rows(group_rows)
        for key, group_rows in sorted(grouped.items())
    }


def bucket_universe(bucket: str, manifest: Mapping) -> int:
    universe = manifest["universe"]
    if bucket == "advtest_only_l2":
        return int(universe["advtest_only_l2"])
    if bucket == "random_only_l2":
        return int(universe["random_only_l2"])
    if bucket in {"shared_l2_advtest", "shared_l2_random"}:
        return int(universe["shared_l2"])
    raise ValueError(f"Unknown bucket: {bucket}")


def human_yes_rates(reviewed: Sequence[Mapping], fields: Sequence[str]) -> dict:
    groups = defaultdict(list)
    for row in reviewed:
        key = tuple(str(row.get(field) or "") for field in fields)
        groups[key].append(row)

    rates = {}
    for key, group_rows in groups.items():
        yes = sum(
            1 for row in group_rows if normalize(row.get("human_valid_failure", "")) == "yes"
        )
        rates[key] = {
            "reviewed_rows": len(group_rows),
            "human_yes": yes,
            "human_yes_rate": yes / len(group_rows) if group_rows else None,
        }
    return rates


def fallback_assisted_rate(label: str) -> float:
    if label == "yes":
        return 1.0
    return 0.0


def calibrate_source_estimates(
    *,
    source_rows: Sequence[Mapping],
    reviewed: Sequence[Mapping],
    universe_manifest: Mapping,
    min_cell_n: int,
) -> dict | None:
    if not reviewed:
        return None

    by_bucket_label = human_yes_rates(reviewed, ["bucket", "manual_valid_failure"])
    by_label = human_yes_rates(reviewed, ["manual_valid_failure"])
    bucket_payload = {}

    for bucket in BUCKETS:
        bucket_source = [row for row in source_rows if row.get("bucket") == bucket]
        label_counts = Counter(
            normalize(row.get("manual_valid_failure", "")) for row in bucket_source
        )
        estimated_valid_in_source = 0.0
        components = []
        for label, count in sorted(label_counts.items()):
            cell_key = (bucket, label)
            label_key = (label,)
            if cell_key in by_bucket_label and by_bucket_label[cell_key]["reviewed_rows"] >= min_cell_n:
                source = "bucket_label"
                rate_payload = by_bucket_label[cell_key]
                rate = rate_payload["human_yes_rate"]
                reviewed_rows = rate_payload["reviewed_rows"]
            elif label_key in by_label:
                source = "label_fallback"
                rate_payload = by_label[label_key]
                rate = rate_payload["human_yes_rate"]
                reviewed_rows = rate_payload["reviewed_rows"]
            else:
                source = "assisted_identity_fallback"
                rate = fallback_assisted_rate(label)
                reviewed_rows = 0

            estimated_valid = count * rate
            estimated_valid_in_source += estimated_valid
            components.append(
                {
                    "assisted_label": label,
                    "source_rows": count,
                    "calibration_source": source,
                    "calibration_reviewed_rows": reviewed_rows,
                    "human_yes_rate": rate,
                    "estimated_valid_source_rows": estimated_valid,
                }
            )

        source_total = len(bucket_source)
        calibrated_rate = (
            estimated_valid_in_source / source_total if source_total else 0.0
        )
        universe_total = bucket_universe(bucket, universe_manifest)
        bucket_payload[bucket] = {
            "source_rows": source_total,
            "universe_total": universe_total,
            "calibrated_source_valid_estimate": estimated_valid_in_source,
            "calibrated_valid_rate": calibrated_rate,
            "calibrated_universe_valid_estimate": universe_total * calibrated_rate,
            "components": components,
        }

    adv = bucket_payload["advtest_only_l2"]
    rnd = bucket_payload["random_only_l2"]
    return {
        "min_cell_n": min_cell_n,
        "rate_tables": {
            "by_bucket_label": {
                " | ".join(key): value for key, value in sorted(by_bucket_label.items())
            },
            "by_label": {
                " | ".join(key): value for key, value in sorted(by_label.items())
            },
        },
        "by_bucket": bucket_payload,
        "exclusive_effect": {
            "advtest_only_calibrated_universe_valid_estimate": adv[
                "calibrated_universe_valid_estimate"
            ],
            "random_only_calibrated_universe_valid_estimate": rnd[
                "calibrated_universe_valid_estimate"
            ],
            "advtest_minus_random_calibrated_universe_valid_estimate": (
                adv["calibrated_universe_valid_estimate"]
                - rnd["calibrated_universe_valid_estimate"]
            ),
        },
    }


def build_summary(
    *,
    adjudication_rows: Sequence[Mapping],
    source_rows: Sequence[Mapping],
    universe_manifest: Mapping,
    min_cell_n: int,
) -> dict:
    reviewed, pending = validate_and_split_rows(adjudication_rows)
    summary = {
        "schema_version": 1,
        "label_source": "human_adjudication_calibration",
        "status": "complete" if not pending else "pending_human_review",
        "total_rows": len(adjudication_rows),
        "reviewed_rows": len(reviewed),
        "pending_rows": len(pending),
        "overall": summarize_reviewed_rows(reviewed),
        "by_bucket": group_summary(reviewed, "bucket"),
        "by_assisted_label": group_summary(reviewed, "manual_valid_failure"),
        "selected_distribution": {
            "by_bucket": counter_by(adjudication_rows, ["bucket"]),
            "by_assisted_label": counter_by(adjudication_rows, ["manual_valid_failure"]),
            "by_selection_reason": counter_by(adjudication_rows, ["selection_reason"]),
        },
    }
    calibration = calibrate_source_estimates(
        source_rows=source_rows,
        reviewed=reviewed,
        universe_manifest=universe_manifest,
        min_cell_n=min_cell_n,
    )
    if calibration is None:
        summary["calibrated_estimates"] = {
            "status": "not_available_until_human_rows_are_reviewed"
        }
    else:
        summary["calibrated_estimates"] = calibration
    return summary


def pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{100 * value:.1f}%"


def write_summary_md(path: Path, summary: Mapping) -> None:
    lines = [
        "# RQ1 Human Adjudication Summary",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Rows: `{summary['total_rows']}`",
        f"- Reviewed rows: `{summary['reviewed_rows']}`",
        f"- Pending rows: `{summary['pending_rows']}`",
        f"- Agreement rate: `{pct(summary['overall']['agreement_rate'])}`",
        "",
        "## Reviewed Label Counts",
        "",
        f"- Human labels: `{summary['overall']['human_label_counts']}`",
        f"- Assisted labels among reviewed rows: `{summary['overall']['assisted_label_counts']}`",
        "",
    ]
    calibration = summary["calibrated_estimates"]
    if calibration.get("status"):
        lines.extend(
            [
                "## Calibrated Estimates",
                "",
                f"- Status: `{calibration['status']}`",
                "",
                "Fill the `human_*` columns in `human_adjudication_pack.csv` and rerun this script to produce calibrated estimates.",
                "",
            ]
        )
    else:
        effect = calibration["exclusive_effect"]
        lines.extend(
            [
                "## Calibrated Exclusive L2 Estimate",
                "",
                f"- ADVTEST-only calibrated valid total: "
                f"{effect['advtest_only_calibrated_universe_valid_estimate']:.1f}",
                f"- Random-only calibrated valid total: "
                f"{effect['random_only_calibrated_universe_valid_estimate']:.1f}",
                f"- Difference: "
                f"{effect['advtest_minus_random_calibrated_universe_valid_estimate']:.1f}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize RQ1 human adjudication labels and calibrated estimates."
    )
    parser.add_argument(
        "--adjudication-csv",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/human_adjudication_pack.csv"),
    )
    parser.add_argument(
        "--source-csv",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/large_manual_review_samples.csv"),
    )
    parser.add_argument(
        "--universe-manifest",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/large_sampling_manifest.json"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/human_adjudication_summary.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large/human_adjudication_summary.md"),
    )
    parser.add_argument("--min-cell-n", type=int, default=3)
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail if any adjudication rows are still pending.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = build_summary(
        adjudication_rows=load_csv(args.adjudication_csv),
        source_rows=load_csv(args.source_csv),
        universe_manifest=load_json(args.universe_manifest),
        min_cell_n=args.min_cell_n,
    )
    if args.require_complete and summary["pending_rows"]:
        raise SystemExit(
            f"Human adjudication is incomplete: pending_rows={summary['pending_rows']}"
        )
    args.output_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_summary_md(args.output_md, summary)
    print(
        f"[human-adjudication-summary] status={summary['status']} "
        f"reviewed={summary['reviewed_rows']} pending={summary['pending_rows']}"
    )


if __name__ == "__main__":
    main()
