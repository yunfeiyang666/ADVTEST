#!/usr/bin/env python3
"""
测试 semantic_auditor_v15.py 的改进效果

对比 V14 vs V15 的 baseline 覆盖率分析质量
"""
import sys
import pathlib
import json

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from semantic_auditor import audit_baseline_question as audit_v14
from semantic_auditor_v15 import audit_baseline_question_v15 as audit_v15
from semantic_auditor import build_scene_context
from gap_pipeline.llm_client import LLMClient
from neo4j import GraphDatabase
import os

# 测试问题集（覆盖常见的误判场景）
TEST_QUESTIONS = [
    {
        "question": "There is a moving truck; how many things are to the back of it?",
        "template_type": "count",
        "num_hop": 1,
        "expected_anchor": "truck",
        "expected_relation": "back",
    },
    {
        "question": "What is to the front of me?",
        "template_type": "object",
        "num_hop": 1,
        "expected_anchor": "ego",
        "expected_relation": "front",
    },
    {
        "question": "Is there a car to the front of the bus?",
        "template_type": "exist",
        "num_hop": 2,
        "expected_anchor": "bus",
        "expected_relation": "front",
    },
    {
        "question": "How many pedestrians are visible from my perspective?",
        "template_type": "count",
        "num_hop": 1,
        "expected_anchor": "ego",
        "expected_relation": "any",
    },
    {
        "question": "What is the status of the car to the left of the truck?",
        "template_type": "status",
        "num_hop": 2,
        "expected_anchor": "truck",
        "expected_relation": "left",
    },
]


def test_auditor_comparison():
    """对比 V14 vs V15 的效果"""

    # 连接 Neo4j
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_pass = os.getenv("NEO4J_PASSWORD", "password")

    print(f"Connecting to Neo4j: {neo4j_uri}")
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))

    # 初始化 LLM
    llm = LLMClient()

    print("\n" + "="*80)
    print("Baseline Coverage Analysis: V14 vs V15 Comparison")
    print("="*80)

    # 构建场景上下文（共享）
    scene_ctx = build_scene_context(driver)
    print(f"\nScene context: {len(scene_ctx)} chars")
    print(f"Scene preview:\n{scene_ctx[:500]}...\n")

    # 统计结果
    v14_stats = {"l0": [], "l1": [], "l2": [], "success": 0, "time": []}
    v15_stats = {"l0": [], "l1": [], "l2": [], "success": 0, "time": []}

    for i, q in enumerate(TEST_QUESTIONS, 1):
        print("\n" + "="*80)
        print(f"Test {i}/{len(TEST_QUESTIONS)}")
        print("="*80)
        print(f"Question: {q['question']}")
        print(f"Expected anchor: {q['expected_anchor']}, relation: {q['expected_relation']}")

        # ── V14 测试 ──────────────────────────────────────────────────────
        print("\n[V14 Result]")
        try:
            result_v14 = audit_v14(
                question=q["question"],
                q_type=q["template_type"],
                num_hop=q["num_hop"],
                driver=driver,
                llm_client=llm,
                scene_context=scene_ctx,
                global_index=i,
            )

            print(f"  Success: {result_v14['success']}")
            print(f"  L0 nodes ({len(result_v14['l0_nodes'])}): {result_v14['l0_nodes']}")
            print(f"  L1 edges ({len(result_v14['l1_edges'])}): {result_v14['l1_edges'][:3]}")
            print(f"  L2 paths ({len(result_v14['l2_paths'])}): {result_v14['l2_paths'][:3]}")
            print(f"  LLM time: {result_v14['llm_ms']}ms")

            if result_v14['success']:
                v14_stats["success"] += 1
            v14_stats["l0"].append(len(result_v14['l0_nodes']))
            v14_stats["l1"].append(len(result_v14['l1_edges']))
            v14_stats["l2"].append(len(result_v14['l2_paths']))
            v14_stats["time"].append(result_v14['llm_ms'])

        except Exception as exc:
            print(f"  ERROR: {exc}")
            v14_stats["l0"].append(0)
            v14_stats["l1"].append(0)
            v14_stats["l2"].append(0)
            v14_stats["time"].append(0)

        # ── V15 测试 ──────────────────────────────────────────────────────
        print("\n[V15 Result]")
        try:
            result_v15 = audit_v15(
                question=q["question"],
                q_type=q["template_type"],
                num_hop=q["num_hop"],
                driver=driver,
                llm_client=llm,
                scene_context=scene_ctx,
                global_index=i,
            )

            print(f"  Success: {result_v15['success']}")
            print(f"  Reasoning: {result_v15.get('reasoning', {})}")
            print(f"  L0 nodes ({len(result_v15['l0_nodes'])}): {result_v15['l0_nodes']}")
            print(f"  L1 edges ({len(result_v15['l1_edges'])}): {result_v15['l1_edges'][:3]}")
            print(f"  L2 paths ({len(result_v15['l2_paths'])}): {result_v15['l2_paths'][:3]}")
            print(f"  LLM time: {result_v15['llm_ms']}ms")

            if result_v15['success']:
                v15_stats["success"] += 1
            v15_stats["l0"].append(len(result_v15['l0_nodes']))
            v15_stats["l1"].append(len(result_v15['l1_edges']))
            v15_stats["l2"].append(len(result_v15['l2_paths']))
            v15_stats["time"].append(result_v15['llm_ms'])

            # 验证 anchor 识别是否正确
            reasoning = result_v15.get('reasoning', {})
            anchor_correct = q['expected_anchor'] in str(reasoning.get('anchor_id', '')).lower()
            relation_correct = q['expected_relation'] in str(reasoning.get('relation', '')).lower()

            print(f"\n  Anchor correct: {anchor_correct} (expected: {q['expected_anchor']}, got: {reasoning.get('anchor_id', 'N/A')})")
            print(f"  Relation correct: {relation_correct} (expected: {q['expected_relation']}, got: {reasoning.get('relation', 'N/A')})")

        except Exception as exc:
            print(f"  ERROR: {exc}")
            v15_stats["l0"].append(0)
            v15_stats["l1"].append(0)
            v15_stats["l2"].append(0)
            v15_stats["time"].append(0)

        # ── 对比 ──────────────────────────────────────────────────────────
        print("\n[Comparison]")
        l0_diff = v15_stats["l0"][-1] - v14_stats["l0"][-1]
        l1_diff = v15_stats["l1"][-1] - v14_stats["l1"][-1]
        l2_diff = v15_stats["l2"][-1] - v14_stats["l2"][-1]

        print(f"  L0: V14={v14_stats['l0'][-1]} → V15={v15_stats['l0'][-1]} (Δ{l0_diff:+d})")
        print(f"  L1: V14={v14_stats['l1'][-1]} → V15={v15_stats['l1'][-1]} (Δ{l1_diff:+d})")
        print(f"  L2: V14={v14_stats['l2'][-1]} → V15={v15_stats['l2'][-1]} (Δ{l2_diff:+d})")

    # ── 总结统计 ──────────────────────────────────────────────────────────
    print("\n\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)

    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    print(f"\n{'Metric':<20} {'V14':<15} {'V15':<15} {'Improvement':<15}")
    print("-" * 65)
    print(f"{'Success Rate':<20} {v14_stats['success']}/{len(TEST_QUESTIONS):<15} {v15_stats['success']}/{len(TEST_QUESTIONS):<15} {v15_stats['success'] - v14_stats['success']:+d}")
    print(f"{'Avg L0 nodes':<20} {avg(v14_stats['l0']):<15.2f} {avg(v15_stats['l0']):<15.2f} {avg(v15_stats['l0']) - avg(v14_stats['l0']):+.2f}")
    print(f"{'Avg L1 edges':<20} {avg(v14_stats['l1']):<15.2f} {avg(v15_stats['l1']):<15.2f} {avg(v15_stats['l1']) - avg(v14_stats['l1']):+.2f}")
    print(f"{'Avg L2 paths':<20} {avg(v14_stats['l2']):<15.2f} {avg(v15_stats['l2']):<15.2f} {avg(v15_stats['l2']) - avg(v14_stats['l2']):+.2f}")
    print(f"{'Avg LLM time (ms)':<20} {avg(v14_stats['time']):<15.1f} {avg(v15_stats['time']):<15.1f} {avg(v15_stats['time']) - avg(v14_stats['time']):+.1f}")

    # 计算提升倍数
    if avg(v14_stats['l0']) > 0:
        l0_mult = avg(v15_stats['l0']) / avg(v14_stats['l0'])
        print(f"\nL0 improvement: {l0_mult:.2f}x")
    if avg(v14_stats['l1']) > 0:
        l1_mult = avg(v15_stats['l1']) / avg(v14_stats['l1'])
        print(f"L1 improvement: {l1_mult:.2f}x")
    if avg(v14_stats['l2']) > 0:
        l2_mult = avg(v15_stats['l2']) / avg(v14_stats['l2'])
        print(f"L2 improvement: {l2_mult:.2f}x")
    elif avg(v15_stats['l2']) > 0:
        print(f"L2 improvement: ∞ (V14 had 0, V15 has {avg(v15_stats['l2']):.2f})")

    driver.close()

    print("\n✓ Test completed")

    # 返回统计结果
    return {
        "v14": v14_stats,
        "v15": v15_stats,
    }


if __name__ == "__main__":
    test_auditor_comparison()
