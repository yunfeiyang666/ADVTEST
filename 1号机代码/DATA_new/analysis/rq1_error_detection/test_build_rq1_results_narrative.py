import tempfile
import unittest
from pathlib import Path

from build_rq1_results_narrative import (
    build_adjusted_estimate,
    build_narrative_payload,
    write_markdown,
)


class BuildRq1ResultsNarrativeTest(unittest.TestCase):
    def test_adjusted_estimate_uses_bucket_valid_rates(self):
        failure_audit = {
            "summary": {
                "failed_l2_overlap": {
                    "advtest_only": 300,
                    "random_only": 100,
                    "shared": 50,
                }
            }
        }
        manual_summary = {
            "by_bucket": {
                "advtest_only_l2": {"valid_rate": 2 / 3},
                "random_only_l2": {"valid_rate": 3 / 4},
                "shared_l2_advtest": {"valid_rate": 0.5},
                "shared_l2_random": {"valid_rate": 1.0},
            }
        }

        estimate = build_adjusted_estimate(failure_audit, manual_summary)

        self.assertAlmostEqual(
            estimate["estimated_valid_advtest_only_l2"], 200
        )
        self.assertAlmostEqual(
            estimate["estimated_valid_random_only_l2"], 75
        )
        self.assertAlmostEqual(estimate["estimated_valid_shared_l2"], 37.5)
        self.assertAlmostEqual(
            estimate["estimated_advtest_only_minus_random_only_valid_l2"], 125
        )

    def test_build_narrative_payload_and_markdown(self):
        report_pack = {
            "main_call1000_table": [
                {
                    "method": "advtest",
                    "unique_failures": 981,
                    "failed_unique_l2": 4488,
                },
                {
                    "method": "random",
                    "unique_failures": 912,
                    "failed_unique_l2": 2727,
                },
            ],
            "adv_vs_random_gains": [
                {
                    "call_budget": 1000,
                    "unique_failure_delta": 69,
                    "unique_failure_relative_gain": 69 / 912,
                    "failed_unique_l2_delta": 1761,
                    "failed_unique_l2_relative_gain": 1761 / 2727,
                    "input_covered_l2_delta": 1690,
                    "input_covered_l2_relative_gain": 1690 / 2818,
                }
            ],
        }
        failure_audit = {
            "summary": {
                "failed_l2_overlap": {
                    "advtest_only": 3070,
                    "random_only": 1309,
                    "shared": 1418,
                }
            }
        }
        manual_summary = {
            "total_rows": 48,
            "overall": {
                "valid_rate": 33 / 48,
                "valid_yes": 33,
                "invalid_or_uncertain": 15,
            },
            "by_bucket": {
                "advtest_only_l2": {"valid_rate": 8 / 12},
                "random_only_l2": {"valid_rate": 9 / 12},
                "shared_l2_advtest": {"valid_rate": 8 / 12},
                "shared_l2_random": {"valid_rate": 8 / 12},
            },
            "issue_type_counts": {"answer_granularity_mismatch": 15},
        }

        payload = build_narrative_payload(
            report_pack, failure_audit, manual_summary
        )

        estimate = payload["adjusted_effective_failure_estimate"]
        self.assertAlmostEqual(
            estimate["estimated_valid_advtest_only_l2"], 2046.6666666666665
        )
        self.assertAlmostEqual(
            estimate["estimated_valid_random_only_l2"], 981.75
        )
        self.assertIn("coverage-breadth", payload["recommended_claim"])

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "narrative.md"
            write_markdown(output, payload)
            text = output.read_text(encoding="utf-8")
            self.assertIn("Random-only has a slightly higher", text)
            self.assertIn("Paper-Ready Paragraph", text)


if __name__ == "__main__":
    unittest.main()
