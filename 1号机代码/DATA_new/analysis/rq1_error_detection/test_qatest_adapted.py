import unittest

from qatest_adapted import (
    PortableMutationOperators,
    coarse_pos_sequence,
    grammar_gain,
    ngram_set,
    normalize_text,
    rouge1_scores,
    sentence_probability,
    transition_model,
)


class QATestLanguageMetricTests(unittest.TestCase):
    def test_rouge1_scores_use_token_multiset_overlap(self):
        scores = rouge1_scores(
            "How many cars are visible?",
            "How many trucks are visible?",
        )

        self.assertAlmostEqual(scores["precision"], 0.8)
        self.assertAlmostEqual(scores["recall"], 0.8)
        self.assertAlmostEqual(scores["f1"], 0.8)

    def test_normalize_text_collapses_case_and_whitespace(self):
        self.assertEqual(
            normalize_text("  How   Many Cars? "),
            "how many cars ?",
        )

    def test_ngram_set_contains_lengths_one_through_four(self):
        grams = ngram_set("one two three four five")

        self.assertIn(("one",), grams)
        self.assertIn(("one", "two", "three", "four"), grams)
        self.assertNotIn(("one", "two", "three", "four", "five"), grams)

    def test_coarse_pos_sequence_has_boundaries_and_question_mark(self):
        sequence = coarse_pos_sequence("How many cars are moving?")

        self.assertEqual(sequence[0], "START")
        self.assertEqual(sequence[-1], "END")
        self.assertIn("WH", sequence)
        self.assertIn("?", sequence)

    def test_unseen_transition_has_zero_sentence_probability(self):
        model = transition_model(
            [coarse_pos_sequence("How many cars are visible?")]
        )

        probability = sentence_probability(
            coarse_pos_sequence("Cars move quickly."),
            model,
        )

        self.assertEqual(probability, 0.0)

    def test_grammar_gain_counts_previously_unseen_ngrams(self):
        covered = ngram_set("How many cars are visible?")
        candidate = ngram_set("Where is the moving bus?")

        gain = grammar_gain(candidate, covered)

        self.assertGreater(gain, 0)
        self.assertEqual(grammar_gain(candidate, set()), len(candidate))


class PortableMutationOperatorTests(unittest.TestCase):
    def test_operators_are_deterministic_for_same_seed(self):
        operators = PortableMutationOperators()

        first = operators.apply(
            "keyboard_substitution",
            "How many cars are visible?",
            seed=17,
        )
        second = operators.apply(
            "keyboard_substitution",
            "How many cars are visible?",
            seed=17,
        )

        self.assertEqual(first, second)
        self.assertNotEqual(first, "How many cars are visible?")

    def test_all_declared_operators_require_no_external_configuration(self):
        operators = PortableMutationOperators()

        outputs = {
            name: operators.apply(
                name,
                "What is visible when the car moves?",
                seed=23,
            )
            for name in operators.names
        }

        self.assertEqual(len(outputs), 7)
        self.assertEqual(set(outputs), set(operators.names))
        self.assertTrue(all(isinstance(value, str) for value in outputs.values()))


if __name__ == "__main__":
    unittest.main()
