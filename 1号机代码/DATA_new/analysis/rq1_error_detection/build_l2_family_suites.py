import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from fixed_budget_experiment import (
    DEFAULT_FRAME_CACHE,
    DEFAULT_OUTPUTS_ROOT,
    FrameInput,
    SwitchPolicy,
    _footprint,
    build_frame_question_counts,
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
    for family in families:
        output_dir = args.output_root / f"advtest-{family}-q{args.generation_budget}-v1" / "results"
        print(f"[l2-family] Building {family} -> {output_dir}", flush=True)
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
