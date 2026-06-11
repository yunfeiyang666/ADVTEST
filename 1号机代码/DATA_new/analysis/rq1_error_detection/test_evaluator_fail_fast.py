import sys
import tempfile
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

import evaluator


class _BrokenModel:
    def generate(self, *args, **kwargs):
        raise TypeError("incompatible transformers API")


class _Tokenizer:
    def __call__(self, *args, **kwargs):
        return {"input_ids": []}


class MPLUGFailFastTests(unittest.TestCase):
    def test_evaluate_raises_when_model_is_not_loaded(self):
        instance = evaluator.MPLUGEvaluator.__new__(evaluator.MPLUGEvaluator)
        instance.model = None

        with self.assertRaisesRegex(RuntimeError, "mPLUG-Owl2 model is not loaded"):
            instance.evaluate({"question": "What is visible?", "answer": "car"}, Path("missing.jpg"))

    def test_evaluate_raises_when_inference_fails(self):
        instance = evaluator.MPLUGEvaluator.__new__(evaluator.MPLUGEvaluator)
        instance.model = _BrokenModel()
        instance.tokenizer = _Tokenizer()
        instance.image_processor = object()
        instance.device = "cuda"

        with tempfile.NamedTemporaryFile(suffix=".jpg") as image_file:
            with self.assertRaisesRegex(RuntimeError, "mPLUG-Owl2 inference failed"):
                instance.evaluate(
                    {"question": "What is visible?", "answer": "car"},
                    Path(image_file.name),
                )


if __name__ == "__main__":
    unittest.main()
