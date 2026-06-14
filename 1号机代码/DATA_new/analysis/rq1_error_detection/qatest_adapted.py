import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Sequence


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[?.!,]")


def tokenize(text: str) -> list:
    return TOKEN_PATTERN.findall(text.lower())


def normalize_text(text: str) -> str:
    return " ".join(tokenize(text))


def rouge1_scores(candidate: str, reference: str) -> dict:
    candidate_tokens = re.findall(r"[A-Za-z0-9]+", candidate.lower())
    reference_tokens = re.findall(r"[A-Za-z0-9]+", reference.lower())
    if not candidate_tokens or not reference_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    overlap = sum(
        (Counter(candidate_tokens) & Counter(reference_tokens)).values()
    )
    precision = overlap / len(candidate_tokens)
    recall = overlap / len(reference_tokens)
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def ngram_set(text: str) -> set:
    tokens = tokenize(text)
    grams = set()
    for width in range(1, 5):
        grams.update(
            tuple(tokens[index : index + width])
            for index in range(len(tokens) - width + 1)
        )
    return grams


def _coarse_pos(token: str) -> str:
    if token in {"?", ".", "!", ","}:
        return token
    if token in {
        "what",
        "which",
        "who",
        "whose",
        "where",
        "when",
        "why",
        "how",
    }:
        return "WH"
    if token.isdigit():
        return "NUM"
    if token in {"a", "an", "the", "this", "that", "these", "those"}:
        return "DET"
    if token in {
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "has",
        "have",
        "had",
        "can",
        "could",
        "will",
        "would",
    }:
        return "AUX"
    if token in {
        "in",
        "on",
        "at",
        "to",
        "from",
        "of",
        "with",
        "behind",
        "front",
        "near",
        "left",
        "right",
        "when",
        "if",
    }:
        return "ADP"
    if token.endswith("ly"):
        return "ADV"
    if token.endswith(("ing", "ed")):
        return "VERB"
    if token.endswith(("ous", "ive", "al", "able", "ible")):
        return "ADJ"
    return "NOUN"


def coarse_pos_sequence(text: str) -> list:
    return ["START", *(_coarse_pos(token) for token in tokenize(text)), "END"]


def transition_model(sequences: Iterable[Sequence[str]]) -> dict:
    counts = defaultdict(Counter)
    totals = Counter()
    for sequence in sequences:
        for left, right in zip(sequence, sequence[1:]):
            counts[left][right] += 1
            totals[left] += 1
    return {
        left: {
            right: count / totals[left]
            for right, count in destinations.items()
        }
        for left, destinations in counts.items()
    }


def sentence_probability(
    sequence: Sequence[str], model: Mapping[str, Mapping[str, float]]
) -> float:
    probability = 1.0
    for left, right in zip(sequence, sequence[1:]):
        probability *= float(model.get(left, {}).get(right, 0.0))
    return probability


def grammar_gain(candidate_grams: set, covered_grams: set) -> float:
    if not covered_grams:
        return float(len(candidate_grams))
    return len(candidate_grams - covered_grams) / len(covered_grams)


class PortableMutationOperators:
    names = (
        "keyboard_substitution",
        "ocr_substitution",
        "spelling_deletion",
        "synonym_replacement",
        "adverbial_preposition",
        "wh_contraction",
        "double_question_mark",
    )

    _keyboard_neighbors = {
        "a": "s",
        "e": "r",
        "i": "o",
        "o": "p",
        "u": "y",
        "s": "d",
        "r": "t",
        "n": "m",
        "l": "k",
        "t": "y",
        "c": "v",
        "m": "n",
    }
    _ocr_neighbors = {
        "o": "0",
        "i": "1",
        "l": "1",
        "s": "5",
        "b": "8",
        "g": "9",
    }
    _synonyms = {
        "car": "vehicle",
        "cars": "vehicles",
        "moving": "traveling",
        "visible": "seen",
        "near": "close",
        "behind": "back",
        "front": "ahead",
        "many": "numerous",
    }

    def apply(self, name: str, text: str, *, seed: int) -> str:
        if name not in self.names:
            raise ValueError(f"Unknown QATest operator: {name}")
        rng = random.Random(seed)
        return getattr(self, f"_{name}")(text, rng)

    @staticmethod
    def _word_matches(text: str) -> list:
        return list(re.finditer(r"[A-Za-z]{3,}", text))

    def _replace_character(self, text: str, rng: random.Random, replacements) -> str:
        candidates = [
            (index, char)
            for index, char in enumerate(text)
            if char.lower() in replacements
        ]
        if not candidates:
            return self._spelling_deletion(text, rng)
        index, char = rng.choice(candidates)
        replacement = replacements[char.lower()]
        if char.isupper():
            replacement = replacement.upper()
        return text[:index] + replacement + text[index + 1 :]

    def _keyboard_substitution(self, text: str, rng: random.Random) -> str:
        return self._replace_character(text, rng, self._keyboard_neighbors)

    def _ocr_substitution(self, text: str, rng: random.Random) -> str:
        return self._replace_character(text, rng, self._ocr_neighbors)

    def _spelling_deletion(self, text: str, rng: random.Random) -> str:
        words = [match for match in self._word_matches(text) if len(match.group()) >= 4]
        if not words:
            return self._double_question_mark(text, rng)
        match = rng.choice(words)
        word = match.group()
        position = rng.randrange(1, len(word) - 1)
        mutated = word[:position] + word[position + 1 :]
        return text[: match.start()] + mutated + text[match.end() :]

    def _synonym_replacement(self, text: str, rng: random.Random) -> str:
        matches = [
            match
            for match in self._word_matches(text)
            if match.group().lower() in self._synonyms
        ]
        if not matches:
            return self._wh_contraction(text, rng)
        match = rng.choice(matches)
        replacement = self._synonyms[match.group().lower()]
        if match.group()[0].isupper():
            replacement = replacement.capitalize()
        return text[: match.start()] + replacement + text[match.end() :]

    @staticmethod
    def _adverbial_preposition(text: str, rng: random.Random) -> str:
        del rng
        match = re.match(r"(.+?)\s+(if|when)\s+(.+?)(\?+)?$", text, re.I)
        if not match:
            return text
        main, conjunction, clause, punctuation = match.groups()
        punctuation = punctuation or "?"
        return (
            f"{conjunction.capitalize()} {clause}, "
            f"{main[:1].lower() + main[1:]}{punctuation}"
        )

    @staticmethod
    def _wh_contraction(text: str, rng: random.Random) -> str:
        del rng
        replacements = (
            ("What is ", "What's "),
            ("Who is ", "Who's "),
            ("Where is ", "Where's "),
            ("When is ", "When's "),
            ("How is ", "How's "),
        )
        for source, target in replacements:
            if text.startswith(source):
                return target + text[len(source) :]
        return text

    @staticmethod
    def _double_question_mark(text: str, rng: random.Random) -> str:
        del rng
        if text.endswith("?") and not text.endswith("??"):
            return text + "?"
        if not text.endswith("?"):
            return text + "??"
        return text


@dataclass(frozen=True)
class QATestSeed:
    source_question_id: str
    source_sample_token: str
    scene_frame: str
    question: str
    answer: str
    template_type: str = ""
    num_hop: int = 0
    root_question: str = ""
    iteration: int = 0
    generation_count: int = 0

    def __post_init__(self):
        if not self.root_question:
            object.__setattr__(self, "root_question", self.question)


@dataclass(frozen=True)
class QATestGenerationResult:
    records: list
    statistics: dict


class QATestCoverageModel:
    def __init__(self, questions: Iterable[str] = ()):
        self.sequences = []
        self.covered_grams = set()
        for question in questions:
            self.observe(question)

    def observe(self, question: str) -> None:
        self.sequences.append(coarse_pos_sequence(question))
        self.covered_grams.update(ngram_set(question))

    def score(self, question: str) -> tuple:
        model = transition_model(self.sequences)
        probability = sentence_probability(coarse_pos_sequence(question), model)
        gain = grammar_gain(ngram_set(question), self.covered_grams)
        return probability, gain


class QATestGenerator:
    def __init__(
        self,
        *,
        seed: int,
        operators=None,
        batch_size: int = 5,
        max_attempts: int = 10,
        max_iterations: int = 3000,
        rouge_threshold: float = 0.5,
    ):
        self.seed = int(seed)
        self.operators = operators or PortableMutationOperators()
        self.batch_size = int(batch_size)
        self.max_attempts = int(max_attempts)
        self.max_iterations = int(max_iterations)
        self.rouge_threshold = float(rouge_threshold)

    def _select_batch(
        self,
        pool: Sequence[QATestSeed],
        root_counts: Mapping[str, int],
        iteration: int,
    ) -> list:
        rng = random.Random(self.seed + iteration * 104729)
        ranked = []
        for index, item in enumerate(pool):
            weight = 1.0 / max(1, root_counts[item.source_question_id])
            key = rng.random() ** (1.0 / weight)
            ranked.append((key, index, item))
        ranked.sort(reverse=True, key=lambda entry: (entry[0], -entry[1]))
        return [entry[2] for entry in ranked[: self.batch_size]]

    def _operator_order(self, item: QATestSeed, iteration: int) -> list:
        names = list(self.operators.names)
        stable = sum(
            (index + 1) * ord(char)
            for index, char in enumerate(item.source_question_id)
        )
        random.Random(self.seed + iteration * 1009 + stable).shuffle(names)
        return names

    def generate(
        self,
        seeds: Sequence[QATestSeed],
        *,
        generation_budget: int,
    ) -> QATestGenerationResult:
        active_pool = list(seeds)
        coverage = QATestCoverageModel(item.question for item in seeds)
        root_counts = Counter(item.source_question_id for item in active_pool)
        emitted_normalized = {
            normalize_text(item.question) for item in active_pool
        }
        per_root_questions = defaultdict(set)
        for item in active_pool:
            per_root_questions[item.source_question_id].add(
                normalize_text(item.question)
            )

        records = []
        statistics = {
            "accepted_questions": 0,
            "attempted_candidates": 0,
            "rejected_quality": 0,
            "rejected_duplicate": 0,
            "feedback_insertions": 0,
            "iterations": 0,
            "operator_attempts": Counter(),
            "operator_acceptances": Counter(),
        }

        for iteration in range(self.max_iterations):
            if len(records) >= generation_budget or not active_pool:
                break
            statistics["iterations"] = iteration + 1
            batch = self._select_batch(active_pool, root_counts, iteration)
            accepted_this_iteration = []

            for item in batch:
                if len(records) >= generation_budget:
                    break
                order = self._operator_order(item, iteration)
                accepted = None
                for attempt in range(min(self.max_attempts, len(order))):
                    operator = order[attempt]
                    statistics["attempted_candidates"] += 1
                    statistics["operator_attempts"][operator] += 1
                    mutation_seed = (
                        self.seed
                        + iteration * 100003
                        + attempt * 997
                        + sum(ord(char) for char in item.question)
                    )
                    candidate = self.operators.apply(
                        operator,
                        item.question,
                        seed=mutation_seed,
                    )
                    normalized = normalize_text(candidate)
                    if (
                        normalized == normalize_text(item.question)
                        or normalized in emitted_normalized
                        or normalized
                        in per_root_questions[item.source_question_id]
                    ):
                        statistics["rejected_duplicate"] += 1
                        continue
                    rouge = rouge1_scores(candidate, item.question)
                    if rouge["f1"] <= self.rouge_threshold:
                        statistics["rejected_quality"] += 1
                        continue
                    probability, gain = coverage.score(candidate)
                    accepted = {
                        "question": candidate,
                        "answer": item.answer,
                        "template_type": item.template_type,
                        "num_hop": item.num_hop,
                        "source_question_id": item.source_question_id,
                        "source_sample_token": item.source_sample_token,
                        "scene_frame": item.scene_frame,
                        "original_question": item.root_question,
                        "qatest_parent_question": item.question,
                        "qatest_iteration": iteration,
                        "qatest_mutated": True,
                        "mutation_operator": operator,
                        "qatest_rouge1_f1": rouge["f1"],
                        "qatest_gram_gain": gain,
                        "qatest_sentence_probability": probability,
                    }
                    statistics["operator_acceptances"][operator] += 1
                    emitted_normalized.add(normalized)
                    per_root_questions[item.source_question_id].add(normalized)
                    coverage.observe(candidate)
                    records.append(accepted)
                    accepted_this_iteration.append((accepted, item))
                    break

            if not accepted_this_iteration:
                break

            min_probability = min(
                accepted_this_iteration,
                key=lambda pair: pair[0]["qatest_sentence_probability"],
            )
            max_gain = max(
                accepted_this_iteration,
                key=lambda pair: pair[0]["qatest_gram_gain"],
            )
            selected_feedback = []
            for pair in (min_probability, max_gain):
                if pair not in selected_feedback:
                    selected_feedback.append(pair)
            for accepted, parent in selected_feedback:
                feedback_seed = replace(
                    parent,
                    question=accepted["question"],
                    iteration=iteration + 1,
                    generation_count=parent.generation_count + 1,
                )
                active_pool.append(feedback_seed)
                root_counts[parent.source_question_id] += 1
                statistics["feedback_insertions"] += 1

        statistics["accepted_questions"] = len(records)
        statistics["operator_attempts"] = dict(
            sorted(statistics["operator_attempts"].items())
        )
        statistics["operator_acceptances"] = dict(
            sorted(statistics["operator_acceptances"].items())
        )
        return QATestGenerationResult(records=records, statistics=statistics)
