import unittest

from structural_sensitivity import (
    build_sensitivity_rows,
    recommend_frame_cap,
    summarize_random,
)


def make_run(cap, seed, *, advtest_l2, advtest_auc, random_l2):
    def metrics(micro_l2, auc):
        return {
            "micro_l0": 1.0,
            "macro_l0": 1.0,
            "micro_l1": 0.5,
            "macro_l1": 0.5,
            "micro_l2": micro_l2,
            "macro_l2": micro_l2,
            "unique_l2_per_question": micro_l2 * 10,
            "suite_size": 1000,
            "visited_frames": 20,
            "switch_reason_counts": {"frame_cap": 19},
            "auc_micro_l2": auc,
            "auc_macro_l2": auc,
        }

    return {
        "run_id": f"cap{cap}-seed{seed}",
        "seed": seed,
        "max_questions": cap,
        "summary": {
            "generation_budget": 1000,
            "frame_pool_size": 100,
            "methods": {
                "advtest": {"summary": metrics(advtest_l2, advtest_auc)},
                "random": {"summary": metrics(random_l2, random_l2 / 2)},
            },
        },
    }


class StructuralSensitivityTests(unittest.TestCase):
    def test_deterministic_methods_keep_only_canonical_seed(self):
        rows = build_sensitivity_rows(
            [
                make_run(50, 42, advtest_l2=0.10, advtest_auc=0.05, random_l2=0.08),
                make_run(50, 43, advtest_l2=0.10, advtest_auc=0.05, random_l2=0.09),
            ]
        )

        advtest_rows = [row for row in rows if row["method"] == "advtest"]
        random_rows = [row for row in rows if row["method"] == "random"]
        self.assertEqual(len(advtest_rows), 1)
        self.assertEqual(advtest_rows[0]["seed"], 42)
        self.assertEqual(len(random_rows), 2)

    def test_random_summary_reports_population_statistics(self):
        rows = build_sensitivity_rows(
            [
                make_run(50, 42, advtest_l2=0.10, advtest_auc=0.05, random_l2=0.08),
                make_run(50, 43, advtest_l2=0.10, advtest_auc=0.05, random_l2=0.10),
                make_run(50, 44, advtest_l2=0.10, advtest_auc=0.05, random_l2=0.12),
            ]
        )

        stats = summarize_random(rows)[0]

        self.assertEqual(stats["max_questions"], 50)
        self.assertEqual(stats["seed_count"], 3)
        self.assertAlmostEqual(stats["micro_l2_mean"], 0.10)
        self.assertAlmostEqual(stats["micro_l2_std"], (0.0008 / 3) ** 0.5)
        self.assertAlmostEqual(stats["micro_l2_min"], 0.08)
        self.assertAlmostEqual(stats["micro_l2_max"], 0.12)

    def test_recommends_cap50_when_advtest_gains_are_below_threshold(self):
        rows = build_sensitivity_rows(
            [
                make_run(50, 42, advtest_l2=0.100, advtest_auc=0.050, random_l2=0.08),
                make_run(100, 42, advtest_l2=0.104, advtest_auc=0.054, random_l2=0.09),
            ]
        )

        decision = recommend_frame_cap(rows)

        self.assertEqual(decision["recommended_max_questions"], 50)
        self.assertAlmostEqual(decision["micro_l2_delta"], 0.004)
        self.assertAlmostEqual(decision["auc_micro_l2_delta"], 0.004)

    def test_recommends_cap100_when_either_gain_reaches_threshold(self):
        rows = build_sensitivity_rows(
            [
                make_run(50, 42, advtest_l2=0.100, advtest_auc=0.050, random_l2=0.08),
                make_run(100, 42, advtest_l2=0.106, advtest_auc=0.054, random_l2=0.09),
            ]
        )

        decision = recommend_frame_cap(rows)

        self.assertEqual(decision["recommended_max_questions"], 100)


if __name__ == "__main__":
    unittest.main()
