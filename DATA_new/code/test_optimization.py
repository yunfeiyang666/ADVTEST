#!/usr/bin/env python3
"""
测试优化功能的单元测试（不需要Neo4j）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "official_pipeline"))

from gap_pipeline.coverage_tracker import (
    CoverageTracker,
    CoverageRecord,
    _l0_key,
    _l1_key_normalized,
    _l2_key_normalized,
)


def test_priority_calculation():
    """测试优先级计算逻辑"""
    print("="*60)
    print("测试1: 优先级计算逻辑")
    print("="*60)

    tracker = CoverageTracker()

    # 手动构建一些测试数据
    # L0: 5个节点，其中3个未覆盖
    tracker._L0["ego"] = CoverageRecord()
    tracker._L0["ego"].hit_count = 1  # 已覆盖
    tracker._L0["car1"] = CoverageRecord()  # 未覆盖
    tracker._L0["car2"] = CoverageRecord()  # 未覆盖
    tracker._L0["car3"] = CoverageRecord()
    tracker._L0["car3"].hit_count = 1  # 已覆盖
    tracker._L0["car4"] = CoverageRecord()  # 未覆盖

    # L1: 4条边，其中2条未覆盖
    tracker._L1[_l1_key_normalized("ego", "car1")] = CoverageRecord()  # 未覆盖
    tracker._L1[_l1_key_normalized("car1", "car2")] = CoverageRecord()  # 未覆盖
    tracker._L1[_l1_key_normalized("ego", "car3")] = CoverageRecord()
    tracker._L1[_l1_key_normalized("ego", "car3")].hit_count = 1  # 已覆盖
    tracker._L1[_l1_key_normalized("car3", "car4")] = CoverageRecord()
    tracker._L1[_l1_key_normalized("car3", "car4")].hit_count = 1  # 已覆盖

    # L2: 2条路径
    path1_key = _l2_key_normalized("ego", "car1", "car2")
    path2_key = _l2_key_normalized("ego", "car3", "car4")

    tracker._L2[path1_key] = CoverageRecord()
    tracker._L2_meta[path1_key] = {
        "_key": path1_key,
        "path_pattern": "ego→car1→car2",
        "n1_id": "ego", "n2_id": "car1", "n3_id": "car2"
    }

    tracker._L2[path2_key] = CoverageRecord()
    tracker._L2_meta[path2_key] = {
        "_key": path2_key,
        "path_pattern": "ego→car3→car4",
        "n1_id": "ego", "n2_id": "car3", "n3_id": "car4"
    }

    # 测试优先级选择
    selected = tracker.select_gaps_with_priority("L2", top_k=2, adaptive=False)

    print(f"\n选中的gaps:")
    print(f"{'路径':<30} {'未覆盖L0':>12} {'未覆盖L1':>12} {'优先级':>10}")
    print("-" * 66)

    for gap_key, gap_meta, priority in selected:
        path = gap_meta.get("path_pattern", gap_key)
        nodes = path.split("→")

        uncovered_l0 = sum(1 for n in nodes if n and tracker._L0.get(n, CoverageRecord()).hit_count == 0)
        uncovered_l1 = sum(1 for i in range(len(nodes)-1) if not tracker.is_covered_l1(nodes[i], nodes[i+1]))

        print(f"{path:<30} {uncovered_l0:>12} {uncovered_l1:>12} {priority:>10.1f}")

    # 验证优先级计算
    assert len(selected) == 2, "应该选中2个gaps"
    assert selected[0][2] == 50.0, f"path1优先级应该是50，实际是{selected[0][2]}"
    assert selected[1][2] == 10.0, f"path2优先级应该是10，实际是{selected[1][2]}"

    print(f"\n[PASS] 优先级计算正确！")
    print(f"   path1 (ego->car1->car2): 2个未覆盖L0 + 2个未覆盖L1 = 50分")
    print(f"   path2 (ego->car3->car4): 1个未覆盖L0 + 0个未覆盖L1 = 10分")


def test_normalization():
    """测试规范化函数"""
    print(f"\n{'='*60}")
    print("测试2: 边规范化")
    print("="*60)

    # L1规范化
    assert _l1_key_normalized("a", "b") == "a->b"
    assert _l1_key_normalized("b", "a") == "a->b"
    print("[PASS] L1规范化测试通过")

    # L2规范化
    assert _l2_key_normalized("a", "b", "c") == "a->b->c"
    assert _l2_key_normalized("c", "b", "a") == "a->b->c"
    print("[PASS] L2规范化测试通过")


def test_quality_check():
    """测试质量检查函数"""
    print(f"\n{'='*60}")
    print("测试3: 质量检查函数")
    print("="*60)

    from run_gap_pipeline_v6 import check_question_quality

    # 构造测试数据
    qa_pairs = [
        {
            "question_id": "q1",
            "question": "What is the car to the front of ego?",
            "answer": "car1",
            "Template_ID": "L2:type_filter",
            "Topology_Level": "L2"
        },
        {
            "question_id": "q2",
            "question": "What is the truck near building1?",
            "answer": "car2",
            "Template_ID": "L2:referent",
            "Topology_Level": "L2"
        },
        {
            "question_id": "q3",
            "question": "Short",
            "answer": "car3",
            "Template_ID": "L1:direction",
            "Topology_Level": "L1"
        },
        {
            "question_id": "q4",
            "question": "",
            "answer": "car4",
            "Template_ID": "L0:type",
            "Topology_Level": "L0"
        },
    ]

    quality = check_question_quality(qa_pairs)

    print(f"\n质量检查结果:")
    print(f"  总问题数: {quality['total']}")
    print(f"  唯一答案数: {quality['unique_answers']}")
    print(f"  平均问题长度: {quality['avg_question_length']:.1f} 字符")
    print(f"  质量问题数: {len(quality['issues'])}")

    assert quality['total'] == 4
    assert quality['unique_answers'] == 4
    assert len(quality['issues']) >= 2

    print(f"\n[PASS] 质量检查功能正常！")


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("优化功能单元测试")
    print("="*60 + "\n")

    try:
        test_normalization()
        test_priority_calculation()
        test_quality_check()

        print(f"\n{'='*60}")
        print("[SUCCESS] 所有测试通过！")
        print("="*60)

        print(f"\n完成的优化:")
        print("  1. Gap优先级选择策略 (L0x10 + L1x15)")
        print("  2. 边规范化 (无向边去重)")
        print("  3. 质量检查函数")
        print("  4. 批处理参数支持")
        print("  5. 完整流程文档")

    except Exception as e:
        print(f"\n[FAIL] 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
