import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from official_qa_experiment import (
    build_official_suite,
    index_official_questions,
    load_official_questions,
)


class OfficialQAExperimentTests(unittest.TestCase):
    def setUp(self):
        self.questions = [
            {
                "split": "val",
                "sample_token": "sample-a",
                "question": "Are any moving bicycles visible?",
                "answer": "no",
                "num_hop": 0,
                "template_type": "exist",
            },
            {
                "split": "val",
                "sample_token": "sample-a",
                "question": "How many cars are visible?",
                "answer": "2",
                "num_hop": 0,
                "template_type": "count",
            },
            {
                "split": "val",
                "sample_token": "sample-b",
                "question": "Is the bus moving?",
                "answer": "yes",
                "num_hop": 1,
                "template_type": "status",
            },
        ]

    def test_loads_questions_from_official_json_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "questions.json"
            path.write_text(
                json.dumps({"info": {}, "questions": self.questions}),
                encoding="utf-8",
            )

            loaded = load_official_questions(path)

        self.assertEqual(loaded, self.questions)

    def test_indexes_questions_by_sample_token_and_assigns_source_ids(self):
        indexed = index_official_questions(self.questions)

        self.assertEqual(len(indexed["sample-a"]), 2)
        self.assertEqual(
            indexed["sample-a"][0]["official_question_id"],
            "sample-a:0",
        )

    def test_qatest_uses_only_official_seed_and_preserves_source_identity(self):
        suite = build_official_suite(
            method="qatest",
            frame_samples=[("scene-1_frame2", "sample-a")],
            questions_by_sample=index_official_questions(self.questions),
            budget=2,
            seed=11,
        )

        self.assertEqual(len(suite), 2)
        for question in suite:
            self.assertEqual(question["question_source"], "nuscenes_qa")
            self.assertEqual(question["source_sample_token"], "sample-a")
            self.assertTrue(question["source_question_id"].startswith("sample-a:"))
            self.assertEqual(question["experiment_method"], "qatest")
            self.assertNotIn("coverage_footprint", question)
            self.assertNotIn("path_pattern", question)

    def test_qatest_avoids_duplicate_mutated_text_with_repeated_seed_cycles(self):
        suite = build_official_suite(
            method="qatest",
            frame_samples=[("scene-1_frame2", "sample-a")],
            questions_by_sample=index_official_questions(self.questions),
            budget=12,
            seed=11,
        )

        self.assertEqual(len(suite), 12)
        self.assertEqual(len({question["question"] for question in suite}), 12)

    def test_official_qa_does_not_mutate_seed_text(self):
        suite = build_official_suite(
            method="official_qa",
            frame_samples=[("scene-1_frame2", "sample-a")],
            questions_by_sample=index_official_questions(self.questions),
            budget=2,
            seed=7,
        )

        self.assertEqual(
            {question["question"] for question in suite},
            {
                "Are any moving bicycles visible?",
                "How many cars are visible?",
            },
        )

    def test_builder_rejects_unknown_external_method(self):
        with self.assertRaisesRegex(ValueError, "Unknown official-QA method"):
            build_official_suite(
                method="advtest",
                frame_samples=[("scene-1_frame2", "sample-a")],
                questions_by_sample=index_official_questions(self.questions),
                budget=1,
                seed=1,
            )


if __name__ == "__main__":
    unittest.main()
