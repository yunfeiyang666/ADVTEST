import random
import re
from collections import Counter, defaultdict
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
