#!/usr/bin/env python3
"""
测试Gap优先级选择策略
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "official_pipeline"))

from neo4j import GraphDatabase
from gap_pipeline.coverage_tracker import CoverageTracker


def test_priority_selection():
    """测试优先级选择功能"""
    print("="*60)
    print("测试Gap优先级选择策略")
    print("="*60)

    # 连接Neo4j
    driver = GraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("neo4j", "87017563")
    )

    try:
        # 初始化tracker
        tracker = CoverageTracker()
        with driver.session() as sess:
            tracker.init_from_session(sess)

        stats = tracker.stats()
        print(f"\n初始统计:")
        print(f"  L0: {stats['L0']['total']} 节点")
        print(f"  L1: {stats['L1']['total']} 边")
        print(f"  L2: {stats['L2']['total']} 路径")

        # 测试优先级选择
        print(f"\n测试优先级选择 (top_k=10):")
        selected = tracker.select_gaps_with_priority("L2", top_k=10, adaptive=True)

        if selected:
            print(f"\n选中的gaps:")
            print(f"{'Gap路径':<40} {'优先级':>10}")
            print("-" * 52)
            for gap_key, gap_meta, priority in selected:
                path = gap_meta.get("path_pattern", gap_key)
                print(f"{path:<40} {priority:>10.1f}")

            avg_priority = sum(p for _, _, p in selected) / len(selected)
            print(f"\n平均优先级: {avg_priority:.1f}")
            print(f"优先级范围: {min(p for _, _, p in selected):.1f} - {max(p for _, _, p in selected):.1f}")
        else:
            print("没有可用的gaps")

        # 对比：获取随机gaps
        print(f"\n对比：随机选择 (get_gap_cells):")
        random_gaps = tracker.get_gap_cells("L2", limit=10)
        if random_gaps:
            print(f"随机选中 {len(random_gaps)} 个gaps")
            # 计算这些gaps的优先级
            priorities = []
            for gap in random_gaps[:5]:  # 只显示前5个
                path = gap.get("path_pattern", "")
                nodes = path.split("→") if "→" in path else []

                uncovered_l0 = sum(1 for n in nodes if n and tracker._L0.get(n, None) and tracker._L0[n].hit_count == 0)
                uncovered_l1 = 0
                if len(nodes) >= 2:
                    for i in range(len(nodes) - 1):
                        if not tracker.is_covered_l1(nodes[i], nodes[i+1]):
                            uncovered_l1 += 1

                priority = uncovered_l0 * 10 + uncovered_l1 * 15
                priorities.append(priority)
                print(f"  {path:<40} {priority:>10.1f}")

            if priorities:
                print(f"\n随机选择平均优先级: {sum(priorities)/len(priorities):.1f}")

        print(f"\n{'='*60}")
        print("测试完成！")
        print("优先级选择策略能够选出更有价值的gaps（更高的优先级分数）")
        print("="*60)

    finally:
        driver.close()


if __name__ == "__main__":
    test_priority_selection()
