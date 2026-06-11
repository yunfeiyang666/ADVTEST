"""
QA Cypher Generator — 规则化Cypher生成器

功能：
  将模板生成的QA对参数直接翻译为可执行的Cypher查询，
  无需LLM参与，用于基于Neo4j的精确覆盖率计算和缺口检测。

设计原则（对应L0/L1/L2模板）：
  - L0: 单节点约束查询
  - L1: 单跳边查询（ref --direction--> target）
  - L2: 两跳链式查询（ref --dir2--> mid --dir1--> target）

Cypher中方向字段选择规则：
  - 4方位词(front/back/left/right) → r.direction_4
  - 8方位词(含"-"如front-left/back-right等) → r.predicates[0]

特殊类型处理（与 ir_to_cypher.py 保持一致）：
  - trailer → WHERE n.category CONTAINS 'trailer'
  - truck   → WHERE n.type='truck' AND NOT n.category CONTAINS 'trailer'
"""
from typing import Optional, Dict, Any


# ──────────────────────────────────────────────────────────
# 内部工具
# ──────────────────────────────────────────────────────────

def _dir_field(direction: str) -> str:
    """根据方向名称选择正确的Neo4j关系属性字段。"""
    if "-" in direction:
        return "predicates[0]"
    return "direction_4"


def _type_where(var: str, obj_type: str, status: Optional[str] = None) -> str:
    """为给定变量生成类型+状态WHERE条件片段（不含WHERE关键字）。"""
    clauses = []
    if obj_type == "trailer":
        clauses.append(f"{var}.category CONTAINS 'trailer'")
    elif obj_type == "truck":
        clauses.append(f"{var}.type = 'truck'")
        clauses.append(f"NOT {var}.category CONTAINS 'trailer'")
    elif obj_type and obj_type not in ("thing", ""):
        clauses.append(f"{var}.type = '{obj_type}'")
    if status and status not in ("unknown", ""):
        clauses.append(f"{var}.status = '{status}'")
    return " AND ".join(clauses) if clauses else ""


def _maybe_where(conditions: str) -> str:
    """如果条件非空，加上 WHERE 前缀。"""
    return f"WHERE {conditions}" if conditions else ""


# ──────────────────────────────────────────────────────────
# L0 Cypher
# ──────────────────────────────────────────────────────────

def cypher_L0_exist_type(obj_type: str) -> str:
    """Are there any {type}?"""
    cond = _type_where("n", obj_type)
    return (
        f"MATCH (n:Object)\n"
        f"{_maybe_where(cond)}\n"
        f"RETURN count(n) > 0 AS exists"
    )


def cypher_L0_exist_status(obj_type: str, status: str) -> str:
    """Are there any {status} {type}?"""
    cond = _type_where("n", obj_type, status)
    return (
        f"MATCH (n:Object)\n"
        f"{_maybe_where(cond)}\n"
        f"RETURN count(n) > 0 AS exists"
    )


def cypher_L0_status_query(ref_id: str) -> str:
    """What is the status of {ref_type} ({ref_id})?"""
    return (
        f"MATCH (n:Object {{unique_id: '{ref_id}'}})\n"
        f"RETURN n.status AS status\n"
        f"LIMIT 1"
    )


# ──────────────────────────────────────────────────────────
# L1 Cypher
# ──────────────────────────────────────────────────────────

def cypher_L1_exist_direction(ref_id: str, direction: str, target_type: str,
                               target_status: Optional[str] = None) -> str:
    """Are there any {type} to the {direction} of {ref} ({ref_id})?"""
    df = _dir_field(direction)
    cond = _type_where("t", target_type, target_status)
    where_parts = [f"r.{df} = '{direction}'"]
    if cond:
        where_parts.append(cond)
    where_clause = "WHERE " + " AND ".join(where_parts)
    return (
        f"MATCH (ref:Object {{unique_id: '{ref_id}'}})-[r:RELATES_TO]->(t:Object)\n"
        f"{where_clause}\n"
        f"RETURN count(t) > 0 AS exists"
    )


def cypher_L1_status_direction(ref_id: str, direction: str, target_id: str) -> str:
    """What is the status of {target} ({target_id}) to the {direction} of {ref} ({ref_id})?"""
    df = _dir_field(direction)
    return (
        f"MATCH (ref:Object {{unique_id: '{ref_id}'}})-[r:RELATES_TO]->(t:Object {{unique_id: '{target_id}'}})\n"
        f"WHERE r.{df} = '{direction}'\n"
        f"RETURN t.status AS status\n"
        f"LIMIT 1"
    )


def cypher_L1_object_direction(ref_id: str, direction: str) -> str:
    """What is to the {direction} of {ref} ({ref_id})?"""
    df = _dir_field(direction)
    return (
        f"MATCH (ref:Object {{unique_id: '{ref_id}'}})-[r:RELATES_TO]->(t:Object)\n"
        f"WHERE r.{df} = '{direction}'\n"
        f"WITH t, r ORDER BY r.distance ASC LIMIT 1\n"
        f"RETURN t.type AS type, t.unique_id AS unique_id"
    )


def cypher_L1_compare_status(obj1_id: str, obj2_id: str) -> str:
    """Does {obj1} ({obj1_id}) have the same status as {obj2} ({obj2_id})?"""
    return (
        f"MATCH (a:Object {{unique_id: '{obj1_id}'}})\n"
        f"MATCH (b:Object {{unique_id: '{obj2_id}'}})\n"
        f"RETURN a.status = b.status AS same"
    )


# ──────────────────────────────────────────────────────────
# L2 Cypher — 严格链式 A --dir2--> B --dir1--> C
# ──────────────────────────────────────────────────────────

def cypher_L2_exist_chain(ref_id: str, dir2: str, mid_id: str,
                           dir1: str, target_type: str,
                           target_status: Optional[str] = None) -> str:
    """
    Is there a {target_type} to the {dir1} of the {mid_type} ({mid_id})
    that is to the {dir2} of {ref_type} ({ref_id})?

    Pattern: ref --dir2--> mid --dir1--> target
    mid_id provided to anchor the chain precisely.
    """
    df1 = _dir_field(dir1)
    df2 = _dir_field(dir2)
    cond = _type_where("c", target_type, target_status)
    where_parts = [
        f"r1.{df2} = '{dir2}'",
        f"r2.{df1} = '{dir1}'",
    ]
    if cond:
        where_parts.append(cond)
    where_clause = "WHERE " + " AND ".join(where_parts)
    return (
        f"MATCH (ref:Object {{unique_id: '{ref_id}'}})-[r1:RELATES_TO]->(mid:Object {{unique_id: '{mid_id}'}})-[r2:RELATES_TO]->(c:Object)\n"
        f"{where_clause}\n"
        f"RETURN count(c) > 0 AS exists"
    )


def cypher_L2_status_chain(ref_id: str, dir2: str, mid_id: str,
                            dir1: str, target_type: str) -> str:
    """
    What is the status of the {target_type} to the {dir1} of the {mid_type} ({mid_id})
    that is to the {dir2} of {ref_type} ({ref_id})?
    """
    df1 = _dir_field(dir1)
    df2 = _dir_field(dir2)
    type_cond = _type_where("c", target_type)
    where_parts = [f"r1.{df2} = '{dir2}'", f"r2.{df1} = '{dir1}'"]
    if type_cond:
        where_parts.append(type_cond)
    where_clause = "WHERE " + " AND ".join(where_parts)
    return (
        f"MATCH (ref:Object {{unique_id: '{ref_id}'}})-[r1:RELATES_TO]->(mid:Object {{unique_id: '{mid_id}'}})-[r2:RELATES_TO]->(c:Object)\n"
        f"{where_clause}\n"
        f"WITH c, r2 ORDER BY r2.distance ASC LIMIT 1\n"
        f"RETURN c.status AS status"
    )


def cypher_L2_compare_chain(obj1_id: str, ref_id: str, direction: str, obj2_type: str) -> str:
    """
    Does the {obj1_type} ({obj1_id}) have the same status as
    the {obj2_type} to the {direction} of {ref_type} ({ref_id})?

    This is: obj1's status vs the status of some obj2 that is in direction of ref.
    "status as bidirectional edge" variant.
    """
    df = _dir_field(direction)
    type_cond = _type_where("b", obj2_type)
    where_parts = [f"r.{df} = '{direction}'"]
    if type_cond:
        where_parts.append(type_cond)
    where_clause = "WHERE " + " AND ".join(where_parts)
    return (
        f"MATCH (a:Object {{unique_id: '{obj1_id}'}})\n"
        f"MATCH (ref:Object {{unique_id: '{ref_id}'}})-[r:RELATES_TO]->(b:Object)\n"
        f"{where_clause}\n"
        f"WITH a, b, r ORDER BY r.distance ASC LIMIT 1\n"
        f"RETURN a.status = b.status AS same"
    )


# ──────────────────────────────────────────────────────────
# Gap Detection Cypher
# ──────────────────────────────────────────────────────────

def cypher_gap_find_uncovered_edges(covered_edge_ids: list) -> str:
    """
    生成查找未覆盖边的Cypher。

    covered_edge_ids: [(source_id, target_id), ...]  已覆盖边列表
    返回的Cypher枚举场景中所有的RELATES_TO边及其属性。
    """
    if not covered_edge_ids:
        # 无覆盖时返回所有边
        return (
            "MATCH (a:Object)-[r:RELATES_TO]->(b:Object)\n"
            "RETURN a.unique_id AS source, b.unique_id AS target,\n"
            "       r.direction_4 AS dir4, r.predicates AS predicates,\n"
            "       r.distance AS distance\n"
            "ORDER BY r.distance ASC"
        )

    # 将已覆盖边转为条件过滤
    covered_pairs = [f"['{s}','{t}']" for s, t in covered_edge_ids]
    covered_list = "[" + ", ".join(covered_pairs) + "]"
    return (
        "MATCH (a:Object)-[r:RELATES_TO]->(b:Object)\n"
        f"WHERE NOT [a.unique_id, b.unique_id] IN {covered_list}\n"
        "RETURN a.unique_id AS source, b.unique_id AS target,\n"
        "       r.direction_4 AS dir4, r.predicates AS predicates,\n"
        "       r.distance AS distance\n"
        "ORDER BY r.distance ASC"
    )


def cypher_find_covered_edge_ids(source_id: str, direction: str,
                                  target_type: Optional[str] = None) -> str:
    """
    给定锚点和方向，查找实际被指向的 target.unique_id 列表（用于精确标记覆盖的边）。
    """
    df = _dir_field(direction)
    cond_parts = [f"r.{df} = '{direction}'"]
    if target_type and target_type not in ("thing", ""):
        tc = _type_where("t", target_type)
        if tc:
            cond_parts.append(tc)
    where_clause = "WHERE " + " AND ".join(cond_parts)
    return (
        f"MATCH (ref:Object {{unique_id: '{source_id}'}})-[r:RELATES_TO]->(t:Object)\n"
        f"{where_clause}\n"
        f"RETURN t.unique_id AS target_id, r.distance AS distance"
    )


# ──────────────────────────────────────────────────────────
# 分发入口
# ──────────────────────────────────────────────────────────

def generate_cypher_for_qa(template_id: str, params: Dict[str, Any]) -> Optional[str]:
    """
    根据 template_id 和参数生成对应的 Cypher 查询。

    params 字段说明（不同模板所需字段不同）：
      - ref_id: 锚点对象 unique_id
      - mid_id: 中间节点 unique_id（L2链式使用）
      - target_id: 目标节点 unique_id（L1_status_direction使用）
      - obj1_id, obj2_id: 比较对象 unique_id（比较模板）
      - direction, dir1, dir2: 方向
      - obj_type: 目标对象类型名 (car/pedestrian/…)
      - status: 状态约束（可选）

    Returns:
        Cypher字符串，若模板未知则返回None。
    """
    p = params
    tid = template_id

    if tid == "L0_exist_type":
        return cypher_L0_exist_type(p.get("obj_type", ""))
    if tid == "L0_exist_status":
        return cypher_L0_exist_status(p.get("obj_type", ""), p.get("status", ""))
    if tid == "L0_status_query":
        return cypher_L0_status_query(p["ref_id"])

    if tid in ("L1_exist_direction", "L1_exist_direction_status"):
        return cypher_L1_exist_direction(
            p["ref_id"], p["direction"], p.get("obj_type", ""),
            p.get("status") if tid == "L1_exist_direction_status" else None
        )
    if tid == "L1_status_direction":
        return cypher_L1_status_direction(p["ref_id"], p["direction"], p["target_id"])
    if tid in ("L1_object_direction", "L1_object_direction_specific"):
        return cypher_L1_object_direction(p["ref_id"], p["direction"])
    if tid == "L1_compare_status":
        return cypher_L1_compare_status(p["obj1_id"], p["obj2_id"])

    if tid in ("L2_exist_chain", "L2_exist_chain_status"):
        return cypher_L2_exist_chain(
            p["ref_id"], p["dir2"], p["mid_id"], p["dir1"],
            p.get("obj_type", ""),
            p.get("status") if tid == "L2_exist_chain_status" else None
        )
    if tid == "L2_status_chain":
        return cypher_L2_status_chain(
            p["ref_id"], p["dir2"], p["mid_id"], p["dir1"],
            p.get("obj_type", "")
        )
    if tid == "L2_compare_chain":
        return cypher_L2_compare_chain(
            p["obj1_id"], p["ref_id"], p["direction"], p.get("obj2_type", "")
        )

    return None  # 未知模板
