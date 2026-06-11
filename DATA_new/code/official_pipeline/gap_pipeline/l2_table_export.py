"""CSV table export with stable column order for v7 records.

Column design principles:
  - CSV stores human-readable / analysis-friendly columns only.
  - Large JSON blobs (verify_result, verify_payload, constraint_trace,
    raw_llm_output) are kept in the JSONL sidecar, NOT in CSV.
  - Coverage delta/cumulative columns are filled by the post-process step
    (postprocess_coverage.py), not during generation.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


# ── Core QA columns (generation phase) ──────────────────────────────────────

QA_COLUMNS: List[str] = [
    # ── identifiers
    "question_id",
    "scene_name",
    "frame_idx",
    # ── question & answer
    "question",
    "answer",
    "answer_type",
    "l2_family",
    "selection_phase",
    # ── gap & topology
    "path_pattern",
    "footprint_nodes",
    "external_refs",
    # ── difficulty / constraint
    "constraint_count",
    "verify_cypher",
    "candidate_before",
    "candidate_after",
    "difficulty_score",
    # ── coverage footprint (raw lists for this question)
    "coverage_l0",
    "coverage_l1",
    "coverage_l2",
    # ── timing (ISO timestamps, ms precision)
    "pipeline_ts_start",
    "pipeline_ts_precompute_done",
    "pipeline_ts_plan_cache_done",
    "timestamp_start",
    "timestamp_end",
    "generation_elapsed_ms",
    "verify_elapsed_ms",
]

# ── Post-process columns (appended by postprocess_coverage.py) ──────────────
# These are NOT written during generation; they are filled later.

POSTPROCESS_COLUMNS: List[str] = [
    "delta_l0",
    "delta_l1",
    "delta_l2",
    "cum_l0",
    "cum_l1",
    "cum_l2",
    "total_covered_l2",
    "coverage_rate_l0",
    "coverage_rate_l1",
    "coverage_rate_l2",
]

# Full column set including post-process (used when reading back)
QA_COLUMNS_FULL: List[str] = QA_COLUMNS + POSTPROCESS_COLUMNS


SUMMARY_COLUMNS: List[str] = [
    "run_id",
    "scene_id",
    "frame_id",
    "timestamp_start",
    "timestamp_end",
    "elapsed_ms",
    # ── pipeline stage timing breakdown
    "precompute_ms",
    "plan_cache_ms",
    "selection_gen_ms",
    "neo4j_verify_ms",
    "pre_verify_filtered",
    "pre_verify_total",
    # ── counts
    "generated",
    "tried_candidate_count",
    "pool_source",
    "pool_size",
    "total_gap_count",
    "covered_gap_count",
    "uncovered_gap_count",
    "failed_candidate_count",
    "coverage_l0",
    "coverage_l1",
    "coverage_l2",
    "families_json",
    "verification_json",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cell(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def extract_external_refs(record: Dict[str, Any]) -> List[str]:
    """Extract IDs of reference objects introduced outside the A-B-C gap."""
    footprint_nodes = set(str(x) for x in (record.get("footprint_nodes") or []))
    ref_ids: List[str] = []
    for clause in (record.get("constraint_types_detail") or record.get("clauses") or []):
        if isinstance(clause, dict):
            rid = str(clause.get("ref_id") or "")
            if rid and rid not in footprint_nodes:
                ref_ids.append(rid)
    # Fallback: parse from coverage footprint L0 minus footprint_nodes
    fp = record.get("coverage_footprint") or {}
    for node in fp.get("l0", []):
        node_str = str(node)
        if node_str not in footprint_nodes and node_str not in ref_ids:
            ref_ids.append(node_str)
    return sorted(set(ref_ids))


def compute_difficulty_score(record: Dict[str, Any]) -> int:
    """Compute a rough difficulty score from constraint and candidate metrics."""
    cb = int(record.get("candidate_before") or 0)
    cc = int(record.get("constraint_count") or 0)
    ext = len(record.get("external_refs") or [])
    return cb * max(cc, 1) + ext * 2


def _flatten_verify_cypher(record: Dict[str, Any]) -> str:
    """Extract a single cypher string from verify_payload for the CSV."""
    vp = record.get("verify_payload") or {}
    if isinstance(vp, str):
        return vp
    if "cypher" in vp:
        return str(vp["cypher"])
    branches = vp.get("branches") or []
    if branches:
        parts = [str(b.get("cypher", "")) for b in branches if isinstance(b, dict)]
        return " || ".join(parts)
    return ""


def enrich_record_for_csv(record: Dict[str, Any]) -> Dict[str, Any]:
    """Add derived CSV-only fields to a record before writing."""
    out = dict(record)
    if "external_refs" not in out:
        out["external_refs"] = extract_external_refs(out)
    if "difficulty_score" not in out:
        out["difficulty_score"] = compute_difficulty_score(out)
    if "verify_elapsed_ms" not in out:
        audit = out.get("verify_audit") or []
        out["verify_elapsed_ms"] = sum(int(a.get("elapsed_ms", 0)) for a in audit) if audit else 0
    if "verify_cypher" not in out:
        out["verify_cypher"] = _flatten_verify_cypher(out)
    return out


# ── Writers ──────────────────────────────────────────────────────────────────

def write_qa_csv(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=QA_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            enriched = enrich_record_for_csv(record)
            writer.writerow({col: _cell(enriched.get(col, "")) for col in QA_COLUMNS})


def append_qa_csv(path: Path, record: Dict[str, Any], *, write_header: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=QA_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        enriched = enrich_record_for_csv(record)
        writer.writerow({col: _cell(enriched.get(col, "")) for col in QA_COLUMNS})


def write_summary_csv(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({col: _cell(row.get(col, "")) for col in SUMMARY_COLUMNS})

