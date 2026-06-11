from gap_pipeline.l2_geometry import (
    official_dir6,
    official_dir6_from_angle,
    distance_rank,
    viewpoint_left_right,
)


def test_official_dir6_angles():
    assert official_dir6_from_angle(30) == "front-right"
    assert official_dir6_from_angle(90) == "front"
    assert official_dir6_from_angle(150) == "front-left"
    assert official_dir6_from_angle(210) == "back-left"
    assert official_dir6_from_angle(270) == "back"
    assert official_dir6_from_angle(330) == "back-right"
    assert official_dir6_from_angle(60, boundary_margin=1) is None


def test_official_dir6_points():
    origin = (0, 0)
    assert official_dir6(origin, (1, 1)) == "front-right"
    assert official_dir6(origin, (0, 1)) == "front"
    assert official_dir6(origin, (-1, 1)) == "front-left"
    assert official_dir6(origin, (-1, -1)) == "back-left"
    assert official_dir6(origin, (0, -1)) == "back"
    assert official_dir6(origin, (1, -1)) == "back-right"



def test_distance_rank():
    rows = [
        {"id": "a", "actual_dist": 10},
        {"id": "b", "actual_dist": 5},
        {"id": "c", "actual_dist": 20},
    ]
    assert distance_rank("b", rows) == "nearest"
    assert distance_rank("a", rows) == "2nd-nearest"
    assert distance_rank("c", rows) == "farthest"


def test_viewpoint_left_right():
    a, b = (0, 0), (0, 1)  # facing front/up
    assert viewpoint_left_right(a, b, (-1, 1)) == "left"
    assert viewpoint_left_right(a, b, (1, 1)) == "right"
    assert viewpoint_left_right(a, b, (0, 2)) is None


if __name__ == "__main__":
    test_official_dir6_angles()
    test_official_dir6_points()
    test_distance_rank()
    test_viewpoint_left_right()
    print("OK: l2_geometry tests passed")

