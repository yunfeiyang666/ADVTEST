import json
import tempfile
import unittest
from pathlib import Path

from mplug_preflight import PreflightConfig, audit_suite


def question(index: int, **overrides) -> dict:
    record = {
        "question": f"What is visible {index}?",
        "answer": "car",
        "experiment_layer": "cross_paradigm",
        "experiment_method": "official_qa",
        "question_source": "nuscenes_qa",
        "source_question_id": f"sample-a:{index}",
        "source_sample_token": "sample-a",
        "generation_adapter": "official_nuscenes_qa",
        "uses_coverage_feedback": False,
        "vlm_call_cost": 1,
        "global_budget_index": index,
        "scene_frame": f"scene-1_frame{index}",
    }
    record.update(overrides)
    return record


class MPLUGPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.outputs_root = self.root / "outputs"
        self.dataroot = self.root / "data"
        self.mosaic_dir = self.root / "mosaics"
        self.real_mosaic = self.root / "real-mosaic.jpg"
        self.real_mosaic.write_bytes(b"real image bytes")
        self.config = PreflightConfig(
            call_budget=2,
            outputs_root=self.outputs_root,
            dataroot=self.dataroot,
            mosaic_dir=self.mosaic_dir,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def write_suite(self, records) -> Path:
        path = self.root / "official_qa_suite.jsonl"
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        return path

    def add_scene_graphs(self, *records) -> None:
        for record in records:
            scene_frame = record["scene_frame"]
            path = (
                self.outputs_root
                / scene_frame
                / "offline"
                / "scene_graphs"
                / f"{scene_frame}_filtered_scene_graph.json"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")

    def test_valid_prefix_consumes_exact_budget_and_resolves_images(self):
        records = [question(0, answer=0), question(1), question(2)]
        self.add_scene_graphs(*records[:2])
        suite = self.write_suite(records)

        result = audit_suite(
            suite,
            self.config,
            image_resolver=lambda *args: self.real_mosaic,
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["evaluated_questions"], 2)
        self.assertEqual(result["evaluated_calls"], 2)
        self.assertEqual(result["unique_frames"], 2)
        self.assertEqual(result["failures"], [])

    def test_rejects_insufficient_call_capacity(self):
        record = question(0)
        self.add_scene_graphs(record)
        suite = self.write_suite([record])

        result = audit_suite(
            suite,
            self.config,
            image_resolver=lambda *args: self.real_mosaic,
        )

        self.assertFalse(result["passed"])
        self.assertIn("insufficient_call_capacity", result["failure_codes"])

    def test_rejects_invalid_content_provenance_and_duplicate_text(self):
        first = question(0, answer="")
        second = question(1, question="  WHAT IS VISIBLE 0?  ")
        del second["generation_adapter"]
        self.add_scene_graphs(first, second)
        suite = self.write_suite([first, second])

        result = audit_suite(
            suite,
            self.config,
            image_resolver=lambda *args: self.real_mosaic,
        )

        self.assertFalse(result["passed"])
        self.assertIn("missing_answer", result["failure_codes"])
        self.assertIn("missing_provenance", result["failure_codes"])
        self.assertIn("duplicate_normalized_question", result["failure_codes"])

    def test_rejects_official_record_without_source_id(self):
        first = question(0, source_question_id="")
        second = question(1)
        self.add_scene_graphs(first, second)
        suite = self.write_suite([first, second])

        result = audit_suite(
            suite,
            self.config,
            image_resolver=lambda *args: self.real_mosaic,
        )

        self.assertFalse(result["passed"])
        self.assertIn("missing_official_source_id", result["failure_codes"])

    def test_rejects_missing_scene_graph_before_image_resolution(self):
        records = [question(0), question(1)]
        suite = self.write_suite(records)
        resolver_calls = []

        result = audit_suite(
            suite,
            self.config,
            image_resolver=lambda *args: resolver_calls.append(args),
        )

        self.assertFalse(result["passed"])
        self.assertIn("missing_scene_graph", result["failure_codes"])
        self.assertEqual(resolver_calls, [])

    def test_rejects_unresolved_real_mosaic(self):
        records = [question(0), question(1)]
        self.add_scene_graphs(*records)
        suite = self.write_suite(records)

        result = audit_suite(
            suite,
            self.config,
            image_resolver=lambda *args: None,
        )

        self.assertFalse(result["passed"])
        self.assertIn("missing_real_mosaic", result["failure_codes"])


if __name__ == "__main__":
    unittest.main()
