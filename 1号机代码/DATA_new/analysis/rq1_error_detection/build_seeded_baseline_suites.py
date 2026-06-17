import argparse
import contextlib
import importlib.util
import json
import random
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Sequence

from experiment_protocol import EXTERNAL_LAYER, annotate_provenance
from qaasker_adapter import QAAskeRAdapter, QAAskeRMR2Process
from qatest_adapted import normalize_text


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SEED_BANK = (
    WORKSPACE_ROOT
    / "scratch"
    / "rq1_group_minimal"
    / "runs"
    / "seed-filter-mplug-f30-q454-v5"
    / "results"
    / "correct_seed_bank.jsonl"
)
DEFAULT_OUTPUT_DIR = (
    WORKSPACE_ROOT
    / "scratch"
    / "rq1_group_minimal"
    / "runs"
    / "seeded_baseline_suites"
    / "results"
)
DEFAULT_QATEST_DIR = WORKSPACE_ROOT / "baselines" / "QATest"
DEFAULT_QAASKER_PYTHON = WORKSPACE_ROOT / ".venv310" / "Scripts" / "python.exe"


QATEST_MUTATION_NAMES = (
    "keybord_mistake",
    "ocr_mistake",
    "spelling_mistake",
    "synonym_replace",
    "adverbial_preposition",
    "insert_word",
    "back_translate",
    "entity_replace",
    "wps",
    "double_question_mark",
)
QATEST_ENV_UNAVAILABLE_MUTATIONS = {
    "insert_word",
    "back_translate",
    "entity_replace",
}


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, records: Iterable[Mapping]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def seed_source_id(seed: Mapping) -> str:
    return str(
        seed.get("official_question_id")
        or seed.get("source_question_id")
        or seed.get("seed_id")
        or ""
    )


def seed_primary_answer(seed: Mapping, *, prefer_vlm_answer: bool = True) -> str:
    if prefer_vlm_answer:
        answer = str(seed.get("seed_filter_predicted") or "").strip()
        if answer:
            return answer
    return str(seed.get("answer") or "").strip()


def to_qatest_seed(seed: Mapping) -> dict:
    question = str(seed.get("question") or "")
    return {
        "question": question,
        "answer": seed.get("answer", ""),
        "init_q": question,
        "is_init": True,
        "aug_times": 0,
        "iter_times": 0,
        "seed_id": seed.get("seed_id", ""),
        "source_question_id": seed_source_id(seed),
        "source_sample_token": seed.get("source_sample_token")
        or seed.get("sample_token")
        or "",
        "sample_token": seed.get("sample_token", ""),
        "scene_frame": seed.get("scene_frame", ""),
        "template_type": seed.get("template_type", ""),
    }


def _as_text(value) -> str:
    if isinstance(value, list):
        if not value:
            return ""
        return str(value[0])
    return str(value)


def _load_original_qatest(qatest_dir: Path):
    if str(qatest_dir) not in sys.path:
        sys.path.insert(0, str(qatest_dir))
    module_path = qatest_dir / "main.py"
    spec = importlib.util.spec_from_file_location("qatest_original_main", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load QATest main.py from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patch_qatest_environment(module) -> None:
    for name in QATEST_MUTATION_NAMES:
        if not hasattr(module, name):
            continue
        original = getattr(module, name)

        def wrapped(question, _name=name, _original=original):
            if _name in QATEST_ENV_UNAVAILABLE_MUTATIONS:
                return str(question)
            try:
                return _as_text(_original(question))
            except Exception:
                # Environment compatibility: original QATest includes operators
                # backed by hard-coded local models or external services. Returning
                # the input lets the original retry loop mark this operator as a
                # failed mutation and continue to another operator.
                return str(question)

        setattr(module, name, wrapped)
    try:
        import question_parse

        def simple_word_tokenize(text: str) -> list[str]:
            return re.findall(r"\w+|[?.,]", str(text))

        def simple_pos_tag(tokens: Sequence[str]) -> list[tuple[str, str]]:
            tagged = []
            for token in tokens:
                lower = token.lower()
                if token in {"?", ".", "??"}:
                    tag = token
                elif lower in {"what", "which", "who"}:
                    tag = "WP"
                elif lower in {"where", "when", "how", "why"}:
                    tag = "WRB"
                elif lower in {"is", "are", "was", "were", "does", "do"}:
                    tag = "VBZ"
                else:
                    tag = "NN"
                tagged.append((token, tag))
            return tagged

        question_parse.word_tokenize = simple_word_tokenize
        question_parse.nltk.pos_tag = simple_pos_tag
    except Exception:
        pass


def run_original_qatest(
    seeds: Sequence[Mapping],
    *,
    budget: int,
    seed: int,
    qatest_dir: Path = DEFAULT_QATEST_DIR,
    iter_n: Optional[int] = None,
    save_path: Optional[Path] = None,
    stdout_log_path: Optional[Path] = None,
) -> tuple[list[dict], dict]:
    if budget < 1:
        raise ValueError("budget must be positive")
    if not seeds:
        raise ValueError("QATest requires at least one seed")
    module = _load_original_qatest(qatest_dir)
    _patch_qatest_environment(module)
    try:
        import numpy as np

        np.random.seed(seed)
    except Exception:
        pass
    random.seed(seed)
    seed_tests = [to_qatest_seed(item) for item in seeds]
    seed_dict = module.get_seed_dict(seed_tests)
    rounds = iter_n if iter_n is not None else max(1, (budget + 4) // 5 + 50)
    if save_path is None:
        tmp = tempfile.NamedTemporaryFile(
            prefix="qatest_aug_num_", suffix=".txt", delete=False
        )
        tmp.close()
        save_path = Path(tmp.name)
    if stdout_log_path is not None:
        stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
        with stdout_log_path.open("w", encoding="utf-8") as log_handle:
            with contextlib.redirect_stdout(log_handle):
                generated, final_seed_tests, aug_num = module.run(
                    seed_tests,
                    str(save_path),
                    seed_dict,
                    "qatest",
                    iter_N=rounds,
                )
    else:
        generated, final_seed_tests, aug_num = module.run(
            seed_tests,
            str(save_path),
            seed_dict,
            "qatest",
            iter_N=rounds,
        )
    metadata = {
        "requested_budget": budget,
        "iter_n": rounds,
        "generated_raw": len(generated),
        "final_seed_pool": len(final_seed_tests),
        "aug_num_trace": list(aug_num),
        "save_path": str(save_path),
        "stdout_log_path": str(stdout_log_path) if stdout_log_path else None,
    }
    return list(generated), metadata


def annotate_qatest_records(records: Sequence[Mapping], *, budget: int) -> list[dict]:
    annotated = []
    for index, record in enumerate(records[:budget], start=1):
        source_id = str(record.get("source_question_id") or record.get("seed_id") or "")
        row = {
            "question": str(record.get("question") or ""),
            "answer": record.get("answer", ""),
            "original_question": record.get("init_q") or record.get("original_question"),
            "qatest_mutated": True,
            "qatest_operator": record.get("aug", ""),
            "qatest_iter_times": record.get("iter_times", 0),
            "template_type": record.get("template_type", ""),
            "seed_id": record.get("seed_id", ""),
        }
        annotated.append(
            annotate_provenance(
                row,
                layer=EXTERNAL_LAYER,
                method="qatest",
                question_source="nuscenes_qa",
                source_question_id=source_id,
                source_sample_token=str(
                    record.get("source_sample_token") or record.get("sample_token") or ""
                ),
                generation_adapter="qatest_original_run_with_env_compat",
                uses_coverage_feedback=False,
                vlm_call_cost=1,
                scene_frame=str(record.get("scene_frame") or ""),
                global_budget_index=index,
            )
        )
    return annotated


def build_qatest_suite(
    seeds: Sequence[Mapping],
    *,
    budget: int,
    seed: int,
    qatest_dir: Path = DEFAULT_QATEST_DIR,
    iter_n: Optional[int] = None,
    stdout_log_path: Optional[Path] = None,
) -> dict:
    generated, metadata = run_original_qatest(
        seeds,
        budget=budget,
        seed=seed,
        qatest_dir=qatest_dir,
        iter_n=iter_n,
        stdout_log_path=stdout_log_path,
    )
    accepted = annotate_qatest_records(generated, budget=budget)
    duplicate_count = count_duplicate_questions(accepted)
    summary = {
        "method": "qatest",
        "requested_budget": budget,
        "accepted_for_eval": len(accepted),
        "generated_raw": len(generated),
        "generation_rejected": max(0, budget - len(accepted)),
        "duplicate_same_frame_questions": duplicate_count,
        **metadata,
    }
    return {"records": accepted, "summary": summary}


def count_duplicate_questions(records: Sequence[Mapping]) -> int:
    seen = set()
    duplicates = 0
    for record in records:
        key = (
            str(record.get("scene_frame") or ""),
            normalize_text(str(record.get("question") or "")),
        )
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates


def build_qaasker_suite(
    seeds: Sequence[Mapping],
    *,
    budget: int,
    seed: int,
    followup_generator: Callable[[str, str], Mapping],
    max_attempts: Optional[int] = None,
    prefer_vlm_answer: bool = True,
) -> dict:
    if budget < 1:
        raise ValueError("budget must be positive")
    if not seeds:
        raise ValueError("QAAskeR requires at least one seed")
    rng = random.Random(seed)
    seed_pool = list(seeds)
    adapter = QAAskeRAdapter(followup_generator=followup_generator)
    attempts_limit = max_attempts or max(budget * 5, len(seed_pool))
    records = []
    rejected = []
    attempts = 0

    while len(records) < budget and attempts < attempts_limit:
        attempts += 1
        seed_item = dict(seed_pool[(attempts - 1) % len(seed_pool)])
        if attempts % len(seed_pool) == 1:
            rng.shuffle(seed_pool)
        try:
            followup = adapter.build_followup(
                {
                    **seed_item,
                    "official_question_id": seed_source_id(seed_item),
                },
                primary_sut_answer=seed_primary_answer(
                    seed_item, prefer_vlm_answer=prefer_vlm_answer
                ),
                scene_frame=str(seed_item.get("scene_frame") or ""),
                global_budget_index=len(records) + 1,
            )
            followup.update(
                {
                    "seed_id": seed_item.get("seed_id", ""),
                    "primary_seed_question": seed_item.get("question", ""),
                    "primary_seed_answer": seed_item.get("answer", ""),
                    "qaasker_attempt_index": attempts,
                }
            )
            records.append(followup)
        except Exception as exc:
            rejected.append(
                {
                    "attempt_index": attempts,
                    "seed_id": seed_item.get("seed_id", ""),
                    "source_question_id": seed_source_id(seed_item),
                    "scene_frame": seed_item.get("scene_frame", ""),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    error_counts = Counter(item["error"] for item in rejected)
    summary = {
        "method": "qaasker",
        "requested_budget": budget,
        "attempted_generated": attempts,
        "accepted_for_eval": len(records),
        "generation_rejected": len(rejected),
        "generation_rejection_rate": len(rejected) / attempts if attempts else 0.0,
        "duplicate_same_frame_questions": count_duplicate_questions(records),
        "unique_same_frame_questions": len(records) - count_duplicate_questions(records),
        "max_attempts": attempts_limit,
        "prefer_vlm_answer": prefer_vlm_answer,
        "rejection_error_counts": dict(error_counts),
    }
    return {"records": records, "summary": summary, "rejected": rejected}


def write_suite_bundle(output_dir: Path, method: str, result: Mapping) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / f"{method}_suite.jsonl", result["records"])
    (output_dir / f"{method}_summary.json").write_text(
        json.dumps(result["summary"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if result.get("rejected"):
        write_jsonl(output_dir / f"{method}_rejected.jsonl", result["rejected"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build seeded QATest/QAAskeR baseline suites from correct seeds."
    )
    parser.add_argument("--seed-bank", type=Path, default=DEFAULT_SEED_BANK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--budget", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=["qatest", "qaasker"],
        default=["qatest", "qaasker"],
    )
    parser.add_argument("--qatest-dir", type=Path, default=DEFAULT_QATEST_DIR)
    parser.add_argument("--qatest-iter-n", type=int, default=None)
    parser.add_argument("--qaasker-python", type=Path, default=DEFAULT_QAASKER_PYTHON)
    parser.add_argument("--qaasker-max-attempts", type=int, default=None)
    parser.add_argument(
        "--qaasker-use-gold-answer",
        action="store_true",
        help="Use seed gold answers instead of the stored VLM primary answer.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    seeds = list(iter_jsonl(args.seed_bank))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_summary = {
        "seed_bank": str(args.seed_bank),
        "seed_count": len(seeds),
        "budget": args.budget,
        "seed": args.seed,
        "methods": args.methods,
    }

    if "qatest" in args.methods:
        qatest_result = build_qatest_suite(
            seeds,
            budget=args.budget,
            seed=args.seed,
            qatest_dir=args.qatest_dir,
            iter_n=args.qatest_iter_n,
            stdout_log_path=args.output_dir / "qatest_original_stdout.log",
        )
        write_suite_bundle(args.output_dir, "qatest", qatest_result)
        run_summary["qatest"] = qatest_result["summary"]

    if "qaasker" in args.methods:
        with QAAskeRMR2Process(args.qaasker_python) as backend:
            qaasker_result = build_qaasker_suite(
                seeds,
                budget=args.budget,
                seed=args.seed,
                followup_generator=backend.generate,
                max_attempts=args.qaasker_max_attempts,
                prefer_vlm_answer=not args.qaasker_use_gold_answer,
            )
        write_suite_bundle(args.output_dir, "qaasker", qaasker_result)
        run_summary["qaasker"] = qaasker_result["summary"]

    (args.output_dir / "seeded_baseline_suites_summary.json").write_text(
        json.dumps(run_summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"[seeded-baselines] seed_count={len(seeds)} "
        f"methods={','.join(args.methods)} output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
