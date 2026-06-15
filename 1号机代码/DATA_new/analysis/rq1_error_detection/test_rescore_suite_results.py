import json
import tempfile
import unittest
from pathlib import Path

from rescore_suite_results import rescore_raw


class RescoreSuiteResultsTests(unittest.TestCase):
    def test_rescore_detects_false_positive_and_deduplicates_official_seed(self):
        rows = [
            {
                "method": "qatest_adapted",
                "scene_frame": "scene-1_frame0",
                "family": "exist",
                "question": "Is there no car?",
                "answer": "no",
                "predicted": "I cannot determine that.",
                "raw_model_output": "I cannot determine that.",
                "is_correct": True,
                "question_source": "nuscenes_qa",
                "source_question_id": "sample-a:0",
                "l2_items": [],
                "vlm_call_cost": 1,
            },
            {
                "method": "qatest_adapted",
                "scene_frame": "scene-1_frame1",
                "family": "exist",
                "question": "Is there no car??",
                "answer": "no",
                "predicted": "There is no car.",
                "raw_model_output": "There is no car.",
                "is_correct": True,
                "question_source": "nuscenes_qa",
                "source_question_id": "sample-a:0",
                "l2_items": [],
                "vlm_call_cost": 1,
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "qatest_adapted_suite_raw_results.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            result = rescore_raw(path)

        self.assertEqual(result["questions"], 2)
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["wrong"], 1)
        self.assertEqual(result["changed_correct_to_wrong"], 1)
        self.assertEqual(result["changed_wrong_to_correct"], 0)
        self.assertEqual(result["unique_failures"], 1)
        self.assertEqual(result["vlm_calls"], 2)

    def test_rescore_uses_l2_items_for_structural_failure_identity(self):
        rows = [
            {
                "method": "advtest",
                "scene_frame": "scene-1_frame0",
                "family": "converge",
                "question": f"Question {index}",
                "answer": "car",
                "predicted": "truck",
                "raw_model_output": "truck",
                "is_correct": False,
                "question_source": "scene_graph",
                "source_question_id": f"source-{index}",
                "l2_items": ["item-a"],
                "vlm_call_cost": 1,
            }
            for index in range(2)
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "advtest_suite_raw_results.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            result = rescore_raw(path)

        self.assertEqual(result["wrong"], 2)
        self.assertEqual(result["unique_failures"], 1)
        self.assertEqual(result["duplicate_failure_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
