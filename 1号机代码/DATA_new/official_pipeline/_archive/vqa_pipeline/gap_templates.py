"""
Gap QA 模板库 — 300 个模板
===========================
四级层次结构
  L1: 难度级别 — L0 / L1 / L2
  L2: 问题类别 — exist / status / type / dir / dist
  L3: 提问角度 — 75 个唯一角度
  L4: 语义变体 — 每种 4 个变体（共 300 条）

模板变量（均通过 str.format(**tvars) 填充）
  L0（以 ego 为 src）:
    {type}   {status}   {dir}   {dist}
  L1（src ≠ ego）:
    {src_type} {src_status} {tgt_type} {tgt_status} {dir} {dist}
  L2 链 A（anc→src→tgt）:
    {anc_type} {anc_status} {dir_as}
    {src_type} {src_status} {dir_st}
    {tgt_type} {tgt_status}
  L2 链 B（src→tgt→beyond）:
    {src_type} {src_status} {dir_st}
    {tgt_type} {tgt_status} {dir_tb}
    {beyond_type} {beyond_status}

答案来源（answer_source 字段）
  "yes"           — exist 类题，缺口边在图中真实存在
  "tgt_status"    — 问 tgt 状态
  "src_status"    — 问 src 状态
  "beyond_status" — 问 beyond 状态
  "tgt_type"      — 问 tgt 类型
  "beyond_type"   — 问 beyond 类型
  "dir"           — 问方向（来自 dir8/dir4）
  "dist_level"    — 问距离级别

requires 选项
  "ego_src"       — src_id 必须为 "ego"
  "tgt_status"    — tgt_status 非空且非 unknown
  "src_status"    — src_status 非空且非 unknown
  "anc_status"    — anc_status 非空且非 unknown
  "beyond_status" — beyond_status 非空且非 unknown
  "dist"          — dist_level 非空
  "anc"           — anc_id 不为 None
  "beyond"        — beyond_id 不为 None
"""
from __future__ import annotations

import random
from typing import Dict, List, NamedTuple, Optional


# ─────────────────────────────────────────────────────────────────────────────
# 模板元数据
# ─────────────────────────────────────────────────────────────────────────────

class TemplateMeta(NamedTuple):
    difficulty:    str        # "L0" / "L1" / "L2"
    category:      str        # "exist" / "status" / "type" / "dir" / "dist"
    answer_type:   str        # "bool" / "open"
    answer_source: str        # ctx 键 或 "yes"
    requires:      List[str]  # 前提条件列表


TEMPLATE_META: Dict[str, TemplateMeta] = {
    # ── L0 Exist ──────────────────────────────────────────────────────────────
    "L0_exist_basic":          TemplateMeta("L0", "exist", "bool", "yes",          ["ego_src"]),
    "L0_exist_status":         TemplateMeta("L0", "exist", "bool", "yes",          ["ego_src", "tgt_status"]),
    "L0_exist_dir":            TemplateMeta("L0", "exist", "bool", "yes",          ["ego_src"]),
    "L0_exist_dir_status":     TemplateMeta("L0", "exist", "bool", "yes",          ["ego_src", "tgt_status"]),
    "L0_exist_dist":           TemplateMeta("L0", "exist", "bool", "yes",          ["ego_src", "dist"]),
    "L0_exist_dir_dist":       TemplateMeta("L0", "exist", "bool", "yes",          ["ego_src", "dist"]),
    # ── L0 Status ─────────────────────────────────────────────────────────────
    "L0_status_basic":         TemplateMeta("L0", "status", "open", "tgt_status",  ["ego_src", "tgt_status"]),
    "L0_status_dir":           TemplateMeta("L0", "status", "open", "tgt_status",  ["ego_src", "tgt_status"]),
    "L0_status_dist":          TemplateMeta("L0", "status", "open", "tgt_status",  ["ego_src", "tgt_status", "dist"]),
    "L0_status_dir_dist":      TemplateMeta("L0", "status", "open", "tgt_status",  ["ego_src", "tgt_status", "dist"]),
    # ── L0 Direction ──────────────────────────────────────────────────────────
    "L0_dir_basic":            TemplateMeta("L0", "dir",    "open", "dir",         ["ego_src"]),
    "L0_dir_status":           TemplateMeta("L0", "dir",    "open", "dir",         ["ego_src", "tgt_status"]),
    "L0_dir_dist":             TemplateMeta("L0", "dir",    "open", "dir",         ["ego_src", "dist"]),
    # ── L0 Distance ───────────────────────────────────────────────────────────
    "L0_dist_basic":           TemplateMeta("L0", "dist",   "open", "dist_level",  ["ego_src", "dist"]),
    "L0_dist_status":          TemplateMeta("L0", "dist",   "open", "dist_level",  ["ego_src", "dist", "tgt_status"]),
    "L0_dist_dir":             TemplateMeta("L0", "dist",   "open", "dist_level",  ["ego_src", "dist"]),
    # ── L0 Type ───────────────────────────────────────────────────────────────
    "L0_type_dir":             TemplateMeta("L0", "type",   "open", "tgt_type",    ["ego_src"]),
    "L0_type_dir_dist":        TemplateMeta("L0", "type",   "open", "tgt_type",    ["ego_src", "dist"]),
    "L0_type_status":          TemplateMeta("L0", "type",   "open", "tgt_type",    ["ego_src", "tgt_status"]),
    "L0_type_dir_status":      TemplateMeta("L0", "type",   "open", "tgt_type",    ["ego_src", "tgt_status"]),

    # ── L1 Exist ──────────────────────────────────────────────────────────────
    "L1_exist_dir":                  TemplateMeta("L1", "exist", "bool", "yes",         []),
    "L1_exist_dir_tgt_status":       TemplateMeta("L1", "exist", "bool", "yes",         ["tgt_status"]),
    "L1_exist_dir_src_status":       TemplateMeta("L1", "exist", "bool", "yes",         ["src_status"]),
    "L1_exist_dir_both_status":      TemplateMeta("L1", "exist", "bool", "yes",         ["tgt_status", "src_status"]),
    "L1_exist_dir_dist":             TemplateMeta("L1", "exist", "bool", "yes",         ["dist"]),
    "L1_exist_dir_dist_tgt_status":  TemplateMeta("L1", "exist", "bool", "yes",         ["dist", "tgt_status"]),
    "L1_exist_dir_dist_src_status":  TemplateMeta("L1", "exist", "bool", "yes",         ["dist", "src_status"]),
    "L1_exist_dir_dist_both_status": TemplateMeta("L1", "exist", "bool", "yes",         ["dist", "tgt_status", "src_status"]),
    # ── L1 Status ─────────────────────────────────────────────────────────────
    "L1_status_dir":                 TemplateMeta("L1", "status", "open", "tgt_status", ["tgt_status"]),
    "L1_status_dir_src_status":      TemplateMeta("L1", "status", "open", "tgt_status", ["tgt_status", "src_status"]),
    "L1_status_dir_dist":            TemplateMeta("L1", "status", "open", "tgt_status", ["tgt_status", "dist"]),
    "L1_status_dir_src_status_dist": TemplateMeta("L1", "status", "open", "tgt_status", ["tgt_status", "src_status", "dist"]),
    "L1_status_dir_ask_src":         TemplateMeta("L1", "status", "open", "src_status", ["src_status"]),
    "L1_status_dir_ask_src_tgt_st":  TemplateMeta("L1", "status", "open", "src_status", ["src_status", "tgt_status"]),
    # ── L1 Type ───────────────────────────────────────────────────────────────
    "L1_type_dir":                   TemplateMeta("L1", "type",   "open", "tgt_type",   []),
    "L1_type_dir_src_status":        TemplateMeta("L1", "type",   "open", "tgt_type",   ["src_status"]),
    "L1_type_dir_dist":              TemplateMeta("L1", "type",   "open", "tgt_type",   ["dist"]),
    "L1_type_dir_tgt_status":        TemplateMeta("L1", "type",   "open", "tgt_type",   ["tgt_status"]),
    "L1_type_dir_both_status":       TemplateMeta("L1", "type",   "open", "tgt_type",   ["tgt_status", "src_status"]),
    # ── L1 Direction ──────────────────────────────────────────────────────────
    "L1_dir_basic":                  TemplateMeta("L1", "dir",    "open", "dir",         []),
    "L1_dir_tgt_status":             TemplateMeta("L1", "dir",    "open", "dir",         ["tgt_status"]),
    "L1_dir_src_status":             TemplateMeta("L1", "dir",    "open", "dir",         ["src_status"]),
    "L1_dir_both_status":            TemplateMeta("L1", "dir",    "open", "dir",         ["tgt_status", "src_status"]),
    "L1_dir_dist":                   TemplateMeta("L1", "dir",    "open", "dir",         ["dist"]),
    # ── L1 Distance ───────────────────────────────────────────────────────────
    "L1_dist_basic":                 TemplateMeta("L1", "dist",   "open", "dist_level",  ["dist"]),
    "L1_dist_tgt_status":            TemplateMeta("L1", "dist",   "open", "dist_level",  ["dist", "tgt_status"]),
    "L1_dist_src_status":            TemplateMeta("L1", "dist",   "open", "dist_level",  ["dist", "src_status"]),
    "L1_dist_both_status":           TemplateMeta("L1", "dist",   "open", "dist_level",  ["dist", "tgt_status", "src_status"]),
    "L1_dist_dir":                   TemplateMeta("L1", "dist",   "open", "dist_level",  ["dist"]),
    "L1_dist_dir_tgt_status":        TemplateMeta("L1", "dist",   "open", "dist_level",  ["dist", "tgt_status"]),

    # ── L2 Chain A Exist ──────────────────────────────────────────────────────
    "L2_exist_chain_A":              TemplateMeta("L2", "exist", "bool", "yes",           ["anc"]),
    "L2_exist_chain_A_tgt_status":   TemplateMeta("L2", "exist", "bool", "yes",           ["anc", "tgt_status"]),
    "L2_exist_chain_A_src_status":   TemplateMeta("L2", "exist", "bool", "yes",           ["anc", "src_status"]),
    "L2_exist_chain_A_anc_status":   TemplateMeta("L2", "exist", "bool", "yes",           ["anc", "anc_status"]),
    "L2_exist_chain_A_tgt_src":      TemplateMeta("L2", "exist", "bool", "yes",           ["anc", "tgt_status", "src_status"]),
    "L2_exist_chain_A_all":          TemplateMeta("L2", "exist", "bool", "yes",           ["anc", "tgt_status", "src_status", "anc_status"]),
    # ── L2 Chain A Status ─────────────────────────────────────────────────────
    "L2_status_chain_A":             TemplateMeta("L2", "status", "open", "tgt_status",   ["anc", "tgt_status"]),
    "L2_status_chain_A_src_status":  TemplateMeta("L2", "status", "open", "tgt_status",   ["anc", "tgt_status", "src_status"]),
    "L2_status_chain_A_anc_status":  TemplateMeta("L2", "status", "open", "tgt_status",   ["anc", "tgt_status", "anc_status"]),
    # ── L2 Chain A Type ───────────────────────────────────────────────────────
    "L2_type_chain_A":               TemplateMeta("L2", "type",   "open", "tgt_type",     ["anc"]),
    "L2_type_chain_A_src_status":    TemplateMeta("L2", "type",   "open", "tgt_type",     ["anc", "src_status"]),
    "L2_type_chain_A_tgt_status":    TemplateMeta("L2", "type",   "open", "tgt_type",     ["anc", "tgt_status"]),
    # ── L2 Chain B Exist ──────────────────────────────────────────────────────
    "L2_exist_chain_B":              TemplateMeta("L2", "exist", "bool", "yes",           ["beyond"]),
    "L2_exist_chain_B_beyond_status":TemplateMeta("L2", "exist", "bool", "yes",           ["beyond", "beyond_status"]),
    "L2_exist_chain_B_tgt_status":   TemplateMeta("L2", "exist", "bool", "yes",           ["beyond", "tgt_status"]),
    "L2_exist_chain_B_src_status":   TemplateMeta("L2", "exist", "bool", "yes",           ["beyond", "src_status"]),
    "L2_exist_chain_B_tgt_beyond":   TemplateMeta("L2", "exist", "bool", "yes",           ["beyond", "tgt_status", "beyond_status"]),
    "L2_exist_chain_B_all":          TemplateMeta("L2", "exist", "bool", "yes",           ["beyond", "tgt_status", "src_status", "beyond_status"]),
    # ── L2 Chain B Status ─────────────────────────────────────────────────────
    "L2_status_chain_B":             TemplateMeta("L2", "status", "open", "beyond_status",["beyond", "beyond_status"]),
    "L2_status_chain_B_tgt_status":  TemplateMeta("L2", "status", "open", "beyond_status",["beyond", "beyond_status", "tgt_status"]),
    "L2_status_chain_B_src_status":  TemplateMeta("L2", "status", "open", "beyond_status",["beyond", "beyond_status", "src_status"]),
    # ── L2 Chain B Type ───────────────────────────────────────────────────────
    "L2_type_chain_B":               TemplateMeta("L2", "type",   "open", "beyond_type",  ["beyond"]),
    "L2_type_chain_B_tgt_status":    TemplateMeta("L2", "type",   "open", "beyond_type",  ["beyond", "tgt_status"]),
    # ── L2 Reverse-chain Status ───────────────────────────────────────────────
    "L2_status_ask_tgt_in_B":        TemplateMeta("L2", "status", "open", "tgt_status",   ["beyond", "tgt_status"]),
    "L2_status_ask_src_in_A":        TemplateMeta("L2", "status", "open", "src_status",   ["anc", "src_status"]),
}


# ─────────────────────────────────────────────────────────────────────────────
# 模板字符串（300 条）
# ─────────────────────────────────────────────────────────────────────────────

GAP_TEMPLATES: Dict[str, List[str]] = {

    # ══════════════════════════════════ L0 ════════════════════════════════════
    # 变量：{type} {status} {dir} {dist}

    "L0_exist_basic": [
        "Is there a {type} in the scene?",
        "Does a {type} appear in this scene?",
        "Can a {type} be found in this scene?",
        "Is a {type} present in the current scene?",
    ],
    "L0_exist_status": [
        "Is there a {status} {type} in the scene?",
        "Does a {status} {type} appear in this scene?",
        "Can a {status} {type} be found in this scene?",
        "Is a {status} {type} present in the current scene?",
    ],
    "L0_exist_dir": [
        "Is there a {type} to the {dir}?",
        "Does a {type} exist on the {dir} side?",
        "Can a {type} be found to the {dir}?",
        "Is any {type} located to the {dir}?",
    ],
    "L0_exist_dir_status": [
        "Is there a {status} {type} to the {dir}?",
        "Does a {status} {type} exist on the {dir} side?",
        "Can a {status} {type} be found to the {dir}?",
        "Is any {status} {type} located to the {dir}?",
    ],
    "L0_exist_dist": [
        "Is there a {type} within {dist} range?",
        "Is there a {type} {dist} away?",
        "Is any {type} {dist} from here?",
        "Can a {type} be found at {dist} distance?",
    ],
    "L0_exist_dir_dist": [
        "Is there a {type} {dist} to the {dir}?",
        "Is there a {type} {dist} on the {dir} side?",
        "Can a {type} be found {dist} to the {dir}?",
        "Is any {type} {dist} in the {dir} direction?",
    ],

    "L0_status_basic": [
        "What is the status of the {type}?",
        "What is the {type} doing?",
        "What state is the {type} in?",
        "Describe the current state of the {type}.",
    ],
    "L0_status_dir": [
        "What is the status of the {type} to the {dir}?",
        "What is the {type} on the {dir} side doing?",
        "What state is the {type} to the {dir} in?",
        "Describe the state of the {type} to the {dir}.",
    ],
    "L0_status_dist": [
        "What is the status of the {dist} {type}?",
        "What is the {type} that is {dist} away doing?",
        "What state is the {dist} {type} in?",
        "Describe the state of the {type} at {dist} range.",
    ],
    "L0_status_dir_dist": [
        "What is the status of the {type} {dist} to the {dir}?",
        "What is the {type} {dist} to the {dir} doing?",
        "What state is the {type} {dist} in the {dir} in?",
        "Describe the state of the {type} {dist} on the {dir} side.",
    ],

    "L0_dir_basic": [
        "In which direction is the {type}?",
        "Where is the {type} located relative to the ego vehicle?",
        "Which side is the {type} on?",
        "What direction can the {type} be found?",
    ],
    "L0_dir_status": [
        "In which direction is the {status} {type}?",
        "Where is the {status} {type} located?",
        "Which side is the {status} {type} on?",
        "What direction can the {status} {type} be found?",
    ],
    "L0_dir_dist": [
        "In which direction is the {dist} {type}?",
        "Where is the {type} that is {dist} away?",
        "Which side is the {type} at {dist} range on?",
        "What direction is the {type} that is {dist} away?",
    ],

    "L0_dist_basic": [
        "How far is the {type}?",
        "What is the distance to the {type}?",
        "How close is the {type}?",
        "At what range is the {type}?",
    ],
    "L0_dist_status": [
        "How far is the {status} {type}?",
        "What is the distance to the {status} {type}?",
        "How close is the {status} {type}?",
        "At what range is the {status} {type}?",
    ],
    "L0_dist_dir": [
        "How far is the {type} to the {dir}?",
        "What is the distance to the {type} on the {dir} side?",
        "How close is the {type} to the {dir}?",
        "At what range is the {type} to the {dir}?",
    ],

    "L0_type_dir": [
        "What type of object is to the {dir}?",
        "What is to the {dir}?",
        "Which type of object can be found to the {dir}?",
        "What object is located to the {dir}?",
    ],
    "L0_type_dir_dist": [
        "What type of object is {dist} to the {dir}?",
        "What is {dist} on the {dir} side?",
        "Which type of object is {dist} from here to the {dir}?",
        "What object can be found {dist} to the {dir}?",
    ],
    "L0_type_status": [
        "What {status} object is in the scene?",
        "Which type of object is {status} in the scene?",
        "What kind of object has a {status} status?",
        "Which object in the scene is {status}?",
    ],
    "L0_type_dir_status": [
        "What {status} object is to the {dir}?",
        "Which type of {status} object is on the {dir} side?",
        "What kind of {status} object is to the {dir}?",
        "Which {status} object can be found to the {dir}?",
    ],

    # ══════════════════════════════════ L1 ════════════════════════════════════
    # 变量：{src_type} {src_status} {tgt_type} {tgt_status} {dir} {dist}

    "L1_exist_dir": [
        "Is there a {tgt_type} to the {dir} of the {src_type}?",
        "Does a {tgt_type} exist to the {dir} of the {src_type}?",
        "Can a {tgt_type} be found to the {dir} of the {src_type}?",
        "Is any {tgt_type} located to the {dir} of the {src_type}?",
    ],
    "L1_exist_dir_tgt_status": [
        "Is there a {tgt_status} {tgt_type} to the {dir} of the {src_type}?",
        "Does a {tgt_status} {tgt_type} exist to the {dir} of the {src_type}?",
        "Can a {tgt_status} {tgt_type} be found to the {dir} of the {src_type}?",
        "Is any {tgt_status} {tgt_type} located to the {dir} of the {src_type}?",
    ],
    "L1_exist_dir_src_status": [
        "Is there a {tgt_type} to the {dir} of the {src_status} {src_type}?",
        "Does a {tgt_type} exist to the {dir} of the {src_status} {src_type}?",
        "Can a {tgt_type} be found to the {dir} of the {src_status} {src_type}?",
        "Is any {tgt_type} located to the {dir} of the {src_status} {src_type}?",
    ],
    "L1_exist_dir_both_status": [
        "Is there a {tgt_status} {tgt_type} to the {dir} of the {src_status} {src_type}?",
        "Does a {tgt_status} {tgt_type} exist to the {dir} of the {src_status} {src_type}?",
        "Can a {tgt_status} {tgt_type} be found to the {dir} of the {src_status} {src_type}?",
        "Is any {tgt_status} {tgt_type} located to the {dir} of the {src_status} {src_type}?",
    ],
    "L1_exist_dir_dist": [
        "Is there a {tgt_type} {dist} to the {dir} of the {src_type}?",
        "Does a {tgt_type} exist {dist} to the {dir} of the {src_type}?",
        "Can a {tgt_type} be found {dist} to the {dir} of the {src_type}?",
        "Is any {tgt_type} {dist} in the {dir} direction of the {src_type}?",
    ],
    "L1_exist_dir_dist_tgt_status": [
        "Is there a {tgt_status} {tgt_type} {dist} to the {dir} of the {src_type}?",
        "Does a {tgt_status} {tgt_type} exist {dist} to the {dir} of the {src_type}?",
        "Can a {tgt_status} {tgt_type} be found {dist} to the {dir} of the {src_type}?",
        "Is any {tgt_status} {tgt_type} {dist} in the {dir} direction of the {src_type}?",
    ],
    "L1_exist_dir_dist_src_status": [
        "Is there a {tgt_type} {dist} to the {dir} of the {src_status} {src_type}?",
        "Does a {tgt_type} exist {dist} to the {dir} of the {src_status} {src_type}?",
        "Can a {tgt_type} be found {dist} to the {dir} of the {src_status} {src_type}?",
        "Is any {tgt_type} {dist} in the {dir} direction of the {src_status} {src_type}?",
    ],
    "L1_exist_dir_dist_both_status": [
        "Is there a {tgt_status} {tgt_type} {dist} to the {dir} of the {src_status} {src_type}?",
        "Does a {tgt_status} {tgt_type} exist {dist} to the {dir} of the {src_status} {src_type}?",
        "Can a {tgt_status} {tgt_type} be found {dist} to the {dir} of the {src_status} {src_type}?",
        "Is any {tgt_status} {tgt_type} {dist} in the {dir} direction of the {src_status} {src_type}?",
    ],

    "L1_status_dir": [
        "What is the status of the {tgt_type} to the {dir} of the {src_type}?",
        "What is the {tgt_type} to the {dir} of the {src_type} doing?",
        "What state is the {tgt_type} to the {dir} of the {src_type} in?",
        "Describe the status of the {tgt_type} to the {dir} of the {src_type}.",
    ],
    "L1_status_dir_src_status": [
        "What is the status of the {tgt_type} to the {dir} of the {src_status} {src_type}?",
        "What is the {tgt_type} to the {dir} of the {src_status} {src_type} doing?",
        "What state is the {tgt_type} to the {dir} of the {src_status} {src_type} in?",
        "Describe the status of the {tgt_type} to the {dir} of the {src_status} {src_type}.",
    ],
    "L1_status_dir_dist": [
        "What is the status of the {tgt_type} {dist} to the {dir} of the {src_type}?",
        "What is the {tgt_type} {dist} to the {dir} of the {src_type} doing?",
        "What state is the {tgt_type} {dist} to the {dir} of the {src_type} in?",
        "Describe the status of the {tgt_type} {dist} to the {dir} of the {src_type}.",
    ],
    "L1_status_dir_src_status_dist": [
        "What is the status of the {tgt_type} {dist} to the {dir} of the {src_status} {src_type}?",
        "What is the {tgt_type} {dist} to the {dir} of the {src_status} {src_type} doing?",
        "What state is the {tgt_type} {dist} to the {dir} of the {src_status} {src_type} in?",
        "Describe the status of the {tgt_type} {dist} to the {dir} of the {src_status} {src_type}.",
    ],
    "L1_status_dir_ask_src": [
        "What is the status of the {src_type} that has a {tgt_type} to its {dir}?",
        "What is the {src_type} with a {tgt_type} to its {dir} doing?",
        "What state is the {src_type} in, given it has a {tgt_type} to its {dir}?",
        "Describe the status of the {src_type} that has a {tgt_type} on its {dir} side.",
    ],
    "L1_status_dir_ask_src_tgt_st": [
        "What is the status of the {src_type} that has a {tgt_status} {tgt_type} to its {dir}?",
        "What is the {src_type} with a {tgt_status} {tgt_type} to its {dir} doing?",
        "What state is the {src_type} in, given it has a {tgt_status} {tgt_type} to its {dir}?",
        "Describe the status of the {src_type} that has a {tgt_status} {tgt_type} on its {dir} side.",
    ],

    "L1_type_dir": [
        "What type of object is to the {dir} of the {src_type}?",
        "What is to the {dir} of the {src_type}?",
        "Which type of object can be found to the {dir} of the {src_type}?",
        "What object is located to the {dir} of the {src_type}?",
    ],
    "L1_type_dir_src_status": [
        "What type of object is to the {dir} of the {src_status} {src_type}?",
        "What is to the {dir} of the {src_status} {src_type}?",
        "Which type of object can be found to the {dir} of the {src_status} {src_type}?",
        "What object is located to the {dir} of the {src_status} {src_type}?",
    ],
    "L1_type_dir_dist": [
        "What type of object is {dist} to the {dir} of the {src_type}?",
        "What is {dist} to the {dir} of the {src_type}?",
        "Which type of object is {dist} from the {src_type} in the {dir} direction?",
        "What object can be found {dist} to the {dir} of the {src_type}?",
    ],
    "L1_type_dir_tgt_status": [
        "What {tgt_status} object is to the {dir} of the {src_type}?",
        "Which type of {tgt_status} object can be found to the {dir} of the {src_type}?",
        "What kind of {tgt_status} object is located to the {dir} of the {src_type}?",
        "Identify the {tgt_status} object to the {dir} of the {src_type}.",
    ],
    "L1_type_dir_both_status": [
        "What {tgt_status} object is to the {dir} of the {src_status} {src_type}?",
        "Which type of {tgt_status} object can be found to the {dir} of the {src_status} {src_type}?",
        "What kind of {tgt_status} object is located to the {dir} of the {src_status} {src_type}?",
        "Identify the {tgt_status} object to the {dir} of the {src_status} {src_type}.",
    ],

    "L1_dir_basic": [
        "In which direction is the {tgt_type} relative to the {src_type}?",
        "Where is the {tgt_type} in relation to the {src_type}?",
        "What direction is the {tgt_type} from the {src_type}?",
        "On which side is the {tgt_type} relative to the {src_type}?",
    ],
    "L1_dir_tgt_status": [
        "In which direction is the {tgt_status} {tgt_type} relative to the {src_type}?",
        "Where is the {tgt_status} {tgt_type} in relation to the {src_type}?",
        "What direction is the {tgt_status} {tgt_type} from the {src_type}?",
        "On which side is the {tgt_status} {tgt_type} relative to the {src_type}?",
    ],
    "L1_dir_src_status": [
        "In which direction is the {tgt_type} relative to the {src_status} {src_type}?",
        "Where is the {tgt_type} in relation to the {src_status} {src_type}?",
        "What direction is the {tgt_type} from the {src_status} {src_type}?",
        "On which side is the {tgt_type} relative to the {src_status} {src_type}?",
    ],
    "L1_dir_both_status": [
        "In which direction is the {tgt_status} {tgt_type} relative to the {src_status} {src_type}?",
        "Where is the {tgt_status} {tgt_type} in relation to the {src_status} {src_type}?",
        "What direction is the {tgt_status} {tgt_type} from the {src_status} {src_type}?",
        "On which side is the {tgt_status} {tgt_type} relative to the {src_status} {src_type}?",
    ],
    "L1_dir_dist": [
        "In which direction is the {dist} {tgt_type} relative to the {src_type}?",
        "Where is the {tgt_type} that is {dist} from the {src_type}?",
        "What direction is the {dist} {tgt_type} from the {src_type}?",
        "On which side is the {tgt_type} that is {dist} away from the {src_type}?",
    ],

    "L1_dist_basic": [
        "How far is the {tgt_type} from the {src_type}?",
        "What is the distance between the {src_type} and the {tgt_type}?",
        "How close is the {tgt_type} to the {src_type}?",
        "At what range is the {tgt_type} from the {src_type}?",
    ],
    "L1_dist_tgt_status": [
        "How far is the {tgt_status} {tgt_type} from the {src_type}?",
        "What is the distance from the {src_type} to the {tgt_status} {tgt_type}?",
        "How close is the {tgt_status} {tgt_type} to the {src_type}?",
        "At what range is the {tgt_status} {tgt_type} from the {src_type}?",
    ],
    "L1_dist_src_status": [
        "How far is the {tgt_type} from the {src_status} {src_type}?",
        "What is the distance from the {src_status} {src_type} to the {tgt_type}?",
        "How close is the {tgt_type} to the {src_status} {src_type}?",
        "At what range is the {tgt_type} from the {src_status} {src_type}?",
    ],
    "L1_dist_both_status": [
        "How far is the {tgt_status} {tgt_type} from the {src_status} {src_type}?",
        "What is the distance from the {src_status} {src_type} to the {tgt_status} {tgt_type}?",
        "How close is the {tgt_status} {tgt_type} to the {src_status} {src_type}?",
        "At what range is the {tgt_status} {tgt_type} from the {src_status} {src_type}?",
    ],
    "L1_dist_dir": [
        "How far is the {tgt_type} to the {dir} of the {src_type}?",
        "What is the distance to the {tgt_type} on the {dir} side of the {src_type}?",
        "How close is the {tgt_type} to the {dir} of the {src_type}?",
        "At what range is the {tgt_type} to the {dir} of the {src_type}?",
    ],
    "L1_dist_dir_tgt_status": [
        "How far is the {tgt_status} {tgt_type} to the {dir} of the {src_type}?",
        "What is the distance to the {tgt_status} {tgt_type} on the {dir} side of the {src_type}?",
        "How close is the {tgt_status} {tgt_type} to the {dir} of the {src_type}?",
        "At what range is the {tgt_status} {tgt_type} to the {dir} of the {src_type}?",
    ],

    # ══════════════════════════════════ L2 ════════════════════════════════════
    # 链 A 变量：{anc_type} {anc_status} {dir_as} {src_type} {src_status} {dir_st} {tgt_type} {tgt_status}
    # 链 B 变量：{src_type} {src_status} {dir_st} {tgt_type} {tgt_status} {dir_tb} {beyond_type} {beyond_status}

    "L2_exist_chain_A": [
        "Is there a {tgt_type} to the {dir_st} of the {src_type} which is to the {dir_as} of the {anc_type}?",
        "Does a {tgt_type} exist to the {dir_st} of the {src_type} that is to the {dir_as} of the {anc_type}?",
        "Can a {tgt_type} be found to the {dir_st} of the {src_type}, which is to the {dir_as} of the {anc_type}?",
        "Is any {tgt_type} located to the {dir_st} of the {src_type} that sits to the {dir_as} of the {anc_type}?",
    ],
    "L2_exist_chain_A_tgt_status": [
        "Is there a {tgt_status} {tgt_type} to the {dir_st} of the {src_type} which is to the {dir_as} of the {anc_type}?",
        "Does a {tgt_status} {tgt_type} exist to the {dir_st} of the {src_type} that is to the {dir_as} of the {anc_type}?",
        "Can a {tgt_status} {tgt_type} be found to the {dir_st} of the {src_type}, which is to the {dir_as} of the {anc_type}?",
        "Is any {tgt_status} {tgt_type} to the {dir_st} of the {src_type} that sits to the {dir_as} of the {anc_type}?",
    ],
    "L2_exist_chain_A_src_status": [
        "Is there a {tgt_type} to the {dir_st} of the {src_status} {src_type} which is to the {dir_as} of the {anc_type}?",
        "Does a {tgt_type} exist to the {dir_st} of the {src_status} {src_type} that is to the {dir_as} of the {anc_type}?",
        "Can a {tgt_type} be found to the {dir_st} of the {src_status} {src_type}, which is to the {dir_as} of the {anc_type}?",
        "Is any {tgt_type} to the {dir_st} of the {src_status} {src_type} that sits to the {dir_as} of the {anc_type}?",
    ],
    "L2_exist_chain_A_anc_status": [
        "Is there a {tgt_type} to the {dir_st} of the {src_type} which is to the {dir_as} of the {anc_status} {anc_type}?",
        "Does a {tgt_type} exist to the {dir_st} of the {src_type} that is to the {dir_as} of the {anc_status} {anc_type}?",
        "Can a {tgt_type} be found to the {dir_st} of the {src_type}, which is to the {dir_as} of the {anc_status} {anc_type}?",
        "Is any {tgt_type} to the {dir_st} of the {src_type} that sits to the {dir_as} of the {anc_status} {anc_type}?",
    ],
    "L2_exist_chain_A_tgt_src": [
        "Is there a {tgt_status} {tgt_type} to the {dir_st} of the {src_status} {src_type} which is to the {dir_as} of the {anc_type}?",
        "Does a {tgt_status} {tgt_type} exist to the {dir_st} of the {src_status} {src_type} that is to the {dir_as} of the {anc_type}?",
        "Can a {tgt_status} {tgt_type} be found to the {dir_st} of the {src_status} {src_type}, to the {dir_as} of the {anc_type}?",
        "Is any {tgt_status} {tgt_type} to the {dir_st} of the {src_status} {src_type} near the {anc_type} to its {dir_as}?",
    ],
    "L2_exist_chain_A_all": [
        "Is there a {tgt_status} {tgt_type} to the {dir_st} of the {src_status} {src_type} which is to the {dir_as} of the {anc_status} {anc_type}?",
        "Does a {tgt_status} {tgt_type} exist to the {dir_st} of the {src_status} {src_type} that is to the {dir_as} of the {anc_status} {anc_type}?",
        "Can a {tgt_status} {tgt_type} be found to the {dir_st} of the {src_status} {src_type}, which is to the {dir_as} of the {anc_status} {anc_type}?",
        "Is any {tgt_status} {tgt_type} to the {dir_st} of {src_status} {src_type} near {anc_status} {anc_type} to its {dir_as}?",
    ],

    "L2_status_chain_A": [
        "What is the status of the {tgt_type} to the {dir_st} of the {src_type} which is to the {dir_as} of the {anc_type}?",
        "What is the {tgt_type} to the {dir_st} of the {src_type} that is to the {dir_as} of the {anc_type} doing?",
        "What state is the {tgt_type} to the {dir_st} of the {src_type} (to the {dir_as} of the {anc_type}) in?",
        "Describe the status of the {tgt_type} to the {dir_st} of the {src_type}, which is to the {dir_as} of the {anc_type}.",
    ],
    "L2_status_chain_A_src_status": [
        "What is the status of the {tgt_type} to the {dir_st} of the {src_status} {src_type} which is to the {dir_as} of the {anc_type}?",
        "What is the {tgt_type} to the {dir_st} of the {src_status} {src_type} near the {anc_type} doing?",
        "What state is the {tgt_type} to the {dir_st} of the {src_status} {src_type} that is to the {dir_as} of the {anc_type} in?",
        "Describe the status of the {tgt_type} to the {dir_st} of the {src_status} {src_type} (to the {dir_as} of the {anc_type}).",
    ],
    "L2_status_chain_A_anc_status": [
        "What is the status of the {tgt_type} to the {dir_st} of the {src_type} which is to the {dir_as} of the {anc_status} {anc_type}?",
        "What is the {tgt_type} to the {dir_st} of the {src_type} near the {anc_status} {anc_type} doing?",
        "What state is the {tgt_type} to the {dir_st} of the {src_type} that is to the {dir_as} of the {anc_status} {anc_type} in?",
        "Describe the status of the {tgt_type} to the {dir_st} of {src_type}, which is to the {dir_as} of the {anc_status} {anc_type}.",
    ],

    "L2_type_chain_A": [
        "What type of object is to the {dir_st} of the {src_type} which is to the {dir_as} of the {anc_type}?",
        "What is to the {dir_st} of the {src_type} that is to the {dir_as} of the {anc_type}?",
        "Which type of object can be found to the {dir_st} of the {src_type} (to the {dir_as} of the {anc_type})?",
        "What object is located to the {dir_st} of the {src_type} that sits to the {dir_as} of the {anc_type}?",
    ],
    "L2_type_chain_A_src_status": [
        "What type of object is to the {dir_st} of the {src_status} {src_type} which is to the {dir_as} of the {anc_type}?",
        "What is to the {dir_st} of the {src_status} {src_type} that is to the {dir_as} of the {anc_type}?",
        "Which type of object can be found to the {dir_st} of the {src_status} {src_type} (to the {dir_as} of the {anc_type})?",
        "What object is located to the {dir_st} of the {src_status} {src_type} that sits to the {dir_as} of the {anc_type}?",
    ],
    "L2_type_chain_A_tgt_status": [
        "What {tgt_status} object is to the {dir_st} of the {src_type} which is to the {dir_as} of the {anc_type}?",
        "Which type of {tgt_status} object can be found to the {dir_st} of the {src_type} (to the {dir_as} of the {anc_type})?",
        "What kind of {tgt_status} object is to the {dir_st} of the {src_type} that is to the {dir_as} of the {anc_type}?",
        "Identify the {tgt_status} object to the {dir_st} of the {src_type} (near {anc_type} to its {dir_as}).",
    ],

    "L2_exist_chain_B": [
        "Is there a {beyond_type} to the {dir_tb} of the {tgt_type} that is to the {dir_st} of the {src_type}?",
        "Does a {beyond_type} exist to the {dir_tb} of the {tgt_type} which is to the {dir_st} of the {src_type}?",
        "Can a {beyond_type} be found to the {dir_tb} of the {tgt_type} that is to the {dir_st} of the {src_type}?",
        "Is any {beyond_type} located to the {dir_tb} of the {tgt_type} that sits to the {dir_st} of the {src_type}?",
    ],
    "L2_exist_chain_B_beyond_status": [
        "Is there a {beyond_status} {beyond_type} to the {dir_tb} of the {tgt_type} that is to the {dir_st} of the {src_type}?",
        "Does a {beyond_status} {beyond_type} exist to the {dir_tb} of the {tgt_type} which is to the {dir_st} of the {src_type}?",
        "Can a {beyond_status} {beyond_type} be found to the {dir_tb} of the {tgt_type} that is to the {dir_st} of the {src_type}?",
        "Is any {beyond_status} {beyond_type} to the {dir_tb} of the {tgt_type} that sits to the {dir_st} of the {src_type}?",
    ],
    "L2_exist_chain_B_tgt_status": [
        "Is there a {beyond_type} to the {dir_tb} of the {tgt_status} {tgt_type} that is to the {dir_st} of the {src_type}?",
        "Does a {beyond_type} exist to the {dir_tb} of the {tgt_status} {tgt_type} which is to the {dir_st} of the {src_type}?",
        "Can a {beyond_type} be found to the {dir_tb} of the {tgt_status} {tgt_type} that is to the {dir_st} of the {src_type}?",
        "Is any {beyond_type} to the {dir_tb} of the {tgt_status} {tgt_type} that sits to the {dir_st} of the {src_type}?",
    ],
    "L2_exist_chain_B_src_status": [
        "Is there a {beyond_type} to the {dir_tb} of the {tgt_type} that is to the {dir_st} of the {src_status} {src_type}?",
        "Does a {beyond_type} exist to the {dir_tb} of the {tgt_type} which is to the {dir_st} of the {src_status} {src_type}?",
        "Can a {beyond_type} be found to the {dir_tb} of the {tgt_type} that is to the {dir_st} of the {src_status} {src_type}?",
        "Is any {beyond_type} to the {dir_tb} of the {tgt_type} that sits to the {dir_st} of the {src_status} {src_type}?",
    ],
    "L2_exist_chain_B_tgt_beyond": [
        "Is there a {beyond_status} {beyond_type} to the {dir_tb} of the {tgt_status} {tgt_type} that is to the {dir_st} of the {src_type}?",
        "Does a {beyond_status} {beyond_type} exist to the {dir_tb} of the {tgt_status} {tgt_type} which is to the {dir_st} of the {src_type}?",
        "Can a {beyond_status} {beyond_type} be found to the {dir_tb} of the {tgt_status} {tgt_type} to the {dir_st} of the {src_type}?",
        "Is any {beyond_status} {beyond_type} to the {dir_tb} of {tgt_status} {tgt_type} that sits to the {dir_st} of the {src_type}?",
    ],
    "L2_exist_chain_B_all": [
        "Is there a {beyond_status} {beyond_type} to the {dir_tb} of the {tgt_status} {tgt_type} that is to the {dir_st} of the {src_status} {src_type}?",
        "Does a {beyond_status} {beyond_type} exist to the {dir_tb} of the {tgt_status} {tgt_type} which is to the {dir_st} of the {src_status} {src_type}?",
        "Can a {beyond_status} {beyond_type} be found to the {dir_tb} of the {tgt_status} {tgt_type} to the {dir_st} of {src_status} {src_type}?",
        "Is any {beyond_status} {beyond_type} to the {dir_tb} of {tgt_status} {tgt_type} (to the {dir_st} of {src_status} {src_type}) present?",
    ],

    "L2_status_chain_B": [
        "What is the status of the {beyond_type} to the {dir_tb} of the {tgt_type} that is to the {dir_st} of the {src_type}?",
        "What is the {beyond_type} to the {dir_tb} of the {tgt_type} (to the {dir_st} of the {src_type}) doing?",
        "What state is the {beyond_type} to the {dir_tb} of the {tgt_type} that is to the {dir_st} of the {src_type} in?",
        "Describe the status of the {beyond_type} to the {dir_tb} of the {tgt_type} (to the {dir_st} of the {src_type}).",
    ],
    "L2_status_chain_B_tgt_status": [
        "What is the status of the {beyond_type} to the {dir_tb} of the {tgt_status} {tgt_type} that is to the {dir_st} of the {src_type}?",
        "What is the {beyond_type} to the {dir_tb} of the {tgt_status} {tgt_type} (to the {dir_st} of the {src_type}) doing?",
        "What state is the {beyond_type} to the {dir_tb} of the {tgt_status} {tgt_type} that is to the {dir_st} of {src_type} in?",
        "Describe the status of the {beyond_type} beyond the {tgt_status} {tgt_type} to the {dir_st} of the {src_type}.",
    ],
    "L2_status_chain_B_src_status": [
        "What is the status of the {beyond_type} to the {dir_tb} of the {tgt_type} that is to the {dir_st} of the {src_status} {src_type}?",
        "What is the {beyond_type} to the {dir_tb} of the {tgt_type} (to the {dir_st} of the {src_status} {src_type}) doing?",
        "What state is the {beyond_type} to the {dir_tb} of the {tgt_type} that is to the {dir_st} of {src_status} {src_type} in?",
        "Describe the status of the {beyond_type} beyond the {tgt_type} to the {dir_st} of the {src_status} {src_type}.",
    ],

    "L2_type_chain_B": [
        "What type of object is to the {dir_tb} of the {tgt_type} that is to the {dir_st} of the {src_type}?",
        "What is to the {dir_tb} of the {tgt_type} which is to the {dir_st} of the {src_type}?",
        "Which type of object can be found to the {dir_tb} of the {tgt_type} (to the {dir_st} of the {src_type})?",
        "What object is located to the {dir_tb} of the {tgt_type} that sits to the {dir_st} of the {src_type}?",
    ],
    "L2_type_chain_B_tgt_status": [
        "What type of object is to the {dir_tb} of the {tgt_status} {tgt_type} that is to the {dir_st} of the {src_type}?",
        "What is to the {dir_tb} of the {tgt_status} {tgt_type} which is to the {dir_st} of the {src_type}?",
        "Which type of object can be found to the {dir_tb} of the {tgt_status} {tgt_type} (to the {dir_st} of the {src_type})?",
        "What object is to the {dir_tb} of the {tgt_status} {tgt_type} that sits to the {dir_st} of the {src_type}?",
    ],

    "L2_status_ask_tgt_in_B": [
        "What is the status of the {tgt_type} to the {dir_st} of the {src_type} that has a {beyond_type} to its {dir_tb}?",
        "What is the {tgt_type} (to the {dir_st} of the {src_type}) with a {beyond_type} to its {dir_tb} doing?",
        "What state is the {tgt_type} to the {dir_st} of the {src_type} in, given it has a {beyond_type} to its {dir_tb}?",
        "Describe the status of the {tgt_type} to the {dir_st} of the {src_type} which has a {beyond_type} to its {dir_tb}.",
    ],
    "L2_status_ask_src_in_A": [
        "What is the status of the {src_type} to the {dir_as} of the {anc_type} that has a {tgt_type} to its {dir_st}?",
        "What is the {src_type} near the {anc_type} (to its {dir_as}) with a {tgt_type} to its {dir_st} doing?",
        "What state is the {src_type} to the {dir_as} of the {anc_type} in, given it has a {tgt_type} to its {dir_st}?",
        "Describe the status of the {src_type} to the {dir_as} of the {anc_type} which has a {tgt_type} to its {dir_st}.",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# 运行期工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _is_known(val: Optional[str]) -> bool:
    """字段有效性检查：非 None、非空字符串、非 'unknown'。"""
    return bool(val) and str(val).strip() not in ("", "unknown", "null", "None")


def check_requires(requires: List[str], ctx: dict) -> bool:
    """检查模板前提条件是否满足。"""
    src_id = ctx.get("src_id", "")
    for req in requires:
        if req == "ego_src":
            if src_id != "ego":
                return False
        elif req == "tgt_status":
            if not _is_known(ctx.get("tgt_status")):
                return False
        elif req == "src_status":
            if not _is_known(ctx.get("src_status")):
                return False
        elif req == "anc_status":
            if not _is_known(ctx.get("anc_status")):
                return False
        elif req == "beyond_status":
            if not _is_known(ctx.get("beyond_status")):
                return False
        elif req == "dist":
            if not _is_known(ctx.get("dist_level")):
                return False
        elif req == "anc":
            if not ctx.get("anc_id"):
                return False
        elif req == "beyond":
            if not ctx.get("beyond_id"):
                return False
    return True


def resolve_answer(
    answer_source: str,
    ctx: dict,
    template_vars: dict,
) -> Optional[str]:
    """从上下文或模板变量中提取答案值。"""
    if answer_source == "yes":
        return "yes"
    # 优先直接查 ctx
    val = ctx.get(answer_source)
    if val is None:
        # 回退到 template_vars（如 dir、tgt_type 等已做自然语言映射的字段）
        val = template_vars.get(answer_source)
    if not _is_known(str(val) if val is not None else None):
        return None
    return str(val)


def get_applicable_templates(ctx: dict) -> List[str]:
    """返回在当前上下文中满足前提条件的所有模板 ID 列表。"""
    return [
        tid
        for tid, meta in TEMPLATE_META.items()
        if check_requires(meta.requires, ctx)
    ]


def pick_variation(template_id: str) -> str:
    """随机选取指定模板的一个语义变体。"""
    return random.choice(GAP_TEMPLATES[template_id])
