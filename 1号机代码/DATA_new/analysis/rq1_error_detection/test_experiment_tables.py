import sys
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from experiment_tables import (
    build_capacity_rows,
    build_common_budget_rows,
    build_structural_rows,
)


class ExperimentTableTests(unittest.TestCase):
    def test_structural_rows_use_generation_budget(self):
        summary = {
            "generation_budget": 1000,
            "methods": {
                "advtest": {
                    "summary": {
                        "suite_size": 1000,
                        "micro_l0": 1.0,
                        "micro_l1": 0.7,
                        "micro_l2": 0.2,
                        "unique_l2_per_question": 1.5,
                        "auc_micro_l2": 0.1,
                    }
                }
            },
        }

        rows = build_structural_rows(summary)

        self.assertEqual(rows[0]["generation_budget"], 1000)
        self.assertEqual(rows[0]["method"], "advtest")

    def test_common_budget_rows_reject_mixed_call_counts(self):
        results = [
            {
                "method": "advtest",
                "vlm_calls": 164,
                "unique_failures": 20,
                "unique_failures_per_100_calls": 12.2,
                "duplicate_failure_rate": 0.1,
                "failure_category_count": 4,
            },
            {
                "method": "qatest",
                "vlm_calls": 1000,
                "unique_failures": 50,
                "unique_failures_per_100_calls": 5.0,
                "duplicate_failure_rate": 0.2,
                "failure_category_count": 3,
            },
        ]

        with self.assertRaisesRegex(ValueError, "same VLM-call budget"):
            build_common_budget_rows(results)

    def test_common_budget_rows_accept_equal_call_counts(self):
        results = [
            {
                "method": method,
                "vlm_calls": 164,
                "unique_failures": failures,
                "unique_failures_per_100_calls": failures / 1.64,
                "duplicate_failure_rate": 0.0,
                "failure_category_count": 2,
            }
            for method, failures in (("advtest", 20), ("qatest", 10))
        ]

        rows = build_common_budget_rows(results)

        self.assertEqual({row["vlm_call_budget"] for row in rows}, {164})

    def test_capacity_rows_allow_different_actual_calls(self):
        results = [
            {
                "method": "official_qa",
                "vlm_calls": 164,
                "vlm_call_budget": 1000,
                "unique_failures": 10,
                "unique_failures_per_100_calls": 6.1,
                "duplicate_failure_rate": 0.0,
                "failure_category_count": 3,
            },
            {
                "method": "advtest",
                "vlm_calls": 1000,
                "vlm_call_budget": 1000,
                "unique_failures": 80,
                "unique_failures_per_100_calls": 8.0,
                "duplicate_failure_rate": 0.1,
                "failure_category_count": 5,
            },
        ]

        rows = build_capacity_rows(results, requested_vlm_call_budget=1000)

        self.assertEqual(
            {row["method"]: row["actual_vlm_calls"] for row in rows},
            {"official_qa": 164, "advtest": 1000},
        )


if __name__ == "__main__":
    unittest.main()
