from gap_pipeline.l2_dry_run import DryRunInput, L2DryRunner
from gap_pipeline.l2_taxonomy import L2Family, L2Gap


def O(id_, type_, x, y, status="moving"):
    return {"id": id_, "unique_id": id_, "type": type_, "status": status, "tx": x, "ty": y}


def test_dry_run_all_simple_families():
    a = O("a", "car", 0, 0)
    b = O("b", "truck", 0, 10)
    c = O("c", "pedestrian", 5, 15)
    gap = L2Gap("a", "b", "c", "car", "truck", "pedestrian")
    converge_rows = [
        {"id": "b", "type": "truck", "dir_from_a": "front", "dir_from_c": "back-left", "tx": 0, "ty": 10}
    ]
    pivot_neighbors = [
        {"id": "a", "type": "car", "dir_official": "back", "tx": 0, "ty": 0},
        {"id": "c", "type": "pedestrian", "dir_official": "front-right", "tx": 5, "ty": 15},
    ]
    data = DryRunInput(gap, a, b, c, converge_rows=converge_rows, pivot_neighbors=pivot_neighbors)
    plans = L2DryRunner(min_distance_gap=0.1).feasible(data)
    fams = {p.family for p in plans}
    assert L2Family.CONVERGE in fams
    assert L2Family.DIVERGE_COMPARE in fams
    assert L2Family.DISTANCE_CHAIN in fams
    assert L2Family.DIRECTION_CHAIN in fams
    assert any(p.question and p.question.question for p in plans)


def test_ego_rules_apply_in_dry_run():
    ego = O("ego", "ego", 0, 0)
    b = O("b", "truck", 0, 10)
    c = O("c", "pedestrian", 5, 15)
    gap = L2Gap("ego", "b", "c", "ego", "truck", "pedestrian")
    data = DryRunInput(gap, ego, b, c)
    fams = {p.family for p in L2DryRunner().run(data)}
    assert L2Family.DIVERGE_COMPARE not in fams


if __name__ == "__main__":
    test_dry_run_all_simple_families()
    test_ego_rules_apply_in_dry_run()
    print("OK: l2_dry_run tests passed")

