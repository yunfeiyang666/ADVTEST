import unittest

from qatest_suite_audit import audit_suite


class QATestSuiteAuditTests(unittest.TestCase):
    def test_audit_detects_duplicates_answer_mismatch_and_leakage(self):
        base = {
            "question": "What is visible?",
            "answer": "car",
            "source_question_id": "sample-a:0",
            "source_sample_token": "sample-a",
            "scene_frame": "scene-1_frame2",
            "experiment_method": "qatest_adapted",
            "generation_adapter": "qatest_adapted_portable",
            "question_source": "nuscenes_qa",
            "mutation_operator": "double_question_mark",
        }
        records = [
            dict(base),
            {
                **base,
                "answer": "truck",
                "coverage_footprint": {"l2": []},
            },
        ]

        audit = audit_suite(
            records,
            source_answers={"sample-a:0": "car"},
        )

        self.assertEqual(audit["questions"], 2)
        self.assertEqual(audit["unique_normalized_questions"], 1)
        self.assertEqual(audit["duplicate_questions"], 1)
        self.assertEqual(audit["answer_mismatches"], 1)
        self.assertEqual(audit["boundary_violations"], 1)

    def test_clean_suite_reports_source_and_operator_diversity(self):
        records = [
            {
                "question": "What is visible??",
                "answer": "car",
                "source_question_id": "sample-a:0",
                "source_sample_token": "sample-a",
                "scene_frame": "scene-1_frame2",
                "experiment_method": "qatest_adapted",
                "generation_adapter": "qatest_adapted_portable",
                "question_source": "nuscenes_qa",
                "mutation_operator": "double_question_mark",
            },
            {
                "question": "How many vehicels are visible?",
                "answer": "2",
                "source_question_id": "sample-a:1",
                "source_sample_token": "sample-a",
                "scene_frame": "scene-1_frame2",
                "experiment_method": "qatest_adapted",
                "generation_adapter": "qatest_adapted_portable",
                "question_source": "nuscenes_qa",
                "mutation_operator": "spelling_deletion",
            },
        ]

        audit = audit_suite(
            records,
            source_answers={"sample-a:0": "car", "sample-a:1": "2"},
        )

        self.assertEqual(audit["source_question_count"], 2)
        self.assertEqual(audit["sample_count"], 1)
        self.assertEqual(audit["frame_count"], 1)
        self.assertEqual(
            audit["operator_counts"],
            {"double_question_mark": 1, "spelling_deletion": 1},
        )
        self.assertEqual(audit["answer_mismatches"], 0)
        self.assertEqual(audit["boundary_violations"], 0)


if __name__ == "__main__":
    unittest.main()
