"""
Weighted sampler for L2 dry-run plans.

This is a side-path module. It does not create questions by itself and is not
wired into the old pipeline yet.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from gap_pipeline.l2_dry_run import DryRunPlan
from gap_pipeline.l2_taxonomy import L2Family


@dataclass(frozen=True)
class SamplerConfig:
    min_score: float = 0.0
    prefer_underused: bool = True
    underused_bonus: float = 0.25


class L2PlanSampler:
    """Select one feasible dry-run plan by weighted random sampling."""

    def __init__(self, *, rng: Optional[random.Random] = None, config: Optional[SamplerConfig] = None) -> None:
        self.rng = rng or random.Random()
        self.config = config or SamplerConfig()

    def feasible_plans(self, plans: Iterable[DryRunPlan]) -> List[DryRunPlan]:
        return [p for p in plans if p.feasible and p.score > self.config.min_score]

    def sample(
        self,
        plans: Sequence[DryRunPlan],
        *,
        used_counts: Optional[dict] = None,
    ) -> Optional[DryRunPlan]:
        feasible = self.feasible_plans(plans)
        if not feasible:
            return None
        weights = [self._weight(p, used_counts or {}) for p in feasible]
        if sum(weights) <= 0:
            return None
        return self.rng.choices(feasible, weights=weights, k=1)[0]

    def best(
        self,
        plans: Sequence[DryRunPlan],
        *,
        used_counts: Optional[dict] = None,
    ) -> Optional[DryRunPlan]:
        feasible = self.feasible_plans(plans)
        if not feasible:
            return None
        return max(feasible, key=lambda p: self._weight(p, used_counts or {}))

    def _weight(self, plan: DryRunPlan, used_counts: dict) -> float:
        base = max(0.0, float(plan.score))
        if not self.config.prefer_underused:
            return base
        counts = {self._family_key(k): int(v) for k, v in used_counts.items()}
        fam = self._family_key(plan.family)
        if not counts:
            return base
        max_count = max(counts.values()) if counts else 0
        fam_count = counts.get(fam, 0)
        if max_count <= 0:
            return base
        rarity = max_count - fam_count
        return base * (1.0 + self.config.underused_bonus * rarity)

    @staticmethod
    def _family_key(family) -> str:
        if isinstance(family, L2Family):
            return family.value
        return str(family)

