from gap_pipeline.l2_constraint_planner import L2Clause
from gap_pipeline.l2_question_realizer import (
    converge_question,
    diverge_status_question,
    distance_chain_question,
    direction_chain_question,
    viewpoint_transfer_question,
)


def test_converge_object_with_ref_and_rank():
    q = converge_question(
        target_type="pedestrian",
        a_id="car1",
        c_id="truck2",
        dir_from_a="front-left",
        dir_from_c="back",
        clauses=[
            L2Clause(kind="ref_dir", ref_id="ped3", value="front-right"),
            L2Clause(kind="dist_rank", value="nearest"),
        ],
        mode="object",
    )
    assert q.question == (
        "What pedestrian is to the front left of car1 and to the back of truck2, "
        "and to the front right of ped3?"
    )
    assert q.answer_type == "object"


def test_converge_count():
    q = converge_question(
        target_type="car",
        a_id="a",
        c_id="c",
        dir_from_a="front",
        dir_from_c="back-right",
        mode="count",
    )
    assert q.question == "How many cars are to the front of a and to the back right of c?"
    assert q.answer_type == "count"


def test_diverge_status():
    q = diverge_status_question(
        b_id="b",
        a_type="car",
        a_dir="front-left",
        c_type="truck",
        c_dir="back",
        a_clauses=[L2Clause(kind="ref_dir", ref_id="refA", value="front")],
    )
    assert q.question == (
        "Do the car to the front left of b, and to the front of refA "
        "and the truck to the back of b have the same status?"
    )


def test_chain_questions():
    assert distance_chain_question("a", "b", "c").question == "Is b closer to a or to c?"
    assert direction_chain_question("a", "b", "c").question == "Is c in the same direction from b as b is from a?"
    assert viewpoint_transfer_question("a", "b", "c").question == "If you face from a toward b, is c on your left or on your right?"


if __name__ == "__main__":
    test_converge_object_with_ref_and_rank()
    test_converge_count()
    test_diverge_status()
    test_chain_questions()
    print("OK: l2_question_realizer tests passed")

