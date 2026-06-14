import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

from experiment_protocol import EXTERNAL_LAYER, validate_question_boundary
from official_qa_experiment import (
    DEFAULT_QUESTIONS_PATH,
    index_official_questions,
    load_official_questions,
)
from qatest_adapted import normalize_text


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def official_answer_index(path: Path) -> dict:
    indexed = index_official_questions(load_official_questions(path))
    return {
        question["official_question_id"]: str(question.get("answer") or "")
        for questions in indexed.values()
        for question in questions
    }


def audit_suite(
    records: Iterable[Mapping],
    *,
    source_answers: Mapping[str, str],
) -> dict:
    records = list(records)
    normalized = [normalize_text(str(record.get("question") or "")) for record in records]
    answer_mismatches = 0
    boundary_violations = 0
    operator_counts = Counter()
    missing_sources = 0
    for record in records:
        source_id = str(record.get("source_question_id") or "")
        expected_answer = source_answers.get(source_id)
        if expected_answer is None:
            missing_sources += 1
        elif str(record.get("answer") or "") != expected_answer:
            answer_mismatches += 1
        try:
            validate_question_boundary(record, EXTERNAL_LAYER)
        except ValueError:
            boundary_violations += 1
        operator = str(record.get("mutation_operator") or "")
        if operator:
            operator_counts[operator] += 1
    return {
        "questions": len(records),
        "unique_normalized_questions": len(set(normalized)),
        "duplicate_questions": len(records) - len(set(normalized)),
        "source_question_count": len(
            {str(record.get("source_question_id") or "") for record in records}
        ),
        "sample_count": len(
            {str(record.get("source_sample_token") or "") for record in records}
        ),
        "frame_count": len(
            {str(record.get("scene_frame") or "") for record in records}
        ),
        "answer_mismatches": answer_mismatches,
        "missing_sources": missing_sources,
        "boundary_violations": boundary_violations,
        "operator_counts": dict(sorted(operator_counts.items())),
        "method_counts": dict(
            sorted(
                Counter(
                    str(record.get("experiment_method") or "")
                    for record in records
                ).items()
            )
        ),
        "adapter_counts": dict(
            sorted(
                Counter(
                    str(record.get("generation_adapter") or "")
                    for record in records
                ).items()
            )
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit generated QATest suites.")
    parser.add_argument(
        "--suite",
        type=Path,
        action="append",
        required=True,
        help="Path to a QATest JSONL suite. Repeat for multiple suites.",
    )
    parser.add_argument(
        "--questions-path",
        type=Path,
        default=DEFAULT_QUESTIONS_PATH,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    source_answers = official_answer_index(args.questions_path)
    payload = {
        path.stem.replace("_suite", ""): audit_suite(
            iter_jsonl(path),
            source_answers=source_answers,
        )
        for path in args.suite
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[qatest-audit] suites={len(payload)} output={args.output}")


if __name__ == "__main__":
    main()
