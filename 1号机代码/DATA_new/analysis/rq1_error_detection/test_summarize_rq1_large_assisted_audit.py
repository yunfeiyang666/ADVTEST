import unittest

from summarize_rq1_large_assisted_audit import (
    fill_assisted_labels,
    summarize_assisted_review,
)


def _row(bucket, method, auto_label, auto_issue, auto_confidence="high"):
    return {
        "bucket": bucket,
        "method": method,
        "auto_valid_failure": auto_label,
        "auto_issue_type": auto_issue,
        "auto_confidence": auto_confidence,
        "auto_notes": "synthetic auto note",
        "manual_valid_failure": "",
        "manual_issue_type": "",
        "manual_notes": "",
    }


class SummarizeRq1LargeAssistedAuditTest(unittest.TestCase):
    def test_fill_assisted_labels_copies_auto_prefill(self):
        rows = [
            _row(
                "advtest_only_l2",
                "advtest",
                "yes",
                "valid_visual_or_structural_error",
            ),
            _row(
                "random_only_l2",
                "random",
                "uncertain",
                "answer_granularity_mismatch",
                auto_confidence="low",
            ),
        ]

        filled = fill_assisted_labels(rows)

        self.assertEqual(filled[0]["manual_valid_failure"], "yes")
        self.assertEqual(
            filled[0]["manual_issue_type"], "valid_visual_or_structural_error"
        )
        self.assertIn("ASSISTED_REVIEW", filled[0]["manual_notes"])
        self.assertEqual(filled[1]["manual_valid_failure"], "uncertain")
        self.assertIn("retained as uncertain", filled[1]["manual_notes"])

    def test_fill_assisted_labels_preserves_existing_manual_without_overwrite(self):
        row = _row(
            "advtest_only_l2",
            "advtest",
            "yes",
            "valid_visual_or_structural_error",
        )
        row["manual_valid_failure"] = "no"
        row["manual_issue_type"] = "ambiguous_question"
        row["manual_notes"] = "human review disagrees"

        preserved = fill_assisted_labels([row], overwrite=False)
        overwritten = fill_assisted_labels([row], overwrite=True)

        self.assertEqual(preserved[0]["manual_valid_failure"], "no")
        self.assertEqual(overwritten[0]["manual_valid_failure"], "yes")

    def test_summarize_assisted_review_scales_bucket_estimates(self):
        manifest = {
            "universe": {
                "advtest_only_l2": 1000,
                "random_only_l2": 500,
                "shared_l2": 200,
            }
        }
        rows = fill_assisted_labels(
            [
                _row(
                    "advtest_only_l2",
                    "advtest",
                    "yes",
                    "valid_visual_or_structural_error",
                ),
                _row(
                    "advtest_only_l2",
                    "advtest",
                    "yes",
                    "valid_visual_or_structural_error",
                ),
                _row(
                    "random_only_l2",
                    "random",
                    "yes",
                    "valid_visual_or_structural_error",
                ),
                _row(
                    "random_only_l2",
                    "random",
                    "no",
                    "answer_granularity_mismatch",
                ),
                _row(
                    "shared_l2_advtest",
                    "advtest",
                    "yes",
                    "valid_visual_or_structural_error",
                ),
                _row(
                    "shared_l2_random",
                    "random",
                    "uncertain",
                    "ambiguous_question",
                ),
            ]
        )

        summary = summarize_assisted_review(rows, manifest)

        self.assertEqual(summary["total_rows"], 6)
        self.assertEqual(
            summary["by_bucket"]["advtest_only_l2"]["estimated_valid_total"],
            1000,
        )
        self.assertEqual(
            summary["by_bucket"]["random_only_l2"]["estimated_valid_total"],
            250,
        )
        self.assertEqual(
            summary["by_bucket"]["shared_l2_advtest"]["universe_total"], 200
        )
        self.assertGreater(
            summary["exclusive_effect"]["advtest_minus_random_estimated_valid_total"],
            0,
        )
        self.assertIn("assisted", summary["label_source"])


if __name__ == "__main__":
    unittest.main()
