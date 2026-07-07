import unittest

from evaluator import check_correctness, check_question_correctness


class AnswerCorrectnessTests(unittest.TestCase):
    def test_empty_prediction_is_never_correct(self):
        self.assertFalse(check_correctness("", "car"))

    def test_no_does_not_match_inside_cannot(self):
        self.assertFalse(
            check_correctness("I cannot determine the answer.", "no")
        )

    def test_category_does_not_match_longer_word(self):
        self.assertFalse(check_correctness("There is a cart.", "car"))

    def test_category_matches_as_independent_word_in_sentence(self):
        self.assertTrue(check_correctness("I can see a car.", "car"))

    def test_boolean_matches_as_independent_word(self):
        self.assertTrue(check_correctness("No, there is not.", "no"))
        self.assertTrue(check_correctness("Yes, that is correct.", "yes"))

    def test_instance_id_requires_exact_token_boundary(self):
        self.assertTrue(check_correctness("The answer is car5.", "car5"))
        self.assertFalse(check_correctness("The answer is car50.", "car5"))

    def test_choice_question_accepts_correct_label(self):
        question = {
            "answer": "back left",
            "choices": [
                {"label": "A", "text": "back"},
                {"label": "B", "text": "back left"},
                {"label": "C", "text": "left"},
                {"label": "D", "text": "front left"},
            ],
            "choice_answer_label": "B",
            "choice_answer_text": "back left",
        }
        self.assertTrue(check_question_correctness("B. back left", question))
        self.assertFalse(check_question_correctness("A. back", question))

    def test_choice_question_accepts_correct_option_text(self):
        question = {
            "answer": "pedestrian",
            "choices": [
                {"label": "A", "text": "car"},
                {"label": "B", "text": "truck"},
                {"label": "C", "text": "pedestrian"},
                {"label": "D", "text": "barrier"},
            ],
            "choice_answer_label": "C",
            "choice_answer_text": "pedestrian",
        }
        self.assertTrue(
            check_question_correctness("The answer is pedestrian.", question)
        )


if __name__ == "__main__":
    unittest.main()
