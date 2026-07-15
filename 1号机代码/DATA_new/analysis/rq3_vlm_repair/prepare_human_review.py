import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

from data_ops import (
    family_name,
    file_sha256,
    iter_jsonl,
    read_json,
    row_scene_frame,
    row_source_id,
    write_json,
)


def load_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".jsonl":
        return list(iter_jsonl(path))
    value = read_json(path)
    if not isinstance(value, list):
        raise ValueError("Review source must be a JSON list or JSONL records")
    return value


def stratified_sample(rows: list[dict], count: int, seed: int) -> list[dict]:
    if count <= 0 or count > len(rows):
        raise ValueError(f"Review count must be in [1, {len(rows)}]")
    grouped = defaultdict(list)
    for row in rows:
        grouped[family_name(row)].append(row)
    rng = random.Random(seed)
    for values in grouped.values():
        rng.shuffle(values)
    selected = []
    families = sorted(grouped)
    while len(selected) < count:
        added = False
        for family in families:
            if grouped[family]:
                selected.append(grouped[family].pop())
                added = True
                if len(selected) == count:
                    break
        if not added:
            break
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare an unfilled, stratified RQ3 human-review sheet."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260715)
    args = parser.parse_args()

    selected = stratified_sample(load_rows(args.source), args.count, args.seed)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    columns = (
        "review_index",
        "source_question_id",
        "scene_frame",
        "family",
        "question",
        "gt_answer",
        "image_path",
        "human_valid",
        "human_gt_correct",
        "human_notes",
    )
    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for index, row in enumerate(selected, start=1):
            writer.writerow(
                {
                    "review_index": index,
                    "source_question_id": row_source_id(row),
                    "scene_frame": row_scene_frame(row),
                    "family": family_name(row),
                    "question": row.get("question", ""),
                    "gt_answer": row.get("answer", ""),
                    "image_path": row.get("image_path", ""),
                    "human_valid": "",
                    "human_gt_correct": "",
                    "human_notes": "",
                }
            )
    write_json(
        args.output_manifest,
        {
            "schema_version": "rq3_human_review_sample_v1",
            "source": str(args.source.resolve()),
            "source_sha256": file_sha256(args.source),
            "output_csv": str(args.output_csv.resolve()),
            "output_sha256": file_sha256(args.output_csv),
            "rows": len(selected),
            "seed": args.seed,
            "labels_completed": False,
        },
    )


if __name__ == "__main__":
    main()
