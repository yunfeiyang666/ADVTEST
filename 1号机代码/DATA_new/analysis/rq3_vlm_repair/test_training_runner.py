import tempfile
import unittest
from pathlib import Path

from run_training import (
    PROFILES,
    build_training_command,
    inspect_training_artifacts,
    matrix_image_root,
    matrix_run_specs,
)


class TrainingRunnerTests(unittest.TestCase):
    def test_matrix_contains_nine_main_runs_and_two_seed42_ablations(self):
        specs = matrix_run_specs(
            {
                "advtest_10k": Path("adv.json"),
                "random_10k": Path("random.json"),
                "official_qa_10k": Path("official.json"),
            },
            Path("hard.json"),
            Path("choice.json"),
        )
        self.assertEqual(len(specs), 11)
        self.assertEqual([seed for _, _, seed in specs[:9]], [42, 43, 44] * 3)
        self.assertEqual([seed for _, _, seed in specs[9:]], [42, 42])

    def test_hard_ablation_requires_its_own_explicit_image_root(self):
        with self.assertRaisesRegex(ValueError, "hard-image-root"):
            matrix_image_root(
                "advtest_hard_10k_open_s42", Path("main-images"), None
            )
        self.assertEqual(
            matrix_image_root(
                "advtest_hard_10k_open_s42",
                Path("main-images"),
                Path("hard-images"),
            ),
            Path("hard-images"),
        )
        self.assertEqual(
            matrix_image_root("advtest_10k_open_s42", Path("main-images"), None),
            Path("main-images"),
        )

    def test_smoke_command_uses_fixed_qlora_boundary(self):
        config = {
            "python_executable": "python",
            "model_path": "/model",
            "training_data": "/data.json",
            "image_root": "/images",
            "adapter_output": "/adapter",
            "seed": 42,
            "training": dict(PROFILES["smoke"]),
        }
        command = build_training_command(config)
        joined = " ".join(command)

        self.assertIn("--lora_r 8", joined)
        self.assertIn("--max_steps 20", joined)
        self.assertIn("--tune_visual_abstractor False", joined)
        self.assertIn("--freeze_vision_model True", joined)
        self.assertIn("--optim paged_adamw_8bit", joined)

    def test_artifact_check_requires_finite_decreasing_loss(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = Path(temp_dir) / "adapter"
            adapter.mkdir()
            (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")
            (adapter / "adapter_model.bin").write_bytes(b"adapter")
            (adapter / "trainer_state.json").write_text(
                '{"log_history": [{"loss": 2.0}, {"loss": 1.5}]}',
                encoding="utf-8",
            )

            result = inspect_training_artifacts({"adapter_output": str(adapter)})

            self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
