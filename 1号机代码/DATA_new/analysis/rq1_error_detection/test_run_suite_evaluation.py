import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from run_suite_evaluation import evaluate_question, evaluate_suite, failure_signature


class AlwaysWrongEvaluator:
    def evaluate(self, question):
        return "wrong", False


class RealStyleEvaluator:
    def __init__(self):
        self.calls = 0

    def evaluate(self, question, image_path):
        self.calls += 1
        return "car", True


class SuiteEvaluationMetricsTests(unittest.TestCase):
    def test_mplug_missing_image_raises_instead_of_using_mock(self):
        with self.assertRaisesRegex(FileNotFoundError, "real mosaic"):
            evaluate_question(
                RealStyleEvaluator(),
                {"question": "What is visible?", "answer": "car"},
                "MPLUG",
                None,
            )

    def test_raw_mplug_result_records_inference_evidence(self):
        question = {
            "experiment_layer": "cross_paradigm",
            "experiment_method": "official_qa",
            "question_source": "nuscenes_qa",
            "source_question_id": "sample-a:0",
            "source_sample_token": "sample-a",
            "scene_frame": "scene-1_frame2",
            "question": "What is visible?",
            "answer": "car",
            "vlm_call_cost": 1,
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite_path = root / "official_qa_suite.jsonl"
            suite_path.write_text(json.dumps(question) + "\n", encoding="utf-8")
            image_path = root / "real.jpg"
            image_path.write_bytes(b"real image")
            with patch(
                "run_suite_evaluation.resolve_image_path",
                return_value=image_path,
            ):
                evaluate_suite(
                    suite_path,
                    RealStyleEvaluator(),
                    "MPLUG",
                    root / "eval",
                    root / "outputs",
                    root / "data",
                )
            raw_path = root / "eval" / "official_qa_suite_raw_results.jsonl"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))

        self.assertEqual(raw["prompt"], "What is visible?")
        self.assertEqual(raw["mode"], "MPLUG")
        self.assertEqual(raw["raw_model_output"], "car")
        self.assertIsNone(raw["error"])
        self.assertGreaterEqual(raw["inference_elapsed_seconds"], 0.0)

    def test_mplug_does_not_reuse_cached_predictions_as_real_calls(self):
        question = {
            "experiment_layer": "cross_paradigm",
            "experiment_method": "official_qa",
            "question_source": "nuscenes_qa",
            "source_question_id": "sample-a:0",
            "source_sample_token": "sample-a",
            "scene_frame": "scene-1_frame2",
            "question": "What is visible?",
            "answer": "car",
            "vlm_call_cost": 1,
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite_path = root / "official_qa_suite.jsonl"
            suite_path.write_text(
                json.dumps(question) + "\n" + json.dumps(question) + "\n",
                encoding="utf-8",
            )
            image_path = root / "real.jpg"
            image_path.write_bytes(b"real image")
            vlm = RealStyleEvaluator()
            with patch(
                "run_suite_evaluation.resolve_image_path",
                return_value=image_path,
            ):
                result = evaluate_suite(
                    suite_path,
                    vlm,
                    "MPLUG",
                    root / "eval",
                    root / "outputs",
                    root / "data",
                    write_raw=False,
                )

        self.assertEqual(result["vlm_calls"], 2)
        self.assertEqual(vlm.calls, 2)

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
