"""
测试 v3 变更: 模板清理 + Cypher 集成 + heading 支持
"""
import sys
sys.path.insert(0, r'E:\Project\ADVTEST\nuscenes_s3c_experiment')

from core_pipeline.qa_generator_v2.cypher_integration import (
    Neo4jImporter, CypherTemplates, CypherResultParser,
    CoverageContribution, extract_coverage_from_path, build_scene_summary,
)
from core_pipeline.qa_generator_v2.cypher_executor import (
    InMemoryGraphEngine, CypherExecutor,
)
from core_pipeline.qa_generator_v2.template_library import (
    get_template_library, ALL_TEMPLATES,
)
from core_pipeline.qa_generator_v2.config import QUESTION_TYPES


def test_template_cleanup():
    """验证模板清理: 无 count/velocity/approaching/精确米数"""
    print("=" * 60)
    print("  TEST 1: Template Cleanup")
    print("=" * 60)

    count_t = [t for t in ALL_TEMPLATES if t.question_type == "count"]
    vel_t = [t for t in ALL_TEMPLATES if "vel" in t.template_id]
    appr_t = [t for t in ALL_TEMPLATES if "approaching" in t.major_pattern]
    meter_t = [t for t in ALL_TEMPLATES if "distance_threshold" in str(t.required_params)]

    assert len(count_t) == 0, f"Count templates still present: {[t.template_id for t in count_t]}"
    assert len(vel_t) == 0, f"Velocity templates still present: {[t.template_id for t in vel_t]}"
    assert len(appr_t) == 0, f"Approaching templates still present: {[t.template_id for t in appr_t]}"
    assert len(meter_t) == 0, f"Exact-meter templates still present: {[t.template_id for t in meter_t]}"

    assert "count" not in QUESTION_TYPES, "count still in QUESTION_TYPES"

    print(f"  Total templates: {len(ALL_TEMPLATES)}")
    print(f"  count=0, velocity=0, approaching=0, exact-meter=0")
    print(f"  QUESTION_TYPES: {QUESTION_TYPES}")
    print("  PASSED\n")


def test_heading_templates():
    """验证 heading 模板存在"""
    print("=" * 60)
    print("  TEST 2: Heading Templates")
    print("=" * 60)

    lib = get_template_library()
    heading_templates = [t for t in ALL_TEMPLATES if "heading" in t.major_pattern]

    assert len(heading_templates) >= 10, f"Expected >=10 heading templates, got {len(heading_templates)}"

    l0_h = [t for t in heading_templates if t.coverage_level == "L0"]
    l1_h = [t for t in heading_templates if t.coverage_level == "L1"]
    l2_h = [t for t in heading_templates if t.coverage_level == "L2"]

    print(f"  Heading templates: {len(heading_templates)} total")
    print(f"    L0: {len(l0_h)}")
    print(f"    L1: {len(l1_h)}")
    print(f"    L2: {len(l2_h)}")

    for t in heading_templates:
        print(f"    [{t.template_id}] {t.template[:60]}...")

    print("  PASSED\n")


def test_l2_pattern_categorization():
    """验证 L2 模式分类: CHAIN / STATUS / COMPLEX"""
    print("=" * 60)
    print("  TEST 3: L2 Pattern Categorization")
    print("=" * 60)

    l2 = [t for t in ALL_TEMPLATES if t.coverage_level == "L2"]

    chain = [t for t in l2 if "chain" in t.major_pattern]
    status = [t for t in l2 if "same_status" in t.major_pattern or "shared_status" in t.major_pattern]
    complex_ = [t for t in l2 if "both_directions" in t.major_pattern
                or "two_direction" in t.major_pattern
                or "id_vs_direction" in t.major_pattern]

    print(f"  L2 total: {len(l2)}")
    print(f"  [CHAIN]   strict chain A→B→C: {len(chain)}")
    print(f"  [STATUS]  status bidirectional: {len(status)}")
    print(f"  [COMPLEX] complex scenarios:    {len(complex_)}")

    assert len(chain) >= 15, f"Expected >=15 CHAIN templates, got {len(chain)}"
    assert len(status) >= 5, f"Expected >=5 STATUS templates, got {len(status)}"
    assert len(complex_) >= 5, f"Expected >=5 COMPLEX templates, got {len(complex_)}"

    print("  PASSED\n")


def test_in_memory_engine():
    """验证 InMemoryGraphEngine 基本功能"""
    print("=" * 60)
    print("  TEST 4: InMemoryGraphEngine")
    print("=" * 60)

    scene = {
        "scene_name": "test",
        "nodes": [
            {"unique_id": "ego", "type": "ego", "status": "moving"},
            {"unique_id": "car1", "type": "car", "status": "moving",
             "heading_class": "facing_ego"},
            {"unique_id": "ped1", "type": "pedestrian", "status": "standing",
             "heading_class": "lateral_left"},
            {"unique_id": "truck1", "type": "truck", "status": "stopped",
             "heading_class": "away_from_ego"},
        ],
        "edges": [
            {"source": "ego", "target": "car1",
             "direction_8": "front", "distance_bin": "near"},
            {"source": "ego", "target": "ped1",
             "direction_8": "left", "distance_bin": "very_near"},
            {"source": "ego", "target": "truck1",
             "direction_8": "front-right", "distance_bin": "visible"},
            {"source": "car1", "target": "ped1",
             "direction_8": "left", "distance_bin": "near"},
            {"source": "car1", "target": "truck1",
             "direction_8": "right", "distance_bin": "near"},
        ],
    }

    engine = InMemoryGraphEngine(scene)

    # 节点
    nodes = engine.enumerate_all_nodes()
    assert len(nodes) == 3, f"Expected 3 non-ego nodes, got {len(nodes)}"
    print(f"  Nodes: {len(nodes)}")

    # 边
    edges = engine.enumerate_all_edges()
    assert len(edges) == 5, f"Expected 5 edges, got {len(edges)}"
    print(f"  Edges: {len(edges)}")

    # 两跳路径
    paths = engine.enumerate_all_2hop_paths()
    print(f"  2-hop paths: {len(paths)}")
    for p in paths:
        print(f"    {p['n1']} --[{p['d1']}]--> {p['n2']} --[{p['d2']}]--> {p['n3']}")

    # ego→[front]→car1→[left]→ped1 应该存在
    assert any(p["n1"] == "ego" and p["n2"] == "car1" and p["n3"] == "ped1"
               for p in paths), "Missing path ego→car1→ped1"

    # L2 chain query
    results = engine.query_l2_chain_exist("ego", "front", "car", "left", "pedestrian")
    assert len(results) >= 1, "L2 chain query should find ego→car1→ped1"
    print(f"  L2 chain ego→[front]→car→[left]→ped: {len(results)} result(s)")

    # L1 heading query
    heading = engine.query_l1_heading("ego", "front")
    assert len(heading) >= 1, "Should find car1 to the front"
    assert heading[0]["heading"] == "facing_ego", f"car1 should be facing_ego, got {heading[0]['heading']}"
    print(f"  L1 heading ego→[front]: {heading[0]}")

    # Coverage contribution
    contrib_records = engine.query_l2_coverage_contribution("ego", "car1", "ped1")
    assert len(contrib_records) == 1
    contrib = extract_coverage_from_path(contrib_records[0])
    assert "car1" in contrib.l0_nodes
    assert "ped1" in contrib.l0_nodes
    assert len(contrib.l1_edges) == 2
    assert len(contrib.l2_paths) == 1
    print(f"  Coverage contribution: L0={contrib.l0_nodes}, "
          f"L1={len(contrib.l1_edges)} edges, L2={len(contrib.l2_paths)} paths")

    print("  PASSED\n")


def test_cypher_executor():
    """验证 CypherExecutor 统一接口"""
    print("=" * 60)
    print("  TEST 5: CypherExecutor")
    print("=" * 60)

    scene = {
        "scene_name": "test",
        "nodes": [
            {"unique_id": "ego", "type": "ego", "status": "moving"},
            {"unique_id": "car1", "type": "car", "status": "moving",
             "heading_class": "facing_ego"},
            {"unique_id": "ped1", "type": "pedestrian", "status": "standing"},
        ],
        "edges": [
            {"source": "ego", "target": "car1",
             "direction_8": "front", "distance_bin": "near"},
            {"source": "ego", "target": "ped1",
             "direction_8": "left", "distance_bin": "very_near"},
            {"source": "car1", "target": "ped1",
             "direction_8": "left", "distance_bin": "near"},
        ],
    }

    executor = CypherExecutor(scene, backend="memory")

    nodes = executor.enumerate_nodes()
    assert len(nodes) == 2
    print(f"  Nodes: {len(nodes)}")

    paths = executor.enumerate_2hop_paths()
    assert len(paths) >= 1
    print(f"  2-hop paths: {len(paths)}")

    # L2 coverage contribution
    contrib = executor.compute_l2_coverage_contribution("ego", "car1", "ped1")
    assert len(contrib.l0_nodes) >= 2
    print(f"  L2 contrib: L0={contrib.l0_nodes}, L1={len(contrib.l1_edges)} edges")

    # Scene summary
    summary = executor.get_scene_summary()
    assert "car" in summary
    print(f"  Scene summary length: {len(summary)} chars")

    print("  PASSED\n")


def test_scene_summary():
    """验证场景摘要生成"""
    print("=" * 60)
    print("  TEST 6: Scene Summary")
    print("=" * 60)

    scene = {
        "nodes": [
            {"unique_id": "ego", "type": "ego"},
            {"unique_id": "car1", "type": "car", "status": "moving",
             "heading_class": "facing_ego"},
            {"unique_id": "car2", "type": "car", "status": "stopped",
             "heading_class": "away_from_ego"},
            {"unique_id": "ped1", "type": "pedestrian", "status": "standing"},
        ],
        "edges": [
            {"source": "ego", "target": "car1",
             "direction_8": "front", "distance_bin": "near"},
            {"source": "ego", "target": "car2",
             "direction_8": "rear", "distance_bin": "visible"},
            {"source": "ego", "target": "ped1",
             "direction_8": "left", "distance_bin": "very_near"},
        ],
    }

    summary = build_scene_summary(scene)
    print(summary)
    assert "car: 2" in summary
    assert "pedestrian: 1" in summary
    assert "front" in summary

    print("\n  PASSED\n")


if __name__ == "__main__":
    test_template_cleanup()
    test_heading_templates()
    test_l2_pattern_categorization()
    test_in_memory_engine()
    test_cypher_executor()
    test_scene_summary()

    print("=" * 60)
    print("  ALL TESTS PASSED")
    print("=" * 60)
