import unittest

from prepare_human_review import stratified_sample


class HumanReviewTests(unittest.TestCase):
    def test_sample_cycles_across_families_without_filling_labels(self):
        rows = [
            {
                "scene_frame": f"scene-0200_frame{index}",
                "source_question_id": f"q{index}",
                "family": family,
            }
            for index, family in enumerate(("l0", "l0", "l1", "l1"))
        ]
        selected = stratified_sample(rows, 2, seed=5)
        self.assertEqual({row["family"] for row in selected}, {"l0", "l1"})


if __name__ == "__main__":
    unittest.main()
