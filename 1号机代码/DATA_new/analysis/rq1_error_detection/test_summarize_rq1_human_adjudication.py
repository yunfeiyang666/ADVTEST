import unittest

from summarize_rq1_human_adjudication import (
    build_summary,
    validate_and_split_rows,
)


def _adjudication_row(bucket, assisted_label, human_label="", index=0):
    return {
        "adjudication_id": f"row_{bucket}_{assisted_label}_{index}",
        "bucket": bucket,
        "selection_reason": "test",
        "manual_valid_failure": assisted_label,
        "manual_issue_type": "valid_visual_or_structural_error",
        "human_valid_failure": human_label,
        "human_issue_type": (
            "valid_visual_or_structural_error" if human_label else ""
        ),
        "human_agrees_with_assisted": (
            "yes" if human_label and human_label == assisted_label else "no" if human_label else ""
        ),
        "human_notes": "reviewed" if human_label else "",
    }


def _source_row(bucket, assisted_label, index):
    return {
        "bucket": bucket,
        "manual_valid_failure": assisted_label,
        "manual_issue_type": "valid_visual_or_structural_error",
        "audit_group": f"source_{bucket}_{assisted_label}_{index}",
    }


MANIFEST = {
    "universe": {
        "advtest_only_l2": 100,
        "random_only_l2": 50,
        "shared_l2": 40,
    }
}


class SummarizeRq1HumanAdjudicationTest(unittest.TestCase):
    def test_pending_rows_do_not_produce_calibrated_estimates(self):
        rows = [
            _adjudication_row("advtest_only_l2", "yes"),
            _adjudication_row("random_only_l2", "no"),
        ]

        summary = build_summary(
            adjudication_rows=rows,
            source_rows=[],
            universe_manifest=MANIFEST,
            min_cell_n=1,
        )

        self.assertEqual(summary["status"], "pending_human_review")
        self.assertEqual(summary["reviewed_rows"], 0)
        self.assertEqual(summary["pending_rows"], 2)
        self.assertEqual(
            summary["calibrated_estimates"]["status"],
            "not_available_until_human_rows_are_reviewed",
        )

    def test_completed_rows_calibrate_source_estimates(self):
        adjudication_rows = [
            _adjudication_row("advtest_only_l2", "yes", "yes", index=1),
            _adjudication_row("advtest_only_l2", "no", "no", index=2),
            _adjudication_row("random_only_l2", "yes", "no", index=3),
            _adjudication_row("random_only_l2", "no", "no", index=4),
            _adjudication_row("shared_l2_advtest", "yes", "yes", index=5),
            _adjudication_row("shared_l2_random", "yes", "yes", index=6),
        ]
        source_rows = (
            [_source_row("advtest_only_l2", "yes", i) for i in range(4)]
            + [_source_row("advtest_only_l2", "no", 4)]
            + [_source_row("random_only_l2", "yes", i) for i in range(5)]
            + [_source_row("random_only_l2", "no", 5)]
            + [_source_row("shared_l2_advtest", "yes", i) for i in range(2)]
            + [_source_row("shared_l2_random", "yes", i) for i in range(2)]
        )

        summary = build_summary(
            adjudication_rows=adjudication_rows,
            source_rows=source_rows,
            universe_manifest=MANIFEST,
            min_cell_n=1,
        )

        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["overall"]["agreement_yes"], 5)
        effect = summary["calibrated_estimates"]["exclusive_effect"]
        self.assertEqual(
            effect["advtest_only_calibrated_universe_valid_estimate"],
            80.0,
        )
        self.assertEqual(
            effect["random_only_calibrated_universe_valid_estimate"],
            0.0,
        )
        self.assertEqual(
            effect["advtest_minus_random_calibrated_universe_valid_estimate"],
            80.0,
        )

    def test_conflicting_agreement_field_fails_validation(self):
        row = _adjudication_row("advtest_only_l2", "yes", "yes")
        row["human_agrees_with_assisted"] = "no"

        with self.assertRaisesRegex(ValueError, "agreement field conflicts"):
            validate_and_split_rows([row])


if __name__ == "__main__":
    unittest.main()
