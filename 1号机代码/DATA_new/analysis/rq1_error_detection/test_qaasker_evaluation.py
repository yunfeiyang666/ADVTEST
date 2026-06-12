import sys
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from qaasker_adapter import QAAskeRAdapter
from run_qaasker_evaluation import evaluate_qaasker_seeds


class ScriptedEvaluator:
    def __init__(self, answers):
        self.answers = iter(answers)

    def evaluate(self, question):
        predicted = next(self.answers)
        expected = str(question["answer"]).lower()
        return predicted, predicted.lower() == expected


class QAAskeREvaluationTests(unittest.TestCase):
    def setUp(self):
        self.seed = {
            "official_question_id": "sample-a:0",
            "sample_token": "sample-a",
            "question": "What vehicle is visible in front?",
            "answer": "car",
        }
        self.adapter = QAAskeRAdapter(
            followup_generator=lambda question, answer: {
                "question": f"Is {answer} visible in front?",
                "answer": "yes",
                "metamorphic_relation": "MR2",
            }
        )

    def test_primary_answer_drives_followup_and_pair_costs_two_calls(self):
        result = evaluate_qaasker_seeds(
            [
                ("scene-1_frame2", self.seed),
                (
                    "scene-1_frame3",
                    dict(
                        self.seed,
                        official_question_id="sample-a:1",
                        question="What vehicle is visible behind?",
                    ),
                ),
            ],
            adapter=self.adapter,
            vlm=ScriptedEvaluator(["truck", "no"]),
            mode="MOCK",
            vlm_call_budget=2,
        )

        self.assertEqual(result["vlm_calls"], 2)
        self.assertEqual(result["pairs"], 1)
        self.assertEqual(result["violations"], 1)
        self.assertEqual(result["budget_stop_reason"], "global_budget")
        self.assertEqual(result["records"][1]["primary_sut_answer"], "truck")
        self.assertIn("truck", result["records"][1]["question"])

    def test_odd_budget_stops_after_primary_without_partial_pair(self):
        result = evaluate_qaasker_seeds(
            [("scene-1_frame2", self.seed)],
            adapter=self.adapter,
            vlm=ScriptedEvaluator(["truck"]),
            mode="MOCK",
            vlm_call_budget=1,
        )

        self.assertEqual(result["vlm_calls"], 0)
        self.assertEqual(result["pairs"], 0)
        self.assertEqual(result["budget_stop_reason"], "insufficient_budget_for_pair")

    def test_consistent_followup_is_not_violation(self):
        result = evaluate_qaasker_seeds(
            [("scene-1_frame2", self.seed)],
            adapter=self.adapter,
            vlm=ScriptedEvaluator(["truck", "yes"]),
            mode="MOCK",
            vlm_call_budget=2,
        )

        self.assertEqual(result["violations"], 0)
        self.assertEqual(result["violation_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
