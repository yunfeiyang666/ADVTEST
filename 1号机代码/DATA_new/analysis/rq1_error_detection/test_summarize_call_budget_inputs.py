import json
import tempfile
import unittest
from pathlib import Path

from summarize_call_budget_inputs import (
    load_structural_denominators,
    summarize_inputs,
)


class SummarizeCallBudgetInputsTests(unittest.TestCase):
    def test_reports_structural_coverage_and_external_boundary(self):
        suites = {
            "advtest": [
                {
                    "question": "q1",
                    "answer": "car1",
                    "scene_frame": "frame-a",
                    "template_id": "converge",
                    "answer_type": "object",
                    "question_source": "programmatic_candidate_space",
                    "coverage_footprint": {
                        "l0": ["car1"],
                        "l1": ["car1|ego"],
                        "l2": ["car1|ego|front"],
                    },
                    "vlm_call_cost": 1,
                },
                {
                    "question": "q2",
                    "answer": False,
                    "scene_frame": "frame-b",
                    "template_id": "direction_chain",
                    "answer_type": "boolean",
                    "question_source": "programmatic_candidate_space",
                    "coverage_footprint": {
                        "l0": ["car1"],
                        "l1": ["bus1|car1"],
                        "l2": ["car1|ego|front"],
                    },
                    "vlm_call_cost": 1,
                },
            ],
            "random": [
                {
                    "question": "q3",
                    "answer": "car2",
                    "scene_frame": "frame-a",
                    "template_id": "converge",
                    "answer_type": "object",
                    "question_source": "programmatic_candidate_space",
                    "coverage_l0": ["car2"],
                    "coverage_l1": ["car2|ego"],
                    "coverage_l2": ["car2|ego|front"],
                    "vlm_call_cost": 1,
                },
                {
                    "question": "q3b",
                    "answer": "bus1",
                    "scene_frame": "frame-a",
                    "template_id": "converge",
                    "answer_type": "object",
                    "question_source": "programmatic_candidate_space",
                    "coverage_l0": ["bus1"],
                    "coverage_l1": ["bus1|ego"],
                    "coverage_l2": ["car2|ego|front"],
                    "vlm_call_cost": 1,
                }
            ],
            "official_qa": [
                {
                    "question": "q4",
                    "answer": "car",
                    "scene_frame": "frame-b",
                    "template_type": "object",
                    "question_source": "nuscenes_qa",
                    "vlm_call_cost": 1,
                },
                {
                    "question": "q5",
                    "answer": "yes",
                    "scene_frame": "frame-c",
                    "template_type": "exist",
                    "question_source": "nuscenes_qa",
                    "vlm_call_cost": 1,
                }
            ],
        }
        denominators = {
            "advtest": {"total_l0": 10, "total_l1": 20, "total_l2": 100},
            "random": {"total_l0": 10, "total_l1": 20, "total_l2": 100},
        }

        result = summarize_inputs(suites, denominators, call_budget=2)
        advtest = result["methods"]["advtest"]
        official = result["methods"]["official_qa"]

        self.assertEqual(advtest["questions"], 2)
        self.assertEqual(advtest["covered_l2"], 2)
        self.assertEqual(advtest["total_l2"], 100)
        self.assertEqual(advtest["micro_l2"], 0.02)
        self.assertEqual(advtest["gt_granularity"], "instance_or_relation")
        self.assertTrue(advtest["coverage_comparable"])
        self.assertFalse(official["coverage_comparable"])
        self.assertEqual(official["coverage_status"], "not_available_by_design")
        self.assertEqual(official["gt_granularity"], "category_level_official")
        self.assertEqual(
            result["internal_ablation"]["advtest_minus_random_covered_l2"],
            1,
        )

    def test_loads_structural_denominators_from_fixed_budget_summary(self):
        payload = {
            "methods": {
                "advtest": {
                    "summary": {
                        "total_l0": 1,
                        "total_l1": 2,
                        "total_l2": 3,
                    }
                },
                "random": {
                    "summary": {
                        "total_l0": 1,
                        "total_l1": 2,
                        "total_l2": 3,
                    }
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixed_budget_summary.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            denominators = load_structural_denominators(path)

        self.assertEqual(denominators["advtest"]["total_l2"], 3)
        self.assertEqual(denominators["random"]["total_l1"], 2)


if __name__ == "__main__":
    unittest.main()
