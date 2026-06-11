import argparse
import csv
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0



WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

import rq1_selectors


DEFAULT_FRAME_CACHE = (
    WORKSPACE_ROOT
    / "1号机代码"
    / "DATA_new"
    / "analysis"
    / "data_cache"
    / "rq1_100_eval_frames.json"
)
DEFAULT_OUTPUTS_ROOT = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "outputs"
DEFAULT_RESULT_DIR = (
    WORKSPACE_ROOT
    / "1号机代码"
    / "DATA_new"
    / "analysis"
    / "fixed_budget_results"
)

METHODS = ("advtest", "random", "qatest", "qaasker")


@dataclass(frozen=True)
class SwitchPolicy:
    min_questions: int = 20
    max_questions: int = 100
    plateau_window: int = 10
    gain_window: int = 20
    relative_gain_threshold: float = 0.25


@dataclass
class FrameCoverage:
    total_l0: int
    total_l1: int
    total_l2: int
    covered_l0: set = field(default_factory=set)
    covered_l1: set = field(default_factory=set)
    covered_l2: set = field(default_factory=set)


@dataclass(frozen=True)
class FrameInput:
    scene_frame: str
    questions: Sequence[dict]
    total_l0: int
    total_l1: int
    total_l2: int


def choose_switch_reason(
    gains: Sequence[int],
    covered_l2: int,
    total_l2: int,
    candidates_exhausted: bool,
    policy: SwitchPolicy,
) -> Optional[str]:
    count = len(gains)
    if total_l2 > 0 and covered_l2 >= total_l2:
        return "full_coverage"
    if count >= policy.max_questions:
        return "frame_cap"
    if candidates_exhausted:
        return "candidate_exhausted"
    if count < policy.min_questions:
        return None
    if (
        count >= policy.plateau_window
        and all(gain == 0 for gain in gains[-policy.plateau_window :])
    ):
        return "plateau"
    if count >= policy.gain_window * 2:
        initial_gain = mean(gains[: policy.gain_window])
        recent_gain = mean(gains[-policy.gain_window :])
        if (
            initial_gain > 0
            and recent_gain < initial_gain * policy.relative_gain_threshold
        ):
            return "relative_gain_drop"
    return None


def compute_aggregate_metrics(
    frames: Dict[str, FrameCoverage], question_count: int
) -> dict:
    frame_count = len(frames)
    metrics = {}
    for level in ("l0", "l1", "l2"):
        total = 0
        covered = 0
        macro_sum = 0.0
        for frame in frames.values():
            frame_total = getattr(frame, f"total_{level}")
            frame_covered = len(getattr(frame, f"covered_{level}"))
            total += frame_total
            covered += frame_covered
            macro_sum += frame_covered / frame_total if frame_total else 1.0
        metrics[f"micro_{level}"] = covered / total if total else 1.0
        metrics[f"macro_{level}"] = macro_sum / frame_count if frame_count else 0.0
        metrics[f"covered_{level}"] = covered
        metrics[f"total_{level}"] = total
    metrics["unique_l2_per_question"] = (
        metrics["covered_l2"] / question_count if question_count else 0.0
    )
    return metrics


def _question_file(frame_dir: Path, scene_frame: str) -> Path:
    qa_dir = frame_dir / "generation" / "qa"
    candidates = [
        qa_dir / f"{scene_frame}_generated.jsonl",
        qa_dir / f"{scene_frame}_all.jsonl",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"No generated question JSONL found for {scene_frame}")


def _load_questions(
    frame_dir: Path, scene_frame: str, load_limit: Optional[int] = None
) -> List[dict]:
    path = _question_file(frame_dir, scene_frame)
    questions = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            questions.append(json.loads(line))
            if load_limit is not None and len(questions) >= load_limit:
                break
    return questions


def _load_frame(
    scene_frame: str, outputs_root: Path, question_load_limit: Optional[int] = None
) -> FrameInput:
    frame_dir = outputs_root / scene_frame
    summary_path = frame_dir / "reports" / f"{scene_frame}_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing frame summary: {summary_path}")
    with summary_path.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)
    coverage = summary.get("coverage") or {}
    total_l0 = int(coverage.get("l0") or 0)
    total_l1 = int(coverage.get("l1") or 0)
    total_l2 = int(summary.get("total_gap_count") or coverage.get("l2") or 0)
    return FrameInput(
        scene_frame=scene_frame,
        questions=_load_questions(frame_dir, scene_frame, question_load_limit),
        total_l0=total_l0,
        total_l1=total_l1,
        total_l2=total_l2,
    )


def load_frame_pool(
    frame_cache: Path,
    outputs_root: Path,
    frame_pool_size: int,
    question_load_limit: Optional[int] = None,
) -> List[FrameInput]:
    with frame_cache.open("r", encoding="utf-8") as handle:
        cached_frames = json.load(handle)
    names = [item["scene_frame"] for item in cached_frames[:frame_pool_size]]
    frames = []
    for index, name in enumerate(names, start=1):
        print(f"[fixed-budget] Loading frame {index}/{len(names)}: {name}", flush=True)
        frames.append(_load_frame(name, outputs_root, question_load_limit))
    return frames


def build_method_stream(
    method: str,
    questions: Sequence[dict],
    max_questions: int,
    seed: int,
) -> List[dict]:
    if method == "advtest":
        return [dict(question) for question in questions[:max_questions]]
    if method == "random":
        stream = [dict(question) for question in questions]
        random.Random(seed).shuffle(stream)
        return stream[:max_questions]
    if method == "qatest":
        return rq1_selectors.select_qatest(
            list(questions), min(max_questions, len(questions)), seed=seed
        )
    if method == "qaasker":
        return rq1_selectors.select_recursive_asking(
            list(questions), min(max_questions, len(questions)), seed=seed
        )
    raise ValueError(f"Unknown method: {method}")


def _footprint(question: dict, level: str) -> set:
    footprint = question.get("coverage_footprint") or {}
    values = footprint.get(level) or question.get(f"coverage_{level}") or []
    return {str(value) for value in values}


def _apply_question(frame: FrameCoverage, question: dict) -> dict:
    deltas = {}
    for level in ("l0", "l1", "l2"):
        covered = getattr(frame, f"covered_{level}")
        new_items = _footprint(question, level) - covered
        covered.update(new_items)
        deltas[f"delta_{level}"] = len(new_items)
    return deltas


def _metric_snapshot(
    frame_states: Dict[str, FrameCoverage],
    question_count: int,
    visited_frames: int,
) -> dict:
    metrics = compute_aggregate_metrics(frame_states, question_count)
    metrics["question_count"] = question_count
    metrics["visited_frames"] = visited_frames
    return metrics


def run_method(
    method: str,
    frames: Sequence[FrameInput],
    budget: int,
    seed: int,
    policy: SwitchPolicy,
) -> dict:
    frame_states = {
        frame.scene_frame: FrameCoverage(
            total_l0=frame.total_l0,
            total_l1=frame.total_l1,
            total_l2=frame.total_l2,
        )
        for frame in frames
    }
    suite = []
    curve = [_metric_snapshot(frame_states, 0, 0)]
    frame_runs = []
    switch_counts = Counter()

    for frame_index, frame_input in enumerate(frames):
        if len(suite) >= budget:
            break
        frame_seed = seed + frame_index * 1009
        stream = build_method_stream(
            method,
            frame_input.questions,
            min(policy.max_questions, budget - len(suite)),
            frame_seed,
        )
        gains = []
        reason = "candidate_exhausted"
        frame_state = frame_states[frame_input.scene_frame]

        for local_index, question in enumerate(stream, start=1):
            deltas = _apply_question(frame_state, question)
            gains.append(deltas["delta_l2"])
            record = dict(question)
            record.update(
                {
                    "experiment_method": method,
                    "global_budget_index": len(suite) + 1,
                    "scene_frame": frame_input.scene_frame,
                    "frame_budget_index": local_index,
                    **deltas,
                }
            )
            suite.append(record)
            curve.append(
                _metric_snapshot(frame_states, len(suite), frame_index + 1)
            )

            exhausted = local_index == len(stream)
            reason = choose_switch_reason(
                gains,
                covered_l2=len(frame_state.covered_l2),
                total_l2=frame_state.total_l2,
                candidates_exhausted=exhausted,
                policy=policy,
            )
            if reason or len(suite) >= budget:
                if len(suite) >= budget:
                    reason = "global_budget"
                break

        switch_counts[reason] += 1
        frame_runs.append(
            {
                "scene_frame": frame_input.scene_frame,
                "questions": len(gains),
                "covered_l2": len(frame_state.covered_l2),
                "total_l2": frame_state.total_l2,
                "coverage_l2": (
                    len(frame_state.covered_l2) / frame_state.total_l2
                    if frame_state.total_l2
                    else 1.0
                ),
                "switch_reason": reason,
                "initial_gain_mean": mean(gains[: policy.gain_window])
                if gains
                else 0.0,
                "final_gain_mean": mean(gains[-policy.gain_window :])
                if gains
                else 0.0,
            }
        )

    if curve:
        while len(curve) <= budget:
            padded = dict(curve[-1])
            padded["question_count"] = len(curve)
            curve.append(padded)

    final_metrics = compute_aggregate_metrics(frame_states, len(suite))
    final_metrics["suite_size"] = len(suite)
    final_metrics["visited_frames"] = len(frame_runs)
    final_metrics["switch_reason_counts"] = dict(switch_counts)
    final_metrics["auc_micro_l2"] = _normalized_auc(
        [point["micro_l2"] for point in curve[: budget + 1]], budget
    )
    final_metrics["auc_macro_l2"] = _normalized_auc(
        [point["macro_l2"] for point in curve[: budget + 1]], budget
    )
    return {
        "method": method,
        "summary": final_metrics,
        "frame_runs": frame_runs,
        "curve": curve[: budget + 1],
        "suite": suite,
    }


def _normalized_auc(values: Sequence[float], budget: int) -> float:
    if budget <= 0 or len(values) < 2:
        return 0.0
    area = sum((left + right) / 2 for left, right in zip(values, values[1:]))
    if len(values) - 1 < budget:
        area += values[-1] * (budget - (len(values) - 1))
    return area / budget


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_results(
    output_dir: Path,
    frame_names: Sequence[str],
    budget: int,
    policy: SwitchPolicy,
    method_results: Sequence[dict],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "budget": budget,
        "frame_pool": list(frame_names),
        "frame_pool_size": len(frame_names),
        "policy": {
            "min_questions": policy.min_questions,
            "max_questions": policy.max_questions,
            "plateau_window": policy.plateau_window,
            "gain_window": policy.gain_window,
            "relative_gain_threshold": policy.relative_gain_threshold,
        },
        "methods": {
            result["method"]: {
                "summary": result["summary"],
                "frame_runs": result["frame_runs"],
            }
            for result in method_results
        },
    }
    with (output_dir / "fixed_budget_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)

    checkpoints = set(range(0, budget + 1, 100))
    with (output_dir / "fixed_budget_curves.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        fieldnames = [
            "method",
            "question_count",
            "visited_frames",
            "micro_l0",
            "micro_l1",
            "micro_l2",
            "macro_l0",
            "macro_l1",
            "macro_l2",
            "unique_l2_per_question",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in method_results:
            for point in result["curve"]:
                if point["question_count"] in checkpoints:
                    writer.writerow(
                        {"method": result["method"], **{
                            key: point[key] for key in fieldnames if key != "method"
                        }}
                    )

    for result in method_results:
        _write_jsonl(
            output_dir / f"{result['method']}_suite.jsonl", result["suite"]
        )

    report_lines = [
        "# Fixed-Budget RQ1 Trial",
        "",
        f"- Shared frame pool: {len(frame_names)} frames",
        f"- Question budget: {budget} per method",
        f"- Per-frame range: {policy.min_questions}-{policy.max_questions}",
        "",
        "| Method | Suite | Frames | Micro L2 | Macro L2 | L2/Q | AUC Micro L2 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in method_results:
        metrics = result["summary"]
        report_lines.append(
            "| {method} | {suite_size} | {visited_frames} | {micro_l2:.4f} | "
            "{macro_l2:.4f} | {unique_l2_per_question:.4f} | "
            "{auc_micro_l2:.4f} |".format(method=result["method"], **metrics)
        )
    report_lines.extend(["", "## Switch Reasons", ""])
    for result in method_results:
        report_lines.append(
            f"- **{result['method']}**: "
            f"{json.dumps(result['summary']['switch_reason_counts'], ensure_ascii=False)}"
        )
    (output_dir / "fixed_budget_report.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fixed-question-budget RQ1 trial")
    parser.add_argument("--budget", type=int, default=1000)
    parser.add_argument("--frame-pool-size", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-questions", type=int, default=100)
    parser.add_argument(
        "--question-load-limit",
        type=int,
        default=None,
        help="Optional per-frame candidate load cap for fast sensitivity runs.",
    )
    parser.add_argument("--frame-cache", type=Path, default=DEFAULT_FRAME_CACHE)
    parser.add_argument("--outputs-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULT_DIR)
    args = parser.parse_args()

    policy = SwitchPolicy(max_questions=args.max_questions)
    frames = load_frame_pool(
        args.frame_cache,
        args.outputs_root,
        args.frame_pool_size,
        question_load_limit=args.question_load_limit,
    )
    results = []
    for method in METHODS:
        print(f"[fixed-budget] Running {method}...", flush=True)
        result = run_method(method, frames, args.budget, args.seed, policy)
        results.append(result)
        print(
            f"  suite={result['summary']['suite_size']} "
            f"frames={result['summary']['visited_frames']} "
            f"micro_l2={result['summary']['micro_l2']:.4f}",
            flush=True,
        )
    write_results(
        args.output_dir,
        [frame.scene_frame for frame in frames],
        args.budget,
        policy,
        results,
    )
    print(f"[fixed-budget] Results written to {args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
