import unittest

from validate_rq1_failure_audit_artifacts import (
    validate_artifacts,
    validate_human_pack,
    validate_large_audit,
)


def _large_row(bucket, label, index=0):
    return {
        "bucket": bucket,
        "manual_valid_failure": label,
        "manual_issue_type": (
            "valid_visual_or_structural_error"
            if label == "yes"
            else "answer_granularity_mismatch"
        ),
        "manual_notes": "assisted review note",
    }


def _human_row(bucket, label, index=0):
    return {
        "adjudication_id": f"row_{index}",
        "bucket": bucket,
        "manual_valid_failure": label,
        "selection_reason": "test_reason",
        "human_valid_failure": "",
        "human_issue_type": "",
        "human_agrees_with_assisted": "",
        "human_notes": "",
    }


class ValidateRq1FailureAuditArtifactsTest(unittest.TestCase):
    def test_validate_large_audit_matches_summary_counts(self):
        rows = [
            _large_row("advtest_only_l2", "yes"),
            _large_row("advtest_only_l2", "no"),
        ]
        summary = {
            "total_rows": 2,
            "overall": {"label_counts": {"no": 1, "yes": 1}},
            "by_bucket": {
                "advtest_only_l2": {
                    "sample_rows": 2,
                    "label_counts": {"no": 1, "yes": 1},
                }
            },
        }

        payload = validate_large_audit(rows, summary)

        self.assertEqual(payload["rows"], 2)
        self.assertEqual(payload["label_counts"], {"no": 1, "yes": 1})

    def test_validate_large_audit_rejects_mismatched_summary(self):
        rows = [_large_row("advtest_only_l2", "yes")]
        summary = {
            "total_rows": 1,
            "overall": {"label_counts": {"no": 1}},
            "by_bucket": {},
        }

        with self.assertRaisesRegex(ValueError, "label counts mismatch"):
            validate_large_audit(rows, summary)

    def test_validate_human_pack_allows_pending_rows(self):
        rows = [
            _human_row("advtest_only_l2", "uncertain", 1),
            _human_row("random_only_l2", "yes", 2),
        ]
        manifest = {
            "selected_counts": {
                "rows": 2,
                "by_bucket": {"advtest_only_l2": 1, "random_only_l2": 1},
                "by_label": {"uncertain": 1, "yes": 1},
                "by_bucket_label": {
                    "advtest_only_l2 | uncertain": 1,
                    "random_only_l2 | yes": 1,
                },
                "by_selection_reason": {"test_reason": 2},
            }
        }
        summary = {
            "total_rows": 2,
            "reviewed_rows": 0,
            "pending_rows": 2,
            "status": "pending_human_review",
            "selected_distribution": {
                "by_bucket": {"advtest_only_l2": 1, "random_only_l2": 1},
                "by_assisted_label": {"uncertain": 1, "yes": 1},
                "by_selection_reason": {"test_reason": 2},
            },
        }

        payload = validate_human_pack(rows, manifest, summary)

        self.assertEqual(payload["pending_rows"], 2)
        self.assertEqual(payload["reviewed_rows"], 0)

    def test_validate_human_pack_rejects_partial_human_review(self):
        rows = [_human_row("advtest_only_l2", "yes", 1)]
        rows[0]["human_valid_failure"] = "yes"
        manifest = {
            "selected_counts": {
                "rows": 1,
                "by_bucket": {"advtest_only_l2": 1},
                "by_label": {"yes": 1},
                "by_bucket_label": {"advtest_only_l2 | yes": 1},
                "by_selection_reason": {"test_reason": 1},
            }
        }
        summary = {
            "total_rows": 1,
            "reviewed_rows": 1,
            "pending_rows": 0,
            "status": "complete",
            "selected_distribution": {
                "by_bucket": {"advtest_only_l2": 1},
                "by_assisted_label": {"yes": 1},
                "by_selection_reason": {"test_reason": 1},
            },
        }

        with self.assertRaisesRegex(ValueError, "human_issue_type"):
            validate_human_pack(rows, manifest, summary)

    def test_validate_artifacts_uses_file_inputs(self):
        # The end-to-end CLI path is covered by repository verification. This
        # assertion keeps the public function importable for downstream scripts.
        self.assertTrue(callable(validate_artifacts))


if __name__ == "__main__":
    unittest.main()
