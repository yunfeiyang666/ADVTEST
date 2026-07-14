#!/usr/bin/env python3
"""Compute coverage added by generated questions beyond a filtered seed bank."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


LEVELS = ("l0", "l1", "l2")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def namespaced_footprint(row: dict[str, Any], frame: str) -> dict[str, set[str]]:
    footprint = row.get("coverage_footprint") or {}
    return {
        level: {f"{frame}::{item}" for item in footprint.get(level, [])}
        for level in LEVELS
    }


def merge(target: dict[str, set[str]], source: dict[str, Iterable[str]]) -> None:
    for level in LEVELS:
        target[level].update(source[level])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-bank", type=Path, required=True)
    parser.add_argument("--generated-suite", type=Path, required=True)
    parser.add_argument("--outputs-root", type=Path, required=True)
    parser.add_argument("--fixed-budget-summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    seed_rows = read_jsonl(args.seed_bank)
    generated_rows = read_jsonl(args.generated_suite)

    seeds_by_frame: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in seed_rows:
        seeds_by_frame[row["scene_frame"]].append(row)

    seed_coverage = {level: set() for level in LEVELS}
    unmatched: list[dict[str, str]] = []
    matched = 0

    for frame, frame_seeds in seeds_by_frame.items():
        source_path = (
            args.outputs_root
            / frame
            / "offline"
            / "initial_coverage"
            / f"{frame}_initial_coverage.jsonl"
        )
        source_rows = read_jsonl(source_path) if source_path.exists() else []
        index: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in source_rows:
            key = (
                normalized(row.get("sample_token")),
                normalized(row.get("question")),
                normalized(row.get("answer")),
            )
            index[key].append(row)

        for seed in frame_seeds:
            key = (
                normalized(seed.get("sample_token") or seed.get("source_sample_token")),
                normalized(seed.get("question")),
                normalized(seed.get("answer")),
            )
            matches = index.get(key, [])
            if not matches:
                unmatched.append({
                    "scene_frame": frame,
                    "question": str(seed.get("question", "")),
                    "answer": str(seed.get("answer", "")),
                })
                continue
            merge(seed_coverage, namespaced_footprint(matches[0], frame))
            matched += 1

    generated_coverage = {level: set() for level in LEVELS}
    generated_frames: set[str] = set()
    for row in generated_rows:
        frame = row["scene_frame"]
        generated_frames.add(frame)
        merge(generated_coverage, namespaced_footprint(row, frame))

    totals: dict[str, int | None] = {level: None for level in LEVELS}
    frame_pool: list[str] = []
    if args.fixed_budget_summary and args.fixed_budget_summary.exists():
        summary = json.loads(args.fixed_budget_summary.read_text(encoding="utf-8"))
        frame_pool = list(summary.get("frame_pool") or [])

    if frame_pool:
        computed_totals = {level: 0 for level in LEVELS}
        for frame in frame_pool:
            summary_path = args.outputs_root / frame / "reports" / f"{frame}_summary.json"
            frame_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            neo4j = (frame_summary.get("universe_stats") or {}).get("neo4j") or {}
            computed_totals["l0"] += int(neo4j.get("object_count") or 0)
            computed_totals["l1"] += int(neo4j.get("relationship_count") or 0) // 2
            computed_totals["l2"] += int(frame_summary.get("total_gap_count") or 0)
        totals = computed_totals

    levels: dict[str, dict[str, Any]] = {}
    for level in LEVELS:
        added = generated_coverage[level] - seed_coverage[level]
        final = seed_coverage[level] | generated_coverage[level]
        denominator = totals[level]
        levels[level] = {
            "universe_total": denominator,
            "seed_covered": len(seed_coverage[level]),
            "generated_suite_covered": len(generated_coverage[level]),
            "overlap_with_seed": len(generated_coverage[level] & seed_coverage[level]),
            "newly_covered": len(added),
            "final_covered": len(final),
            "seed_rate": len(seed_coverage[level]) / denominator if denominator else None,
            "new_rate": len(added) / denominator if denominator else None,
            "final_rate": len(final) / denominator if denominator else None,
        }

    result = {
        "seed_rows": len(seed_rows),
        "seed_rows_matched": matched,
        "seed_rows_unmatched": len(unmatched),
        "seed_frames": len(seeds_by_frame),
        "generated_rows": len(generated_rows),
        "generated_frames": len(generated_frames),
        "frame_pool_size": len(frame_pool),
        "levels": levels,
        "unmatched_examples": unmatched[:20],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
