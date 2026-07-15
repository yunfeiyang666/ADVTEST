import json
import sys
import tempfile
import unittest
from pathlib import Path


RQ1_DIR = Path(__file__).resolve().parents[1] / "rq1_error_detection"
sys.path.insert(0, str(RQ1_DIR))

from run_suite_evaluation import evaluate_suite  # noqa: E402


class AlwaysCorrectEvaluator:
    def evaluate(self, question, image_path=None):
        return str(question["answer"]), ""


class ResumeEvaluationTests(unittest.TestCase):
    def test_resume_appends_after_exact_raw_prefix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = root / "resume_suite.jsonl"
            rows = [
                {
                    "scene_frame": f"scene-0200_frame{index}",
                    "source_question_id": f"source-{index}",
                    "question": f"Question {index}?",
                    "answer": "yes",
                    "family": "l0",
                }
                for index in range(3)
            ]
            suite.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            output = root / "results"
            kwargs = {
                "path": suite,
                "vlm": AlwaysCorrectEvaluator(),
                "mode": "MOCK",
                "output_dir": output,
                "outputs_root": root,
                "dataroot": root,
            }

            first = evaluate_suite(**kwargs, limit=1)
            resumed = evaluate_suite(**kwargs, resume=True)

            raw_path = output / "resume_suite_raw_results.jsonl"
            raw_rows = [
                json.loads(line)
                for line in raw_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(first["questions"], 1)
            self.assertEqual(resumed["questions"], 3)
            self.assertEqual(resumed["resumed_questions"], 1)
            self.assertEqual(len(raw_rows), 3)

    def test_resume_rejects_nonmatching_prefix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = root / "bad_suite.jsonl"
            suite.write_text(
                json.dumps(
                    {
                        "scene_frame": "scene-0200_frame0",
                        "source_question_id": "source-0",
                        "question": "Question?",
                        "answer": "yes",
                        "family": "l0",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output = root / "results"
            output.mkdir()
            (output / "bad_suite_raw_results.jsonl").write_text(
                json.dumps(
                    {
                        "scene_frame": "scene-0200_frame0",
                        "source_question_id": "different-source",
                        "question": "Question?",
                        "predicted": "yes",
                        "is_correct": True,
                        "vlm_call_cost": 1,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "not an exact prefix"):
                evaluate_suite(
                    suite,
                    AlwaysCorrectEvaluator(),
                    "MOCK",
                    output,
                    root,
                    root,
                    resume=True,
                )


if __name__ == "__main__":
    unittest.main()
