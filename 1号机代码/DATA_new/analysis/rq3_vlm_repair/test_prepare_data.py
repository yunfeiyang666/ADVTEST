import csv
import tempfile
import unittest
from pathlib import Path

from data_ops import (
    build_prompt,
    dedupe_and_validate_rows,
    frame_family_distribution,
    normalize_open_rows,
    select_common_frames,
    select_hard_rows,
    to_sft_record,
)
from prepare_data import (
    _required_visible_ids,
    build_split_manifest,
    scene_name,
    write_split_artifacts,
)


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


class DatasetOperationTests(unittest.TestCase):
    def test_frame_family_distribution_detects_budget_mismatch(self):
        rows = [
            {"scene_frame": "scene-0200_frame0", "family": "l0"},
            {"scene_frame": "scene-0201_frame0", "family": "l1"},
        ]
        changed = [dict(row) for row in rows]
        changed[1]["scene_frame"] = "scene-0202_frame0"

        self.assertNotEqual(
            frame_family_distribution(rows), frame_family_distribution(changed)
        )

    def test_visibility_requires_only_explicit_question_objects(self):
        row = {
            "answer": "car16",
            "source_object": "truck2",
            "target_object": "pedestrian4",
            "footprint_nodes": ["car16", "truck2", "pedestrian4", "car99"],
        }

        self.assertEqual(
            _required_visible_ids(row), {"car16", "truck2", "pedestrian4"}
        )

    def test_l2_visibility_includes_all_referenced_objects(self):
        row = {
            "answer": "car16",
            "family": "converge",
            "coverage_l0": ["car16", "truck2", "ego"],
        }

        self.assertEqual(_required_visible_ids(row), {"car16", "truck2"})

    def test_viewpoint_open_target_uses_precise_choice_answer(self):
        source = {
            "scene_frame": "scene-0200_frame0",
            "family": "viewpoint_transfer",
            "question": "Would car3 be left or right?",
            "answer": "left",
            "path_pattern": "car1|car2|car3",
            "source_question_id": "q1",
        }
        choice = {
            **source,
            "choice_answer_canonical_text": "back left",
        }

        normalized = normalize_open_rows([source], [choice])[0]

        self.assertEqual(normalized["answer"], "back left")
        self.assertIn("From car1, facing car2", normalized["question"])

    def test_common_frames_round_robin_scenes(self):
        rows = [
            {"scene_name": scene, "scene_frame": f"{scene}_frame{frame}"}
            for scene in ("scene-0200", "scene-0201", "scene-0202")
            for frame in range(3)
        ]
        selected = select_common_frames(rows, 6, seed=7)
        counts = {}
        for row in selected:
            counts[row["scene_name"]] = counts.get(row["scene_name"], 0) + 1
        self.assertEqual(sorted(counts.values()), [2, 2, 2])

    def test_sft_prompt_requires_exact_object_id(self):
        row = {
            "scene_frame": "scene-0200_frame0",
            "question": "Which car is behind car1?",
            "answer": "car2",
            "family": "converge",
            "source_question_id": "scene-0200_frame0:q1",
        }
        prompt, target = build_prompt(row, "open")
        self.assertIn("exact complete object ID", prompt)
        self.assertEqual(target, "car2")
        record = to_sft_record(row, "advtest_10k", "open", "abc")
        self.assertTrue(record["conversations"][0]["value"].startswith("<|image|>"))

    def test_hard_screen_uses_same_call_result_and_source(self):
        source = []
        raw = []
        quotas = {"l0": 1, "l1": 1}
        for index, family in enumerate(quotas):
            row = {
                "scene_frame": f"scene-020{index}_frame0",
                "question": f"question {index}",
                "answer": "yes",
                "family": family,
                "source_question_id": f"q{index}",
                "logic_verification": "IN_MEMORY_VERIFIED",
            }
            source.append(row)
            raw.append(
                {
                    "scene_frame": row["scene_frame"],
                    "source_question_id": row["source_question_id"],
                    "is_correct": False,
                    "error": None,
                }
            )
        selected, summary = select_hard_rows(raw, source, quotas, seed=3)
        self.assertEqual(len(selected), 2)
        self.assertEqual(summary["redistributed"], 0)

    def test_hard_screen_deduplicates_repeated_candidate_batches(self):
        source = [
            {
                "scene_frame": "scene-0200_frame0",
                "question": "Is car1 moving?",
                "answer": "yes",
                "family": "l0",
                "source_question_id": "q1",
                "logic_verification": "IN_MEMORY_VERIFIED",
            }
        ]
        raw = [
            {
                "scene_frame": "scene-0200_frame0",
                "source_question_id": "q1",
                "is_correct": False,
                "error": None,
            }
        ] * 2
        selected, summary = select_hard_rows(raw, source, {"l0": 1}, seed=3)
        self.assertEqual(len(selected), 1)
        self.assertEqual(summary["wrong_available_by_family"]["l0"], 1)

    def test_dedupe_reports_same_frame_same_text(self):
        rows = [
            {
                "scene_frame": "scene-0200_frame0",
                "question": "Is car1 moving?",
                "answer": "yes",
                "source_question_id": f"q{index}",
                "logic_verification": "OFFICIAL_DATASET",
            }
            for index in range(2)
        ]
        with self.assertRaisesRegex(ValueError, "duplicate_text"):
            dedupe_and_validate_rows(rows, 2)


if __name__ == "__main__":
    unittest.main()
