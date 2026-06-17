import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from selectors_qaasker import (
    HAS_QAASKER,
    S2I,
    change,
    coordinate_question_for_qaasker,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SEED_BANK = (
    WORKSPACE_ROOT
    / "scratch"
    / "rq1_group_minimal"
    / "runs"
    / "seed-filter-mplug-f30-q454-v5"
    / "results"
    / "correct_seed_bank.jsonl"
)
DEFAULT_OUTPUT_DIR = (
    WORKSPACE_ROOT
    / "scratch"
    / "rq1_group_minimal"
    / "runs"
    / "qaasker-seed-failure-audit"
    / "results"
)


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def seed_source_id(seed: Mapping) -> str:
    return str(seed.get("source_question_id") or seed.get("official_question_id") or "")


def short_vlm_answer(seed: Mapping) -> str:
    answer = str(seed.get("seed_filter_predicted") or "").strip()
    return answer or str(seed.get("answer") or "").strip()


def question_family(question: str) -> str:
    text = question.strip().lower()
    if text.startswith("there is"):
        return "there_is"
    if text.startswith("are there") or text.startswith("are any"):
        return "existential"
    if text.startswith("is there"):
        return "is_there"
    if text.startswith("does ") or text.startswith("do "):
        return "comparison_yes_no"
    if text.startswith("is "):
        return "is_yes_no"
    if text.startswith("what "):
        return "what"
    if text.startswith("which "):
        return "which"
    if text.startswith("who "):
        return "who"
    if text.startswith("where "):
        return "where"
    if text.startswith("when "):
        return "when"
    if text.startswith("how "):
        return "how"
    return "other"


def answer_kind(answer: str) -> str:
    text = answer.strip().lower()
    if text in {"yes", "no", "true", "false"}:
        return "boolean"
    if len(text.split()) > 3:
        return "long_phrase"
    if text in {"car", "truck", "bus", "pedestrian", "bicycle", "motorcycle"}:
        return "object_class"
    if text in {"moving", "parked", "standing", "stopped", "with rider", "without rider"}:
        return "status"
    return "short_phrase"


def normalize_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def run_pipeline(question: str, answer: str, *, coordinated: bool) -> dict:
    input_question = coordinate_question_for_qaasker(question) if coordinated else question
    try:
        statement = change(input_question, answer)
    except Exception as exc:
        return {
            "ok": False,
            "stage": "q2s_exception",
            "error": normalize_error(exc),
            "input_question": input_question,
        }
    if not statement or str(statement) == "None":
        return {
            "ok": False,
            "stage": "q2s_none",
            "error": "Q2S returned None",
            "input_question": input_question,
        }
    try:
        followup = S2I(statement)
    except Exception as exc:
        return {
            "ok": False,
            "stage": "s2g_exception",
            "error": normalize_error(exc),
            "input_question": input_question,
            "statement": str(statement),
        }
    if not followup or str(followup) == "None":
        return {
            "ok": False,
            "stage": "s2g_none",
            "error": "S2G returned None",
            "input_question": input_question,
            "statement": str(statement),
        }
    return {
        "ok": True,
        "stage": "ok",
        "input_question": input_question,
        "statement": str(statement),
        "followup": str(followup),
        "target_answer": "yes",
    }


def audit(seeds: Sequence[Mapping]) -> dict:
    if not HAS_QAASKER:
        raise RuntimeError("Original QAAskeR Q2S/S2G modules are unavailable")
    modes = {
        "raw_gold": {"coordinated": False, "answer": "gold"},
        "coordinated_gold": {"coordinated": True, "answer": "gold"},
        "raw_vlm": {"coordinated": False, "answer": "vlm"},
        "coordinated_vlm": {"coordinated": True, "answer": "vlm"},
    }
    rows = []
    for seed_index, seed in enumerate(seeds, start=1):
        question = str(seed.get("question") or "")
        gold = str(seed.get("answer") or "")
        vlm = short_vlm_answer(seed)
        for mode, config in modes.items():
            answer = gold if config["answer"] == "gold" else vlm
            result = run_pipeline(
                question,
                answer,
                coordinated=bool(config["coordinated"]),
            )
            rows.append(
                {
                    "mode": mode,
                    "seed_index": seed_index,
                    "seed_id": seed.get("seed_id", ""),
                    "source_question_id": seed_source_id(seed),
                    "scene_frame": seed.get("scene_frame", ""),
                    "template_type": seed.get("template_type", ""),
                    "question_family": question_family(question),
                    "answer_kind": answer_kind(answer),
                    "question": question,
                    "answer": answer,
                    **result,
                }
            )
    return {
        "rows": rows,
        "summary": summarize(rows),
    }


def summarize(rows: Sequence[Mapping]) -> dict:
    by_mode = {}
    for mode in sorted({row["mode"] for row in rows}):
        subset = [row for row in rows if row["mode"] == mode]
        ok = [row for row in subset if row["ok"]]
        failed = [row for row in subset if not row["ok"]]
        by_mode[mode] = {
            "attempted": len(subset),
            "ok": len(ok),
            "failed": len(failed),
            "success_rate": len(ok) / len(subset) if subset else 0.0,
            "failure_stage_counts": dict(Counter(row["stage"] for row in failed)),
            "failure_by_question_family": dict(
                Counter(row["question_family"] for row in failed)
            ),
            "failure_by_template_type": dict(
                Counter(str(row.get("template_type") or "unknown") for row in failed)
            ),
            "failure_by_answer_kind": dict(
                Counter(row["answer_kind"] for row in failed)
            ),
        }
    return {"by_mode": by_mode}


def choose_examples(rows: Sequence[Mapping], mode: str, limit: int) -> list[dict]:
    failures = [row for row in rows if row["mode"] == mode and not row["ok"]]
    grouped = defaultdict(list)
    for row in failures:
        grouped[(row["stage"], row["question_family"], row["answer_kind"])].append(row)
    examples = []
    for key in sorted(grouped, key=lambda item: len(grouped[item]), reverse=True):
        examples.append(grouped[key][0])
        if len(examples) >= limit:
            break
    return examples


def write_jsonl(path: Path, rows: Iterable[Mapping]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_report(output_dir: Path, summary: Mapping, examples: Sequence[Mapping]) -> None:
    lines = [
        "# QAAskeR Seed Failure Audit",
        "",
        "## What Was Checked",
        "",
        "- Core QAAskeR calls: original `Q2S.change()` and `S2G.S2I()`.",
        "- Compared raw original question input vs the existing NuScenes coordination shim.",
        "- Compared gold short answers vs stored VLM primary answers.",
        "- A failure here means no executable follow-up question was produced; it is not a VLM answer error.",
        "",
        "## Summary",
        "",
        "| Mode | Attempted | OK | Failed | Success Rate | Main Failure Stages |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for mode, stats in summary["by_mode"].items():
        stages = ", ".join(
            f"{key}={value}"
            for key, value in stats["failure_stage_counts"].items()
        )
        lines.append(
            f"| {mode} | {stats['attempted']} | {stats['ok']} | "
            f"{stats['failed']} | {stats['success_rate']:.3f} | {stages} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "QAAskeR is a rule-based metamorphic consistency method. It expects common text-QA wh-question patterns that can be transformed into a declarative sentence, then into a yes/no follow-up question.",
            "",
            "NuScenes-QA contains many spatial relation, comparison, existential, and status questions. These often do not match QAAskeR's expected templates, so the original Q2S stage returns `None` before any VLM follow-up test can run.",
            "",
            "If raw input performs worse than coordinated input, the failure is not caused by the coordination shim; the shim is only helping the original parser handle a few NuScenes-specific forms.",
            "",
            "## Representative Failures",
            "",
        ]
    )
    for example in examples:
        lines.extend(
            [
                f"### {example['mode']} / {example['stage']} / {example['question_family']}",
                "",
                f"- Source: `{example['source_question_id']}`",
                f"- Scene frame: `{example['scene_frame']}`",
                f"- Template: `{example.get('template_type', '')}`",
                f"- Question: {example['question']}",
                f"- Answer used: {example['answer']}",
                f"- Input to Q2S: {example.get('input_question', '')}",
                f"- Error: {example.get('error', '')}",
                "",
            ]
        )
        if example.get("statement"):
            lines.append(f"- Statement: {example['statement']}")
            lines.append("")
    (output_dir / "qaasker_seed_failure_audit.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit why original QAAskeR fails to build follow-ups from seeds."
    )
    parser.add_argument("--seed-bank", type=Path, default=DEFAULT_SEED_BANK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--example-limit", type=int, default=12)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    seeds = list(iter_jsonl(args.seed_bank))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = audit(seeds)
    rows = result["rows"]
    summary = result["summary"]
    (args.output_dir / "qaasker_seed_failure_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_jsonl(args.output_dir / "qaasker_seed_failure_rows.jsonl", rows)
    examples = choose_examples(rows, "coordinated_gold", args.example_limit)
    write_jsonl(args.output_dir / "qaasker_seed_failure_examples.jsonl", examples)
    write_report(args.output_dir, summary, examples)
    stats = summary["by_mode"]["coordinated_gold"]
    print(
        "[qaasker-audit] coordinated_gold "
        f"ok={stats['ok']}/{stats['attempted']} "
        f"success_rate={stats['success_rate']:.3f} -> {args.output_dir}"
    )


if __name__ == "__main__":
    main()
