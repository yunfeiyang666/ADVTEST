from gap_pipeline.l2_adapter import plan_to_qa_record
from gap_pipeline.l2_dry_run import DryRunInput, L2DryRunner
from gap_pipeline.l2_sampler import L2PlanSampler
from gap_pipeline.l2_taxonomy import L2Family, L2Gap


def O(id_, type_, x, y, status="moving"):
    return {"id": id_, "unique_id": id_, "type": type_, "status": status, "tx": x, "ty": y}


def test_adapt_converge_plan():
    a = O("a", "car", 0, 0)
    b = O("b", "truck", 0, 10)
    c = O("c", "pedestrian", 5, 15)
    gap = L2Gap("a", "b", "c", "car", "truck", "pedestrian")
    data = DryRunInput(
        gap,
        a,
        b,
        c,
        converge_rows=[{"id": "b", "type": "truck", "dir_from_a": "front", "dir_from_c": "back-left", "tx": 0, "ty": 10}],
    )
    plans = L2DryRunner(min_distance_gap=0.1).feasible(data)
    plan = next(p for p in plans if p.family == L2Family.CONVERGE)
    qa = plan_to_qa_record(data, plan, question_id="q1", scene_name="scene", frame_idx=3)
    assert qa["question_id"] == "q1"
    assert qa["Template_ID"] == "converge"
    assert qa["answer"] == "b"
    assert qa["coverage_footprint"]["l2"] == ["a|b|c"]
    assert "direction_official" in qa["verify_payload"]["cypher"]
    assert qa["l2_refactor"] is True


def test_adapt_sampled_chain_plan():
    a = O("a", "car", 0, 0)
    b = O("b", "truck", 0, 10)
    c = O("c", "pedestrian", 5, 15)
    gap = L2Gap("a", "b", "c", "car", "truck", "pedestrian")
    data = DryRunInput(gap, a, b, c)
    plan = L2PlanSampler().best(L2DryRunner(min_distance_gap=0.1).feasible(data))
    qa = plan_to_qa_record(data, plan)
    assert qa["question"]
    assert qa["answer"] is not None
    assert qa["coverage_footprint"]["l2"] == ["a|b|c"]


if __name__ == "__main__":
    test_adapt_converge_plan()
    test_adapt_sampled_chain_plan()
    print("OK: l2_adapter tests passed")

