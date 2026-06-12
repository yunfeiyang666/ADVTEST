import argparse
import json
import time
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence, Tuple

from official_qa_experiment import (
    DEFAULT_DATAROOT,
    DEFAULT_FRAME_CACHE,
    DEFAULT_OUTPUTS_ROOT,
    DEFAULT_QUESTIONS_PATH,
    index_official_questions,
    load_official_questions,
    resolve_frame_samples,
)
from qaasker_adapter import QAAskeRAdapter, QAAskeRMR2Process
from run_suite_evaluation import (
    evaluate_question,
    make_evaluator,
    resolve_image_path,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_DIR = (
    WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "analysis" / "qaasker_results"
)
DEFAULT_QAASKER_PYTHON = WORKSPACE_ROOT / ".venv310" / "Scripts" / "python.exe"


def iter_qaasker_seeds(
    frame_samples: Sequence[Tuple[str, str]],
    questions_by_sample: Mapping[str, Sequence[dict]],
) -> Iterable[Tuple[str, dict]]:
    for scene_frame, sample_token in frame_samples:
        for question in questions_by_sample.get(sample_token, ()):
            text = str(question.get("question") or "").strip().lower()
            if text.startswith(("what ", "which ", "who ", "where ", "when ", "how ")):
                yield scene_frame, dict(question)


def evaluate_qaasker_seeds(
    seeds: Iterable[Tuple[str, dict]],
    *,
    adapter: QAAskeRAdapter,
    vlm,
    mode: str,
    vlm_call_budget: int,
    outputs_root: Optional[Path] = None,
    dataroot: Optional[Path] = None,
    image_cache_dir: Optional[Path] = None,
) -> dict:
    started = time.time()
    vlm_calls = 0
    pairs = 0
    violations = 0
    unique_violation_sources = set()
    records = []
    stop_reason = None

    for scene_frame, seed in seeds:
        if vlm_calls >= vlm_call_budget:
            stop_reason = "global_budget"
            break
        if vlm_calls + 2 > vlm_call_budget:
            stop_reason = "insufficient_budget_for_pair"
            break
        image_path = None
        if mode != "MOCK":
            if outputs_root is None or dataroot is None or image_cache_dir is None:
                raise ValueError("Real VLM mode requires image path configuration")
            probe = {"scene_frame": scene_frame}
            image_path = resolve_image_path(
                probe, outputs_root, image_cache_dir, dataroot
            )

        primary = adapter.build_primary(
            seed,
            scene_frame=scene_frame,
            global_budget_index=vlm_calls + 1,
        )
        primary_predicted, primary_correct = evaluate_question(
            vlm, primary, mode, image_path
        )
        primary.update(
            {
                "predicted": primary_predicted,
                "is_correct": primary_correct,
            }
        )

        followup = adapter.build_followup(
            seed,
            primary_sut_answer=primary_predicted,
            scene_frame=scene_frame,
            global_budget_index=vlm_calls + 2,
        )
        followup_predicted, followup_consistent = evaluate_question(
            vlm, followup, mode, image_path
        )
        violation = not followup_consistent
        followup.update(
            {
                "predicted": followup_predicted,
                "is_correct": followup_consistent,
                "is_mr_violation": violation,
            }
        )

        records.extend([primary, followup])
        vlm_calls += 2
        pairs += 1
        if violation:
            violations += 1
            unique_violation_sources.add(str(seed["official_question_id"]))

    if stop_reason is None and vlm_calls >= vlm_call_budget:
        stop_reason = "global_budget"

    return {
        "method": "qaasker_mr2",
        "questions": len(records),
        "vlm_calls": vlm_calls,
        "vlm_call_budget": vlm_call_budget,
        "pairs": pairs,
        "violations": violations,
        "unique_violations": len(unique_violation_sources),
        "wrong": violations,
        "unique_failures": len(unique_violation_sources),
        "violation_rate": violations / pairs if pairs else 0.0,
        "failure_rate": violations / pairs if pairs else 0.0,
        "duplicate_failure_rate": (
            (violations - len(unique_violation_sources)) / violations
            if violations
            else 0.0
        ),
        "failure_category_count": 1 if violations else 0,
        "unique_violations_per_100_calls": (
            len(unique_violation_sources) / vlm_calls * 100 if vlm_calls else 0.0
        ),
        "unique_failures_per_100_calls": (
            len(unique_violation_sources) / vlm_calls * 100 if vlm_calls else 0.0
        ),
        "calls_per_unique_failure": (
            vlm_calls / len(unique_violation_sources)
            if unique_violation_sources
            else None
        ),
        "budget_stop_reason": stop_reason,
        "elapsed_seconds": time.time() - started,
        "records": records,
    }


def write_results(result: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = result["records"]
    summary = {key: value for key, value in result.items() if key != "records"}
    (output_dir / "qaasker_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with (output_dir / "qaasker_raw_results.jsonl").open(
        "w", encoding="utf-8"
    ) as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    report = [
        "# QAAskeR MR2 Evaluation",
        "",
        f"- VLM calls: {summary['vlm_calls']}",
        f"- Complete pairs: {summary['pairs']}",
        f"- MR violations: {summary['violations']}",
        f"- Unique violations: {summary['unique_violations']}",
        f"- Violation rate: {summary['violation_rate']:.4f}",
        (
            "- Unique violations per 100 calls: "
            f"{summary['unique_violations_per_100_calls']:.2f}"
        ),
    ]
    (output_dir / "qaasker_report.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate original QAAskeR MR2 with a VLM-call budget."
    )
    parser.add_argument("--mode", choices=["MOCK", "MPLUG", "MINICPM"], default="MOCK")
    parser.add_argument("--vlm-call-budget", type=int, default=1000)
    parser.add_argument("--frame-pool-size", type=int, default=100)
    parser.add_argument("--questions-path", type=Path, default=DEFAULT_QUESTIONS_PATH)
    parser.add_argument("--frame-cache", type=Path, default=DEFAULT_FRAME_CACHE)
    parser.add_argument("--outputs-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    parser.add_argument("--dataroot", type=Path, default=DEFAULT_DATAROOT)
    parser.add_argument("--qaasker-python", type=Path, default=DEFAULT_QAASKER_PYTHON)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    frame_samples = resolve_frame_samples(
        args.frame_cache,
        args.outputs_root,
        args.dataroot,
        args.frame_pool_size,
    )
    indexed = index_official_questions(load_official_questions(args.questions_path))
    seeds = list(iter_qaasker_seeds(frame_samples, indexed))
    vlm = make_evaluator(args.mode)
    image_cache_dir = args.output_dir / "mosaics"

    with QAAskeRMR2Process(args.qaasker_python) as backend:
        adapter = QAAskeRAdapter(followup_generator=backend.generate)
        result = evaluate_qaasker_seeds(
            seeds,
            adapter=adapter,
            vlm=vlm,
            mode=args.mode,
            vlm_call_budget=args.vlm_call_budget,
            outputs_root=args.outputs_root,
            dataroot=args.dataroot,
            image_cache_dir=image_cache_dir,
        )
    write_results(result, args.output_dir)
    print(
        f"[qaasker] calls={result['vlm_calls']} pairs={result['pairs']} "
        f"violations={result['violations']} -> {args.output_dir}"
    )


if __name__ == "__main__":
    main()
