import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Iterable, Optional, Tuple

WORKSPACE_ROOT = Path(__file__).absolute().parents[4]
sys.path.insert(0, str(Path(__file__).parent))

import evaluator
from run_suite_evaluation import (
    DEFAULT_DATAROOT,
    get_scene_frame,
    make_evaluator,
    resolve_image_path,
)


DEFAULT_OUTPUT_DIR = (
    WORKSPACE_ROOT
    / "scratch"
    / "rq1_choice_suites_v3_formal"
    / "think_audit_pilot"
)


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def clean_choice_question(text: str) -> str:
    text = str(text or "").strip()
    if "\n\nChoose the best answer from the options below." in text:
        return text.split("\n\nChoose the best answer from the options below.", 1)[0].strip()
    return text


def source_question_text(row: dict) -> str:
    return str(
        row.get("source_question")
        or row.get("question")
        or row.get("prompt")
        or ""
    ).strip()


def option_lines(row: dict) -> str:
    choices = row.get("choices") or []
    return "\n".join(
        f"{choice.get('label')}. {choice.get('text')}" for choice in choices
    )


def choice_answer(row: dict) -> str:
    label = str(row.get("choice_answer_label") or "").strip()
    text = str(row.get("choice_answer_text") or row.get("answer") or "").strip()
    return f"{label}. {text}".strip(". ")


def prior_prediction(row: dict) -> str:
    return str(
        row.get("mapping_predicted")
        or row.get("predicted")
        or row.get("raw_model_output")
        or ""
    ).strip()


def build_think_prompt(row: dict) -> str:
    return (
        "Answer the visual multiple-choice question.\n"
        "You must output exactly four lines.\n"
        "Lines 1-3 must start with Think: and be short.\n"
        "Line 4 must start with Final answer: and include one option letter plus option text.\n"
        "Do not omit the final answer line.\n"
        "Format:\n"
        "Think: <what you see>\n"
        "Think: <how it matches an option>\n"
        "Think: <why the other close option is less likely, or say no close option>\n"
        "Final answer: <one option, for example A. yes>\n\n"
        f"Question:\n{clean_choice_question(source_question_text(row))}\n\n"
        "Options:\n"
        f"{option_lines(row)}"
    )


def build_reason_prompt(row: dict, selected_answer: str) -> str:
    return (
        "Look at the image, question, and answer options below.\n"
        "Do not solve the question again. Explain the visual clue for the selected answer.\n"
        "The explanation must mention the object(s), count, direction, or relation asked in the question.\n"
        "Do not give a generic scene description.\n"
        "Output exactly one short sentence, no more than 25 words.\n\n"
        f"Question:\n{clean_choice_question(source_question_text(row))}\n\n"
        "Options:\n"
        f"{option_lines(row)}\n\n"
        f"Selected answer: {selected_answer}\n"
    )


def parse_pred_and_think(output: str) -> Tuple[str, str]:
    text = str(output or "").strip()
    pred_match = re.search(r"(?im)^\s*(?:Pred|Answer|Final answer|Final)\s*:\s*(.+?)\s*$", text)
    think_matches = re.findall(r"(?im)^\s*(?:Think|Reason|Because|Evidence)\s*:\s*(.+?)\s*$", text)
    if pred_match:
        pred = pred_match.group(1).strip()
    else:
        first_line = text.splitlines()[0].strip() if text.splitlines() else ""
        pred = first_line if re.match(r"^\s*(?:option\s*)?[A-D](?:[\).:,\-\s]|$)", first_line, re.I) else ""
    slash_placeholder = re.match(r"(?i)^\s*A/B/C/D\.\s*([A-D])\s*$", pred)
    if slash_placeholder:
        pred = slash_placeholder.group(1).upper()
    think_lines = [match.strip() for match in think_matches if match.strip()]
    think = "\n".join(think_lines[:3])
    return pred, think


def normalize_raw_row(row: dict, method: str) -> dict:
    normalized = dict(row)
    normalized["method"] = str(row.get("method") or method)
    normalized["question"] = clean_choice_question(source_question_text(row))
    normalized["prompt"] = normalized["question"]
    if "answer" not in normalized:
        normalized["answer"] = row.get("choice_answer_text", "")
    return normalized


def collect_wrong_rows(paths: list[Path], per_file_limit: int) -> list[dict]:
    rows = []
    for path in paths:
        method = path.stem.replace("_raw_results", "").replace("_two_step_raw_results", "")
        count = 0
        for row in iter_jsonl(path):
            if row.get("is_correct") is True:
                continue
            if not row.get("choices"):
                continue
            rows.append(normalize_raw_row(row, method))
            count += 1
            if per_file_limit and count >= per_file_limit:
                break
    return rows


def evaluate_row(
    row: dict,
    vlm,
    mode: str,
    outputs_root: Path,
    dataroot: Path,
    image_cache_dir: Path,
    two_call_reason: bool = False,
) -> dict:
    question = dict(row)
    question["question"] = build_think_prompt(row)
    question["prompt"] = question["question"]
    question["max_new_tokens"] = 120
    image_path: Optional[Path] = None
    if mode != "MOCK":
        image_path = resolve_image_path(question, outputs_root, image_cache_dir, dataroot)
        if image_path is None:
            raise FileNotFoundError(
                f"A real mosaic is required for {mode}: {get_scene_frame(question)}"
            )
    start = time.perf_counter()
    if mode == "MOCK":
        raw_output, _ = vlm.evaluate(question)
    else:
        raw_output, _ = vlm.evaluate(question, image_path)
    elapsed = time.perf_counter() - start
    pred, think = parse_pred_and_think(raw_output)
    reason_raw_output = ""
    reason_elapsed = 0.0
    if two_call_reason:
        reason_question = dict(row)
        reason_question["question"] = build_reason_prompt(row, pred)
        reason_question["prompt"] = reason_question["question"]
        reason_start = time.perf_counter()
        if mode == "MOCK":
            reason_raw_output = "visual clue unavailable in mock mode"
        else:
            reason_raw_output, _ = vlm.evaluate(reason_question, image_path)
        reason_elapsed = time.perf_counter() - reason_start
        if not think:
            think = str(reason_raw_output or "").strip()
    return {
        "method": row.get("method", ""),
        "question_index": row.get("question_index", ""),
        "scene_frame": get_scene_frame(row),
        "family": row.get("family", ""),
        "think_case_group": row.get("think_case_group", ""),
        "think_case_sample": row.get("think_case_sample", ""),
        "source_question_id": row.get("source_question_id", ""),
        "question": clean_choice_question(source_question_text(row)),
        "choices": row.get("choices", []),
        "gt": choice_answer(row),
        "prior_pred": prior_prediction(row),
        "think_pred": pred,
        "think": think,
        "think_is_correct": evaluator.check_question_correctness(pred, row),
        "raw_think_output": raw_output,
        "raw_reason_output": reason_raw_output,
        "image_path": str(image_path) if image_path else str(row.get("image_path") or ""),
        "elapsed_seconds": elapsed,
        "reason_elapsed_seconds": reason_elapsed,
        "vlm_calls": 2 if two_call_reason else 1,
    }


def ensure_real_evaluator(mode: str, vlm) -> None:
    """Fail fast when a real VLM mode silently fell back to MOCK."""
    if mode == "MOCK":
        return
    if mode == "LOCAL_GPU" and getattr(vlm, "model", None) is None:
        raise RuntimeError("LOCAL_GPU model did not load; refusing to write MOCK think results.")
    if mode == "MINICPM" and getattr(vlm, "model", None) is None:
        raise RuntimeError("MINICPM model did not load; refusing to write MOCK think results.")
    if mode == "API" and getattr(vlm, "client", None) is None:
        raise RuntimeError("API client is unavailable; refusing to write MOCK think results.")


def write_outputs(rows: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "think_audit_raw_results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    csv_path = output_dir / "think_audit_summary.csv"
    fields = [
        "method",
        "question_index",
        "scene_frame",
        "family",
        "think_case_group",
        "think_case_sample",
        "source_question_id",
        "question",
        "gt",
        "prior_pred",
        "think_pred",
        "think",
        "think_is_correct",
        "vlm_calls",
        "image_path",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    lines = ["# Choice Think Audit Pilot", ""]
    lines.append(
        "| Case | Method | Family | QIdx | GT | Prior Pred | Think Pred | Correct | Think |"
    )
    lines.append("|---|---|---|---:|---|---|---|---:|---|")
    for row in rows:
        lines.append(
            "| {case} | {method} | {family} | {idx} | {gt} | {prior} | {pred} | {ok} | {think} |".format(
                case=str(row.get("think_case_group", "")).replace("|", "/"),
                method=row.get("method", ""),
                family=str(row.get("family", "")).replace("|", "/"),
                idx=row.get("question_index", ""),
                gt=str(row.get("gt", "")).replace("|", "/"),
                prior=str(row.get("prior_pred", "")).replace("|", "/"),
                pred=str(row.get("think_pred", "")).replace("|", "/"),
                ok=row.get("think_is_correct", False),
                think=str(row.get("think", "")).replace("|", "/"),
            )
        )
    (output_dir / "think_audit_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-ask wrong choice cases with concise Pred/Think output."
    )
    parser.add_argument("--raw-result", type=Path, action="append", required=True)
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
    parser.add_argument("--per-file-limit", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--two-call-reason",
        action="store_true",
        help="After the answer call, make a second VLM call asking for a short visual reason.",
    )
    args = parser.parse_args()

    selected = collect_wrong_rows(args.raw_result, args.per_file_limit)
    if args.limit:
        selected = selected[: args.limit]
    if not selected:
        raise ValueError("No wrong choice rows selected for think audit.")

    vlm = make_evaluator(args.mode)
    ensure_real_evaluator(args.mode, vlm)
    image_cache_dir = args.output_dir / "mosaics"
    results = []
    for index, row in enumerate(selected, start=1):
        print(
            f"[think-audit] {index}/{len(selected)} "
            f"{row.get('method')} qidx={row.get('question_index')}",
            flush=True,
        )
        results.append(
            evaluate_row(
                row,
                vlm,
                args.mode,
                args.outputs_root,
                args.dataroot,
                image_cache_dir,
                args.two_call_reason,
            )
        )
    write_outputs(results, args.output_dir)
    print(f"[think-audit] Results written to {args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
