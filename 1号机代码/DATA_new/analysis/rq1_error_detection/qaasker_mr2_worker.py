import json
import sys

from selectors_qaasker import (
    HAS_QAASKER,
    S2I,
    change,
    coordinate_question_for_qaasker,
)


def generate_mr2(question: str, primary_answer: str) -> dict:
    if not HAS_QAASKER:
        raise RuntimeError("Original QAAskeR modules are unavailable")
    coordinated = coordinate_question_for_qaasker(question)
    statement = change(coordinated, primary_answer)
    if not statement or statement == "None":
        raise ValueError("Q2S could not synthesize a declarative statement")
    followup = S2I(statement)
    if not followup or followup == "None":
        raise ValueError("S2G could not synthesize a general question")
    return {
        "question": str(followup),
        "answer": "yes",
        "metamorphic_relation": "MR2",
        "qaasker_statement": str(statement),
        "generation_backend": "qaasker_original_q2s_s2g",
    }


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            followup = generate_mr2(
                str(request["question"]), str(request["primary_answer"])
            )
            response = {"ok": True, "followup": followup}
        except Exception as exc:
            response = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
