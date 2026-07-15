import argparse
import tempfile
import unittest
from pathlib import Path

from analyze_results import (
    evaluate_success,
    exact_mcnemar_p,
    holm_adjust,
    merge_predictions,
    paired_metrics,
)


def rows(values):
    return [
        {
            "scene_frame": f"scene-0200_frame{index}",
            "source_question_id": f"q{index}",
            "family": "l0",
            "is_correct": value,
        }
        for index, value in enumerate(values)
    ]


class ResultAnalysisTests(unittest.TestCase):
    def test_merge_predictions_drops_mixed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.jsonl"
            source.write_text(
                "{\"scene_frame\":\"scene-0200_frame0\",\"source_question_id\":\"q0\",\"family\":\"l0\",\"is_correct\":true}\n"
                "{\"scene_frame\":\"scene-0200_frame1\",\"source_question_id\":\"q1\",\"family\":\"mixed\",\"is_correct\":false}\n",
                encoding="utf-8",
            )
            output = root / "merged.jsonl"
            manifest = root / "manifest.json"
            merge_predictions(
                argparse.Namespace(
                    input=[source], output=output, manifest=manifest
                )
            )
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 1)
    def test_success_requires_advtest_margin_and_three_seeds(self):
        methods = {}
        for method, reduction in (
            ("advtest_10k", 0.08),
            ("random_10k", 0.03),
            ("official_qa_10k", 0.04),
        ):
            methods[method] = {
                family: {
                    "error_rate_reduction_mean": reduction,
                    "seeds": [42, 43, 44],
                }
                for family in (
                    "l0",
                    "l1",
                    "converge",
                    "direction_chain",
                    "distance_chain",
                    "viewpoint_transfer",
                    "official_qa",
                )
            }
        result = evaluate_success({"methods": methods})
        self.assertTrue(result["passed"])

    def test_paired_metrics_separates_repairs_and_regressions(self):
        metrics = paired_metrics(
            rows([False, False, True, True]),
            rows([True, False, False, True]),
            bootstrap_samples=100,
            seed=1,
        )["l0"]

        self.assertEqual(metrics["repaired_questions"], 1)
        self.assertEqual(metrics["degraded_questions"], 1)
        self.assertEqual(metrics["error_rate_reduction"], 0.0)

    def test_formal_comparison_excludes_mixed(self):
        base = rows([False])
        model = rows([True])
        base[0]["family"] = "mixed"
        model[0]["family"] = "mixed"
        self.assertEqual(
            paired_metrics(base, model, bootstrap_samples=10, seed=1), {}
        )

    def test_exact_mcnemar_handles_no_disagreement(self):
        self.assertEqual(exact_mcnemar_p([True, False], [True, False]), 1.0)

    def test_holm_adjustment_is_monotonic(self):
        adjusted = holm_adjust([("a", 0.01), ("b", 0.03), ("c", 0.2)])

        self.assertLessEqual(adjusted["a"], adjusted["b"])
        self.assertLessEqual(adjusted["b"], adjusted["c"])


if __name__ == "__main__":
    unittest.main()
