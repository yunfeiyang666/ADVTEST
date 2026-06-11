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
    path = artifact_root / frame / "offline" / "scene_graphs" / f"{frame}_filtered_scene_graph.json"
    if path.exists():
        return path
    fallback = Path("filtered_scene_graphs") / f"{frame}_scene_graph.json"
    if fallback.exists():
        return fallback
    raise FileNotFoundError(frame)


def _records(frame: str, artifact_root: Path, qa_file: Path) -> List[Dict[str, Any]]:
    cached = artifact_root / frame / "offline" / "initial_coverage" / f"{frame}_initial_coverage.jsonl"
    if cached.exists():
        return [json.loads(line) for line in cached.read_text(encoding="utf-8").splitlines() if line.strip()]
    scene_id, frame_part = frame.rsplit("_frame", 1)
    frame_id = int(frame_part)
    out = []
    for rec in _read_records(qa_file):
        if str(rec.get("scene_id") or rec.get("scene") or "") == scene_id and int(rec.get("frame_id") or rec.get("frame_idx") or -1) == frame_id:
            out.append(rec)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True)
    ap.add_argument("--artifact-root", default="outputs/v7_formal_test")
    ap.add_argument("--qa-file", default="")
    ap.add_argument("--max-edges", type=int, default=9999)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    advtest_env.load_advtest_env()
    qa_file = Path(args.qa_file or os.environ.get("ADVTEST_ORIGINAL_QA") or "../data/NuScenes_val_questions.json")
    artifact_root = Path(args.artifact_root)
    graph_path = _frame_graph_path(args.frame, artifact_root)
    graph = _load_ground_graph(graph_path)
    records = _records(args.frame, artifact_root, qa_file)
    object_ids = [str(n.get("unique_id")) for n in graph.get("nodes", []) if n.get("unique_id")]
    scene_context = compact_scene_context(graph_path, max_edges=args.max_edges)
    client = LLMClient.from_env()

    summaries = []
    for idx, rec in enumerate(records, 1):
        fp = _footprint_from_llm(rec, llm_client=client, object_ids=object_ids, scene_context=scene_context, graph=graph)
        q = rec.get("question") or rec.get("Question")
        a = rec.get("answer") or rec.get("Answer")
        row = {
            "index": idx,
            "question": q,
            "answer": a,
            "status": fp.get("_llm_footprint_status"),
            "reason": fp.get("_llm_footprint_reason"),
            "l0": len(fp.get("l0") or []),
            "l1": len(fp.get("l1") or []),
            "l2": len(fp.get("l2") or []),
            "nodes": fp.get("_grounded_nodes"),
            "edges": fp.get("_grounded_edges"),
            "payload": fp.get("_llm_payload"),
        }
        summaries.append(row)
        print(f"#{idx} {row['status']} l={row['l0']}/{row['l1']}/{row['l2']} | {q}", flush=True)
        print(f"  reason: {row['reason']}", flush=True)
        print(f"  nodes: {row['nodes']}", flush=True)
        print(f"  edges: {row['edges']}", flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

