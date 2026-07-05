import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from fixed_budget_experiment import (
    DEFAULT_FRAME_CACHE,
    DEFAULT_OUTPUTS_ROOT,
    FrameCoverage,
    FrameInput,
    SwitchPolicy,
    _footprint,
    _metric_snapshot,
    _normalized_auc,
    annotate_provenance,
    build_frame_question_counts,
    compute_aggregate_metrics,
    redistribute_frame_question_counts,
    run_method_presampled_frames,
    write_results,
)


L2_FAMILIES = ("converge", "direction_chain", "distance_chain", "viewpoint_transfer")


def _question_file(frame_dir: Path, scene_frame: str) -> Path:
    qa_dir = frame_dir / "generation" / "qa"
    for path in (
        qa_dir / f"{scene_frame}_generated.jsonl",
        qa_dir / f"{scene_frame}_all.jsonl",
    ):
        if path.exists():
            return path
    raise FileNotFoundError(f"No generated question JSONL found for {scene_frame}")


def _family(question: dict) -> str:
    return str(question.get("l2_family") or question.get("template_id") or "general")


def _rank_key(question: dict) -> tuple:
    return (
        len(_footprint(question, "l2")),
        len(_footprint(question, "l1")),
        len(_footprint(question, "l0")),
        str(question.get("question_id") or question.get("id") or ""),
    )


def _read_summary(frame_dir: Path, scene_frame: str) -> tuple[int, int, int]:
    summary_path = frame_dir / "reports" / f"{scene_frame}_summary.json"
    with summary_path.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)
    coverage = summary.get("coverage") or {}
    return (
        int(coverage.get("l0") or 0),
        int(coverage.get("l1") or 0),
        int(summary.get("total_gap_count") or coverage.get("l2") or 0),
    )


def _load_frame_names(frame_cache: Path, frame_pool_size: int) -> list[str]:
    with frame_cache.open("r", encoding="utf-8") as handle:
        cached_frames = json.load(handle)
    return [item["scene_frame"] for item in cached_frames[:frame_pool_size]]


def load_family_frames(
    frame_names: Iterable[str],
    outputs_root: Path,
    families: tuple[str, ...],
    per_frame_candidate_limit: int,
) -> dict[str, list[FrameInput]]:
    frames_by_family = {family: [] for family in families}
    for index, scene_frame in enumerate(frame_names, start=1):
        print(f"[l2-family] Loading frame {index}: {scene_frame}", flush=True)
        frame_dir = outputs_root / scene_frame
        total_l0, total_l1, total_l2 = _read_summary(frame_dir, scene_frame)
        buckets = defaultdict(list)
        with _question_file(frame_dir, scene_frame).open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                question = json.loads(line)
                family = _family(question)
                if family in frames_by_family:
                    buckets[family].append(question)
        for family in families:
            candidates = sorted(buckets[family], key=_rank_key, reverse=True)
            frames_by_family[family].append(
                FrameInput(
                    scene_frame=scene_frame,
                    questions=candidates[:per_frame_candidate_limit],
                    total_l0=total_l0,
                    total_l1=total_l1,
                    total_l2=total_l2,
                )
            )
    return frames_by_family


def select_common_frames(
    frames_by_family: dict[str, list[FrameInput]], families: tuple[str, ...]
) -> dict[str, list[FrameInput]]:
    frame_order = [frame.scene_frame for frame in frames_by_family[families[0]]]
    lookup = {
        family: {frame.scene_frame: frame for frame in frames_by_family[family]}
        for family in families
    }
    common_names = [
        scene_frame
        for scene_frame in frame_order
        if all(lookup[family][scene_frame].questions for family in families)
    ]
    return {
        family: [lookup[family][scene_frame] for scene_frame in common_names]
        for family in families
    }


def _flatten_questions(frames: list[FrameInput]) -> list[dict]:
    rows = []
    for frame in frames:
        for question in frame.questions:
            row = dict(question)
            row["scene_frame"] = frame.scene_frame
            rows.append(row)
    return rows


def build_random_common_frame_suite(
    family: str,
    frames: list[FrameInput],
    output_dir: Path,
    generation_budget: int,
    seed: int,
    per_frame_candidate_limit: int,
) -> dict:
    rng = random.Random(f"{seed}:{family}:common-frame-random")
    candidates = _flatten_questions(frames)
    rng.shuffle(candidates)
    if len(candidates) < generation_budget:
        raise ValueError(
            f"Family {family} has only {len(candidates)} candidates, "
            f"less than requested budget {generation_budget}"
        )
    selected = candidates[:generation_budget]
    coverage_states = {
        frame.scene_frame: FrameCoverage(
            total_l0=frame.total_l0,
            total_l1=frame.total_l1,
            total_l2=frame.total_l2,
        )
        for frame in frames
    }
    suite = []
    curve = []
    visited_frames = set()
    for global_index, question in enumerate(selected, start=1):
        scene_frame = question["scene_frame"]
        visited_frames.add(scene_frame)
        state = coverage_states[scene_frame]
        deltas = {}
        for level in ("l0", "l1", "l2"):
            covered = getattr(state, f"covered_{level}")
            new_items = _footprint(question, level) - covered
            covered.update(new_items)
            deltas[f"delta_{level}"] = len(new_items)
        record = annotate_provenance(
            question,
            layer="structural_coverage",
            method="advtest",
            question_source="programmatic_candidate_space_random_common_frames",
            source_question_id=str(
                question.get("question_id") or question.get("id") or global_index
            ),
            source_sample_token=str(question.get("sample_token") or ""),
            generation_adapter=str(question.get("generation_backend") or "programmatic"),
            uses_coverage_feedback=False,
            vlm_call_cost=1,
            scene_frame=scene_frame,
            global_budget_index=global_index,
        )
        record.update(
            {
                "selection_mode": "random_common_frames",
                "frame_budget_index": None,
                "frame_assigned_questions": None,
                **deltas,
            }
        )
        suite.append(record)
        curve.append(
            _metric_snapshot(
                coverage_states,
                global_index,
                len(visited_frames),
            )
        )
    summary = compute_aggregate_metrics(coverage_states, len(suite))
    summary["suite_size"] = len(suite)
    summary["visited_frames"] = len(visited_frames)
    summary["switch_reason_counts"] = {}
    summary["auc_micro_l2"] = _normalized_auc(
        [point["micro_l2"] for point in curve],
        generation_budget,
    )
    summary["auc_macro_l2"] = _normalized_auc(
        [point["macro_l2"] for point in curve],
        generation_budget,
    )
    result = {
        "method": "advtest",
        "summary": summary,
        "frame_runs": [],
        "curve": curve,
        "suite": suite,
    }
    write_results(
        output_dir,
        [frame.scene_frame for frame in frames],
        generation_budget,
        SwitchPolicy(),
        [result],
        execution_metadata={
            "execution_mode": "random_common_frames",
            "l2_family_filter": [family],
            "per_frame_candidate_limit": per_frame_candidate_limit,
            "common_frame_count": len(frames),
            "seed": seed,
        },
    )
    return result


def build_family_suite(
    family: str,
    frames: list[FrameInput],
    output_dir: Path,
    generation_budget: int,
    seed: int,
    per_frame_candidate_limit: int,
) -> dict:
    raw_assignment = build_frame_question_counts(
        [frame.scene_frame for frame in frames],
        generation_budget,
        seed,
    )
    frame_assignment = redistribute_frame_question_counts(
        frames,
        raw_assignment["frame_question_counts"],
        generation_budget,
    )
    frame_assignment["seed"] = raw_assignment["seed"]
    result = run_method_presampled_frames(
        "advtest",
        frames,
        generation_budget,
        seed,
        frame_assignment["frame_question_counts"],
    )
    write_results(
        output_dir,
        [frame.scene_frame for frame in frames],
        generation_budget,
        SwitchPolicy(),
        [result],
        execution_metadata={
            "execution_mode": "presampled_frames",
            "l2_family_filter": [family],
            "per_frame_candidate_limit": per_frame_candidate_limit,
            "frame_assignment": frame_assignment,
        },
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build one ADVTEST L2 suite per family.")
    parser.add_argument("--generation-budget", type=int, default=1000)
    parser.add_argument("--frame-pool-size", type=int, default=308)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--frame-cache", type=Path, default=DEFAULT_FRAME_CACHE)
    parser.add_argument("--outputs-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("scratch/rq1_l2_family_1000"),
    )
    parser.add_argument("--per-frame-candidate-limit", type=int, default=200)
    parser.add_argument("--families", nargs="+", default=list(L2_FAMILIES))
    parser.add_argument(
        "--selection-mode",
        choices=["advtest_presampled", "random_common_frames"],
        default="advtest_presampled",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    families = tuple(args.families)
    frame_names = _load_frame_names(args.frame_cache, args.frame_pool_size)
    frames_by_family = load_family_frames(
        frame_names,
        args.outputs_root,
        families,
        args.per_frame_candidate_limit,
    )
    if args.selection_mode == "random_common_frames":
        frames_by_family = select_common_frames(frames_by_family, families)
        common_count = len(frames_by_family[families[0]]) if families else 0
        print(f"[l2-family] Common frame count: {common_count}", flush=True)
    for family in families:
        output_dir = args.output_root / f"advtest-{family}-q{args.generation_budget}-v1" / "results"
        print(f"[l2-family] Building {family} -> {output_dir}", flush=True)
        if args.selection_mode == "random_common_frames":
            result = build_random_common_frame_suite(
                family,
                frames_by_family[family],
                output_dir,
                args.generation_budget,
                args.seed,
                args.per_frame_candidate_limit,
            )
        else:
            result = build_family_suite(
                family,
                frames_by_family[family],
                output_dir,
                args.generation_budget,
                args.seed,
                args.per_frame_candidate_limit,
            )
        print(
            f"[l2-family] {family}: suite={result['summary']['suite_size']} "
            f"frames={result['summary']['visited_frames']} "
            f"micro_l2={result['summary']['micro_l2']:.4f}",
            flush=True,
        )


if __name__ == "__main__":
    main()
