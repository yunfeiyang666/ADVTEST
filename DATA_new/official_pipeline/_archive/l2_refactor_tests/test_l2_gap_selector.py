import random

from gap_pipeline.l2_gap_selector import L2CoverageState, L2GapSelector, gap_coverage_level


def R(a, b, c):
    return {"a_id": a, "b_id": b, "c_id": c}


def test_level_priority():
    state = L2CoverageState(l0={"a", "b", "c"}, l1={"a|b", "b|c"}, l2=set())
    assert gap_coverage_level(R("a", "b", "c"), state) == 2
    state.l2.add("a|b|c")
    assert gap_coverage_level(R("a", "b", "c"), state) == -1
    assert gap_coverage_level(R("a", "b", "d"), state) == 2


def test_select_ignores_tried():
    rows = [R("a", "b", "c"), R("x", "y", "z")]
    sel = L2GapSelector(rng=random.Random(1))
    picked = sel.select_next(rows, L2CoverageState(), already_tried={"a|b|c"})
    assert picked == rows[1]


def test_mark_coverage():
    state = L2CoverageState()
    state.mark({"l0": ["a", "b"], "l1": ["a|b"], "l2": ["a|b|c"]})
    assert "a" in state.l0
    assert "a|b" in state.l1
    assert "a|b|c" in state.l2


if __name__ == "__main__":
    test_level_priority()
    test_select_ignores_tried()
    test_mark_coverage()
    print("OK: l2_gap_selector tests passed")

