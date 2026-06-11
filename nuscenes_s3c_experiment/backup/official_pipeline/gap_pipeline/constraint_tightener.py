"""
Gap Pipeline — Constraint Tightener
逐层添加约束，将问题范围收束到唯一答案；收束不了则退化为 yes/no 存在性问题。

流程：
    base Cypher → 候选集 count
        count == 1 → 直接通过
        count  > 1 → Layer 1 → 2 → ... → yes/no fallback

约束层（依次尝试）：
    L1  type         目标类型唯一
    L2  status       目标状态唯一
    L3  dist_order   距离最近 / 最远
    L4  dir8         子方向唯一（front vs front-left）
    L5  type+status  类型 + 状态组合唯一
    L6  yes/no       兜底存在性问题（一定可答，但稍简单）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# 距离档位排序（数值越小越近）
_DIST_RANK: Dict[str, int] = {
    "very_close": 0,
    "close": 1,
    "medium": 2,
    "far": 3,
}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Constraint:
    """单条约束描述"""
    kind: str                      # type / status / dist_order / dir8 / type+status
    value: str = ""                # 单值约束（type / status / dir8 的具体值）
    order: str = ""                # dist_order 时: "closest" | "farthest"
    type_val: str = ""             # type+status 复合时的 type
    status_val: str = ""           # type+status 复合时的 status


@dataclass
class TightenResult:
    """收束结果"""
    question: str
    answer: str
    is_unique: bool                # True=唯一锁定；False=yes/no fallback
    constraints_applied: List[str] = field(default_factory=list)
    yesno_fallback: bool = False


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------

class ConstraintTightener:
    """
    逐层添加约束，将一道问题收束到唯一答案。

    Usage:
        tightener = ConstraintTightener()
        result = tightener.tighten(gap_target, candidates, tvars)
        result.question   # 最终问题文本
        result.answer     # 对应答案
        result.is_unique  # 是否唯一锁定
    """

    _LAYERS = ["type", "status", "dist_order", "dir8", "type+status", "yesno"]

    def tighten(
        self,
        gap_target: Dict,
        candidates: List[Dict],
        tvars: Dict,
    ) -> TightenResult:
        """
        Args:
            gap_target : ctx 中的目标节点属性（必须含 id / tgt_type / tgt_status /
                         dist_level / dir8 等字段）
            candidates : 宽泛查询返回的全部候选节点列表（每项同 gap_target 结构）
            tvars      : 模板变量字典（src_type / src_id / dir8 等，用于生成问题文本）

        Returns:
            TightenResult
        """
        others = [c for c in candidates if c.get("id") != gap_target.get("id")]

        # 已经唯一，无需约束
        if not others:
            q = self._render_question(tvars, constraints=[])
            return TightenResult(
                question=q,
                answer=gap_target.get("tgt_type", ""),
                is_unique=True,
            )

        # 逐层尝试
        for layer in self._LAYERS:

            # ---- 兜底层 ----
            if layer == "yesno":
                return TightenResult(
                    question=self._render_yesno(tvars),
                    answer="Yes",
                    is_unique=False,
                    constraints_applied=["yesno_fallback"],
                    yesno_fallback=True,
                )

            # ---- 查找本层约束 ----
            c = self._find_constraint(layer, gap_target, others)
            if c is None:
                continue  # 本层找不到有效约束，跳下一层

            # ---- 验证：施加约束后候选集是否收束到 1 ----
            remaining = self._apply_filter(candidates, c)
            if len(remaining) == 1 and remaining[0].get("id") == gap_target.get("id"):
                return TightenResult(
                    question=self._render_question(tvars, constraints=[c]),
                    answer=self._derive_answer(gap_target, c, tvars),
                    is_unique=True,
                    constraints_applied=[layer],
                )
            # 约束缩小了候选集但还未唯一，继续下一层

        # 理论上不会到达（yesno 层保证提前返回）
        return TightenResult(
            question=self._render_yesno(tvars),
            answer="Yes",
            is_unique=False,
            constraints_applied=["yesno_fallback"],
            yesno_fallback=True,
        )

    # ------------------------------------------------------------------
    # 约束查找
    # ------------------------------------------------------------------

    def _find_constraint(
        self,
        layer: str,
        gap_target: Dict,
        others: List[Dict],
    ) -> Optional[Constraint]:
        """尝试在本层找到一条使 gap_target 有别于 others 的约束。"""

        if layer == "type":
            v = gap_target.get("tgt_type", "")
            if v and all(c.get("tgt_type") != v for c in others):
                return Constraint(kind="type", value=v)

        elif layer == "status":
            v = gap_target.get("tgt_status", "")
            if v and all(c.get("tgt_status") != v for c in others):
                return Constraint(kind="status", value=v)

        elif layer == "dist_order":
            gap_rank = _DIST_RANK.get(gap_target.get("dist_level", ""), 99)
            other_ranks = [_DIST_RANK.get(c.get("dist_level", ""), 99) for c in others]
            if gap_rank < min(other_ranks):
                return Constraint(kind="dist_order", order="closest")
            if gap_rank > max(other_ranks):
                return Constraint(kind="dist_order", order="farthest")

        elif layer == "dir8":
            v = gap_target.get("dir8", "")
            if v and all(c.get("dir8") != v for c in others):
                return Constraint(kind="dir8", value=v)

        elif layer == "type+status":
            t = gap_target.get("tgt_type", "")
            s = gap_target.get("tgt_status", "")
            if t and s:
                if all(
                    not (c.get("tgt_type") == t and c.get("tgt_status") == s)
                    for c in others
                ):
                    return Constraint(kind="type+status", type_val=t, status_val=s)

        return None

    # ------------------------------------------------------------------
    # 候选集过滤（用于验证约束是否真的收束到1）
    # ------------------------------------------------------------------

    def _apply_filter(self, candidates: List[Dict], c: Constraint) -> List[Dict]:
        if c.kind == "type":
            return [x for x in candidates if x.get("tgt_type") == c.value]

        if c.kind == "status":
            return [x for x in candidates if x.get("tgt_status") == c.value]

        if c.kind == "dist_order":
            ranks = [_DIST_RANK.get(x.get("dist_level", ""), 99) for x in candidates]
            target_rank = min(ranks) if c.order == "closest" else max(ranks)
            return [x for x in candidates
                    if _DIST_RANK.get(x.get("dist_level", ""), 99) == target_rank]

        if c.kind == "dir8":
            return [x for x in candidates if x.get("dir8") == c.value]

        if c.kind == "type+status":
            return [x for x in candidates
                    if x.get("tgt_type") == c.type_val
                    and x.get("tgt_status") == c.status_val]

        return candidates

    # ------------------------------------------------------------------
    # 问题文本生成
    # ------------------------------------------------------------------

    def _render_question(self, tvars: Dict, constraints: List[Constraint]) -> str:
        """把约束条件渲染进问题文本。"""
        src = f"{tvars.get('src_type', '')} {tvars.get('src_id', '')}".strip()
        dir8 = tvars.get("dir8", "")

        # 从约束中提取修饰词
        prefix_parts: List[str] = []    # 放在名词前（"moving", "closest"）
        noun = "object"                 # 默认用泛化名词

        for c in constraints:
            if c.kind == "type":
                noun = c.value
            elif c.kind == "status":
                prefix_parts.append(c.value)
            elif c.kind == "dist_order":
                prefix_parts.insert(0, c.order)   # "closest" 放最前
            elif c.kind == "dir8":
                dir8 = c.value                     # 用更精确的子方向
            elif c.kind == "type+status":
                noun = c.type_val
                prefix_parts.append(c.status_val)

        prefix = (" ".join(prefix_parts) + " ") if prefix_parts else ""
        return f"What is the {prefix}{noun} to the {dir8} of {src}?"

    def _render_yesno(self, tvars: Dict) -> str:
        """生成 yes/no 存在性问题（兜底）。"""
        src = f"{tvars.get('src_type', '')} {tvars.get('src_id', '')}".strip()
        tgt_type = tvars.get("tgt_type", "object")
        tgt_status = tvars.get("tgt_status", "")
        dir8 = tvars.get("dir8", "")
        status_str = (tgt_status + " ") if tgt_status else ""
        return f"Is there a {status_str}{tgt_type} to the {dir8} of {src}?"

    def _derive_answer(
        self, gap_target: Dict, c: Constraint, tvars: Dict
    ) -> str:
        """根据约束类型推导问题的答案。"""
        # 当前所有非 yes/no 问题均以目标类型作为答案
        return gap_target.get("tgt_type", tvars.get("tgt_type", ""))
