"""
Answer Logic → Cypher 生成规则
确保问题语义和 Cypher 查询严格一致
"""

def augment_cypher_with_answer_logic(
    original_cypher: str,
    answer_logic: str,
    cell: dict,
    template_params: dict
) -> str:
    """
    根据 answer_logic 增强现有的 Cypher 查询

    Args:
        original_cypher: 原始 Cypher 查询
        answer_logic: 模板的 answer_logic 字段
        cell: gap cell 信息
        template_params: 模板参数

    Returns:
        增强后的 Cypher 查询
    """
    if not answer_logic or answer_logic == "direct":
        return original_cypher

    # 提取原始 WHERE 子句
    import re
    where_match = re.search(r'WHERE\s+(.+?)\s+RETURN', original_cypher, re.DOTALL | re.IGNORECASE)
    if not where_match:
        return original_cypher

    original_where = where_match.group(1).strip()

    # 根据 answer_logic 添加额外约束
    extra_conditions = []

    if answer_logic == "exists_same_status_another":
        # "another X" 的语义：排除路径中已有的同类型对象
        # 应该排除目标对象 n3_id（路径终点），而不是参考对象 n2_id（中间节点）
        target_id = cell.get('n3_id')  # 路径的目标对象
        target_type = cell.get('n3_type')  # 目标对象类型
        query_type = template_params.get('obj_type')  # 问题查询的类型

        # 只有当目标对象类型和查询类型相同时，才需要排除
        # 例如：路径是 ego->motorcycle1->car2，问题是 "another car"
        # 如果 car2 是 car 类型，就应该排除 car2
        if target_id and target_type == query_type:
            extra_conditions.append(f"c.unique_id <> '{target_id}'")

        # 添加方向约束，确保唯一性（避免匹配多个同状态对象）
        direction = cell.get('r2_dir6')
        if direction:
            extra_conditions.append(f"r2.direction_6 = '{str(direction).replace('-', '_')}'")

    elif answer_logic == "exists_another_type":
        # 排除参考对象
        ref_id = cell.get('n2_id') or template_params.get('ref_id')
        if ref_id:
            extra_conditions.append(f"c.unique_id <> '{ref_id}'")

    elif answer_logic == "count_excluding_ref":
        # 计数时排除参考对象
        ref_id = cell.get('n2_id') or template_params.get('ref_id')
        if ref_id:
            extra_conditions.append(f"c.unique_id <> '{ref_id}'")

    # 如果有额外条件，添加到 WHERE 子句
    if extra_conditions:
        if original_where.lower() == "true":
            new_where = " AND ".join(extra_conditions)
        else:
            new_where = original_where + " AND " + " AND ".join(extra_conditions)

        # 替换 WHERE 子句
        new_cypher = re.sub(
            r'WHERE\s+.+?\s+RETURN',
            f'WHERE {new_where}\nRETURN',
            original_cypher,
            flags=re.DOTALL | re.IGNORECASE
        )
        return new_cypher

    return original_cypher


def generate_cypher_for_answer_logic(
    answer_logic: str,
    path_info: dict,
    template_params: dict
) -> str:
    """
    根据 answer_logic 生成对应的 Cypher 查询

    Args:
        answer_logic: 模板的 answer_logic 字段
        path_info: 路径信息 {src_id, mid_id, target_id, ...}
        template_params: 模板参数 {status, direction, obj_type, ...}

    Returns:
        完整的 Cypher 查询字符串
    """

    # L2 两跳路径基础结构
    src_id = path_info.get('src_id', 'ego')
    mid_id = path_info.get('mid_id')
    target_id = path_info.get('target_id')

    # 基础 MATCH 子句
    base_match = f"""MATCH (a:Object {{unique_id:'{src_id}'}})-[:RELATES_TO]->(b:Object {{unique_id:'{mid_id}'}})-[r2:RELATES_TO]->(c:Object)"""

    # 根据 answer_logic 生成 WHERE 条件
    where_conditions = []

    if answer_logic == "exists_same_status_another":
        # 查询同状态的另一个对象
        obj_type = template_params.get('obj_type')
        ref_status = path_info.get('ref_status')  # 参考对象的状态

        where_conditions.append(f"c.type = '{obj_type}'")
        where_conditions.append(f"coalesce(c.status,'') = '{ref_status}'")
        where_conditions.append(f"c.unique_id <> '{mid_id}'")  # 排除参考对象本身

    elif answer_logic == "exists_2hop_chain":
        # 链式两跳方向存在性
        target_type = template_params.get('target_type')
        direction1 = template_params.get('direction1')

        where_conditions.append(f"c.type = '{target_type}'")
        where_conditions.append(f"r2.direction_6 = '{str(direction1).replace('-', '_')}'")

    elif answer_logic == "exists_both_directions":
        # 双方向交集
        target_type = template_params.get('target_type')
        direction2 = template_params.get('direction2')
        ref2_id = template_params.get('ref2_id')

        where_conditions.append(f"c.type = '{target_type}'")
        where_conditions.append(f"r2.direction_6 = '{str(direction2).replace('-', '_')}'")

        # 添加第二个参考点的约束
        base_match += f"""
MATCH (ref2:Object {{unique_id:'{ref2_id}'}})-[ref_r:RELATES_TO]->(c)"""
        where_conditions.append(f"ref_r.direction_6 = '{str(template_params.get('direction1')).replace('-', '_')}'")

    else:
        # 未知的 answer_logic，返回错误
        raise ValueError(f"Unknown answer_logic: {answer_logic}")

    # 组装完整查询
    where_clause = " AND ".join(where_conditions) if where_conditions else "true"

    cypher = f"""{base_match}
WHERE {where_clause}
RETURN count(c) AS n, collect(c.unique_id) AS ids"""

    return cypher


def validate_cypher_matches_question(question: str, cypher: str, answer_logic: str):
    """
    验证 Cypher 查询是否正确实现了问题的语义

    Returns:
        (is_valid, error_message)
    """
    errors = []

    # 检查 1: 如果问题提到 "same status"，Cypher 必须检查 status
    if "same status" in question.lower():
        if "status" not in cypher.lower():
            errors.append("Question mentions 'same status' but Cypher doesn't check status")

    # 检查 2: 如果问题提到 "other than X"，Cypher 必须排除 X
    if "other than" in question.lower() or "another" in question.lower():
        if "<>" not in cypher and "!=" not in cypher:
            errors.append("Question mentions 'another/other than' but Cypher doesn't exclude")

    # 检查 3: 不允许 WHERE true
    if "WHERE true" in cypher:
        errors.append("Cypher uses 'WHERE true' - no filtering")

    # 检查 4: 如果问题提到方向，Cypher 必须检查方向
    directions = ["front", "back", "left", "right"]
    question_has_direction = any(d in question.lower() for d in directions)
    if question_has_direction:
        if "direction" not in cypher.lower():
            errors.append("Question mentions direction but Cypher doesn't check it")

    # 检查 5: 如果问题提到类型，Cypher 必须检查类型
    types = ["car", "truck", "pedestrian", "barrier", "bicycle", "bus", "trailer"]
    question_has_type = any(t in question.lower() for t in types)
    if question_has_type:
        if "c.type" not in cypher:
            errors.append("Question mentions type but Cypher doesn't check it")

    if errors:
        return False, "; ".join(errors)

    return True, ""
