"""
Gap Pipeline — Constraint Method Library
插拔式约束方法库，用于将候选集收束到唯一答案。

每个 ConstraintMethod 实现三步接口：
    can_apply(gap_target, others, ctx)  → bool
    find_value(gap_target, others, ctx) → Dict   (要加进问题的约束值)
    render(tvars, value)                → str    (约束后的问题文本)

ConstraintChain 按优先级顺序试用方法，找到第一个能使候选集收束到1的即止。
收束不了则最终退到 FallbackYesNo。

方法优先级（越靠前越优先，越自然，视觉模型越容易回答）：
    P1.  TypeFilter            目标类型唯一
    P2.  StatusAnchor          目标状态唯一
    P3.  TypeStatusAnchor      类型+状态组合
    P4.  Dir8Refine            子方向细化（dir8 vs dir4）
    P5.  DualReference         两个参考点方向交集（需 ego_dir8）
    P6.  DistOrder             距离档位序 closest/farthest
    P7.  TypeDistCombo         类型+距离档位
    P8.  TypeDir8DistCombo     类型+dir8+距离档位
    P9.  AllPropsCombo         四属性全组合
    P10. OrdinalByDistance     按实际浮点距离排序（需 actual_dist）
    P11. TwoHopReferent        单二跳 referent 唯一（需 referents 预取）
    P12. DualHopReferent       双二跳 referent 交集
    P13. AnchorIntro           引入 src 锡点
    P14. CountFallback         转为计数题
    P15. FallbackYesNo         啤底存在性

参考：
    NuScenes-QA (AAAI 2024) 的问题模式，
    + 我们自己对 dist_order / anchor_intro 的扩展。
"""
from __future__ import annotations

import itertools
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_logger = logging.getLogger("gap_pipeline.constraint_chain")

# 距离档位排序
_DIST_RANK: Dict[str, int] = {
    "very_close": 0,
    "close": 1,
    "medium": 2,
    "far": 3,
}

_STATIONARY = frozenset({"stopped", "parked", "standing", "not_standing",
                          "sitting", "not standing", "lying_down"})


def _is_stationary(s: str) -> bool:
    return s.lower() in _STATIONARY if s else False


# ---------------------------------------------------------------------------
# 结果结构
# ---------------------------------------------------------------------------

@dataclass
class TightenResult:
    question: str
    answer: str
    is_unique: bool                          # True=唯一锁定 False=fallback
    method_used: str = ""                    # 使用的约束方法名
    yesno_fallback: bool = False
    count_fallback: bool = False
    # 逐方法计时（ms）：method_name → 该方法在 tighten 中总耗时
    method_timings: Dict[str, float] = field(default_factory=dict)
    # 全部尝试过的方法名列表（按顺序）
    methods_tried: List[str] = field(default_factory=list)
    # 最终生效的约束属性值（用于验证 Cypher 生成）
    value: Dict[str, Any] = field(default_factory=dict)
    # L2 方法所用的参照对象 ID（pipe分隔）—— n_referents 验证的数据源
    # two_hop: "car9"   dual_hop: "car9|car15"   attr+two_hop: "car9"   其他: ""
    referent_ids: str = ""
    # 逐方法尝试记录（用于 RQ1 消融实验）
    # 每个元素：{method: str, success: bool, time_ms: float, remaining_n: int}
    trace_log: List[Dict[str, Any]] = field(default_factory=list)

    def format_trace(self) -> str:
        """格式化为 'type(F,0.02ms,14)->two_hop(S,22.7ms,1)'。
        F=失败未唯一  S=成功唯一，最后的数字是剩余候选数。
        """
        parts = []
        for item in self.trace_log:
            flag  = "S" if item["success"] else "F"
            rem   = item.get("remaining_n", "?")
            t_ms  = item["time_ms"]
            parts.append(f"{item['method']}({flag},{t_ms:.2f}ms,{rem})")
        return "->".join(parts)

    @property
    def n_failed_attempts(self) -> int:
        return sum(1 for item in self.trace_log if not item["success"])


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class ConstraintMethod(ABC):
    """单个约束方法的接口。"""

    name: str = "base"
    priority: int = 99

    # ---- 三步接口 ----

    @abstractmethod
    def can_apply(
        self,
        gap_target: Dict,
        others: List[Dict],
        ctx: Dict,
    ) -> bool:
        """能否在当前场景应用本方法？"""

    @abstractmethod
    def find_value(
        self,
        gap_target: Dict,
        others: List[Dict],
        ctx: Dict,
    ) -> Optional[Dict]:
        """
        返回使 gap_target 有别于 others 的约束值字典，
        如 {"type": "pedestrian"} 或 {"status": "moving", "dir_ref": "front"}。
        找不到时返回 None。
        """

    @abstractmethod
    def filter_candidates(
        self,
        candidates: List[Dict],
        value: Dict,
    ) -> List[Dict]:
        """施加约束后的剩余候选集。"""

    @abstractmethod
    def render_question(
        self,
        tvars: Dict,
        value: Dict,
    ) -> str:
        """根据约束值生成问题文本。"""

    def render_answer(
        self,
        gap_target: Dict,
        value: Dict,
        tvars: Dict,
    ) -> str:
        """答案默认为目标 unique_id，子类可覆盖。"""
        return gap_target.get("id", gap_target.get("tgt_type", tvars.get("tgt_type", "")))


# ---------------------------------------------------------------------------
# M1  TypeFilter — 类型唯一
# ---------------------------------------------------------------------------

class TypeFilter(ConstraintMethod):
    """目标类型在候选集中唯一。
    生成: "What is the {type} to the {dir8} of {src}?"
    """
    name = "type_filter"
    priority = 1

    def can_apply(self, gap_target, others, ctx):
        return bool(gap_target.get("tgt_type"))

    def find_value(self, gap_target, others, ctx):
        v = gap_target.get("tgt_type", "")
        if v and all(c.get("tgt_type") != v for c in others):
            return {"type": v}
        return None

    def filter_candidates(self, candidates, value):
        return [c for c in candidates if c.get("tgt_type") == value["type"]]

    def render_question(self, tvars, value):
        src = _src(tvars)
        return f"What is the {value['type']} to the {tvars.get('dir8','')} of {src}?"


# ---------------------------------------------------------------------------
# M2  StatusAnchor — 状态作锚点 (NuScenes-QA 主力)
# ---------------------------------------------------------------------------

class StatusAnchor(ConstraintMethod):
    """目标状态在候选集中唯一。
    生成: "What is the {status} thing to the {dir8} of {src}?"
           对应 NuScenes-QA: "The moving thing to the front of me is what?"
    """
    name = "status_anchor"
    priority = 2

    def can_apply(self, gap_target, others, ctx):
        return bool(gap_target.get("tgt_status"))

    def find_value(self, gap_target, others, ctx):
        v = gap_target.get("tgt_status", "")
        if v and all(c.get("tgt_status") != v for c in others):
            return {"status": v}
        return None

    def filter_candidates(self, candidates, value):
        return [c for c in candidates if c.get("tgt_status") == value["status"]]

    def render_question(self, tvars, value):
        src = _src(tvars)
        return (
            f"What is the {value['status']} thing to the "
            f"{tvars.get('dir8','')} of {src}?"
        )


# ---------------------------------------------------------------------------
# M3  TypeStatusAnchor — 类型+状态组合
# ---------------------------------------------------------------------------

class TypeStatusAnchor(ConstraintMethod):
    """类型+状态组合唯一。
    生成: "What is the {status} {type} to the {dir8} of {src}?"
    """
    name = "type_status_anchor"
    priority = 3

    def can_apply(self, gap_target, others, ctx):
        return bool(gap_target.get("tgt_type") and gap_target.get("tgt_status"))

    def find_value(self, gap_target, others, ctx):
        t = gap_target.get("tgt_type", "")
        s = gap_target.get("tgt_status", "")
        if t and s and all(
            not (c.get("tgt_type") == t and c.get("tgt_status") == s)
            for c in others
        ):
            return {"type": t, "status": s}
        return None

    def filter_candidates(self, candidates, value):
        return [
            c for c in candidates
            if c.get("tgt_type") == value["type"]
            and c.get("tgt_status") == value["status"]
        ]

    def render_question(self, tvars, value):
        src = _src(tvars)
        return (
            f"What is the {value['status']} {value['type']} to the "
            f"{tvars.get('dir8','')} of {src}?"
        )


# ---------------------------------------------------------------------------
# M4  Dir8Refine — 子方向细化
# ---------------------------------------------------------------------------

class Dir8Refine(ConstraintMethod):
    """用 dir8 代替 dir4，缩小方向扇区。
    例：其他候选在 front-left / front-right，目标在 front → 可区分
    """
    name = "dir8_refine"
    priority = 4

    def can_apply(self, gap_target, others, ctx):
        return bool(gap_target.get("dir8"))

    def find_value(self, gap_target, others, ctx):
        v = gap_target.get("dir8", "")
        if v and all(c.get("dir8") != v for c in others):
            return {"dir8": v}
        return None

    def filter_candidates(self, candidates, value):
        return [c for c in candidates if c.get("dir8") == value["dir8"]]

    def render_question(self, tvars, value):
        src = _src(tvars)
        tgt_type = tvars.get("tgt_type", "object")
        return f"What {tgt_type} is directly to the {value['dir8']} of {src}?"


# ---------------------------------------------------------------------------
# M5  DualReference — 双参考点方向交集 (NuScenes-QA 最强手段)
# ---------------------------------------------------------------------------

class DualReference(ConstraintMethod):
    """
    用两个参考点的方向约束缩小目标范围。
    需要 ctx 中提供 ego 到目标的方向（ego_dir8 字段），
    与 src 到目标的方向（dir8）形成双重约束。

    生成: "What {type} is both to the {dir8} of {src} and the {ego_dir8} of ego?"
    对应 NuScenes-QA: "What is the thing that is both to the front of car1 and the front-left of me?"
    """
    name = "dual_reference"
    priority = 5

    def can_apply(self, gap_target, others, ctx):
        # 需要知道目标相对 ego 的方向
        return bool(ctx.get("ego_dir8") or gap_target.get("ego_dir8"))

    def find_value(self, gap_target, others, ctx):
        ego_dir = ctx.get("ego_dir8") or gap_target.get("ego_dir8", "")
        if not ego_dir:
            return None
        src_dir = gap_target.get("dir8", "")
        # 双重约束：src_dir + ego_dir 唯一锁定目标
        remaining = [
            c for c in others
            if c.get("dir8") == src_dir and c.get("ego_dir8") == ego_dir
        ]
        if not remaining:
            return {"dir8": src_dir, "ego_dir8": ego_dir}
        return None

    def filter_candidates(self, candidates, value):
        return [
            c for c in candidates
            if c.get("dir8") == value["dir8"]
            and c.get("ego_dir8") == value["ego_dir8"]
        ]

    def render_question(self, tvars, value):
        src = _src(tvars)
        tgt_type = tvars.get("tgt_type", "thing")
        return (
            f"What is the {tgt_type} that is both to the {value['dir8']} of {src}"
            f" and the {value['ego_dir8']} of ego?"
        )


# ---------------------------------------------------------------------------
# M6  DistOrder — 距离序 closest/farthest（按 dist_level 档位）
# ---------------------------------------------------------------------------

class DistOrder(ConstraintMethod):
    """
    目标是同 type+dir8 候选中距离最近或最远的（dist_level 档位比较）。
    """
    name = "dist_order"
    priority = 6

    def can_apply(self, gap_target, others, ctx):
        return bool(gap_target.get("dist_level"))

    def find_value(self, gap_target, others, ctx):
        # 只比较同 type 同 dir8 的 others
        t  = gap_target.get("tgt_type", "")
        d8 = gap_target.get("dir8", "")
        same = [o for o in others
                if o.get("tgt_type") == t and o.get("dir8") == d8]
        if not same:
            return None
        gap_rank = _DIST_RANK.get(gap_target.get("dist_level", ""), 99)
        other_ranks = [_DIST_RANK.get(c.get("dist_level", ""), 99) for c in same]
        if gap_rank < min(other_ranks):
            return {"order": "closest", "type": t, "dir8": d8}
        if gap_rank > max(other_ranks):
            return {"order": "farthest", "type": t, "dir8": d8}
        return None

    def filter_candidates(self, candidates, value):
        same = [c for c in candidates
                if c.get("tgt_type") == value.get("type")
                and c.get("dir8") == value.get("dir8")]
        ranks = [_DIST_RANK.get(c.get("dist_level", ""), 99) for c in same]
        if not ranks:
            return []
        target_rank = min(ranks) if value["order"] == "closest" else max(ranks)
        return [c for c in same if _DIST_RANK.get(c.get("dist_level", ""), 99) == target_rank]

    def render_question(self, tvars, value):
        src = _src(tvars)
        tgt_type = tvars.get("tgt_type", "object")
        return (
            f"What is the {value['order']} {tgt_type} to the "
            f"{tvars.get('dir8','')} of {src}?"
        )


# ---------------------------------------------------------------------------
# M7  TypeDistCombo — type + dist_level 联合
# ---------------------------------------------------------------------------

class TypeDistCombo(ConstraintMethod):
    """目标类型 + 距离档位联合唯一。
    生成: "What is the {dist} {type} to the {dir8} of {src}?"
    """
    name = "type_dist_combo"
    priority = 7

    def can_apply(self, gap_target, others, ctx):
        return bool(gap_target.get("tgt_type") and gap_target.get("dist_level"))

    def find_value(self, gap_target, others, ctx):
        t = gap_target.get("tgt_type", "")
        d = gap_target.get("dist_level", "")
        if t and d and all(
            not (c.get("tgt_type") == t and c.get("dist_level") == d)
            for c in others
        ):
            return {"type": t, "dist": d}
        return None

    def filter_candidates(self, candidates, value):
        return [c for c in candidates
                if c.get("tgt_type") == value["type"] and c.get("dist_level") == value["dist"]]

    def render_question(self, tvars, value):
        src = _src(tvars)
        return (f"What is the {value['dist']} {value['type']} "
                f"to the {tvars.get('dir8','')} of {src}?")


# ---------------------------------------------------------------------------
# M8  TypeDir8DistCombo — type + dir8(精确) + dist_level 联合
# ---------------------------------------------------------------------------

class TypeDir8DistCombo(ConstraintMethod):
    """类型 + 精确 8 方向 + 距离档位三元组唯一。
    生成: "What is the {dist} {type} at the {dir8} of {src}?"
    """
    name = "type_dir8_dist_combo"
    priority = 8

    def can_apply(self, gap_target, others, ctx):
        return bool(gap_target.get("tgt_type")
                    and gap_target.get("dir8")
                    and gap_target.get("dist_level"))

    def find_value(self, gap_target, others, ctx):
        t  = gap_target.get("tgt_type", "")
        d8 = gap_target.get("dir8", "")
        dl = gap_target.get("dist_level", "")
        if t and d8 and dl and all(
            not (c.get("tgt_type") == t
                 and c.get("dir8") == d8
                 and c.get("dist_level") == dl)
            for c in others
        ):
            return {"type": t, "dir8": d8, "dist": dl}
        return None

    def filter_candidates(self, candidates, value):
        return [c for c in candidates
                if c.get("tgt_type") == value["type"]
                and c.get("dir8") == value["dir8"]
                and c.get("dist_level") == value["dist"]]

    def render_question(self, tvars, value):
        src = _src(tvars)
        return (f"What is the {value['dist']} {value['type']} "
                f"at the {value['dir8']} of {src}?")


# ---------------------------------------------------------------------------
# M9  AllPropsCombo — type + dir8 + status + dist 全属性联合
# ---------------------------------------------------------------------------

class AllPropsCombo(ConstraintMethod):
    """四属性全部组合唯一（最强单跳约束）。
    生成: "What is the {status} {dist} {type} at the {dir8} of {src}?"
    """
    name = "all_props_combo"
    priority = 9

    def can_apply(self, gap_target, others, ctx):
        return bool(gap_target.get("tgt_type")
                    and gap_target.get("dir8")
                    and gap_target.get("tgt_status")
                    and gap_target.get("dist_level"))

    def find_value(self, gap_target, others, ctx):
        t  = gap_target.get("tgt_type", "")
        d8 = gap_target.get("dir8", "")
        s  = gap_target.get("tgt_status", "")
        dl = gap_target.get("dist_level", "")
        if t and d8 and s and dl and all(
            not (c.get("tgt_type") == t and c.get("dir8") == d8
                 and c.get("tgt_status") == s and c.get("dist_level") == dl)
            for c in others
        ):
            return {"type": t, "dir8": d8, "status": s, "dist": dl}
        return None

    def filter_candidates(self, candidates, value):
        return [c for c in candidates
                if c.get("tgt_type") == value["type"]
                and c.get("dir8") == value["dir8"]
                and c.get("tgt_status") == value["status"]
                and c.get("dist_level") == value["dist"]]

    def render_question(self, tvars, value):
        src = _src(tvars)
        return (f"What is the {value['status']} {value['dist']} {value['type']} "
                f"at the {value['dir8']} of {src}?")


# ---------------------------------------------------------------------------
# M10  OrdinalByDistance — 按实际距离排序（需 actual_dist 字段）
# ---------------------------------------------------------------------------

class OrdinalByDistance(ConstraintMethod):
    """
    目标在同 type+dir8 候选中按实际距离（浮点数）排序，
    是第 1 近或第 N 远（不允许并列）。
    生成: "What is the closest/farthest {type} to the {dir8} of {src}?"
    """
    name = "ordinal_by_distance"
    priority = 10

    def can_apply(self, gap_target, others, ctx):
        d = gap_target.get("actual_dist")
        return d is not None and float(d) > 0 and bool(gap_target.get("tgt_type"))

    def find_value(self, gap_target, others, ctx):
        gap_d = gap_target.get("actual_dist")
        if gap_d is None:
            return None
        gap_d = float(gap_d)
        # 只比较同 type 同 dir8、且有真实距离数据的 others
        same = [o for o in others
                if o.get("tgt_type") == gap_target.get("tgt_type")
                and o.get("dir8") == gap_target.get("dir8")
                and o.get("actual_dist") is not None
                and float(o["actual_dist"]) > 0]
        if not same:
            return None
        other_ds = [float(c["actual_dist"]) for c in same]
        # 最近
        if gap_d < min(other_ds):
            return {"order": "closest", "type": gap_target.get("tgt_type"),
                    "dir8": gap_target.get("dir8", "")}
        # 最远
        if gap_d > max(other_ds):
            return {"order": "farthest", "type": gap_target.get("tgt_type"),
                    "dir8": gap_target.get("dir8", "")}
        return None

    def filter_candidates(self, candidates, value):
        same = [c for c in candidates
                if c.get("tgt_type") == value["type"]
                and c.get("dir8") == value["dir8"]
                and c.get("actual_dist") is not None]
        if not same:
            return []
        if value["order"] == "closest":
            best = min(same, key=lambda c: float(c["actual_dist"]))
        else:
            best = max(same, key=lambda c: float(c["actual_dist"]))
        return [best]

    def render_question(self, tvars, value):
        src = _src(tvars)
        return (f"What is the {value['order']} {value['type']} "
                f"to the {value['dir8']} of {src}?")


# ---------------------------------------------------------------------------
# M11  TwoHopReferent — 单二跳 referent（需 ctx["referents"] 预取）
# ---------------------------------------------------------------------------

class TwoHopReferent(ConstraintMethod):
    """
    借助预先批量查询的 referents 列表（指向 gap_target 的节点集），
    找到能唯一锁定 gap_target 的第三节点 R：
        sibling_cnt(R, dir8_from_R, tgt_type) == 1

    生成: "What {tgt_type} is to the {dir8} of {ref_type} {ref_id}?"

    referents 由 run_gap_pipeline 的 _REFERENT_BATCH_CYPHER 预取，
    每条含: ref_id, ref_type, dir8, dist, sibling_cnt, sibling_ids
    """
    name = "two_hop_referent"
    priority = 11
    bypass_filter = True   # sibling_cnt==1 已在外部验证，无需 filter_candidates

    def can_apply(self, gap_target, others, ctx):
        return bool(ctx.get("referents"))

    def find_value(self, gap_target, others, ctx):
        for ref in ctx.get("referents", []):
            if ref.get("sibling_cnt", 99) == 1:
                return {
                    "ref_id":       ref["ref_id"],
                    "ref_type":     ref["ref_type"],
                    "dir8":         ref["dir8"],
                    "dist":         ref.get("dist", ""),
                    "ref_ego_dir8": ref.get("ref_ego_dir8", ""),
                }
        return None

    def filter_candidates(self, candidates, value):
        return []  # bypass_filter=True，不走这里

    def render_question(self, tvars, value):
        tgt_type  = tvars.get("tgt_type", "object")
        ref_label = _ref_label(value.get("ref_type", ""), value.get("ref_id", "?"))
        return f"What {tgt_type} is to the {value['dir8']} of {ref_label}?"


# ---------------------------------------------------------------------------
# M12  DualHopReferent — 双二跳 referent 交集（需 ctx["referents"] 含 sibling_ids）
# ---------------------------------------------------------------------------

class DualHopReferent(ConstraintMethod):
    """
    当单 referent 不能唯一锁定时，用两个 referent 的候选集交集锁定。
    前提：每个 referent 的 sibling_ids 列表已由批量查询返回。

    生成: "What {tgt_type} is both to the {dir8_1} of {ref1} and the {dir8_2} of {ref2}?"
    """
    name = "dual_hop_referent"
    priority = 12
    bypass_filter = True

    def can_apply(self, gap_target, others, ctx):
        refs = ctx.get("referents", [])
        return len(refs) >= 2

    def find_value(self, gap_target, others, ctx):
        tgt_id = gap_target.get("id", "")
        refs = ctx.get("referents", [])[:6]   # 最多组合前6个
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                r1, r2 = refs[i], refs[j]
                ids1 = set(r1.get("sibling_ids", []))
                ids2 = set(r2.get("sibling_ids", []))
                intersect = ids1 & ids2
                if len(intersect) == 1 and tgt_id in intersect:
                    return {
                        "ref1_id":       r1["ref_id"],
                        "ref1_type":     r1["ref_type"],
                        "ref1_dir8":     r1["dir8"],
                        "ref1_ego_dir8": r1.get("ref_ego_dir8", ""),
                        "ref2_id":       r2["ref_id"],
                        "ref2_type":     r2["ref_type"],
                        "ref2_dir8":     r2["dir8"],
                        "ref2_ego_dir8": r2.get("ref_ego_dir8", ""),
                    }
        return None

    def filter_candidates(self, candidates, value):
        return []  # bypass_filter=True

    def render_question(self, tvars, value):
        tgt_type = tvars.get("tgt_type", "object")
        ref1 = _ref_label(value.get("ref1_type", ""), value.get("ref1_id", "?"))
        ref2 = _ref_label(value.get("ref2_type", ""), value.get("ref2_id", "?"))
        return (
            f"What {tgt_type} is both to the {value['ref1_dir8']} of {ref1} "
            f"and to the {value['ref2_dir8']} of {ref2}?"
        )


# ---------------------------------------------------------------------------
# M13  AnchorIntro — 先引入锚点再问 (NuScenes-QA 计数常用)
# ---------------------------------------------------------------------------

class AnchorIntro(ConstraintMethod):
    """
    先用一句话引入 src 作为唯一锚点，再针对它提问。
    生成: "There is a {src_status} {src_type}; what is to the {dir8} of it?"
    对应 NuScenes-QA: "There is a not-standing pedestrian; what is to the front of it?"

    注：src 需要在场景中唯一可识别（比如特定状态）。
    """
    name = "anchor_intro"
    priority = 13

    def can_apply(self, gap_target, others, ctx):
        # src 有状态才能用作有区分度的锚点
        return bool(ctx.get("src_status"))

    def find_value(self, gap_target, others, ctx):
        # 这个方法不靠 others 做过滤，而是靠 src 锚点的唯一性
        # 返回 src 描述信息
        return {
            "src_status": ctx.get("src_status", ""),
            "src_type": ctx.get("src_type", ""),
        }

    def filter_candidates(self, candidates, value):
        # anchor_intro 不过滤 candidates，靠锚点自然唯一
        return candidates

    def render_question(self, tvars, value):
        anchor = f"{value['src_status']} {value['src_type']}".strip()
        tgt_type = tvars.get("tgt_type", "thing")
        dir8 = tvars.get("dir8", "")
        return f"There is a {anchor}; what {tgt_type} is to the {dir8} of it?"


# ---------------------------------------------------------------------------
# M8  CountFallback — 转为计数题
# ---------------------------------------------------------------------------

class CountFallback(ConstraintMethod):
    """
    转为计数问题。答案为整数，不需要唯一性，但问法自然。
    生成: "How many {type}s are to the {dir8} of {src}?"
    """
    name = "count_fallback"
    priority = 14

    def can_apply(self, gap_target, others, ctx):
        return bool(gap_target.get("tgt_type"))

    def find_value(self, gap_target, others, ctx):
        return {"type": gap_target.get("tgt_type", "object")}

    def filter_candidates(self, candidates, value):
        return [c for c in candidates if c.get("tgt_type") == value["type"]]

    def render_question(self, tvars, value):
        src = _src(tvars)
        t = value["type"]
        noun = t + "s" if not t.endswith("s") else t
        return f"How many {noun} are to the {tvars.get('dir8','')} of {src}?"

    def render_answer(self, gap_target, value, tvars):
        # 答案是 count，由外部统计候选集大小后填入
        return "__count__"     # 占位符，ConstraintChain 负责替换


# ---------------------------------------------------------------------------
# M9  FallbackYesNo — 兜底存在性
# ---------------------------------------------------------------------------

class FallbackYesNo(ConstraintMethod):
    """
    兜底：转为 yes/no 存在性问题，答案恒为 Yes（gap 存在即成立）。
    """
    name = "yesno_fallback"
    priority = 15

    def can_apply(self, gap_target, others, ctx):
        return True   # 永远可用

    def find_value(self, gap_target, others, ctx):
        return {}

    def filter_candidates(self, candidates, value):
        return candidates

    def render_question(self, tvars, value):
        src = _src(tvars)
        tgt_type = tvars.get("tgt_type", "object")
        tgt_status = tvars.get("tgt_status", "")
        dir8 = tvars.get("dir8", "")
        status_str = (tgt_status + " ") if tgt_status else ""
        return f"Is there a {status_str}{tgt_type} to the {dir8} of {src}?"

    def render_answer(self, gap_target, value, tvars):
        return "Yes"


# ---------------------------------------------------------------------------
# ConstraintChain — 统一调度器
# ---------------------------------------------------------------------------

# 默认方法顺序（优先级越小越优先）
# P1-P5:   单属性精确约束
# P6-P10:  距离序 + 联合属性组合
# P11-P12: 二跳 referent (需预取)
# P13:     锚点引入
# P14-P15: 兜底
DEFAULT_METHODS: List[ConstraintMethod] = [
    TypeFilter(),           # P1
    StatusAnchor(),         # P2
    TypeStatusAnchor(),     # P3
    Dir8Refine(),           # P4
    DualReference(),        # P5  (需 ctx["ego_dir8"])
    DistOrder(),            # P6
    TypeDistCombo(),        # P7
    TypeDir8DistCombo(),    # P8
    AllPropsCombo(),        # P9
    OrdinalByDistance(),    # P10 (需 actual_dist)
    TwoHopReferent(),       # P11 (需 ctx["referents"])
    DualHopReferent(),      # P12 (需 ctx["referents"] + sibling_ids)
    AnchorIntro(),          # P13
    CountFallback(),        # P14
    FallbackYesNo(),        # P15 兜底，永远能 apply
]


class ConstraintChain:
    """
    按优先级依次尝试每个 ConstraintMethod，
    找到第一个能使候选集收束到 1 的方法即止。

    Usage:
        chain = ConstraintChain()
        result = chain.tighten(gap_target, candidates, tvars, ctx)
    """

    def __init__(self, methods: List[ConstraintMethod] = None):
        self.methods = sorted(
            methods or DEFAULT_METHODS,
            key=lambda m: m.priority,
        )

    def tighten(
        self,
        gap_target: Dict,
        candidates: List[Dict],
        tvars: Dict,
        ctx: Dict = None,
    ) -> TightenResult:
        """
        Args:
            gap_target  : 目标节点属性 dict (from Neo4j ctx)
            candidates  : 宽泛查询返回的全部候选
            tvars       : 模板变量 dict
            ctx         : 完整 Neo4j 上下文（含 ego_dir8 等扩展字段）

        Returns:
            TightenResult（含 method_timings: 每方法耗时 ms）
        """
        ctx = ctx or {}
        others = [c for c in candidates if c.get("id") != gap_target.get("id")]
        method_timings: Dict[str, float] = {}
        methods_tried: List[str] = []

        # 已唯一，直接返回
        if not others:
            return TightenResult(
                question=self._direct_question(tvars),
                answer=gap_target.get("tgt_type", ""),
                is_unique=True,
                method_used="no_constraint_needed",
                method_timings={},
                methods_tried=[],
            )

        for method in self.methods:
            _t0 = time.perf_counter()

            if not method.can_apply(gap_target, others, ctx):
                method_timings[method.name] = (time.perf_counter() - _t0) * 1_000
                continue

            value = method.find_value(gap_target, others, ctx)
            if value is None:
                method_timings[method.name] = (time.perf_counter() - _t0) * 1_000
                continue

            methods_tried.append(method.name)

            # bypass_filter: 外部已验证唯一（如二跳 referent sibling_cnt==1）
            if getattr(method, "bypass_filter", False):
                q = method.render_question(tvars, value)
                a = method.render_answer(gap_target, value, tvars)
                method_timings[method.name] = (time.perf_counter() - _t0) * 1_000
                return TightenResult(
                    question=q, answer=a,
                    is_unique=True,
                    method_used=method.name,
                    method_timings=method_timings,
                    methods_tried=methods_tried,
                )

            remaining = method.filter_candidates(candidates, value)

            # CountFallback: 候选集大小就是答案，不要求唯一
            if method.name == "count_fallback":
                count = len(remaining)
                q = method.render_question(tvars, value)
                method_timings[method.name] = (time.perf_counter() - _t0) * 1_000
                return TightenResult(
                    question=q,
                    answer=str(count),
                    is_unique=False,
                    method_used=method.name,
                    count_fallback=True,
                    method_timings=method_timings,
                    methods_tried=methods_tried,
                )

            # FallbackYesNo: 兜底
            if method.name == "yesno_fallback":
                q = method.render_question(tvars, value)
                method_timings[method.name] = (time.perf_counter() - _t0) * 1_000
                return TightenResult(
                    question=q,
                    answer="Yes",
                    is_unique=False,
                    method_used=method.name,
                    yesno_fallback=True,
                    method_timings=method_timings,
                    methods_tried=methods_tried,
                )

            # 普通方法：看候选集是否收束到1
            if (
                len(remaining) == 1
                and remaining[0].get("id") == gap_target.get("id")
            ):
                q = method.render_question(tvars, value)
                a = method.render_answer(gap_target, value, tvars)
                method_timings[method.name] = (time.perf_counter() - _t0) * 1_000
                return TightenResult(
                    question=q, answer=a,
                    is_unique=True,
                    method_used=method.name,
                    method_timings=method_timings,
                    methods_tried=methods_tried,
                )

            # 收束不完全：继续试下一个方法（记录耗时）
            method_timings[method.name] = (time.perf_counter() - _t0) * 1_000

        # 理论上不会到这里（FallbackYesNo 一定能 apply）
        return TightenResult(
            question=self._direct_question(tvars),
            answer="Yes",
            is_unique=False,
            method_used="emergency_fallback",
            yesno_fallback=True,
            method_timings=method_timings,
            methods_tried=methods_tried,
        )

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _direct_question(tvars: Dict) -> str:
        src = _src(tvars)
        tgt_type = tvars.get("tgt_type", "object")
        dir8 = tvars.get("dir8", "")
        return f"What is the {tgt_type} to the {dir8} of {src}?"


# ---------------------------------------------------------------------------
# CumulativeConstraintChain — 动态叠加约束链
# ---------------------------------------------------------------------------

class CumulativeConstraintChain:
    """
    从最少约束开始逐步叠加属性，找到“最简约束组合”使候选集收束为 1。

    vs. ConstraintChain：
        ConstraintChain  : 按固定优先级逐个尝试预定义方法，初次命中即止。
        CumulativeChain  : 动态搜索 2⁴-1=15 种属性子集，按大小递增顺序递举，
                            找到最小能唯一定位的组合。

    可叠加属性（ATTR_ORDER）：
        type     目标类型（car/pedestrian/...）
        status   目标状态（moving/stopped/...）
        dir8     精确 8 方向（front-left/...）
        dist_ord 距离排序（closest/farthest）

    润落层：属性组合全失败 → TwoHopReferent → DualHopReferent
               → AnchorIntro → CountFallback → FallbackYesNo
    """

    ATTR_ORDER: List[str] = ["type", "status", "dir8", "dist_ord"]
    # 属性+two_hop 联合时仅用这两种属性进行入口收缩，问题文本更自然
    _ATTR_FOR_CROSS: List[str] = ["type", "status"]

    def __init__(self) -> None:
        self._two_hop  = TwoHopReferent()
        self._dual_hop = DualHopReferent()
        self._anchor   = AnchorIntro()
        self._count    = CountFallback()
        self._yesno    = FallbackYesNo()

    # ------------------------------------------------------------------
    # 属性提取
    # ------------------------------------------------------------------

    def _extract_attrs(
        self,
        gap_target: Dict,
        others: List[Dict],
    ) -> Dict[str, str]:
        """提取 gap_target 的各原子约束属性。
        dist_ord 只有在 gap_target 是同类型候选中最远或最近时才有效。
        """
        attrs: Dict[str, str] = {}
        v = gap_target.get("tgt_type", "")
        if v:
            attrs["type"] = v
        v = gap_target.get("tgt_status", "")
        if v:
            attrs["status"] = v
        v = gap_target.get("dir8", "")
        if v:
            attrs["dir8"] = v
        # dist_ord: 是否是同 dir8 同类型中最近或最远
        t  = gap_target.get("tgt_type", "")
        d8 = gap_target.get("dir8", "")
        same = [o for o in others
                if o.get("tgt_type") == t and o.get("dir8") == d8]
        if same:
            gap_rank    = _DIST_RANK.get(gap_target.get("dist_level", ""), 99)
            other_ranks = [_DIST_RANK.get(o.get("dist_level", ""), 99) for o in same]
            if gap_rank < min(other_ranks):
                attrs["dist_ord"] = "closest"
            elif gap_rank > max(other_ranks):
                attrs["dist_ord"] = "farthest"
        return attrs

    # ------------------------------------------------------------------
    # 多属性过滤
    # ------------------------------------------------------------------

    def _apply_combo(
        self,
        candidates: List[Dict],
        combo: Dict[str, str],
    ) -> List[Dict]:
        """\u5bf9候选集应用多属性组合过滤。"""
        result = list(candidates)
        if "type" in combo:
            result = [c for c in result if c.get("tgt_type") == combo["type"]]
        if "status" in combo:
            result = [c for c in result if c.get("tgt_status") == combo["status"]]
        if "dir8" in combo:
            result = [c for c in result if c.get("dir8") == combo["dir8"]]
        if "dist_ord" in combo:
            ranks = [(_DIST_RANK.get(c.get("dist_level", ""), 99), c) for c in result]
            if not ranks:
                return []
            best = (min if combo["dist_ord"] == "closest" else max)(r for r, _ in ranks)
            result = [c for r, c in ranks if r == best]
        return result

    # ------------------------------------------------------------------
    # 问题文本渲染
    # ------------------------------------------------------------------

    def _render_question(self, tvars: Dict, combo: Dict[str, str]) -> str:
        """一套模板渲染全部属性组合。
        首选 combo 里的 dir8，否则用 tvars dir8；最后退到 tvars dir4。
        """
        src     = _src(tvars)
        dir_ref = combo.get("dir8") or tvars.get("dir8") or tvars.get("dir4", "")
        parts: List[str] = []
        if "dist_ord" in combo:
            parts.append(combo["dist_ord"])
        if "status" in combo:
            parts.append(combo["status"])
        # 如果属性组合里没有 type，就用 tvars 里的已知目标类型，不用 "thing" 占位
        parts.append(combo.get("type", tvars.get("tgt_type", "thing")))
        return f"What is the {' '.join(parts)} to the {dir_ref} of {src}?"

    # ------------------------------------------------------------------
    # 属性缩小 + two_hop 异质叠加
    # ------------------------------------------------------------------

    def _try_attr_then_twohop(
        self,
        gap_target: Dict,
        candidates: List[Dict],
        tvars: Dict,
        ctx: Dict,
        method_timings: Dict[str, float],
        methods_tried: List[str],
    ) -> Optional["TightenResult"]:
        """属性维度小幅收缩 → 在缩小后的候选集重新校验 two_hop。

        为什么需要重新校验？
            step 5c 预取的 sibling_cnt 是封全集计算的。
            例如 truck1→right: sibling_ids=[car1, car3]，sibling_cnt=2 → 不唯一。
            但当候选集已经被 type=car 缩小后，用 Python 过滤一下：
                sibling_ids ∩ narrowed_ids = {car3} → 唯一 ✔
            不需要额外 Neo4j 查询，用已有的 sibling_ids 字段即可。

        联合问题文本：
            "What {status} {type} is to the {dir} of {ref_desc}?"
            例："What moving car is to the right of the truck in front?"
        """
        referents = ctx.get("referents", [])
        if not referents:
            return None

        target_id = gap_target.get("id", "")
        available = self._extract_attrs(gap_target,
                                        [c for c in candidates if c.get("id") != target_id])
        # 只用 type/status 作入口约束，问题文本更简洁
        cross_keys = [a for a in self._ATTR_FOR_CROSS if a in available]

        for n in range(1, len(cross_keys) + 1):
            for combo_keys in itertools.combinations(cross_keys, n):
                combo     = {k: available[k] for k in combo_keys}
                cname     = "+".join(combo_keys)
                _t0       = time.perf_counter()
                narrowed  = self._apply_combo(candidates, combo)

                # 候选集已经分现了但仍不唯一（唯一的情况已经在之前阶段处理）
                if len(narrowed) <= 1 or len(narrowed) >= len(candidates):
                    continue

                narrowed_ids = {c.get("id") for c in narrowed}

                for ref in referents:
                    sibling_ids = set(ref.get("sibling_ids", []))
                    # 在小上下文中重新校验：候选集与 sibling 的交集
                    overlap = sibling_ids & narrowed_ids
                    if len(overlap) == 1 and target_id in overlap:
                        compound = f"{cname}+two_hop"
                        # 直接用 ref ID，避免类型+ID 冗余
                        ref_desc = _ref_label(ref.get("ref_type", ""), ref.get("ref_id", "?"))
                        # 属性描述："moving car" / "car" / "stopped pedestrian"
                        attr_parts: List[str] = []
                        if "status" in combo:
                            attr_parts.append(combo["status"])
                        attr_parts.append(combo.get("type",
                                           tvars.get("tgt_type", "thing")))
                        noun = " ".join(attr_parts)
                        q = (f"What {noun} is to the "
                             f"{ref['dir8']} of {ref_desc}?")
                        a = target_id  # 答案用 ID，不用 type
                        elapsed = (time.perf_counter() - _t0) * 1_000
                        method_timings[compound] = (
                            method_timings.get(compound, 0.0) + elapsed
                        )
                        methods_tried.append(compound)
                        return TightenResult(
                            question=q, answer=a,
                            is_unique=True, method_used=compound,
                            method_timings=method_timings,
                            methods_tried=methods_tried,
                            referent_ids=ref.get("ref_id", ""),
                        )

                method_timings[cname + "_cross"] = (
                    method_timings.get(cname + "_cross", 0.0)
                    + (time.perf_counter() - _t0) * 1_000
                )
        return None

    # ------------------------------------------------------------------
    # 主方法
    # ------------------------------------------------------------------

    def tighten(
        self,
        gap_target: Dict,
        candidates: List[Dict],
        tvars: Dict,
        ctx: Dict = None,
    ) -> TightenResult:
        """
        动态叠加约束，返回最小约束组合的 TightenResult。
        TightenResult.method_used 格式为 'type+status' / 'type+dir8' 等，
        直观显示最终使用了哪些维度。
        """
        ctx = ctx or {}
        others = [c for c in candidates if c.get("id") != gap_target.get("id")]
        method_timings: Dict[str, float] = {}
        methods_tried:  List[str] = []
        trace_log:      List[Dict]  = []   # RQ1 消融实验用

        _logger.debug(
            "  CumulativeChain 开始: src=%s tgt=%s 候选集 %d 个 (不含目标)",
            gap_target.get("id",""), gap_target.get("id",""), len(others)
        )

        if not others:
            return TightenResult(
                question=ConstraintChain._direct_question(tvars),
                answer=gap_target.get("id", gap_target.get("tgt_type", "")),
                is_unique=True, method_used="no_constraint_needed",
                method_timings={}, methods_tried=[], value={},
                trace_log=[],
            )

        # ――― 阶段 1：单属性（1 属性） ―――――――――――――――――――――――――――――
        # 实测命中率：ordinal=13%, type_filter=5%, dir8=5%, status=3%
        available = self._extract_attrs(gap_target, others)
        attr_keys = [a for a in self.ATTR_ORDER if a in available]
        _logger.debug("  可用属性: %s", available)

        def _try_combos(n_range):
            for n in n_range:
                for combo_keys in itertools.combinations(attr_keys, n):
                    combo = {k: available[k] for k in combo_keys}
                    cname = "+".join(combo_keys)
                    _t0 = time.perf_counter()
                    remaining = self._apply_combo(candidates, combo)
                    elapsed = (time.perf_counter() - _t0) * 1_000
                    method_timings[cname] = method_timings.get(cname, 0.0) + elapsed
                    is_hit = (
                        len(remaining) == 1
                        and remaining[0].get("id") == gap_target.get("id")
                    )
                    trace_log.append({"method": cname, "success": is_hit,
                                      "time_ms": elapsed, "remaining_n": len(remaining)})
                    _logger.debug(
                        "    试 %-30s 候选 %d→%d  %s",
                        cname, len(candidates), len(remaining),
                        "✅ 唯一" if is_hit else "  "
                    )
                    if is_hit:
                        methods_tried.append(cname)
                        return TightenResult(
                            question=self._render_question(tvars, combo),
                            answer=gap_target.get("id",
                                       gap_target.get("tgt_type", tvars.get("tgt_type", ""))),
                            is_unique=True, method_used=cname,
                            method_timings=method_timings,
                            methods_tried=methods_tried,
                            value=combo,
                            trace_log=list(trace_log),
                        )
            return None

        r = _try_combos(range(1, 3))  # 1、2 属性
        if r is not None:
            return r

        # ――― 阶段 2a：纯二跳 referent（实测命中瓯 31%）――――――――――――――――――
        _t0 = time.perf_counter()
        if self._two_hop.can_apply(gap_target, others, ctx):
            value = self._two_hop.find_value(gap_target, others, ctx)
            elapsed = (time.perf_counter() - _t0) * 1_000
            if value is not None:
                _logger.debug("    试 two_hop_referent ref=%s dir=%s sibling_cnt=1 ✅ 唯一",
                              value.get('ref_id','?'), value.get('dir8','?'))
                trace_log.append({"method": self._two_hop.name, "success": True,
                                  "time_ms": elapsed, "remaining_n": 1})
                method_timings[self._two_hop.name] = elapsed
                methods_tried.append(self._two_hop.name)
                return TightenResult(
                    question=self._two_hop.render_question(tvars, value),
                    answer=self._two_hop.render_answer(gap_target, value, tvars),
                    is_unique=True, method_used=self._two_hop.name,
                    method_timings=method_timings,
                    methods_tried=methods_tried,
                    value=value,
                    referent_ids=value.get("ref_id", ""),
                    trace_log=list(trace_log),
                )
            _logger.debug("    试 two_hop_referent — referent 全集 sibling_cnt>1")
            trace_log.append({"method": self._two_hop.name, "success": False,
                              "time_ms": elapsed, "remaining_n": -1})
        method_timings[self._two_hop.name] = (time.perf_counter() - _t0) * 1_000

        # ――― 阶段 2b：属性缩小后再试 two_hop（异质叠加）―――――――――――――――
        # 属性将候选集从 N 缩小到 k 后，重新校验 sibling_ids∩narrowed，
        # 功效相当于在更小的子寻找 uniqueness。
        # 问题文本: "What {type} is to the {dir} of {ref}?" —— 天然包含属性维度。
        r = self._try_attr_then_twohop(
            gap_target, candidates, tvars, ctx, method_timings, methods_tried
        )
        if r is not None:
            return r

        # ――― 阶段 3：3-4 属性组合（实测命中 4+2+2=8 次）―――――――――――――――
        r = _try_combos(range(3, len(attr_keys) + 1))
        if r is not None:
            return r

        # ――― 阶段 4：双二跳 referent ―――――――――――――――――――――――――
        _t0 = time.perf_counter()
        if self._dual_hop.can_apply(gap_target, others, ctx):
            value = self._dual_hop.find_value(gap_target, others, ctx)
            elapsed = (time.perf_counter() - _t0) * 1_000
            if value is not None:
                _logger.debug("    试 dual_hop ref1=%s ref2=%s ✅ 唯一",
                              value.get('ref1_id','?'), value.get('ref2_id','?'))
                trace_log.append({"method": self._dual_hop.name, "success": True,
                                  "time_ms": elapsed, "remaining_n": 1})
                method_timings[self._dual_hop.name] = elapsed
                methods_tried.append(self._dual_hop.name)
                return TightenResult(
                    question=self._dual_hop.render_question(tvars, value),
                    answer=self._dual_hop.render_answer(gap_target, value, tvars),
                    is_unique=True, method_used=self._dual_hop.name,
                    method_timings=method_timings,
                    methods_tried=methods_tried,
                    value=value,
                    referent_ids=f"{value.get('ref1_id','')}|{value.get('ref2_id','')}",
                    trace_log=list(trace_log),
                )
            trace_log.append({"method": self._dual_hop.name, "success": False,
                              "time_ms": elapsed, "remaining_n": -1})
        method_timings[self._dual_hop.name] = (time.perf_counter() - _t0) * 1_000

        # ――― 阶段 5：锁点引入 ―――――――――――――――――――――――――――――――
        _t0 = time.perf_counter()
        if self._anchor.can_apply(gap_target, others, ctx):
            value = self._anchor.find_value(gap_target, others, ctx)
            if value is not None:
                method_timings["anchor_intro"] = (time.perf_counter() - _t0) * 1_000
                methods_tried.append("anchor_intro")
                return TightenResult(
                    question=self._anchor.render_question(tvars, value),
                    answer=self._anchor.render_answer(gap_target, value, tvars),
                    is_unique=True, method_used="anchor_intro",
                    method_timings=method_timings,
                    methods_tried=methods_tried,
                )
        method_timings["anchor_intro"] = (time.perf_counter() - _t0) * 1_000

        # ――― 阶段 6：存在性问题（无法唯一时退化）―――――――――――――――――
        # 选择存在性而非计数：
        #   计数题要求 VLM 数出具体数量，容错率低
        #   存在性题只需判断有/没有，所有答案恒为 Yes，更基础、更容易回答
        # ――― 阶段 6：存在性问题（无法唯一时退化）―――――――――――――――――
        _t0 = time.perf_counter()
        yv = self._yesno.find_value(gap_target, others, ctx)
        q  = self._yesno.render_question(tvars, yv)
        elapsed = (time.perf_counter() - _t0) * 1_000
        trace_log.append({"method": "yesno_fallback", "success": False,
                          "time_ms": elapsed, "remaining_n": len(candidates)})
        _logger.debug("退化为存在性问题: %s", q)
        method_timings["yesno_fallback"] = elapsed
        return TightenResult(
            question=q, answer="Yes",
            is_unique=False, method_used="yesno_fallback",
            yesno_fallback=True,
            method_timings=method_timings,
            methods_tried=methods_tried,
            value=yv or {},
            trace_log=list(trace_log),
        )

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _src(tvars: Dict) -> str:
    src_type = tvars.get("src_type", "")
    src_id = tvars.get("src_id", "")
    # 避免 "ego ego" / "car car33" 这类冗余拼接
    if not src_type or src_id.lower().startswith(src_type.lower()):
        return src_id
    return f"{src_type} {src_id}".strip()


def _ref_label(ref_type: str, ref_id: str) -> str:
    """返回引用对象的显示标签。
    当 ID 已经包含类型前缀时（如 car6），不再重复写类型：
        _ref_label('car', 'car6')         → 'car6'      ✔
        _ref_label('car', 'car6')  前缀删前 → 'car car6'  ✘
        _ref_label('truck', 'vehicle1')   → 'truck vehicle1'  ✔ (ID 不含类型前缀)
    """
    if not ref_type or ref_id.lower().startswith(ref_type.lower()):
        return ref_id
    return f"{ref_type} {ref_id}"
