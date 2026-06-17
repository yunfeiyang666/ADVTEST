import unittest

from pathlib import Path
from tempfile import TemporaryDirectory

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


def _write_artifact_fixture(base: Path) -> dict[str, Path]:
    paths = {
        "large_csv": base / "large.csv",
        "assisted_json": base / "assisted.json",
        "human_csv": base / "human.csv",
        "human_manifest_json": base / "human_manifest.json",
        "human_summary_json": base / "human_summary.json",
    }
    paths["large_csv"].write_text(
        "\n".join(
            [
                "bucket,manual_valid_failure,manual_issue_type,manual_notes",
                "advtest_only_l2,yes,valid_visual_or_structural_error,note",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    paths["assisted_json"].write_text(
        """{
  "total_rows": 1,
  "overall": {"label_counts": {"yes": 1}},
  "by_bucket": {
    "advtest_only_l2": {
      "sample_rows": 1,
      "label_counts": {"yes": 1}
    }
  }
}
""",
        encoding="utf-8",
    )
    paths["human_csv"].write_text(
        "\n".join(
            [
                "adjudication_id,bucket,manual_valid_failure,selection_reason,human_valid_failure,human_issue_type,human_agrees_with_assisted,human_notes",
                "row_1,advtest_only_l2,yes,test_reason,,,,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    paths["human_manifest_json"].write_text(
        """{
  "selected_counts": {
    "rows": 1,
    "by_bucket": {"advtest_only_l2": 1},
    "by_label": {"yes": 1},
    "by_bucket_label": {"advtest_only_l2 | yes": 1},
    "by_selection_reason": {"test_reason": 1}
  }
}
""",
        encoding="utf-8",
    )
    paths["human_summary_json"].write_text(
        """{
  "total_rows": 1,
  "reviewed_rows": 0,
  "pending_rows": 1,
  "status": "pending_human_review",
  "selected_distribution": {
    "by_bucket": {"advtest_only_l2": 1},
    "by_assisted_label": {"yes": 1},
    "by_selection_reason": {"test_reason": 1}
  }
}
""",
        encoding="utf-8",
    )
    return paths


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
        with TemporaryDirectory() as temp_dir:
            paths = _write_artifact_fixture(Path(temp_dir))

            payload = validate_artifacts(
                large_csv=paths["large_csv"],
                assisted_summary_json=paths["assisted_json"],
                human_pack_csv=paths["human_csv"],
                human_manifest_json=paths["human_manifest_json"],
                human_summary_json=paths["human_summary_json"],
            )

        self.assertEqual(payload["human_adjudication"]["pending_rows"], 1)

    def test_validate_artifacts_can_require_complete_human_review(self):
        with TemporaryDirectory() as temp_dir:
            paths = _write_artifact_fixture(Path(temp_dir))

            with self.assertRaisesRegex(ValueError, "pending_rows=1"):
                validate_artifacts(
                    large_csv=paths["large_csv"],
                    assisted_summary_json=paths["assisted_json"],
                    human_pack_csv=paths["human_csv"],
                    human_manifest_json=paths["human_manifest_json"],
                    human_summary_json=paths["human_summary_json"],
                    require_human_complete=True,
                )


if __name__ == "__main__":
    unittest.main()
