from typing import Callable, Mapping, Optional

from experiment_protocol import EXTERNAL_LAYER, annotate_provenance


FollowupGenerator = Callable[[str, str], Mapping]


class QAAskeRAdapter:
    """Stateful boundary for QAAskeR primary/follow-up VLM calls."""

    def __init__(
        self, followup_generator: Optional[FollowupGenerator] = None
    ) -> None:
        self._followup_generator = followup_generator

    def build_primary(
        self,
        seed_question: Mapping,
        *,
        scene_frame: str,
        global_budget_index: int,
    ) -> dict:
        question = {
            key: seed_question[key]
            for key in ("question", "answer", "sample_token")
            if key in seed_question
        }
        question["qaasker_stage"] = "primary"
        return annotate_provenance(
            question,
            layer=EXTERNAL_LAYER,
            method="qaasker",
            question_source="nuscenes_qa",
            source_question_id=str(seed_question["official_question_id"]),
            source_sample_token=str(seed_question["sample_token"]),
            generation_adapter="qaasker_stateful_adapter",
            uses_coverage_feedback=False,
            vlm_call_cost=1,
            scene_frame=scene_frame,
            global_budget_index=global_budget_index,
        )

    def build_followup(
        self,
        seed_question: Mapping,
        *,
        primary_sut_answer: str,
        scene_frame: str,
        global_budget_index: int,
    ) -> dict:
        if not primary_sut_answer:
            raise ValueError("QAAskeR follow-up requires the primary SUT answer")
        if self._followup_generator is None:
            raise RuntimeError(
                "QAAskeR follow-up generation backend is not configured"
            )
        generated = dict(
            self._followup_generator(
                str(seed_question["question"]), str(primary_sut_answer)
            )
        )
        if not generated.get("question") or "answer" not in generated:
            raise ValueError(
                "QAAskeR backend must return question and answer fields"
            )
        generated.update(
            {
                "qaasker_stage": "followup",
                "primary_question": str(seed_question["question"]),
                "primary_sut_answer": str(primary_sut_answer),
                "qaasker_pair_vlm_call_cost": 2,
            }
        )
        return annotate_provenance(
            generated,
            layer=EXTERNAL_LAYER,
            method="qaasker",
            question_source="nuscenes_qa",
            source_question_id=str(seed_question["official_question_id"]),
            source_sample_token=str(seed_question["sample_token"]),
            generation_adapter="qaasker_stateful_adapter",
            uses_coverage_feedback=False,
            vlm_call_cost=1,
            scene_frame=scene_frame,
            global_budget_index=global_budget_index,
        )
