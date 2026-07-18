import tempfile
import unittest
from pathlib import Path

from gap_pipeline.random_full_coverage import (
    CoverageAccumulator,
    StaticRandomSelector,
    VerifiedPlanCache,
    load_checkpoint,
    run_until_full,
    write_checkpoint,
)


PLAN_BANK = {
    "a|b|c": ["p0", "p1"],
    "d|e|f": ["p2"],
    "g|h|i": ["p3", "p4", "p5"],
}


def make_accumulator():
    return CoverageAccumulator.create(
        universe={"l0": ["a", "b", "c"], "l1": ["a|b"], "l2": PLAN_BANK},
        initial_coverage={"l0": [], "l1": [], "l2": []},
    )


class StaticRandomSelectorTests(unittest.TestCase):
    def test_verified_cache_is_selection_independent_and_round_trips(self):
        cache = VerifiedPlanCache(
            {
                "p0": {"question": "q0", "coverage_footprint": {"l2": ["a|b|c"]}},
                "p1": {"question": "q1", "coverage_footprint": {"l2": ["a|b|c"]}},
                "p2": {"question": "q2", "coverage_footprint": {"l2": ["d|e|f"]}},
                "p3": {"question": "q3", "coverage_footprint": {"l2": ["g|h|i"]}},
                "p4": {"question": "q4", "coverage_footprint": {"l2": ["g|h|i"]}},
                "p5": {"question": "q5", "coverage_footprint": {"l2": ["g|h|i"]}},
            }
        )
        cache.validate_plan_ids(plan_id for plans in PLAN_BANK.values() for plan_id in plans)
        selector = StaticRandomSelector(PLAN_BANK, seed=42)
        first = selector.draw()
        self.assertIn(first.plan_id, cache.plan_ids)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            cache.write(path, candidate_fingerprint=selector.fingerprint)
            loaded = VerifiedPlanCache.load(path, candidate_fingerprint=selector.fingerprint)
            self.assertEqual(loaded.fingerprint, cache.fingerprint)
            self.assertEqual(loaded.get(first.plan_id), cache.get(first.plan_id))

    def test_cached_and_direct_realization_have_identical_coverage_trace(self):
        records = {
            plan_id: {
                "question": f"question-{plan_id}",
                "coverage_footprint": {"l2": [gap_id]},
            }
            for gap_id, plan_ids in PLAN_BANK.items()
            for plan_id in plan_ids
        }
        cache = VerifiedPlanCache(records)
        direct_selector = StaticRandomSelector(PLAN_BANK, seed=43)
        cached_selector = StaticRandomSelector(PLAN_BANK, seed=43)
        direct_accumulator = make_accumulator()
        cached_accumulator = make_accumulator()

        for _ in range(60):
            direct_draw = direct_selector.draw()
            cached_draw = cached_selector.draw()
            self.assertEqual(direct_draw, cached_draw)
            direct_record = records[direct_draw.plan_id]
            cached_record = cache.get(cached_draw.plan_id)
            direct_accumulator.observe(
                direct_draw, direct_record["coverage_footprint"], question_text=direct_record["question"]
            )
            cached_accumulator.observe(
                cached_draw, cached_record["coverage_footprint"], question_text=cached_record["question"]
            )
            self.assertEqual(direct_accumulator.state_dict(), cached_accumulator.state_dict())

    def test_rejects_initial_gap_without_plan(self):
        with self.assertRaisesRegex(ValueError, "no verified plan"):
            StaticRandomSelector({"gap": []}, seed=42)

    def test_selection_is_independent_of_coverage_state(self):
        first = StaticRandomSelector(PLAN_BANK, seed=42)
        second = StaticRandomSelector(PLAN_BANK, seed=42)
        accumulator = make_accumulator()

        first_sequence = []
        second_sequence = []
        for index in range(50):
            draw_a = first.draw()
            draw_b = second.draw()
            first_sequence.append((draw_a.gap_id, draw_a.plan_id))
            second_sequence.append((draw_b.gap_id, draw_b.plan_id))
            if index % 2 == 0:
                accumulator.observe(
                    draw_a,
                    {"l0": ["a"], "l1": ["a|b"], "l2": [draw_a.gap_id]},
                )

        self.assertEqual(first_sequence, second_sequence)

    def test_sampling_with_replacement_keeps_duplicates(self):
        selector = StaticRandomSelector({"only-gap": ["only-plan"]}, seed=7)
        draws = [selector.draw() for _ in range(4)]
        self.assertEqual([draw.gap_id for draw in draws], ["only-gap"] * 4)
        self.assertEqual([draw.plan_id for draw in draws], ["only-plan"] * 4)

    def test_checkpoint_resume_matches_uninterrupted_sequence(self):
        uninterrupted = StaticRandomSelector(PLAN_BANK, seed=44)
        expected = [uninterrupted.draw() for _ in range(80)]

        selector = StaticRandomSelector(PLAN_BANK, seed=44)
        accumulator = make_accumulator()
        prefix = []
        for _ in range(31):
            draw = selector.draw()
            prefix.append(draw)
            accumulator.observe(draw, {"l2": [draw.gap_id]})

        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp) / "checkpoint.json"
            write_checkpoint(
                checkpoint, selector=selector, accumulator=accumulator
            )
            resumed_selector = StaticRandomSelector(PLAN_BANK, seed=44)
            resumed_accumulator = make_accumulator()
            load_checkpoint(
                checkpoint,
                selector=resumed_selector,
                accumulator=resumed_accumulator,
            )
            suffix = [resumed_selector.draw() for _ in range(49)]

        self.assertEqual(prefix + suffix, expected)

    def test_run_stops_only_after_full_l2_coverage(self):
        selector = StaticRandomSelector(PLAN_BANK, seed=3)
        accumulator = make_accumulator()

        def realize(draw, draw_index):
            return {
                "question": f"question-{draw.plan_id}",
                "coverage_footprint": {"l2": [draw.gap_id]},
            }

        summary = run_until_full(
            selector=selector,
            accumulator=accumulator,
            realize=realize,
            max_draws=1000,
        )
        self.assertTrue(summary["full_l2"])
        self.assertEqual(summary["coverage"]["l2"]["rate"], 1.0)
        self.assertEqual(summary["milestones"]["l2"]["100"], summary["draws"])


if __name__ == "__main__":
    unittest.main()
