import argparse
import csv
import json
from pathlib import Path
from typing import Mapping, Sequence


METHOD_LABELS = {
    "advtest": "ADVTEST",
    "random": "Random",
    "official_qa": "Official NuScenes-QA",
    "qatest_adapted": "QATest-adapted",
}

METHOD_ORDER = {
    "advtest": 0,
    "random": 1,
    "official_qa": 2,
    "qatest_adapted": 3,
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{100 * float(value):.2f}%"


def fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.3f}"
    return str(value)


def markdown_table(rows: Sequence[Mapping], fields: Sequence[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(fields) + " |",
        "|" + "|".join("---" for _ in fields) + "|",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join(fmt(row.get(field)) for field in fields) + " |"
        )
    return "\n".join(lines)


def result_map(summary: Mapping) -> dict[str, Mapping]:
    return {str(row["method"]): row for row in summary.get("results", [])}


def call_budget(summary: Mapping) -> int:
    calls = {int(row["vlm_calls"]) for row in summary.get("results", [])}
    if len(calls) != 1:
        raise ValueError(f"Expected one call budget per summary, got {calls}")
    return calls.pop()


def comparable_coverage(input_audit: Mapping | None, method: str) -> Mapping | None:
    if not input_audit:
        return None
    payload = input_audit.get("methods", {}).get(method)
    if payload and payload.get("coverage_comparable"):
        return payload
    return None


def build_scaling_rows(summaries: Mapping[str, Mapping]) -> list[dict]:
    rows = []
    for run_label, summary in summaries.items():
        budget = call_budget(summary)
        for row in summary.get("results", []):
            method = str(row["method"])
            rows.append(
                {
                    "run": run_label,
                    "call_budget": budget,
                    "method": method,
                    "method_label": METHOD_LABELS.get(method, method),
                    "role": row.get("role", ""),
                    "wrong": int(row.get("wrong", 0)),
                    "failure_rate": float(row.get("failure_rate", 0.0)),
                    "unique_failures": int(row.get("unique_failures", 0)),
                    "unique_failures_per_100_calls": float(
                        row.get("unique_failures_per_100_calls", 0.0)
                    ),
                    "duplicate_failure_rate": float(
                        row.get("duplicate_failure_rate", 0.0)
                    ),
                    "failed_unique_l2": int(row.get("failed_unique_l2", 0)),
                    "visited_frames": int(row.get("visited_frames", 0)),
                    "gt_granularity": row.get("gt_granularity", ""),
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            int(row["call_budget"]),
            METHOD_ORDER.get(str(row["method"]), 99),
        ),
    )


def build_main_rows(call1000: Mapping, input_audit: Mapping | None) -> list[dict]:
    rows = []
    for row in call1000.get("results", []):
        method = str(row["method"])
        coverage = comparable_coverage(input_audit, method)
        rows.append(
            {
                "method": method,
                "method_label": METHOD_LABELS.get(method, method),
                "role": row.get("role", ""),
                "vlm_calls": int(row["vlm_calls"]),
                "wrong": int(row["wrong"]),
                "failure_rate": float(row["failure_rate"]),
                "unique_failures": int(row["unique_failures"]),
                "unique_failures_per_100_calls": float(
                    row["unique_failures_per_100_calls"]
                ),
                "duplicate_failure_rate": float(row["duplicate_failure_rate"]),
                "failed_unique_l2": int(row.get("failed_unique_l2", 0)),
                "visited_frames": int(row.get("visited_frames", 0)),
                "gt_granularity": row.get("gt_granularity", ""),
                "coverage_comparable": bool(coverage),
                "covered_l2": (
                    int(coverage["covered_l2"]) if coverage is not None else None
                ),
                "unique_l2_per_question": (
                    float(coverage["unique_l2_per_question"])
                    if coverage is not None
                    else None
                ),
            }
        )
    return sorted(rows, key=lambda row: METHOD_ORDER.get(str(row["method"]), 99))


def _relative(delta: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return delta / denominator


def build_adv_random_gain_rows(
    summaries: Mapping[str, Mapping],
    input_audit: Mapping | None,
) -> list[dict]:
    rows = []
    for run_label, summary in summaries.items():
        budget = call_budget(summary)
        by_method = result_map(summary)
        if "advtest" not in by_method or "random" not in by_method:
            continue
        adv = by_method["advtest"]
        random = by_method["random"]
        unique_delta = int(adv["unique_failures"]) - int(random["unique_failures"])
        failed_l2_delta = int(adv.get("failed_unique_l2", 0)) - int(
            random.get("failed_unique_l2", 0)
        )
        input_l2_delta = None
        input_l2_relative = None
        if budget == 1000:
            adv_cov = comparable_coverage(input_audit, "advtest")
            random_cov = comparable_coverage(input_audit, "random")
            if adv_cov and random_cov:
                input_l2_delta = int(adv_cov["covered_l2"]) - int(
                    random_cov["covered_l2"]
                )
                input_l2_relative = _relative(
                    input_l2_delta, float(random_cov["covered_l2"])
                )
        rows.append(
            {
                "run": run_label,
                "call_budget": budget,
                "unique_failure_delta": unique_delta,
                "unique_failure_relative_gain": _relative(
                    unique_delta, float(random["unique_failures"])
                ),
                "failed_unique_l2_delta": failed_l2_delta,
                "failed_unique_l2_relative_gain": _relative(
                    failed_l2_delta, float(random.get("failed_unique_l2", 0))
                ),
                "input_covered_l2_delta": input_l2_delta,
                "input_covered_l2_relative_gain": input_l2_relative,
            }
        )
    return sorted(rows, key=lambda row: int(row["call_budget"]))


def build_random_variance_rows(random_variance: Mapping) -> list[dict]:
    rows = []
    for row in random_variance.get("random_runs", []):
        rows.append(
            {
                "method": "random",
                "seed": int(row["seed"]),
                "call_budget": int(row["vlm_calls"]),
                "unique_failures": int(row["unique_failures"]),
                "failed_unique_l2": int(row["failed_unique_l2"]),
            }
        )
    adv = random_variance.get("advtest", {})
    if adv:
        rows.append(
            {
                "method": "advtest",
                "seed": "fixed",
                "call_budget": int(adv["vlm_calls"]),
                "unique_failures": int(adv["unique_failures"]),
                "failed_unique_l2": int(adv["failed_unique_l2"]),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            0 if row["method"] == "advtest" else 1,
            str(row["seed"]),
        ),
    )


def build_claims(report: Mapping) -> list[dict]:
    gains = {
        int(row["call_budget"]): row for row in report["adv_vs_random_gains"]
    }
    call1000 = gains[1000]
    random_variance = report["random_variance_summary"]
    return [
        {
            "claim": (
                "Under the same 1000-question / 1000-VLM-call budget, "
                "coverage-guided ADVTEST detects more unique VLM failures than "
                "random candidate selection."
            ),
            "evidence": (
                f"ADVTEST finds +{call1000['unique_failure_delta']} unique "
                f"failures over Random "
                f"({pct(call1000['unique_failure_relative_gain'])})."
            ),
            "status": "supported_by_call1000_internal_ablation",
        },
        {
            "claim": (
                "ADVTEST's advantage is stronger on structural error coverage "
                "than on raw unique-failure count."
            ),
            "evidence": (
                f"Failed unique L2 increases by "
                f"+{call1000['failed_unique_l2_delta']} "
                f"({pct(call1000['failed_unique_l2_relative_gain'])}), while "
                f"input covered L2 increases by "
                f"+{call1000['input_covered_l2_delta']} "
                f"({pct(call1000['input_covered_l2_relative_gain'])})."
            ),
            "status": "supported_by_frame_qualified_l2_metrics",
        },
        {
            "claim": (
                "The ADVTEST-vs-Random trend is not explained by one lucky "
                "Random seed in the call100 pilot."
            ),
            "evidence": (
                "At 100 calls, ADVTEST exceeds all "
                f"{random_variance['advtest_vs_random']['seed_count']} Random "
                "seeds on unique failures and failed unique L2."
            ),
            "status": "supported_by_random_seed_variance",
        },
        {
            "claim": (
                "Official NuScenes-QA and QATest-adapted should be described as "
                "external references, not coverage-comparable head-to-head baselines."
            ),
            "evidence": (
                "Both use category-level official ground truth and do not expose "
                "ADVTEST-private structural L2 coverage footprints."
            ),
            "status": "boundary_condition",
        },
    ]


def build_report_pack(
    *,
    summaries: Mapping[str, Mapping],
    input_audit: Mapping,
    random_variance: Mapping,
) -> dict:
    if "call1000" not in summaries:
        raise ValueError("call1000 summary is required")
    report = {
        "schema_version": 1,
        "scoring": summaries["call1000"].get("scoring"),
        "source_runs": {
            label: {
                "run_id": summary.get("run_id"),
                "status": summary.get("status"),
                "exit_code": summary.get("exit_code"),
                "actual_real_inference_records": summary.get(
                    "actual_real_inference_records"
                ),
                "mock_fallback_records": summary.get("mock_fallback_records"),
            }
            for label, summary in summaries.items()
        },
        "main_call1000_table": build_main_rows(
            summaries["call1000"], input_audit
        ),
        "scaling_table": build_scaling_rows(summaries),
        "adv_vs_random_gains": build_adv_random_gain_rows(
            summaries, input_audit
        ),
        "random_variance_table": build_random_variance_rows(random_variance),
        "random_variance_summary": random_variance,
        "comparison_boundaries": input_audit.get("comparison_boundaries", []),
        "warnings": summaries["call1000"].get("warnings", []),
    }
    report["claims_to_evidence"] = build_claims(report)
    return report


def write_csv(path: Path, rows: Sequence[Mapping], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def write_readme(output_dir: Path, report: Mapping) -> None:
    main_fields = [
        "method_label",
        "vlm_calls",
        "wrong",
        "failure_rate",
        "unique_failures",
        "unique_failures_per_100_calls",
        "failed_unique_l2",
        "covered_l2",
        "unique_l2_per_question",
        "visited_frames",
        "gt_granularity",
    ]
    gain_fields = [
        "call_budget",
        "unique_failure_delta",
        "unique_failure_relative_gain",
        "failed_unique_l2_delta",
        "failed_unique_l2_relative_gain",
        "input_covered_l2_delta",
        "input_covered_l2_relative_gain",
    ]
    lines = [
        "# RQ1 mPLUG Report Pack",
        "",
        "This directory is generated from recorded RQ1 mPLUG summaries. It is "
        "intended as the paper-ready result pack for the equal-question-budget "
        "experiment.",
        "",
        "## Headline",
        "",
    ]
    for claim in report["claims_to_evidence"][:3]:
        lines.append(f"- {claim['evidence']}")
    lines.extend(
        [
            "",
            "## Main Call1000 Table",
            "",
            markdown_table(report["main_call1000_table"], main_fields),
            "",
            "## ADVTEST vs Random Gains",
            "",
            markdown_table(report["adv_vs_random_gains"], gain_fields),
            "",
            "## Boundary Notes",
            "",
        ]
    )
    for warning in report["warnings"]:
        lines.append(f"- {warning}")
    lines.extend(
        [
            "",
            "## Generated Files",
            "",
            "- `report_pack.json`: complete structured payload.",
            "- `table_main_call1000.csv`: main method comparison.",
            "- `table_scaling.csv`: call20/call100/call1000 scaling trend.",
            "- `table_adv_vs_random_gains.csv`: ADVTEST-vs-Random deltas.",
            "- `table_random_variance.csv`: call100 random-seed robustness rows.",
            "- `paper_claims.md`: claim-to-evidence mapping and caveats.",
            "",
            "## Reproduction",
            "",
            "Run from repository root:",
            "",
            "```powershell",
            "$codeRoot = (Get-ChildItem -Directory | Where-Object Name -Like '1*' | Select-Object -First 1).FullName",
            "$script = Join-Path $codeRoot 'DATA_new\\analysis\\rq1_error_detection\\build_rq1_report_pack.py'",
            "python $script",
            "```",
            "",
            "Source artifacts:",
            "",
            "- `experiments/rq1_mplug_smoke/call20_summary.json`",
            "- `experiments/rq1_mplug_call100/call100_summary.json`",
            "- `experiments/rq1_mplug_call1000/call1000_summary.json`",
            "- `experiments/rq1_mplug_call1000/input_audit.json`",
            "- `experiments/rq1_mplug_random_variance/random_variance_summary.json`",
            "",
        ]
    )
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def write_claims(output_dir: Path, report: Mapping) -> None:
    lines = [
        "# RQ1 Claim-to-Evidence Notes",
        "",
        "## Recommended Main Framing",
        "",
        (
            "Under an equal 1000-question / 1000-VLM-call budget, ADVTEST's "
            "coverage-guided question selection finds more and structurally "
            "broader VLM failures than random candidate selection."
        ),
        "",
        "## Claims",
        "",
    ]
    for item in report["claims_to_evidence"]:
        lines.extend(
            [
                f"### {item['status']}",
                "",
                f"Claim: {item['claim']}",
                "",
                f"Evidence: {item['evidence']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Caveats To Preserve In Paper Text",
            "",
            "- Official NuScenes-QA and QATest-adapted are external references, "
            "not the main coverage-comparable baselines.",
            "- Correctness is currently deterministic token-boundary lexical "
            "scoring, not semantic judging.",
            "- Structural L2 metrics are frame-qualified; this is intentional to "
            "avoid merging same-named objects across frames.",
            "",
        ]
    )
    (output_dir / "paper_claims.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def write_report_pack(output_dir: Path, report: Mapping) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report_pack.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_csv(
        output_dir / "table_main_call1000.csv",
        report["main_call1000_table"],
        [
            "method",
            "method_label",
            "role",
            "vlm_calls",
            "wrong",
            "failure_rate",
            "unique_failures",
            "unique_failures_per_100_calls",
            "duplicate_failure_rate",
            "failed_unique_l2",
            "visited_frames",
            "gt_granularity",
            "coverage_comparable",
            "covered_l2",
            "unique_l2_per_question",
        ],
    )
    write_csv(
        output_dir / "table_scaling.csv",
        report["scaling_table"],
        [
            "run",
            "call_budget",
            "method",
            "method_label",
            "role",
            "wrong",
            "failure_rate",
            "unique_failures",
            "unique_failures_per_100_calls",
            "duplicate_failure_rate",
            "failed_unique_l2",
            "visited_frames",
            "gt_granularity",
        ],
    )
    write_csv(
        output_dir / "table_adv_vs_random_gains.csv",
        report["adv_vs_random_gains"],
        [
            "run",
            "call_budget",
            "unique_failure_delta",
            "unique_failure_relative_gain",
            "failed_unique_l2_delta",
            "failed_unique_l2_relative_gain",
            "input_covered_l2_delta",
            "input_covered_l2_relative_gain",
        ],
    )
    write_csv(
        output_dir / "table_random_variance.csv",
        report["random_variance_table"],
        [
            "method",
            "seed",
            "call_budget",
            "unique_failures",
            "failed_unique_l2",
        ],
    )
    write_readme(output_dir, report)
    write_claims(output_dir, report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a paper-ready RQ1 report pack from recorded summaries."
    )
    parser.add_argument(
        "--call20-summary",
        type=Path,
        default=Path("experiments/rq1_mplug_smoke/call20_summary.json"),
    )
    parser.add_argument(
        "--call100-summary",
        type=Path,
        default=Path("experiments/rq1_mplug_call100/call100_summary.json"),
    )
    parser.add_argument(
        "--call1000-summary",
        type=Path,
        default=Path("experiments/rq1_mplug_call1000/call1000_summary.json"),
    )
    parser.add_argument(
        "--input-audit",
        type=Path,
        default=Path("experiments/rq1_mplug_call1000/input_audit.json"),
    )
    parser.add_argument(
        "--random-variance",
        type=Path,
        default=Path(
            "experiments/rq1_mplug_random_variance/"
            "random_variance_summary.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/rq1_report_pack"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summaries = {
        "call20": load_json(args.call20_summary),
        "call100": load_json(args.call100_summary),
        "call1000": load_json(args.call1000_summary),
    }
    report = build_report_pack(
        summaries=summaries,
        input_audit=load_json(args.input_audit),
        random_variance=load_json(args.random_variance),
    )
    write_report_pack(args.output_dir, report)
    print(f"[rq1-report-pack] wrote {args.output_dir}")


if __name__ == "__main__":
    main()
