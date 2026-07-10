import argparse
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


LABELS = ("A", "B", "C", "D")
DIRECTION_OPTIONS = (
    "front",
    "front left",
    "left",
    "back left",
    "back",
    "back right",
    "right",
    "front right",
)
NUSCENES_DIRECTION_OPTIONS = (
    "front",
    "front left",
    "back left",
    "back",
    "back right",
    "front right",
)
STATUS_OPTIONS = ("moving", "parked", "stopped")
TYPE_OPTIONS = (
    "car",
    "truck",
    "bus",
    "pedestrian",
    "bicycle",
    "motorcycle",
    "traffic cone",
    "barrier",
    "trailer",
    "construction vehicle",
)
BOOLEAN_OPTIONS = ("yes", "no")
DEFAULT_OUTPUTS_ROOT = Path(__file__).resolve().parents[2] / "outputs"
OBJECT_ID_RE = r"(?:ego|[a-zA-Z_]+(?:\s+[a-zA-Z_]+)*\d+)"
OBJECT_TYPE_ALIASES = {
    "car": "car",
    "truck": "truck",
    "bus": "bus",
    "pedestrian": "pedestrian",
    "person": "pedestrian",
    "bicycle": "bicycle",
    "bike": "bicycle",
    "motorcycle": "motorcycle",
    "motorbike": "motorcycle",
    "traffic cone": "traffic_cone",
    "cone": "traffic_cone",
    "barrier": "barrier",
    "trailer": "trailer",
    "construction vehicle": "construction_vehicle",
    "ego": "ego",
}

DIRECTION_DISTRACTORS = {
    "front": ("front left", "front right", "back"),
    "front left": ("front", "left", "back left"),
    "left": ("front left", "back left", "right"),
    "back left": ("back", "left", "back right"),
    "back": ("back left", "back right", "front"),
    "back right": ("back", "right", "back left"),
    "right": ("front right", "back right", "left"),
    "front right": ("front", "right", "back right"),
}
NUSCENES_DIRECTION_DISTRACTORS = {
    "front": ("front left", "front right", "back"),
    "front left": ("front", "back left", "front right"),
    "back left": ("back", "front left", "back right"),
    "back": ("back left", "back right", "front"),
    "back right": ("back", "front right", "back left"),
    "front right": ("front", "back right", "front left"),
}
NUSCENES_DIRECTION_RANGES = {
    "front": "-30° < theta <= 30°",
    "front left": "30° < theta <= 90°",
    "front right": "-90° < theta <= -30°",
    "back left": "90° < theta <= 150°",
    "back right": "-150° < theta <= -90°",
    "back": "otherwise",
}
DIRECTION_DISPLAY_RANGES = {
    **NUSCENES_DIRECTION_RANGES,
    "left": "around +90°",
    "right": "around -90°",
}


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def trailing_number_prefix(value: str) -> str:
    match = re.fullmatch(r"([a-zA-Z_ ]+?)(\d+)", value.strip())
    return match.group(1).strip().replace(" ", "_").lower() if match else ""


def requested_object_prefix(question: str) -> str:
    text = re.sub(r"\s+", " ", question.lower().replace("_", " ")).strip()
    type_pattern = "|".join(
        re.escape(key) for key in sorted(OBJECT_TYPE_ALIASES, key=len, reverse=True)
    )
    patterns = (
        rf"\bthere is an? ({type_pattern})\b",
        rf"\bwhich ({type_pattern})\b",
        rf"\bwhat ({type_pattern})\b",
        rf"\bidentify the ({type_pattern})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return OBJECT_TYPE_ALIASES[match.group(1)]
    return ""


def metadata_key(row: dict) -> tuple[str, str]:
    scene_frame = str(row.get("scene_frame") or "")
    qid = str(
        row.get("source_question_id")
        or row.get("question_id")
        or row.get("id")
        or ""
    )
    return scene_frame, qid


def load_metadata_index(path: Path) -> dict[tuple[str, str], dict]:
    index = {}
    for row in iter_jsonl(path):
        key = metadata_key(row)
        if key[0] and key[1]:
            index[key] = row
    return index


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            count += 1
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return count


def clean_answer(answer: object) -> str:
    if isinstance(answer, bool):
        text = "true" if answer else "false"
    else:
        text = str(answer if answer is not None else "").strip().lower()
    if text == "true":
        text = "yes"
    elif text == "false":
        text = "no"
    text = re.sub(r"\s+", " ", text)
    return text


def is_int_answer(answer: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", answer))


def family_key(row: dict) -> str:
    return str(row.get("family") or row.get("template_id") or "unknown")


def answer_pool_key(row: dict) -> str:
    answer = clean_answer(row.get("answer"))
    family = family_key(row)
    if answer in ("yes", "no"):
        return "boolean"
    if is_int_answer(answer) or "count" in family or "number" in family:
        return "count"
    if answer in STATUS_OPTIONS or "status" in family:
        return "status"
    if answer in TYPE_OPTIONS or "type" in family:
        return "type"
    if (
        answer in DIRECTION_OPTIONS
        or "direction" in family
        or family == "viewpoint_transfer"
    ):
        return "direction"
    return family


def collect_answer_pools(rows: list[dict]) -> dict[str, list[str]]:
    pools: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        answer = clean_answer(row.get("answer"))
        if answer:
            pools[answer_pool_key(row)].add(answer)
            pools["global"].add(answer)
            prefix = trailing_number_prefix(answer)
            if prefix:
                pools[f"object_prefix:{prefix}"].add(answer)
    return {key: sorted(values) for key, values in pools.items()}


def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        clean = clean_answer(value)
        if clean and clean not in seen:
            seen.add(clean)
            output.append(clean)
    return output


def numeric_options(answer: str) -> list[str]:
    value = int(answer)
    candidates = [value, value - 1, value + 1, value + 2, value - 2, value + 3]
    return [str(item) for item in candidates if item >= 0]


def extract_distance_chain_candidates(question: str) -> list[str]:
    patterns = (
        rf"\bnearer to,\s*({OBJECT_ID_RE})\s+or\s+({OBJECT_ID_RE})\??",
        rf"\bcloser to\s+({OBJECT_ID_RE})\s+or\s+to\s+({OBJECT_ID_RE})\??",
        rf"\bcloser to\s+({OBJECT_ID_RE})\s+or\s+({OBJECT_ID_RE})\??",
        rf"\bbetween\s+({OBJECT_ID_RE})\s+and\s+({OBJECT_ID_RE}),",
        rf"\bof\s+({OBJECT_ID_RE})\s+and\s+({OBJECT_ID_RE}),",
    )
    text = question.lower()
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return dedupe_keep_order(match.groups())
    return []


def scene_graph_path(outputs_root: Path, scene_frame: str) -> Path:
    return (
        outputs_root
        / scene_frame
        / "offline"
        / "scene_graphs"
        / f"{scene_frame}_filtered_scene_graph.json"
    )


def discretize_direction_nuscenes(angle_deg: float) -> str:
    # Match the NuScenes-QA six-way direction bins.
    if -30 < angle_deg <= 30:
        return "front"
    if 30 < angle_deg <= 90:
        return "front left"
    if -90 < angle_deg <= -30:
        return "front right"
    if 90 < angle_deg <= 150:
        return "back left"
    if -150 < angle_deg <= -90:
        return "back right"
    return "back"


def viewpoint_path_pattern(row: dict) -> str:
    path_pattern = str(row.get("path_pattern") or "")
    if path_pattern:
        return path_pattern
    for item in row.get("l2_items") or []:
        value = str(item or "")
        if value.count("|") == 2:
            return value
    return ""


def viewpoint_relative_angle(row: dict, outputs_root: Path) -> float | None:
    path_pattern = viewpoint_path_pattern(row)
    parts = path_pattern.split("|")
    if len(parts) != 3:
        return None
    scene_frame = str(row.get("scene_frame") or "")
    if not scene_frame:
        return None
    sg_path = scene_graph_path(outputs_root, scene_frame)
    if not sg_path.exists():
        return None
    scene_graph = json.loads(sg_path.read_text(encoding="utf-8"))
    nodes = {
        str(node.get("unique_id") or node.get("id")): node
        for node in (scene_graph.get("nodes") or scene_graph.get("objects") or [])
    }
    try:
        origin, facing, target = (nodes[part] for part in parts)
        ox = float(origin["translation"]["x"])
        oy = float(origin["translation"]["y"])
        fx = float(facing["translation"]["x"]) - ox
        fy = float(facing["translation"]["y"]) - oy
        tx = float(target["translation"]["x"]) - ox
        ty = float(target["translation"]["y"]) - oy
    except Exception:
        return None
    if (fx == 0 and fy == 0) or (tx == 0 and ty == 0):
        return None
    dot = fx * tx + fy * ty
    cross = fx * ty - fy * tx
    return math.degrees(math.atan2(cross, dot))


def viewpoint_direction_nuscenes(row: dict, outputs_root: Path) -> str:
    angle = viewpoint_relative_angle(row, outputs_root)
    return discretize_direction_nuscenes(angle) if angle is not None else ""


def viewpoint_choice_question(row: dict) -> str:
    path_pattern = viewpoint_path_pattern(row)
    parts = path_pattern.split("|")
    if len(parts) == 3 and all(parts):
        origin, facing, target = parts
        return f"From {origin}, facing {facing}, where is {target} relative to you?"
    return str(row.get("question") or row.get("prompt") or "")


def base_candidates(row: dict, pools: dict[str, list[str]]) -> list[str]:
    answer = clean_answer(row.get("answer"))
    pool_key = answer_pool_key(row)
    if pool_key == "direction":
        return [answer, *DIRECTION_DISTRACTORS.get(answer, ()), *DIRECTION_OPTIONS]
    if pool_key == "status":
        return [answer, *STATUS_OPTIONS]
    if pool_key == "type":
        return [answer, *TYPE_OPTIONS]
    if pool_key == "boolean":
        return [answer, *BOOLEAN_OPTIONS]
    if pool_key == "count" and is_int_answer(answer):
        return numeric_options(answer)
    prefix = trailing_number_prefix(answer)
    if prefix:
        return [answer, *pools.get(f"object_prefix:{prefix}", [])]
    return [answer, *pools.get(pool_key, []), *pools.get("global", [])]


def choose_options(
    row: dict,
    pools: dict[str, list[str]],
    rng: random.Random,
    outputs_root: Path,
) -> list[str]:
    answer = clean_answer(row.get("answer"))
    if family_key(row) == "viewpoint_transfer":
        answer = viewpoint_direction_nuscenes(row, outputs_root)
        row["answer"] = answer
        row["answer_type"] = "direction"
        row["choice_answer_resolution"] = "viewpoint_transfer_nuscenes_6way"
    if not answer:
        raise ValueError("Cannot build choices for a row with an empty answer")
    if answer in ("yes", "no"):
        return [answer, "no" if answer == "yes" else "yes"]
    if family_key(row) == "viewpoint_transfer":
        candidates = dedupe_keep_order(
            [
                answer,
                *NUSCENES_DIRECTION_DISTRACTORS.get(answer, ()),
                *NUSCENES_DIRECTION_OPTIONS,
            ]
        )
        distractors = [item for item in candidates if item != answer]
        rng.shuffle(distractors)
        options = [answer, *distractors[:3]]
        rng.shuffle(options)
        return options
    if family_key(row) == "distance_chain":
        question = str(row.get("question") or row.get("prompt") or "")
        candidates = extract_distance_chain_candidates(question)
        if answer not in candidates:
            raise ValueError(
                "Cannot align distance_chain answer with question candidates"
            )
        return candidates

    prefix = trailing_number_prefix(answer)
    if prefix:
        question = str(row.get("question") or row.get("prompt") or "")
        requested_prefix = requested_object_prefix(question)
        if requested_prefix and requested_prefix != prefix:
            raise ValueError(
                "Question asks for "
                f"{requested_prefix}, but answer is {answer}"
            )
        candidate_prefix = requested_prefix or prefix
        candidates = dedupe_keep_order(
            [answer, *pools.get(f"object_prefix:{candidate_prefix}", [])]
        )
        distractors = [item for item in candidates if item != answer]
        if not distractors:
            raise ValueError(
                f"Cannot build type-consistent object choices for {answer}"
            )
        rng.shuffle(distractors)
        options = [answer, *distractors[:3]]
        rng.shuffle(options)
        return options
    if answer == "ego":
        raise ValueError(
            "Cannot build fair multiple-choice options for unique ego answer"
        )

    pool_key = answer_pool_key(row)
    candidates = dedupe_keep_order(base_candidates(row, pools))
    distractors = [item for item in candidates if item != answer]
    rng.shuffle(distractors)
    options = [answer, *distractors[:3]]
    if len(options) < 4 and pool_key not in {"status"}:
        fillers = [item for item in pools.get("global", []) if item not in options]
        rng.shuffle(fillers)
        options.extend(fillers[: 4 - len(options)])
    if len(options) < 4 and pool_key not in {"status"}:
        options.extend([f"none-{idx}" for idx in range(4 - len(options))])
    options = options[:4]
    rng.shuffle(options)
    return options


def direction_instruction() -> str:
    return (
        "Use the NuScenes-QA direction convention. Theta is measured relative to "
        "the current facing/reference direction: 0° means straight ahead from the "
        "reference object along the stated facing/front direction; positive angles "
        "rotate to the left. "
        "front if -30° < theta <= 30°; "
        "front left if 30° < theta <= 90°; front right if -90° < theta <= -30°; "
        "back left if 90° < theta <= 150°; back right if -150° < theta <= -90°; "
        "back otherwise."
    )


def precise_direction_instruction() -> str:
    return (
        direction_instruction()
        + " Select the most precise direction label, not only the coarse left/right side."
    )


def build_choice_question_text(
    question: str,
    choices: list[dict],
    *,
    include_direction_instruction: bool = False,
    precise_direction: bool = False,
) -> str:
    option_lines = "\n".join(
        f"{item['label']}. {item['text']}" for item in choices
    )
    instruction = ""
    if include_direction_instruction:
        instruction = (
            precise_direction_instruction() if precise_direction else direction_instruction()
        ) + "\n"
    return (
        f"{question}\n\n"
        f"{instruction}"
        "Choose the best answer from the options below. "
        "Answer with the option letter and option text.\n"
        f"{option_lines}"
    )


def annotate_direction_terms(text: str) -> str:
    directions = sorted(DIRECTION_DISPLAY_RANGES, key=len, reverse=True)
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(direction) for direction in directions) + r")\b(?!\s*\()",
        flags=re.IGNORECASE,
    )

    def replace(match: re.Match) -> str:
        direction = match.group(1).lower()
        angle_range = DIRECTION_DISPLAY_RANGES[direction]
        return f"{direction} ({angle_range})"

    return pattern.sub(replace, str(text or ""))


def has_direction_terms(text: str) -> bool:
    value = str(text or "")
    return any(
        re.search(rf"\b{re.escape(direction)}\b", value, flags=re.IGNORECASE)
        for direction in DIRECTION_DISPLAY_RANGES
    )


def choice_display_text(answer: str, *, direction_choice: bool = False) -> str:
    if direction_choice:
        angle_range = DIRECTION_DISPLAY_RANGES.get(answer)
        if angle_range:
            return f"{answer} ({angle_range})"
    return answer


def convert_row(
    row: dict,
    pools: dict[str, list[str]],
    rng: random.Random,
    outputs_root: Path,
) -> dict:
    option_texts = choose_options(row, pools, rng, outputs_root)
    answer = clean_answer(row.get("answer"))
    is_viewpoint_transfer = family_key(row) == "viewpoint_transfer"
    is_direction_choice = answer_pool_key(row) == "direction"
    choices = [
        {
            "label": label,
            "text": choice_display_text(
                text,
                direction_choice=is_direction_choice,
            ),
            "canonical_text": text,
        }
        for label, text in zip(LABELS, option_texts)
    ]
    correct = next(item for item in choices if item["canonical_text"] == answer)

    converted = dict(row)
    source_question = str(row.get("question") or row.get("prompt") or "")
    choice_question = (
        viewpoint_choice_question(row)
        if is_viewpoint_transfer
        else source_question
    )
    question_has_direction_terms = has_direction_terms(choice_question)
    if question_has_direction_terms:
        choice_question = annotate_direction_terms(choice_question)
    converted["question"] = build_choice_question_text(
        choice_question,
        choices,
        include_direction_instruction=is_direction_choice or question_has_direction_terms,
        precise_direction=is_viewpoint_transfer,
    )
    converted["prompt"] = converted["question"]
    converted["answer"] = answer
    converted["choices"] = choices
    converted["choice_answer_label"] = correct["label"]
    converted["choice_answer_text"] = correct["text"]
    converted["choice_answer_canonical_text"] = correct["canonical_text"]
    converted["question_format"] = f"multiple_choice_{len(choices)}way"
    converted["source_question_format"] = "strict_open_qa"
    converted["source_question"] = source_question
    return converted


def parse_source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Source must be NAME=PATH")
    name, path = value.split("=", 1)
    if not name:
        raise argparse.ArgumentTypeError("Source name cannot be empty")
    return name, Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build four-option multiple-choice RQ1 suites from frozen raw QA rows."
    )
    parser.add_argument("--source", action="append", type=parse_source, required=True)
    parser.add_argument("--metadata-source", action="append", type=parse_source, default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--outputs-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    parser.add_argument("--seed", type=int, default=20260707)
    args = parser.parse_args()
    metadata = {
        name: load_metadata_index(path)
        for name, path in args.metadata_source
    }

    manifest = {
        "format": "multiple_choice_variable_by_answer_type",
        "seed": args.seed,
        "sources": {},
        "answer_banks": {
            "direction": list(DIRECTION_OPTIONS),
            "status": list(STATUS_OPTIONS),
            "type": list(TYPE_OPTIONS),
            "boolean": list(BOOLEAN_OPTIONS),
            "nuscenes_direction": list(NUSCENES_DIRECTION_OPTIONS),
        },
    }

    for source_index, (name, path) in enumerate(args.source):
        meta_index = metadata.get(name, {})
        rows = []
        for raw_row in iter_jsonl(path):
            row = dict(meta_index.get(metadata_key(raw_row), {}))
            row.update(raw_row)
            rows.append(row)
        pools = collect_answer_pools(rows)
        rng = random.Random(f"{args.seed}:{name}:{source_index}")
        converted = []
        rejected = []
        for index, row in enumerate(rows, start=1):
            try:
                converted.append(convert_row(row, pools, rng, args.outputs_root))
            except ValueError as exc:
                rejected.append(
                    {
                        "index": index,
                        "reason": str(exc),
                        "question": row.get("question") or row.get("prompt") or "",
                        "answer": row.get("answer", ""),
                    }
                )
        output_path = args.output_dir / f"{name}_choice_suite.jsonl"
        count = write_jsonl(output_path, converted)
        rejected_path = args.output_dir / f"{name}_choice_rejected.jsonl"
        rejected_count = write_jsonl(rejected_path, rejected)
        family_counts = Counter(family_key(row) for row in converted)
        manifest["sources"][name] = {
            "input": str(path),
            "output": str(output_path),
            "rejected_output": str(rejected_path),
            "rows": count,
            "rejected_rows": rejected_count,
            "families": dict(sorted(family_counts.items())),
            "pool_sizes": {key: len(value) for key, value in pools.items()},
        }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "choice_suite_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
