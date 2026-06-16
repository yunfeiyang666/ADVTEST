import tempfile
import unittest
from pathlib import Path

from summarize_rq1_manual_failure_audit import (
    load_review_rows,
    summarize_rows,
    write_summary,
)


HEADER = (
    "bucket,method,manual_valid_failure,manual_issue_type,manual_notes\n"
)


class SummarizeRq1ManualFailureAuditTest(unittest.TestCase):
    def test_summarize_rows_counts_labels_by_bucket_and_method(self):
        rows = [
            {
                "bucket": "advtest_only_l2",
                "method": "advtest",
                "manual_valid_failure": "yes",
                "manual_issue_type": "valid_visual_or_structural_error",
                "manual_notes": "opposite direction",
            },
            {
                "bucket": "advtest_only_l2",
                "method": "advtest",
                "manual_valid_failure": "no",
                "manual_issue_type": "answer_granularity_mismatch",
                "manual_notes": "class only",
            },
            {
                "bucket": "random_only_l2",
                "method": "random",
                "manual_valid_failure": "uncertain",
                "manual_issue_type": "ambiguous_question",
                "manual_notes": "cannot tell",
            },
        ]

        summary = summarize_rows(rows)

        self.assertEqual(summary["total_rows"], 3)
        self.assertEqual(summary["overall"]["valid_yes"], 1)
        self.assertAlmostEqual(summary["overall"]["valid_rate"], 1 / 3)
        self.assertEqual(
            summary["by_bucket"]["advtest_only_l2"]["valid_no"], 1
        )
        self.assertEqual(summary["by_method"]["random"]["valid_uncertain"], 1)
        self.assertEqual(
            summary["issue_type_counts"]["answer_granularity_mismatch"], 1
        )

    def test_missing_annotation_fails_validation(self):
        with self.assertRaisesRegex(ValueError, "manual_valid_failure"):
            summarize_rows(
                [
                    {
                        "bucket": "advtest_only_l2",
                        "method": "advtest",
                        "manual_valid_failure": "",
                        "manual_issue_type": "valid_visual_or_structural_error",
                        "manual_notes": "missing label",
                    }
                ]
            )

    def test_load_and_write_summary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "review.csv"
            csv_path.write_text(
                HEADER
                + "advtest_only_l2,advtest,yes,"
                + "valid_visual_or_structural_error,wrong object\n",
                encoding="utf-8",
            )
            rows = load_review_rows(csv_path)
            summary = summarize_rows(rows)
            output_json = tmp_path / "summary.json"
            output_md = tmp_path / "summary.md"
            write_summary(output_json, output_md, summary)

            self.assertTrue(output_json.exists())
            self.assertTrue(output_md.exists())
            self.assertIn("Valid visual/structural", output_md.read_text())


if __name__ == "__main__":
    unittest.main()
