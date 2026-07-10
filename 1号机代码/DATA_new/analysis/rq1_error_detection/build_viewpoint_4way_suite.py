import argparse
import json
import random
from collections import Counter
from pathlib import Path

from build_choice_suites import (
    iter_jsonl,
    viewpoint_choice_question,
    viewpoint_relative_angle,
)


LABELS = ("A", "B", "C", "D")
DIRECTIONS = ("front", "left", "back", "right")
DIRECTION_RANGES = {
    "front": "-45 <= theta < 45 degrees",
    "left": "45 <= theta < 135 degrees",
    "back": "theta >= 135 degrees or theta < -135 degrees",
    "right": "-135 <= theta < -45 degrees",
}


def discretize_direction_4way(angle_deg: float) -> str:
    angle = ((float(angle_deg) + 180.0) % 360.0) - 180.0
    if -45.0 <= angle < 45.0:
        return "front"
    if 45.0 <= angle < 135.0:
        return "left"
    if angle >= 135.0 or angle < -135.0:
        return "back"
    return "right"


def build_question(row: dict, choices: list[dict]) -> str:
    option_lines = "\n".join(
        f"{choice['label']}. {choice['text']}" for choice in choices
    )
    return (
        f"{viewpoint_choice_question(row)}\n\n"
        "Use four broad directions. Theta is measured from the ray that starts "
        "at the first named object and points toward the object it is facing; "
        "that ray is 0 degrees. Positive theta turns left. "
        "front: -45 <= theta < 45 degrees; "
        "left: 45 <= theta < 135 degrees; "
        "back: theta >= 135 degrees or theta < -135 degrees; "
        "right: -135 <= theta < -45 degrees.\n"
        "Choose the best answer. Answer with the option letter and option text.\n"
        f"{option_lines}"
    )


def convert_row(row: dict, outputs_root: Path, rng: random.Random) -> dict:
    angle = viewpoint_relative_angle(row, outputs_root)
    if angle is None:
        raise ValueError("Cannot recover the viewpoint-transfer relative angle")
    answer = discretize_direction_4way(angle)
    option_names = list(DIRECTIONS)
    rng.shuffle(option_names)
    choices = [
        {
            "label": label,
            "text": f"{direction} ({DIRECTION_RANGES[direction]})",
            "canonical_text": direction,
        }
        for label, direction in zip(LABELS, option_names)
    ]
    correct = next(choice for choice in choices if choice["canonical_text"] == answer)
    converted = dict(row)
    converted.update(
        {
            "question": build_question(row, choices),
            "prompt": build_question(row, choices),
            "answer": answer,
            "choices": choices,
            "choice_answer_label": correct["label"],
            "choice_answer_text": correct["text"],
            "choice_answer_canonical_text": answer,
            "question_format": "multiple_choice_4way",
            "source_question_format": "strict_open_qa_left_right",
            "source_question": str(row.get("question") or row.get("prompt") or ""),
            "viewpoint_relative_angle_degrees": angle,
            "choice_answer_resolution": "viewpoint_transfer_4way_90_degree_bins",
        }
    )
    return converted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a true four-direction viewpoint-transfer suite."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--outputs-root", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260710)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    suite_path = args.output_dir / "advtest_l2_viewpoint_transfer_4way_choice_suite.jsonl"
    manifest_path = args.output_dir / "viewpoint_4way_suite_manifest.json"
    rng = random.Random(args.seed)
    rows = []
    answer_counts = Counter()
    answer_label_counts = Counter()
    for row in iter_jsonl(args.source):
        converted = convert_row(row, args.outputs_root, rng)
        rows.append(converted)
        answer_counts[converted["answer"]] += 1
        answer_label_counts[converted["choice_answer_label"]] += 1

    with suite_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest = {
        "source": str(args.source.resolve()),
        "output": str(suite_path.resolve()),
        "outputs_root": str(args.outputs_root.resolve()),
        "seed": args.seed,
        "rows": len(rows),
        "direction_bins": DIRECTION_RANGES,
        "answer_counts": dict(answer_counts),
        "answer_label_counts": dict(answer_label_counts),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
