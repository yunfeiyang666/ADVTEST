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
                {"unique_id": "car1", "type": "car", "status": "moving"},
                {"unique_id": "traffic_cone2", "type": "traffic_cone"},
                {
                    "unique_id": "pedestrian3",
                    "category": "human.pedestrian.adult",
                    "status": "stopped",
                },
                {"unique_id": "car4", "type": "car", "status": "stopped"},
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

        self.assertGreaterEqual(len(questions), 9)
        self.assertEqual(questions[0]["question"], "What type of object is car1?")
        self.assertEqual(questions[0]["answer"], "car")
        self.assertEqual(questions[0]["coverage_footprint"]["l0"], ["car1"])
        self.assertEqual(questions[0]["topology_level"], "L0")
        by_template = {question["template_id"]: question for question in questions}
        self.assertIn("l0_object_status", by_template)
        self.assertIn("l0_object_type_yes", by_template)
        self.assertIn("l0_object_type_no", by_template)
        self.assertIn("l0_object_status_yes", by_template)
        self.assertIn("l0_object_status_no", by_template)
        self.assertIn("l0_object_exists", by_template)
        self.assertIn("l0_count_type", by_template)
        self.assertIn("l0_exist_status_type", by_template)
        self.assertIn("l0_more_type_than_type", by_template)
        self.assertTrue(
            any(
                question["question"] == "Are any moving cars visible?"
                and question["answer"] == "yes"
                for question in questions
            )
        )
        self.assertTrue(
            any(
                question["question"] == "How many traffic cones are visible?"
                and question["answer"] == "1"
                for question in questions
            )
        )
        self.assertTrue(
            any(
                question["question"] == "Is car1 a car?"
                and question["answer"] == "yes"
                for question in questions
            )
        )
        self.assertTrue(
            any(
                question["question"] == "Is car1 moving?"
                and question["answer"] == "yes"
                for question in questions
            )
        )

    def test_l1_candidates_ask_pair_direction_and_filter_missing_nodes(self):
        questions = l1_candidates(self.scene_frame, self.scene_graph)

        self.assertGreaterEqual(len(questions), 8)
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
        templates = {question["template_id"] for question in questions}
        self.assertIn("l1_pair_direction_reverse", templates)
        self.assertIn("l1_relation_exists", templates)
        self.assertIn("l1_relation_exists_neg", templates)
        self.assertIn("l1_object_at_direction", templates)
        self.assertIn("l1_exist_direction_type", templates)
        self.assertIn("l1_exist_direction_type_no", templates)
        self.assertIn("l1_exist_status_direction_type", templates)
        self.assertIn("l1_count_status_direction_type", templates)
        self.assertIn("l1_count_direction_type", templates)
        self.assertTrue(
            any(
                question["question"]
                == "How many traffic cones are to the front left of car1?"
                and question["answer"] == "1"
                for question in questions
            )
        )
        self.assertTrue(
            any(
                question["question"] == "Where is car1 relative to traffic_cone2?"
                and question["answer"] == "back right"
                for question in questions
            )
        )
        self.assertTrue(
            any(
                question["question"]
                == "Are any traffic cones to the front left of car1?"
                and question["answer"] == "yes"
                for question in questions
            )
        )


if __name__ == "__main__":
    unittest.main()
