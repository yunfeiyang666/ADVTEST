import unittest

from build_rq1_human_adjudication_pack import (
    BUCKETS,
    build_adjudication_pack,
    counter_by,
    validate_source_rows,
)


def _row(bucket, label, index, confidence="medium"):
    return {
        "audit_group": f"{bucket}_{label}_{index}",
        "bucket": bucket,
        "method": "advtest" if "advtest" in bucket else "random",
        "scene_frame": f"scene-{index % 3:04d}_frame{index}",
        "l2_key": f"{bucket}::obj{index}|mid|ref",
        "question": f"Question {index}?",
        "answer": "car1",
        "predicted": "bus1",
        "auto_confidence": confidence,
        "manual_valid_failure": label,
        "manual_issue_type": (
            "valid_visual_or_structural_error"
            if label == "yes"
            else "answer_granularity_mismatch"
        ),
        "manual_notes": "assisted note",
    }


def _source_rows():
    rows = []
    for bucket in BUCKETS:
        rows.append(_row(bucket, "uncertain", 0, confidence="low"))
        for index in range(1, 4):
            rows.append(_row(bucket, "no", index))
        for index in range(4, 10):
            rows.append(_row(bucket, "yes", index))
    return rows


class BuildRq1HumanAdjudicationPackTest(unittest.TestCase):
    def test_build_pack_includes_all_uncertain_and_balances_buckets(self):
        selected = build_adjudication_pack(
            _source_rows(),
            seed=7,
            target_total=12,
            max_no_per_bucket=1,
            max_per_scene=3,
        )

        self.assertEqual(len(selected), 12)
        self.assertEqual(
            counter_by(selected, ["bucket"]),
            {bucket: 3 for bucket in BUCKETS},
        )
        self.assertEqual(
            counter_by(selected, ["manual_valid_failure"]),
            {"no": 4, "uncertain": 4, "yes": 4},
        )
        self.assertEqual(
            counter_by(selected, ["selection_reason"]),
            {
                "all_uncertain": 4,
                "stratified_assisted_no": 4,
                "stratified_assisted_yes": 4,
            },
        )

    def test_build_pack_adds_blank_human_columns_and_is_deterministic(self):
        first = build_adjudication_pack(
            _source_rows(),
            seed=11,
            target_total=16,
            max_no_per_bucket=2,
            max_per_scene=4,
        )
        second = build_adjudication_pack(
            _source_rows(),
            seed=11,
            target_total=16,
            max_no_per_bucket=2,
            max_per_scene=4,
        )

        self.assertEqual(
            [row["audit_group"] for row in first],
            [row["audit_group"] for row in second],
        )
        self.assertEqual(first[0]["adjudication_id"], "rq1_adjudication_001")
        self.assertTrue(all(row["human_valid_failure"] == "" for row in first))
        self.assertTrue(all(row["human_notes"] == "" for row in first))

    def test_validate_source_rows_rejects_duplicate_keys(self):
        rows = _source_rows()
        rows.append(dict(rows[0]))

        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_source_rows(rows)


if __name__ == "__main__":
    unittest.main()
