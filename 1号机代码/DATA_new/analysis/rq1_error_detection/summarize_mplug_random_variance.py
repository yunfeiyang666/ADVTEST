import argparse
import json
import statistics
from pathlib import Path
from typing import Mapping, Sequence

from rescore_suite_results import rescore_raw


def summarize_results(
    advtest: Mapping,
    random_results: Sequence[Mapping],
) -> dict:
    if not random_results:
        raise ValueError("At least one Random seed result is required")

    call_budget = int(advtest["vlm_calls"])
    if any(int(row["vlm_calls"]) != call_budget for row in random_results):
        raise ValueError("All methods must use the same VLM call budget")

    seeds = [int(row["seed"]) for row in random_results]
    if len(seeds) != len(set(seeds)):
        raise ValueError("Random seed values must be unique")

    ordered = sorted(random_results, key=lambda row: int(row["seed"]))
    unique_values = [int(row["unique_failures"]) for row in ordered]
    wrong_values = [int(row["wrong"]) for row in ordered]
    failed_l2_values = [int(row["failed_unique_l2"]) for row in ordered]
    unique_mean = statistics.fmean(unique_values)
    failed_l2_mean = statistics.fmean(failed_l2_values)
    adv_unique = int(advtest["unique_failures"])
    adv_failed_l2 = int(advtest["failed_unique_l2"])
    absolute_gain = adv_unique - unique_mean
    failed_l2_gain = adv_failed_l2 - failed_l2_mean

    return {
        "call_budget": call_budget,
        "advtest": dict(advtest),
        "random_runs": [dict(row) for row in ordered],
        "random": {
            "seed_count": len(ordered),
            "seeds": [int(row["seed"]) for row in ordered],
            "wrong_mean": statistics.fmean(wrong_values),
            "wrong_population_std": statistics.pstdev(wrong_values),
            "wrong_min": min(wrong_values),
            "wrong_max": max(wrong_values),
            "unique_failures_mean": unique_mean,
            "unique_failures_population_std": statistics.pstdev(unique_values),
            "unique_failures_min": min(unique_values),
            "unique_failures_max": max(unique_values),
            "failed_unique_l2_mean": failed_l2_mean,
            "failed_unique_l2_population_std": statistics.pstdev(
                failed_l2_values
            ),
            "failed_unique_l2_min": min(failed_l2_values),
            "failed_unique_l2_max": max(failed_l2_values),
        },
        "advtest_vs_random": {
            "absolute_gain_over_mean": absolute_gain,
            "relative_gain_over_mean": (
                absolute_gain / unique_mean if unique_mean else None
            ),
            "seeds_advtest_exceeds": sum(
                adv_unique > value for value in unique_values
            ),
            "failed_unique_l2_gain_over_mean": failed_l2_gain,
            "failed_unique_l2_relative_gain_over_mean": (
                failed_l2_gain / failed_l2_mean if failed_l2_mean else None
            ),
            "seeds_advtest_exceeds_failed_unique_l2": sum(
                adv_failed_l2 > value for value in failed_l2_values
            ),
            "seed_count": len(unique_values),
        },
    }


def parse_seeded_paths(values: Sequence[str]) -> list[tuple[int, Path]]:
    parsed = []
    for value in values:
        if "=" not in value:
            raise ValueError(f"Random input must use SEED=PATH syntax: {value}")
        seed_text, path_text = value.split("=", 1)
        parsed.append((int(seed_text), Path(path_text)))
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize mPLUG Random-seed variance from frozen outputs."
    )
    parser.add_argument("--advtest-raw", type=Path, required=True)
    parser.add_argument("--random-raw", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    advtest = rescore_raw(args.advtest_raw)
    random_results = []
    for seed, path in parse_seeded_paths(args.random_raw):
        result = rescore_raw(path)
        result["seed"] = seed
        random_results.append(result)

    payload = {
        "scoring": "token_boundary_v2",
        **summarize_results(advtest, random_results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"[random-variance] seeds={payload['random']['seed_count']} "
        f"output={args.output}"
    )


if __name__ == "__main__":
    main()
