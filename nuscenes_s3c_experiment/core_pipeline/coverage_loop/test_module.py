"""
测试覆盖率闭环模块
"""
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_unified_coverage():
    """测试统一覆盖率数据结构"""
    print("=" * 60)
    print("测试 UnifiedCoverageStats")
    print("=" * 60)
    
    from coverage_loop.unified_coverage import UnifiedCoverageStats
    
    stats = UnifiedCoverageStats()
    stats.scene_name = "scene-0103"
    stats.frame_idx = 25
    stats.total_nodes = 10
    stats.total_edges = 50
    
    # 添加覆盖
    stats.add_node_coverage("car1")
    stats.add_node_coverage("car2")
    stats.add_node_coverage("pedestrian1")
    stats.add_edge_coverage("ego", "front", "car1")
    stats.add_direction_coverage("front")
    
    rates = stats.get_coverage_rates()
    print(f"场景: {stats.scene_name} 帧{stats.frame_idx}")
    print(f"L0 (节点): {len(stats.covered_nodes)}/{stats.total_nodes} = {rates['L0']:.1%}")
    print(f"L1 (边): {len(stats.covered_edges)}/{stats.total_edges} = {rates['L1']:.1%}")
    print(f"覆盖的节点: {sorted(stats.covered_nodes)}")
    print("✓ UnifiedCoverageStats 测试通过\n")
    
    return stats


def test_coverage_adapter():
    """测试格式适配器"""
    print("=" * 60)
    print("测试 CoverageAdapter")
    print("=" * 60)
    
    from coverage_loop.unified_coverage import UnifiedCoverageStats, CoverageAdapter
    
    # 模拟coverage_pipeline的输出
    pipeline_result = {
        'scene': {'name': 'scene-0103', 'frame_idx': 25},
        'totals': {'nodes': 48, 'edges': 1122, '2hop': 5000},
        'coverage': {
            'L0': {'covered': 20, 'total': 48, 'rate': 0.416, 'nodes': ['car1', 'car2', 'pedestrian1']},
            'L1': {'covered': 100, 'total': 1122, 'rate': 0.089},
            'L2': {'covered': 50, 'total': 5000, 'rate': 0.01}
        },
        'details': []
    }
    
    stats = CoverageAdapter.from_coverage_pipeline_result(pipeline_result)
    print(f"从coverage_pipeline转换: {stats.scene_name} 帧{stats.frame_idx}")
    print(f"节点总数: {stats.total_nodes}, 边总数: {stats.total_edges}")
    print(f"覆盖节点: {sorted(stats.covered_nodes)}")
    
    # 转换回qa_generator格式
    qa_format = CoverageAdapter.to_qa_generator_format(stats)
    print(f"转回qa_generator格式: {list(qa_format.keys())}")
    print("✓ CoverageAdapter 测试通过\n")


def test_loop_controller_init():
    """测试闭环控制器初始化"""
    print("=" * 60)
    print("测试 CoverageLoopController 初始化")
    print("=" * 60)
    
    from coverage_loop.loop_controller import CoverageLoopController, LoopConfig
    
    config = LoopConfig(
        target_l0_coverage=0.7,
        target_l1_coverage=0.3,
        max_iterations=3,
        questions_per_iteration=5,
        verify_answers=False,
    )
    
    controller = CoverageLoopController(config)
    print(f"配置: L0目标={config.target_l0_coverage:.0%}, L1目标={config.target_l1_coverage:.0%}")
    print(f"最大迭代: {config.max_iterations}, 每次生成: {config.questions_per_iteration}")
    print("✓ CoverageLoopController 初始化测试通过\n")
    
    return controller


def test_find_scene_graph():
    """查找可用的场景图"""
    print("=" * 60)
    print("查找场景图文件")
    print("=" * 60)
    
    search_paths = [
        Path(__file__).parent.parent / "output" / "scene_graphs",
        Path(__file__).parent.parent.parent / "output" / "coverage_analysis" / "scene_graphs",
    ]
    
    available = []
    for p in search_paths:
        if p.exists():
            found = list(p.glob("*_scene_graph.json"))
            found = [f for f in found if 'all_scene' not in f.name]
            available.extend(found)
            if found:
                print(f"在 {p} 找到 {len(found)} 个场景图")
    
    if available:
        print(f"\n可用场景图:")
        for f in available[:5]:
            print(f"  - {f.name}")
        if len(available) > 5:
            print(f"  ... 还有 {len(available) - 5} 个")
        print(f"\n首选: {available[0]}")
        return available[0]
    else:
        print("未找到场景图文件")
        return None


def main():
    print("\n" + "=" * 60)
    print("  覆盖率闭环模块测试")
    print("=" * 60 + "\n")
    
    try:
        test_unified_coverage()
        test_coverage_adapter()
        test_loop_controller_init()
        scene_graph = test_find_scene_graph()
        
        print("\n" + "=" * 60)
        print("  所有测试通过! ✓")
        print("=" * 60)
        
        if scene_graph:
            print(f"\n下一步: 运行完整闭环")
            print(f"  python -m coverage_loop.run_loop --scene-graph {scene_graph}")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
