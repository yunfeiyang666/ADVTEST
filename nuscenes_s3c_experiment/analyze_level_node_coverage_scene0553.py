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

SCENE_GRAPH_PATH = Path("output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json")
QA_PATH = Path("output/coverage_analysis/vqa_results/scene-0553_frame8_official_qa.json")

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


def main() -> None:
    scene_graph = _load_scene_graph(SCENE_GRAPH_PATH)
    all_questions_raw = _load_questions_from_vqa(QA_PATH)

    # Re-attach original cypher for classification (load from raw file)
    with QA_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    raw_items = raw.get("results", [])

    assert len(all_questions_raw) == len(raw_items), "Mismatch question count"

    buckets = {"L0": [], "L1": [], "L2": []}
    level_counts = Counter()

    for q_struct, raw_item in zip(all_questions_raw, raw_items):
        cypher = (raw_item.get("cypher_query") or raw_item.get("cypher") or "").strip()
        lvl = classify_level(cypher)
        level_counts[lvl] += 1
        # For coverage we only need question text + cypher_query
        buckets[lvl].append({
            "question": raw_item.get("question", ""),
            "cypher_query": cypher,
            "query_result": raw_item.get("query_result", {}),
        })

    print(f"Total questions: {sum(level_counts.values())}")
    print("By level:", dict(level_counts))

    # Helper to compute node coverage for a given subset of questions
    def coverage_for(label: str, qs):
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

    for lvl in ["L1", "L2"]:
        stats = coverage_for(lvl, buckets[lvl])
        if stats is None:
            print(f"\n{lvl}: no questions")
            continue
        print(f"\n=== {lvl} only ===")
        print(f"questions: {stats['question_count']}")
        print(f"edge coverage: {stats['edge_covered']} / {stats['edge_total']} -> {stats['edge_rate']}%")
        print(f"node coverage: {stats['node_covered']} / {stats['node_total']} -> {stats['node_rate']}%")


if __name__ == "__main__":
    main()
