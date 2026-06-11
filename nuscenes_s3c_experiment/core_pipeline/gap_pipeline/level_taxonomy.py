"""
level_taxonomy.py — 约束方法到等级/类型/难度的硬映射

等级定义（严格按节点数划分）：
  L0  Node Status   单节点属性问题（直接问节点状态/类型，无空间关系）
  L1  Edge Relation 两节点直接关系（src → tgt，方向/距离/属性）
  L2  Chain/Logical 三节点及以上链式逻辑（two_hop / dual_hop / anc+beyond）

题目类型：
  一级（q_type1）：Attribute / Spatial / Logical / Reasoning
  二级（q_type2）：细分分类

难度分级：
  Easy   P1-P3 属性约束（类型/状态）
  Medium P4-P7 空间/距离约束
  Hard   P10+  两跳/双跳参照约束
"""
from __future__ import annotations
from typing import NamedTuple


class QuestionMeta(NamedTuple):
    level:      str   # L0 / L1 / L2
    q_type1:    str   # Attribute / Spatial / Logical / Reasoning
    q_type2:    str   # 细分标签
    difficulty: str   # Easy / Medium / Hard


# ─── 核心映射表 ────────────────────────────────────────────────────────────
_TAXONOMY: dict[str, QuestionMeta] = {
    # ── L0: Node-only attribute （无空间关系，直接问节点状态） ─────────────
    "node_status":          QuestionMeta("L0", "Attribute", "Status_Query",   "Easy"),
    "node_type":            QuestionMeta("L0", "Attribute", "Type_Query",     "Easy"),

    # ── L1: Direct Edge Relation （src → tgt，单跳）──────────────────────
    # 属性类 Easy
    "no_constraint_needed": QuestionMeta("L1", "Attribute", "Unique_Direct",  "Easy"),
    "type":                 QuestionMeta("L1", "Attribute", "Type_Filter",    "Easy"),
    "status":               QuestionMeta("L1", "Attribute", "Status_Query",   "Easy"),
    "type+status":          QuestionMeta("L1", "Attribute", "Type_Status",    "Easy"),
    "status_anchor":        QuestionMeta("L1", "Attribute", "Status_Query",   "Easy"),
    "type_filter":          QuestionMeta("L1", "Attribute", "Type_Filter",    "Easy"),
    "type_status_anchor":   QuestionMeta("L1", "Attribute", "Type_Status",    "Easy"),
    # 空间类 Medium
    "dir8":                 QuestionMeta("L1", "Spatial",   "Direction_Refine","Medium"),
    "dir8_refine":          QuestionMeta("L1", "Spatial",   "Direction_Refine","Medium"),
    "type+dir8":            QuestionMeta("L1", "Spatial",   "Direction_Refine","Medium"),
    "status+dir8":          QuestionMeta("L1", "Spatial",   "Direction_Refine","Medium"),
    "dist_ord":             QuestionMeta("L1", "Spatial",   "Distance_Order",  "Medium"),
    "dist_order":           QuestionMeta("L1", "Spatial",   "Distance_Order",  "Medium"),
    "ordinal_by_distance":  QuestionMeta("L1", "Spatial",   "Distance_Order",  "Medium"),
    "type+dist_ord":        QuestionMeta("L1", "Spatial",   "Distance_Order",  "Medium"),
    "dir8+dist_ord":        QuestionMeta("L1", "Spatial",   "Direction_Distance","Medium"),
    "type+dir8+dist_ord":   QuestionMeta("L1", "Spatial",   "Direction_Distance","Medium"),
    "type+status+dir8":     QuestionMeta("L1", "Spatial",   "Direction_Refine", "Medium"),
    "type_dist_combo":      QuestionMeta("L1", "Spatial",   "Distance_Order",  "Medium"),
    "type_dir8_dist_combo": QuestionMeta("L1", "Spatial",   "Direction_Distance","Medium"),
    "all_props_combo":      QuestionMeta("L1", "Spatial",   "Full_Props",      "Medium"),
    "dual_reference":       QuestionMeta("L1", "Spatial",   "Dual_Direction",  "Medium"),
    "anchor_intro":         QuestionMeta("L1", "Attribute", "Anchor_Reference","Medium"),
    # 存在性/兜底
    "yesno_fallback":       QuestionMeta("L1", "Reasoning", "Existence_Check", "Medium"),
    "count_fallback":       QuestionMeta("L1", "Reasoning", "Count_Query",     "Medium"),
    # 否定题
    "negation":             QuestionMeta("L1", "Reasoning", "Attribute_Negation","Medium"),

    # ── L2: Chain/Logical （three-node+，多跳）──────────────────────────
    "two_hop_referent":     QuestionMeta("L2", "Logical",   "Multi_Object_Relational","Hard"),
    "dual_hop_referent":    QuestionMeta("L2", "Logical",   "Multi_Object_Relational","Hard"),
    "type+two_hop":         QuestionMeta("L2", "Logical",   "Attribute_Filtered_Hop", "Hard"),
    "status+two_hop":       QuestionMeta("L2", "Logical",   "Attribute_Filtered_Hop", "Hard"),
    # 多跳链式题
    "multihop":             QuestionMeta("L2", "Logical",   "Chain_Query",     "Hard"),
}

_DEFAULT = QuestionMeta("L1", "Attribute", "Unknown", "Medium")


def get_meta(method_used: str, question_type: str = "") -> QuestionMeta:
    """
    根据约束方法名和题目类型返回 L0/L1/L2 等级及分类元数据。
    question_type 优先：negation/multihop/node_status 特殊处理。
    """
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
