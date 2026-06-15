import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

import evaluator
from run_suite_evaluation import failure_signature


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def rescore_raw(path: Path) -> dict:
    rows = list(iter_jsonl(path))
    correct = 0
    wrong = 0
    vlm_calls = 0
    changed_correct_to_wrong = 0
    changed_wrong_to_correct = 0
    unique_failure_keys = set()
    failed_unique_l2 = set()
    failure_families = Counter()
    changed_rows = []

    for index, row in enumerate(rows, start=1):
        predicted = str(
            row.get("raw_model_output")
            if row.get("raw_model_output") is not None
            else row.get("predicted") or ""
        )
        rescored_correct = evaluator.check_correctness(
            predicted,
            row.get("answer"),
        )
        old_correct = bool(row.get("is_correct"))
        call_cost = int(row.get("vlm_call_cost") or 1)
        vlm_calls += call_cost

        if rescored_correct:
            correct += 1
        else:
            wrong += 1
            question = {
                "question_source": row.get("question_source", ""),
                "source_question_id": row.get("source_question_id", ""),
                "scene_frame": row.get("scene_frame", ""),
                "l2_family": row.get("family", ""),
                "answer": row.get("answer", ""),
                "coverage_l2_items": row.get("l2_items") or [],
            }
            unique_failure_keys.add(failure_signature(question, predicted))
            failed_unique_l2.update(
                str(item) for item in question["coverage_l2_items"]
            )
            failure_families[str(row.get("family") or "unknown")] += 1

        if old_correct and not rescored_correct:
            changed_correct_to_wrong += 1
        elif not old_correct and rescored_correct:
            changed_wrong_to_correct += 1
        else:
            continue
        changed_rows.append(
            {
                "question_index": index,
                "scene_frame": row.get("scene_frame", ""),
                "question": row.get("question", ""),
                "answer": row.get("answer", ""),
                "raw_model_output": predicted,
                "old_is_correct": old_correct,
                "rescored_is_correct": rescored_correct,
            }
        )

    unique_failures = len(unique_failure_keys)
    return {
        "raw_path": str(path),
        "method": path.name.replace("_suite_raw_results.jsonl", ""),
        "questions": len(rows),
        "vlm_calls": vlm_calls,
        "correct": correct,
        "wrong": wrong,
        "failure_rate": wrong / len(rows) if rows else 0.0,
        "unique_failures": unique_failures,
        "failed_unique_l2": len(failed_unique_l2),
        "unique_failures_per_100_calls": (
            unique_failures / vlm_calls * 100 if vlm_calls else 0.0
        ),
        "calls_per_unique_failure": (
            vlm_calls / unique_failures if unique_failures else None
        ),
        "duplicate_failure_rate": (
            (wrong - unique_failures) / wrong if wrong else 0.0
        ),
        "failure_category_count": len(failure_families),
        "top_failure_families": failure_families.most_common(10),
        "changed_correct_to_wrong": changed_correct_to_wrong,
        "changed_wrong_to_correct": changed_wrong_to_correct,
        "changed_rows": changed_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rescore frozen raw VLM outputs with the current evaluator."
    )
    parser.add_argument("--raw", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = {
        "scoring": "token_boundary_v2",
        "results": [rescore_raw(path) for path in args.raw],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"[rescore] files={len(payload['results'])} output={args.output}"
    )


if __name__ == "__main__":
    main()
