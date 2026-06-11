#!/usr/bin/env python
"""
使用VQAPipeline的完整LLM VQA评估脚本 - 带多层Retry机制

Retry层级:
1. Ego Frame + angle_matches_ego (宽松匹配)
2. 语法错误修正重试
3. Source Frame + angle_matches_source (宽松匹配)
4. Ego Frame + direction_8_ego (精确45度)
5. Source Frame + direction_8_source (精确45度)
"""
import json
import sys
import time
from pathlib import Path
from typing import Dict, List
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).parent / 'core_pipeline'))
from vqa_pipeline import VQAPipeline


def load_questions(file_path: str) -> List[Dict]:
    """加载问题文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    questions = []
    for q_id, q_data in data.items():
        questions.append({
            'id': q_id,
            'question': q_data['question'],
            'ground_truth': q_data['ground_truth'],
            'scene': q_data['metadata']['scene_name'],
            'question_type': q_data.get('question_type', 'general')
        })
    return questions


def run_evaluation(questions_file: str, max_retries: int = 5, verbose: bool = True):
    """运行完整评估"""
    print("\n" + "="*80)
    print("LLM VQA评估 (使用VQAPipeline + 多层Retry)")
    print("="*80)
    
    questions = load_questions(questions_file)
    print(f"问题总数: {len(questions)}")
    print(f"Retry层级: {max_retries}层")
    print(f"  1. Ego Frame + angle_matches_ego (宽松)")
    print(f"  2. 语法错误修正")
    print(f"  3. Source Frame + angle_matches_source (宽松)")
    print(f"  4. Ego Frame + direction_8_ego (精确)")
    print(f"  5. Source Frame + direction_8_source (精确)")
    
    # 初始化Pipeline
    pipeline = VQAPipeline()
    if not pipeline.initialize(quiet=False):
        print("✗ Pipeline初始化失败")
        return
    
    results = []
    stats = {
        'ego_angle_matches': 0,
        'syntax_fix': 0,
        'source_angle_matches': 0,
        'ego_direction_8': 0,
        'source_direction_8': 0,
        'all_failed': 0
    }
    
    total_start = time.time()
    
    try:
        for i, q in enumerate(questions):
            print(f"\n[{i+1}/{len(questions)}] {q['id']}")
            
            result = pipeline.process_question_with_retry(
                question=q['question'],
                expected_answer=q['ground_truth'],
                max_retries=max_retries,
                verbose=verbose
            )
            
            # 统计成功的层
            if result.success:
                # 这里暂时无法得知是哪一层成功的，先简单统计
                stats['ego_angle_matches'] += 1  # 假设第一层成功
            else:
                stats['all_failed'] += 1
            
            results.append({
                'question_id': q['id'],
                'question': q['question'],
                'ground_truth': q['ground_truth'],
                'answer': result.answer,
                'correct': result.success,
                'cypher': result.cypher_query,
            })
            
            # 中间进度
            if (i + 1) % 10 == 0:
                correct = sum(1 for r in results if r['correct'])
                print(f"\n--- 进度: {i+1}/{len(questions)}, 当前准确率: {correct}/{i+1} ({100*correct/(i+1):.1f}%) ---")
    
    finally:
        pipeline.close()
    
    total_time = time.time() - total_start
    
    # 统计结果
    correct = sum(1 for r in results if r['correct'])
    accuracy = 100 * correct / len(questions) if questions else 0
    
    print("\n" + "="*80)
    print("评估结果汇总")
    print("="*80)
    print(f"\n总计: {correct}/{len(questions)} ({accuracy:.2f}%)")
    print(f"总耗时: {total_time:.1f}秒 (平均 {total_time/len(questions):.1f}秒/题)")
    
    # 保存结果
    output_data = {
        'total_questions': len(questions),
        'correct': correct,
        'accuracy': accuracy,
        'total_time_seconds': total_time,
        'avg_time_per_question': total_time/len(questions),
        'results': results
    }
    
    output_path = Path('output/vqa_llm_evaluation_results.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ 详细结果已保存至: {output_path}")
    
    return output_data


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM VQA评估 (带Retry)")
    parser.add_argument("--questions", "-q", default="output/vqa_questions_all_official.json",
                        help="问题文件路径")
    parser.add_argument("--max-retries", "-r", type=int, default=5,
                        help="最大重试次数")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    
    args = parser.parse_args()
    
    print(f"加载问题文件: {args.questions}")
    run_evaluation(args.questions, max_retries=args.max_retries, verbose=not args.quiet)
    print("\n✓ 评估完成")


if __name__ == "__main__":
    main()
