import hashlib
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import ijson
from PIL import Image

from config import (
    DATA_NEW_ROOT,
    DATAROOT,
    OUTPUTS_ROOT,
    SCRATCH_ROOT,
    TEST_SCENES,
    WORKSPACE_ROOT,
)


RQ1_MODULE_DIR = DATA_NEW_ROOT / "analysis" / "rq1_error_detection"
if str(RQ1_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(RQ1_MODULE_DIR))

from build_choice_suites import (  # noqa: E402
    BOOLEAN_OPTIONS,
    DIRECTION_OPTIONS,
    NUSCENES_DIRECTION_OPTIONS,
    LABELS,
    clean_answer,
    collect_answer_pools,
    convert_row,
    precise_direction_instruction,
    trailing_number_prefix,
    viewpoint_choice_question,
)
from build_l0_l1_structural_suites import (  # noqa: E402
    annotate_suite,
    build_frame_inputs,
)
from build_l2_family_suites import L2_FAMILIES, load_family_frames  # noqa: E402
from fixed_budget_experiment import (  # noqa: E402
    FrameInput,
    build_frame_question_counts,
    redistribute_frame_question_counts,
    run_method_presampled_frames,
)
from evaluator import (  # noqa: E402
    CAM_ORDER,
    _ensure_projected_visibility,
    _find_metadata_file,
    cache_sample_camera_records,
    get_sample_camera_files,
    get_sample_token,
)
from official_qa_experiment import (  # noqa: E402
    index_official_questions,
    load_official_questions,
)


OBJECT_ID_RE = re.compile(r"^[a-zA-Z_ ]+\d+$")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[Mapping]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            count += 1
    return count


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_scene_frame(row: Mapping) -> str:
    sf = str(row.get("scene_frame") or "")
    if sf:
        return sf
    scene = str(row.get("scene_name") or "")
    frame = row.get("frame_idx")
    return f"{scene}_frame{frame}" if scene and frame is not None else ""


def row_source_id(row: Mapping, index: int = 0) -> str:
    return str(
        row.get("source_question_id")
        or row.get("question_id")
        or row.get("id")
        or f"row-{index}"
    )


def family_name(row: Mapping) -> str:
    value = str(
        row.get("family")
        or row.get("l2_family")
        or row.get("template_id")
        or row.get("template_type")
        or "unknown"
    ).lower()
    if value.startswith("l0_"):
        return "l0"
    if value.startswith("l1_"):
        return "l1"
    return value


def frame_family_distribution(rows: Iterable[Mapping]) -> Counter:
    return Counter((family_name(row), row_scene_frame(row)) for row in rows)


def scene_graph_path(outputs_root: Path, scene_frame: str) -> Path:
    return (
        outputs_root
        / scene_frame
        / "offline"
        / "scene_graphs"
        / f"{scene_frame}_filtered_scene_graph.json"
    )


def load_scene_graph(outputs_root: Path, scene_frame: str) -> dict:
    return read_json(scene_graph_path(outputs_root, scene_frame))


def project_visible_ids(scene_graph: Mapping, dataroot: Path) -> set[str]:
    sample_token = get_sample_token(scene_graph, dataroot)
    if not sample_token:
        return set()
    camera_files = get_sample_camera_files(sample_token, dataroot)
    image_sizes = {}
    for channel in CAM_ORDER:
        image_path = camera_files.get(channel)
        if image_path and image_path.exists():
            with Image.open(image_path) as image:
                image_sizes[channel] = image.size
    projected = _ensure_projected_visibility(
        scene_graph,
        dataroot,
        sample_token,
        image_sizes,
    )
    visible = set()
    for node in projected.get("nodes") or projected.get("objects") or []:
        node_id = str(node.get("unique_id") or node.get("id") or "")
        if not node_id or node_id == "ego":
            continue
        if any(
            value.get("visible") and value.get("bbox2d")
            for value in (node.get("visibility") or {}).values()
        ):
            visible.add(node_id)
    return visible


def preload_camera_records(sample_tokens: Iterable[str], dataroot: Path) -> None:
    wanted = {str(token) for token in sample_tokens if token}
    if not wanted:
        return
    cache_path = SCRATCH_ROOT / "cache" / "sample_camera_records.json"
    persistent_records: dict[str, dict[str, dict]] = {}
    if cache_path.exists():
        cached = read_json(cache_path)
        if cached.get("dataroot") == str(dataroot.resolve()):
            persistent_records = cached.get("records_by_sample") or {}
    ready = {
        token: persistent_records[token]
        for token in wanted
        if len(persistent_records.get(token) or {}) == len(CAM_ORDER)
    }
    if ready:
        cache_sample_camera_records(dataroot, ready)
        wanted -= set(ready)
    if not wanted:
        return
    sample_data_file = _find_metadata_file(dataroot, "sample_data.json")
    if not sample_data_file:
        raise FileNotFoundError("Could not locate nuScenes sample_data.json")
    records_by_sample: dict[str, dict[str, dict]] = defaultdict(dict)
    with sample_data_file.open("rb") as handle:
        for record in ijson.items(handle, "item"):
            sample_token = str(record.get("sample_token") or "")
            if sample_token not in wanted or not record.get("is_key_frame", True):
                continue
            filename = str(record.get("filename") or "").replace("\\", "/")
            for channel in CAM_ORDER:
                if f"/{channel}/" in filename:
                    records_by_sample[sample_token][channel] = record
                    break
            if len(records_by_sample[sample_token]) == len(CAM_ORDER):
                wanted.remove(sample_token)
            if not wanted:
                break
    if wanted:
        raise ValueError(
            f"Missing six-camera metadata for {len(wanted)} samples: "
            f"{sorted(wanted)[:3]}"
        )
    persistent_records.update(records_by_sample)
    write_json(
        cache_path,
        {
            "schema_version": "rq3_sample_camera_records_v1",
            "dataroot": str(dataroot.resolve()),
            "records_by_sample": persistent_records,
        },
    )
    cache_sample_camera_records(dataroot, records_by_sample)


def required_visible_ids(row: Mapping) -> set[str]:
    required: set[str] = set()
    answer = str(row.get("answer") or "").strip().lower()
    if OBJECT_ID_RE.fullmatch(answer):
        required.add(answer)
    for key in ("target_object", "source_object"):
        value = str(row.get(key) or "")
        if value and value != "ego":
            required.add(value)
    if family_name(row) in {
        "converge",
        "direction_chain",
        "distance_chain",
        "viewpoint_transfer",
    }:
        required.update(
            str(value)
            for value in row.get("coverage_l0") or row.get("footprint_nodes") or []
            if value and str(value) != "ego"
        )
    return required


def choice_candidate_is_usable(row: Mapping, visible_ids: set[str]) -> bool:
    answer = clean_answer(row.get("answer"))
    prefix = trailing_number_prefix(answer)
    if not prefix:
        return True
    same_type = [value for value in visible_ids if trailing_number_prefix(value) == prefix]
    return len(same_type) >= 4


def filter_frame_inputs_by_visibility(
    frames: Sequence[FrameInput], visible_ids_by_frame: Mapping[str, set[str]]
) -> list[FrameInput]:
    filtered = []
    for frame in frames:
        visible_ids = visible_ids_by_frame[frame.scene_frame]
        questions = []
        seen_text = set()
        for question in frame.questions:
            text_key = str(question.get("question") or "").strip().lower()
            if (
                not text_key
                or text_key in seen_text
                or not _basic_valid(question)
                or not required_visible_ids(question) <= visible_ids
                or not choice_candidate_is_usable(question, visible_ids)
            ):
                continue
            seen_text.add(text_key)
            questions.append(question)
        filtered.append(
            FrameInput(
                scene_frame=frame.scene_frame,
                questions=questions,
                total_l0=frame.total_l0,
                total_l1=frame.total_l1,
                total_l2=frame.total_l2,
            )
        )
    return filtered


def select_common_frames(
    frame_rows: Sequence[Mapping], frame_pool_size: int, seed: int
) -> list[dict]:
    by_scene: dict[str, list[dict]] = defaultdict(list)
    for row in frame_rows:
        by_scene[str(row["scene_name"])].append(dict(row))
    rng = random.Random(seed)
    scenes = sorted(by_scene)
    rng.shuffle(scenes)
    for scene in scenes:
        by_scene[scene].sort(key=lambda item: item["scene_frame"])
        rng.shuffle(by_scene[scene])
    selected = []
    round_index = 0
    while len(selected) < frame_pool_size:
        added = 0
        for scene in scenes:
            rows = by_scene[scene]
            if round_index < len(rows):
                selected.append(rows[round_index])
                added += 1
                if len(selected) >= frame_pool_size:
                    break
        if not added:
            break
        round_index += 1
    if len(selected) != frame_pool_size:
        raise ValueError(
            f"Requested {frame_pool_size} common frames, found {len(selected)}"
        )
    return selected


def _prepare_structural_row(row: Mapping, family: str, dataset_name: str) -> dict:
    prepared = dict(row)
    sf = row_scene_frame(prepared)
    prepared["scene_frame"] = sf
    prepared["scene_name"] = sf.split("_frame", 1)[0]
    prepared["family"] = family
    prepared["dataset_name"] = dataset_name
    source_id = row_source_id(prepared)
    prepared["source_question_id"] = (
        source_id if source_id.startswith(f"{sf}:") else f"{sf}:{source_id}"
    )
    return prepared


def _basic_valid(row: Mapping) -> bool:
    if not str(row.get("question") or "").strip():
        return False
    answer = clean_answer(row.get("answer"))
    if not answer or answer == "ego":
        return False
    verification = str(row.get("logic_verification") or "")
    if verification and verification not in {
        "IN_MEMORY_VERIFIED",
        "OFFICIAL_DATASET",
    }:
        return False
    return True


def dedupe_and_validate_rows(rows: Iterable[Mapping], expected: int) -> list[dict]:
    output = []
    seen_ids = set()
    seen_text = set()
    rejected = Counter()
    for index, raw in enumerate(rows, start=1):
        row = dict(raw)
        if not _basic_valid(row):
            rejected["invalid"] += 1
            continue
        source_id = row_source_id(row, index)
        key = (row_scene_frame(row), str(row.get("question") or "").strip().lower())
        if source_id in seen_ids:
            rejected["duplicate_id"] += 1
            continue
        if key in seen_text:
            rejected["duplicate_text"] += 1
            continue
        seen_ids.add(source_id)
        seen_text.add(key)
        row["source_question_id"] = source_id
        output.append(row)
        if len(output) == expected:
            break
    if len(output) != expected:
        raise ValueError(
            f"Expected {expected} valid unique rows, found {len(output)}; "
            f"rejected={dict(rejected)}"
        )
    return output


def build_structural_pair(
    frame_rows: Sequence[Mapping],
    quotas: Mapping[str, int],
    outputs_root: Path,
    dataroot: Path,
    seed: int,
    per_frame_candidate_limit: int = 300,
) -> tuple[dict[str, list[dict]], dict]:
    frame_names = [str(row["scene_frame"]) for row in frame_rows]
    datasets = {"advtest": [], "random": []}
    assignment_manifest = {}
    graphs_by_frame = {
        scene_frame: load_scene_graph(outputs_root, scene_frame)
        for scene_frame in frame_names
    }
    preload_camera_records(
        (get_sample_token(graph, dataroot) for graph in graphs_by_frame.values()),
        dataroot,
    )
    visible_ids_by_frame = {
        scene_frame: project_visible_ids(graph, dataroot)
        for scene_frame, graph in graphs_by_frame.items()
    }

    for level in ("l0", "l1"):
        quota = int(quotas.get(level, 0))
        if quota <= 0:
            continue
        frames = build_frame_inputs(frame_names, outputs_root, level)
        frames = filter_frame_inputs_by_visibility(frames, visible_ids_by_frame)
        raw_assignment = build_frame_question_counts(frame_names, quota, seed)
        adjusted = redistribute_frame_question_counts(
            frames, raw_assignment["frame_question_counts"], quota
        )
        assignment_manifest[level] = adjusted
        for dataset_name, selection_method in (
            ("advtest", f"greedy_{level}"),
            ("random", "random"),
        ):
            suite, _ = annotate_suite(
                level=level,
                frames=frames,
                generation_budget=quota,
                seed=seed,
                method=selection_method,
                frame_counts=adjusted["frame_question_counts"],
            )
            suite = [
                _prepare_structural_row(row, level, dataset_name) for row in suite
            ]
            datasets[dataset_name].extend(dedupe_and_validate_rows(suite, quota))

    l2_frames = load_family_frames(
        frame_names,
        outputs_root,
        tuple(L2_FAMILIES),
        per_frame_candidate_limit,
    )
    l2_frames = {
        family: filter_frame_inputs_by_visibility(frames, visible_ids_by_frame)
        for family, frames in l2_frames.items()
    }
    for family in L2_FAMILIES:
        quota = int(quotas.get(family, 0))
        if quota <= 0:
            continue
        frames = l2_frames[family]
        raw_assignment = build_frame_question_counts(frame_names, quota, seed)
        adjusted = redistribute_frame_question_counts(
            frames, raw_assignment["frame_question_counts"], quota
        )
        assignment_manifest[family] = adjusted
        for dataset_name, selection_method in (
            ("advtest", "advtest"),
            ("random", "random"),
        ):
            result = run_method_presampled_frames(
                selection_method,
                frames,
                quota,
                seed,
                adjusted["frame_question_counts"],
            )
            suite = [
                _prepare_structural_row(row, family, dataset_name)
                for row in result["suite"]
            ]
            datasets[dataset_name].extend(dedupe_and_validate_rows(suite, quota))

    expected_total = sum(int(value) for value in quotas.values())
    for dataset_name in datasets:
        datasets[dataset_name] = dedupe_and_validate_rows(
            datasets[dataset_name], expected_total
        )
    if frame_family_distribution(datasets["advtest"]) != frame_family_distribution(
        datasets["random"]
    ):
        raise ValueError(
            "ADVTEST and Random do not have identical per-frame family budgets"
        )
    return datasets, assignment_manifest


def _proportional_allocations(counts: Mapping[str, int], budget: int) -> dict[str, int]:
    total = sum(counts.values())
    if total < budget:
        raise ValueError(f"Only {total} candidates are available for budget {budget}")
    raw = {key: budget * value / total for key, value in counts.items()}
    allocations = {key: math.floor(value) for key, value in raw.items()}
    remainder = budget - sum(allocations.values())
    order = sorted(raw, key=lambda key: (raw[key] - allocations[key], key), reverse=True)
    for key in order[:remainder]:
        allocations[key] += 1
    return allocations


def build_official_dataset(
    frame_rows: Sequence[Mapping],
    questions_path: Path,
    outputs_root: Path,
    dataroot: Path,
    budget: int,
    seed: int,
    per_frame_cap: int = 10,
) -> list[dict]:
    questions_by_sample = index_official_questions(
        load_official_questions(questions_path)
    )
    candidates = []
    for frame_index, frame_row in enumerate(frame_rows, start=1):
        sf = str(frame_row["scene_frame"])
        graph = load_scene_graph(outputs_root, sf)
        sample_token = get_sample_token(graph, dataroot)
        if not sample_token:
            continue
        for question_index, question in enumerate(
            questions_by_sample.get(sample_token, []), start=1
        ):
            row = dict(question)
            row.update(
                {
                    "scene_frame": sf,
                    "scene_name": sf.split("_frame", 1)[0],
                    "family": "official_qa",
                    "dataset_name": "official_qa",
                    "question_source": "nuscenes_qa",
                    "logic_verification": "OFFICIAL_DATASET",
                    "source_question_id": str(
                        question.get("source_question_id")
                        or f"{sample_token}:{question_index}"
                    ),
                }
            )
            candidates.append(row)
        if frame_index % 250 == 0:
            print(
                f"[rq3-data] indexed official QA for {frame_index}/{len(frame_rows)} frames",
                flush=True,
            )

    rng = random.Random(seed)
    strata: dict[str, list[dict]] = defaultdict(list)
    for row in candidates:
        key = f"hop={row.get('num_hop')}|template={row.get('template_type')}"
        strata[key].append(row)
    for rows in strata.values():
        rng.shuffle(rows)
    allocations = _proportional_allocations(
        {key: len(rows) for key, rows in strata.items()}, budget
    )
    selected = []
    selected_by_stratum = Counter()
    frame_counts = Counter()
    leftovers = []
    for key in sorted(strata):
        need = allocations[key]
        for row in strata[key]:
            sf = row["scene_frame"]
            if selected_by_stratum[key] < need:
                if frame_counts[sf] < per_frame_cap:
                    picked = dict(row)
                    picked["_stratum"] = key
                    selected.append(picked)
                    selected_by_stratum[key] += 1
                    frame_counts[sf] += 1
                    continue
            leftovers.append(row)
    if len(selected) < budget:
        rng.shuffle(leftovers)
        for row in leftovers:
            sf = row["scene_frame"]
            if frame_counts[sf] >= per_frame_cap:
                continue
            picked = dict(row)
            picked["_stratum"] = f"hop={row.get('num_hop')}|template={row.get('template_type')}"
            selected.append(picked)
            frame_counts[sf] += 1
            if len(selected) == budget:
                break
    for row in selected:
        row.pop("_stratum", None)
    return dedupe_and_validate_rows(selected, budget)


def _append_status_unknown_option(choice: dict, rng: random.Random) -> dict:
    options = [dict(option) for option in choice.get("choices") or []]
    if len(options) != 3 or clean_answer(choice.get("answer")) not in {
        "moving",
        "parked",
        "stopped",
    }:
        return choice
    values = [str(option["canonical_text"]) for option in options] + ["unknown"]
    rng.shuffle(values)
    choices = [
        {"label": label, "text": value, "canonical_text": value}
        for label, value in zip(LABELS, values)
    ]
    answer = clean_answer(choice.get("answer"))
    correct = next(option for option in choices if option["canonical_text"] == answer)
    marker = "\nChoose the best answer from the options below."
    prefix = str(choice.get("question") or "").split(marker, 1)[0]
    option_lines = "\n".join(
        f"{option['label']}. {option['text']}" for option in choices
    )
    prompt = (
        f"{prefix}{marker} Answer with the option letter and option text.\n"
        f"{option_lines}"
    )
    choice.update(
        {
            "question": prompt,
            "prompt": prompt,
            "choices": choices,
            "choice_answer_label": correct["label"],
            "choice_answer_text": correct["text"],
            "choice_answer_canonical_text": correct["canonical_text"],
            "question_format": "multiple_choice_4way",
        }
    )
    return choice


def convert_to_choice(
    rows: Sequence[Mapping],
    outputs_root: Path,
    seed: int,
    visible_ids_by_frame: Mapping[str, set[str]] | None = None,
) -> list[dict]:
    source_rows = [dict(row) for row in rows]
    pools = collect_answer_pools(source_rows)
    rng = random.Random(seed)
    converted = []
    for row in source_rows:
        row_pools = dict(pools)
        answer = clean_answer(row.get("answer"))
        prefix = trailing_number_prefix(answer)
        sf = row_scene_frame(row)
        if prefix and visible_ids_by_frame is not None:
            same_type = sorted(
                value
                for value in visible_ids_by_frame.get(sf, set())
                if trailing_number_prefix(value) == prefix
            )
            row_pools[f"object_prefix:{prefix}"] = same_type
        choice = convert_row(dict(row), row_pools, rng, outputs_root)
        choice = _append_status_unknown_option(choice, rng)
        options = choice.get("choices") or []
        option_labels = [str(option.get("label") or "") for option in options]
        option_values = [
            clean_answer(option.get("canonical_text") or option.get("text"))
            for option in options
        ]
        correct_value = clean_answer(choice.get("choice_answer_canonical_text"))
        correct_labels = [
            label
            for label, value in zip(option_labels, option_values)
            if value == correct_value
        ]
        if (
            len(options) not in {2, 4}
            or len(option_labels) != len(set(option_labels))
            or len(option_values) != len(set(option_values))
            or len(correct_labels) != 1
            or str(choice.get("choice_answer_label") or "") != correct_labels[0]
        ):
            raise ValueError(
                f"Invalid or ambiguous choice options: {row_source_id(row)}"
            )
        choice["source_question_id"] = row_source_id(row)
        choice["scene_frame"] = row_scene_frame(row)
        choice["scene_name"] = choice["scene_frame"].split("_frame", 1)[0]
        choice["family"] = family_name(row)
        converted.append(choice)
    return converted


def normalize_open_rows(
    source_rows: Sequence[Mapping], choice_rows: Sequence[Mapping]
) -> list[dict]:
    choice_by_source = {row_source_id(row): row for row in choice_rows}
    normalized = []
    for source in source_rows:
        row = dict(source)
        if family_name(row) == "viewpoint_transfer":
            choice = choice_by_source[row_source_id(row)]
            row["question"] = (
                f"{viewpoint_choice_question(row)}\n\n"
                f"{precise_direction_instruction()}"
            )
            row["answer"] = choice["choice_answer_canonical_text"]
            row["answer_type"] = "direction"
            row["answer_resolution"] = "viewpoint_transfer_nuscenes_6way"
        normalized.append(row)
    return normalized


def build_prompt(row: Mapping, question_format: str) -> tuple[str, str]:
    question = str(row.get("question") or row.get("prompt") or "").strip()
    answer = clean_answer(row.get("answer"))
    family = family_name(row)
    if question_format == "choice":
        target = str(row.get("choice_answer_label") or "").strip()
        if not target:
            raise ValueError(f"Choice row lacks answer label: {row_source_id(row)}")
        question = question.replace(
            "Answer with the option letter and option text.",
            "Answer with the option letter only.",
        )
        return question, target
    if answer in BOOLEAN_OPTIONS:
        instruction = "Answer with yes or no only."
    elif OBJECT_ID_RE.fullmatch(answer):
        instruction = "Answer with the exact complete object ID only."
    elif answer in set(DIRECTION_OPTIONS) | set(NUSCENES_DIRECTION_OPTIONS) or (
        "direction" in family or family == "viewpoint_transfer"
    ):
        instruction = "Answer with the single most precise direction term only."
    else:
        instruction = "Answer the question using a single word or phrase."
    return f"{question}\n{instruction}", answer


def to_sft_record(
    row: Mapping,
    dataset_name: str,
    question_format: str,
    image_sha256: str,
) -> dict:
    sf = row_scene_frame(row)
    source_id = row_source_id(row)
    prompt, target = build_prompt(row, question_format)
    return {
        "id": f"{sf}:{source_id}:{question_format}",
        "image": f"images/{sf}_labeled_mosaic.jpg",
        "conversations": [
            {"from": "human", "value": f"<|image|>{prompt}"},
            {"from": "gpt", "value": target},
        ],
        "metadata": {
            "dataset_name": dataset_name,
            "question_format": question_format,
            "scene_frame": sf,
            "scene_name": sf.split("_frame", 1)[0],
            "source_question_id": source_id,
            "family": family_name(row),
            "image_sha256": image_sha256,
        },
    }


def select_hard_rows(
    raw_results: Sequence[Mapping],
    source_rows: Sequence[Mapping],
    quotas: Mapping[str, int],
    seed: int,
) -> tuple[list[dict], dict]:
    source_index = {
        (row_scene_frame(row), row_source_id(row)): dict(row) for row in source_rows
    }
    wrong_by_family: dict[str, list[dict]] = defaultdict(list)
    seen_wrong = set()
    for result in raw_results:
        if result.get("error") not in (None, "") or bool(result.get("is_correct")):
            continue
        key = (row_scene_frame(result), row_source_id(result))
        source = source_index.get(key)
        if source is not None and key not in seen_wrong:
            seen_wrong.add(key)
            wrong_by_family[family_name(source)].append(source)
    rng = random.Random(seed)
    selected = []
    deficits = {}
    surplus = []
    for family, quota in quotas.items():
        rows = wrong_by_family.get(family, [])
        rng.shuffle(rows)
        selected.extend(rows[:quota])
        deficits[family] = max(0, quota - len(rows))
        surplus.extend(rows[quota:])
    deficit_total = sum(deficits.values())
    rng.shuffle(surplus)
    selected.extend(surplus[:deficit_total])
    expected = sum(quotas.values())
    selected = dedupe_and_validate_rows(selected, min(expected, len(selected)))
    if len(selected) != expected:
        raise ValueError(
            f"Hard-screen shortfall: selected={len(selected)}, expected={expected}, "
            f"deficits={deficits}"
        )
    return selected, {
        "wrong_available_by_family": {
            key: len(value) for key, value in sorted(wrong_by_family.items())
        },
        "initial_deficits": deficits,
        "redistributed": deficit_total,
    }


def assert_no_test_scene(rows: Iterable[Mapping]) -> None:
    leaked = sorted(
        {
            row_scene_frame(row).split("_frame", 1)[0]
            for row in rows
            if row_scene_frame(row).split("_frame", 1)[0] in TEST_SCENES
        }
    )
    if leaked:
        raise ValueError(f"Frozen test-scene leakage: {leaked}")
