"""
Cypher Integration Module — Neo4j 场景图查询接口

职责:
  1. 将场景图数据导入 Neo4j（节点 + 空间关系边）
  2. 提供 Cypher 查询模板，用于覆盖率计算和缺口采集
  3. 解析 Cypher 查询结果，提取覆盖贡献（L0 节点 + L1 边 + L2 路径）
  4. 为 LLM→Cypher Oracle 提供 schema 描述和 few-shot 示例

设计原则:
  - 所有属性必须是 CV 可见的（图片可判断的离散化描述）
  - L2 子图严格为首尾相连两连边: A→[edge1]→B→[edge2]→C
  - 不使用精确数值（速度、距离米数、TTC 等）
"""

import logging
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================================
#  Neo4j Schema 定义
# ============================================================================

NEO4J_SCHEMA = """
// ====== Node: Object ======
// 每个场景中的对象（含 ego）
(:Object {
    unique_id: STRING,          // "ego", "car1", "ped3", "truck2", ...
    type: STRING,               // "ego", "car", "truck", "pedestrian", "bicycle", "motorcycle", "bus", "barrier", "trafficcone"
    status: STRING,             // "moving", "stopped", "parked" (vehicle) | "moving", "standing", "sitting" (pedestrian) | "with_rider", "without_rider" (cycle)
    heading_class: STRING,      // "facing_ego", "away_from_ego", "lateral_left", "lateral_right"  (朝向分类，图片可见)
    visibility: STRING,         // "v0-40", "v40-60", "v60-80", "v80-100" (可见度分级)
    size_class: STRING          // "small", "medium", "large" (相对尺寸)
})

// ====== Edge: SPATIAL ======
// 两个对象间的空间关系（有向: source→target 表示 target 相对于 source 的位置）
[:SPATIAL {
    direction_8: STRING,        // "front", "front-left", "left", "rear-left", "rear", "rear-right", "right", "front-right"
    distance_bin: STRING        // "near_coll"(<4m), "super_near"(<7m), "very_near"(<10m), "near"(<16m), "visible"(<25m), "far"(>25m)
}]
"""

# CV 可见属性清单
CV_VISIBLE_ATTRIBUTES = {
    "node": [
        "type",           # 对象类型 — 图片可见
        "status",         # 运动状态 — 图片可判断 (moving/stopped/parked)
        "heading_class",  # 朝向分类 — 图片可见车头朝向
        "visibility",     # 遮挡程度 — 图片可见是否被遮挡
        "size_class",     # 相对尺寸 — 图片可比较大小
    ],
    "edge": [
        "direction_8",    # 8方向 — 图片可见空间位置
        "distance_bin",   # 距离分级 — 图片可大致判断远近
    ],
}

# 不可用属性（精确数值，CV 模型无法从图片判断）
NON_CV_ATTRIBUTES = [
    "velocity_mps",      # 精确速度
    "distance_meters",   # 精确距离
    "ttc",               # 碰撞时间
    "heading_angle",     # 精确朝向角
    "acceleration",      # 加速度
]


# ============================================================================
#  场景图导入 Neo4j
# ============================================================================

@dataclass
class Neo4jImporter:
    """将场景图 JSON 转换为 Neo4j 导入语句"""

    @staticmethod
    def scene_to_cypher_statements(scene_data: Dict) -> List[str]:
        """
        将场景图数据转换为 Cypher CREATE 语句

        Args:
            scene_data: {"nodes": [...], "edges": [...], "scene_name": str}

        Returns:
            Cypher 语句列表
        """
        statements = []

        # 清空当前图
        statements.append("MATCH (n) DETACH DELETE n")

        # 创建节点
        nodes = scene_data.get("nodes", [])
        for node in nodes:
            uid = node.get("unique_id", "")
            ntype = node.get("type", "unknown")
            status = node.get("status", "unknown")
            heading = node.get("heading_class", "unknown")
            visibility = node.get("visibility", "v80-100")
            size_class = node.get("size_class", "medium")

            stmt = (
                f"CREATE (:Object {{"
                f"unique_id: '{uid}', "
                f"type: '{ntype}', "
                f"status: '{status}', "
                f"heading_class: '{heading}', "
                f"visibility: '{visibility}', "
                f"size_class: '{size_class}'"
                f"}})"
            )
            statements.append(stmt)

        # 创建边
        edges = scene_data.get("edges", [])
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            direction_8 = Neo4jImporter._extract_direction_8(edge)
            distance_bin = Neo4jImporter._extract_distance_bin(edge)

            if not src or not tgt or not direction_8:
                continue

            stmt = (
                f"MATCH (a:Object {{unique_id: '{src}'}}), "
                f"(b:Object {{unique_id: '{tgt}'}}) "
                f"CREATE (a)-[:SPATIAL {{"
                f"direction_8: '{direction_8}', "
                f"distance_bin: '{distance_bin}'"
                f"}}]->(b)"
            )
            statements.append(stmt)

        return statements

    @staticmethod
    def _extract_direction_8(edge: Dict) -> Optional[str]:
        """从边数据中提取 8方向"""
        if "direction_8" in edge:
            return edge["direction_8"]
        metrics = edge.get("metrics", {})
        if isinstance(metrics, dict):
            for key in ("direction_source", "direction_ego"):
                ds = metrics.get(key, {})
                if isinstance(ds, dict) and "direction_8" in ds:
                    return ds["direction_8"]
        return None

    @staticmethod
    def _extract_distance_bin(edge: Dict) -> str:
        """从边数据中提取距离分级"""
        if "distance_bin" in edge:
            return edge["distance_bin"]
        metrics = edge.get("metrics", {})
        if isinstance(metrics, dict):
            dist = metrics.get("distance", 999)
            if dist <= 4:
                return "near_coll"
            elif dist <= 7:
                return "super_near"
            elif dist <= 10:
                return "very_near"
            elif dist <= 16:
                return "near"
            elif dist <= 25:
                return "visible"
            else:
                return "far"
        return "unknown"


# ============================================================================
#  Cypher 查询模板 — 用于覆盖率计算和缺口采集
# ============================================================================

class CypherTemplates:
    """预定义的 Cypher 查询模板"""

    # ---- 覆盖率枚举查询 ----

    @staticmethod
    def enumerate_all_nodes() -> str:
        """枚举所有非 ego 节点"""
        return """
        MATCH (o:Object)
        WHERE o.type <> 'ego'
        RETURN o.unique_id AS uid, o.type AS type, o.status AS status,
               o.heading_class AS heading, o.visibility AS visibility,
               o.size_class AS size_class
        """

    @staticmethod
    def enumerate_all_edges() -> str:
        """枚举所有空间关系边"""
        return """
        MATCH (a:Object)-[r:SPATIAL]->(b:Object)
        RETURN a.unique_id AS src, r.direction_8 AS direction,
               b.unique_id AS tgt, r.distance_bin AS distance_bin
        """

    @staticmethod
    def enumerate_all_2hop_paths() -> str:
        """枚举所有两跳路径 (L2 覆盖率计算)"""
        return """
        MATCH (a:Object)-[r1:SPATIAL]->(b:Object)-[r2:SPATIAL]->(c:Object)
        WHERE a.unique_id <> c.unique_id
        RETURN a.unique_id AS n1, r1.direction_8 AS dir1,
               b.unique_id AS n2, r2.direction_8 AS dir2,
               c.unique_id AS n3
        """

    # ---- L0 查询 ----

    @staticmethod
    def l0_type_exist(target_type: str) -> str:
        """L0: 某类型是否存在"""
        return f"""
        MATCH (o:Object {{type: '{target_type}'}})
        RETURN o.unique_id AS uid, o.status AS status
        """

    @staticmethod
    def l0_status_type_exist(target_type: str, status: str) -> str:
        """L0: 某状态+类型是否存在"""
        return f"""
        MATCH (o:Object {{type: '{target_type}', status: '{status}'}})
        RETURN o.unique_id AS uid
        """

    @staticmethod
    def l0_object_status(unique_id: str) -> str:
        """L0: 查询对象状态"""
        return f"""
        MATCH (o:Object {{unique_id: '{unique_id}'}})
        RETURN o.status AS status, o.heading_class AS heading
        """

    # ---- L1 查询 ----

    @staticmethod
    def l1_direction_exist(ref_id: str, direction: str, target_type: str) -> str:
        """L1: 某方向是否有某类型"""
        return f"""
        MATCH (ref:Object {{unique_id: '{ref_id}'}})
              -[r:SPATIAL {{direction_8: '{direction}'}}]->
              (obj:Object {{type: '{target_type}'}})
        RETURN obj.unique_id AS uid, obj.status AS status,
               r.distance_bin AS distance_bin
        """

    @staticmethod
    def l1_direction_status(ref_id: str, direction: str) -> str:
        """L1: 查询某方向对象的状态"""
        return f"""
        MATCH (ref:Object {{unique_id: '{ref_id}'}})
              -[r:SPATIAL {{direction_8: '{direction}'}}]->
              (obj:Object)
        RETURN obj.unique_id AS uid, obj.type AS type,
               obj.status AS status, obj.heading_class AS heading
        """

    @staticmethod
    def l1_heading_query(ref_id: str, direction: str) -> str:
        """L1: 查询某方向对象的朝向"""
        return f"""
        MATCH (ref:Object {{unique_id: '{ref_id}'}})
              -[r:SPATIAL {{direction_8: '{direction}'}}]->
              (obj:Object)
        RETURN obj.unique_id AS uid, obj.type AS type,
               obj.heading_class AS heading
        """

    # ---- L2 查询: 严格两连边 A→B→C ----

    @staticmethod
    def l2_chain_exist(ref_id: str, dir1: str, mid_type: str,
                       dir2: str, target_type: str) -> str:
        """L2: 链式方向存在性 — A的B的C是否存在"""
        return f"""
        MATCH (ref:Object {{unique_id: '{ref_id}'}})
              -[r1:SPATIAL {{direction_8: '{dir1}'}}]->
              (mid:Object {{type: '{mid_type}'}})
              -[r2:SPATIAL {{direction_8: '{dir2}'}}]->
              (target:Object {{type: '{target_type}'}})
        RETURN ref.unique_id AS n1, r1.direction_8 AS d1,
               mid.unique_id AS n2, r2.direction_8 AS d2,
               target.unique_id AS n3, target.status AS target_status
        """

    @staticmethod
    def l2_chain_status(ref_id: str, dir1: str, mid_type: str,
                        dir2: str) -> str:
        """L2: 链式方向状态查询 — A的B的C的状态"""
        return f"""
        MATCH (ref:Object {{unique_id: '{ref_id}'}})
              -[r1:SPATIAL {{direction_8: '{dir1}'}}]->
              (mid:Object {{type: '{mid_type}'}})
              -[r2:SPATIAL {{direction_8: '{dir2}'}}]->
              (target:Object)
        RETURN target.unique_id AS uid, target.type AS type,
               target.status AS status, target.heading_class AS heading,
               mid.unique_id AS mid_id
        """

    @staticmethod
    def l2_chain_object(ref_id: str, dir1: str, dir2: str,
                        target_status: str = None) -> str:
        """L2: 链式方向对象查询 — A的B的C是什么"""
        status_filter = f", status: '{target_status}'" if target_status else ""
        return f"""
        MATCH (ref:Object {{unique_id: '{ref_id}'}})
              -[r1:SPATIAL {{direction_8: '{dir1}'}}]->
              (mid:Object)
              -[r2:SPATIAL {{direction_8: '{dir2}'}}]->
              (target:Object{{{status_filter[2:] if status_filter else ''}}})
        RETURN target.unique_id AS uid, target.type AS type,
               target.status AS status, mid.unique_id AS mid_id,
               mid.type AS mid_type
        """

    @staticmethod
    def l2_chain_with_attributes(ref_id: str, dir1: str, mid_type: str,
                                  mid_status: str, dir2: str) -> str:
        """L2: 带属性约束的链式查询 — A的[status] B的C"""
        return f"""
        MATCH (ref:Object {{unique_id: '{ref_id}'}})
              -[r1:SPATIAL {{direction_8: '{dir1}'}}]->
              (mid:Object {{type: '{mid_type}', status: '{mid_status}'}})
              -[r2:SPATIAL {{direction_8: '{dir2}'}}]->
              (target:Object)
        RETURN target.unique_id AS uid, target.type AS type,
               target.status AS status, mid.unique_id AS mid_id
        """

    # ---- L2 覆盖贡献分析 ----

    @staticmethod
    def l2_coverage_contribution(ref_id: str, dir1: str, mid_id: str,
                                  dir2: str, target_id: str) -> str:
        """
        分析一条 L2 路径对 L0/L1 的覆盖贡献

        返回完整路径信息，调用方可自动提取:
          - L0 贡献: mid 节点属性, target 节点属性
          - L1 贡献: ref→mid 边, mid→target 边
          - L2 贡献: ref→mid→target 路径
        """
        return f"""
        MATCH (ref:Object {{unique_id: '{ref_id}'}})
              -[r1:SPATIAL]->(mid:Object {{unique_id: '{mid_id}'}})
              -[r2:SPATIAL]->(target:Object {{unique_id: '{target_id}'}})
        RETURN ref.unique_id AS n1, ref.type AS n1_type, ref.status AS n1_status,
               r1.direction_8 AS d1, r1.distance_bin AS db1,
               mid.unique_id AS n2, mid.type AS n2_type, mid.status AS n2_status,
               r2.direction_8 AS d2, r2.distance_bin AS db2,
               target.unique_id AS n3, target.type AS n3_type, target.status AS n3_status
        """


# ============================================================================
#  覆盖贡献提取器
# ============================================================================

@dataclass
class CoverageContribution:
    """从 Cypher 查询结果中提取的覆盖贡献"""
    l0_nodes: Set[str] = field(default_factory=set)       # 涉及的节点 ID
    l1_edges: Set[Tuple[str, str, str]] = field(default_factory=set)  # (src, dir, tgt)
    l2_paths: Set[Tuple[str, str, str]] = field(default_factory=set)  # (n1, n2, n3)


def extract_coverage_from_path(path_record: Dict) -> CoverageContribution:
    """
    从一条 L2 路径的 Cypher 返回记录中提取全部覆盖贡献

    Args:
        path_record: Cypher 查询返回的一行，包含 n1, d1, n2, d2, n3 等字段

    Returns:
        CoverageContribution 包含该路径涉及的所有 L0/L1/L2 元素
    """
    contrib = CoverageContribution()

    n1 = path_record.get("n1", "")
    n2 = path_record.get("n2", "")
    n3 = path_record.get("n3", "")
    d1 = path_record.get("d1", "")
    d2 = path_record.get("d2", "")

    # L0: 所有涉及的非 ego 节点
    for nid in [n1, n2, n3]:
        if nid and nid != "ego":
            contrib.l0_nodes.add(nid)

    # L1: 两条边
    if n1 and n2 and d1:
        contrib.l1_edges.add((n1, d1, n2))
    if n2 and n3 and d2:
        contrib.l1_edges.add((n2, d2, n3))

    # L2: 完整路径
    if n1 and n2 and n3:
        contrib.l2_paths.add((n1, n2, n3))

    return contrib


# ============================================================================
#  LLM→Cypher Oracle 的 Prompt 模板
# ============================================================================

LLM_CYPHER_SYSTEM_PROMPT = """You are a Cypher query generator for a driving scene graph stored in Neo4j.

## Schema

{schema}

## Rules
1. All queries must only use the attributes listed in the schema above.
2. Do NOT use any numerical attributes like speed, distance in meters, or TTC.
3. direction_8 values: front, front-left, left, rear-left, rear, rear-right, right, front-right
4. status values: moving, stopped, parked (vehicles) | moving, standing, sitting (pedestrians)
5. heading_class values: facing_ego, away_from_ego, lateral_left, lateral_right
6. distance_bin values: near_coll, super_near, very_near, near, visible, far
7. visibility values: v0-40, v40-60, v60-80, v80-100
8. The ego vehicle has unique_id = 'ego' and type = 'ego'
9. SPATIAL edges go from source to target, meaning "target is to the [direction] of source"
10. Return ALL intermediate nodes and edges in the path, not just the final answer.

## Examples

Question: "Are there any cars to the front of me?"
Cypher:
```cypher
MATCH (ego:Object {{unique_id: 'ego'}})-[r:SPATIAL {{direction_8: 'front'}}]->(obj:Object {{type: 'car'}})
RETURN obj.unique_id AS uid, obj.status AS status
```

Question: "Is there a truck to the left of the car that is to the front of me?"
Cypher:
```cypher
MATCH (ego:Object {{unique_id: 'ego'}})-[r1:SPATIAL {{direction_8: 'front'}}]->(mid:Object {{type: 'car'}})-[r2:SPATIAL {{direction_8: 'left'}}]->(target:Object {{type: 'truck'}})
RETURN ego.unique_id AS n1, r1.direction_8 AS d1, mid.unique_id AS n2, r2.direction_8 AS d2, target.unique_id AS n3, target.status AS target_status
```

Question: "What is the status of the car that is facing me to the front?"
Cypher:
```cypher
MATCH (ego:Object {{unique_id: 'ego'}})-[r:SPATIAL {{direction_8: 'front'}}]->(obj:Object {{type: 'car', heading_class: 'facing_ego'}})
RETURN obj.unique_id AS uid, obj.status AS status
```
"""

LLM_CYPHER_USER_TEMPLATE = """Given the following question about a driving scene, generate the corresponding Cypher query.

Scene summary:
{scene_summary}

Question: {question}

Generate ONLY the Cypher query, no explanation."""


def build_scene_summary(scene_data: Dict) -> str:
    """
    构建场景摘要，供 LLM 生成 Cypher 时参考

    Returns:
        简洁的场景描述字符串
    """
    nodes = scene_data.get("nodes", [])
    edges = scene_data.get("edges", [])

    # 统计对象
    type_counts: Dict[str, int] = {}
    for node in nodes:
        ntype = node.get("type", "unknown")
        if ntype != "ego":
            type_counts[ntype] = type_counts.get(ntype, 0) + 1

    # 构建摘要
    lines = []
    lines.append(f"Objects: {sum(type_counts.values())} total")
    for t, c in sorted(type_counts.items()):
        lines.append(f"  - {t}: {c}")

    # 列出所有对象及关键属性
    lines.append("\nObject details:")
    for node in nodes:
        uid = node.get("unique_id", "")
        ntype = node.get("type", "unknown")
        if ntype == "ego":
            continue
        status = node.get("status", "unknown")
        heading = node.get("heading_class", "unknown")
        lines.append(f"  {uid}: type={ntype}, status={status}, heading={heading}")

    # 列出空间关系
    lines.append(f"\nSpatial relations: {len(edges)} edges")
    for edge in edges[:20]:  # 最多显示20条
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        d8 = Neo4jImporter._extract_direction_8(edge)
        db = Neo4jImporter._extract_distance_bin(edge)
        if d8:
            lines.append(f"  {src} --[{d8}, {db}]--> {tgt}")

    if len(edges) > 20:
        lines.append(f"  ... and {len(edges) - 20} more edges")

    return "\n".join(lines)


# ============================================================================
#  Cypher 结果解析器
# ============================================================================

class CypherResultParser:
    """解析 Neo4j Cypher 查询结果"""

    @staticmethod
    def parse_exist_result(records: List[Dict]) -> Tuple[bool, List[str]]:
        """解析存在性查询结果 → (exists, [matched_ids])"""
        ids = [r.get("uid", "") for r in records if r.get("uid")]
        return len(ids) > 0, ids

    @staticmethod
    def parse_status_result(records: List[Dict]) -> Tuple[Optional[str], str]:
        """解析状态查询结果 → (status, uid)"""
        if records:
            return records[0].get("status"), records[0].get("uid", "")
        return None, ""

    @staticmethod
    def parse_object_result(records: List[Dict]) -> Tuple[Optional[str], str]:
        """解析对象类型查询结果 → (type, uid)"""
        if records:
            return records[0].get("type"), records[0].get("uid", "")
        return None, ""

    @staticmethod
    def parse_comparison_result(records: List[Dict],
                                 compare_field: str = "status") -> Tuple[bool, Dict]:
        """解析比较查询结果"""
        if len(records) >= 2:
            val1 = records[0].get(compare_field)
            val2 = records[1].get(compare_field)
            return val1 == val2, {
                "obj1": records[0].get("uid", ""),
                "obj2": records[1].get("uid", ""),
                "val1": val1,
                "val2": val2,
            }
        return False, {}

    @staticmethod
    def parse_path_result(records: List[Dict]) -> List[CoverageContribution]:
        """解析路径查询结果，提取覆盖贡献"""
        contributions = []
        for record in records:
            contrib = extract_coverage_from_path(record)
            contributions.append(contrib)
        return contributions

    @staticmethod
    def merge_contributions(contributions: List[CoverageContribution]) -> CoverageContribution:
        """合并多条路径的覆盖贡献"""
        merged = CoverageContribution()
        for c in contributions:
            merged.l0_nodes.update(c.l0_nodes)
            merged.l1_edges.update(c.l1_edges)
            merged.l2_paths.update(c.l2_paths)
        return merged
