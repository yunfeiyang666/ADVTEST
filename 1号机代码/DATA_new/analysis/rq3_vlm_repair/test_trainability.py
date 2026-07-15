import sys
import unittest
from pathlib import Path


MPLUG_ROOT = (
    Path(__file__).resolve().parents[4]
    / "baselines"
    / "mPLUG-Owl"
    / "mPLUG-Owl2"
)
sys.path.insert(0, str(MPLUG_ROOT))

from mplug_owl2.train.trainability import (  # noqa: E402
    audit_trainable_parameters,
    enforce_rq3_trainability,
)


class FakeParameter:
    def __init__(self, size: int = 1, requires_grad: bool = True):
        self.size = size
        self.requires_grad = requires_grad

    def numel(self) -> int:
        return self.size


class FakeModel:
    def __init__(self):
        self.parameters = {
            "base_model.model.layers.0.weight": FakeParameter(10),
            "base_model.model.layers.0.lora_A.default.weight": FakeParameter(2),
            "base_model.model.layers.0.lora_B.default.weight": FakeParameter(2),
            "base_model.model.visual_abstractor.proj.weight": FakeParameter(5),
            "base_model.model.vision_model.encoder.weight": FakeParameter(7),
        }

    def named_parameters(self):
        return iter(self.parameters.items())


class TrainabilityTests(unittest.TestCase):
    def test_enforces_lora_and_visual_abstractor_only(self):
        model = FakeModel()
        audit = enforce_rq3_trainability(model, tune_visual_abstractor=True)

        self.assertEqual(audit["tensor_counts"]["lora"], 2)
        self.assertEqual(audit["tensor_counts"]["visual_abstractor"], 1)
        self.assertEqual(audit["tensor_counts"]["vision_model"], 0)
        self.assertEqual(audit["tensor_counts"]["forbidden_base"], 0)
        self.assertFalse(model.parameters["base_model.model.layers.0.weight"].requires_grad)

    def test_can_disable_visual_abstractor(self):
        model = FakeModel()
        audit = enforce_rq3_trainability(model, tune_visual_abstractor=False)

        self.assertEqual(audit["tensor_counts"]["visual_abstractor"], 0)

    def test_audit_detects_unfrozen_base_parameter(self):
        model = FakeModel()
        audit = audit_trainable_parameters(model)

        self.assertEqual(audit["tensor_counts"]["forbidden_base"], 1)
        self.assertEqual(audit["tensor_counts"]["vision_model"], 1)


if __name__ == "__main__":
    unittest.main()
