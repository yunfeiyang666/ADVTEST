import unittest

from summarize_mplug_random_variance import summarize_results


class SummarizeMPLUGRandomVarianceTests(unittest.TestCase):
    def test_summarizes_random_seeds_against_fixed_advtest(self):
        advtest = {
            "vlm_calls": 100,
            "wrong": 92,
            "unique_failures": 92,
            "failed_unique_l2": 236,
        }
        random_results = [
            {
                "seed": 42,
                "vlm_calls": 100,
                "wrong": 86,
                "unique_failures": 86,
                "failed_unique_l2": 169,
            },
            {
                "seed": 43,
                "vlm_calls": 100,
                "wrong": 88,
                "unique_failures": 88,
                "failed_unique_l2": 171,
            },
            {
                "seed": 44,
                "vlm_calls": 100,
                "wrong": 90,
                "unique_failures": 90,
                "failed_unique_l2": 175,
            },
        ]

        summary = summarize_results(advtest, random_results)

        self.assertEqual(summary["random"]["seed_count"], 3)
        self.assertEqual(summary["random"]["seeds"], [42, 43, 44])
        self.assertEqual(summary["random"]["unique_failures_mean"], 88.0)
        self.assertAlmostEqual(
            summary["random"]["unique_failures_population_std"],
            1.632993161855452,
        )
        self.assertEqual(
            summary["advtest_vs_random"]["absolute_gain_over_mean"],
            4.0,
        )
        self.assertAlmostEqual(
            summary["advtest_vs_random"]["relative_gain_over_mean"],
            4 / 88,
        )
        self.assertEqual(
            summary["advtest_vs_random"]["seeds_advtest_exceeds"],
            3,
        )
        self.assertAlmostEqual(
            summary["random"]["failed_unique_l2_mean"],
            515 / 3,
        )
        self.assertAlmostEqual(
            summary["advtest_vs_random"]["failed_unique_l2_gain_over_mean"],
            236 - 515 / 3,
        )

    def test_rejects_mixed_call_budgets(self):
        advtest = {
            "vlm_calls": 100,
            "wrong": 92,
            "unique_failures": 92,
            "failed_unique_l2": 236,
        }
        random_results = [
            {
                "seed": 42,
                "vlm_calls": 20,
                "wrong": 18,
                "unique_failures": 18,
                "failed_unique_l2": 40,
            }
        ]

        with self.assertRaisesRegex(ValueError, "same VLM call budget"):
            summarize_results(advtest, random_results)


if __name__ == "__main__":
    unittest.main()
