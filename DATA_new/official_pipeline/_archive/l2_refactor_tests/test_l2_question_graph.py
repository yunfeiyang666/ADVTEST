from gap_pipeline.l2_question_graph import converge_graph, diverge_graph, chain_graph


def test_converge_with_refs():
    g = converge_graph("a", "b", "c", refs=["ref1", "ref2"])
    fp = g.footprint().as_dict()
    assert fp["l1"] == ["a|b", "b|c", "b|ref1", "b|ref2"]
    assert fp["l2"] == [
        "a|b|c",
        "a|b|ref1",
        "a|b|ref2",
        "c|b|ref1",
        "c|b|ref2",
        "ref1|b|ref2",
    ]


def test_diverge_with_branch_refs():
    g = diverge_graph("a", "b", "c", x_refs=["refA"], y_refs=["refC"])
    fp = g.footprint().as_dict()
    assert fp["l1"] == ["a|b", "a|refA", "b|c", "c|refC"]
    assert fp["l2"] == ["a|b|c", "b|a|refA", "b|c|refC"]


def test_chain_graph():
    g = chain_graph("a", "b", "c", family="distance_chain")
    fp = g.footprint().as_dict()
    assert fp["l0"] == ["a", "b", "c"]
    assert fp["l1"] == ["a|b", "b|c"]
    assert fp["l2"] == ["a|b|c"]


if __name__ == "__main__":
    test_converge_with_refs()
    test_diverge_with_branch_refs()
    test_chain_graph()
    print("OK: l2_question_graph footprint tests passed")

