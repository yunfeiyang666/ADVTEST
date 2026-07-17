import json
import tempfile
import unittest
from pathlib import Path

import run_random_full_coverage_experiment as experiment


class RandomFullCoverageExperimentTests(unittest.TestCase):
    def test_split_scene_frame(self):
        self.assertEqual(
            experiment.split_scene_frame("scene-0003_frame17"),
            ("scene-0003", "17"),
        )

    def test_is_complete_requires_exact_full_l2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            path.write_text(
                json.dumps(
                    {"full_l2": True, "coverage": {"l2": {"rate": 0.99}}}
                ),
                encoding="utf-8",
            )
            self.assertFalse(experiment.is_complete(path))
            path.write_text(
                json.dumps(
                    {"full_l2": True, "coverage": {"l2": {"rate": 1.0}}}
                ),
                encoding="utf-8",
            )
            self.assertTrue(experiment.is_complete(path))

    def test_summary_paths_are_isolated_by_formal_run_id(self):
        root = Path("outputs")
        path = experiment.random_summary_path(root, "scene-0003_frame17", 42, "formal-a")
        self.assertEqual(
            path,
            root / "scene-0003_frame17" / "random_full" / "formal-a" / "seed_42" / "summary.json",
        )

    def test_size_groups(self):
        self.assertEqual(experiment.size_group(3), "S(3-15)")
        self.assertEqual(experiment.size_group(16), "M(16-30)")
        self.assertEqual(experiment.size_group(31), "L(>=31)")


if __name__ == "__main__":
    unittest.main()
