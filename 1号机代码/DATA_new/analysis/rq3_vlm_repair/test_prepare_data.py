import csv
import tempfile
import unittest
from pathlib import Path

from prepare_data import build_split_manifest, scene_name, write_split_artifacts


class SceneSplitTests(unittest.TestCase):
    def test_scene_name_rejects_malformed_value(self):
        self.assertEqual(scene_name("scene-0003_frame12"), "scene-0003")
        with self.assertRaisesRegex(ValueError, "Invalid scene_frame"):
            scene_name("scene-0003")

    def test_builds_disjoint_fixture_split(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs = root / "outputs"
            outputs.mkdir()
            stats = outputs / "all_frames_stats.csv"
            fields = [
                "scene_frame",
                "filtered_nodes",
                "total_l2_gaps",
                "generated_questions",
                "final_coverage_l2",
            ]
            frames = [
                "scene-0003_frame0",
                "scene-0096_frame0",
                "scene-0200_frame0",
            ]
            with stats.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for frame in frames:
                    writer.writerow(
                        {
                            "scene_frame": frame,
                            "filtered_nodes": 3,
                            "total_l2_gaps": 1,
                            "generated_questions": 2,
                            "final_coverage_l2": 1.0,
                        }
                    )
                    (outputs / frame).mkdir()

            manifest, split_frames = build_split_manifest(
                stats,
                outputs,
                None,
                enforce_expected_counts=False,
            )
            self.assertEqual(
                [row["scene_frame"] for row in split_frames["test"]],
                ["scene-0003_frame0"],
            )
            self.assertEqual(
                [row["scene_frame"] for row in split_frames["validation"]],
                ["scene-0096_frame0"],
            )
            self.assertEqual(
                [row["scene_frame"] for row in split_frames["train"]],
                ["scene-0200_frame0"],
            )
            output_dir = root / "artifacts"
            write_split_artifacts(output_dir, manifest, split_frames)
            self.assertTrue((output_dir / "split_manifest.json").exists())
            self.assertTrue((output_dir / "train_frames.json").exists())

    def test_rejects_duplicate_frame_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs = root / "outputs"
            outputs.mkdir()
            (outputs / "scene-0200_frame0").mkdir()
            stats = outputs / "all_frames_stats.csv"
            stats.write_text(
                "scene_frame,filtered_nodes,total_l2_gaps,generated_questions,final_coverage_l2\n"
                "scene-0200_frame0,3,1,2,1\n"
                "scene-0200_frame0,3,1,2,1\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Duplicate frame"):
                build_split_manifest(stats, outputs, None, enforce_expected_counts=False)


if __name__ == "__main__":
    unittest.main()
