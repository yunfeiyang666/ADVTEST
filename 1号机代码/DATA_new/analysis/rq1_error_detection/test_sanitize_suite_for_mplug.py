import json
import tempfile
import unittest
from pathlib import Path

from sanitize_suite_for_mplug import sanitize_suite


class SanitizeSuiteForMPLUGTests(unittest.TestCase):
    def test_skips_same_frame_duplicates_and_fills_budget(self):
        rows = [
            {
                "scene_frame": "frame-a",
                "question": "How many cars are there?",
                "answer": "2",
                "vlm_call_cost": 1,
            },
            {
                "scene_frame": "frame-a",
                "question": "How many cars are there?",
                "answer": "2",
                "vlm_call_cost": 1,
            },
            {
                "scene_frame": "frame-a",
                "question": "What is in front?",
                "answer": "car",
                "vlm_call_cost": 1,
            },
            {
                "scene_frame": "frame-b",
                "question": "How many cars are there?",
                "answer": "1",
                "vlm_call_cost": 1,
            },
        ]

        result = sanitize_suite(rows, call_budget=3)

        self.assertEqual(result["calls"], 3)
        self.assertEqual(result["questions"], 3)
        self.assertEqual(result["skipped_duplicate_questions"], 1)
        self.assertEqual(result["input_records_consumed"], 4)
        self.assertEqual(
            [row["scene_frame"] for row in result["records"]],
            ["frame-a", "frame-a", "frame-b"],
        )

    def test_fails_when_unique_records_cannot_reach_budget(self):
        rows = [
            {
                "scene_frame": "frame-a",
                "question": "q",
                "answer": "yes",
                "vlm_call_cost": 1,
            },
            {
                "scene_frame": "frame-a",
                "question": "q",
                "answer": "yes",
                "vlm_call_cost": 1,
            },
        ]

        with self.assertRaisesRegex(ValueError, "only provides 1 unique calls"):
            sanitize_suite(rows, call_budget=2)

    def test_cli_writes_jsonl_and_manifest(self):
        rows = [
            {
                "scene_frame": f"frame-{index}",
                "question": f"q{index}",
                "answer": "yes",
                "vlm_call_cost": 1,
            }
            for index in range(2)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.jsonl"
            output = Path(tmp) / "output.jsonl"
            manifest = Path(tmp) / "manifest.json"
            source.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )

            from sanitize_suite_for_mplug import main

            main(
                [
                    "--source",
                    str(source),
                    "--output",
                    str(output),
                    "--manifest",
                    str(manifest),
                    "--call-budget",
                    "2",
                ]
            )

            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 2)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["questions"], 2)


if __name__ == "__main__":
    unittest.main()
