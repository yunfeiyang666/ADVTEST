import tempfile
import unittest
from pathlib import Path

from build_rq1_report_pack import build_report_pack, write_report_pack


def _summary(run_id: str, budget: int) -> dict:
    scale = budget // 100
    return {
        "run_id": run_id,
        "status": "completed",
        "exit_code": 0,
        "scoring": "token_boundary_v2_frame_qualified_l2",
        "actual_real_inference_records": budget * 2,
        "mock_fallback_records": 0,
        "results": [
            {
                "method": "advtest",
                "role": "proposed_method",
                "vlm_calls": budget,
                "wrong": 90 * scale,
                "failure_rate": 0.90,
                "unique_failures": 90 * scale,
                "unique_failures_per_100_calls": 90.0,
                "duplicate_failure_rate": 0.0,
                "failed_unique_l2": 200 * scale,
                "visited_frames": 20,
                "gt_granularity": "instance_or_relation",
            },
            {
                "method": "random",
                "role": "internal_ablation",
                "vlm_calls": budget,
                "wrong": 80 * scale,
                "failure_rate": 0.80,
                "unique_failures": 80 * scale,
                "unique_failures_per_100_calls": 80.0,
                "duplicate_failure_rate": 0.0,
                "failed_unique_l2": 100 * scale,
                "visited_frames": 20,
                "gt_granularity": "instance_or_relation",
            },
            {
                "method": "official_qa",
                "role": "neutral_reference",
                "vlm_calls": budget,
                "wrong": 50 * scale,
                "failure_rate": 0.50,
                "unique_failures": 50 * scale,
                "unique_failures_per_100_calls": 50.0,
                "duplicate_failure_rate": 0.0,
                "failed_unique_l2": 0,
                "visited_frames": 40,
                "gt_granularity": "category_level_official",
            },
        ],
        "warnings": ["preserve boundary note"],
    }


class BuildRq1ReportPackTest(unittest.TestCase):
    def test_build_report_pack_marks_only_internal_coverage_comparable(self):
        input_audit = {
            "methods": {
                "advtest": {
                    "coverage_comparable": True,
                    "covered_l2": 4500,
                    "unique_l2_per_question": 4.5,
                },
                "random": {
                    "coverage_comparable": True,
                    "covered_l2": 2800,
                    "unique_l2_per_question": 2.8,
                },
                "official_qa": {
                    "coverage_comparable": False,
                    "coverage_status": "not_available_by_design",
                },
            },
            "comparison_boundaries": ["official qa is reference only"],
        }
        random_variance = {
            "advtest": {
                "vlm_calls": 100,
                "unique_failures": 90,
                "failed_unique_l2": 200,
            },
            "random_runs": [
                {
                    "seed": 42,
                    "vlm_calls": 100,
                    "unique_failures": 80,
                    "failed_unique_l2": 100,
                }
            ],
            "advtest_vs_random": {"seed_count": 1},
        }

        report = build_report_pack(
            summaries={
                "call20": _summary("call20", 20),
                "call100": _summary("call100", 100),
                "call1000": _summary("call1000", 1000),
            },
            input_audit=input_audit,
            random_variance=random_variance,
        )

        main = {row["method"]: row for row in report["main_call1000_table"]}
        self.assertTrue(main["advtest"]["coverage_comparable"])
        self.assertEqual(main["advtest"]["covered_l2"], 4500)
        self.assertFalse(main["official_qa"]["coverage_comparable"])
        self.assertIsNone(main["official_qa"]["covered_l2"])

        gains = {
            row["call_budget"]: row for row in report["adv_vs_random_gains"]
        }
        self.assertEqual(gains[1000]["unique_failure_delta"], 100)
        self.assertEqual(gains[1000]["failed_unique_l2_delta"], 1000)
        self.assertEqual(gains[1000]["input_covered_l2_delta"], 1700)
        self.assertAlmostEqual(
            gains[1000]["input_covered_l2_relative_gain"], 1700 / 2800
        )
        self.assertEqual(len(report["claims_to_evidence"]), 4)

    def test_write_report_pack_outputs_expected_files(self):
        report = {
            "main_call1000_table": [],
            "scaling_table": [],
            "adv_vs_random_gains": [],
            "random_variance_table": [],
            "claims_to_evidence": [],
            "warnings": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_report_pack(output_dir, report)
            self.assertTrue((output_dir / "report_pack.json").exists())
            self.assertTrue((output_dir / "table_main_call1000.csv").exists())
            self.assertTrue((output_dir / "README.md").exists())
            self.assertTrue((output_dir / "paper_claims.md").exists())


if __name__ == "__main__":
    unittest.main()
