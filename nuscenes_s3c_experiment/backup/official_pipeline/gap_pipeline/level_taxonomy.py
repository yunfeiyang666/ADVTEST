"""
level_taxonomy.py — V5 权威分级映射

论文核心数据模型（设计底稿硬编码）：

等级   覆盖单元   题目类型          约束策略              难度
L0    节点(Node)   Attribute_Query    属性匹配(Type/Status)  Easy
L1    单边(Edge)   Spatial_Relation   8方向/距离序/属性叠加  Medium
L2    路径(Path)   Path_Logic         链式引用+干扰项排除  Hard

L2 拓扑两种：
  L2A: ego → A → B  (主车起始锚点链)
  L2B: A → B → C   (物体起始链，全部非主车)
"""
from __future__ import annotations
from typing import NamedTuple


class QuestionMeta(NamedTuple):
    level:             str   # L0 / L1 / L2
    question_category: str   # Attribute_Query / Spatial_Relation / Path_Logic  (V5)
    q_type1:           str   # Attribute / Spatial / Logical / Reasoning
    q_type2:           str   # 细分标签
    difficulty:        str   # Easy / Medium / Hard


# ─── V5 权威映射表 (question_category 为论文数据模型)────────────────────────────────
_TAXONOMY: dict[str, QuestionMeta] = {
    # ── L0: Node 属性题 (Attribute_Query) ──────────────────────────────────
    "node_status":          QuestionMeta("L0", "Attribute_Query", "Attribute", "Status_Query",   "Easy"),
    "node_type":            QuestionMeta("L0", "Attribute_Query", "Attribute", "Type_Query",     "Easy"),

    # ── L1: Edge 空间关系题 (Spatial_Relation) ─────────────────────────────
    "no_constraint_needed": QuestionMeta("L1", "Spatial_Relation", "Attribute", "Unique_Direct",  "Easy"),
    "type":                 QuestionMeta("L1", "Spatial_Relation", "Attribute", "Type_Filter",    "Easy"),
    "status":               QuestionMeta("L1", "Spatial_Relation", "Attribute", "Status_Query",   "Easy"),
    "type+status":          QuestionMeta("L1", "Spatial_Relation", "Attribute", "Type_Status",    "Easy"),
    "status_anchor":        QuestionMeta("L1", "Spatial_Relation", "Attribute", "Status_Query",   "Easy"),
    "type_filter":          QuestionMeta("L1", "Spatial_Relation", "Attribute", "Type_Filter",    "Easy"),
    "type_status_anchor":   QuestionMeta("L1", "Spatial_Relation", "Attribute", "Type_Status",    "Easy"),
    "dir8":                 QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Direction_Refine","Medium"),
    "dir8_refine":          QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Direction_Refine","Medium"),
    "type+dir8":            QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Direction_Refine","Medium"),
    "status+dir8":          QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Direction_Refine","Medium"),
    "dist_ord":             QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Distance_Order",  "Medium"),
    "dist_order":           QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Distance_Order",  "Medium"),
    "ordinal_by_distance":  QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Distance_Order",  "Medium"),
    "type+dist_ord":        QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Distance_Order",  "Medium"),
    "dir8+dist_ord":        QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Direction_Distance","Medium"),
    "type+dir8+dist_ord":   QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Direction_Distance","Medium"),
    "type+status+dir8":     QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Direction_Refine", "Medium"),
    "type_dist_combo":      QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Distance_Order",  "Medium"),
    "type_dir8_dist_combo": QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Direction_Distance","Medium"),
    "all_props_combo":      QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Full_Props",      "Medium"),
    "dual_reference":       QuestionMeta("L1", "Spatial_Relation", "Spatial",   "Dual_Direction",  "Medium"),
    "anchor_intro":         QuestionMeta("L1", "Spatial_Relation", "Attribute", "Anchor_Reference","Medium"),
    "yesno_fallback":       QuestionMeta("L1", "Spatial_Relation", "Reasoning", "Existence_Check", "Medium"),
    "count_fallback":       QuestionMeta("L1", "Spatial_Relation", "Reasoning", "Count_Query",     "Medium"),
    "negation":             QuestionMeta("L1", "Spatial_Relation", "Reasoning", "Attribute_Negation","Medium"),

    # ── L2: Path 链式逻辑题 (Path_Logic) ───────────────────────────────
    # V5 路径约束方法（干扰项排除 + 链式引用）
    "l2a_chain":            QuestionMeta("L2", "Path_Logic", "Logical",   "Ego_Anchor_Chain",  "Hard"),
    "l2b_chain":            QuestionMeta("L2", "Path_Logic", "Logical",   "Object_Chain",      "Hard"),
    # 已有 V2 方法（兼容）
    "two_hop_referent":     QuestionMeta("L2", "Path_Logic", "Logical",   "Multi_Object_Relational","Hard"),
    "dual_hop_referent":    QuestionMeta("L2", "Path_Logic", "Logical",   "Multi_Object_Relational","Hard"),
    "type+two_hop":         QuestionMeta("L2", "Path_Logic", "Logical",   "Attribute_Filtered_Hop", "Hard"),
    "status+two_hop":       QuestionMeta("L2", "Path_Logic", "Logical",   "Attribute_Filtered_Hop", "Hard"),
    "multihop":             QuestionMeta("L2", "Path_Logic", "Logical",   "Chain_Query",     "Hard"),
}

_DEFAULT = QuestionMeta("L1", "Spatial_Relation", "Attribute", "Unknown", "Medium")


def get_meta(method_used: str, question_type: str = "",
            topology_level: str = "") -> QuestionMeta:
    """
    根据约束方法名和题目类型返回 L0/L1/L2 等级及分类元数据。
    question_type 优先：negation/multihop/node_status 特殊处理。
    """
    # V5: topology_level supersedes method_used for L2 classification
    if topology_level in ("L2A",):
        return _TAXONOMY["l2a_chain"]
    if topology_level in ("L2B",):
        return _TAXONOMY["l2b_chain"]
    if question_type in ("negation",):
        return _TAXONOMY["negation"]
    if question_type in ("multihop",):
        return _TAXONOMY["multihop"]
    if question_type in ("node_status", "node_type"):
        return _TAXONOMY.get(question_type, _TAXONOMY["node_status"])
    return _TAXONOMY.get(method_used, _DEFAULT)


def validate_l2(method_used: str, n_referents: int) -> str:
    """
    校验 L2 问题的 n_referents 是否合理。
    返回 '' (OK) 或错误描述字符串。
    """
    meta = get_meta(method_used)
    if meta.level == "L2" and n_referents == 0:
        return f"BUG: L2 method '{method_used}' but n_referents=0"
    if meta.level != "L2" and n_referents > 0:
        return f"WARN: non-L2 method '{method_used}' has n_referents={n_referents}"
    return ""
