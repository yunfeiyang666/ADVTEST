import json
import tempfile
import unittest
from pathlib import Path

from build_rq1_failure_audit import (
    build_failure_audit,
    flatten_manual_review_rows,
    write_failure_audit,
)


def _row(method, index, frame, family, l2_items, *, correct=False):
    return {
        "method": method,
        "question_index": index,
        "scene_frame": frame,
        "question_id": str(index),
        "family": family,
        "question": f"question {index}",
        "answer": "car1",
        "predicted": "bus",
        "raw_model_output": "bus",
        "is_correct": correct,
        "image_path": f"{frame}.jpg",
        "l2_items": l2_items,
    }


def _write_jsonl(path: Path, rows):
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


class BuildRq1FailureAuditTest(unittest.TestCase):
    def test_build_failure_audit_counts_signature_and_l2_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            adv_path = tmp_path / "adv.jsonl"
            random_path = tmp_path / "random.jsonl"
            _write_jsonl(
                adv_path,
                [
                    _row("advtest", 1, "frame_a", "converge", ["a|b|c"]),
                    _row("advtest", 2, "frame_a", "converge", ["x|y|z"]),
                    _row("advtest", 3, "frame_b", "distance", ["m|n|o"]),
                    _row("advtest", 4, "frame_b", "distance", ["skip"], correct=True),
                ],
            )
            _write_jsonl(
                random_path,
                [
                    _row("random", 1, "frame_a", "converge", ["a|b|c"]),
                    _row("random", 2, "frame_c", "direction", ["u|v|w"]),
                ],
            )

            audit = build_failure_audit(
                adv_path, random_path, sample_per_bucket=10
            )

            self.assertEqual(audit["summary"]["advtest"]["failed_questions"], 3)
            self.assertEqual(audit["summary"]["random"]["failed_questions"], 2)
            self.assertEqual(
                audit["summary"]["failed_l2_overlap"],
                {"advtest_only": 2, "random_only": 1, "shared": 1},
            )
            self.assertEqual(
                audit["summary"]["signature_overlap"],
                {"advtest_only": 2, "random_only": 1, "shared": 1},
            )
            self.assertEqual(len(audit["samples"]["advtest_only_l2"]), 2)
            self.assertEqual(len(audit["samples"]["random_only_l2"]), 1)
            self.assertEqual(len(audit["samples"]["shared_l2_pairs"]), 1)

            review_rows = flatten_manual_review_rows(audit)
            self.assertEqual(len(review_rows), 5)
            self.assertEqual(
                {row["bucket"] for row in review_rows},
                {
                    "advtest_only_l2",
                    "random_only_l2",
                    "shared_l2_advtest",
                    "shared_l2_random",
                },
            )

    def test_write_failure_audit_outputs_expected_files(self):
        audit = {
            "summary": {
                "advtest": {
                    "unique_failure_signatures": 1,
                    "failed_unique_l2": 1,
                },
                "random": {
                    "unique_failure_signatures": 1,
                    "failed_unique_l2": 1,
                },
                "signature_overlap": {
                    "advtest_only": 0,
                    "random_only": 0,
                    "shared": 1,
                },
                "failed_l2_overlap": {
                    "advtest_only": 0,
                    "random_only": 0,
                    "shared": 1,
                },
            },
            "samples": {
                "advtest_only_l2": [],
                "random_only_l2": [],
                "shared_l2_pairs": [],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_failure_audit(output_dir, audit)
            self.assertTrue((output_dir / "failure_audit.json").exists())
            self.assertTrue((output_dir / "failure_overlap_summary.csv").exists())
            self.assertTrue((output_dir / "manual_review_samples.csv").exists())
            self.assertTrue((output_dir / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
