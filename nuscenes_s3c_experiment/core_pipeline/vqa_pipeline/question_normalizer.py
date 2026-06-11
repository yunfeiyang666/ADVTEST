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
import logging
from typing import Tuple, Dict, List

logger = logging.getLogger(__name__)


class QuestionNormalizer:
    """Lightweight, non-destructive question normalizer.
    
    This normalizer performs safe, surface-level transformations only.
    It never changes the semantic meaning of questions.
    """

    # Safe, intra-class type synonyms (no cross-class merges)
    # WARNING: "vehicle" -> "car" mapping may be imprecise in some contexts
    TYPE_SYNONYMS: Dict[str, str] = {
        # Construction vehicles -> treated as trucks in our simplified type system
        "construction vehicle": "truck",
        "construction vehicles": "trucks",
        # Generic "vehicle" often refers to a car in nuScenes scenes
        # TODO: Consider removing this mapping if it causes false matches
        "vehicle": "car",
        "vehicles": "cars",
    }

    # Status synonyms (only truly equivalent words)
    STATUS_SYNONYMS: Dict[str, str] = {
        "stationary": "stopped",
        "not moving": "stopped",
        # Explicit moving semantics
        "driving": "moving",
        "running": "moving",
    }

    # Direction / phrasing synonyms (unify wording, do not change direction semantics)
    # Sorted by length (longest first) to avoid partial replacement issues
    DIRECTION_SYNONYMS: Dict[str, str] = {
        "in the front of": "to the front of",  # longest first
        "in front of": "to the front of",
        "in the back of": "to the back of",
        "to the rear of": "to the back of",
        "on the left of": "to the left of",
        "on the right of": "to the right of",
        "behind": "to the back of",  # single word last
    }

    # Question type patterns (only used for answer formatting)
    # Order matters: more specific patterns should come first within each type
    QUESTION_TYPE_PATTERNS: Dict[str, List[str]] = {
        # Comparison checked first (more specific than exist)
        "comparison": [
            r"same (status|type) as",
            r"same as",
            r"(is|are) .+ the same",
        ],
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
    }

    def normalize(self, question: str | None) -> Tuple[str, str]:
        """Normalize question text.

        Args:
            question: The question text to normalize (can be None)

        Returns:
            Tuple of (normalized_text, question_type)
        """
        # Robust handling of non-string inputs
        if question is None:
            logger.debug("Received None question, returning empty string")
            return "", "general"
        
        q = str(question).strip()
        if not q:
            logger.debug("Received empty question")
            return "", "general"

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

        # Log if normalization changed the question
        if normalized != q:
            logger.debug(f"Question normalized: '{q}' -> '{normalized}'")
        logger.debug(f"Detected question type: {question_type}")

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
        """Replace direction synonyms, processing longer phrases first."""
        normalized = question
        # Sort by length (longest first) to avoid partial replacement issues
        # e.g., "in the front of" should be processed before "in front of"
        sorted_synonyms = sorted(self.DIRECTION_SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True)
        for synonym, standard in sorted_synonyms:
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
    # Setup logging for standalone test
    logging.basicConfig(level=logging.DEBUG)
    
    # Simple manual test
    normalizer = QuestionNormalizer()
    tests = [
        "Are there any trailers?",
        "What status is the bicycle?",
        "There is a trailer; is it the same status as the truck to the back right of the with rider bicycle?",
        "What number of other things are there of the same status as the trailer?",
        # Edge cases
        None,
        "",
        "Is the vehicle behind the truck?",  # Tests direction + type synonym
    ]
    print("Question normalization quick test:")
    print("=" * 80)
    for q in tests:
        norm, qtype = normalizer.normalize(q)
        fmt = normalizer.get_expected_format(qtype)
        print(f"\nQ: {q!r}\nN: {norm!r}\nType: {qtype}\nFormat: {fmt}\n" + "-" * 80)
