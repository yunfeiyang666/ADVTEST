"""Build a frame cache containing frames that have official NuScenes-QA rows.

The existing official-QA suite builder consumes a compact frame cache. This
script expands that cache directly from DATA_new/outputs, stopping once the
matched official QA count reaches a target.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Mapping, Optional


WORKSPACE_ROOT = Path(__file__).absolute().parents[4]
MODULE_DIR = Path(__file__).absolute().parent
sys.path.insert(0, str(MODULE_DIR))

from evaluator import get_sample_token
from official_qa_experiment import index_official_questions, load_official_questions


def find_data_new_root(workspace_root: Path) -> Path:
    candidates = []
    for child in workspace_root.iterdir():
        data_new = child / "DATA_new"
        if (data_new / "outputs").exists() and (data_new / "data").exists():
            candidates.append(data_new)
    if not candidates:
        raise FileNotFoundError(
            f"Could not find a DATA_new root below {workspace_root}"
        )
    return candidates[0]


def natural_scene_key(path: Path) -> tuple:
    match = re.match(r"scene-(\d+)_frame(\d+)$", path.name)
    if not match:
        return (1, path.name, -1)
    return (0, int(match.group(1)), int(match.group(2)))


def iter_frame_dirs(outputs_root: Path, scan_limit: Optional[int]) -> Iterable[Path]:
    count = 0
    for frame_dir in sorted(outputs_root.iterdir(), key=natural_scene_key):
        if not frame_dir.is_dir():
            continue
        if scan_limit is not None and count >= scan_limit:
            break
        count += 1
        yield frame_dir


def scene_graph_path(frame_dir: Path) -> Path:
    return (
        frame_dir
        / "offline"
        / "scene_graphs"
        / f"{frame_dir.name}_filtered_scene_graph.json"
    )


def load_scene_graph(frame_dir: Path) -> Optional[dict]:
    path = scene_graph_path(frame_dir)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_cache(
    *,
    outputs_root: Path,
    dataroot: Path,
    questions_by_sample: Mapping[str, list[dict]],
    target_question_count: int,
    max_frames: Optional[int],
    scan_limit: Optional[int],
) -> tuple[list[dict], dict]:
    cache = []
    total_questions = 0
    scanned_frames = 0
    missing_graph = 0
    no_sample_token = 0
    no_official_questions = 0

    for frame_dir in iter_frame_dirs(outputs_root, scan_limit):
        scanned_frames += 1
        scene_graph = load_scene_graph(frame_dir)
        if scene_graph is None:
            missing_graph += 1
            continue
        sample_token = get_sample_token(scene_graph, dataroot)
        if not sample_token:
            no_sample_token += 1
            continue
        official_questions = questions_by_sample.get(sample_token, [])
        if not official_questions:
            no_official_questions += 1
            continue
        n_objects = len(scene_graph.get("nodes") or scene_graph.get("objects") or [])
        cache.append(
            {
                "scene_frame": frame_dir.name,
                "n_objects": n_objects,
                "generated_count": len(official_questions),
                "official_qa_count": len(official_questions),
                "sample_token": sample_token,
            }
        )
        total_questions += len(official_questions)
        if max_frames is not None and len(cache) >= max_frames:
            break
        if total_questions >= target_question_count:
            break

    summary = {
        "scanned_frames": scanned_frames,
        "matched_frames": len(cache),
        "official_question_count": total_questions,
        "target_question_count": target_question_count,
        "max_frames": max_frames,
        "scan_limit": scan_limit,
        "missing_graph": missing_graph,
        "no_sample_token": no_sample_token,
        "no_official_questions": no_official_questions,
        "outputs_root": str(outputs_root),
        "dataroot": str(dataroot),
    }
    return cache, summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a larger official NuScenes-QA frame cache."
    )
    parser.add_argument("--questions-path", type=Path)
    parser.add_argument("--outputs-root", type=Path)
    parser.add_argument("--dataroot", type=Path)
    parser.add_argument("--target-question-count", type=int, default=3500)
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--scan-limit", type=int)
    parser.add_argument("--output-cache", required=True, type=Path)
    parser.add_argument("--summary-json", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    data_new_root = find_data_new_root(WORKSPACE_ROOT)
    questions_path = args.questions_path or (
        data_new_root / "data" / "NuScenes_val_questions.json"
    )
    outputs_root = args.outputs_root or (data_new_root / "outputs")
    dataroot = args.dataroot or (data_new_root / "data")
    questions_by_sample = index_official_questions(
        load_official_questions(questions_path)
    )

    cache, summary = build_cache(
        outputs_root=outputs_root,
        dataroot=dataroot,
        questions_by_sample=questions_by_sample,
        target_question_count=args.target_question_count,
        max_frames=args.max_frames,
        scan_limit=args.scan_limit,
    )
    args.output_cache.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_cache.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    args.summary_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        "[official-frame-cache] "
        f"matched_frames={summary['matched_frames']} "
        f"official_questions={summary['official_question_count']} "
        f"scanned_frames={summary['scanned_frames']} "
        f"cache={args.output_cache}"
    )


if __name__ == "__main__":
    main()
