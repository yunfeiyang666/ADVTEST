import argparse
import json
from pathlib import Path

from build_choice_suites import iter_jsonl


OLD_OPTION = "back (otherwise)"
NEW_OPTION = (
    "back (150 degrees < theta <= 180 degrees or "
    "-180 degrees <= theta <= -150 degrees)"
)
OLD_RULE = "back otherwise."
NEW_RULE = (
    "back if 150 degrees < theta <= 180 degrees or "
    "-180 degrees <= theta <= -150 degrees."
)


def convert_row(row: dict) -> dict:
    converted = dict(row)
    converted["question"] = str(row.get("question") or "").replace(
        OLD_OPTION, NEW_OPTION
    ).replace(OLD_RULE, NEW_RULE)
    converted["prompt"] = converted["question"]
    converted["choices"] = [dict(choice) for choice in row.get("choices") or []]
    for choice in converted["choices"]:
        if str(choice.get("canonical_text") or "").lower() == "back":
            choice["text"] = NEW_OPTION
    if str(row.get("answer") or "").lower() == "back":
        converted["choice_answer_text"] = NEW_OPTION
    converted["question_format"] = "multiple_choice_4_of_6_no_catchall"
    converted["choice_wording_variant"] = "explicit_back_angle_range"
    return converted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove the catch-all wording from the v7 back option."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = (
        args.output_dir
        / "advtest_l2_viewpoint_transfer_6way_no_catchall_choice_suite.jsonl"
    )
    rows = [convert_row(row) for row in iter_jsonl(args.source)]
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {
        "source": str(args.source.resolve()),
        "output": str(output_path.resolve()),
        "rows": len(rows),
        "changed_question_rows": sum(
            NEW_OPTION in row["question"] or NEW_RULE in row["question"] for row in rows
        ),
        "remaining_catchall_rows": sum(
            "otherwise" in row["question"].lower() for row in rows
        ),
    }
    (args.output_dir / "viewpoint_no_catchall_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
