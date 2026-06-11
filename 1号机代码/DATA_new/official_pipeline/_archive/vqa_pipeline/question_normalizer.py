"""Question normalization module (clean, non-destructive version).

Design goals:
- Do NOT change the semantic target set of the question.
- NEVER collapse types across classes (no motorcycle→bicycle, no trailer→truck).
- NEVER drop negation (keep "not standing", "not stopped").
- Only perform safe surface-level cleanup and synonym unification.
- Question type detection is only for choosing answer format templates.
"""
from __future__ import annotations

import re
from typing import Tuple


class QuestionNormalizer:
    """Lightweight, non-destructive question normalizer."""

    # Safe, intra-class type synonyms (no cross-class merges)
    TYPE_SYNONYMS = {
        # Construction vehicles → treated as trucks in our simplified type system
        "construction vehicle": "truck",
        "construction vehicles": "trucks",
        # Generic "vehicle" often refers to a car in nuScenes scenes
        "vehicle": "car",
        "vehicles": "cars",
    }

    # Status synonyms (only truly equivalent words)
    STATUS_SYNONYMS = {
        "stationary": "stopped",
        "not moving": "stopped",
        # Explicit moving semantics
        "driving": "moving",
        "running": "moving",
    }

    # Direction / phrasing synonyms (unify wording, do not change direction semantics)
    DIRECTION_SYNONYMS = {
        "in front of": "to the front of",
        "in the front of": "to the front of",
        "behind": "to the back of",
        "in the back of": "to the back of",
        "to the rear of": "to the back of",
        "on the left of": "to the left of",
        "on the right of": "to the right of",
    }

    # Question type patterns (only used for answer formatting)
    QUESTION_TYPE_PATTERNS = {
        "exist": [
            r"^(Are|Is) there",
            r"^(Are|Is) any",
            r"^(Do|Does) .+ exist",
            r"^Can you see",
        ],
        "count": [
            r"^How many",
            r"^What number of",
            r"^What is the number of",
        ],
        "status": [
            r"^What (is|are) the status",
            r"^What status (is|are)",
            r"what (is|are) .+ status",
        ],
        "object": [
            r"^What (is|are) the .+ thing",
            r"^What (is|are) .+ that",
            r"^The .+ (is|are) what",
            r".+ is what\?$",
            # L2 patterns: "There is ...; what is it?"
            r"^There is .+what is it\??$",
            r"what is it\??$",
        ],
        "comparison": [
            r"same (status|type) as",
            r"same as",
            r"(is|are) .+ the same",
        ],
    }

    def normalize(self, question: str | None) -> Tuple[str, str]:
        """Normalize question text.

        Returns:
            (normalized_text, question_type)
        """
        # Robust handling of non-string inputs
        if question is None:
            q = ""
        else:
            q = str(question)

        # 0. Safe phrase-level cleanup (whitespace only)
        normalized = self._apply_phrase_normalizations(q)

        # 1. Type synonyms (only safe, intra-class mappings)
        normalized = self._replace_type_synonyms(normalized)

        # 2. Status synonyms
        normalized = self._replace_status_synonyms(normalized)

        # 3. Direction phrasing synonyms
        normalized = self._replace_direction_synonyms(normalized)

        # 4. Question type detection (for answer template only)
        question_type = self._detect_question_type(normalized)

        return normalized, question_type

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_phrase_normalizations(self, question: str) -> str:
        """Very conservative, surface-level normalization.

        Principles:
        - Do NOT remove negations (keep "not standing" etc.).
        - Do NOT change object types.
        - Only normalize whitespace and trivial formatting.
        """
        normalized = question.strip()
        # Collapse multiple whitespace characters into a single space
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _replace_type_synonyms(self, question: str) -> str:
        normalized = question
        for synonym, standard in self.TYPE_SYNONYMS.items():
            pattern = r"\b" + re.escape(synonym) + r"\b"
            normalized = re.sub(pattern, standard, normalized, flags=re.IGNORECASE)
        return normalized

    def _replace_status_synonyms(self, question: str) -> str:
        normalized = question
        for synonym, standard in self.STATUS_SYNONYMS.items():
            pattern = r"\b" + re.escape(synonym) + r"\b"
            normalized = re.sub(pattern, standard, normalized, flags=re.IGNORECASE)
        return normalized

    def _replace_direction_synonyms(self, question: str) -> str:
        normalized = question
        for synonym, standard in self.DIRECTION_SYNONYMS.items():
            normalized = re.sub(re.escape(synonym), standard, normalized, flags=re.IGNORECASE)
        return normalized

    def _detect_question_type(self, question: str) -> str:
        for qtype, patterns in self.QUESTION_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, question, re.IGNORECASE):
                    return qtype
        return "general"

    def get_expected_format(self, question_type: str) -> str:
        """Return expected answer format description for the given type."""
        format_specs = {
            "exist": 'Answer with "yes" or "no" only.',
            "count": 'Answer with a number only (e.g., "5").',
            "status": 'Answer with a status word only (e.g., "stopped", "moving", "with rider", "without rider").',
            "object": 'Answer with the object type only (e.g., "car", "pedestrian", "bicycle").',
            "comparison": 'Answer with "yes" or "no" only.',
            "general": 'Answer concisely with the key information only.',
        }
        return format_specs.get(question_type, format_specs["general"])


if __name__ == "__main__":
    # Simple manual test
    normalizer = QuestionNormalizer()
    tests = [
        "Are there any trailers?",
        "What status is the bicycle?",
        "There is a trailer; is it the same status as the truck to the back right of the with rider bicycle?",
        "What number of other things are there of the same status as the trailer?",
    ]
    print("Question normalization quick test:")
    print("=" * 80)
    for q in tests:
        norm, qtype = normalizer.normalize(q)
        fmt = normalizer.get_expected_format(qtype)
        print(f"\nQ: {q}\nN: {norm}\nType: {qtype}\nFormat: {fmt}\n" + "-" * 80)
