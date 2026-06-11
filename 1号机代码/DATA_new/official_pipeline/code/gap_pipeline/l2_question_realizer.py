"""
Question realizer for the L2 refactor side path.

Programmatic templates only. No LLM rewriting is used here.
Each family has multiple sentence variants to improve diversity.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, List, Optional

from gap_pipeline.l2_constraint_planner import L2Clause
from gap_pipeline.l2_geometry import direction_text


# Module-level RNG for variant selection; seeded externally if needed.
_variant_rng = random.Random()


def set_variant_seed(seed: int) -> None:
    """Set seed for reproducible variant selection."""
    _variant_rng.seed(seed)


@dataclass(frozen=True)
class RealizedQuestion:
    question: str
    answer_type: str
    template_family: str


def _article(noun: str) -> str:
    if not noun:
        return "a"
    return "an" if noun[0].lower() in "aeiou" else "a"


def _plural(noun: str) -> str:
    if not noun:
        return "objects"
    if noun.endswith("s"):
        return noun
    if noun.endswith("y") and len(noun) > 1 and noun[-2].lower() not in "aeiou":
        return noun[:-1] + "ies"
    return noun + "s"


def _clean_spaces(text: str) -> str:
    return " ".join(text.replace(" ,", ",").replace(" ?", "?").split())


def render_clause(clause: L2Clause) -> str:
    if clause.kind == "ref_dir":
        return f"to the {direction_text(clause.value)} of {clause.ref_id}"
    if clause.kind == "dist_rank":
        return clause.value.replace("-", " ")
    return clause.text_hint or clause.value


def render_extra_clauses(clauses: Iterable[L2Clause]) -> str:
    parts = [render_clause(c) for c in clauses if c.kind == "ref_dir"]
    if not parts:
        return ""
    return ", and " + ", and ".join(parts)


def render_rank_prefix(clauses: Iterable[L2Clause]) -> str:
    for c in clauses:
        if c.kind == "dist_rank":
            return c.value.replace("-", " ") + " "
    return ""


def object_desc(
    obj_type: str,
    *,
    base_relation: str,
    anchor_id: str,
    clauses: Iterable[L2Clause] = (),
) -> str:
    rank = render_rank_prefix(clauses)
    extra = render_extra_clauses(clauses)
    label = "ego vehicle" if obj_type == "ego" else f"{rank}{obj_type}"
    return _clean_spaces(f"the {label} to the {direction_text(base_relation)} of {anchor_id}{extra}")


# ── Converge question variants ─────────────────────────────────────────────

def converge_question(
    *,
    target_type: str,
    a_id: str,
    c_id: str,
    dir_from_a: str,
    dir_from_c: str,
    clauses: Iterable[L2Clause] = (),
    mode: str = "object",
) -> RealizedQuestion:
    rank = render_rank_prefix(clauses)
    extra = render_extra_clauses(clauses)
    label = "ego vehicle" if target_type == "ego" else f"{rank}{target_type}"
    da = direction_text(dir_from_a)
    dc = direction_text(dir_from_c)

    if mode == "status":
        variants = [
            f"What is the status of the {label} to the {da} of {a_id} and to the {dc} of {c_id}{extra}?",
            f"The {label} to the {da} of {a_id} and to the {dc} of {c_id}{extra} — what is its status?",
            f"Describe the status of the {label} located to the {da} of {a_id} and to the {dc} of {c_id}{extra}.",
            f"What state is the {label} in, the one to the {da} of {a_id} and to the {dc} of {c_id}{extra}?",
        ]
        answer_type = "status"
    elif mode == "exist":
        variants = [
            f"Is there {_article(target_type)} {label} to the {da} of {a_id} and to the {dc} of {c_id}{extra}?",
            f"Can you see {_article(target_type)} {label} to the {da} of {a_id} and to the {dc} of {c_id}{extra}?",
            f"Is {_article(target_type)} {label} visible to the {da} of {a_id} and to the {dc} of {c_id}{extra}?",
        ]
        answer_type = "boolean"
    elif mode == "count":
        tp = _plural(target_type)
        variants = [
            f"How many {tp} are to the {da} of {a_id} and to the {dc} of {c_id}{extra}?",
            f"Count the {tp} to the {da} of {a_id} and to the {dc} of {c_id}{extra}.",
            f"What number of {tp} are located to the {da} of {a_id} and to the {dc} of {c_id}{extra}?",
        ]
        answer_type = "count"
    else:
        variants = [
            f"What {target_type} is to the {da} of {a_id} and to the {dc} of {c_id}{extra}?",
            f"Which {target_type} can be found to the {da} of {a_id} and to the {dc} of {c_id}{extra}?",
            f"Identify the {target_type} located to the {da} of {a_id} and to the {dc} of {c_id}{extra}.",
            f"There is a {target_type} to the {da} of {a_id} and to the {dc} of {c_id}{extra}; what is it?",
            f"What {target_type} is positioned to the {da} of {a_id} and also to the {dc} of {c_id}{extra}?",
        ]
        answer_type = "object"

    q = _variant_rng.choice(variants)
    return RealizedQuestion(_clean_spaces(q), answer_type, "converge")


# ── Diverge question variants ──────────────────────────────────────────────

def diverge_status_question(
    *,
    b_id: str,
    a_type: str,
    a_dir: str,
    c_type: str,
    c_dir: str,
    a_clauses: Iterable[L2Clause] = (),
    c_clauses: Iterable[L2Clause] = (),
) -> RealizedQuestion:
    a_desc = object_desc(a_type, base_relation=a_dir, anchor_id=b_id, clauses=a_clauses)
    c_desc = object_desc(c_type, base_relation=c_dir, anchor_id=b_id, clauses=c_clauses)
    variants = [
        f"Do {a_desc} and {c_desc} have the same status?",
        f"Are {a_desc} and {c_desc} in the same state?",
        f"Is the status of {a_desc} identical to that of {c_desc}?",
        f"Compare {a_desc} and {c_desc}: do they share the same status?",
    ]
    q = _variant_rng.choice(variants)
    return RealizedQuestion(_clean_spaces(q), "boolean", "diverge_compare")


def diverge_type_question(
    *,
    b_id: str,
    a_type: str,
    a_dir: str,
    c_type: str,
    c_dir: str,
    a_clauses: Iterable[L2Clause] = (),
    c_clauses: Iterable[L2Clause] = (),
) -> RealizedQuestion:
    """Diverge variant: compare types of two branches."""
    a_desc = object_desc(a_type, base_relation=a_dir, anchor_id=b_id, clauses=a_clauses)
    c_desc = object_desc(c_type, base_relation=c_dir, anchor_id=b_id, clauses=c_clauses)
    variants = [
        f"Are {a_desc} and {c_desc} the same type of object?",
        f"Do {a_desc} and {c_desc} belong to the same category?",
        f"Is {a_desc} the same type as {c_desc}?",
    ]
    q = _variant_rng.choice(variants)
    return RealizedQuestion(_clean_spaces(q), "boolean", "diverge_compare")


def diverge_branch_status_question(
    *,
    b_id: str,
    branch_type: str,
    branch_dir: str,
    branch_clauses: Iterable[L2Clause] = (),
) -> RealizedQuestion:
    """Ask the status of one spatially-locked branch object."""
    desc = object_desc(branch_type, base_relation=branch_dir, anchor_id=b_id, clauses=branch_clauses)
    variants = [
        f"What is the status of {desc}?",
        f"Describe the current state of {desc}.",
        f"{desc} — what is its status?",
    ]
    q = _variant_rng.choice(variants)
    return RealizedQuestion(_clean_spaces(q), "status", "diverge_compare")


def diverge_branch_object_question(
    *,
    b_id: str,
    branch_type: str,
    branch_dir: str,
    branch_clauses: Iterable[L2Clause] = (),
) -> RealizedQuestion:
    """Ask the identity of one spatially-locked branch object."""
    desc_label = f"{branch_type} to the {direction_text(branch_dir)} of {b_id}"
    extra = render_extra_clauses(branch_clauses)
    variants = [
        f"What {desc_label}{extra} can you identify?",
        f"Which {desc_label}{extra} is present in the scene?",
        f"Identify the {desc_label}{extra}.",
    ]
    q = _variant_rng.choice(variants)
    return RealizedQuestion(_clean_spaces(q), "object", "diverge_compare")


def diverge_branch_exist_question(
    *,
    b_id: str,
    branch_type: str,
    branch_dir: str,
    branch_clauses: Iterable[L2Clause] = (),
) -> RealizedQuestion:
    """Ask whether the spatially-locked branch object exists."""
    desc = object_desc(branch_type, base_relation=branch_dir, anchor_id=b_id, clauses=branch_clauses)
    variants = [
        f"Is {desc} visible in the scene?",
        f"Can you see {desc}?",
        f"Is there {_article(branch_type)} {branch_type} to the {direction_text(branch_dir)} of {b_id}{render_extra_clauses(branch_clauses)}?",
    ]
    q = _variant_rng.choice(variants)
    return RealizedQuestion(_clean_spaces(q), "boolean", "diverge_compare")


def diverge_branch_count_question(
    *,
    b_id: str,
    branch_type: str,
    branch_dir: str,
    branch_clauses: Iterable[L2Clause] = (),
) -> RealizedQuestion:
    """Ask count of objects matching the branch description."""
    tp = _plural(branch_type)
    extra = render_extra_clauses(branch_clauses)
    variants = [
        f"How many {tp} are to the {direction_text(branch_dir)} of {b_id}{extra}?",
        f"Count the {tp} to the {direction_text(branch_dir)} of {b_id}{extra}.",
    ]
    q = _variant_rng.choice(variants)
    return RealizedQuestion(_clean_spaces(q), "count", "diverge_compare")


def counterfactual_exist_question(
    *,
    anchor_id: str,
    fake_type: str,
    direction: str,
) -> RealizedQuestion:
    """Ask about a type that does NOT exist at the described location. Answer: No."""
    dtext = direction_text(direction)
    variants = [
        f"Is there {_article(fake_type)} {fake_type} to the {dtext} of {anchor_id}?",
        f"Can you see any {fake_type} to the {dtext} of {anchor_id}?",
        f"Is {_article(fake_type)} {fake_type} present to the {dtext} of {anchor_id}?",
    ]
    q = _variant_rng.choice(variants)
    return RealizedQuestion(_clean_spaces(q), "boolean", "counterfactual_exist")


# ── Distance chain variants ───────────────────────────────────────────────

def distance_chain_question(a_id: str, b_id: str, c_id: str) -> RealizedQuestion:
    variants = [
        f"Is {b_id} closer to {a_id} or to {c_id}?",
        f"Which object is {b_id} nearer to, {a_id} or {c_id}?",
        f"Between {a_id} and {c_id}, which one is closer to {b_id}?",
        f"Of {a_id} and {c_id}, which is at a shorter distance from {b_id}?",
    ]
    q = _variant_rng.choice(variants)
    return RealizedQuestion(_clean_spaces(q), "choice", "distance_chain")


# ── Direction chain variants ──────────────────────────────────────────────

def direction_chain_question(a_id: str, b_id: str, c_id: str) -> RealizedQuestion:
    variants = [
        f"Is {c_id} in the same direction from {b_id} as {b_id} is from {a_id}?",
        f"Does {c_id} lie in the same direction from {b_id} as {a_id}?",
        f"From {b_id}'s perspective, are {a_id} and {c_id} in the same direction?",
        f"Considering the direction from {a_id} to {b_id}, is {c_id} in a similar direction from {b_id}?",
    ]
    q = _variant_rng.choice(variants)
    return RealizedQuestion(_clean_spaces(q), "boolean", "direction_chain")


# ── Viewpoint transfer variants ───────────────────────────────────────────

def viewpoint_transfer_question(a_id: str, b_id: str, c_id: str) -> RealizedQuestion:
    variants = [
        f"If you face from {a_id} toward {b_id}, is {c_id} on your left or on your right?",
        f"Standing at {a_id} and looking toward {b_id}, is {c_id} to the left or the right?",
        f"From {a_id}, facing {b_id}, which side is {c_id} on — left or right?",
        f"Imagine facing from {a_id} toward {b_id}; would {c_id} be on your left or right?",
    ]
    q = _variant_rng.choice(variants)
    return RealizedQuestion(_clean_spaces(q), "choice", "viewpoint_transfer")


