import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping, Sequence


STRUCTURAL_METHODS = {"advtest", "random"}
EXTERNAL_METHODS = {"official_qa", "qatest_adapted", "qatest"}


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _footprint(record: Mapping, level: str) -> set[str]:
    footprint = record.get("coverage_footprint") or {}
    values = footprint.get(level) or record.get(f"coverage_{level}") or []
    return {str(value) for value in values}


def _frame_qualified_footprint(record: Mapping, level: str) -> set[str]:
    frame = str(record.get("scene_frame") or "unknown")
    return {f"{frame}::{item}" for item in _footprint(record, level)}


def _answer_type(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def select_prefix(records: Sequence[Mapping], call_budget: int) -> list[dict]:
    prefix = []
    calls = 0
    for record in records:
        cost = record.get("vlm_call_cost", 1)
        if not isinstance(cost, int) or isinstance(cost, bool) or cost < 1:
            raise ValueError(f"Invalid vlm_call_cost: {cost!r}")
        if calls + cost > call_budget:
            raise ValueError(
                f"Cannot consume exact budget {call_budget}; next cost is {cost}"
            )
        prefix.append(dict(record))
        calls += cost
        if calls == call_budget:
            return prefix
    raise ValueError(f"Suite only provides {calls} calls; {call_budget} required")


def load_structural_denominators(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    denominators = {}
    for method in STRUCTURAL_METHODS:
        summary = payload.get("methods", {}).get(method, {}).get("summary", {})
        denominators[method] = {
            "total_l0": int(summary.get("total_l0") or 0),
            "total_l1": int(summary.get("total_l1") or 0),
            "total_l2": int(summary.get("total_l2") or 0),
        }
    return denominators


def summarize_suite(
    method: str,
    records: Sequence[Mapping],
    denominators: Mapping[str, int] | None,
    *,
    call_budget: int,
) -> dict:
    prefix = select_prefix(records, call_budget)
    frames = Counter(str(row.get("scene_frame") or "unknown") for row in prefix)
    families = Counter(
        str(
            row.get("l2_family")
            or row.get("template_id")
            or row.get("template_type")
            or "unknown"
        )
        for row in prefix
    )
    question_sources = Counter(
        str(row.get("question_source") or "unknown") for row in prefix
    )
    answer_types = Counter(_answer_type(row.get("answer")) for row in prefix)
    calls = sum(int(row.get("vlm_call_cost", 1)) for row in prefix)
    coverage_present = any(_footprint(row, "l2") for row in prefix)

    result = {
        "method": method,
        "questions": len(prefix),
        "vlm_calls": calls,
        "unique_frames": len(frames),
        "maximum_questions_per_frame": max(frames.values()) if frames else 0,
        "top_frames": frames.most_common(10),
        "answer_types": dict(sorted(answer_types.items())),
        "top_families": dict(families.most_common(10)),
        "question_sources": dict(sorted(question_sources.items())),
    }

    if method in STRUCTURAL_METHODS and coverage_present:
        totals = denominators or {}
        covered = {
            level: set().union(
                *[_frame_qualified_footprint(row, level) for row in prefix]
            )
            for level in ("l0", "l1", "l2")
        }
        result.update(
            {
                "coverage_comparable": True,
                "coverage_status": "available",
                "gt_granularity": "instance_or_relation",
            }
        )
        for level in ("l0", "l1", "l2"):
            total = int(totals.get(f"total_{level}") or 0)
            count = len(covered[level])
            result[f"covered_{level}"] = count
            result[f"total_{level}"] = total
            result[f"micro_{level}"] = count / total if total else 0.0
        result["unique_l2_per_question"] = (
            result["covered_l2"] / len(prefix) if prefix else 0.0
        )
    elif method in EXTERNAL_METHODS:
        result.update(
            {
                "coverage_comparable": False,
                "coverage_status": "not_available_by_design",
                "gt_granularity": "category_level_official",
                "coverage_boundary_reason": (
                    "NuScenes-QA-derived suites intentionally do not carry "
                    "ADVTEST-private coverage footprints."
                ),
            }
        )
    else:
        result.update(
            {
                "coverage_comparable": False,
                "coverage_status": "missing",
                "gt_granularity": "unknown",
            }
        )
    return result


def summarize_inputs(
    suites: Mapping[str, Sequence[Mapping]],
    denominators: Mapping[str, Mapping[str, int]],
    *,
    call_budget: int,
) -> dict:
    methods = {
        method: summarize_suite(
            method,
            records,
            denominators.get(method),
            call_budget=call_budget,
        )
        for method, records in suites.items()
    }
    payload = {
        "schema_version": 1,
        "call_budget_per_method": call_budget,
        "budget_unit": "actual_vlm_calls",
        "selection_policy": "frozen_suite_prefix",
        "methods": methods,
        "comparison_boundaries": [
            "ADVTEST versus Random is the structurally comparable internal ablation.",
            "Official QA and QATest-adapted are cross-paradigm references; they do not expose structural L2 coverage.",
            "Cross-paradigm failure rates must report GT granularity and frame distribution.",
        ],
    }
    if "advtest" in methods and "random" in methods:
        advtest = methods["advtest"]
        random = methods["random"]
        payload["internal_ablation"] = {
            "advtest_minus_random_covered_l2": (
                int(advtest.get("covered_l2", 0))
                - int(random.get("covered_l2", 0))
            ),
            "advtest_relative_l2_coverage_gain": (
                (
                    float(advtest.get("micro_l2", 0.0))
                    - float(random.get("micro_l2", 0.0))
                )
                / float(random.get("micro_l2", 0.0))
                if float(random.get("micro_l2", 0.0))
                else None
            ),
            "advtest_minus_random_unique_l2_per_question": (
                float(advtest.get("unique_l2_per_question", 0.0))
                - float(random.get("unique_l2_per_question", 0.0))
            ),
        }
    return payload


def parse_suite_args(values: Sequence[str]) -> dict[str, Path]:
    suites = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Suite must use METHOD=PATH syntax: {value}")
        method, path = value.split("=", 1)
        suites[method] = Path(path)
    return suites


def write_markdown(payload: Mapping, path: Path) -> None:
    lines = [
        "# RQ1 Call-1000 Input Audit",
        "",
        f"- Budget: {payload['call_budget_per_method']} actual VLM calls per method",
        f"- Selection: {payload['selection_policy']}",
        "",
        "## Methods",
        "",
        "| Method | Calls | Frames | Max/frame | GT granularity | Coverage comparable | Covered L2 | Micro L2 | L2/Q |",
        "|---|---:|---:|---:|---|---|---:|---:|---:|",
    ]
    for method, row in payload["methods"].items():
        lines.append(
            f"| `{method}` | {row['vlm_calls']} | {row['unique_frames']} | "
            f"{row['maximum_questions_per_frame']} | {row['gt_granularity']} | "
            f"{row['coverage_comparable']} | {row.get('covered_l2', 'N/A')} | "
            f"{float(row.get('micro_l2', 0.0)):.6f} | "
            f"{float(row.get('unique_l2_per_question', 0.0)):.3f} |"
        )
    if payload.get("internal_ablation"):
        ablation = payload["internal_ablation"]
        lines.extend(
            [
                "",
                "## Internal Ablation",
                "",
                (
                    f"- ADVTEST minus Random covered L2: "
                    f"{ablation['advtest_minus_random_covered_l2']}"
                ),
                (
                    f"- Relative micro-L2 gain: "
                    f"{ablation['advtest_relative_l2_coverage_gain']:.2%}"
                    if ablation["advtest_relative_l2_coverage_gain"] is not None
                    else "- Relative micro-L2 gain: N/A"
                ),
                (
                    f"- L2/Q gain: "
                    f"{ablation['advtest_minus_random_unique_l2_per_question']:.3f}"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Comparison Boundaries",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload["comparison_boundaries"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize fixed-call-budget RQ1 suite inputs."
    )
    parser.add_argument("--suite", action="append", required=True)
    parser.add_argument("--call-budget", type=int, required=True)
    parser.add_argument("--structural-summary", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    suite_paths = parse_suite_args(args.suite)
    suites = {
        method: list(iter_jsonl(path)) for method, path in suite_paths.items()
    }
    denominators = load_structural_denominators(args.structural_summary)
    payload = summarize_inputs(
        suites,
        denominators,
        call_budget=args.call_budget,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_markdown(payload, args.output_md)
    print(
        f"[call-budget-inputs] methods={len(payload['methods'])} "
        f"output={args.output_json}"
    )


if __name__ == "__main__":
    main()
