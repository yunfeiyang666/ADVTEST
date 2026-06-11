"""Utilities to translate IR QueryPlan into Cypher.

This module assumes the QueryPlan / ObjectExpr schema defined in the IR generation prompt:
- question_type in {status, exist, count, count_same_status, comparison, object}
- ObjectExpr has fields: type, status, alias, constraints, relations[]
- relations is a list of {direction, ref:ObjectExpr}

Special handling:
- type="trailer" is converted to category-based query: WHERE n.category CONTAINS 'trailer'
- type="truck" excludes trailer: WHERE n.type='truck' AND NOT n.category CONTAINS 'trailer'

We intentionally only use discrete properties: type, status, category and RELATES_TO.predicates[0].
"""
from typing import Dict, Any, List, Set, Tuple


def _next_var(base: str, used: Set[str]) -> str:
    i = 1
    while True:
        cand = f"{base}{i}"
        if cand not in used:
            used.add(cand)
            return cand
        i += 1


def _object_match(obj: Dict[str, Any], var: str) -> Tuple[str, List[str]]:
    """Generate a MATCH pattern for a single ObjectExpr node (without relations).

    返回：(MATCH语句, [额外WHERE条件列表])
    
    约束策略：
    - type == "thing" 视为通配符，不加类型过滤；
    - type == "trailer" 特殊处理：使用 category CONTAINS 'trailer'
    - type == "truck" 排除trailer：type='truck' AND NOT category CONTAINS 'trailer'
    - 其它类型按 type 过滤；
    - 如果有明确的 status，也一并加到匹配条件中。
    """
    obj_type = obj.get("type")
    status = obj.get("status")
    
    # 特殊处理 trailer：使用 category 字段
    if obj_type == "trailer":
        match_stmt = f"MATCH ({var}:Object)"
        where_clauses = [f"{var}.category CONTAINS 'trailer'"]
        if status and status not in {"unknown", ""}:
            where_clauses.append(f"{var}.status = '{status}'")
        return match_stmt, where_clauses
    
    # 特殊处理 truck：排除 trailer
    if obj_type == "truck":
        props = ["type:'truck'"]
        if status and status not in {"unknown", ""}:
            props.append(f"status:'{status}'")
        props_str = ", ".join(props)
        match_stmt = f"MATCH ({var}:Object {{{props_str}}})"
        where_clauses = [f"NOT {var}.category CONTAINS 'trailer'"]
        return match_stmt, where_clauses
    
    # 普通类型
    props = []
    if obj_type and obj_type != "thing":
        props.append(f"type:'{obj_type}'")
    if status and status not in {"unknown", ""}:
        props.append(f"status:'{status}'")
    props_str = ", ".join(props)
    if props_str:
        return f"MATCH ({var}:Object {{{props_str}}})", []
    else:
        return f"MATCH ({var}:Object)", []


def _append_relations(target_var: str,
                       target_obj: Dict[str, Any],
                       used: Set[str],
                       lines: List[str],
                       where_clauses: List[str]) -> None:
    """Expand relations of the target object into MATCH/WHERE clauses.

    For each relation in target_obj['relations'], we:
      - MATCH the ref object with its own properties
      - MATCH a RELATES_TO edge from ref to target
      - Constrain predicates[0] to the given direction
    """
    for rel in target_obj.get("relations", []) or []:
        direction = rel["direction"]
        ref_obj = rel["ref"]
        # normalize direction label to match stored schema (use exact labels)
        db_direction = str(direction).replace("_", "-")
        # choose variable name for ref
        ref_alias = ref_obj.get("alias") or _next_var(ref_obj["type"][0], used)
        # MATCH ref node (now returns tuple)
        match_stmt, extra_wheres = _object_match(ref_obj, ref_alias)
        lines.append(match_stmt)
        where_clauses.extend(extra_wheres)
        # MATCH relation
        edge_var = f"r_{ref_alias}_{target_var}"
        lines.append(f"MATCH ({ref_alias})-[{edge_var}:RELATES_TO]->({target_var})")
        where_clauses.append(f"{edge_var}.predicates[0] = '{db_direction}'")


def cypher_from_query_plan(plan: Dict[str, Any]) -> str:
    """Translate a single QueryPlan dict into a Cypher query string.

    This does NOT attempt to be fully general - it only covers the patterns
    present in the NuScenes official QA templates (status/object/count/exist/comparison/count_same_status).
    """
    qtype = plan["question_type"]
    if qtype == "comparison":
        return _cypher_for_comparison(plan["comparison"])

    # Handle count_same_status specially
    if qtype == "count_same_status":
        target = plan.get("target")
        reference = plan.get("reference")
        if target is None or reference is None:
            raise ValueError("count_same_status QueryPlan must have 'target' and 'reference' fields")
        return _cypher_for_count_same_status(target, reference)
    
    # Handle self-referential exist queries (e.g., "trailer in front of trailer")
    if qtype == "exist_self_reference":
        target = plan.get("target")
        if target is None:
            raise ValueError("exist_self_reference QueryPlan must have 'target' field")
        return _cypher_for_exist_self_reference(target)
    
    # Handle "another X with same status" queries
    if qtype == "exist_another_same_status":
        target = plan.get("target")
        reference = plan.get("reference")
        if target is None or reference is None:
            raise ValueError("exist_another_same_status QueryPlan must have 'target' and 'reference' fields")
        return _cypher_for_exist_another_same_status(target, reference)
    
    # Handle "cars with same status as truck" queries  
    if qtype == "exist_different_type_same_status":
        target = plan.get("target")
        reference = plan.get("reference")
        if target is None or reference is None:
            raise ValueError("exist_different_type_same_status QueryPlan must have 'target' and 'reference' fields")
        return _cypher_for_exist_different_type_same_status(target, reference)

    target = plan.get("target")
    if target is None:
        raise ValueError("Non-comparison QueryPlan must have a 'target' field")

    if qtype == "status":
        return _cypher_for_status(target)
    if qtype == "object":
        return _cypher_for_object(target)
    if qtype == "count":
        return _cypher_for_count(target)
    if qtype == "exist":
        return _cypher_for_exist(target)

    raise ValueError(f"Unsupported question_type in QueryPlan: {qtype}")


def _build_where_clause(where_clauses: List[str]) -> str:
    """Build WHERE clause from list of conditions."""
    if not where_clauses:
        return ""
    return "WHERE " + " AND ".join(where_clauses)


def _cypher_for_status(target: Dict[str, Any]) -> str:
    used: Set[str] = set()
    var = target.get("alias") or _next_var(target["type"][0], used)
    lines: List[str] = []
    where_clauses: List[str] = []

    match_stmt, extra_wheres = _object_match(target, var)
    lines.append(match_stmt)
    where_clauses.extend(extra_wheres)
    _append_relations(var, target, used, lines, where_clauses)

    if where_clauses:
        lines.append(_build_where_clause(where_clauses))
    lines.append(f"RETURN {var}.status AS status LIMIT 1")
    return "\n".join(lines)


def _cypher_for_object(target: Dict[str, Any]) -> str:
    used: Set[str] = set()
    var = target.get("alias") or _next_var("o", used)
    lines: List[str] = []
    where_clauses: List[str] = []

    match_stmt, extra_wheres = _object_match(target, var)
    lines.append(match_stmt)
    where_clauses.extend(extra_wheres)
    _append_relations(var, target, used, lines, where_clauses)

    if where_clauses:
        lines.append(_build_where_clause(where_clauses))
    lines.append(f"RETURN {var}.type AS type LIMIT 1")
    return "\n".join(lines)


def _cypher_for_count(target: Dict[str, Any]) -> str:
    used: Set[str] = set()
    var = target.get("alias") or _next_var("o", used)
    lines: List[str] = []
    where_clauses: List[str] = []

    match_stmt, extra_wheres = _object_match(target, var)
    lines.append(match_stmt)
    where_clauses.extend(extra_wheres)
    _append_relations(var, target, used, lines, where_clauses)

    if where_clauses:
        lines.append(_build_where_clause(where_clauses))
    lines.append(f"RETURN count({var}) AS count")
    return "\n".join(lines)


def _cypher_for_exist(target: Dict[str, Any]) -> str:
    used: Set[str] = set()
    var = target.get("alias") or _next_var("o", used)
    lines: List[str] = []
    where_clauses: List[str] = []

    match_stmt, extra_wheres = _object_match(target, var)
    lines.append(match_stmt)
    where_clauses.extend(extra_wheres)
    _append_relations(var, target, used, lines, where_clauses)

    if where_clauses:
        lines.append(_build_where_clause(where_clauses))
    lines.append(f"RETURN count({var}) > 0 AS exists")
    return "\n".join(lines)


def _cypher_for_count_same_status(target: Dict[str, Any], reference: Dict[str, Any]) -> str:
    """Count other objects with the same status as the reference object.
    
    Example: "What number of other things are there of the same status as the trailer?"
    - reference = trailer
    - target = thing (all objects)
    - We count objects with same status as trailer, excluding the trailer itself
    """
    used: Set[str] = set()
    ref_var = reference.get("alias") or _next_var("ref", used)
    target_var = target.get("alias") or _next_var("obj", used)
    
    lines: List[str] = []
    
    # First, match the reference object and get its status
    ref_match, ref_wheres = _object_match(reference, ref_var)
    lines.append(ref_match)
    if ref_wheres:
        lines.append(_build_where_clause(ref_wheres))
    lines.append(f"WITH {ref_var}.status AS ref_status, {ref_var}.unique_id AS ref_id")
    lines.append("LIMIT 1")  # Ensure we only use one reference object
    
    # Then, match all objects with the same status, excluding the reference
    target_match, target_wheres = _object_match(target, target_var)
    lines.append(target_match)
    
    # Build WHERE clause: same status AND not the reference object
    final_wheres = target_wheres.copy()
    final_wheres.append(f"{target_var}.status = ref_status")
    final_wheres.append(f"{target_var}.unique_id <> ref_id")
    lines.append(_build_where_clause(final_wheres))
    
    lines.append(f"RETURN count({target_var}) AS count")
    return "\n".join(lines)


def _cypher_for_comparison(comp: Dict[str, Any]) -> str:
    """Comparison of lhs and rhs on a single property (status or type)."""
    prop = comp["property"]  # 'status' or 'type'
    lhs = comp["lhs"]
    rhs = comp["rhs"]

    used: Set[str] = set()
    lines: List[str] = []
    where_clauses: List[str] = []

    lhs_var = lhs.get("alias") or _next_var(lhs["type"][0], used)
    rhs_var = rhs.get("alias") or _next_var(rhs["type"][0], used)

    lhs_match, lhs_wheres = _object_match(lhs, lhs_var)
    lines.append(lhs_match)
    where_clauses.extend(lhs_wheres)
    _append_relations(lhs_var, lhs, used, lines, where_clauses)

    rhs_match, rhs_wheres = _object_match(rhs, rhs_var)
    lines.append(rhs_match)
    where_clauses.extend(rhs_wheres)
    _append_relations(rhs_var, rhs, used, lines, where_clauses)

    if where_clauses:
        lines.append(_build_where_clause(where_clauses))
    lines.append(f"RETURN {lhs_var}.{prop} = {rhs_var}.{prop} AS same")
    return "\n".join(lines)
