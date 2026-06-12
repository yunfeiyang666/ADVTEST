from typing import Mapping


STRUCTURAL_LAYER = "structural_coverage"
EXTERNAL_LAYER = "cross_paradigm"
OFFICIAL_SELECTION_LAYER = "official_qa_selection"

ADVTEST_PRIVATE_FIELDS = frozenset(
    {
        "coverage_footprint",
        "coverage_l0",
        "coverage_l1",
        "coverage_l2",
        "delta_l0",
        "delta_l1",
        "delta_l2",
        "generation_phase",
        "generation_round",
        "l2_score",
        "path_pattern",
        "plan_attempt_key",
        "selection_phase",
    }
)

REQUIRED_PROVENANCE_FIELDS = frozenset(
    {
        "experiment_layer",
        "experiment_method",
        "question_source",
        "source_question_id",
        "source_sample_token",
        "generation_adapter",
        "uses_coverage_feedback",
        "vlm_call_cost",
        "global_budget_index",
        "scene_frame",
    }
)


def validate_question_boundary(question: Mapping, layer: str) -> None:
    if layer == EXTERNAL_LAYER:
        leaked = sorted(ADVTEST_PRIVATE_FIELDS.intersection(question))
        if leaked:
            raise ValueError(
                "External question contains ADVTEST-private fields: "
                + ", ".join(leaked)
            )


def validate_provenance(question: Mapping) -> None:
    missing = sorted(REQUIRED_PROVENANCE_FIELDS.difference(question))
    if missing:
        raise ValueError("Question is missing provenance fields: " + ", ".join(missing))


def annotate_provenance(
    question: Mapping,
    *,
    layer: str,
    method: str,
    question_source: str,
    source_question_id: str,
    source_sample_token: str,
    generation_adapter: str,
    uses_coverage_feedback: bool,
    vlm_call_cost: int,
    scene_frame: str,
    global_budget_index: int,
) -> dict:
    validate_question_boundary(question, layer)
    annotated = dict(question)
    annotated.update(
        {
            "experiment_layer": layer,
            "experiment_method": method,
            "question_source": question_source,
            "source_question_id": str(source_question_id),
            "source_sample_token": str(source_sample_token or ""),
            "generation_adapter": generation_adapter,
            "uses_coverage_feedback": bool(uses_coverage_feedback),
            "vlm_call_cost": int(vlm_call_cost),
            "global_budget_index": int(global_budget_index),
            "scene_frame": scene_frame,
        }
    )
    validate_provenance(annotated)
    return annotated
