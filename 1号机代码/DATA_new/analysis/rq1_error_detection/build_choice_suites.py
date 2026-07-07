import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


LABELS = ("A", "B", "C", "D")
DIRECTION_OPTIONS = (
    "front",
    "front left",
    "left",
    "back left",
    "back",
    "back right",
    "right",
    "front right",
)
STATUS_OPTIONS = ("moving", "parked", "stopped")
TYPE_OPTIONS = (
    "car",
    "truck",
    "bus",
    "pedestrian",
    "bicycle",
    "motorcycle",
    "traffic cone",
    "barrier",
    "trailer",
    "construction vehicle",
)
BOOLEAN_OPTIONS = ("yes", "no")

DIRECTION_DISTRACTORS = {
    "front": ("front left", "front right", "back"),
    "front left": ("front", "left", "back left"),
    "left": ("front left", "back left", "right"),
    "back left": ("back", "left", "back right"),
    "back": ("back left", "back right", "front"),
    "back right": ("back", "right", "back left"),
    "right": ("front right", "back right", "left"),
    "front right": ("front", "right", "back right"),
}


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            count += 1
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return count


def clean_answer(answer: object) -> str:
    if isinstance(answer, bool):
        text = "true" if answer else "false"
    else:
        text = str(answer if answer is not None else "").strip().lower()
    if text == "true":
        text = "yes"
    elif text == "false":
        text = "no"
    text = re.sub(r"\s+", " ", text)
    return text


def is_int_answer(answer: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", answer))


def family_key(row: dict) -> str:
    return str(row.get("family") or row.get("template_id") or "unknown")


def answer_pool_key(row: dict) -> str:
    answer = clean_answer(row.get("answer"))
    family = family_key(row)
    if answer in ("yes", "no"):
        return "boolean"
    if answer in DIRECTION_OPTIONS or "direction" in family:
        return "direction"
    if answer in STATUS_OPTIONS or "status" in family:
        return "status"
    if answer in TYPE_OPTIONS or "type" in family:
        return "type"
    if is_int_answer(answer) or "count" in family or "number" in family:
        return "count"
    return family


def collect_answer_pools(rows: list[dict]) -> dict[str, list[str]]:
    pools: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        answer = clean_answer(row.get("answer"))
        if answer:
            pools[answer_pool_key(row)].add(answer)
            pools["global"].add(answer)
    return {key: sorted(values) for key, values in pools.items()}


def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        clean = clean_answer(value)
        if clean and clean not in seen:
            seen.add(clean)
            output.append(clean)
    return output


def numeric_options(answer: str) -> list[str]:
    value = int(answer)
    candidates = [value, value - 1, value + 1, value + 2, value - 2, value + 3]
    return [str(item) for item in candidates if item >= 0]


def base_candidates(row: dict, pools: dict[str, list[str]]) -> list[str]:
    answer = clean_answer(row.get("answer"))
    pool_key = answer_pool_key(row)
    if pool_key == "direction":
        return [answer, *DIRECTION_DISTRACTORS.get(answer, ()), *DIRECTION_OPTIONS]
    if pool_key == "status":
        return [answer, *STATUS_OPTIONS]
    if pool_key == "type":
        return [answer, *TYPE_OPTIONS]
    if pool_key == "boolean":
        return [answer, *BOOLEAN_OPTIONS]
    if pool_key == "count" and is_int_answer(answer):
        return numeric_options(answer)
    return [answer, *pools.get(pool_key, []), *pools.get("global", [])]


def choose_options(row: dict, pools: dict[str, list[str]], rng: random.Random) -> list[str]:
    answer = clean_answer(row.get("answer"))
    if not answer:
        raise ValueError("Cannot build choices for a row with an empty answer")
    if answer in ("yes", "no"):
        return [answer, "no" if answer == "yes" else "yes"]

    candidates = dedupe_keep_order(base_candidates(row, pools))
    distractors = [item for item in candidates if item != answer]
    rng.shuffle(distractors)
    options = [answer, *distractors[:3]]
    if len(options) < 4:
        fillers = [item for item in pools.get("global", []) if item not in options]
        rng.shuffle(fillers)
        options.extend(fillers[: 4 - len(options)])
    if len(options) < 4:
        options.extend([f"none-{idx}" for idx in range(4 - len(options))])
    options = options[:4]
    rng.shuffle(options)
    return options


def direction_instruction() -> str:
    return (
        "Use the ego-vehicle coordinate convention. Direction labels are "
        "determined by the approximate bearing from the reference object to "
        "the target object: front is around 0 degrees, front left around 45, "
        "left around 90, back left around 135, back around 180, back right "
        "around -135, right around -90, and front right around -45."
    )


def build_choice_question_text(
    question: str, choices: list[dict], *, include_direction_instruction: bool = False
) -> str:
    option_lines = "\n".join(
        f"{item['label']}. {item['text']}" for item in choices
    )
    instruction = ""
    if include_direction_instruction:
        instruction = direction_instruction() + "\n"
    return (
        f"{question}\n\n"
        f"{instruction}"
        "Choose the best answer from the options below. "
        "Answer with the option letter and option text.\n"
        f"{option_lines}"
    )


def convert_row(row: dict, pools: dict[str, list[str]], rng: random.Random) -> dict:
    answer = clean_answer(row.get("answer"))
    option_texts = choose_options(row, pools, rng)
    choices = [
        {"label": label, "text": text}
        for label, text in zip(LABELS, option_texts)
    ]
    correct = next(item for item in choices if item["text"] == answer)

    converted = dict(row)
    converted["question"] = build_choice_question_text(
        str(row.get("question") or row.get("prompt") or ""),
        choices,
        include_direction_instruction=answer_pool_key(row) == "direction",
    )
    converted["prompt"] = converted["question"]
    converted["answer"] = answer
    converted["choices"] = choices
    converted["choice_answer_label"] = correct["label"]
    converted["choice_answer_text"] = correct["text"]
    converted["question_format"] = f"multiple_choice_{len(choices)}way"
    converted["source_question_format"] = "strict_open_qa"
    converted["source_question"] = row.get("question") or row.get("prompt") or ""
    return converted


def parse_source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Source must be NAME=PATH")
    name, path = value.split("=", 1)
    if not name:
        raise argparse.ArgumentTypeError("Source name cannot be empty")
    return name, Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build four-option multiple-choice RQ1 suites from frozen raw QA rows."
    )
    parser.add_argument("--source", action="append", type=parse_source, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260707)
    args = parser.parse_args()

    manifest = {
        "format": "multiple_choice_variable_by_answer_type",
        "seed": args.seed,
        "sources": {},
        "answer_banks": {
            "direction": list(DIRECTION_OPTIONS),
            "status": list(STATUS_OPTIONS),
            "type": list(TYPE_OPTIONS),
            "boolean": list(BOOLEAN_OPTIONS),
        },
    }

    for source_index, (name, path) in enumerate(args.source):
        rows = list(iter_jsonl(path))
        pools = collect_answer_pools(rows)
        rng = random.Random(f"{args.seed}:{name}:{source_index}")
        converted = []
        rejected = []
        for index, row in enumerate(rows, start=1):
            try:
                converted.append(convert_row(row, pools, rng))
            except ValueError as exc:
                rejected.append(
                    {
                        "index": index,
                        "reason": str(exc),
                        "question": row.get("question") or row.get("prompt") or "",
                        "answer": row.get("answer", ""),
                    }
                )
        output_path = args.output_dir / f"{name}_choice_suite.jsonl"
        count = write_jsonl(output_path, converted)
        rejected_path = args.output_dir / f"{name}_choice_rejected.jsonl"
        rejected_count = write_jsonl(rejected_path, rejected)
        family_counts = Counter(family_key(row) for row in converted)
        manifest["sources"][name] = {
            "input": str(path),
            "output": str(output_path),
            "rejected_output": str(rejected_path),
            "rows": count,
            "rejected_rows": rejected_count,
            "families": dict(sorted(family_counts.items())),
            "pool_sizes": {key: len(value) for key, value in pools.items()},
        }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "choice_suite_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
