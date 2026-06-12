import json
import subprocess
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from experiment_protocol import EXTERNAL_LAYER, annotate_provenance


FollowupGenerator = Callable[[str, str], Mapping]


class QAAskeRMR2Process:
    """Persistent bridge to the original QAAskeR NLP environment."""

    def __init__(
        self,
        python_executable: Path,
        worker_path: Optional[Path] = None,
        command: Optional[Sequence[str]] = None,
    ) -> None:
        if command is None:
            worker = worker_path or Path(__file__).with_name("qaasker_mr2_worker.py")
            command = [str(python_executable), "-u", str(worker)]
        self._command = list(command)
        self._process: Optional[subprocess.Popen] = None

    def start(self) -> "QAAskeRMR2Process":
        if self._process is not None:
            return self
        self._process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        return self

    def generate(self, question: str, primary_answer: str) -> Mapping:
        self.start()
        assert self._process is not None
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        request = {"question": question, "primary_answer": primary_answer}
        self._process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self._process.stdin.flush()
        response_line = self._process.stdout.readline()
        if not response_line:
            stderr = ""
            if self._process.stderr is not None:
                stderr = self._process.stderr.read()
            raise RuntimeError(
                "QAAskeR MR2 worker terminated without a response"
                + (f": {stderr.strip()}" if stderr.strip() else "")
            )
        response = json.loads(response_line)
        if not response.get("ok"):
            raise RuntimeError(
                f"QAAskeR MR2 generation failed: {response.get('error', 'unknown')}"
            )
        return response["followup"]

    def close(self) -> None:
        if self._process is None:
            return
        if self._process.stdin is not None:
            self._process.stdin.close()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            self._process.wait(timeout=5)
        self._process = None

    def __enter__(self) -> "QAAskeRMR2Process":
        return self.start()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


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
