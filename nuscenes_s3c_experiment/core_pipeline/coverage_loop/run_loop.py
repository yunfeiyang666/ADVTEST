"""
运行覆盖率驱动问题生成闭环 - 快速启动脚本

使用方法:
    python run_loop.py                           # 使用默认场景
    python run_loop.py --scene-graph path/to/sg.json  # 指定场景图
"""

import sys
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from coverage_loop import CoverageLoopController
from coverage_loop.loop_controller import LoopConfig


def main():
    # 默认配置
    DEFAULT_OUTPUT = Path(__file__).parent / "output" / "loop_results"
    
    # 查找可用的场景图 - 多个位置搜索
    search_paths = [
        Path(__file__).parent.parent.parent / "output" / "coverage_analysis" / "scene_graphs",
        Path(__file__).parent.parent / "output" / "scene_graphs",
        Path(__file__).parent.parent.parent / "output" / "scene_graphs",
    ]
    
    available_scenes = []
    for search_dir in search_paths:
        if search_dir.exists():
            found = list(search_dir.glob("*_scene_graph.json"))
            # 过滤掉合集文件
            found = [f for f in found if 'all_scene' not in f.name]
            available_scenes.extend(found)
        if available_scenes:
            break
    
    if not available_scenes:
        print("❌ 未找到场景图文件")
        print("请指定场景图路径: python run_loop.py --scene-graph path/to/sg.json")
        return
    
    # 使用第一个可用场景
    scene_graph_path = available_scenes[0]
    print(f"✓ 使用场景图: {scene_graph_path}")
    
    # 查找对应的覆盖率数据文件
    coverage_data_dir = Path(__file__).parent.parent.parent / "output" / "coverage_final_fixed"
    print(f"✓ 覆盖率数据目录: {coverage_data_dir}")
    
    # 创建输出目录
    output_dir = DEFAULT_OUTPUT
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 配置
    config = LoopConfig(
        target_l0_coverage=0.50,      # 从7.8%提升到50%
        target_l1_coverage=0.10,      # L1边覆盖率目标10%
        max_iterations=5,              # 先跑5轮测试
        questions_per_iteration=10,
        verify_answers=False,          # 先关闭VQA验证，加快测试
        save_intermediate=True,
        coverage_data_dir=str(coverage_data_dir),  # 指定覆盖率数据目录
    )
    
    print(f"\n配置:")
    print(f"  - 目标L0覆盖率: {config.target_l0_coverage:.0%}")
    print(f"  - 目标L1覆盖率: {config.target_l1_coverage:.0%}")
    print(f"  - 最大迭代次数: {config.max_iterations}")
    print(f"  - 每次生成问题: {config.questions_per_iteration}")
    print(f"  - VQA验证: {'开启' if config.verify_answers else '关闭'}")
    print(f"  - 输出目录: {output_dir}")
    print(f"\n⚠️  初始覆盖率将从NuScenesQA分析结果加载（非0开始）")
    
    # 运行闭环
    controller = CoverageLoopController(config)
    result = controller.run(
        scene_graph_path=str(scene_graph_path),
        output_dir=str(output_dir),
    )
    
    print("\n" + "=" * 60)
    print("  运行结果")
    print("=" * 60)
    
    if result.get('success'):
        print(f"✓ 成功完成!")
        print(f"  - 迭代次数: {result['total_iterations']}")
        print(f"  - 生成问题: {result['total_questions']}")
        coverage = result['final_coverage']
        print(f"  - 最终覆盖率: L0={coverage['L0']:.1%}, L1={coverage['L1']:.1%}, L2={coverage['L2']:.1%}")
        print(f"  - 输出目录: {result['output_dir']}")
    else:
        print(f"❌ 运行失败: {result.get('error', '未知错误')}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="覆盖率驱动问题生成闭环")
    parser.add_argument("--scene-graph", "-s", help="场景图JSON文件路径")
    parser.add_argument("--output", "-o", help="输出目录")
    parser.add_argument("--target-l0", type=float, default=0.7, help="L0目标覆盖率")
    parser.add_argument("--max-iter", type=int, default=5, help="最大迭代次数")
    
    args = parser.parse_args()
    
    if args.scene_graph or args.output:
        # 使用命令行参数
        config = LoopConfig(
            target_l0_coverage=args.target_l0,
            max_iterations=args.max_iter,
            verify_answers=False,
        )
        
        controller = CoverageLoopController(config)
        result = controller.run(
            scene_graph_path=args.scene_graph or str(Path(__file__).parent.parent / "output" / "scene_graphs" / "scene-0103_frame25_scene_graph.json"),
            output_dir=args.output or str(Path(__file__).parent / "output" / "loop_results"),
        )
        print(f"\n结果: {result}")
    else:
        main()
