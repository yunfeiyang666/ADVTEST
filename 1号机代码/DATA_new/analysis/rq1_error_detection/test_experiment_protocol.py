import sys
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from experiment_protocol import (
    EXTERNAL_LAYER,
    STRUCTURAL_LAYER,
    annotate_provenance,
    validate_question_boundary,
)


class ExperimentProtocolTests(unittest.TestCase):
    def test_external_question_rejects_advtest_private_fields(self):
        question = {
            "question": "Are any cars visible?",
            "answer": "yes",
            "coverage_footprint": {"l2": ["car1|car2|ego"]},
        }

        with self.assertRaisesRegex(ValueError, "coverage_footprint"):
            validate_question_boundary(question, EXTERNAL_LAYER)

    def test_structural_question_allows_coverage_fields(self):
        question = {
            "question": "Which car is behind car1?",
            "answer": "car2",
            "coverage_footprint": {"l2": ["car1|car2|ego"]},
        }

        validate_question_boundary(question, STRUCTURAL_LAYER)

    def test_annotation_adds_required_provenance(self):
        question = {"question": "Are any cars visible?", "answer": "yes"}

        annotated = annotate_provenance(
            question,
            layer=EXTERNAL_LAYER,
            method="qatest",
            question_source="nuscenes_qa",
            source_question_id="official-7",
            source_sample_token="sample-1",
            generation_adapter="qatest",
            uses_coverage_feedback=False,
            vlm_call_cost=1,
            scene_frame="scene-1_frame2",
            global_budget_index=3,
        )

        self.assertEqual(annotated["experiment_layer"], EXTERNAL_LAYER)
        self.assertEqual(annotated["experiment_method"], "qatest")
        self.assertEqual(annotated["source_question_id"], "official-7")
        self.assertFalse(annotated["uses_coverage_feedback"])
        self.assertEqual(annotated["vlm_call_cost"], 1)
        self.assertNotIn("coverage_footprint", annotated)


if __name__ == "__main__":
    unittest.main()
