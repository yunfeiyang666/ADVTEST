import argparse
import json
from pathlib import Path
from typing import Mapping


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def one_decimal_pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def method_map(report_pack: Mapping) -> dict[str, Mapping]:
    return {row["method"]: row for row in report_pack["main_call1000_table"]}


def call1000_gain(report_pack: Mapping) -> Mapping:
    for row in report_pack["adv_vs_random_gains"]:
        if int(row["call_budget"]) == 1000:
            return row
    raise ValueError("call1000 gain row not found")


def build_adjusted_estimate(
    failure_audit: Mapping,
    manual_summary: Mapping,
) -> dict:
    l2_overlap = failure_audit["summary"]["failed_l2_overlap"]
    bucket_summary = manual_summary["by_bucket"]

    adv_only_total = int(l2_overlap["advtest_only"])
    random_only_total = int(l2_overlap["random_only"])
    shared_total = int(l2_overlap["shared"])
    adv_rate = float(bucket_summary["advtest_only_l2"]["valid_rate"])
    random_rate = float(bucket_summary["random_only_l2"]["valid_rate"])
    shared_rate = (
        float(bucket_summary["shared_l2_advtest"]["valid_rate"])
        + float(bucket_summary["shared_l2_random"]["valid_rate"])
    ) / 2

    adv_est = adv_only_total * adv_rate
    random_est = random_only_total * random_rate
    shared_est = shared_total * shared_rate
    return {
        "basis": (
            "qualitative audit extrapolation from 12 sampled L2 rows per "
            "exclusive bucket and 12 shared L2 pairs"
        ),
        "advtest_only_failed_l2": adv_only_total,
        "random_only_failed_l2": random_only_total,
        "shared_failed_l2": shared_total,
        "advtest_only_valid_rate": adv_rate,
        "random_only_valid_rate": random_rate,
        "shared_valid_rate_mean": shared_rate,
        "estimated_valid_advtest_only_l2": adv_est,
        "estimated_valid_random_only_l2": random_est,
        "estimated_valid_shared_l2": shared_est,
        "estimated_advtest_only_minus_random_only_valid_l2": adv_est - random_est,
        "estimated_advtest_only_vs_random_only_ratio": (
            adv_est / random_est if random_est else None
        ),
        "caveat": (
            "This is a qualitative audit estimate, not a statistical "
            "significance claim. It should be reported as supporting evidence "
            "for the structural coverage interpretation."
        ),
    }


def build_narrative_payload(
    report_pack: Mapping,
    failure_audit: Mapping,
    manual_summary: Mapping,
) -> dict:
    methods = method_map(report_pack)
    gain = call1000_gain(report_pack)
    adjusted = build_adjusted_estimate(failure_audit, manual_summary)
    return {
        "schema_version": 1,
        "main_finding": {
            "advtest_failed_unique_l2": methods["advtest"]["failed_unique_l2"],
            "random_failed_unique_l2": methods["random"]["failed_unique_l2"],
            "failed_unique_l2_delta": gain["failed_unique_l2_delta"],
            "failed_unique_l2_relative_gain": gain[
                "failed_unique_l2_relative_gain"
            ],
            "advtest_unique_failures": methods["advtest"]["unique_failures"],
            "random_unique_failures": methods["random"]["unique_failures"],
            "unique_failure_delta": gain["unique_failure_delta"],
            "unique_failure_relative_gain": gain[
                "unique_failure_relative_gain"
            ],
            "input_covered_l2_delta": gain["input_covered_l2_delta"],
            "input_covered_l2_relative_gain": gain[
                "input_covered_l2_relative_gain"
            ],
        },
        "failure_overlap": failure_audit["summary"],
        "manual_audit": {
            "total_rows": manual_summary["total_rows"],
            "overall_valid_rate": manual_summary["overall"]["valid_rate"],
            "overall_valid_yes": manual_summary["overall"]["valid_yes"],
            "overall_invalid_or_uncertain": manual_summary["overall"][
                "invalid_or_uncertain"
            ],
            "advtest_only_valid_rate": manual_summary["by_bucket"][
                "advtest_only_l2"
            ]["valid_rate"],
            "random_only_valid_rate": manual_summary["by_bucket"][
                "random_only_l2"
            ]["valid_rate"],
            "answer_granularity_mismatch": manual_summary[
                "issue_type_counts"
            ].get("answer_granularity_mismatch", 0),
        },
        "adjusted_effective_failure_estimate": adjusted,
        "recommended_claim": (
            "Under an equal 1000-question / 1000-VLM-call budget, ADVTEST "
            "finds a broader structural error space than random candidate "
            "selection. Manual inspection indicates that both methods produce "
            "valid structural failures and answer-format boundary cases; "
            "ADVTEST's advantage is a coverage-breadth effect from "
            "substantially larger structural coverage, not from higher "
            "per-sample validity."
        ),
    }


def write_markdown(path: Path, payload: Mapping) -> None:
    main = payload["main_finding"]
    overlap = payload["failure_overlap"]
    manual = payload["manual_audit"]
    adjusted = payload["adjusted_effective_failure_estimate"]

    lines = [
        "# RQ1 Results Narrative",
        "",
        "## Main Finding",
        "",
        (
            "At the formal 1000-question / 1000-VLM-call budget, ADVTEST "
            f"finds {main['advtest_unique_failures']} unique failures versus "
            f"{main['random_unique_failures']} for Random "
            f"(+{main['unique_failure_delta']}, "
            f"{pct(main['unique_failure_relative_gain'])})."
        ),
        "",
        (
            "The larger effect appears in structural coverage: ADVTEST touches "
            f"{main['advtest_failed_unique_l2']} failed unique L2 items versus "
            f"{main['random_failed_unique_l2']} for Random "
            f"(+{main['failed_unique_l2_delta']}, "
            f"{pct(main['failed_unique_l2_relative_gain'])}). Its generated "
            f"questions also cover +{main['input_covered_l2_delta']} input L2 "
            f"items over Random "
            f"({pct(main['input_covered_l2_relative_gain'])})."
        ),
        "",
        "## Manual Audit Interpretation",
        "",
        (
            f"The manual audit reviewed {manual['total_rows']} sampled failure "
            f"rows. {manual['overall_valid_yes']} were judged valid "
            f"visual/structural failures "
            f"({one_decimal_pct(manual['overall_valid_rate'])}), while "
            f"{manual['overall_invalid_or_uncertain']} were boundary cases."
        ),
        "",
        (
            "Random-only samples have a slightly higher sampled validity rate "
            f"({one_decimal_pct(manual['random_only_valid_rate'])}) than "
            f"ADVTEST-only samples "
            f"({one_decimal_pct(manual['advtest_only_valid_rate'])}). This "
            "should not be read as Random being better overall, because the "
            "exclusive structural space is much smaller for Random."
        ),
        "",
        "## Adjusted Effective Failure Estimate",
        "",
        (
            "Using the manual audit only as a qualitative extrapolation, "
            f"ADVTEST-only failed L2 has about "
            f"{adjusted['estimated_valid_advtest_only_l2']:.1f} estimated "
            "valid structural failures "
            f"({adjusted['advtest_only_failed_l2']} * "
            f"{one_decimal_pct(adjusted['advtest_only_valid_rate'])}), "
            f"whereas Random-only has about "
            f"{adjusted['estimated_valid_random_only_l2']:.1f} "
            f"({adjusted['random_only_failed_l2']} * "
            f"{one_decimal_pct(adjusted['random_only_valid_rate'])})."
        ),
        "",
        (
            "Thus, even with Random-only's slightly higher sampled validity "
            "rate, ADVTEST's larger exclusive structural space gives an "
            f"estimated +{adjusted['estimated_advtest_only_minus_random_only_valid_l2']:.1f} "
            "additional valid exclusive failed L2 items "
            f"(~{adjusted['estimated_advtest_only_vs_random_only_ratio']:.2f}x "
            "Random-only)."
        ),
        "",
        "## Limitations",
        "",
        "- The adjusted estimate is qualitative and based on a small audit sample.",
        "- Correctness is still deterministic token-boundary lexical scoring.",
        "- Instance-level answers are strict; rows marked answer-granularity mismatch should not be counted as strong visual failures.",
        "- The mosaics do not render object IDs, so the review is scene-graph-assisted rather than purely visual.",
        "",
        "## Paper-Ready Paragraph",
        "",
        (
            "Under an equal 1000-question budget, ADVTEST identifies broader "
            "structural failure coverage than random candidate selection. It "
            f"finds {main['advtest_unique_failures']} unique failures compared "
            f"with {main['random_unique_failures']} for Random "
            f"(+{main['unique_failure_delta']}, "
            f"{pct(main['unique_failure_relative_gain'])}), and its failed "
            f"unique L2 coverage is {main['advtest_failed_unique_l2']} versus "
            f"{main['random_failed_unique_l2']} "
            f"(+{main['failed_unique_l2_delta']}, "
            f"{pct(main['failed_unique_l2_relative_gain'])}). A manual audit "
            f"of {manual['total_rows']} sampled failures shows that both "
            "ADVTEST-only and Random-only samples contain valid structural "
            "errors as well as answer-format boundary cases. Random-only has "
            "a slightly higher sampled validity rate, but its exclusive failed "
            "L2 space is much smaller; a qualitative extrapolation estimates "
            f"{adjusted['estimated_valid_advtest_only_l2']:.0f} valid "
            "ADVTEST-only failed L2 items versus "
            f"{adjusted['estimated_valid_random_only_l2']:.0f} for "
            "Random-only. We therefore interpret ADVTEST's advantage as a "
            "coverage-breadth effect rather than a per-sample validity effect."
        ),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build paper-ready RQ1 narrative from report and manual audit."
    )
    parser.add_argument(
        "--report-pack",
        type=Path,
        default=Path("experiments/rq1_report_pack/report_pack.json"),
    )
    parser.add_argument(
        "--failure-audit",
        type=Path,
        default=Path("experiments/rq1_failure_audit/failure_audit.json"),
    )
    parser.add_argument(
        "--manual-summary",
        type=Path,
        default=Path("experiments/rq1_failure_audit/manual_review_summary.json"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("experiments/rq1_report_pack/rq1_results_narrative.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("experiments/rq1_report_pack/rq1_results_narrative.md"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = build_narrative_payload(
        load_json(args.report_pack),
        load_json(args.failure_audit),
        load_json(args.manual_summary),
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_markdown(args.output_md, payload)
    print(f"[rq1-narrative] wrote {args.output_md}")


if __name__ == "__main__":
    main()
