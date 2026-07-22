"""Freeze the genuinely distinct QAAskeR successes without hiding raw output."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    raw_rows = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    kept = []
    seen = set()
    duplicate_rows = 0
    for row in raw_rows:
        key = (
            str(row.get("scene_frame") or ""),
            str(row.get("question") or "").strip().lower(),
            str(row.get("answer") or "").strip().lower(),
        )
        if key in seen:
            duplicate_rows += 1
            continue
        seen.add(key)
        kept.append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept),
        encoding="utf-8",
    )
    summary = {
        "method": "qaasker_original",
        "raw_success_rows": len(raw_rows),
        "unique_success_rows": len(kept),
        "duplicate_rows_removed": duplicate_rows,
        "duplicate_rate": duplicate_rows / len(raw_rows) if raw_rows else 0.0,
        "dedupe_key": "scene_frame + followup_question + answer",
        "question_text_unique": len({str(row.get("question") or "").strip().lower() for row in kept}),
        "note": "Raw successes are preserved separately; evaluation should use this unique suite.",
    }
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
