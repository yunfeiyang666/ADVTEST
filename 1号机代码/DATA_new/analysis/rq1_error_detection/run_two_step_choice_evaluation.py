import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional, Tuple

WORKSPACE_ROOT = Path(__file__).absolute().parents[4]
sys.path.insert(0, str(Path(__file__).parent))

import evaluator
from run_suite_evaluation import (
    DEFAULT_DATAROOT,
    failure_signature,
    frame_qualified_l2_items,
    get_scene_frame,
    l2_items,
    make_evaluator,
    question_family,
    resolve_image_path,
)


DEFAULT_OUTPUT_DIR = (
    WORKSPACE_ROOT
    / "scratch"
    / "rq1_choice_suites_v3_formal"
    / "two_step_choice_eval"
)


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def source_question_text(question: dict) -> str:
    source = str(question.get("source_question") or "").strip()
    if source:
        return source
    text = str(question.get("question") or "")
    marker = "\n\nChoose the best answer from the options below."
    return text.split(marker, 1)[0].strip()


def option_lines(question: dict) -> str:
    choices = question.get("choices") or []
    return "\n".join(
        f"{choice.get('label')}. {choice.get('text')}" for choice in choices
    )


def build_mapping_prompt(question: dict, primary_answer: str) -> str:
    return (
        "We first answered the visual question freely. Now map that answer "
        "to the closest option. Do not solve a new question from scratch; "
        "choose the option that directly answers the original question. "
        "Do not choose objects that are only mentioned as reference/context "
        "in the free-form answer.\n\n"
        f"Original question:\n{source_question_text(question)}\n\n"
        f"Free-form answer:\n{primary_answer}\n\n"
        "Options:\n"
        f"{option_lines(question)}\n\n"
        "Choose the option that best matches the free-form answer and the image. "
        "Answer with the option letter and option text."
    )


def evaluate_primary(
    vlm,
    question: dict,
    mode: str,
    image_path: Optional[Path],
) -> Tuple[str, bool]:
    primary = dict(question)
    primary["question"] = source_question_text(question)
    primary["prompt"] = primary["question"]
    primary.pop("choices", None)
    primary.pop("choice_answer_label", None)
    primary.pop("choice_answer_text", None)
    if mode == "MOCK":
        predicted, _ = vlm.evaluate(primary)
    else:
        if image_path is None:
            raise FileNotFoundError(
                f"A real mosaic is required for {mode} evaluation: "
                f"{get_scene_frame(question)}"
            )
        predicted, _ = vlm.evaluate(primary, image_path)
    return predicted, evaluator.check_correctness(predicted, str(question.get("answer", "")))


def evaluate_mapping(
    vlm,
    question: dict,
    mode: str,
    image_path: Optional[Path],
    primary_answer: str,
) -> Tuple[str, bool]:
    mapped = dict(question)
    mapped["question"] = build_mapping_prompt(question, primary_answer)
    mapped["prompt"] = mapped["question"]
    if mode == "MOCK":
        predicted, _ = vlm.evaluate(mapped)
    else:
        if image_path is None:
            raise FileNotFoundError(
                f"A real mosaic is required for {mode} evaluation: "
                f"{get_scene_frame(question)}"
            )
        predicted, _ = vlm.evaluate(mapped, image_path)
    return predicted, evaluator.check_question_correctness(predicted, mapped)


def evaluate_suite_two_step(
    path: Path,
    vlm,
    mode: str,
    output_dir: Path,
    outputs_root: Path,
    dataroot: Path,
    limit: int = 0,
    write_raw: bool = True,
) -> dict:
    start = time.time()
    total = 0
    wrong = 0
    primary_wrong = 0
    primary_correct_mapping_wrong = 0
    unique_l2 = set()
    failed_l2 = set()
    unique_failure_keys = set()
    failure_by_family = Counter()
    frames = Counter()
    raw_path = output_dir / f"{path.stem}_two_step_raw_results.jsonl"
    image_cache_dir = output_dir / "mosaics"

    if write_raw:
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_handle = raw_path.open("w", encoding="utf-8")
    else:
        raw_handle = None

    try:
        for question in iter_jsonl(path):
            if limit and total >= limit:
                break
            total += 1
            scene_frame = get_scene_frame(question)
            frames[scene_frame] += 1
            question_l2 = l2_items(question)
            qualified_l2 = frame_qualified_l2_items(question)
            unique_l2.update(qualified_l2)

            image_path = resolve_image_path(
                question, outputs_root, image_cache_dir, dataroot
            )
            image_path_text = str(image_path) if image_path else None
            inference_start = time.perf_counter()
            primary_pred, primary_ok = evaluate_primary(
                vlm, question, mode, image_path
            )
            mapping_pred, mapping_ok = evaluate_mapping(
                vlm, question, mode, image_path, primary_pred
            )
            inference_elapsed = time.perf_counter() - inference_start

            if not primary_ok:
                primary_wrong += 1
            if not mapping_ok:
                wrong += 1
                failed_l2.update(qualified_l2)
                family = question_family(question)
                failure_by_family[family] += 1
                unique_failure_keys.add(failure_signature(question, mapping_pred))
                if primary_ok:
                    primary_correct_mapping_wrong += 1

            if raw_handle is not None:
                raw_handle.write(
                    json.dumps(
                        {
                            "method": path.name.replace("_suite.jsonl", ""),
                            "question_index": total,
                            "scene_frame": scene_frame,
                            "question_id": question.get("question_id", ""),
                            "family": question_family(question),
                            "source_question": source_question_text(question),
                            "mapping_prompt": build_mapping_prompt(
                                question, primary_pred
                            ),
                            "answer": question.get("answer", ""),
                            "choices": question.get("choices", []),
                            "choice_answer_label": question.get(
                                "choice_answer_label", ""
                            ),
                            "choice_answer_text": question.get(
                                "choice_answer_text", ""
                            ),
                            "primary_predicted": primary_pred,
                            "primary_is_correct": primary_ok,
                            "mapping_predicted": mapping_pred,
                            "is_correct": mapping_ok,
                            "mode": mode,
                            "inference_elapsed_seconds": inference_elapsed,
                            "image_path": image_path_text,
                            "vlm_calls": 2,
                            "l2_items": sorted(question_l2),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    finally:
        if raw_handle is not None:
            raw_handle.close()

    elapsed = time.time() - start
    return {
        "suite": path.name,
        "method": path.name.replace("_suite.jsonl", ""),
        "mode": mode,
        "questions": total,
        "vlm_calls": total * 2,
        "primary_wrong": primary_wrong,
        "primary_failure_rate": primary_wrong / total if total else 0.0,
        "wrong": wrong,
        "failure_rate": wrong / total if total else 0.0,
        "primary_correct_mapping_wrong": primary_correct_mapping_wrong,
        "unique_failures": len(unique_failure_keys),
        "unique_failures_per_100_calls": (
            len(unique_failure_keys) / (total * 2) * 100 if total else 0.0
        ),
        "failure_category_count": len(failure_by_family),
        "unique_l2": len(unique_l2),
        "failed_unique_l2": len(failed_l2),
        "visited_frames": len(frames),
        "elapsed_seconds": elapsed,
    }


def write_report(results: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "two_step_choice_summary.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    csv_path = output_dir / "two_step_choice_summary.csv"
    fields = [
        "method",
        "questions",
        "vlm_calls",
        "primary_wrong",
        "primary_failure_rate",
        "wrong",
        "failure_rate",
        "primary_correct_mapping_wrong",
        "unique_failures",
        "unique_failures_per_100_calls",
        "failure_category_count",
        "unique_l2",
        "failed_unique_l2",
        "visited_frames",
        "elapsed_seconds",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow({field: result[field] for field in fields})

    lines = ["# Two-Step Choice Evaluation", ""]
    lines.append(
        "| Method | Q | Calls | Primary Wrong | Final Wrong | "
        "Primary-Correct But Mapping Wrong | Unique Failures |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for result in results:
        lines.append(
            f"| {result['method']} | {result['questions']} | "
            f"{result['vlm_calls']} | {result['primary_wrong']} "
            f"({result['primary_failure_rate']:.3f}) | "
            f"{result['wrong']} ({result['failure_rate']:.3f}) | "
            f"{result['primary_correct_mapping_wrong']} | "
            f"{result['unique_failures']} |"
        )
    (output_dir / "two_step_choice_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate multiple-choice suites with free-form answer first."
    )
    parser.add_argument("--suite-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "outputs",
    )
    parser.add_argument("--dataroot", type=Path, default=DEFAULT_DATAROOT)
    parser.add_argument(
        "--mode",
        choices=["MOCK", "LOCAL_GPU", "API", "MPLUG", "MINICPM"],
        default="MOCK",
    )
    parser.add_argument("--methods", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-raw", action="store_true")
    args = parser.parse_args()

    suites = sorted(args.suite_dir.glob("*_suite.jsonl"))
    if args.methods:
        allowed = {method.lower() for method in args.methods}
        suites = [
            suite
            for suite in suites
            if suite.name.replace("_suite.jsonl", "").lower() in allowed
        ]
    if not suites:
        raise FileNotFoundError(f"No requested suites found in {args.suite_dir}")

    vlm = make_evaluator(args.mode)
    results = []
    for suite in suites:
        print(
            f"[two-step] Evaluating {suite.name} mode={args.mode} "
            f"limit={args.limit or 'all'}",
            flush=True,
        )
        result = evaluate_suite_two_step(
            suite,
            vlm,
            args.mode,
            args.output_dir,
            args.outputs_root,
            args.dataroot,
            limit=args.limit,
            write_raw=not args.no_raw,
        )
        print(
            f"[two-step]   primary_wrong={result['primary_wrong']}/"
            f"{result['questions']} final_wrong={result['wrong']}/"
            f"{result['questions']} calls={result['vlm_calls']}",
            flush=True,
        )
        results.append(result)
    write_report(results, args.output_dir)
    print(f"[two-step] Results written to {args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
