"""
运行 QA Generator

从场景图生成问答对，支持：
- 单个场景图文件
- 批量处理多个场景图
- 输出两种格式（完整版 / CV模型简化版）
"""
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

# 添加父目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent))

from qa_generator import QAGenerator, QA_CONFIG
from qa_generator.generator import generate_qa_from_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def process_single_scene(scene_graph_path: str, output_dir: str, 
                         max_questions: int = None) -> dict:
    """
    处理单个场景图
    
    Args:
        scene_graph_path: 场景图JSON文件路径
        output_dir: 输出目录
        max_questions: 最大问题数量
    
    Returns:
        统计信息字典
    """
    logger.info(f"Processing: {scene_graph_path}")
    
    # 读取场景图
    with open(scene_graph_path, "r", encoding="utf-8") as f:
        scene_data = json.load(f)
    
    scene_name = scene_data.get("scene_name", "unknown")
    frame_idx = scene_data.get("frame_idx", 0)
    
    # 生成问答对
    generator = QAGenerator()
    qa_pairs = generator.generate_from_scene_graph(scene_data, max_questions)
    
    # 准备输出路径
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    base_name = f"{scene_name}_frame{frame_idx}"
    
    # 保存完整版
    full_output_path = output_dir / f"{base_name}_qa_full.json"
    generator.save_qa_pairs(qa_pairs, str(full_output_path))
    
    # 保存CV模型简化版（带选项）
    cv_with_options = generator.format_for_cv_model(qa_pairs, with_options=True)
    cv_options_path = output_dir / f"{base_name}_qa_cv_options.json"
    with open(cv_options_path, "w", encoding="utf-8") as f:
        json.dump({
            "scene_name": scene_name,
            "frame_idx": frame_idx,
            "direction_frame": "source",
            "mode": "with_options",
            "questions": cv_with_options
        }, f, ensure_ascii=False, indent=2)
    
    # 保存CV模型简化版（无选项）
    cv_no_options = generator.format_for_cv_model(qa_pairs, with_options=False)
    cv_no_options_path = output_dir / f"{base_name}_qa_cv_open.json"
    with open(cv_no_options_path, "w", encoding="utf-8") as f:
        json.dump({
            "scene_name": scene_name,
            "frame_idx": frame_idx,
            "direction_frame": "source",
            "mode": "open_ended",
            "questions": cv_no_options
        }, f, ensure_ascii=False, indent=2)
    
    # 统计
    stats = {
        "scene_name": scene_name,
        "frame_idx": frame_idx,
        "total_questions": len(qa_pairs),
        "by_difficulty": {},
        "by_type": {},
        "output_files": [
            str(full_output_path),
            str(cv_options_path),
            str(cv_no_options_path)
        ]
    }
    
    for qa in qa_pairs:
        stats["by_difficulty"][qa.difficulty] = stats["by_difficulty"].get(qa.difficulty, 0) + 1
        stats["by_type"][qa.question_type] = stats["by_type"].get(qa.question_type, 0) + 1
    
    logger.info(f"  Generated {len(qa_pairs)} questions")
    logger.info(f"  By difficulty: {stats['by_difficulty']}")
    logger.info(f"  By type: {stats['by_type']}")
    
    return stats


def process_batch(scene_graph_dir: str, output_dir: str, 
                  max_questions_per_scene: int = None) -> list:
    """
    批量处理场景图目录
    
    Args:
        scene_graph_dir: 场景图目录
        output_dir: 输出目录
        max_questions_per_scene: 每个场景最大问题数量
    
    Returns:
        所有场景的统计信息列表
    """
    scene_graph_dir = Path(scene_graph_dir)
    all_stats = []
    
    # 查找所有场景图文件
    scene_files = list(scene_graph_dir.glob("*_scene_graph.json"))
    logger.info(f"Found {len(scene_files)} scene graph files")
    
    for scene_file in scene_files:
        try:
            stats = process_single_scene(
                str(scene_file), 
                output_dir, 
                max_questions_per_scene
            )
            all_stats.append(stats)
        except Exception as e:
            logger.error(f"Error processing {scene_file}: {e}")
            continue
    
    # 保存汇总统计
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_scenes": len(all_stats),
        "total_questions": sum(s["total_questions"] for s in all_stats),
        "config": QA_CONFIG,
        "scenes": all_stats
    }
    
    summary_path = Path(output_dir) / "qa_generation_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Batch processing complete!")
    logger.info(f"Total scenes: {len(all_stats)}")
    logger.info(f"Total questions: {summary['total_questions']}")
    logger.info(f"Summary saved to: {summary_path}")
    
    return all_stats


def demo():
    """演示：使用现有的场景图文件"""
    scene_graph_dir = Path(__file__).parent / "output" / "coverage_analysis" / "scene_graphs"
    output_dir = Path(__file__).parent / "output" / "qa_generated"
    
    if not scene_graph_dir.exists():
        logger.error(f"Scene graph directory not found: {scene_graph_dir}")
        logger.info("Please run generate_selected_scenes_improved.py first to generate scene graphs.")
        return
    
    # 找一个示例场景图
    scene_files = list(scene_graph_dir.glob("*_scene_graph.json"))
    if not scene_files:
        logger.error("No scene graph files found.")
        return
    
    # 处理第一个场景
    logger.info(f"Demo: Processing {scene_files[0].name}")
    stats = process_single_scene(str(scene_files[0]), str(output_dir), max_questions=50)
    
    # 打印一些示例问答
    full_output = output_dir / f"{stats['scene_name']}_frame{stats['frame_idx']}_qa_full.json"
    with open(full_output, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print("\n" + "="*60)
    print("  示例问答对 (Source Frame)")
    print("="*60)
    
    for qa in data["qa_pairs"][:10]:
        print(f"\n[{qa['difficulty']}] {qa['question']}")
        print(f"  答案: {qa['answer']}")
        if qa['target_objects']:
            print(f"  目标对象: {qa['target_objects']}")
        if qa['reference_objects']:
            print(f"  参考对象: {qa['reference_objects']}")
        if qa['directions_used']:
            print(f"  方向: {qa['directions_used']}")
        if qa['with_options']:
            print(f"  选项: {qa['with_options']['formatted_options']}")


def main():
    parser = argparse.ArgumentParser(description="QA Generator - 从场景图生成问答对")
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # 单文件处理
    single_parser = subparsers.add_parser("single", help="处理单个场景图")
    single_parser.add_argument("scene_graph", type=str, help="场景图JSON文件路径")
    single_parser.add_argument("-o", "--output", type=str, default="output/qa_generated",
                               help="输出目录")
    single_parser.add_argument("-n", "--max-questions", type=int, default=None,
                               help="最大问题数量")
    
    # 批量处理
    batch_parser = subparsers.add_parser("batch", help="批量处理场景图目录")
    batch_parser.add_argument("scene_dir", type=str, help="场景图目录")
    batch_parser.add_argument("-o", "--output", type=str, default="output/qa_generated",
                              help="输出目录")
    batch_parser.add_argument("-n", "--max-questions", type=int, default=100,
                              help="每个场景最大问题数量")
    
    # 演示
    demo_parser = subparsers.add_parser("demo", help="运行演示")
    
    args = parser.parse_args()
    
    if args.command == "single":
        process_single_scene(args.scene_graph, args.output, args.max_questions)
    elif args.command == "batch":
        process_batch(args.scene_dir, args.output, args.max_questions)
    elif args.command == "demo":
        demo()
    else:
        parser.print_help()
        print("\n运行演示: python run_qa_generator.py demo")


if __name__ == "__main__":
    main()
