import random
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from build_choice_suites import (
    DIRECTION_OPTIONS,
    STATUS_OPTIONS,
    TYPE_OPTIONS,
    answer_pool_key,
    choose_options,
    collect_answer_pools,
    viewpoint_choice_question,
    viewpoint_path_pattern,
)


class ChoiceSuiteConstructionTests(unittest.TestCase):
    def test_count_direction_family_uses_numeric_options(self):
        row = {
            "family": "l1_count_direction_type",
            "question": "How many stopped cars are to the back of car14?",
            "answer": "4",
        }
        self.assertEqual(answer_pool_key(row), "count")

        pools = collect_answer_pools([row])
        options = choose_options(row, pools, random.Random(1), Path(tempfile.gettempdir()))

        self.assertIn("4", options)
        self.assertTrue(all(option.isdigit() for option in options))
        self.assertFalse(set(options) & set(DIRECTION_OPTIONS))

    def test_type_answer_in_direction_family_uses_type_options(self):
        row = {
            "family": "l1_object_at_direction",
            "question": "There is an object to the front of barrier6; what is it?",
            "answer": "barrier",
        }
        self.assertEqual(answer_pool_key(row), "type")

        pools = collect_answer_pools([row])
        options = choose_options(row, pools, random.Random(1), Path(tempfile.gettempdir()))

        self.assertIn("barrier", options)
        self.assertTrue(set(options).issubset(set(TYPE_OPTIONS)))
        self.assertFalse(set(options) & set(DIRECTION_OPTIONS))

    def test_viewpoint_transfer_can_use_l2_item_as_path_pattern(self):
        row = {
            "family": "viewpoint_transfer",
            "question": "Standing at car1 and looking toward ego, is truck1 to the left or the right?",
            "answer": "left",
            "l2_items": ["car1|ego|truck1"],
        }

        self.assertEqual(viewpoint_path_pattern(row), "car1|ego|truck1")
        self.assertEqual(
            viewpoint_choice_question(row),
            "From car1, facing ego, where is truck1 relative to you?",
        )

    def test_status_options_do_not_use_global_fillers(self):
        rows = [
            {
                "family": "l0_object_status",
                "question": "What is the movement status of barrier1?",
                "answer": "stopped",
            },
            {
                "family": "l0_object_type",
                "question": "What type of object is barrier1?",
                "answer": "barrier",
            },
            {
                "family": "l0_count_type",
                "question": "How many cars are there?",
                "answer": "3",
            },
        ]
        pools = collect_answer_pools(rows)
        options = choose_options(rows[0], pools, random.Random(1), Path(tempfile.gettempdir()))

        self.assertEqual(set(options), set(STATUS_OPTIONS))


if __name__ == "__main__":
    unittest.main()
