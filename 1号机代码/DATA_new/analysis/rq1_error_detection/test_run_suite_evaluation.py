import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from run_suite_evaluation import evaluate_suite, failure_signature


class AlwaysWrongEvaluator:
    def evaluate(self, question):
        return "wrong", False


class SuiteEvaluationMetricsTests(unittest.TestCase):
    def test_qatest_mutations_of_same_seed_count_as_one_independent_failure(self):
        first = {
            "experiment_layer": "cross_paradigm",
            "experiment_method": "qatest",
            "question_source": "nuscenes_qa",
            "source_question_id": "sample-a:0",
            "source_sample_token": "sample-a",
            "scene_frame": "scene-1_frame2",
            "template_type": "exist",
            "question": "Are any cars visible??",
            "answer": "yes",
        }
        second = dict(first, question="are any cars visible?")

        self.assertEqual(
            failure_signature(first, "wrong"),
            failure_signature(second, "wrong"),
        )

    def test_vlm_call_budget_stops_before_record_that_would_exceed_budget(self):
        questions = [
            {
                "experiment_layer": "cross_paradigm",
                "experiment_method": "qaasker",
                "question_source": "nuscenes_qa",
                "source_question_id": f"sample-a:{index}",
                "source_sample_token": "sample-a",
                "scene_frame": "scene-1_frame2",
                "question": f"q{index}",
                "answer": "yes",
                "vlm_call_cost": cost,
            }
            for index, cost in enumerate([1, 2, 1])
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite_path = root / "qaasker_suite.jsonl"
            suite_path.write_text(
                "".join(json.dumps(row) + "\n" for row in questions),
                encoding="utf-8",
            )
            result = evaluate_suite(
                suite_path,
                AlwaysWrongEvaluator(),
                "MOCK",
                root / "eval",
                root / "outputs",
                root / "data",
                vlm_call_budget=2,
                write_raw=False,
            )

        self.assertEqual(result["questions"], 1)
        self.assertEqual(result["vlm_calls"], 1)
        self.assertEqual(result["budget_stop_reason"], "next_record_exceeds_budget")

    def test_unique_failure_metrics_deduplicate_same_official_seed(self):
        questions = [
            {
                "experiment_layer": "cross_paradigm",
                "experiment_method": "qatest",
                "question_source": "nuscenes_qa",
                "source_question_id": "sample-a:0",
                "source_sample_token": "sample-a",
                "scene_frame": "scene-1_frame2",
                "template_type": "exist",
                "question": text,
                "answer": "yes",
                "vlm_call_cost": 1,
            }
            for text in ("Are cars visible??", "Are cras visible?")
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite_path = root / "qatest_suite.jsonl"
            suite_path.write_text(
                "".join(json.dumps(row) + "\n" for row in questions),
                encoding="utf-8",
            )
            result = evaluate_suite(
                suite_path,
                AlwaysWrongEvaluator(),
                "MOCK",
                root / "eval",
                root / "outputs",
                root / "data",
                write_raw=False,
            )

        self.assertEqual(result["wrong"], 2)
        self.assertEqual(result["unique_failures"], 1)
        self.assertEqual(result["duplicate_failure_rate"], 0.5)
        self.assertEqual(result["unique_failures_per_100_calls"], 50.0)


if __name__ == "__main__":
    unittest.main()
