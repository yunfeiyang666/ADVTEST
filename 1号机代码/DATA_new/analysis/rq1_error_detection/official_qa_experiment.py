import argparse
import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from evaluator import get_sample_token
from experiment_protocol import EXTERNAL_LAYER, annotate_provenance
from qatest_adapted import QATestGenerator, QATestSeed


DEFAULT_QUESTIONS_PATH = (
    WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "data" / "NuScenes_val_questions.json"
)
DEFAULT_FRAME_CACHE = (
    WORKSPACE_ROOT
    / "1号机代码"
    / "DATA_new"
    / "analysis"
    / "data_cache"
    / "rq1_100_eval_frames.json"
)
DEFAULT_OUTPUTS_ROOT = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "outputs"
DEFAULT_DATAROOT = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "data"
DEFAULT_OUTPUT_DIR = (
    WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "analysis" / "official_qa_results"
)
METHODS = ("official_qa", "qatest", "qatest_style", "qatest_adapted")


def load_official_questions(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        questions = payload.get("questions")
    else:
        questions = payload
    if not isinstance(questions, list):
        raise ValueError("Official QA file must contain a questions list")
    return questions


def index_official_questions(questions: Iterable[Mapping]) -> Dict[str, List[dict]]:
    indexed = defaultdict(list)
    per_sample_index = defaultdict(int)
    for raw_question in questions:
        sample_token = str(raw_question.get("sample_token") or "")
        if not sample_token:
            continue
        question = {
            key: raw_question[key]
            for key in (
                "split",
                "sample_token",
                "question",
                "answer",
                "num_hop",
                "template_type",
            )
            if key in raw_question
        }
        question["official_question_id"] = (
            f"{sample_token}:{per_sample_index[sample_token]}"
        )
        per_sample_index[sample_token] += 1
        indexed[sample_token].append(question)
    return dict(indexed)


def _stable_seed(text: str, seed: int, cycle: int) -> int:
    digest = hashlib.sha256(f"{seed}|{cycle}|{text}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _double_question_mark(text: str) -> str:
    return text + "?" if text.endswith("?") else text + "??"


def _contract_or_case_question(text: str) -> str:
    replacements = (
        ("What is ", "What's "),
        ("Who is ", "Who's "),
        ("Where is ", "Where's "),
        ("How is ", "How's "),
        ("There is ", "There's "),
    )
    for source, target in replacements:
        if text.startswith(source):
            return target + text[len(source) :]
    return text[:1].lower() + text[1:]


def _swap_internal_letters(text: str, rng: random.Random) -> str:
    words = list(re.finditer(r"[A-Za-z]{4,}", text))
    if not words:
        return _double_question_mark(text)
    match = rng.choice(words)
    word = match.group(0)
    position = rng.randrange(1, len(word) - 1)
    chars = list(word)
    chars[position - 1], chars[position] = chars[position], chars[position - 1]
    return text[: match.start()] + "".join(chars) + text[match.end() :]


def _edit_internal_character(
    text: str, rng: random.Random, operation: str
) -> str:
    words = list(re.finditer(r"[A-Za-z]{4,}", text))
    if not words:
        return _double_question_mark(text)
    match = rng.choice(words)
    word = match.group(0)
    position = rng.randrange(1, len(word) - 1)
    if operation == "delete":
        mutated = word[:position] + word[position + 1 :]
    elif operation == "duplicate":
        mutated = word[:position] + word[position] + word[position:]
    else:
        neighbors = {
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
        }
        original = word[position]
        replacement = neighbors.get(original.lower(), "x")
        if original.isupper():
            replacement = replacement.upper()
        mutated = word[:position] + replacement + word[position + 1 :]
    return text[: match.start()] + mutated + text[match.end() :]


def _double_whitespace(text: str, rng: random.Random) -> str:
    spaces = [index for index, char in enumerate(text) if char == " "]
    if not spaces:
        return _double_question_mark(text)
    position = rng.choice(spaces)
    return text[:position] + "  " + text[position + 1 :]


def mutate_qatest_question(text: str, seed: int, cycle: int) -> Tuple[str, str]:
    rng = random.Random(_stable_seed(text, seed, cycle))
    operators = (
        ("double_question_mark", lambda value: _double_question_mark(value)),
        ("contraction_or_case", lambda value: _contract_or_case_question(value)),
        ("internal_letter_swap", lambda value: _swap_internal_letters(value, rng)),
        (
            "character_deletion",
            lambda value: _edit_internal_character(value, rng, "delete"),
        ),
        (
            "character_duplication",
            lambda value: _edit_internal_character(value, rng, "duplicate"),
        ),
        (
            "keyboard_substitution",
            lambda value: _edit_internal_character(value, rng, "keyboard"),
        ),
        ("whitespace_perturbation", lambda value: _double_whitespace(value, rng)),
    )
    operator_name, operator = operators[cycle % len(operators)]
    mutated = operator(text)
    if mutated == text:
        operator_name = "double_question_mark"
        mutated = _double_question_mark(text)
    return mutated, operator_name


def _ordered_seeds(
    frame_samples: Sequence[Tuple[str, str]],
    questions_by_sample: Mapping[str, Sequence[dict]],
) -> List[Tuple[str, dict]]:
    seeds = []
    for scene_frame, sample_token in frame_samples:
        for question in questions_by_sample.get(sample_token, ()):
            seeds.append((scene_frame, dict(question)))
    return seeds


def build_official_suite(
    *,
    method: str,
    frame_samples: Sequence[Tuple[str, str]],
    questions_by_sample: Mapping[str, Sequence[dict]],
    generation_budget: int,
    seed: int,
) -> List[dict]:
    suite, _ = build_official_suite_with_stats(
        method=method,
        frame_samples=frame_samples,
        questions_by_sample=questions_by_sample,
        generation_budget=generation_budget,
        seed=seed,
    )
    return suite


def build_official_suite_with_stats(
    *,
    method: str,
    frame_samples: Sequence[Tuple[str, str]],
    questions_by_sample: Mapping[str, Sequence[dict]],
    generation_budget: int,
    seed: int,
) -> Tuple[List[dict], dict]:
    if method not in METHODS:
        raise ValueError(f"Unknown official-QA method: {method}")
    seeds = _ordered_seeds(frame_samples, questions_by_sample)
    if not seeds or generation_budget <= 0:
        return [], {"accepted_questions": 0}
    normalized_method = "qatest_style" if method == "qatest" else method

    if normalized_method == "qatest_adapted":
        adapted_seeds = [
            QATestSeed(
                source_question_id=source["official_question_id"],
                source_sample_token=source["sample_token"],
                scene_frame=scene_frame,
                question=source["question"],
                answer=str(source.get("answer") or ""),
                template_type=str(source.get("template_type") or ""),
                num_hop=int(source.get("num_hop") or 0),
            )
            for scene_frame, source in seeds
        ]
        generated = QATestGenerator(seed=seed).generate(
            adapted_seeds,
            generation_budget=generation_budget,
        )
        suite = []
        for generated_question in generated.records:
            question = {
                key: generated_question[key]
                for key in (
                    "question",
                    "answer",
                    "template_type",
                    "num_hop",
                    "original_question",
                    "qatest_parent_question",
                    "qatest_iteration",
                    "qatest_mutated",
                    "mutation_operator",
                    "qatest_rouge1_f1",
                    "qatest_gram_gain",
                    "qatest_sentence_probability",
                )
            }
            suite.append(
                annotate_provenance(
                    question,
                    layer=EXTERNAL_LAYER,
                    method="qatest_adapted",
                    question_source="nuscenes_qa",
                    source_question_id=generated_question[
                        "source_question_id"
                    ],
                    source_sample_token=generated_question[
                        "source_sample_token"
                    ],
                    generation_adapter="qatest_adapted_portable",
                    uses_coverage_feedback=False,
                    vlm_call_cost=1,
                    scene_frame=generated_question["scene_frame"],
                    global_budget_index=len(suite) + 1,
                )
            )
        return suite, generated.statistics

    suite = []
    seen_question_text = set()
    cycle = 0
    stalled_cycles = 0
    while (
        len(suite) < generation_budget
        and stalled_cycles < len(seeds) + 10
    ):
        cycle_seeds = list(seeds)
        if normalized_method == "qatest_style":
            random.Random(seed + cycle).shuffle(cycle_seeds)
        before_cycle = len(suite)
        for scene_frame, source in cycle_seeds:
            if len(suite) >= generation_budget:
                break
            question = {
                key: source[key]
                for key in (
                    "split",
                    "sample_token",
                    "question",
                    "answer",
                    "num_hop",
                    "template_type",
                )
                if key in source
            }
            adapter = "official_nuscenes_qa"
            if normalized_method == "qatest_style":
                original_text = question["question"]
                mutated_text, operator = mutate_qatest_question(
                    original_text, seed, cycle
                )
                question.update(
                    {
                        "question": mutated_text,
                        "original_question": original_text,
                        "qatest_mutated": True,
                        "mutation_operator": operator,
                    }
                )
                adapter = "qatest_local_adapter"
                if question["question"] in seen_question_text:
                    continue

            record = annotate_provenance(
                question,
                layer=EXTERNAL_LAYER,
                method=normalized_method,
                question_source="nuscenes_qa",
                source_question_id=source["official_question_id"],
                source_sample_token=source["sample_token"],
                generation_adapter=adapter,
                uses_coverage_feedback=False,
                vlm_call_cost=1,
                scene_frame=scene_frame,
                global_budget_index=len(suite) + 1,
            )
            suite.append(record)
            seen_question_text.add(question["question"])
        if normalized_method == "official_qa":
            break
        if len(suite) == before_cycle:
            stalled_cycles += 1
        else:
            stalled_cycles = 0
        cycle += 1
    return suite, {
        "accepted_questions": len(suite),
        "generation_adapter": (
            "official_nuscenes_qa"
            if normalized_method == "official_qa"
            else "qatest_local_adapter"
        ),
    }


def resolve_frame_samples(
    frame_cache: Path,
    outputs_root: Path,
    dataroot: Path,
    frame_pool_size: int,
) -> List[Tuple[str, str]]:
    with frame_cache.open("r", encoding="utf-8") as handle:
        cached_frames = json.load(handle)
    resolved = []
    for item in cached_frames[:frame_pool_size]:
        scene_frame = item["scene_frame"]
        graph_path = (
            outputs_root
            / scene_frame
            / "offline"
            / "scene_graphs"
            / f"{scene_frame}_filtered_scene_graph.json"
        )
        with graph_path.open("r", encoding="utf-8") as handle:
            scene_graph = json.load(handle)
        sample_token = get_sample_token(scene_graph, dataroot)
        if not sample_token:
            raise ValueError(f"Unable to resolve sample token for {scene_frame}")
        resolved.append((scene_frame, sample_token))
    return resolved


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build independent official NuScenes-QA and QATest suites."
    )
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    parser.add_argument("--generation-budget", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--frame-pool-size", type=int, default=100)
    parser.add_argument("--questions-path", type=Path, default=DEFAULT_QUESTIONS_PATH)
    parser.add_argument("--frame-cache", type=Path, default=DEFAULT_FRAME_CACHE)
    parser.add_argument("--outputs-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    parser.add_argument("--dataroot", type=Path, default=DEFAULT_DATAROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    questions_by_sample = index_official_questions(
        load_official_questions(args.questions_path)
    )
    frame_samples = resolve_frame_samples(
        args.frame_cache,
        args.outputs_root,
        args.dataroot,
        args.frame_pool_size,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for method in args.methods:
        suite, statistics = build_official_suite_with_stats(
            method=method,
            frame_samples=frame_samples,
            questions_by_sample=questions_by_sample,
            generation_budget=args.generation_budget,
            seed=args.seed,
        )
        output_path = args.output_dir / f"{method}_suite.jsonl"
        _write_jsonl(output_path, suite)
        (args.output_dir / f"{method}_generation_stats.json").write_text(
            json.dumps(statistics, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[official-qa] {method}: {len(suite)} questions -> {output_path}")
        if len(suite) < args.generation_budget:
            print(
                f"[official-qa] WARNING: {method} produced {len(suite)} unique "
                "questions for requested generation budget "
                f"{args.generation_budget}."
            )


if __name__ == "__main__":
    main()
