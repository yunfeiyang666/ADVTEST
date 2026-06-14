import json
import sys
import tempfile
import unittest
from pathlib import Path

from experiment_tracking import (
    build_manifest,
    run_recorded_experiment,
    sha256_file,
)


class ExperimentManifestTests(unittest.TestCase):
    def test_manifest_records_inputs_parameters_and_git_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            frame_cache = workspace / "frames.json"
            frame_cache.write_text('[{"scene_frame": "frame-a"}]', encoding="utf-8")

            manifest = build_manifest(
                run_id="structural-cap50-seed42",
                purpose="Measure structural coverage",
                command=["python", "fixed_budget_experiment.py"],
                workspace_root=workspace,
                input_files=[frame_cache],
                parameters={
                    "generation_budget": 1000,
                    "max_questions": 50,
                },
            )

            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["run_id"], "structural-cap50-seed42")
            self.assertEqual(manifest["status"], "prepared")
            self.assertEqual(
                manifest["parameters"]["generation_budget"],
                1000,
            )
            self.assertEqual(manifest["inputs"][0]["sha256"], sha256_file(frame_cache))
            self.assertEqual(len(manifest["inputs"][0]["sha256"]), 64)
            self.assertIn("git", manifest)
            self.assertNotIn("environment", manifest)


class RecordedExperimentTests(unittest.TestCase):
    def test_successful_command_records_logs_and_completion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_dir = workspace / "runs" / "success"
            manifest = build_manifest(
                run_id="success",
                purpose="Exercise the runner",
                command=[sys.executable, "-c", "print('ok')"],
                workspace_root=workspace,
                input_files=[],
                parameters={},
            )

            result = run_recorded_experiment(
                run_dir=run_dir,
                manifest=manifest,
                command=[sys.executable, "-c", "print('ok')"],
                cwd=workspace,
            )

            saved = json.loads(
                (run_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(saved["exit_code"], 0)
            self.assertGreaterEqual(saved["duration_seconds"], 0)
            self.assertEqual(
                (run_dir / "stdout.log").read_text(encoding="utf-8").strip(),
                "ok",
            )
            self.assertEqual(
                (run_dir / "stderr.log").read_text(encoding="utf-8"),
                "",
            )

    def test_failed_command_preserves_stderr_and_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_dir = workspace / "runs" / "failure"
            command = [
                sys.executable,
                "-c",
                "import sys; print('bad', file=sys.stderr); raise SystemExit(3)",
            ]
            manifest = build_manifest(
                run_id="failure",
                purpose="Exercise failure recording",
                command=command,
                workspace_root=workspace,
                input_files=[],
                parameters={},
            )

            result = run_recorded_experiment(
                run_dir=run_dir,
                manifest=manifest,
                command=command,
                cwd=workspace,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 3)
            self.assertIn(
                "bad",
                (run_dir / "stderr.log").read_text(encoding="utf-8"),
            )

    def test_existing_run_directory_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            run_dir = workspace / "existing"
            run_dir.mkdir()
            manifest = build_manifest(
                run_id="existing",
                purpose="Protect old evidence",
                command=[sys.executable, "-c", "print('ok')"],
                workspace_root=workspace,
                input_files=[],
                parameters={},
            )

            with self.assertRaises(FileExistsError):
                run_recorded_experiment(
                    run_dir=run_dir,
                    manifest=manifest,
                    command=[sys.executable, "-c", "print('ok')"],
                    cwd=workspace,
                )


if __name__ == "__main__":
    unittest.main()
