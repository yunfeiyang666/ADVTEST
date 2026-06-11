from gap_pipeline.l2_constraint_planner import L2ConstraintPlanner


def C(id_, x, y, dist=None):
    row = {"id": id_, "tx": x, "ty": y}
    if dist is not None:
        row["actual_dist"] = dist
    return row


def test_ref_constraint_uniques_target():
    # Same coarse branch candidates. ref ped1 sees target ped7 as back-right,
    # while other candidates are front-right, so one ref should isolate target.
    target = C("ped7", 11, 18, 8)
    candidates = [
        C("ped1", 10, 20, 7),
        C("ped3", 12, 22, 9),
        target,
        C("ped9", 13, 21, 10),
    ]
    planner = L2ConstraintPlanner(max_refs=2, allow_dist_rank=True)
    res = planner.plan(target, candidates)
    assert res.unique
    assert res.remaining_ids == ["ped7"]
    assert res.clauses[0].kind == "ref_dir"
    assert res.clauses[0].ref_id == "ped1"


def test_distance_rank_fallback():
    # No external geometry ref can split these, but rank can.
    target = C("b", 1, 0, 5)
    candidates = [C("a", 0, 0, 3), target, C("c", 2, 0, 7)]
    planner = L2ConstraintPlanner(max_refs=0, allow_dist_rank=True)
    res = planner.plan(target, candidates)
    assert res.unique
    assert res.clauses[-1].kind == "dist_rank"
    assert res.clauses[-1].value == "2nd-nearest"


def test_non_unique_without_gain_or_rank():
    target = C("b", 1, 0)
    candidates = [C("a", 0, 0), target, C("c", 2, 0)]
    planner = L2ConstraintPlanner(max_refs=0, allow_dist_rank=True)
    res = planner.plan(target, candidates)
    assert not res.unique


if __name__ == "__main__":
    test_ref_constraint_uniques_target()
    test_distance_rank_fallback()
    test_non_unique_without_gain_or_rank()
    print("OK: l2_constraint_planner tests passed")

