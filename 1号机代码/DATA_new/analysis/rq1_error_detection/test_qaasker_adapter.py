import sys
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from qaasker_adapter import QAAskeRAdapter


class QAAskeRAdapterTests(unittest.TestCase):
    def setUp(self):
        self.seed = {
            "official_question_id": "sample-a:0",
            "sample_token": "sample-a",
            "question": "What vehicle is in front?",
            "answer": "car",
        }

    def test_followup_requires_primary_sut_answer(self):
        adapter = QAAskeRAdapter(followup_generator=lambda question, answer: {})

        with self.assertRaisesRegex(ValueError, "primary SUT answer"):
            adapter.build_followup(
                self.seed,
                primary_sut_answer="",
                scene_frame="scene-1_frame2",
                global_budget_index=2,
            )

    def test_missing_backend_fails_instead_of_using_fake_selector(self):
        adapter = QAAskeRAdapter()

        with self.assertRaisesRegex(RuntimeError, "backend is not configured"):
            adapter.build_followup(
                self.seed,
                primary_sut_answer="car",
                scene_frame="scene-1_frame2",
                global_budget_index=2,
            )

    def test_primary_and_followup_pair_cost_two_vlm_calls(self):
        adapter = QAAskeRAdapter(
            followup_generator=lambda question, answer: {
                "question": f"Is the answer {answer}?",
                "answer": "yes",
                "metamorphic_relation": "MR2",
            }
        )

        primary = adapter.build_primary(
            self.seed,
            scene_frame="scene-1_frame2",
            global_budget_index=1,
        )
        followup = adapter.build_followup(
            self.seed,
            primary_sut_answer="car",
            scene_frame="scene-1_frame2",
            global_budget_index=2,
        )

        self.assertEqual(primary["vlm_call_cost"], 1)
        self.assertEqual(followup["vlm_call_cost"], 1)
        self.assertEqual(followup["qaasker_pair_vlm_call_cost"], 2)
        self.assertEqual(followup["primary_sut_answer"], "car")
        self.assertEqual(followup["question_source"], "nuscenes_qa")


if __name__ == "__main__":
    unittest.main()
