import json
import tempfile
import unittest
from pathlib import Path

from run_minicpm_training import (
    check_model_shards,
    convert_for_llamafactory,
    training_config,
)


class MiniCPMTrainingTests(unittest.TestCase):
    def test_model_preflight_rejects_missing_weight_shards(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "model.safetensors.index.json").write_text(
                json.dumps({"weight_map": {"x": "model-00001-of-00002.safetensors"}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(FileNotFoundError, "model is incomplete"):
                check_model_shards(root)

    def test_model_preflight_rejects_truncated_weight_shards(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "model.safetensors.index.json").write_text(
                json.dumps(
                    {
                        "metadata": {"total_size": 10},
                        "weight_map": {"x": "model-00001-of-00001.safetensors"},
                    }
                ),
                encoding="utf-8",
            )
            (root / "model-00001-of-00001.safetensors").write_bytes(b"short")
            with self.assertRaisesRegex(ValueError, "size does not match"):
                check_model_shards(root)

    def test_converts_image_token_and_keeps_one_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "images" / "frame.jpg"
            image.parent.mkdir()
            image.write_bytes(b"image")
            records = [
                {
                    "id": "q1",
                    "image": "images/frame.jpg",
                    "conversations": [
                        {"from": "human", "value": "<|image|>What is this?"},
                        {"from": "gpt", "value": "car1"},
                    ],
                    "metadata": {"source_question_id": "source-q1"},
                }
            ]
            converted = convert_for_llamafactory(records, root, 1, 42)
            self.assertEqual(converted[0]["conversations"][0]["value"].count("<image>"), 1)
            self.assertEqual(converted[0]["images"], [str(image.resolve())])

    def test_formal_profile_uses_all_rows_and_three_epochs(self):
        config = training_config(
            Path("model"), Path("run"), "formal", "pilot_formal", 300
        )
        self.assertEqual(config["max_samples"], 300)
        self.assertEqual(config["num_train_epochs"], 3.0)
        self.assertEqual(config["max_steps"], -1)
        self.assertEqual(config["save_strategy"], "epoch")


if __name__ == "__main__":
    unittest.main()
