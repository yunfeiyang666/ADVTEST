import argparse
import csv
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence


STRUCTURAL_FIELDS = (
    "method",
    "generation_budget",
    "suite_size",
    "micro_l0",
    "micro_l1",
    "micro_l2",
    "unique_l2_per_question",
    "auc_micro_l2",
)

ERROR_FIELDS = (
    "method",
    "vlm_call_budget",
    "actual_vlm_calls",
    "unique_failures",
    "unique_failures_per_100_calls",
    "calls_per_unique_failure",
    "duplicate_failure_rate",
    "failure_category_count",
)


def build_structural_rows(summary: Mapping) -> list:
    generation_budget = int(summary["generation_budget"])
    rows = []
    for method, payload in summary["methods"].items():
        metrics = payload["summary"]
        rows.append(
            {
                "method": method,
                "generation_budget": generation_budget,
                "suite_size": int(metrics["suite_size"]),
                "micro_l0": float(metrics["micro_l0"]),
                "micro_l1": float(metrics["micro_l1"]),
                "micro_l2": float(metrics["micro_l2"]),
                "unique_l2_per_question": float(
                    metrics["unique_l2_per_question"]
                ),
                "auc_micro_l2": float(metrics["auc_micro_l2"]),
            }
        )
    return sorted(rows, key=lambda row: row["micro_l2"], reverse=True)


def _error_row(result: Mapping, budget: int) -> dict:
    return {
        "method": str(result["method"]),
        "vlm_call_budget": int(budget),
        "actual_vlm_calls": int(result["vlm_calls"]),
        "unique_failures": int(result["unique_failures"]),
        "unique_failures_per_100_calls": float(
            result["unique_failures_per_100_calls"]
        ),
        "calls_per_unique_failure": result.get("calls_per_unique_failure"),
        "duplicate_failure_rate": float(result["duplicate_failure_rate"]),
        "failure_category_count": int(result["failure_category_count"]),
    }


def build_common_budget_rows(results: Sequence[Mapping]) -> list:
    if not results:
        return []
    actual_calls = {int(result["vlm_calls"]) for result in results}
    if len(actual_calls) != 1:
        raise ValueError(
            "Common-budget table requires every method to use the same "
            "VLM-call budget"
        )
    budget = actual_calls.pop()
    rows = [_error_row(result, budget) for result in results]
    return sorted(
        rows, key=lambda row: row["unique_failures_per_100_calls"], reverse=True
    )


def build_capacity_rows(
    results: Sequence[Mapping], *, requested_vlm_call_budget: int
) -> list:
    rows = [
        _error_row(result, requested_vlm_call_budget) for result in results
    ]
    return sorted(
        rows, key=lambda row: row["unique_failures_per_100_calls"], reverse=True
    )


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_error_results(paths: Iterable[Path]) -> list:
    results = []
    for path in paths:
        payload = load_json(path)
        if isinstance(payload, list):
            results.extend(payload)
        else:
            results.append(payload)
    return results


def _write_csv(path: Path, rows: Sequence[Mapping], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _markdown_table(rows: Sequence[Mapping], fieldnames: Sequence[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(fieldnames) + " |",
        "|" + "|".join("---" for _ in fieldnames) + "|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(row.get(field, "")) for field in fieldnames)
            + " |"
        )
    return "\n".join(lines)


def write_tables(
    output_dir: Path,
    structural_rows: Sequence[Mapping],
    common_rows: Sequence[Mapping],
    capacity_rows: Sequence[Mapping],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "table_a_structural_coverage": list(structural_rows),
        "table_b_common_vlm_call_budget": list(common_rows),
        "table_c_capacity_at_requested_budget": list(capacity_rows),
    }
    (output_dir / "experiment_tables.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_csv(
        output_dir / "table_a_structural_coverage.csv",
        structural_rows,
        STRUCTURAL_FIELDS,
    )
    _write_csv(
        output_dir / "table_b_common_vlm_call_budget.csv",
        common_rows,
        ERROR_FIELDS,
    )
    _write_csv(
        output_dir / "table_c_capacity.csv",
        capacity_rows,
        ERROR_FIELDS,
    )
    report = [
        "# RQ1 Experiment Tables",
        "",
        "## Table A: Structural Coverage at Equal Generation Budget",
        "",
        _markdown_table(structural_rows, STRUCTURAL_FIELDS),
        "",
        "## Table B: Error Detection at Equal VLM-Call Budget",
        "",
        _markdown_table(common_rows, ERROR_FIELDS),
        "",
        "## Table C: Capacity at Requested VLM-Call Budget",
        "",
        _markdown_table(capacity_rows, ERROR_FIELDS),
        "",
    ]
    (output_dir / "experiment_tables.md").write_text(
        "\n".join(report), encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the three RQ1 result tables.")
    parser.add_argument("--structural-summary", type=Path, required=True)
    parser.add_argument("--common-results", type=Path, nargs="+", required=True)
    parser.add_argument("--capacity-results", type=Path, nargs="+", required=True)
    parser.add_argument("--requested-vlm-call-budget", type=int, default=1000)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    structural_rows = build_structural_rows(load_json(args.structural_summary))
    common_rows = build_common_budget_rows(
        load_error_results(args.common_results)
    )
    capacity_rows = build_capacity_rows(
        load_error_results(args.capacity_results),
        requested_vlm_call_budget=args.requested_vlm_call_budget,
    )
    write_tables(args.output_dir, structural_rows, common_rows, capacity_rows)
    print(f"[tables] Results written to {args.output_dir}")


if __name__ == "__main__":
    main()
