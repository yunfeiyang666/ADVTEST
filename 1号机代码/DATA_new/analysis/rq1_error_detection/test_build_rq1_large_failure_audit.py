import json
import tempfile
import unittest
from pathlib import Path

from build_rq1_large_failure_audit import (
    auto_prefill,
    build_large_audit,
    stratified_scene_capped_keys,
    wilson_interval,
)


def _row(method, index, frame, family, l2_items, answer, predicted):
    return {
        "method": method,
        "question_index": index,
        "scene_frame": frame,
        "question_id": str(index),
        "family": family,
        "question": f"What car is described by row {index}?",
        "answer": answer,
        "predicted": predicted,
        "raw_model_output": predicted,
        "is_correct": False,
        "image_path": f"{frame}.jpg",
        "l2_items": l2_items,
    }


def _write_jsonl(path: Path, rows):
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


class BuildRq1LargeFailureAuditTest(unittest.TestCase):
    def test_auto_prefill_distinguishes_common_failure_types(self):
        self.assertEqual(
            auto_prefill(
                {
                    "answer": False,
                    "predicted": "Yes, they are in the same direction.",
                    "question": "Are they aligned?",
                    "l2_item": "a|b|c",
                }
            )["auto_issue_type"],
            "valid_visual_or_structural_error",
        )
        self.assertEqual(
            auto_prefill(
                {
                    "answer": "left",
                    "predicted": "It is on your right.",
                    "question": "left or right?",
                    "l2_item": "a|b|c",
                }
            )["auto_valid_failure"],
            "yes",
        )
        granularity = auto_prefill(
            {
                "answer": "car4",
                "predicted": "The car is in front of the bicycle.",
                "question": "What car is in front of the bicycle?",
                "l2_item": "bicycle2|car4|ego",
            }
        )
        self.assertEqual(
            granularity["auto_issue_type"], "answer_granularity_mismatch"
        )

    def test_stratified_scene_capped_keys_respects_scene_cap(self):
        index = {}
        keys = []
        for scene in ["s1", "s2", "s3"]:
            for i in range(5):
                key = f"{scene}::obj{i}|mid|ref"
                keys.append(key)
                index[key] = {"family": "converge"}
        selected = stratified_scene_capped_keys(
            keys,
            index,
            target=6,
            min_per_family=1,
            max_per_scene=2,
            seed=1,
        )
        counts = {}
        for key in selected:
            scene = key.split("::", 1)[0]
            counts[scene] = counts.get(scene, 0) + 1
        self.assertEqual(len(selected), 6)
        self.assertTrue(all(count <= 2 for count in counts.values()))

    def test_build_large_audit_outputs_expected_row_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            adv_path = tmp_path / "adv.jsonl"
            random_path = tmp_path / "random.jsonl"
            shared = [
                _row(
                    "advtest",
                    1,
                    "frame_a",
                    "converge",
                    ["shared|a|b"],
                    "car1",
                    "the car",
                )
            ]
            _write_jsonl(
                adv_path,
                shared
                + [
                    _row("advtest", 2, "frame_a", "direction", ["adv|a|b"], False, "Yes"),
                    _row("advtest", 3, "frame_b", "converge", ["adv|c|d"], "car2", "bus"),
                ],
            )
            _write_jsonl(
                random_path,
                [
                    _row(
                        "random",
                        1,
                        "frame_a",
                        "converge",
                        ["shared|a|b"],
                        "car1",
                        "the car",
                    ),
                    _row("random", 2, "frame_b", "distance", ["rnd|a|b"], "car4", "bus1"),
                    _row("random", 3, "frame_c", "converge", ["rnd|c|d"], "car3", "the car"),
                ],
            )

            payload = build_large_audit(
                adv_path,
                random_path,
                exclusive_samples_per_bucket=2,
                shared_pairs=1,
                min_per_family=1,
                max_per_scene=2,
                seed=7,
            )

            self.assertEqual(len(payload["review_rows"]), 6)
            self.assertEqual(
                payload["manifest"]["selected"]["advtest_only_l2"]["count"], 2
            )
            self.assertEqual(
                payload["manifest"]["selected"]["random_only_l2"]["count"], 2
            )
            self.assertEqual(
                payload["manifest"]["selected"]["shared_l2_pairs"]["count"], 1
            )
            self.assertEqual(payload["effective_ci"]["buckets"]["advtest_only_l2"]["sample_rows"], 2)

    def test_wilson_interval_is_bounded(self):
        interval = wilson_interval(8, 10)
        self.assertGreaterEqual(interval["lower"], 0)
        self.assertLessEqual(interval["upper"], 1)
        self.assertLess(interval["lower"], interval["upper"])


if __name__ == "__main__":
    unittest.main()
