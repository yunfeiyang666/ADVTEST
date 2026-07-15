import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

from data_ops import (
    family_name,
    file_sha256,
    iter_jsonl,
    read_json,
    row_scene_frame,
    row_source_id,
    write_json,
    write_jsonl,
)


STRUCTURAL_FAMILIES = (
    "l0",
    "l1",
    "converge",
    "direction_chain",
    "distance_chain",
    "viewpoint_transfer",
)


def load_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".jsonl":
        return list(iter_jsonl(path))
    value = read_json(path)
    if not isinstance(value, list):
        raise ValueError(f"Prediction file must contain a list: {path}")
    return value


def merge_predictions(args: argparse.Namespace) -> None:
    rows = []
    for path in args.input:
        rows.extend(
            row for row in load_rows(path) if prediction_family(row) != "mixed"
        )
    index_predictions(rows)
    write_jsonl(args.output, rows)
    family_counts = defaultdict(int)
    for row in rows:
        family_counts[prediction_family(row)] += 1
    manifest = {
        "schema_version": "rq3_merged_predictions_v1",
        "inputs": [str(path.resolve()) for path in args.input],
        "output": str(args.output.resolve()),
        "output_sha256": file_sha256(args.output),
        "rows": len(rows),
        "family_counts": dict(sorted(family_counts.items())),
        "mixed_rows_included": 0,
    }
    write_json(args.manifest, manifest)
    print(json.dumps(manifest, ensure_ascii=False))


def prediction_key(row: dict) -> tuple[str, str]:
    metadata = row.get("metadata") or {}
    scene_frame = str(metadata.get("scene_frame") or row_scene_frame(row))
    source_id = str(metadata.get("source_question_id") or row_source_id(row))
    return scene_frame, source_id


def prediction_family(row: dict) -> str:
    metadata = row.get("metadata") or {}
    if (
        str(row.get("question_source") or "").lower() == "nuscenes_qa"
        or str(metadata.get("dataset_name") or "").lower() == "official_qa"
    ):
        return "official_qa"
    value = str(metadata.get("family") or row.get("family") or family_name(row)).lower()
    if value.startswith("l0_"):
        return "l0"
    if value.startswith("l1_"):
        return "l1"
    return value


def prediction_correct(row: dict) -> bool:
    value = row.get("is_correct")
    if not isinstance(value, bool):
        raise ValueError(f"Prediction lacks boolean is_correct: {prediction_key(row)}")
    return value


def index_predictions(rows: list[dict]) -> dict[tuple[str, str], dict]:
    output = {}
    for row in rows:
        key = prediction_key(row)
        if key in output:
            raise ValueError(f"Duplicate prediction key: {key}")
        output[key] = row
    return output


def exact_mcnemar_p(base: list[bool], model: list[bool]) -> float:
    base_only = sum(left and not right for left, right in zip(base, model))
    model_only = sum(not left and right for left, right in zip(base, model))
    discordant = base_only + model_only
    if not discordant:
        return 1.0
    tail = min(base_only, model_only)
    probability = sum(
        math.comb(discordant, value) for value in range(tail + 1)
    ) / (2**discordant)
    return min(1.0, 2.0 * probability)


def bootstrap_improvement_ci(
    base: list[bool], model: list[bool], samples: int, seed: int
) -> tuple[float, float]:
    rng = random.Random(seed)
    count = len(base)
    improvements = []
    for _ in range(samples):
        indices = [rng.randrange(count) for _ in range(count)]
        value = sum(
            int(model[index]) - int(base[index]) for index in indices
        ) / count
        improvements.append(value)
    improvements.sort()
    low = improvements[int(0.025 * (samples - 1))]
    high = improvements[int(0.975 * (samples - 1))]
    return low, high


def paired_metrics(
    base_rows: list[dict],
    model_rows: list[dict],
    *,
    bootstrap_samples: int = 10000,
    seed: int = 20260715,
) -> dict[str, dict]:
    base_index = index_predictions(base_rows)
    model_index = index_predictions(model_rows)
    if set(base_index) != set(model_index):
        missing = len(set(base_index) - set(model_index))
        extra = len(set(model_index) - set(base_index))
        raise ValueError(f"Prediction keys differ: missing={missing}, extra={extra}")
    grouped: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    for key in sorted(base_index):
        base_row = base_index[key]
        model_row = model_index[key]
        family = prediction_family(base_row)
        if family == "mixed":
            continue
        if prediction_family(model_row) != family:
            raise ValueError(f"Family mismatch for {key}")
        grouped[family].append(
            (prediction_correct(base_row), prediction_correct(model_row))
        )
    metrics = {}
    for family, pairs in sorted(grouped.items()):
        base = [pair[0] for pair in pairs]
        model = [pair[1] for pair in pairs]
        count = len(pairs)
        base_wrong = sum(not value for value in base)
        base_correct = sum(base)
        repairs = sum(not left and right for left, right in pairs)
        regressions = sum(left and not right for left, right in pairs)
        improvement = (sum(model) - sum(base)) / count
        ci_low, ci_high = bootstrap_improvement_ci(
            base, model, bootstrap_samples, seed
        )
        metrics[family] = {
            "questions": count,
            "base_error_rate": 1.0 - sum(base) / count,
            "model_error_rate": 1.0 - sum(model) / count,
            "error_rate_reduction": improvement,
            "error_rate_reduction_ci95": [ci_low, ci_high],
            "base_wrong_repair_rate": repairs / base_wrong if base_wrong else 0.0,
            "base_correct_degradation_rate": (
                regressions / base_correct if base_correct else 0.0
            ),
            "repaired_questions": repairs,
            "degraded_questions": regressions,
            "mcnemar_p": exact_mcnemar_p(base, model),
        }
    return metrics


def holm_adjust(values: list[tuple[str, float]]) -> dict[str, float]:
    ordered = sorted(values, key=lambda item: item[1])
    total = len(ordered)
    adjusted = {}
    running = 0.0
    for rank, (key, value) in enumerate(ordered):
        running = max(running, min(1.0, (total - rank) * value))
        adjusted[key] = running
    return adjusted


def select_checkpoint(args: argparse.Namespace) -> None:
    base_rows = load_rows(args.base)
    base_keys = set(index_predictions(base_rows))
    base_official = [
        prediction_correct(row)
        for row in base_rows
        if prediction_family(row) == "official_qa"
    ]
    if not base_official:
        raise ValueError("Base validation results contain no official_qa rows")
    base_official_accuracy = sum(base_official) / len(base_official)
    candidates = []
    for name, path in args.candidate:
        rows = load_rows(path)
        if set(index_predictions(rows)) != base_keys:
            raise ValueError(f"Candidate {name} does not match the fixed validation questions")
        grouped = defaultdict(list)
        for row in rows:
            grouped[prediction_family(row)].append(prediction_correct(row))
        missing = [family for family in STRUCTURAL_FAMILIES if not grouped[family]]
        if missing or not grouped["official_qa"]:
            raise ValueError(f"Candidate {name} misses validation families: {missing}")
        official_accuracy = sum(grouped["official_qa"]) / len(grouped["official_qa"])
        macro_accuracy = sum(
            sum(grouped[family]) / len(grouped[family])
            for family in STRUCTURAL_FAMILIES
        ) / len(STRUCTURAL_FAMILIES)
        candidates.append(
            {
                "name": name,
                "path": str(path.resolve()),
                "official_accuracy": official_accuracy,
                "official_drop": base_official_accuracy - official_accuracy,
                "structural_macro_accuracy": macro_accuracy,
                "passes_official_guard": official_accuracy >= base_official_accuracy - 0.02,
            }
        )
    eligible = [row for row in candidates if row["passes_official_guard"]]
    selected = max(eligible, key=lambda row: row["structural_macro_accuracy"]) if eligible else None
    result = {
        "schema_version": "rq3_checkpoint_selection_v1",
        "base_official_accuracy": base_official_accuracy,
        "official_accuracy_floor": base_official_accuracy - 0.02,
        "candidates": candidates,
        "selected": selected,
        "status": "selected" if selected else "failed_official_guard",
        "retry_learning_rate": None if selected else 5e-5,
    }
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False))


def compare_results(args: argparse.Namespace) -> None:
    base_rows = load_rows(args.base)
    all_metrics = {}
    tests = []
    for name, path in args.model:
        metrics = paired_metrics(
            base_rows,
            load_rows(path),
            bootstrap_samples=args.bootstrap_samples,
            seed=args.seed,
        )
        all_metrics[name] = metrics
        tests.extend((f"{name}:{family}", row["mcnemar_p"]) for family, row in metrics.items())
    adjusted = holm_adjust(tests)
    for name, metrics in all_metrics.items():
        for family, row in metrics.items():
            row["mcnemar_p_holm"] = adjusted[f"{name}:{family}"]
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "rq3_paired_comparison_v1",
        "base": str(args.base.resolve()),
        "bootstrap_samples": args.bootstrap_samples,
        "models": all_metrics,
    }
    write_json(output_dir / "comparison.json", payload)
    with (output_dir / "comparison.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "model",
                "family",
                "questions",
                "base_error_rate",
                "model_error_rate",
                "error_rate_reduction",
                "repair_rate",
                "degradation_rate",
                "mcnemar_p_holm",
            ]
        )
        for name, metrics in all_metrics.items():
            for family, row in metrics.items():
                writer.writerow(
                    [
                        name,
                        family,
                        row["questions"],
                        row["base_error_rate"],
                        row["model_error_rate"],
                        row["error_rate_reduction"],
                        row["base_wrong_repair_rate"],
                        row["base_correct_degradation_rate"],
                        row["mcnemar_p_holm"],
                    ]
                )
    lines = [
        "# RQ3 paired evaluation",
        "",
        "| Model | Family | Q | Base error | Model error | Reduction | Repair | Degradation | Holm p |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in all_metrics.items():
        for family, row in metrics.items():
            lines.append(
                f"| {name} | {family} | {row['questions']} | "
                f"{row['base_error_rate']:.1%} | {row['model_error_rate']:.1%} | "
                f"{row['error_rate_reduction']:+.1%} | "
                f"{row['base_wrong_repair_rate']:.1%} | "
                f"{row['base_correct_degradation_rate']:.1%} | "
                f"{row['mcnemar_p_holm']:.4g} |"
            )
    (output_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _t_critical_95(sample_count: int) -> float:
    return {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776}.get(sample_count, 1.96)


def aggregate_seeds(args: argparse.Namespace) -> None:
    base_rows = load_rows(args.base)
    grouped = defaultdict(list)
    for method_seed, path in args.run:
        method, raw_seed = method_seed.rsplit(":", 1)
        metrics = paired_metrics(base_rows, load_rows(path), bootstrap_samples=1000, seed=int(raw_seed))
        for family, row in metrics.items():
            grouped[(method, family)].append((int(raw_seed), row))
    summary = {}
    for (method, family), values in sorted(grouped.items()):
        error_rates = [row["model_error_rate"] for _, row in values]
        reductions = [row["error_rate_reduction"] for _, row in values]
        count = len(values)
        if count < 2:
            std = 0.0
            half_width = 0.0
        else:
            mean = sum(error_rates) / count
            std = math.sqrt(sum((value - mean) ** 2 for value in error_rates) / (count - 1))
            half_width = _t_critical_95(count) * std / math.sqrt(count)
        summary.setdefault(method, {})[family] = {
            "seeds": [seed for seed, _ in values],
            "runs": count,
            "error_rate_mean": sum(error_rates) / count,
            "error_rate_std": std,
            "error_rate_ci95": [
                sum(error_rates) / count - half_width,
                sum(error_rates) / count + half_width,
            ],
            "error_rate_reduction_mean": sum(reductions) / count,
        }
    write_json(
        args.output,
        {"schema_version": "rq3_seed_aggregate_v1", "methods": summary},
    )


def evaluate_success(summary: dict) -> dict:
    methods = summary.get("methods") or {}
    required = ("advtest_10k", "random_10k", "official_qa_10k")
    missing = [method for method in required if method not in methods]
    if missing:
        raise ValueError(f"Seed aggregate is missing methods: {missing}")
    macro_reductions = {}
    seed_checks = {}
    for method in required:
        rows = methods[method]
        missing_families = [
            family for family in STRUCTURAL_FAMILIES if family not in rows
        ]
        if missing_families or "official_qa" not in rows:
            raise ValueError(
                f"Method {method} misses result families: {missing_families}"
            )
        macro_reductions[method] = sum(
            rows[family]["error_rate_reduction_mean"]
            for family in STRUCTURAL_FAMILIES
        ) / len(STRUCTURAL_FAMILIES)
        seed_checks[method] = sorted(rows[STRUCTURAL_FAMILIES[0]]["seeds"])
    best_baseline = max(
        macro_reductions["random_10k"],
        macro_reductions["official_qa_10k"],
    )
    official_reduction = methods["advtest_10k"]["official_qa"][
        "error_rate_reduction_mean"
    ]
    checks = {
        "advtest_reduction_at_least_5pp": macro_reductions["advtest_10k"] >= 0.05,
        "advtest_beats_best_baseline_by_3pp": (
            macro_reductions["advtest_10k"] - best_baseline >= 0.03
        ),
        "official_accuracy_drop_at_most_2pp": official_reduction >= -0.02,
        "all_main_methods_have_seeds_42_43_44": all(
            seeds == [42, 43, 44] for seeds in seed_checks.values()
        ),
    }
    return {
        "schema_version": "rq3_success_judgement_v1",
        "passed": all(checks.values()),
        "checks": checks,
        "structural_macro_error_reduction": macro_reductions,
        "advtest_margin_over_best_baseline": (
            macro_reductions["advtest_10k"] - best_baseline
        ),
        "advtest_official_accuracy_change": official_reduction,
        "seeds": seed_checks,
    }


def judge_success(args: argparse.Namespace) -> None:
    result = evaluate_success(read_json(args.aggregate))
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False))


def parse_named_path(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Expected NAME=PATH")
    name, path = value.split("=", 1)
    return name, Path(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze paired RQ3 predictions.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    merge = subparsers.add_parser("merge-predictions")
    merge.add_argument("--input", action="append", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--manifest", type=Path, required=True)
    merge.set_defaults(func=merge_predictions)

    select = subparsers.add_parser("select-checkpoint")
    select.add_argument("--base", type=Path, required=True)
    select.add_argument("--candidate", action="append", type=parse_named_path, required=True)
    select.add_argument("--output", type=Path, required=True)
    select.set_defaults(func=select_checkpoint)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--base", type=Path, required=True)
    compare.add_argument("--model", action="append", type=parse_named_path, required=True)
    compare.add_argument("--output-dir", type=Path, required=True)
    compare.add_argument("--bootstrap-samples", type=int, default=10000)
    compare.add_argument("--seed", type=int, default=20260715)
    compare.set_defaults(func=compare_results)

    aggregate = subparsers.add_parser("aggregate-seeds")
    aggregate.add_argument("--base", type=Path, required=True)
    aggregate.add_argument("--run", action="append", type=parse_named_path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    aggregate.set_defaults(func=aggregate_seeds)

    judge = subparsers.add_parser("judge-success")
    judge.add_argument("--aggregate", type=Path, required=True)
    judge.add_argument("--output", type=Path, required=True)
    judge.set_defaults(func=judge_success)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
