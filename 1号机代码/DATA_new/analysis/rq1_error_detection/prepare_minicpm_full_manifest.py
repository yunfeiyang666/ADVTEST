"""Create and validate the frozen full RQ1 suite manifest for MiniCPM runs."""

import argparse
import hashlib
import json
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).absolute().parents[4]
SCRATCH = WORKSPACE_ROOT / "scratch"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def count_jsonl(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def suite_entries() -> list[dict]:
    expansion = SCRATCH / "rq1_seed_expansion" / "runs"
    l2_a = SCRATCH / "rq1_l2_family_formal_mplug_1000" / "suite_inputs"
    l2_b = SCRATCH / "rq1_l2_family_formal_mplug_1000_resume1" / "suite_inputs"
    choice = SCRATCH / "rq1_choice_suites_v3_formal" / "choice_suites"
    return [
        {"track": "strict_open", "family": "l0", "expected_questions": 1000,
         "path": expansion / "advtest-l0-l1-expanded-f308-q1000-v5-templatebalanced" / "results" / "advtest_l0_suite.jsonl"},
        {"track": "strict_open", "family": "l1", "expected_questions": 1000,
         "path": expansion / "advtest-l0-l1-expanded-f308-q1000-v5-templatebalanced" / "results" / "advtest_l1_suite.jsonl"},
        {"track": "strict_open", "family": "converge", "expected_questions": 1000,
         "path": l2_a / "advtest_l2_converge_suite.jsonl"},
        {"track": "strict_open", "family": "direction_chain", "expected_questions": 1000,
         "path": l2_a / "advtest_l2_direction_chain_suite.jsonl"},
        {"track": "strict_open", "family": "distance_chain", "expected_questions": 1000,
         "path": l2_b / "advtest_l2_distance_chain_suite.jsonl"},
        {"track": "strict_open", "family": "viewpoint_transfer", "expected_questions": 1000,
         "path": l2_b / "advtest_l2_viewpoint_transfer_suite.jsonl"},
        {"track": "choice", "family": "l0", "expected_questions": 1000,
         "path": choice / "advtest_l0_choice_suite.jsonl"},
        {"track": "choice", "family": "l1", "expected_questions": 1000,
         "path": choice / "advtest_l1_choice_suite.jsonl"},
        {"track": "choice", "family": "converge", "expected_questions": 973,
         "path": choice / "advtest_l2_converge_choice_suite.jsonl"},
        {"track": "choice", "family": "direction_chain", "expected_questions": 1000,
         "path": choice / "advtest_l2_direction_chain_choice_suite.jsonl"},
        {"track": "choice", "family": "distance_chain", "expected_questions": 1000,
         "path": choice / "advtest_l2_distance_chain_choice_suite.jsonl"},
        {"track": "choice", "family": "viewpoint_transfer", "expected_questions": 1000,
         "path": choice / "advtest_l2_viewpoint_transfer_choice_suite.jsonl"},
        {"track": "official", "family": "nuscenes_qa", "expected_questions": 3503,
         "path": expansion / "official-candidates-f308-q3503" / "results" / "official_qa_suite.jsonl"},
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    entries = []
    for entry in suite_entries():
        path = entry.pop("path")
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = count_jsonl(path)
        if actual != entry["expected_questions"]:
            raise ValueError(f"{path}: expected {entry['expected_questions']}, found {actual}")
        entries.append({**entry, "questions": actual, "sha256": sha256(path), "path": str(path)})

    payload = {
        "purpose": "Frozen full RQ1 MiniCPM evaluation: strict open, final choice, and official QA.",
        "question_total": sum(entry["questions"] for entry in entries),
        "suites": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "question_total": payload["question_total"], "suites": len(entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
