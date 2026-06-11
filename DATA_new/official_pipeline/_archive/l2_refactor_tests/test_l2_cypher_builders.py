from gap_pipeline.l2_constraint_planner import L2Clause
from gap_pipeline.l2_cypher_builders import (
    fetch_pivot_neighbors,
    fetch_converge_intersection,
    verify_converge,
    verify_branch,
    verify_distance_chain,
    verify_direction_chain,
)


def test_fetch_queries_use_official_direction():
    q1 = fetch_pivot_neighbors("b")
    q2 = fetch_converge_intersection("a", "c")
    assert "direction_official" in q1.cypher
    assert "direction_official" in q2.cypher
    assert "direction_8" not in q1.cypher + q2.cypher


def test_verify_converge_with_ref_clause():
    q = verify_converge(
        a_id="a",
        c_id="c",
        target_type="car",
        dir_from_a="front",
        dir_from_c="back",
        clauses=[L2Clause(kind="ref_dir", ref_id="ref1", value="front-left")],
    )
    assert "MATCH (ref1:Object {unique_id:$ref_id_1})" in q.cypher
    assert "r_ref1.direction_official = $ref_dir_1" in q.cypher
    assert q.params["ref_id_1"] == "ref1"
    assert q.params["ref_dir_1"] == "front-left"


def test_verify_branch():
    q = verify_branch(b_id="b", branch_type="pedestrian", branch_dir="front")
    assert "x.type = $branch_type" in q.cypher
    assert "r.direction_official = $branch_dir" in q.cypher
    assert q.params == {"b_id": "b", "branch_type": "pedestrian", "branch_dir": "front"}


def test_chain_queries():
    dq = verify_distance_chain("a", "b", "c")
    gq = verify_direction_chain("a", "b", "c")
    assert "rab.distance AS d_ab" in dq.cypher
    assert "rab.direction_official AS dir_ab" in gq.cypher


if __name__ == "__main__":
    test_fetch_queries_use_official_direction()
    test_verify_converge_with_ref_clause()
    test_verify_branch()
    test_chain_queries()
    print("OK: l2_cypher_builders tests passed")

