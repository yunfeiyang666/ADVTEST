"""Post-process coverage calculator for v7 generated QA CSV.

Reads the generated QA CSV (sorted by question_id), computes incremental
coverage delta/cumulative/rate columns, and writes an enriched CSV.

Can be used as:
  - A standalone script:  python -m gap_pipeline.postprocess_coverage --qa qa.csv --gaps summary.json
  - A library function called at the end of run_gap_pipeline_v7.py
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Set


def _parse_json_list(value: Any) -> List[str]:
    """Parse a JSON-encoded list or return as-is if already a list."""
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def postprocess_coverage(
    qa_csv: Path,
    total_l2_count: int,
    output_csv: Path | None = None,
    *,
    total_l0_count: int = 0,
    total_l1_count: int = 0,
    initial_coverage: Dict[str, Any] | None = None,
    graph_stats: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compute incremental coverage and append delta/cum/rate columns.

    Args:
        qa_csv: Path to the generated QA CSV (must have coverage_l0/l1/l2 columns).
        total_l2_count: Total number of L2 gaps in the universe (denominator for rate).
        output_csv: Where to write the enriched CSV. If None, overwrites qa_csv.
        total_l0_count: Total L0 count (for rate, optional; 0 = skip rate).
        total_l1_count: Total L1 count (for rate, optional; 0 = skip rate).
        initial_coverage: Dict with 'l0','l1','l2' counts for row-0 baseline.
        graph_stats: Dict with 'raw_nodes','raw_edges','filtered_nodes','filtered_edges'.

    Returns:
        Summary dict with final coverage stats.
    """
    if output_csv is None:
        output_csv = qa_csv

    # Read all rows
    rows: List[Dict[str, Any]] = []
    with qa_csv.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        original_fieldnames = list(reader.fieldnames or [])
        for row in reader:
            rows.append(dict(row))

    if not rows:
        return {"records": 0, "coverage": {"l0": 0, "l1": 0, "l2": 0}}

    # Seed initial coverage (from initial QA analysis) as baseline
    init = initial_coverage or {}
    init_l0 = int(init.get("l0", 0))
    init_l1 = int(init.get("l1", 0))
    init_l2 = int(init.get("l2", 0))

    # Compute incremental coverage
    seen_l0: Set[str] = set()
    seen_l1: Set[str] = set()
    seen_l2: Set[str] = set()

    # Insert row 0: initial coverage baseline (before any generated questions)
    row0: Dict[str, Any] = {k: "" for k in original_fieldnames}
    row0["question_id"] = "0"
    row0["question"] = "[initial coverage baseline]"
    row0["answer"] = ""
    row0["answer_type"] = ""
    row0["l2_family"] = ""
    row0["delta_l0"] = init_l0
    row0["delta_l1"] = init_l1
    row0["delta_l2"] = init_l2
    row0["cum_l0"] = init_l0
    row0["cum_l1"] = init_l1
    row0["cum_l2"] = init_l2
    row0["total_covered_l2"] = 0
    row0["coverage_rate_l0"] = round(init_l0 / max(total_l0_count, 1), 6) if total_l0_count else 0
    row0["coverage_rate_l1"] = round(init_l1 / max(total_l1_count, 1), 6) if total_l1_count else 0
    row0["coverage_rate_l2"] = round(init_l2 / max(total_l2_count, 1), 6)

    for row in rows:
        l0 = set(_parse_json_list(row.get("coverage_l0", "[]")))
        l1 = set(_parse_json_list(row.get("coverage_l1", "[]")))
        l2 = set(_parse_json_list(row.get("coverage_l2", "[]")))

        new_l0 = l0 - seen_l0
        new_l1 = l1 - seen_l1
        new_l2 = l2 - seen_l2

        seen_l0.update(l0)
        seen_l1.update(l1)
        seen_l2.update(l2)

        row["delta_l0"] = len(new_l0)
        row["delta_l1"] = len(new_l1)
        row["delta_l2"] = len(new_l2)
        row["cum_l0"] = len(seen_l0)
        row["cum_l1"] = len(seen_l1)
        row["cum_l2"] = len(seen_l2)
        row["total_covered_l2"] = len(l2)   # total L2 gaps this question covers
        row["coverage_rate_l0"] = round(len(seen_l0) / max(total_l0_count, 1), 6) if total_l0_count else 0
        row["coverage_rate_l1"] = round(len(seen_l1) / max(total_l1_count, 1), 6) if total_l1_count else 0
        row["coverage_rate_l2"] = round(len(seen_l2) / max(total_l2_count, 1), 6)

    # Prepend row 0
    rows.insert(0, row0)

    # Determine output fieldnames: original + new columns (avoid duplicates)
    postprocess_cols = ["delta_l0", "delta_l1", "delta_l2",
                        "cum_l0", "cum_l1", "cum_l2",
                        "total_covered_l2",
                        "coverage_rate_l0", "coverage_rate_l1", "coverage_rate_l2"]
    out_fieldnames = list(original_fieldnames)
    for col in postprocess_cols:
        if col not in out_fieldnames:
            out_fieldnames.append(col)

    # Write enriched CSV (main table)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Write metadata sheet (graph stats + initial coverage)
    meta_csv = output_csv.parent / (output_csv.stem + "_meta.csv")
    gs = graph_stats or {}
    meta_rows = [
        {"key": "raw_nodes", "value": gs.get("raw_nodes", "")},
        {"key": "raw_edges", "value": gs.get("raw_edges", "")},
        {"key": "filtered_nodes", "value": gs.get("filtered_nodes", "")},
        {"key": "filtered_edges", "value": gs.get("filtered_edges", "")},
        {"key": "total_l2_gaps", "value": total_l2_count},
        {"key": "total_l0_objects", "value": total_l0_count},
        {"key": "total_l1_pairs", "value": total_l1_count},
        {"key": "initial_coverage_l0", "value": init_l0},
        {"key": "initial_coverage_l1", "value": init_l1},
        {"key": "initial_coverage_l2", "value": init_l2},
        {"key": "generated_questions", "value": len(rows) - 1},
        {"key": "final_coverage_l2", "value": len(seen_l2)},
    ]
    with meta_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["key", "value"])
        writer.writeheader()
        writer.writerows(meta_rows)

    return {
        "records": len(rows) - 1,  # exclude row 0
        "total_l2_count": total_l2_count,
        "coverage": {
            "l0": len(seen_l0),
            "l1": len(seen_l1),
            "l2": len(seen_l2),
        },
        "coverage_rate_l2": round(len(seen_l2) / max(total_l2_count, 1), 6),
        "output_csv": str(output_csv),
        "meta_csv": str(meta_csv),
    }


def postprocess_from_summary(qa_csv: Path, summary_json: Path, output_csv: Path | None = None) -> Dict[str, Any]:
    """Convenience: read total_gap_count from summary.json and run postprocess."""
    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    total_l2 = int(summary.get("total_gap_count") or summary.get("pool_size") or 0)
    cov = summary.get("coverage") or {}
    total_l0 = int(cov.get("l0") or 0)
    total_l1 = int(cov.get("l1") or 0)
    return postprocess_coverage(
        qa_csv, total_l2, output_csv,
        total_l0_count=total_l0, total_l1_count=total_l1,
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Post-process QA CSV with incremental coverage")
    p.add_argument("--qa", required=True, help="Path to generated QA CSV")
    p.add_argument("--gaps", required=True, help="Path to summary.json (for total_gap_count)")
    p.add_argument("--output", default="", help="Output CSV path (default: overwrite input)")
    args = p.parse_args()

    qa_csv = Path(args.qa)
    summary_json = Path(args.gaps)
    output_csv = Path(args.output) if args.output else None

    result = postprocess_from_summary(qa_csv, summary_json, output_csv)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
