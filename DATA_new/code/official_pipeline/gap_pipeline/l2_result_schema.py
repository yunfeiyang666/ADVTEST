"""Stable output schema checks for v7 generated QA records."""
from __future__ import annotations

from typing import Any, Dict, List

SCHEMA_VERSION = "v7_l2_generated_qa_v1"

REQUIRED_FIELDS = [
    "schema_version",
    "question_id",
    "scene_name",
    "frame_idx",
    "question",
    "answer",
    "answer_type",
    "l2_family",
    "path_pattern",
    "footprint_nodes",
    "coverage_footprint",
    "logic_verification",
    "l2_refactor",
]

COVERAGE_LEVELS = ["l0", "l1", "l2"]


def normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(record)
    out["schema_version"] = SCHEMA_VERSION
    out.setdefault("scene_name", "")
    out.setdefault("frame_idx", None)
    out.setdefault("topology_level", "L2")
    out.setdefault("selection_phase", "")
    out.setdefault("constraint_trace", [])
    out.setdefault("constraint_count", 0)
    out.setdefault("constraint_types", [])
    out.setdefault("candidate_before", 0)
    out.setdefault("candidate_after", 0)
    out.setdefault("generation_backend", "programmatic")
    out.setdefault("timestamp_start", "")
    out.setdefault("timestamp_end", "")
    out.setdefault("generation_elapsed_ms", 0)

    fp = out.setdefault("coverage_footprint", {})
    for level in COVERAGE_LEVELS:
        fp.setdefault(level, [])
    out["coverage_l0"] = list(fp.get("l0", []))
    out["coverage_l1"] = list(fp.get("l1", []))
    out["coverage_l2"] = list(fp.get("l2", []))
    return out


def validate_record(record: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing:{field}")
    if record.get("topology_level") != "L2":
        errors.append("topology_level_not_L2")
    fp = record.get("coverage_footprint")
    if not isinstance(fp, dict):
        errors.append("coverage_footprint_not_dict")
    else:
        for level in COVERAGE_LEVELS:
            if not isinstance(fp.get(level), list):
                errors.append(f"coverage_{level}_not_list")
    if not isinstance(record.get("footprint_nodes"), list):
        errors.append("footprint_nodes_not_list")
    if not record.get("question"):
        errors.append("empty_question")
    if record.get("logic_verification") not in {"NEO4J_EXECUTED", "NEO4J_AND_GEOMETRY_EXECUTED", "DRY_RUN_TRUSTED", "IN_MEMORY_VERIFIED"}:
        errors.append("logic_verification_not_executed")
    return errors


def normalize_and_validate(record: Dict[str, Any]) -> Dict[str, Any]:
    out = normalize_record(record)
    errors = validate_record(out)
    if errors:
        raise ValueError(f"Invalid v7 QA record {out.get('question_id')}: {errors}")
    return out

