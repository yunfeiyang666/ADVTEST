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
    return set(map(str, footprint.get("l2") or []))



def resolve_image_path(
    question: dict, outputs_root: Path, image_cache_dir: Path, dataroot: Path
) -> Optional[Path]:
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


def make_evaluator(mode: str):
    if mode == "MOCK":
        return evaluator.MockVLMEvaluator()
    if mode == "LOCAL_GPU":
        return evaluator.LocalGPUEvaluator()
    if mode == "MPLUG":
        return evaluator.MPLUGEvaluator()
    if mode == "MINICPM":
        return evaluator.MiniCPMOEvaluator()
    if mode == "API":
        return evaluator.APIEvaluator()
    raise ValueError(f"Unknown mode: {mode}")


def evaluate_question(
    vlm, question: dict, mode: str, image_path: Optional[Path]
) -> Tuple[str, bool]:
    if mode == "MOCK":
        return vlm.evaluate(question)
    if image_path is None:
        return evaluator.MockVLMEvaluator().evaluate(question)
    return vlm.evaluate(question, image_path)


def evaluate_suite(
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
    correct = 0
    wrong = 0
    unique_l2 = set()
    failed_l2 = set()
    frames = Counter()
    failure_by_family = Counter()
    failure_rows = []
    cache: Dict[Tuple[str, str], Tuple[str, bool, Optional[str]]] = {}
    raw_path = output_dir / f"{path.stem}_raw_results.jsonl"
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
            unique_l2.update(question_l2)
            q_text = str(question.get("question", ""))
            cache_key = (scene_frame, q_text)
            if cache_key in cache:
                predicted, is_correct, image_path_text = cache[cache_key]
            else:
                image_path = resolve_image_path(
                    question, outputs_root, image_cache_dir, dataroot
                )
                image_path_text = str(image_path) if image_path else None
                predicted, is_correct = evaluate_question(vlm, question, mode, image_path)
                cache[cache_key] = (predicted, is_correct, image_path_text)
            family = str(question.get("l2_family") or question.get("template_id") or "unknown")
            if raw_handle is not None:
                raw_handle.write(
                    json.dumps(
                        {
                            "method": path.name.replace("_suite.jsonl", ""),
                            "question_index": total,
                            "scene_frame": scene_frame,
                            "question_id": question.get("question_id", ""),
                            "family": family,
                            "question": q_text,
                            "answer": question.get("answer", ""),
                            "predicted": predicted,
                            "is_correct": is_correct,
                            "image_path": image_path_text,
                            "l2_items": sorted(question_l2),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            if is_correct:
                correct += 1
                continue
            wrong += 1
            failed_l2.update(question_l2)
            failure_by_family[family] += 1
            if len(failure_rows) < 200:
                failure_rows.append(
                    {
                        "scene_frame": scene_frame,
                        "question_id": question.get("question_id", ""),
                        "family": family,
                        "question": q_text,
                        "answer": question.get("answer", ""),
                        "predicted": predicted,
                        "image_path": image_path_text,
                        "l2_items": sorted(question_l2),
                    }
                )
    finally:
        if raw_handle is not None:
            raw_handle.close()

    elapsed = time.time() - start
    return {
        "suite": path.name,
        "method": path.name.replace("_suite.jsonl", ""),
        "mode": mode,
        "limit": limit or None,
        "questions": total,
        "correct": correct,
        "wrong": wrong,
        "failure_rate": wrong / total if total else 0.0,
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
                "wrong",
                "failure_rate",
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

    md_lines = ["# Suite Evaluation Smoke Report", ""]
    md_lines.append("| Method | Q | Wrong | Fail Rate | Failed L2 | Failed L2/Q | Frames |")
    md_lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for result in results:
        md_lines.append(
            f"| {result['method']} | {result['questions']} | {result['wrong']} | "
            f"{result['failure_rate']:.3f} | {result['failed_unique_l2']} | "
            f"{result['failed_l2_per_question']:.3f} | {result['visited_frames']} |"
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
    parser.add_argument("--methods", nargs="*", default=None)
    parser.add_argument(
        "--no-raw", action="store_true", help="Do not write raw per-question JSONL results."
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Optional per-suite question cap for smoke runs."
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
    vlm = make_evaluator(args.mode)
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
            write_raw=not args.no_raw,
        )
        print(
            f"[suite-eval]   wrong={result['wrong']}/{result['questions']} "
            f"failed_l2={result['failed_unique_l2']}",
            flush=True,
        )
        results.append(result)
    write_report(results, args.output_dir)
    print(f"[suite-eval] Results written to {args.output_dir}")


if __name__ == "__main__":
    main()

