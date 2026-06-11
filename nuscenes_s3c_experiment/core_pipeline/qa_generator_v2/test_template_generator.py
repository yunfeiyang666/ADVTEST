"""
快速测试模板库 + 确定性填充 + 覆盖率驱动生成
"""
import sys
import json
import logging
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(message)s")

def test_template_library():
    """测试模板库四级结构"""
    from core_pipeline.qa_generator_v2.template_library import get_template_library
    
    lib = get_template_library()
    lib.print_hierarchy()
    
    summary = lib.summary()
    print(f"\n✓ 模板库加载成功: {summary['total']} 个模板")
    return True

def test_template_filler(scene_graph_path: str):
    """测试模板填充器"""
    from core_pipeline.qa_generator_v2.template_filler import TemplateFiller
    
    with open(scene_graph_path, "r", encoding="utf-8") as f:
        scene_data = json.load(f)
    
    filler = TemplateFiller(scene_data)
    idx = filler.index
    
    print(f"\n场景图索引:")
    print(f"  节点数: {len(idx.non_ego_nodes)} (非ego)")
    print(f"  边数: {len(idx.edges)}")
    print(f"  类型分布: {dict((t, len(ns)) for t, ns in idx.nodes_by_type.items() if t != 'ego')}")
    
    # 测试 L0 填充
    if idx.non_ego_nodes:
        test_node = idx.non_ego_nodes[0]
        nid = test_node.get("unique_id", "")
        print(f"\n--- L0 测试: node={nid} ---")
        l0_qa = filler.fill_for_node_gap(nid, ["exist", "status"])
        for qa in l0_qa[:3]:
            print(f"  Q: {qa.question}")
            print(f"  A: {qa.answer}  (template: {qa.template_id})")
    
    # 测试 L1 填充
    if idx.edges:
        test_edge = idx.edges[0]
        src = test_edge.get("source", "")
        tgt = test_edge.get("target", "")
        d8 = idx._get_direction_8(test_edge)
        if d8:
            print(f"\n--- L1 测试: {src}→{tgt} direction={d8} ---")
            l1_qa = filler.fill_for_edge_gap(src, tgt, d8, ["exist", "count"])
            for qa in l1_qa[:3]:
                print(f"  Q: {qa.question}")
                print(f"  A: {qa.answer}  (template: {qa.template_id})")
    
    # 测试缺口提取 (空覆盖)
    gaps = filler.extract_gaps_from_coverage(None)
    print(f"\n缺口提取 (空覆盖): {len(gaps)} 个")
    
    print(f"\n✓ 模板填充器测试通过")
    return True

def test_coverage_driven_generator(scene_graph_path: str):
    """测试覆盖率驱动生成器"""
    from core_pipeline.qa_generator_v2.coverage_driven_template_generator import (
        CoverageDrivenTemplateGenerator, CoverageGoal
    )
    
    generator = CoverageDrivenTemplateGenerator.from_scene_graph_file(
        scene_graph_path, seed=42)
    
    goal = CoverageGoal(
        l0_target=1.0,
        l1_target=0.5,
        l2_target=0.3,
        max_questions=30,
    )
    
    print(f"\n--- 覆盖率驱动生成 (目标: L0=100%, L1=50%, L2=30%, 预算=30题) ---")
    result = generator.generate(coverage_stats=None, goal=goal)
    
    print(f"\n生成结果:")
    print(f"  题数: {len(result.questions)}")
    print(f"  耗时: {result.generation_time:.3f}s")
    print(f"  覆盖率变化:")
    for level in ["L0", "L1", "L2"]:
        before = result.coverage_before[level]
        after = result.coverage_after[level]
        print(f"    {level}: {before:.1%} → {after:.1%}")
    
    # 按类型统计
    type_counts = {}
    level_counts = {}
    for q in result.questions:
        qt = q["question_type"]
        cl = q["coverage_level"]
        type_counts[qt] = type_counts.get(qt, 0) + 1
        level_counts[cl] = level_counts.get(cl, 0) + 1
    
    print(f"\n  按类型: {type_counts}")
    print(f"  按级别: {level_counts}")
    print(f"  模板使用: {result.template_stats}")
    
    # 打印前5个问题示例
    print(f"\n  示例问题:")
    for q in result.questions[:5]:
        print(f"    [{q['coverage_level']}][{q['question_type']}] Q: {q['question']}")
        print(f"      A: {q['answer']}")
    
    print(f"\n✓ 覆盖率驱动生成器测试通过")
    return True


if __name__ == "__main__":
    # 查找场景图文件
    sg_dir = Path(__file__).parent.parent / "output" / "coverage_analysis" / "scene_graphs"
    sg_files = list(sg_dir.glob("scene-*_scene_graph.json"))
    
    if not sg_files:
        print("未找到场景图文件，仅测试模板库")
        test_template_library()
    else:
        sg_path = str(sg_files[0])
        print(f"使用场景图: {sg_path}\n")
        
        test_template_library()
        test_template_filler(sg_path)
        test_coverage_driven_generator(sg_path)
