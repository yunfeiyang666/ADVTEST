from gap_pipeline.l2_candidate_builder import (
    v6_endpoint_candidates_from_ctx,
    filter_by_type_dir,
    build_diverge_candidates,
    build_converge_candidates,
)


def test_v6_ctx_normalization_and_dir_mapping():
    ctx = {
        "n3_id": "ped7",
        "n3_type": "pedestrian",
        "n3_status": "moving",
        "r2_dir_official": "front-left",
        "r2_actual_dist": 7.0,
        "n3_tx": 1,
        "n3_ty": 2,
        "sibling_ids": ["ped1", "car1"],
        "sibling_types": ["pedestrian", "car"],
        "sibling_statuses": ["moving", "parked"],
        "sibling_dir_officials": ["front-left", "back"],
        "sibling_actual_dists": [8.0, 9.0],
        "sibling_txs": [2, 3],
        "sibling_tys": [2, 3],
    }
    rows, target = v6_endpoint_candidates_from_ctx(ctx)
    assert target["id"] == "ped7"
    assert target["dir_official"] == "front-left"
    assert rows[2]["dir_official"] == "back"


def test_filter_by_type_dir():
    rows = [
        {"id": "a", "type": "car", "dir_official": "front"},
        {"id": "b", "type": "car", "dir_official": "front-left"},
        {"id": "c", "type": "truck", "dir_official": "front"},
    ]
    out = filter_by_type_dir(rows, target_type="car", target_dir="front")
    assert [r["id"] for r in out] == ["a"]


def test_build_diverge_candidates():
    neighbors = [
        {"id": "a1", "type": "car", "dir_official": "front"},
        {"id": "a2", "type": "car", "dir_official": "front"},
        {"id": "c1", "type": "truck", "dir_official": "back"},
    ]
    div = build_diverge_candidates(
        neighbors,
        {"id": "a1", "type": "car", "dir_official": "front"},
        {"id": "c1", "type": "truck", "dir_official": "back"},
        a_type="car",
        a_dir="front",
        c_type="truck",
        c_dir="back",
    )
    assert [r["id"] for r in div.a_branch.candidates] == ["a1", "a2"]
    assert [r["id"] for r in div.c_branch.candidates] == ["c1"]


def test_build_converge_candidates():
    rows = [
        {"id": "b1", "type": "car", "dir_from_a": "front", "dir_from_c": "back"},
        {"id": "b2", "type": "car", "dir_from_a": "front", "dir_from_c": "front"},
        {"id": "b3", "type": "truck", "dir_from_a": "front", "dir_from_c": "back"},
    ]
    out = build_converge_candidates(rows, target_type="car", dir_from_a="front", dir_from_c="back")
    assert [r["id"] for r in out] == ["b1"]


if __name__ == "__main__":
    test_v6_ctx_normalization_and_dir_mapping()
    test_filter_by_type_dir()
    test_build_diverge_candidates()
    test_build_converge_candidates()
    print("OK: l2_candidate_builder tests passed")

