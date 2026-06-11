"""
Candidate builders for the L2 refactor side path.

This module is pure Python and does not query Neo4j. It normalizes candidate
rows and builds candidate subsets for converge/diverge template dry-runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

def _get(row: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for k in keys:
        v = row.get(k)
        if v is not None and v != "":
            return v
    return default


def normalize_candidate(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize old/new candidate shapes to the official-direction schema."""
    return {
        "id": str(_get(row, "id", "unique_id", "node_id", default="")),
        "type": str(_get(row, "type", "tgt_type", "node_type", default="")),
        "status": str(_get(row, "status", "tgt_status", default="")),
        "dir_official": str(_get(row, "dir_official", "direction_official", default="")),
        "actual_dist": _get(row, "actual_dist", "distance", default=None),
        "tx": _get(row, "tx", "x", default=None),
        "ty": _get(row, "ty", "y", default=None),
        "raw": row,
    }


@dataclass(frozen=True)
class BranchCandidates:
    target: Dict[str, Any]
    candidates: List[Dict[str, Any]]
    branch_type: str
    branch_dir: str


@dataclass(frozen=True)
class DivergeCandidates:
    a_branch: BranchCandidates
    c_branch: BranchCandidates


def v6_endpoint_candidates_from_ctx(ctx: Dict[str, Any], endpoint: str = "n3") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Normalize old V6 context for one pivot-neighbor endpoint.

    endpoint currently supports n3/c-side because old fallback returns n3 plus
    sibling_* arrays around n2. Future Neo4j builders can call normalize_candidate
    directly for a-side as well.
    """
    if endpoint != "n3":
        raise ValueError("v6_endpoint_candidates_from_ctx currently supports endpoint='n3' only")

    target = normalize_candidate({
        "id": ctx.get("n3_id"),
        "type": ctx.get("n3_type"),
        "status": ctx.get("n3_status"),
        "dir_official": ctx.get("r2_dir_official") or ctx.get("r2_direction_official"),
        "actual_dist": ctx.get("r2_actual_dist"),
        "tx": ctx.get("n3_tx"),
        "ty": ctx.get("n3_ty"),
    })

    ids = ctx.get("sibling_ids", []) or []
    types = ctx.get("sibling_types", []) or []
    statuses = ctx.get("sibling_statuses", []) or []
    dirs = ctx.get("sibling_dir_officials", []) or ctx.get("sibling_direction_officials", []) or []
    dists = ctx.get("sibling_actual_dists", []) or ctx.get("sibling_dists", []) or []
    txs = ctx.get("sibling_txs", []) or []
    tys = ctx.get("sibling_tys", []) or []

    siblings: List[Dict[str, Any]] = []
    for i, sid in enumerate(ids):
        if not sid:
            continue
        siblings.append(normalize_candidate({
            "id": sid,
            "type": types[i] if i < len(types) else "",
            "status": statuses[i] if i < len(statuses) else "",
            "dir_official": dirs[i] if i < len(dirs) else "",
            "actual_dist": dists[i] if i < len(dists) else None,
            "tx": txs[i] if i < len(txs) else None,
            "ty": tys[i] if i < len(tys) else None,
        }))
    return [target] + siblings, target


def filter_by_type_dir(
    candidates: Sequence[Dict[str, Any]],
    *,
    target_type: str,
    target_dir: str,
) -> List[Dict[str, Any]]:
    """Filter normalized candidates by type and official direction."""
    out: List[Dict[str, Any]] = []
    target_dir = str(target_dir or "").replace(" ", "-")
    for c in candidates:
        row = normalize_candidate(c)
        if target_type and row["type"] != target_type:
            continue
        if target_dir and row["dir_official"] != target_dir:
            continue
        out.append(row)
    return out


def build_branch_candidates(
    neighbors: Sequence[Dict[str, Any]],
    target: Dict[str, Any],
    *,
    branch_type: str,
    branch_dir: str,
) -> BranchCandidates:
    """Build one diverge branch candidate set from pivot-neighbor rows."""
    norm_target = normalize_candidate(target)
    rows = filter_by_type_dir(neighbors, target_type=branch_type, target_dir=branch_dir)
    if norm_target["id"] and norm_target["id"] not in {r["id"] for r in rows}:
        rows = [norm_target] + rows
    return BranchCandidates(norm_target, rows, branch_type, branch_dir)


def build_diverge_candidates(
    neighbors: Sequence[Dict[str, Any]],
    a_target: Dict[str, Any],
    c_target: Dict[str, Any],
    *,
    a_type: str,
    a_dir: str,
    c_type: str,
    c_dir: str,
) -> DivergeCandidates:
    return DivergeCandidates(
        a_branch=build_branch_candidates(neighbors, a_target, branch_type=a_type, branch_dir=a_dir),
        c_branch=build_branch_candidates(neighbors, c_target, branch_type=c_type, branch_dir=c_dir),
    )


def build_converge_candidates(
    rows: Sequence[Dict[str, Any]],
    *,
    target_type: str,
    dir_from_a: str,
    dir_from_c: str,
) -> List[Dict[str, Any]]:
    """
    Build converge candidate set from precomputed intersection rows.

    Expected row fields include type plus dir_from_a/dir_from_c or equivalent.
    """
    out: List[Dict[str, Any]] = []
    da = str(dir_from_a or "").replace(" ", "-")
    dc = str(dir_from_c or "").replace(" ", "-")
    for row in rows:
        n = normalize_candidate(row)
        row_da = str(_get(row, "dir_from_a", "a_dir", default="")).replace(" ", "-")
        row_dc = str(_get(row, "dir_from_c", "c_dir", default="")).replace(" ", "-")
        if target_type and n["type"] != target_type:
            continue
        if da and row_da != da:
            continue
        if dc and row_dc != dc:
            continue
        out.append(n)
    return out

