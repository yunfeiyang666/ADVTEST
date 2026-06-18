import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_l0_l1_structural_suites import l0_candidates, l1_candidates


class BuildL0L1StructuralSuitesTests(unittest.TestCase):
    def setUp(self):
        self.scene_frame = "scene-test_frame3"
        self.scene_graph = {
            "nodes": [
                {"unique_id": "ego", "type": "ego"},
                {"unique_id": "car1", "type": "car"},
                {"unique_id": "traffic_cone2", "type": "traffic_cone"},
                {"unique_id": "pedestrian3", "category": "human.pedestrian.adult"},
            ],
            "edges": [
                {
                    "source": "car1",
                    "target": "traffic_cone2",
                    "direction_6": "front_left",
                },
                {
                    "source": "traffic_cone2",
                    "target": "car1",
                    "direction_6": "back_right",
                },
                {
                    "source": "car1",
                    "target": "missing",
                    "direction_6": "front",
                },
            ],
        }

    def test_l0_candidates_ask_object_type_and_skip_ego(self):
        questions = l0_candidates(self.scene_frame, self.scene_graph)

        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0]["question"], "What type of object is car1?")
        self.assertEqual(questions[0]["answer"], "car")
        self.assertEqual(questions[1]["answer"], "traffic cone")
        self.assertEqual(questions[2]["answer"], "adult")
        self.assertEqual(questions[0]["coverage_footprint"]["l0"], ["car1"])
        self.assertEqual(questions[0]["topology_level"], "L0")

    def test_l1_candidates_ask_pair_direction_and_filter_missing_nodes(self):
        questions = l1_candidates(self.scene_frame, self.scene_graph)

        self.assertEqual(len(questions), 2)
        self.assertEqual(
            questions[0]["question"],
            "Where is traffic_cone2 relative to car1?",
        )
        self.assertEqual(questions[0]["answer"], "front left")
        self.assertEqual(
            questions[0]["coverage_footprint"]["l1"],
            ["car1|traffic_cone2|front_left"],
        )
        self.assertEqual(questions[0]["topology_level"], "L1")


if __name__ == "__main__":
    unittest.main()
