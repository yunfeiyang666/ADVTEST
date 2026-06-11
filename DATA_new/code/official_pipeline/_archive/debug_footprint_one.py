from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import advtest_env
from gap_pipeline.l2_initial_coverage_analyzer import _footprint_from_llm, _load_ground_graph, _read_records
from gap_pipeline.l2_llm_client import LLMClient
from run_gap_pipeline_v7 import compact_scene_context


def _frame_graph_path(frame: str, artifact_root: Path) -> Path:
    direct = artifact_root / frame / "offline" / "scene_graphs" / f"{frame}_filtered_scene_graph.json"
    if direct.exists():
        return direct
    fallback = Path("filtered_scene_graphs") / f"{frame}_scene_graph.json"
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"scene graph not found for {frame}: {direct} or {fallback}")


def _object_ids(graph: Dict[str, Any]) -> List[str]:
    return [str(n.get("unique_id")) for n in graph.get("nodes", []) if n.get("unique_id")]


def _objects_text(graph: Dict[str, Any]) -> str:
    rows = []
    for n in graph.get("nodes", []):
        rows.append(f"{n.get('unique_id')}: type={n.get('type')} category={n.get('category')} status={n.get('status')}")
    return "\n".join(rows)


def _matched_records(frame: str, qa_file: Path, artifact_root: Path) -> List[Dict[str, Any]]:
    cached = artifact_root / frame / "offline" / "initial_coverage" / f"{frame}_initial_coverage.jsonl"
    if cached.exists():
        return [json.loads(line) for line in cached.read_text(encoding="utf-8").splitlines() if line.strip()]
    scene_id, frame_part = frame.rsplit("_frame", 1)
    frame_id = int(frame_part)
    out = []
    for rec in _read_records(qa_file):
        rec_scene = str(rec.get("scene_id") or rec.get("scene") or "")
        rec_frame = rec.get("frame_id") if rec.get("frame_id") is not None else rec.get("frame_idx")
        if rec_scene == scene_id and int(rec_frame if rec_frame is not None else -1) == frame_id:
            out.append(rec)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug one LLM footprint grounding item.")
    parser.add_argument("--frame", required=True, help="e.g. scene-0103_frame3")
    parser.add_argument("--index", type=int, required=True, help="1-based index among original QA records for the frame")
    parser.add_argument("--qa-file", default="")
    parser.add_argument("--artifact-root", default="outputs/v7_formal_test")
    parser.add_argument("--max-edges", type=int, default=9999, help="scene context relation limit; use 9999 for full context")
    parser.add_argument("--objects-only", action="store_true", help="send object inventory only")
    args = parser.parse_args()

    advtest_env.load_advtest_env()
    graph_path = _frame_graph_path(args.frame, Path(args.artifact_root))
    graph = _load_ground_graph(graph_path)
    qa_file = Path(args.qa_file or os.environ.get("ADVTEST_ORIGINAL_QA") or "../data/NuScenes_val_questions.json")
    records = _matched_records(args.frame, qa_file, Path(args.artifact_root))
    if args.index < 1 or args.index > len(records):
        raise IndexError(f"index {args.index} out of range; matched records={len(records)}")
    record = records[args.index - 1]

    object_ids = _object_ids(graph)
    if args.objects_only:
        scene_context = "Objects:\n" + _objects_text(graph)
    else:
        scene_context = compact_scene_context(graph_path, max_edges=args.max_edges)

    client = LLMClient.from_env()
    fp = _footprint_from_llm(record, llm_client=client, object_ids=object_ids, scene_context=scene_context, graph=graph)

    print("=" * 100)
    print(f"frame: {args.frame}")
    print(f"graph: {graph_path}")
    print(f"matched_index: {args.index}/{len(records)}")
    print(f"scene_context_chars: {len(scene_context)} max_edges={args.max_edges} objects_only={args.objects_only}")
    print("-" * 100)
    print("QUESTION:", record.get("question") or record.get("Question"))
    print("ANSWER:  ", record.get("answer") or record.get("Answer"))
    print("-" * 100)
    print("STATUS:", fp.get("_llm_footprint_status"))
    print("REASON:", fp.get("_llm_footprint_reason"))
    print("L0/L1/L2:", len(fp.get("l0") or []), len(fp.get("l1") or []), len(fp.get("l2") or []))
    print("NODES:", fp.get("_grounded_nodes"))
    print("EDGES:", fp.get("_grounded_edges"))
    print("-" * 100)
    print("PAYLOAD:")
    print(json.dumps(fp.get("_llm_payload"), ensure_ascii=False, indent=2))
    print("=" * 100)


if __name__ == "__main__":
    main()

