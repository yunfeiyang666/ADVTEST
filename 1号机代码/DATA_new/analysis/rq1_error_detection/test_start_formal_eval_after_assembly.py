import sys
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from start_formal_eval_after_assembly import is_seed_filter_process


class StopSeedFilterProcessTests(unittest.TestCase):
    def test_matches_only_seed_filter_recorded_or_eval_processes(self):
        run_id = "seed-filter-mplug-f308-q3503-v2"

        self.assertTrue(
            is_seed_filter_process(
                f"python run_recorded_experiment.py --run-id {run_id}",
                run_id,
            )
        )
        self.assertTrue(
            is_seed_filter_process(
                f"python run_suite_evaluation.py --output-dir runs/{run_id}/results",
                run_id,
            )
        )
        self.assertFalse(
            is_seed_filter_process(
                f"python start_formal_eval_after_assembly.py --seed-filter-run-id {run_id}",
                run_id,
            )
        )
        self.assertFalse(
            is_seed_filter_process(
                "python run_suite_evaluation.py --output-dir runs/other/results",
                run_id,
            )
        )


if __name__ == "__main__":
    unittest.main()
