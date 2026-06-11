import random

from gap_pipeline.l2_dry_run import DryRunPlan
from gap_pipeline.l2_sampler import L2PlanSampler, SamplerConfig
from gap_pipeline.l2_taxonomy import L2Family


def P(fam, feasible=True, score=1.0):
    return DryRunPlan(family=fam, feasible=feasible, score=score)


def test_filters_infeasible():
    sampler = L2PlanSampler(config=SamplerConfig(min_score=0.0))
    plans = [P(L2Family.CONVERGE, False, 10), P(L2Family.DISTANCE_CHAIN, True, 1)]
    assert sampler.feasible_plans(plans) == [plans[1]]


def test_best_prefers_score():
    sampler = L2PlanSampler(config=SamplerConfig(prefer_underused=False))
    plans = [P(L2Family.CONVERGE, True, 0.5), P(L2Family.DISTANCE_CHAIN, True, 2.0)]
    assert sampler.best(plans).family == L2Family.DISTANCE_CHAIN


def test_underused_bonus():
    sampler = L2PlanSampler(config=SamplerConfig(prefer_underused=True, underused_bonus=1.0))
    plans = [P(L2Family.CONVERGE, True, 1.0), P(L2Family.DIVERGE_COMPARE, True, 1.0)]
    used = {"converge": 5, "diverge_compare": 0}
    assert sampler.best(plans, used_counts=used).family == L2Family.DIVERGE_COMPARE


def test_sample_deterministic_rng():
    sampler = L2PlanSampler(rng=random.Random(1), config=SamplerConfig(prefer_underused=False))
    plans = [P(L2Family.CONVERGE, True, 1.0), P(L2Family.DISTANCE_CHAIN, True, 0.0)]
    assert sampler.sample(plans).family == L2Family.CONVERGE


if __name__ == "__main__":
    test_filters_infeasible()
    test_best_prefers_score()
    test_underused_bonus()
    test_sample_deterministic_rng()
    print("OK: l2_sampler tests passed")

