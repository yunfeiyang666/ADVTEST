import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Mapping, Sequence


ROW_FIELDS = (
    "run_id",
    "method",
    "seed",
    "max_questions",
    "generation_budget",
    "frame_pool_size",
    "suite_size",
    "visited_frames",
    "micro_l0",
    "macro_l0",
    "micro_l1",
    "macro_l1",
    "micro_l2",
    "macro_l2",
    "unique_l2_per_question",
    "auc_micro_l2",
    "auc_macro_l2",
    "switch_reason_counts",
)


def build_sensitivity_rows(runs: Sequence[Mapping]) -> list:
    rows = []
    seen_deterministic = set()
    for run in runs:
        summary = run["summary"]
        seed = int(run["seed"])
        cap = int(run["max_questions"])
        for method, payload in summary["methods"].items():
            if method != "random":
                key = (method, cap)
                if seed != 42 or key in seen_deterministic:
                    continue
                seen_deterministic.add(key)
            metrics = payload["summary"]
            rows.append(
                {
                    "run_id": str(run["run_id"]),
                    "method": method,
                    "seed": seed,
                    "max_questions": cap,
                    "generation_budget": int(summary["generation_budget"]),
                    "frame_pool_size": int(summary["frame_pool_size"]),
                    "suite_size": int(metrics["suite_size"]),
                    "visited_frames": int(metrics["visited_frames"]),
                    "micro_l0": float(metrics["micro_l0"]),
                    "macro_l0": float(metrics["macro_l0"]),
                    "micro_l1": float(metrics["micro_l1"]),
                    "macro_l1": float(metrics["macro_l1"]),
                    "micro_l2": float(metrics["micro_l2"]),
                    "macro_l2": float(metrics["macro_l2"]),
                    "unique_l2_per_question": float(
                        metrics["unique_l2_per_question"]
                    ),
                    "auc_micro_l2": float(metrics["auc_micro_l2"]),
                    "auc_macro_l2": float(metrics["auc_macro_l2"]),
                    "switch_reason_counts": dict(
                        metrics["switch_reason_counts"]
                    ),
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            row["max_questions"],
            row["method"],
            row["seed"],
        ),
    )


def summarize_random(rows: Sequence[Mapping]) -> list:
    grouped = {}
    for row in rows:
        if row["method"] == "random":
            grouped.setdefault(int(row["max_questions"]), []).append(row)
    summaries = []
    for cap, cap_rows in sorted(grouped.items()):
        values = [float(row["micro_l2"]) for row in cap_rows]
        auc_values = [float(row["auc_micro_l2"]) for row in cap_rows]
        summaries.append(
            {
                "max_questions": cap,
                "seed_count": len(cap_rows),
                "seeds": [int(row["seed"]) for row in cap_rows],
                "micro_l2_mean": statistics.fmean(values),
                "micro_l2_std": statistics.pstdev(values),
                "micro_l2_min": min(values),
                "micro_l2_max": max(values),
                "auc_micro_l2_mean": statistics.fmean(auc_values),
                "auc_micro_l2_std": statistics.pstdev(auc_values),
                "auc_micro_l2_min": min(auc_values),
                "auc_micro_l2_max": max(auc_values),
            }
        )
    return summaries


def recommend_frame_cap(
    rows: Sequence[Mapping], *, negligible_threshold: float = 0.005
) -> dict:
    advtest = {
        int(row["max_questions"]): row
        for row in rows
        if row["method"] == "advtest"
    }
    missing = {50, 100} - set(advtest)
    if missing:
        raise ValueError(
            f"ADVTEST rows are required for frame caps: {sorted(missing)}"
        )
    micro_delta = float(advtest[100]["micro_l2"]) - float(
        advtest[50]["micro_l2"]
    )
    auc_delta = float(advtest[100]["auc_micro_l2"]) - float(
        advtest[50]["auc_micro_l2"]
    )
    recommended = (
        50
        if micro_delta < negligible_threshold
        and auc_delta < negligible_threshold
        else 100
    )
    return {
        "recommended_max_questions": recommended,
        "negligible_threshold": negligible_threshold,
        "micro_l2_delta": micro_delta,
        "auc_micro_l2_delta": auc_delta,
        "reason": (
            "cap100 gains are negligible"
            if recommended == 50
            else "cap100 reaches the material-gain threshold"
        ),
    }


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_structural_run(run_dir: Path) -> dict:
    manifest = _load_json(run_dir / "manifest.json")
    if manifest["status"] != "completed":
        raise ValueError(f"Run is not completed: {run_dir}")
    summary = _load_json(run_dir / "results" / "fixed_budget_summary.json")
    return {
        "run_id": manifest["run_id"],
        "seed": manifest["parameters"]["seed"],
        "max_questions": manifest["parameters"]["max_questions"],
        "manifest": manifest,
        "summary": summary,
    }


def count_jsonl(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def load_external_capacity(run_dir: Path) -> list:
    manifest = _load_json(run_dir / "manifest.json")
    if manifest["status"] != "completed":
        raise ValueError(f"Run is not completed: {run_dir}")
    results_dir = run_dir / "results"
    return [
        {
            "method": method,
            "requested_generation_budget": int(
                manifest["parameters"]["generation_budget"]
            ),
            "actual_questions": count_jsonl(
                results_dir / f"{method}_suite.jsonl"
            ),
            "run_id": manifest["run_id"],
        }
        for method in ("official_qa", "qatest")
    ]


def _jsonable_rows(rows: Sequence[Mapping]) -> list:
    return [dict(row) for row in rows]


def write_summary(
    output_dir: Path,
    rows: Sequence[Mapping],
    random_stats: Sequence[Mapping],
    decision: Mapping,
    external_capacity: Sequence[Mapping],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "structural_runs": _jsonable_rows(rows),
        "random_statistics": _jsonable_rows(random_stats),
        "frame_cap_decision": dict(decision),
        "external_capacity": _jsonable_rows(external_capacity),
    }
    (output_dir / "structural_sensitivity.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "structural_sensitivity.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=ROW_FIELDS)
        writer.writeheader()
        for row in rows:
            serialized = dict(row)
            serialized["switch_reason_counts"] = json.dumps(
                serialized["switch_reason_counts"],
                sort_keys=True,
            )
            writer.writerow(serialized)

    lines = [
        "# RQ1 Structural Sensitivity",
        "",
        "## Frame-Cap Decision",
        "",
        (
            f"- Recommended cap: {decision['recommended_max_questions']}"
            f"\n- Micro-L2 delta (100 - 50): {decision['micro_l2_delta']:.6f}"
            f"\n- AUC delta (100 - 50): {decision['auc_micro_l2_delta']:.6f}"
            f"\n- Rule: {decision['reason']}"
        ),
        "",
        "## External Generation Capacity",
        "",
        "| Method | Requested | Actual | Run |",
        "|---|---:|---:|---|",
    ]
    for row in external_capacity:
        lines.append(
            f"| {row['method']} | {row['requested_generation_budget']} | "
            f"{row['actual_questions']} | {row['run_id']} |"
        )
    lines.extend(
        [
            "",
            "## Random Stability",
            "",
            "| Cap | Seeds | Micro-L2 Mean | Std | Min | Max |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in random_stats:
        lines.append(
            f"| {row['max_questions']} | {row['seed_count']} | "
            f"{row['micro_l2_mean']:.6f} | {row['micro_l2_std']:.6f} | "
            f"{row['micro_l2_min']:.6f} | {row['micro_l2_max']:.6f} |"
        )
    (output_dir / "structural_sensitivity.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate recorded RQ1 structural sensitivity runs."
    )
    parser.add_argument(
        "--structural-run-dir",
        type=Path,
        action="append",
        required=True,
    )
    parser.add_argument("--external-run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    runs = [load_structural_run(path) for path in args.structural_run_dir]
    rows = build_sensitivity_rows(runs)
    random_stats = summarize_random(rows)
    decision = recommend_frame_cap(rows)
    external_capacity = load_external_capacity(args.external_run_dir)
    write_summary(
        args.output_dir,
        rows,
        random_stats,
        decision,
        external_capacity,
    )
    print(
        f"[sensitivity] cap={decision['recommended_max_questions']} "
        f"results={args.output_dir}"
    )


if __name__ == "__main__":
    main()
