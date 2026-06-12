import sys
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from fixed_budget_experiment import (
    FrameCoverage,
    FrameInput,
    SwitchPolicy,
    build_method_stream,
    choose_switch_reason,
    compute_aggregate_metrics,
    run_method,
)


class SwitchPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = SwitchPolicy(
            min_questions=20,
            max_questions=100,
            plateau_window=10,
            gain_window=20,
            relative_gain_threshold=0.25,
        )

    def test_switches_on_full_l2_coverage(self):
        reason = choose_switch_reason(
            gains=[1] * 20,
            covered_l2=50,
            total_l2=50,
            candidates_exhausted=False,
            policy=self.policy,
        )
        self.assertEqual(reason, "full_coverage")

    def test_switches_after_ten_zero_gain_questions(self):
        reason = choose_switch_reason(
            gains=[1] * 20 + [0] * 10,
            covered_l2=20,
            total_l2=100,
            candidates_exhausted=False,
            policy=self.policy,
        )
        self.assertEqual(reason, "plateau")

    def test_switches_when_recent_gain_falls_below_initial_quarter(self):
        reason = choose_switch_reason(
            gains=[4] * 20 + [0] * 19 + [1],
            covered_l2=81,
            total_l2=200,
            candidates_exhausted=False,
            policy=self.policy,
        )
        self.assertEqual(reason, "relative_gain_drop")

    def test_does_not_switch_before_minimum_questions(self):
        reason = choose_switch_reason(
            gains=[0] * 10,
            covered_l2=0,
            total_l2=100,
            candidates_exhausted=False,
            policy=self.policy,
        )
        self.assertIsNone(reason)

    def test_switches_at_hard_cap(self):
        reason = choose_switch_reason(
            gains=[1] * 100,
            covered_l2=100,
            total_l2=1000,
            candidates_exhausted=False,
            policy=self.policy,
        )
        self.assertEqual(reason, "frame_cap")

    def test_hard_cap_takes_precedence_when_truncated_stream_also_ends(self):
        reason = choose_switch_reason(
            gains=[1] * 100,
            covered_l2=100,
            total_l2=1000,
            candidates_exhausted=True,
            policy=self.policy,
        )
        self.assertEqual(reason, "frame_cap")

    def test_switches_when_candidates_are_exhausted(self):
        reason = choose_switch_reason(
            gains=[1] * 7,
            covered_l2=7,
            total_l2=100,
            candidates_exhausted=True,
            policy=self.policy,
        )
        self.assertEqual(reason, "candidate_exhausted")


class CoverageAccountingTests(unittest.TestCase):
    def test_deduplicates_coverage_and_keeps_unvisited_frame_in_denominator(self):
        frames = {
            "frame-a": FrameCoverage(
                total_l0=2,
                total_l1=2,
                total_l2=4,
                covered_l0={"a"},
                covered_l1={"a|b"},
                covered_l2={"a|b|c", "a|b|d"},
            ),
            "frame-b": FrameCoverage(total_l0=2, total_l1=2, total_l2=6),
        }

        metrics = compute_aggregate_metrics(frames, question_count=2)

        self.assertAlmostEqual(metrics["micro_l2"], 0.2)
        self.assertAlmostEqual(metrics["macro_l2"], 0.25)
        self.assertAlmostEqual(metrics["unique_l2_per_question"], 1.0)

    def test_load_questions_stops_at_limit(self):
        import json
        import tempfile

        from fixed_budget_experiment import _load_questions

        with tempfile.TemporaryDirectory() as tmp:
            frame_dir = Path(tmp)
            qa_dir = frame_dir / "generation" / "qa"
            qa_dir.mkdir(parents=True)
            path = qa_dir / "frame-a_generated.jsonl"
            rows = [
                {"question": f"q{i}", "coverage_l2_items": [str(i)]}
                for i in range(5)
            ]
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )

            loaded = _load_questions(frame_dir, "frame-a", load_limit=2)

        self.assertEqual([row["question"] for row in loaded], ["q0", "q1"])





class FixedBudgetRunnerTests(unittest.TestCase):
    def setUp(self):
        self.questions = [
            {
                "question_id": str(index),
                "question": f"q{index}",
                "template_id": family,
                "footprint_nodes": nodes,
                "coverage_footprint": {
                    "l0": nodes,
                    "l1": l1_items,
                    "l2": l2_items,
                },
            }
            for index, (family, nodes, l1_items, l2_items) in enumerate(
                [
                    ("a", ["car1"], ["car1|left"], ["car1|left|ego"]),
                    ("a", ["car1"], ["car1|right"], ["car1|right|ego"]),
                    ("a", ["car1"], ["car1|front"], ["car1|front|ego"]),
                    ("b", ["bus1"], ["bus1|left"], ["bus1|left|ego"]),
                    ("c", ["bike1"], ["bike1|near"], ["bike1|near|ego"]),
                ],
                start=1,
            )
        ]

    def test_random_stream_is_deterministic_and_not_advtest_order(self):
        first = build_method_stream("random", self.questions, 5, seed=17)
        second = build_method_stream("random", self.questions, 5, seed=17)

        first_ids = [question["question_id"] for question in first]
        self.assertEqual(first_ids, [question["question_id"] for question in second])
        self.assertNotEqual(first_ids, ["1", "2", "3", "4", "5"])

    def test_advtest_recomputes_coverage_gain_after_each_question(self):
        questions = [
            {
                "question_id": "1",
                "question": "first",
                "coverage_footprint": {
                    "l0": ["car1"],
                    "l1": ["car1|left"],
                    "l2": ["car1|left|ego"],
                },
            },
            {
                "question_id": "2",
                "question": "duplicate",
                "coverage_footprint": {
                    "l0": ["car1"],
                    "l1": ["car1|left"],
                    "l2": ["car1|left|ego"],
                },
            },
            {
                "question_id": "3",
                "question": "new coverage",
                "coverage_footprint": {
                    "l0": ["bus1"],
                    "l1": ["bus1|right"],
                    "l2": ["bus1|right|ego"],
                },
            },
        ]

        stream = build_method_stream("advtest", questions, 2, seed=3)

        self.assertEqual(
            {question["question_id"] for question in stream},
            {"1", "3"},
        )

    def test_template_balanced_round_robins_families(self):
        stream = build_method_stream(
            "template_balanced", self.questions, 3, seed=4
        )

        self.assertEqual(
            {question["template_id"] for question in stream},
            {"a", "b", "c"},
        )

    def test_object_balanced_avoids_repeating_same_object_first(self):
        stream = build_method_stream("object_balanced", self.questions, 3, seed=9)

        selected_objects = [
            tuple(question["footprint_nodes"]) for question in stream
        ]
        self.assertEqual(len(set(selected_objects)), 3)

    def test_greedy_l0_maximizes_new_object_coverage(self):
        stream = build_method_stream("greedy_l0", self.questions, 3, seed=1)

        selected_objects = {
            node for question in stream for node in question["footprint_nodes"]
        }
        self.assertEqual(selected_objects, {"car1", "bus1", "bike1"})

    def test_greedy_l1_maximizes_new_relation_coverage(self):
        stream = build_method_stream("greedy_l1", self.questions, 4, seed=1)

        selected_l1 = {
            item
            for question in stream
            for item in question["coverage_footprint"]["l1"]
        }
        self.assertEqual(len(selected_l1), 4)

    def test_random_does_not_switch_on_coverage_plateau(self):
        repeated_questions = [
            {
                "question_id": str(index),
                "question": f"q{index}",
                "coverage_footprint": {
                    "l0": ["car1"],
                    "l1": ["car1|left"],
                    "l2": ["car1|left|ego"],
                },
            }
            for index in range(30)
        ]
        frame = FrameInput(
            scene_frame="frame-a",
            questions=repeated_questions,
            total_l0=10,
            total_l1=10,
            total_l2=10,
        )

        result = run_method(
            "random",
            [frame],
            budget=30,
            seed=42,
            policy=SwitchPolicy(
                min_questions=1,
                max_questions=30,
                plateau_window=3,
                gain_window=3,
            ),
        )

        self.assertEqual(result["summary"]["suite_size"], 30)
        self.assertEqual(result["frame_runs"][0]["switch_reason"], "global_budget")

    def test_custom_frame_cap_controls_number_of_questions_per_frame(self):
        questions = [
            {
                "question": f"q{i}",
                "coverage_l0_items": [f"obj{i}"],
                "coverage_l1_items": [f"obj{i}|attr"],
                "coverage_l2_items": [f"obj{i}|attr|rel"],
            }
            for i in range(80)
        ]
        frame = FrameInput(
            scene_frame="frame-a",
            questions=questions,
            total_l0=100,
            total_l1=100,
            total_l2=100,
        )

        result = run_method(
            "advtest",
            [frame],
            budget=1000,
            seed=42,
            policy=SwitchPolicy(
                min_questions=1,
                max_questions=50,
                plateau_window=60,
                gain_window=60,
            ),
        )

        self.assertEqual(result["summary"]["suite_size"], 50)
        self.assertEqual(result["frame_runs"][0]["questions"], 50)
        self.assertEqual(
            result["summary"]["switch_reason_counts"], {"frame_cap": 1}
        )

if __name__ == "__main__":
    unittest.main()
