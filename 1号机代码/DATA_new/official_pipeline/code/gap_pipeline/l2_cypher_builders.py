"""
Cypher builders for the L2 refactor side path.

These builders only create query strings + parameter dictionaries. They do not
execute Neo4j queries. New L2 code uses official direction fields only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

from gap_pipeline.l2_constraint_planner import L2Clause


DIR_FIELD = "direction_6"


def dir_expr(rel_alias: str) -> str:
    return (
        f"coalesce({rel_alias}.direction_6, {rel_alias}.direction_official, CASE "
        f"WHEN {rel_alias}.angle > -30 AND {rel_alias}.angle <= 30 THEN 'front' "
        f"WHEN {rel_alias}.angle > 30 AND {rel_alias}.angle <= 90 THEN 'front_left' "
        f"WHEN {rel_alias}.angle > -90 AND {rel_alias}.angle <= -30 THEN 'front_right' "
        f"WHEN {rel_alias}.angle > 90 AND {rel_alias}.angle <= 150 THEN 'back_left' "
        f"WHEN {rel_alias}.angle > -150 AND {rel_alias}.angle <= -90 THEN 'back_right' "
        f"ELSE 'back' END)"
    )



@dataclass(frozen=True)
class CypherQuery:
    cypher: str
    params: Dict[str, Any]


def _constraint_where_clauses(
    clauses: Iterable[L2Clause], target_alias: str = "x"
) -> Tuple[List[str], Dict[str, Any], List[str]]:
    """Translate ref_dir clauses to MATCH/WHERE snippets.

    dist_rank is intentionally not translated here; callers should verify ranks
    by ordered results or post-query filtering.
    """
    matches: List[str] = []
    wheres: List[str] = []
    params: Dict[str, Any] = {}
    ref_idx = 0
    for clause in clauses:
        if clause.kind != "ref_dir":
            continue
        ref_idx += 1
        ref_alias = f"ref{ref_idx}"
        rel_alias = f"r_ref{ref_idx}"
        matches.append(
            f"MATCH ({ref_alias}:Object {{unique_id:$ref_id_{ref_idx}}})-[{rel_alias}:RELATES_TO]->({target_alias})"
        )
        wheres.append(f"{dir_expr(rel_alias)} = $ref_dir_{ref_idx}")
        params[f"ref_id_{ref_idx}"] = clause.ref_id
        params[f"ref_dir_{ref_idx}"] = clause.value
    return matches, params, wheres


def fetch_pivot_neighbors(b_id: str) -> CypherQuery:
    """Fetch all neighbors around pivot b for diverge dry-run."""
    return CypherQuery(
        cypher=f"""
MATCH (b:Object {{unique_id:$b_id}})-[r:RELATES_TO]->(x:Object)
RETURN DISTINCT x.unique_id AS id,
       x.type AS type,
       x.status AS status,
       {dir_expr('r')} AS dir_official,
       r.distance AS actual_dist,
       x.translation_x AS tx,
       x.translation_y AS ty
""".strip(),
        params={"b_id": b_id},
    )


def fetch_converge_intersection(a_id: str, c_id: str) -> CypherQuery:
    """Fetch nodes x connected to both anchors a and c."""
    return CypherQuery(
        cypher=f"""
MATCH (a:Object {{unique_id:$a_id}})-[ra:RELATES_TO]->(x:Object)
MATCH (c:Object {{unique_id:$c_id}})-[rc:RELATES_TO]->(x)
RETURN DISTINCT x.unique_id AS id,
       x.type AS type,
       x.status AS status,
       {dir_expr('ra')} AS dir_from_a,
       {dir_expr('rc')} AS dir_from_c,
       x.translation_x AS tx,
       x.translation_y AS ty
""".strip(),
        params={"a_id": a_id, "c_id": c_id},
    )


def fetch_candidate_ref_directions(candidate_ids) -> CypherQuery:
    return CypherQuery(
        cypher=f"""
MATCH (ref:Object)-[rel:RELATES_TO]->(cand:Object)
WHERE cand.unique_id IN $candidate_ids AND NOT ref.unique_id IN $candidate_ids
RETURN ref.unique_id AS ref_id,
       ref.type AS ref_type,
       ref.status AS ref_status,
       ref.translation_x AS ref_tx,
       ref.translation_y AS ref_ty,
       cand.unique_id AS cand_id,
       {dir_expr('rel')} AS dir_official
""".strip(),
        params={"candidate_ids": list(candidate_ids)},
    )


def verify_converge(
    *,
    a_id: str,
    c_id: str,
    target_type: str,
    dir_from_a: str,
    dir_from_c: str,
    clauses: Iterable[L2Clause] = (),
) -> CypherQuery:
    matches, extra_params, wheres = _constraint_where_clauses(clauses, "x")
    where_lines = [
        "x.type = $target_type",
        f"{dir_expr('ra')} = $dir_from_a",
        f"{dir_expr('rc')} = $dir_from_c",
        *wheres,
    ]
    cypher = "\n".join([
        "MATCH (a:Object {unique_id:$a_id})-[ra:RELATES_TO]->(x:Object)",
        "MATCH (c:Object {unique_id:$c_id})-[rc:RELATES_TO]->(x)",
        *matches,
        "WHERE " + "\n  AND ".join(where_lines),
        "RETURN count(DISTINCT x) AS n, collect(DISTINCT x.unique_id) AS ids",
    ])
    params = {
        "a_id": a_id,
        "c_id": c_id,
        "target_type": target_type,
        "dir_from_a": dir_from_a,
        "dir_from_c": dir_from_c,
    }
    params.update(extra_params)
    return CypherQuery(cypher=cypher, params=params)


def verify_branch(
    *,
    b_id: str,
    branch_type: str,
    branch_dir: str,
    clauses: Iterable[L2Clause] = (),
) -> CypherQuery:
    matches, extra_params, wheres = _constraint_where_clauses(clauses, "x")
    where_lines = [
        "x.type = $branch_type",
        f"{dir_expr('r')} = $branch_dir",
        *wheres,
    ]
    cypher = "\n".join([
        "MATCH (b:Object {unique_id:$b_id})-[r:RELATES_TO]->(x:Object)",
        *matches,
        "WHERE " + "\n  AND ".join(where_lines),
        "RETURN count(DISTINCT x) AS n, collect(DISTINCT x.unique_id) AS ids",
    ])
    params = {"b_id": b_id, "branch_type": branch_type, "branch_dir": branch_dir}
    params.update(extra_params)
    return CypherQuery(cypher=cypher, params=params)


def verify_diverge_pair(
    *,
    b_id: str,
    a_id: str,
    c_id: str,
    a_type: str,
    c_type: str,
    dir_to_a: str,
    dir_to_c: str,
) -> CypherQuery:
    return CypherQuery(
        cypher=f"""
MATCH (b:Object {{unique_id:$b_id}})-[ra:RELATES_TO]->(a:Object {{unique_id:$a_id}})
MATCH (b)-[rc:RELATES_TO]->(c:Object {{unique_id:$c_id}})
WHERE a.type = $a_type
  AND c.type = $c_type
  AND {dir_expr('ra')} = $dir_to_a
  AND {dir_expr('rc')} = $dir_to_c
RETURN count(*) AS n,
       a.unique_id AS a_id,
       c.unique_id AS c_id,
       a.type AS a_type,
       c.type AS c_type,
       a.status AS a_status,
       c.status AS c_status,
       {dir_expr('ra')} AS dir_to_a,
       {dir_expr('rc')} AS dir_to_c
""".strip(),
        params={
            "b_id": b_id,
            "a_id": a_id,
            "c_id": c_id,
            "a_type": a_type,
            "c_type": c_type,
            "dir_to_a": dir_to_a,
            "dir_to_c": dir_to_c,
        },
    )



def verify_distance_chain(a_id: str, b_id: str, c_id: str) -> CypherQuery:
    return CypherQuery(
        cypher="""
MATCH (a:Object {unique_id:$a_id})-[rab:RELATES_TO]->(b:Object {unique_id:$b_id})
MATCH (b)-[rbc:RELATES_TO]->(c:Object {unique_id:$c_id})
RETURN rab.distance AS d_ab, rbc.distance AS d_bc
""".strip(),
        params={"a_id": a_id, "b_id": b_id, "c_id": c_id},
    )


def verify_direction_chain(a_id: str, b_id: str, c_id: str) -> CypherQuery:
    return CypherQuery(
        cypher=f"""
MATCH (a:Object {{unique_id:$a_id}})-[rab:RELATES_TO]->(b:Object {{unique_id:$b_id}})
MATCH (b)-[rbc:RELATES_TO]->(c:Object {{unique_id:$c_id}})
RETURN {dir_expr('rab')} AS dir_ab, {dir_expr('rbc')} AS dir_bc
""".strip(),
        params={"a_id": a_id, "b_id": b_id, "c_id": c_id},
    )

