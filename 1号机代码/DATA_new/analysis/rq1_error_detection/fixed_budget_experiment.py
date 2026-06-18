import argparse
import csv
import heapq
import json
import random
import sys
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0



WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from experiment_protocol import STRUCTURAL_LAYER, annotate_provenance


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

METHODS = (
    "advtest",
    "random",
    "template_balanced",
    "object_balanced",
    "greedy_l0",
    "greedy_l1",
)

COVERAGE_FEEDBACK_METHODS = frozenset({"advtest", "greedy_l0", "greedy_l1"})


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


def build_frame_question_counts(
    frame_names: Sequence[str], generation_budget: int, seed: int
) -> dict:
    if generation_budget < 0:
        raise ValueError("generation_budget must be non-negative")
    names = list(frame_names)
    if generation_budget and not names:
        raise ValueError("Cannot assign questions without frames")
    rng = random.Random(seed)
    counts = Counter(rng.choice(names) for _ in range(generation_budget))
    return {
        "seed": seed,
        "total_questions": generation_budget,
        "frame_question_counts": {
            name: int(counts.get(name, 0)) for name in names
        },
    }


def redistribute_frame_question_counts(
    frames: Sequence[FrameInput],
    frame_question_counts: Mapping[str, int],
    generation_budget: int,
) -> dict:
    if generation_budget < 0:
        raise ValueError("generation_budget must be non-negative")

    capacities = {frame.scene_frame: len(frame.questions) for frame in frames}
    adjusted = {}
    redistributed_questions = 0
    for frame in frames:
        name = frame.scene_frame
        requested = max(0, int(frame_question_counts.get(name, 0)))
        assigned = min(requested, capacities[name])
        adjusted[name] = assigned
        redistributed_questions += requested - assigned

    target_questions = min(generation_budget, sum(capacities.values()))
    shortfall = target_questions - sum(adjusted.values())
    heap = []
    for order, frame in enumerate(frames):
        name = frame.scene_frame
        spare = capacities[name] - adjusted[name]
        if spare > 0:
            heapq.heappush(heap, (adjusted[name], order, name, spare))
    while shortfall > 0 and heap:
        current, order, name, spare = heapq.heappop(heap)
        adjusted[name] += 1
        shortfall -= 1
        spare -= 1
        if spare > 0:
            heapq.heappush(heap, (current + 1, order, name, spare))

    return {
        "total_questions": generation_budget,
        "target_questions": target_questions,
        "assigned_questions": sum(adjusted.values()),
        "unassigned_questions": generation_budget - sum(adjusted.values()),
        "redistributed_questions": redistributed_questions,
        "frame_question_counts": adjusted,
        "raw_frame_question_counts": {
            frame.scene_frame: int(frame_question_counts.get(frame.scene_frame, 0))
            for frame in frames
        },
    }


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
        return _select_advtest(questions, max_questions)
    if method == "random":
        stream = [dict(question) for question in questions]
        random.Random(seed).shuffle(stream)
        return stream[:max_questions]
    if method == "template_balanced":
        return _select_template_balanced(questions, max_questions, seed)
    if method == "object_balanced":
        return _select_object_balanced(questions, max_questions, seed)
    if method == "greedy_l0":
        return _select_greedy_coverage(questions, max_questions, "l0", seed)
    if method == "greedy_l1":
        return _select_greedy_coverage(questions, max_questions, "l1", seed)
    raise ValueError(f"Unknown method: {method}")


def _stable_shuffled(questions: Sequence[dict], seed: int) -> List[dict]:
    shuffled = [dict(question) for question in questions]
    random.Random(seed).shuffle(shuffled)
    return shuffled


def _select_advtest(
    questions: Sequence[dict], max_questions: int
) -> List[dict]:
    remaining = [dict(question) for question in questions]
    selected = []
    covered = {"l0": set(), "l1": set(), "l2": set()}
    while remaining and len(selected) < max_questions:
        best_index = max(
            range(len(remaining)),
            key=lambda index: (
                len(_footprint(remaining[index], "l2") - covered["l2"]),
                len(_footprint(remaining[index], "l1") - covered["l1"]),
                len(_footprint(remaining[index], "l0") - covered["l0"]),
                -index,
            ),
        )
        question = remaining.pop(best_index)
        selected.append(question)
        for level in ("l0", "l1", "l2"):
            covered[level].update(_footprint(question, level))
    return selected


def _select_template_balanced(
    questions: Sequence[dict], max_questions: int, seed: int
) -> List[dict]:
    groups = defaultdict(list)
    for question in _stable_shuffled(questions, seed):
        family = str(
            question.get("l2_family")
            or question.get("template_id")
            or "general"
        )
        groups[family].append(question)
    family_names = sorted(groups)
    random.Random(seed).shuffle(family_names)
    queues = {family: deque(groups[family]) for family in family_names}
    selected = []
    while len(selected) < max_questions:
        made_progress = False
        for family in family_names:
            if queues[family]:
                selected.append(queues[family].popleft())
                made_progress = True
                if len(selected) >= max_questions:
                    break
        if not made_progress:
            break
    return selected


def _question_nodes(question: dict) -> set:
    values = question.get("footprint_nodes") or _footprint(question, "l0")
    return {str(value) for value in values if str(value) != "ego"}


def _select_object_balanced(
    questions: Sequence[dict], max_questions: int, seed: int
) -> List[dict]:
    remaining = _stable_shuffled(questions, seed)
    selected = []
    counts = Counter()
    while remaining and len(selected) < max_questions:
        best_index = max(
            range(len(remaining)),
            key=lambda index: (
                sum(1.0 / (1 + counts[node]) for node in _question_nodes(remaining[index])),
                len(_question_nodes(remaining[index])),
                -index,
            ),
        )
        question = remaining.pop(best_index)
        selected.append(question)
        counts.update(_question_nodes(question))
    return selected


def _select_greedy_coverage(
    questions: Sequence[dict], max_questions: int, level: str, seed: int
) -> List[dict]:
    remaining = _stable_shuffled(questions, seed)
    selected = []
    covered = set()
    while remaining and len(selected) < max_questions:
        best_index = max(
            range(len(remaining)),
            key=lambda index: (
                len(_footprint(remaining[index], level) - covered),
                len(_footprint(remaining[index], level)),
                -index,
            ),
        )
        question = remaining.pop(best_index)
        selected.append(question)
        covered.update(_footprint(question, level))
    return selected


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
    generation_budget: int,
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
        if len(suite) >= generation_budget:
            break
        frame_seed = seed + frame_index * 1009
        stream = build_method_stream(
            method,
            frame_input.questions,
            min(policy.max_questions, generation_budget - len(suite)),
            frame_seed,
        )
        gains = []
        reason = "candidate_exhausted"
        frame_state = frame_states[frame_input.scene_frame]

        for local_index, question in enumerate(stream, start=1):
            deltas = _apply_question(frame_state, question)
            gains.append(deltas["delta_l2"])
            record = annotate_provenance(
                question,
                layer=STRUCTURAL_LAYER,
                method=method,
                question_source="programmatic_candidate_space",
                source_question_id=str(
                    question.get("question_id") or question.get("id") or local_index
                ),
                source_sample_token=str(question.get("sample_token") or ""),
                generation_adapter=str(
                    question.get("generation_backend") or "programmatic"
                ),
                uses_coverage_feedback=method in COVERAGE_FEEDBACK_METHODS,
                vlm_call_cost=1,
                scene_frame=frame_input.scene_frame,
                global_budget_index=len(suite) + 1,
            )
            record.update({"frame_budget_index": local_index, **deltas})
            suite.append(record)
            curve.append(
                _metric_snapshot(frame_states, len(suite), frame_index + 1)
            )

            exhausted = local_index == len(stream)
            if method == "advtest":
                reason = choose_switch_reason(
                    gains,
                    covered_l2=len(frame_state.covered_l2),
                    total_l2=frame_state.total_l2,
                    candidates_exhausted=exhausted,
                    policy=policy,
                )
            elif local_index >= policy.max_questions:
                reason = "frame_cap"
            elif exhausted:
                reason = "candidate_exhausted"
            else:
                reason = None
            if reason or len(suite) >= generation_budget:
                if len(suite) >= generation_budget:
                    reason = "global_generation_budget"
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
        while len(curve) <= generation_budget:
            padded = dict(curve[-1])
            padded["question_count"] = len(curve)
            curve.append(padded)

    final_metrics = compute_aggregate_metrics(frame_states, len(suite))
    final_metrics["suite_size"] = len(suite)
    final_metrics["visited_frames"] = len(frame_runs)
    final_metrics["switch_reason_counts"] = dict(switch_counts)
    final_metrics["auc_micro_l2"] = _normalized_auc(
        [point["micro_l2"] for point in curve[: generation_budget + 1]],
        generation_budget,
    )
    final_metrics["auc_macro_l2"] = _normalized_auc(
        [point["macro_l2"] for point in curve[: generation_budget + 1]],
        generation_budget,
    )
    return {
        "method": method,
        "summary": final_metrics,
        "frame_runs": frame_runs,
        "curve": curve[: generation_budget + 1],
        "suite": suite,
    }


def run_method_presampled_frames(
    method: str,
    frames: Sequence[FrameInput],
    generation_budget: int,
    seed: int,
    frame_question_counts: Mapping[str, int],
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
        assigned_questions = int(frame_question_counts.get(frame_input.scene_frame, 0))
        if assigned_questions <= 0:
            continue
        frame_seed = seed + frame_index * 1009
        stream = build_method_stream(
            method,
            frame_input.questions,
            assigned_questions,
            frame_seed,
        )
        gains = []
        frame_state = frame_states[frame_input.scene_frame]
        for local_index, question in enumerate(stream, start=1):
            deltas = _apply_question(frame_state, question)
            gains.append(deltas["delta_l2"])
            record = annotate_provenance(
                question,
                layer=STRUCTURAL_LAYER,
                method=method,
                question_source="programmatic_candidate_space",
                source_question_id=str(
                    question.get("question_id") or question.get("id") or local_index
                ),
                source_sample_token=str(question.get("sample_token") or ""),
                generation_adapter=str(
                    question.get("generation_backend") or "programmatic"
                ),
                uses_coverage_feedback=method in COVERAGE_FEEDBACK_METHODS,
                vlm_call_cost=1,
                scene_frame=frame_input.scene_frame,
                global_budget_index=len(suite) + 1,
            )
            record.update(
                {
                    "frame_budget_index": local_index,
                    "frame_assigned_questions": assigned_questions,
                    **deltas,
                }
            )
            suite.append(record)
            curve.append(
                _metric_snapshot(frame_states, len(suite), len(frame_runs) + 1)
            )

        if len(gains) < assigned_questions:
            reason = "candidate_exhausted"
        else:
            reason = "assigned_questions_done"
        switch_counts[reason] += 1
        frame_runs.append(
            {
                "scene_frame": frame_input.scene_frame,
                "assigned_questions": assigned_questions,
                "questions": len(gains),
                "covered_l2": len(frame_state.covered_l2),
                "total_l2": frame_state.total_l2,
                "coverage_l2": (
                    len(frame_state.covered_l2) / frame_state.total_l2
                    if frame_state.total_l2
                    else 1.0
                ),
                "switch_reason": reason,
                "initial_gain_mean": mean(gains[:20]) if gains else 0.0,
                "final_gain_mean": mean(gains[-20:]) if gains else 0.0,
            }
        )

    if curve:
        while len(curve) <= generation_budget:
            padded = dict(curve[-1])
            padded["question_count"] = len(curve)
            curve.append(padded)

    final_metrics = compute_aggregate_metrics(frame_states, len(suite))
    final_metrics["suite_size"] = len(suite)
    final_metrics["visited_frames"] = len(frame_runs)
    final_metrics["assigned_frame_count"] = sum(
        1 for value in frame_question_counts.values() if int(value) > 0
    )
    final_metrics["switch_reason_counts"] = dict(switch_counts)
    final_metrics["auc_micro_l2"] = _normalized_auc(
        [point["micro_l2"] for point in curve[: generation_budget + 1]],
        generation_budget,
    )
    final_metrics["auc_macro_l2"] = _normalized_auc(
        [point["macro_l2"] for point in curve[: generation_budget + 1]],
        generation_budget,
    )
    return {
        "method": method,
        "summary": final_metrics,
        "frame_runs": frame_runs,
        "curve": curve[: generation_budget + 1],
        "suite": suite,
    }


def _normalized_auc(values: Sequence[float], generation_budget: int) -> float:
    if generation_budget <= 0 or len(values) < 2:
        return 0.0
    area = sum((left + right) / 2 for left, right in zip(values, values[1:]))
    if len(values) - 1 < generation_budget:
        area += values[-1] * (generation_budget - (len(values) - 1))
    return area / generation_budget


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_results(
    output_dir: Path,
    frame_names: Sequence[str],
    generation_budget: int,
    policy: SwitchPolicy,
    method_results: Sequence[dict],
    execution_metadata: Optional[dict] = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "generation_budget": generation_budget,
        "budget_unit": "generated_questions",
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
    if execution_metadata:
        summary.update(execution_metadata)
    with (output_dir / "fixed_budget_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)

    checkpoints = set(range(0, generation_budget + 1, 100))
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

    execution_mode = (
        execution_metadata.get("execution_mode")
        if execution_metadata
        else "sequential_frames"
    )
    report_lines = [
        "# Generation-Budget Structural Coverage Trial",
        "",
        f"- Shared frame pool: {len(frame_names)} frames",
        f"- Generation budget: {generation_budget} questions per method",
        f"- Execution mode: {execution_mode}",
    ]
    if execution_mode == "presampled_frames":
        report_lines.append(
            "- Frame counts are sampled once with the fixed random seed, then "
            "each frame is processed in one batch."
        )
    else:
        report_lines.append(f"- Per-frame range: {policy.min_questions}-{policy.max_questions}")
    report_lines.extend(
        [
        "",
        "| Method | Suite | Frames | Micro L2 | Macro L2 | L2/Q | AUC Micro L2 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
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
    if execution_mode == "presampled_frames":
        report_lines.extend(
            [
                "",
                "## Frame Question Counts",
                "",
                "Frame counts are sampled once with the fixed random seed, then each "
                "frame is processed in one batch.",
            ]
        )
    (output_dir / "fixed_budget_report.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generated-question-budget RQ1 structural coverage trial"
    )
    parser.add_argument("--generation-budget", type=int, default=1000)
    parser.add_argument("--frame-pool-size", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    parser.add_argument(
        "--execution-mode",
        choices=["sequential_frames", "presampled_frames"],
        default="sequential_frames",
        help=(
            "sequential_frames keeps the original frame-by-frame switching; "
            "presampled_frames first samples how many questions each frame gets, "
            "then processes each frame in one batch."
        ),
    )
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
    return parser


def main() -> None:
    args = build_parser().parse_args()

    policy = SwitchPolicy(max_questions=args.max_questions)
    frames = load_frame_pool(
        args.frame_cache,
        args.outputs_root,
        args.frame_pool_size,
        question_load_limit=args.question_load_limit,
    )
    results = []
    frame_assignment = None
    if args.execution_mode == "presampled_frames":
        raw_frame_assignment = build_frame_question_counts(
            [frame.scene_frame for frame in frames],
            args.generation_budget,
            args.seed,
        )
        frame_assignment = redistribute_frame_question_counts(
            frames,
            raw_frame_assignment["frame_question_counts"],
            args.generation_budget,
        )
        frame_assignment["seed"] = raw_frame_assignment["seed"]
        print(
            "[fixed-budget] Presampled frame question counts with seed "
            f"{args.seed}.",
            flush=True,
        )
    for method in args.methods:
        print(f"[fixed-budget] Running {method}...", flush=True)
        if args.execution_mode == "presampled_frames":
            assert frame_assignment is not None
            result = run_method_presampled_frames(
                method,
                frames,
                args.generation_budget,
                args.seed,
                frame_assignment["frame_question_counts"],
            )
        else:
            result = run_method(
                method, frames, args.generation_budget, args.seed, policy
            )
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
        args.generation_budget,
        policy,
        results,
        execution_metadata={
            "execution_mode": args.execution_mode,
            "frame_assignment": frame_assignment,
        }
        if frame_assignment
        else {"execution_mode": args.execution_mode},
    )
    print(f"[fixed-budget] Results written to {args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
