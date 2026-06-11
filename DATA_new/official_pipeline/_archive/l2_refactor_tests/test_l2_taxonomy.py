from gap_pipeline.l2_taxonomy import L2Family, L2Gap, eligible_families


def names(gap):
    return [s.family for s in eligible_families(gap)]


def test_no_ego_all_families():
    gap = L2Gap("car1", "truck1", "ped1", "car", "truck", "pedestrian")
    fams = set(names(gap))
    assert fams == set(L2Family)


def test_ego_as_pivot_blocks_converge_only():
    gap = L2Gap("car1", "ego", "ped1", "car", "ego", "pedestrian")
    fams = set(names(gap))
    assert L2Family.CONVERGE not in fams
    assert L2Family.DIVERGE_COMPARE in fams
    assert L2Family.DISTANCE_CHAIN in fams


def test_ego_as_branch_blocks_diverge_only():
    gap = L2Gap("ego", "car1", "ped1", "ego", "car", "pedestrian")
    fams = set(names(gap))
    assert L2Family.DIVERGE_COMPARE not in fams
    assert L2Family.CONVERGE in fams
    assert L2Family.VIEWPOINT_TRANSFER in fams


def test_missing_types_block_needed_families():
    gap = L2Gap("a", "b", "c")
    fams = set(names(gap))
    assert L2Family.CONVERGE not in fams
    assert L2Family.DIVERGE_COMPARE not in fams
    assert L2Family.DISTANCE_CHAIN in fams


if __name__ == "__main__":
    test_no_ego_all_families()
    test_ego_as_pivot_blocks_converge_only()
    test_ego_as_branch_blocks_diverge_only()
    test_missing_types_block_needed_families()
    print("OK: l2_taxonomy tests passed")

