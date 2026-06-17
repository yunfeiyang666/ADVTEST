import json
import tempfile
import unittest
from pathlib import Path

from build_seed_bank_from_eval import build_seed_bank, main


class BuildSeedBankFromEvalTests(unittest.TestCase):
    def test_keeps_only_correct_rows_and_joins_candidate_metadata(self):
        candidates = [
            {
                "scene_frame": "scene-1_frame0",
                "sample_token": "sample-a",
                "question": "What is here?",
                "answer": "car",
                "source_question_id": "sample-a:0",
            },
            {
                "scene_frame": "scene-1_frame0",
                "sample_token": "sample-a",
                "question": "What color?",
                "answer": "red",
                "source_question_id": "sample-a:1",
            },
        ]
        eval_rows = [
            {
                "question_index": 1,
                "scene_frame": "scene-1_frame0",
                "question": "What is here?",
                "answer": "car",
                "predicted": "car",
                "raw_model_output": "car",
                "is_correct": True,
                "mode": "MPLUG",
                "source_question_id": "sample-a:0",
            },
            {
                "question_index": 2,
                "scene_frame": "scene-1_frame0",
                "question": "What color?",
                "answer": "red",
                "predicted": "blue",
                "raw_model_output": "blue",
                "is_correct": False,
                "mode": "MPLUG",
                "source_question_id": "sample-a:1",
            },
        ]

        seeds, summary = build_seed_bank(candidates, eval_rows)

        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0]["seed_id"], "seed_00001")
        self.assertEqual(seeds[0]["sample_token"], "sample-a")
        self.assertEqual(seeds[0]["source_question_id"], "sample-a:0")
        self.assertEqual(seeds[0]["seed_filter_mode"], "MPLUG")
        self.assertEqual(summary["candidate_rows"], 2)
        self.assertEqual(summary["eval_rows"], 2)
        self.assertEqual(summary["seed_rows"], 1)
        self.assertEqual(summary["incorrect_or_rejected_eval_rows"], 1)

    def test_strict_mode_rejects_correct_rows_without_candidates(self):
        with self.assertRaisesRegex(ValueError, "missing from candidate suite"):
            build_seed_bank(
                [],
                [
                    {
                        "is_correct": True,
                        "scene_frame": "scene-1_frame0",
                        "question": "q",
                    }
                ],
            )

    def test_cli_writes_seed_bank_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_path = root / "candidate.jsonl"
            eval_path = root / "eval.jsonl"
            output_path = root / "seeds.jsonl"
            summary_path = root / "summary.json"
            candidate = {
                "scene_frame": "scene-1_frame0",
                "question": "q",
                "answer": "yes",
                "source_question_id": "sample-a:0",
            }
            result = {
                "question_index": 1,
                "scene_frame": "scene-1_frame0",
                "question": "q",
                "answer": "yes",
                "predicted": "yes",
                "raw_model_output": "yes",
                "is_correct": True,
                "mode": "MOCK",
                "source_question_id": "sample-a:0",
            }
            candidate_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            eval_path.write_text(json.dumps(result) + "\n", encoding="utf-8")

            main(
                [
                    "--candidate-suite",
                    str(candidate_path),
                    "--eval-raw-results",
                    str(eval_path),
                    "--output-jsonl",
                    str(output_path),
                    "--summary-json",
                    str(summary_path),
                ]
            )

            self.assertEqual(len(output_path.read_text(encoding="utf-8").splitlines()), 1)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["seed_rows"], 1)


if __name__ == "__main__":
    unittest.main()
