import json
import re
from pathlib import Path
from collections import Counter

from test_multi_level_coverage import (
    _load_scene_graph,
    _load_questions_from_vqa,
    _build_edge_sets,
    _compute_l0_node_coverage,
)
from vqa_pipeline.scene_coverage import calculate_scene_coverage

SCENES = [
    ("scene-0553", 8),
    ("scene-0103", 38),
    ("scene-0916", 8),
    ("scene-0103", 25),
]

BASE_SG = Path("output/coverage_analysis/scene_graphs")
BASE_QA = Path("output/coverage_analysis/vqa_results")

REL_PATTERN = re.compile(r"\(\w+[^)]*\)-\[[^\]]*\]->\(\w+[^)]*\)")
STATUS_EQ_PATTERN = re.compile(r"\b(\w+)\.status\s*=\s*(\w+)\.status\b")


def classify_level(cypher: str) -> str:
    if not cypher:
        return "L0"
    rels = REL_PATTERN.findall(cypher)
    rel_count = len(rels)
    has_status_eq = bool(STATUS_EQ_PATTERN.search(cypher)) or "same_status" in cypher
    if rel_count >= 2 or has_status_eq:
        return "L2"
    if rel_count == 0:
        return "L0"
    return "L1"


def coverage_for_subset(scene_graph, qs):
    if not qs:
        return None
    cov_stats = calculate_scene_coverage(qs, scene_graph)
    edge_details = cov_stats["edge_details"]
    all_edges, covered_edges = _build_edge_sets(edge_details)
    l0 = _compute_l0_node_coverage(scene_graph, all_edges, covered_edges)
    return {
        "edge_covered": cov_stats["covered_edges"],
        "edge_total": cov_stats["total_edges"],
        "edge_rate": cov_stats["coverage_rate"],
        "node_total": l0["total"],
        "node_covered": l0["covered"],
        "node_rate": l0["coverage_rate"],
        "question_count": len(qs),
    }


def main() -> None:
    for scene_name, frame_idx in SCENES:
        sg_path = BASE_SG / f"{scene_name}_frame{frame_idx}_scene_graph.json"
        qa_path = BASE_QA / f"{scene_name}_frame{frame_idx}_official_qa.json"

        if not sg_path.exists() or not qa_path.exists():
            print(f"\n[SKIP] {scene_name}_frame{frame_idx}: missing files")
            continue

        print("\n" + "=" * 70)
        print(f"Scene: {scene_name}_frame{frame_idx}")
        print(f"  scene_graph: {sg_path}")
        print(f"  qa_file:     {qa_path}")

        scene_graph = _load_scene_graph(sg_path)
        # also load raw QA for cypher text
        with qa_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        raw_items = raw.get("results", [])

        buckets = {"L0": [], "L1": [], "L2": []}
        level_counts = Counter()

        for item in raw_items:
            cypher = (item.get("cypher_query") or item.get("cypher") or "").strip()
            lvl = classify_level(cypher)
            level_counts[lvl] += 1
            buckets[lvl].append({
                "question": item.get("question", ""),
                "cypher_query": cypher,
                "query_result": item.get("query_result", {}),
            })

        total_q = sum(level_counts.values())
        print(f"Total questions: {total_q}  | by level: {dict(level_counts)}")

        for lvl in ["L1", "L2"]:
            stats = coverage_for_subset(scene_graph, buckets[lvl])
            if stats is None:
                print(f"\n  {lvl}: no questions")
                continue
            print(f"\n  -- {lvl} only --")
            print(f"    questions:     {stats['question_count']}")
            print(f"    edge coverage: {stats['edge_covered']} / {stats['edge_total']} -> {stats['edge_rate']}%")
            print(f"    node coverage: {stats['node_covered']} / {stats['node_total']} -> {stats['node_rate']}%")


if __name__ == "__main__":
    main()
