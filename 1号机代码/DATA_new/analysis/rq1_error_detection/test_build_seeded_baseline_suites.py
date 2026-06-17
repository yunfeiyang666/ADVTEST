import sys
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from build_seeded_baseline_suites import (
    annotate_qatest_records,
    build_qaasker_suite,
    count_duplicate_questions,
    seed_primary_answer,
    to_qatest_seed,
)


class SeededBaselineSuiteTests(unittest.TestCase):
    def setUp(self):
        self.seed = {
            "seed_id": "seed_00001",
            "source_question_id": "sample-a:0",
            "sample_token": "sample-a",
            "source_sample_token": "sample-a",
            "scene_frame": "scene-1_frame2",
            "question": "What object is visible?",
            "answer": "car",
            "template_type": "what",
            "seed_filter_predicted": "A car is visible.",
        }

    def test_qatest_seed_shape_matches_original_run_contract(self):
        converted = to_qatest_seed(self.seed)

        self.assertEqual(converted["init_q"], "What object is visible?")
        self.assertTrue(converted["is_init"])
        self.assertEqual(converted["aug_times"], 0)
        self.assertEqual(converted["iter_times"], 0)

    def test_qatest_records_get_external_provenance(self):
        generated = [
            {
                **to_qatest_seed(self.seed),
                "question": "What object is visible??",
                "aug": "double_question_mark",
                "is_init": False,
            }
        ]

        suite = annotate_qatest_records(generated, budget=1)

        self.assertEqual(suite[0]["experiment_method"], "qatest")
        self.assertEqual(suite[0]["question_source"], "nuscenes_qa")
        self.assertFalse(suite[0]["uses_coverage_feedback"])
        self.assertEqual(suite[0]["vlm_call_cost"], 1)
        self.assertEqual(suite[0]["source_question_id"], "sample-a:0")

    def test_seed_primary_answer_prefers_stored_vlm_answer(self):
        self.assertEqual(seed_primary_answer(self.seed), "A car is visible.")
        self.assertEqual(
            seed_primary_answer(self.seed, prefer_vlm_answer=False),
            "car",
        )

    def test_qaasker_records_rejections_without_faking_success(self):
        def generator(question, answer):
            if "bad" in question:
                raise ValueError("cannot convert")
            return {
                "question": f"Is it true that {answer}",
                "answer": "yes",
                "metamorphic_relation": "MR2",
            }

        good = dict(self.seed)
        bad = dict(self.seed, seed_id="seed_00002", question="bad question")

        result = build_qaasker_suite(
            [good, bad],
            budget=3,
            seed=3,
            followup_generator=generator,
            max_attempts=4,
        )

        self.assertLess(result["summary"]["accepted_for_eval"], 3)
        self.assertGreater(result["summary"]["generation_rejected"], 0)
        self.assertTrue(result["rejected"])

    def test_duplicate_counter_uses_same_frame_normalized_question(self):
        records = [
            {"scene_frame": "a", "question": "Is there a car?"},
            {"scene_frame": "a", "question": " is there a car ? "},
            {"scene_frame": "b", "question": "Is there a car?"},
        ]

        self.assertEqual(count_duplicate_questions(records), 1)


if __name__ == "__main__":
    unittest.main()
