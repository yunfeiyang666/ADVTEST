import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Mapping, Sequence

WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from experiment_protocol import STRUCTURAL_LAYER, annotate_provenance
from fixed_budget_experiment import (
    FrameInput,
    build_frame_question_counts,
    build_method_stream,
    redistribute_frame_question_counts,
)


DEFAULT_OUTPUTS_ROOT = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "outputs"
DEFAULT_FRAME_CACHE = (
    WORKSPACE_ROOT
    / "scratch"
    / "rq1_seed_expansion"
    / "runs"
    / "official-frame-cache-target3500"
    / "results"
    / "frame_cache.json"
)

DIRECTION_TEXT = {
    "front": "front",
    "back": "back",
    "front_left": "front left",
    "front_right": "front right",
    "back_left": "back left",
    "back_right": "back right",
}


def display_type(node: Mapping) -> str:
    value = str(node.get("type") or node.get("category") or "").strip()
    if not value:
        value = str(node.get("unique_id") or "object")
    if "." in value:
        value = value.rsplit(".", 1)[-1]
    return value.replace("_", " ").replace("-", " ")


def scene_graph_path(outputs_root: Path, scene_frame: str) -> Path:
    return (
        outputs_root
        / scene_frame
        / "offline"
        / "scene_graphs"
        / f"{scene_frame}_filtered_scene_graph.json"
    )


def iter_frame_names(frame_cache: Path, frame_pool_size: int) -> List[str]:
    records = json.loads(frame_cache.read_text(encoding="utf-8"))
    return [str(item["scene_frame"]) for item in records[:frame_pool_size]]


def load_scene_graph(outputs_root: Path, scene_frame: str) -> dict:
    path = scene_graph_path(outputs_root, scene_frame)
    if not path.exists():
        raise FileNotFoundError(f"Missing filtered scene graph: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def split_scene_frame(scene_frame: str) -> tuple[str, int]:
    if "_frame" not in scene_frame:
        return scene_frame, 0
    scene_name, frame_text = scene_frame.rsplit("_frame", 1)
    try:
        return scene_name, int(frame_text)
    except ValueError:
        return scene_name, 0


def base_record(scene_frame: str, level: str, question_id: str) -> dict:
    scene_name, frame_idx = split_scene_frame(scene_frame)
    return {
        "question_id": question_id,
        "scene_name": scene_name,
        "frame_idx": frame_idx,
        "scene_frame": scene_frame,
        "topology_level": level.upper(),
        "generation_backend": "programmatic",
        "logic_verification": "IN_MEMORY_VERIFIED",
        "schema_version": "rq1_l0_l1_structural_v1",
    }


def l0_candidates(scene_frame: str, scene_graph: Mapping) -> List[dict]:
    records = []
    for node in scene_graph.get("nodes") or []:
        uid = str(node.get("unique_id") or "")
        if not uid or uid == "ego":
            continue
        answer = display_type(node)
        record = base_record(scene_frame, "l0", f"{scene_frame}:l0:type:{uid}")
        record.update(
            {
                "template_id": "l0_object_type",
                "question": f"What type of object is {uid}?",
                "answer": answer,
                "answer_type": "category",
                "target_object": uid,
                "footprint_nodes": [uid],
                "coverage_footprint": {"l0": [uid], "l1": [], "l2": []},
                "coverage_l0": [uid],
                "coverage_l1": [],
                "coverage_l2": [],
            }
        )
        records.append(record)
    return records


def l1_candidates(scene_frame: str, scene_graph: Mapping) -> List[dict]:
    nodes = {
        str(node.get("unique_id")): node
        for node in scene_graph.get("nodes") or []
        if node.get("unique_id")
    }
    records = []
    for edge in scene_graph.get("edges") or []:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        direction = str(edge.get("direction_6") or "")
        if not source or not target or source == target:
            continue
        if source not in nodes or target not in nodes:
            continue
        if direction not in DIRECTION_TEXT:
            continue
        relation_item = f"{source}|{target}|{direction}"
        record = base_record(
            scene_frame, "l1", f"{scene_frame}:l1:direction:{source}:{target}"
        )
        record.update(
            {
                "template_id": "l1_pair_direction",
                "question": f"Where is {target} relative to {source}?",
                "answer": DIRECTION_TEXT[direction],
                "answer_type": "direction",
                "source_object": source,
                "target_object": target,
                "direction_6": direction,
                "footprint_nodes": [source, target],
                "coverage_footprint": {
                    "l0": [source, target],
                    "l1": [relation_item],
                    "l2": [],
                },
                "coverage_l0": [source, target],
                "coverage_l1": [relation_item],
                "coverage_l2": [],
            }
        )
        records.append(record)
    return records


def build_frame_inputs(
    frame_names: Sequence[str], outputs_root: Path, level: str
) -> List[FrameInput]:
    frames = []
    for index, scene_frame in enumerate(frame_names, start=1):
        print(
            f"[l0-l1] Loading frame {index}/{len(frame_names)}: {scene_frame}",
            flush=True,
        )
        scene_graph = load_scene_graph(outputs_root, scene_frame)
        if level == "l0":
            questions = l0_candidates(scene_frame, scene_graph)
        elif level == "l1":
            questions = l1_candidates(scene_frame, scene_graph)
        else:
            raise ValueError(f"Unsupported level: {level}")
        total_l0 = len(
            {
                str(node.get("unique_id"))
                for node in scene_graph.get("nodes") or []
                if node.get("unique_id") and node.get("unique_id") != "ego"
            }
        )
        total_l1 = len(
            {
                f"{edge.get('source')}|{edge.get('target')}|{edge.get('direction_6')}"
                for edge in scene_graph.get("edges") or []
                if edge.get("source")
                and edge.get("target")
                and edge.get("source") != edge.get("target")
                and edge.get("direction_6") in DIRECTION_TEXT
            }
        )
        frames.append(
            FrameInput(
                scene_frame=scene_frame,
                questions=questions,
                total_l0=total_l0,
                total_l1=total_l1,
                total_l2=0,
            )
        )
    return frames


def annotate_suite(
    *,
    level: str,
    frames: Sequence[FrameInput],
    generation_budget: int,
    seed: int,
    method: str,
    frame_counts: Mapping[str, int],
) -> tuple[list[dict], dict]:
    suite = []
    frame_runs = []
    for frame_index, frame in enumerate(frames):
        assigned = int(frame_counts.get(frame.scene_frame, 0))
        if assigned <= 0:
            continue
        stream = build_method_stream(
            method,
            frame.questions,
            assigned,
            seed + frame_index * 1009,
        )
        for question in stream:
            annotated = annotate_provenance(
                question,
                layer=STRUCTURAL_LAYER,
                method=f"advtest_{level}",
                question_source=f"programmatic_{level}_candidate_space",
                source_question_id=str(question.get("question_id") or ""),
                source_sample_token="",
                generation_adapter="programmatic",
                uses_coverage_feedback=True,
                vlm_call_cost=1,
                scene_frame=frame.scene_frame,
                global_budget_index=len(suite) + 1,
            )
            annotated["frame_budget_index"] = 1 + sum(
                1 for row in suite if row.get("scene_frame") == frame.scene_frame
            )
            annotated["frame_assigned_questions"] = assigned
            suite.append(annotated)
        frame_runs.append(
            {
                "scene_frame": frame.scene_frame,
                "assigned_questions": assigned,
                "questions": len(stream),
                "candidate_count": len(frame.questions),
            }
        )
        if len(suite) >= generation_budget:
            break
    suite = suite[:generation_budget]
    summary = {
        "level": level,
        "method": f"advtest_{level}",
        "generation_budget": generation_budget,
        "suite_size": len(suite),
        "visited_frames": len({row["scene_frame"] for row in suite}),
        "template_counts": dict(Counter(row["template_id"] for row in suite)),
        "answer_type_counts": dict(Counter(row["answer_type"] for row in suite)),
        "frame_runs": frame_runs,
    }
    return suite, summary


def write_jsonl(path: Path, records: Iterable[Mapping]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_outputs(output_dir: Path, suites: Mapping[str, list[dict]], summary: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for level, suite in suites.items():
        write_jsonl(output_dir / f"advtest_{level}_suite.jsonl", suite)
    (output_dir / "l0_l1_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    lines = ["# L0/L1 Structural Suite Summary", ""]
    lines.append("| Level | Suite Size | Frames | Templates |")
    lines.append("|---|---:|---:|---|")
    for level, data in summary["levels"].items():
        lines.append(
            f"| {level.upper()} | {data['suite_size']} | "
            f"{data['visited_frames']} | {data['template_counts']} |"
        )
    (output_dir / "l0_l1_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build ADVTEST-style L0/L1 structural suites from filtered scene graphs."
    )
    parser.add_argument("--frame-cache", type=Path, default=DEFAULT_FRAME_CACHE)
    parser.add_argument("--outputs-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frame-pool-size", type=int, default=308)
    parser.add_argument("--generation-budget", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--levels",
        nargs="+",
        choices=["l0", "l1"],
        default=["l0", "l1"],
    )
    parser.add_argument(
        "--method",
        choices=["advtest", "greedy_l0", "greedy_l1", "random"],
        default="advtest",
        help="Selection strategy within each level candidate pool.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frame_names = iter_frame_names(args.frame_cache, args.frame_pool_size)
    suites = {}
    level_summaries = {}
    for level in args.levels:
        frames = build_frame_inputs(frame_names, args.outputs_root, level)
        raw_assignment = build_frame_question_counts(
            [frame.scene_frame for frame in frames],
            args.generation_budget,
            args.seed,
        )
        adjusted = redistribute_frame_question_counts(
            frames,
            raw_assignment["frame_question_counts"],
            args.generation_budget,
        )
        method = args.method
        if args.method == "advtest" and level == "l0":
            method = "greedy_l0"
        elif args.method == "advtest" and level == "l1":
            method = "greedy_l1"
        suite, summary = annotate_suite(
            level=level,
            frames=frames,
            generation_budget=args.generation_budget,
            seed=args.seed,
            method=method,
            frame_counts=adjusted["frame_question_counts"],
        )
        summary["selection_method"] = method
        summary["frame_assignment"] = adjusted
        suites[level] = suite
        level_summaries[level] = summary
    write_outputs(
        args.output_dir,
        suites,
        {
            "frame_cache": str(args.frame_cache),
            "outputs_root": str(args.outputs_root),
            "frame_pool_size": args.frame_pool_size,
            "generation_budget": args.generation_budget,
            "seed": args.seed,
            "levels": level_summaries,
        },
    )


if __name__ == "__main__":
    main()
