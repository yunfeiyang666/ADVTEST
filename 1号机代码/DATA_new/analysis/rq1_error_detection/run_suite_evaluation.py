import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

WORKSPACE_ROOT = Path(__file__).absolute().parents[4]
sys.path.insert(0, str(Path(__file__).parent))

import evaluator

DEFAULT_SUITE_DIR = (
    WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "analysis" / "fixed_budget_results"
)
DEFAULT_OUTPUT_DIR = (
    WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "analysis" / "suite_eval_results"
)

DEFAULT_DATAROOT = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "data"


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def get_scene_frame(question: dict) -> str:
    scene_frame = question.get("scene_frame")
    if scene_frame:
        return str(scene_frame)
    scene = question.get("scene_name")
    frame_idx = question.get("frame_idx")
    if scene is not None and frame_idx is not None:
        return f"{scene}_frame{frame_idx}"
    return "unknown"


def l2_items(question: dict) -> set:
    if question.get("coverage_l2_items"):
        return set(map(str, question["coverage_l2_items"]))
    footprint = question.get("coverage_footprint") or {}
    return set(map(str, footprint.get("l2") or question.get("coverage_l2") or []))


def frame_qualified_l2_items(question: dict) -> set:
    scene_frame = get_scene_frame(question)
    return {f"{scene_frame}::{item}" for item in l2_items(question)}


def question_family(question: dict) -> str:
    return str(
        question.get("family")
        or question.get("l2_family")
        or question.get("template_id")
        or question.get("template_type")
        or question.get("mutation_operator")
        or "unknown"
    )


def failure_signature(question: dict, predicted: str) -> str:
    source = str(question.get("question_source") or "")
    source_id = str(question.get("source_question_id") or "")
    if source == "nuscenes_qa" and source_id:
        return f"nuscenes_qa|{source_id}"

    items = sorted(frame_qualified_l2_items(question))
    if items:
        return "l2|" + "|".join(items)

    scene_frame = get_scene_frame(question)
    family = question_family(question)
    answer = evaluator.normalize_answer(str(question.get("answer") or ""))
    return f"semantic|{scene_frame}|{family}|{answer}"



def resolve_image_path(
    question: dict, outputs_root: Path, image_cache_dir: Path, dataroot: Path
) -> Optional[Path]:
    direct_image = question.get("image_path")
    if direct_image:
        direct_path = Path(str(direct_image))
        if direct_path.exists():
            return direct_path

    scene_frame = get_scene_frame(question)
    if scene_frame == "unknown":
        return None
    cached = image_cache_dir / f"{scene_frame}_mosaic.jpg"
    if cached.exists():
        return cached
    sg_path = (
        outputs_root
        / scene_frame
        / "offline"
        / "scene_graphs"
        / f"{scene_frame}_filtered_scene_graph.json"
    )
    if not sg_path.exists():
        return None
    try:
        scene_graph = json.loads(sg_path.read_text(encoding="utf-8"))
        ok = evaluator.render_labeled_mosaic(scene_graph, dataroot, cached)
    except Exception as exc:
        print(f"[suite-eval] Mosaic render failed for {scene_frame}: {exc}", flush=True)
        return None
    return cached if ok and cached.exists() else None


def make_evaluator(
    mode: str,
    model_path: Optional[str] = None,
    model_base: Optional[str] = None,
):
    if mode == "MOCK":
        return evaluator.MockVLMEvaluator()
    if mode == "LOCAL_GPU":
        return evaluator.LocalGPUEvaluator()
    if mode == "MPLUG":
        kwargs = {}
        if model_path:
            kwargs["model_path"] = model_path
        if model_base:
            kwargs["model_base"] = model_base
        return evaluator.MPLUGEvaluator(**kwargs)
    if mode == "MINICPM":
        return evaluator.MiniCPMOEvaluator()
    if mode == "API":
        return evaluator.APIEvaluator()
    raise ValueError(f"Unknown mode: {mode}")


def evaluate_question(
    vlm, question: dict, mode: str, image_path: Optional[Path]
) -> Tuple[str, bool]:
    if mode == "MOCK":
        predicted, _ = vlm.evaluate(question)
        return predicted, evaluator.check_question_correctness(predicted, question)
    if image_path is None:
        raise FileNotFoundError(
            f"A real mosaic is required for {mode} evaluation: "
            f"{get_scene_frame(question)}"
        )
    predicted, _ = vlm.evaluate(question, image_path)
    return predicted, evaluator.check_question_correctness(predicted, question)


def evaluate_suite(
    path: Path,
    vlm,
    mode: str,
    output_dir: Path,
    outputs_root: Path,
    dataroot: Path,
    limit: int = 0,
    vlm_call_budget: int = 0,
    write_raw: bool = True,
    resume: bool = False,
) -> dict:
    start = time.time()
    total = 0
    correct = 0
    wrong = 0
    unique_l2 = set()
    failed_l2 = set()
    frames = Counter()
    failure_by_family = Counter()
    failure_rows = []
    unique_failure_keys = set()
    vlm_calls = 0
    budget_stop_reason = None
    cache: Dict[
        Tuple[str, str],
        Tuple[str, bool, Optional[str], float],
    ] = {}
    raw_path = output_dir / f"{path.stem}_raw_results.jsonl"
    image_cache_dir = output_dir / "mosaics"
    resume_rows = []
    if resume:
        if not write_raw:
            raise ValueError("--resume requires raw-result writing")
        if raw_path.exists():
            resume_rows = list(iter_jsonl(raw_path))
        if limit and len(resume_rows) > limit:
            raise ValueError(
                f"Raw results contain {len(resume_rows)} rows, exceeding limit={limit}"
            )
        resumed_calls = sum(int(row.get("vlm_call_cost") or 1) for row in resume_rows)
        if vlm_call_budget and resumed_calls > vlm_call_budget:
            raise ValueError(
                "Existing raw results already exceed the requested VLM call budget"
            )
    if write_raw:
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_handle = raw_path.open("a" if resume else "w", encoding="utf-8")
    else:
        raw_handle = None

    try:
        for question in iter_jsonl(path):
            if limit and total >= limit:
                budget_stop_reason = "question_limit"
                break
            call_cost = int(question.get("vlm_call_cost") or 1)
            if call_cost < 1:
                raise ValueError("vlm_call_cost must be a positive integer")
            if vlm_call_budget and vlm_calls + call_cost > vlm_call_budget:
                budget_stop_reason = "next_record_exceeds_budget"
                break
            total += 1
            vlm_calls += call_cost
            scene_frame = get_scene_frame(question)
            frames[scene_frame] += 1
            question_l2 = l2_items(question)
            qualified_question_l2 = frame_qualified_l2_items(question)
            unique_l2.update(qualified_question_l2)
            q_text = str(question.get("question", ""))
            cache_key = (scene_frame, q_text)
            use_cache = mode == "MOCK"
            resume_row = resume_rows[total - 1] if total <= len(resume_rows) else None
            if resume_row is not None:
                expected_identity = (
                    scene_frame,
                    str(question.get("source_question_id") or ""),
                    q_text,
                    mode,
                    call_cost,
                )
                actual_identity = (
                    str(resume_row.get("scene_frame") or ""),
                    str(resume_row.get("source_question_id") or ""),
                    str(resume_row.get("question") or ""),
                    str(resume_row.get("mode") or ""),
                    int(resume_row.get("vlm_call_cost") or 1),
                )
                if actual_identity != expected_identity:
                    raise ValueError(
                        "Resume raw results are not an exact prefix of the suite at "
                        f"question {total}: expected={expected_identity}, "
                        f"found={actual_identity}"
                    )
                predicted = str(resume_row.get("predicted") or "")
                is_correct = bool(resume_row.get("is_correct"))
                image_path_text = resume_row.get("image_path")
                inference_elapsed = float(
                    resume_row.get("inference_elapsed_seconds") or 0.0
                )
            elif use_cache and cache_key in cache:
                predicted, is_correct, image_path_text, inference_elapsed = cache[
                    cache_key
                ]
            else:
                image_path = resolve_image_path(
                    question, outputs_root, image_cache_dir, dataroot
                )
                image_path_text = str(image_path) if image_path else None
                inference_start = time.perf_counter()
                predicted, is_correct = evaluate_question(vlm, question, mode, image_path)
                inference_elapsed = time.perf_counter() - inference_start
                if use_cache:
                    cache[cache_key] = (
                        predicted,
                        is_correct,
                        image_path_text,
                        inference_elapsed,
                    )
            family = question_family(question)
            if raw_handle is not None and resume_row is None:
                raw_handle.write(
                    json.dumps(
                        {
                            "method": path.name.replace("_suite.jsonl", ""),
                            "question_index": total,
                            "scene_frame": scene_frame,
                            "question_id": question.get("question_id", ""),
                            "family": family,
                            "question": q_text,
                            "prompt": q_text,
                            "answer": question.get("answer", ""),
                            "choices": question.get("choices", []),
                            "choice_answer_label": question.get(
                                "choice_answer_label", ""
                            ),
                            "choice_answer_text": question.get(
                                "choice_answer_text", ""
                            ),
                            "predicted": predicted,
                            "raw_model_output": predicted,
                            "is_correct": is_correct,
                            "mode": mode,
                            "inference_elapsed_seconds": inference_elapsed,
                            "error": None,
                            "experiment_layer": question.get("experiment_layer", ""),
                            "question_source": question.get("question_source", ""),
                            "source_question_id": question.get(
                                "source_question_id", ""
                            ),
                            "vlm_call_cost": call_cost,
                            "cumulative_vlm_calls": vlm_calls,
                            "image_path": image_path_text,
                            "l2_items": sorted(question_l2),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                raw_handle.flush()
            if is_correct:
                correct += 1
                continue
            wrong += 1
            failed_l2.update(qualified_question_l2)
            failure_by_family[family] += 1
            signature = failure_signature(question, predicted)
            unique_failure_keys.add(signature)
            if len(failure_rows) < 200:
                failure_rows.append(
                    {
                        "scene_frame": scene_frame,
                        "question_id": question.get("question_id", ""),
                        "family": family,
                        "question": q_text,
                        "answer": question.get("answer", ""),
                        "predicted": predicted,
                        "failure_signature": signature,
                        "image_path": image_path_text,
                        "l2_items": sorted(question_l2),
                    }
                )
    finally:
        if raw_handle is not None:
            raw_handle.close()

    if len(resume_rows) > total:
        raise ValueError(
            "Suite ended before all existing resume rows could be matched"
        )

    elapsed = time.time() - start
    unique_failures = len(unique_failure_keys)
    return {
        "suite": path.name,
        "method": path.name.replace("_suite.jsonl", ""),
        "mode": mode,
        "limit": limit or None,
        "questions": total,
        "resumed_questions": min(len(resume_rows), total),
        "vlm_calls": vlm_calls,
        "vlm_call_budget": vlm_call_budget or None,
        "budget_stop_reason": budget_stop_reason,
        "correct": correct,
        "wrong": wrong,
        "failure_rate": wrong / total if total else 0.0,
        "unique_failures": unique_failures,
        "unique_failures_per_100_calls": (
            unique_failures / vlm_calls * 100 if vlm_calls else 0.0
        ),
        "calls_per_unique_failure": (
            vlm_calls / unique_failures if unique_failures else None
        ),
        "duplicate_failure_rate": (
            (wrong - unique_failures) / wrong if wrong else 0.0
        ),
        "failure_category_count": len(failure_by_family),
        "unique_l2": len(unique_l2),
        "failed_unique_l2": len(failed_l2),
        "failed_l2_per_question": len(failed_l2) / total if total else 0.0,
        "visited_frames": len(frames),
        "top_failure_families": failure_by_family.most_common(10),
        "elapsed_seconds": elapsed,
        "failure_examples": failure_rows,
    }


def write_report(results: list, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "suite_eval_summary.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    csv_path = output_dir / "suite_eval_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "method",
                "questions",
                "vlm_calls",
                "wrong",
                "failure_rate",
                "unique_failures",
                "unique_failures_per_100_calls",
                "calls_per_unique_failure",
                "duplicate_failure_rate",
                "failure_category_count",
                "unique_l2",
                "failed_unique_l2",
                "failed_l2_per_question",
                "visited_frames",
                "elapsed_seconds",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow({key: result[key] for key in writer.fieldnames})

    md_lines = ["# Budgeted Suite Evaluation Report", ""]
    md_lines.append(
        "| Method | Q | Calls | Wrong | Unique Failures | UF/100 Calls | "
        "Duplicate Rate | Failure Types | Failed L2 | Frames |"
    )
    md_lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for result in results:
        md_lines.append(
            f"| {result['method']} | {result['questions']} | {result['vlm_calls']} | "
            f"{result['wrong']} | {result['unique_failures']} | "
            f"{result['unique_failures_per_100_calls']:.2f} | "
            f"{result['duplicate_failure_rate']:.3f} | "
            f"{result['failure_category_count']} | "
            f"{result['failed_unique_l2']} | {result['visited_frames']} |"
        )
    (output_dir / "suite_eval_report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Evaluate fixed-budget suites end-to-end.")
    parser.add_argument("--suite-dir", type=Path, default=DEFAULT_SUITE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "outputs",
    )
    parser.add_argument(
        "--mode",
        choices=["MOCK", "LOCAL_GPU", "API", "MPLUG", "MINICPM"],
        default="MOCK",
    )
    parser.add_argument("--dataroot", type=Path, default=DEFAULT_DATAROOT)
    parser.add_argument(
        "--model-path",
        help="Explicit base checkpoint or LoRA adapter directory for MPLUG mode.",
    )
    parser.add_argument(
        "--model-base",
        help="Base checkpoint directory when --model-path is a LoRA adapter.",
    )
    parser.add_argument("--methods", nargs="*", default=None)
    parser.add_argument(
        "--no-raw", action="store_true", help="Do not write raw per-question JSONL results."
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue an existing raw JSONL after verifying it is an exact suite prefix.",
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Optional per-suite question cap for smoke runs."
    )
    parser.add_argument(
        "--vlm-call-budget",
        type=int,
        default=0,
        help="Maximum logical VLM calls per suite. Records never partially consume budget.",
    )
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
        raise FileNotFoundError(f"No *_suite.jsonl files found in {args.suite_dir}")
    if args.model_base and args.mode != "MPLUG":
        parser.error("--model-base is only supported in MPLUG mode")
    vlm = make_evaluator(args.mode, args.model_path, args.model_base)
    results = []
    for suite in suites:
        print(f"[suite-eval] Evaluating {suite.name} mode={args.mode} limit={args.limit or 'all'}", flush=True)
        result = evaluate_suite(
            suite,
            vlm,
            args.mode,
            args.output_dir,
            args.outputs_root,
            args.dataroot,
            args.limit,
            vlm_call_budget=args.vlm_call_budget,
            write_raw=not args.no_raw,
            resume=args.resume,
        )
        print(
            f"[suite-eval]   wrong={result['wrong']}/{result['questions']} "
            f"unique_failures={result['unique_failures']} "
            f"calls={result['vlm_calls']} failed_l2={result['failed_unique_l2']}",
            flush=True,
        )
        results.append(result)
    write_report(results, args.output_dir)
    print(f"[suite-eval] Results written to {args.output_dir}")


if __name__ == "__main__":
    main()
