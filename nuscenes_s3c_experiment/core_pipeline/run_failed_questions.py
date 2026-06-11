"""
错题单独运行脚本

功能：
1. 从之前的测试结果JSON中提取错题
2. 单独运行这些错题进行调试
3. 输出详细的错误分析

使用方法：
    python run_failed_questions.py [--result-file PATH] [--verbose]
"""
import json
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Any
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from vqa_pipeline.pipeline import VQAPipeline, VQAResult
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig


# ==================== 配置 ====================
@dataclass
class FailedQuestion:
    """错题数据"""
    scene_name: str
    frame_idx: int
    question_idx: int  # 1-based
    question: str
    expected: str
    actual: str
    reason: str
    final_cypher: str
    attempts: int


def load_failed_questions(result_file: Path) -> Tuple[List[FailedQuestion], Dict]:
    """从结果文件中提取错题"""
    with open(result_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    failed = []
    for scene in data.get('scenes', []):
        scene_name = scene['scene_name']
        frame_idx = scene['frame_idx']
        
        for i, result in enumerate(scene['results'], 1):
            # 跳过已跳过的题目
            if result.get('actual') == '[SKIPPED]':
                continue
            
            # 提取错题
            if not result.get('correct', False):
                failed.append(FailedQuestion(
                    scene_name=scene_name,
                    frame_idx=frame_idx,
                    question_idx=i,
                    question=result['question'],
                    expected=result['expected'],
                    actual=result.get('actual', ''),
                    reason=result.get('reason', ''),
                    final_cypher=result.get('final_cypher', ''),
                    attempts=result.get('attempts', 0)
                ))
    
    return failed, data


def print_failed_summary(failed: List[FailedQuestion]):
    """打印错题摘要"""
    print("\n" + "=" * 70)
    print(f"  错题列表 (共 {len(failed)} 题)")
    print("=" * 70)
    
    # 按场景分组
    by_scene = {}
    for q in failed:
        key = (q.scene_name, q.frame_idx)
        if key not in by_scene:
            by_scene[key] = []
        by_scene[key].append(q)
    
    for (scene_name, frame_idx), questions in by_scene.items():
        print(f"\n【{scene_name} 帧{frame_idx}】 {len(questions)} 题错误")
        for q in questions:
            print(f"  Q{q.question_idx}: {q.question[:50]}...")
            print(f"       期望: {q.expected}, 实际: {q.actual}")
            print(f"       原因: {q.reason[:50]}..." if len(q.reason) > 50 else f"       原因: {q.reason}")


def run_single_question(
    pipeline: VQAPipeline,
    importer: Neo4jImporter,
    scene_graph: Dict,
    question: str,
    expected: str,
    verbose: bool = True
) -> Dict:
    """运行单个问题"""
    # 清空并导入场景
    importer.clear_database()
    importer.create_schema()
    importer.import_scene(scene_graph)
    
    # 处理问题
    result = pipeline.process_question(question, verbose=verbose)
    
    # 判断正确性
    actual = result.answer.lower().strip() if result.answer else ''
    expected_norm = expected.lower().strip()
    
    # 简单等价判断
    is_correct = actual == expected_norm
    if not is_correct:
        # 等价词检查
        equiv_pairs = [
            ('stopped', 'parked'),
            ('with_rider', 'with rider'),
            ('without_rider', 'without rider'),
            ('standing', 'stopped'),
        ]
        for a, b in equiv_pairs:
            if (actual == a and expected_norm == b) or (actual == b and expected_norm == a):
                is_correct = True
                break
    
    return {
        'question': question,
        'expected': expected,
        'actual': result.answer,
        'correct': is_correct,
        'cypher': result.cypher_query,
        'query_result': result.query_result,
        'success': result.success,
        'error': result.error
    }


def run_failed_questions(
    failed: List[FailedQuestion],
    scene_graph_dir: Path,
    verbose: bool = True,
    max_questions: int = None
):
    """运行所有错题"""
    # 初始化
    config = Neo4jConfig.from_env()
    importer = Neo4jImporter(config)
    pipeline = VQAPipeline(use_ir=False)
    
    if not pipeline.initialize(quiet=True):
        logger.error("Pipeline 初始化失败")
        return
    
    # 按场景分组
    by_scene = {}
    for q in failed:
        key = (q.scene_name, q.frame_idx)
        if key not in by_scene:
            by_scene[key] = []
        by_scene[key].append(q)
    
    results = []
    total = len(failed)
    if max_questions:
        total = min(total, max_questions)
    
    processed = 0
    
    try:
        for (scene_name, frame_idx), questions in by_scene.items():
            # 加载场景图
            scene_file = scene_graph_dir / f"{scene_name}_frame{frame_idx}_scene_graph.json"
            if not scene_file.exists():
                logger.warning(f"找不到场景图: {scene_file}")
                continue
            
            with open(scene_file, 'r', encoding='utf-8') as f:
                scene_graph = json.load(f)
            
            print(f"\n{'=' * 70}")
            print(f"  场景: {scene_name} 帧{frame_idx}")
            print(f"  错题数: {len(questions)}")
            print(f"{'=' * 70}")
            
            for q in questions:
                if max_questions and processed >= max_questions:
                    break
                
                processed += 1
                print(f"\n[{processed}/{total}] Q{q.question_idx}: {q.question}")
                print(f"  原期望: {q.expected}")
                print(f"  原实际: {q.actual}")
                print(f"  原因: {q.reason}")
                
                # 重新运行
                result = run_single_question(
                    pipeline, importer, scene_graph,
                    q.question, q.expected, verbose=verbose
                )
                
                status = "✅ 现在正确" if result['correct'] else "❌ 仍然错误"
                print(f"\n  {status}")
                print(f"  新答案: {result['actual']}")
                
                results.append({
                    'scene_name': scene_name,
                    'frame_idx': frame_idx,
                    'question_idx': q.question_idx,
                    **result
                })
                
                if max_questions and processed >= max_questions:
                    break
    
    finally:
        pipeline.close()
        importer.close()
    
    # 统计
    print("\n" + "=" * 70)
    print("  错题重跑统计")
    print("=" * 70)
    
    fixed = sum(1 for r in results if r['correct'])
    still_wrong = len(results) - fixed
    
    print(f"  总错题数: {len(failed)}")
    print(f"  本次运行: {len(results)}")
    print(f"  已修复: {fixed}")
    print(f"  仍错误: {still_wrong}")
    
    if still_wrong > 0:
        print("\n  仍然错误的题目:")
        for r in results:
            if not r['correct']:
                print(f"    {r['scene_name']} 帧{r['frame_idx']} Q{r['question_idx']}")
                print(f"      问题: {r['question'][:50]}...")
                print(f"      期望: {r['expected']}, 实际: {r['actual']}")
    
    return results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='运行错题')
    parser.add_argument('--result-file', type=str, default=None,
                        help='测试结果JSON文件路径（默认使用最新的）')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='详细输出')
    parser.add_argument('--max', '-n', type=int, default=None,
                        help='最多运行N道错题')
    parser.add_argument('--list-only', '-l', action='store_true',
                        help='只列出错题，不运行')
    args = parser.parse_args()
    
    # 查找结果文件
    result_dir = Path(__file__).parent / 'output' / 'coverage_analysis' / 'vqa_results'
    
    if args.result_file:
        result_file = Path(args.result_file)
    else:
        # 找最新的结果文件
        json_files = list(result_dir.glob('enhanced_qa_test_*.json'))
        if not json_files:
            logger.error("找不到测试结果文件")
            return
        result_file = max(json_files, key=lambda f: f.stat().st_mtime)
    
    print(f"使用结果文件: {result_file}")
    
    # 加载错题
    failed, data = load_failed_questions(result_file)
    
    if not failed:
        print("没有错题！🎉")
        return
    
    # 打印摘要
    print_failed_summary(failed)
    
    if args.list_only:
        return
    
    # 运行错题
    scene_graph_dir = Path(__file__).parent / 'output' / 'coverage_analysis' / 'scene_graphs'
    
    print("\n开始运行错题...")
    results = run_failed_questions(
        failed,
        scene_graph_dir,
        verbose=args.verbose,
        max_questions=args.max
    )
    
    # 保存结果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = result_dir / f'failed_rerun_{timestamp}.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {output_file}")


if __name__ == '__main__':
    main()
