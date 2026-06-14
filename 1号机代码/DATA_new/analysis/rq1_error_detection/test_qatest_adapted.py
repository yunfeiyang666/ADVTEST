import unittest

from qatest_adapted import (
    PortableMutationOperators,
    QATestGenerator,
    QATestSeed,
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


class StubOperators:
    def __init__(self, outputs):
        self.names = tuple(outputs)
        self.outputs = outputs

    def apply(self, name, text, *, seed):
        del seed
        output = self.outputs[name]
        return output(text) if callable(output) else output


def seed_record(source_id, question):
    return QATestSeed(
        source_question_id=source_id,
        source_sample_token="sample-a",
        scene_frame="scene-1_frame2",
        question=question,
        answer="yes",
        template_type="exist",
        num_hop=0,
    )


class QATestGeneratorTests(unittest.TestCase):
    def test_generation_is_deterministic_and_preserves_source_identity(self):
        seeds = [
            seed_record("sample-a:0", "What is visible near the car?"),
            seed_record("sample-a:1", "How many cars are visible?"),
        ]

        first = QATestGenerator(seed=17).generate(seeds, generation_budget=6)
        second = QATestGenerator(seed=17).generate(seeds, generation_budget=6)

        self.assertEqual(first.records, second.records)
        self.assertEqual(first.statistics, second.statistics)
        self.assertLessEqual(len(first.records), 6)
        self.assertTrue(
            all(
                record["source_question_id"] in {"sample-a:0", "sample-a:1"}
                for record in first.records
            )
        )

    def test_low_rouge_candidate_is_rejected(self):
        operators = StubOperators(
            {"unrelated": "Completely different tokens appear here."}
        )
        generator = QATestGenerator(
            seed=3,
            operators=operators,
            max_iterations=1,
        )

        result = generator.generate(
            [seed_record("sample-a:0", "How many cars are visible?")],
            generation_budget=1,
        )

        self.assertEqual(result.records, [])
        self.assertGreater(result.statistics["rejected_quality"], 0)

    def test_duplicate_candidate_is_emitted_only_once(self):
        operators = StubOperators(
            {"double": lambda text: text + "?"}
        )
        generator = QATestGenerator(
            seed=5,
            operators=operators,
            max_iterations=2,
        )

        result = generator.generate(
            [seed_record("sample-a:0", "How many cars are visible?")],
            generation_budget=5,
        )

        normalized = [normalize_text(record["question"]) for record in result.records]
        self.assertEqual(len(normalized), len(set(normalized)))
        self.assertGreater(result.statistics["rejected_duplicate"], 0)

    def test_feedback_candidates_return_to_seed_pool(self):
        operators = StubOperators(
            {
                "double": lambda text: text + "?",
                "case": lambda text: text[:1].lower() + text[1:],
            }
        )
        generator = QATestGenerator(
            seed=7,
            operators=operators,
            max_iterations=2,
        )

        result = generator.generate(
            [seed_record("sample-a:0", "How many cars are visible?")],
            generation_budget=2,
        )

        self.assertGreater(result.statistics["feedback_insertions"], 0)
        self.assertTrue(
            any(record["qatest_iteration"] == 1 for record in result.records)
        )

    def test_generation_budget_is_strict(self):
        result = QATestGenerator(seed=11).generate(
            [
                seed_record("sample-a:0", "What is visible near the car?"),
                seed_record("sample-a:1", "How many cars are visible?"),
                seed_record("sample-a:2", "Where is the moving bus?"),
            ],
            generation_budget=2,
        )

        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.statistics["accepted_questions"], 2)


if __name__ == "__main__":
    unittest.main()
