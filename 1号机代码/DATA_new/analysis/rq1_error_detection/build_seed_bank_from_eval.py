import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def row_key(row: dict) -> str:
    source_id = str(row.get("source_question_id") or "")
    if source_id:
        return f"source:{source_id}"
    scene_frame = str(row.get("scene_frame") or "")
    question = str(row.get("question") or row.get("prompt") or "")
    return f"text:{scene_frame}\0{question}"


def index_candidates(rows: Iterable[dict]) -> dict[str, dict]:
    indexed = {}
    duplicates = []
    for row in rows:
        key = row_key(row)
        if key in indexed:
            duplicates.append(key)
            continue
        indexed[key] = row
    if duplicates:
        preview = ", ".join(duplicates[:3])
        raise ValueError(f"candidate suite has duplicate seed keys: {preview}")
    return indexed


def is_correct(row: dict) -> bool:
    return row.get("is_correct") is True


def build_seed_bank(
    candidate_rows: Iterable[dict],
    eval_rows: Iterable[dict],
    *,
    strict: bool = True,
) -> tuple[list[dict], dict]:
    candidates = index_candidates(candidate_rows)
    seed_rows = []
    eval_count = 0
    correct_count = 0
    missing_candidate_keys = []
    frame_counts = Counter()
    mode_counts = Counter()

    for eval_row in eval_rows:
        eval_count += 1
        mode_counts[str(eval_row.get("mode") or "")] += 1
        if not is_correct(eval_row):
            continue
        correct_count += 1
        key = row_key(eval_row)
        candidate = candidates.get(key)
        if candidate is None:
            missing_candidate_keys.append(key)
            if strict:
                continue
            candidate = {
                "scene_frame": eval_row.get("scene_frame", ""),
                "question": eval_row.get("question", ""),
                "answer": eval_row.get("answer", ""),
                "question_source": eval_row.get("question_source", ""),
                "source_question_id": eval_row.get("source_question_id", ""),
            }

        seed_index = len(seed_rows) + 1
        seed_row = dict(candidate)
        seed_row.update(
            {
                "seed_id": f"seed_{seed_index:05d}",
                "seed_source": "official_nuscenes_qa_correct_on_vlm",
                "seed_filter_mode": eval_row.get("mode", ""),
                "seed_filter_question_index": eval_row.get("question_index"),
                "seed_filter_predicted": eval_row.get("predicted", ""),
                "seed_filter_raw_model_output": eval_row.get(
                    "raw_model_output", ""
                ),
                "seed_filter_inference_elapsed_seconds": eval_row.get(
                    "inference_elapsed_seconds"
                ),
                "seed_filter_image_path": eval_row.get("image_path", ""),
                "seed_filter_is_correct": True,
            }
        )
        seed_rows.append(seed_row)
        frame_counts[str(seed_row.get("scene_frame") or "")] += 1

    if strict and missing_candidate_keys:
        preview = ", ".join(missing_candidate_keys[:3])
        raise ValueError(f"eval rows missing from candidate suite: {preview}")

    summary = {
        "candidate_rows": len(candidates),
        "eval_rows": eval_count,
        "correct_eval_rows": correct_count,
        "seed_rows": len(seed_rows),
        "incorrect_or_rejected_eval_rows": eval_count - correct_count,
        "missing_candidate_rows": len(missing_candidate_keys),
        "mode_counts": dict(mode_counts),
        "visited_frames": len(frame_counts),
        "seed_rows_by_frame": dict(sorted(frame_counts.items())),
    }
    return seed_rows, summary


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a unified seed bank from VLM-correct official QA rows."
    )
    parser.add_argument("--candidate-suite", required=True, type=Path)
    parser.add_argument("--eval-raw-results", required=True, type=Path)
    parser.add_argument("--output-jsonl", required=True, type=Path)
    parser.add_argument("--summary-json", required=True, type=Path)
    parser.add_argument(
        "--allow-missing-candidates",
        action="store_true",
        help="Keep VLM-correct eval rows even when the original suite row is absent.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    seeds, summary = build_seed_bank(
        iter_jsonl(args.candidate_suite),
        iter_jsonl(args.eval_raw_results),
        strict=not args.allow_missing_candidates,
    )
    summary.update(
        {
            "candidate_suite": str(args.candidate_suite),
            "eval_raw_results": str(args.eval_raw_results),
            "output_jsonl": str(args.output_jsonl),
        }
    )
    write_jsonl(args.output_jsonl, seeds)
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"[seed-bank] seeds={summary['seed_rows']} "
        f"eval_rows={summary['eval_rows']} output={args.output_jsonl}"
    )


if __name__ == "__main__":
    main()
