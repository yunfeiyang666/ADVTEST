"""
快速运行58题测试（verbose=False 减少输出）
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core_pipeline.vqa_pipeline.pipeline import VQAPipeline
from import_single_scene_to_neo4j import Neo4jImporter


# 硬编码的等价词组
EQUIVALENT_SETS = [
    {'parked', 'stopped'},
    {'with_rider', 'with rider'},
    {'without_rider', 'without rider'},
    {'moving', 'in motion'},
]


def normalize_answer(answer: str) -> str:
    """标准化答案格式"""
    return answer.lower().strip().replace('_', ' ')


def check_equivalent(expected: str, actual: str) -> bool:
    """检查两个答案是否在等价词组中"""
    exp_norm = normalize_answer(expected)
    act_norm = normalize_answer(actual)
    
    if exp_norm == act_norm:
        return True
    
    for equiv_set in EQUIVALENT_SETS:
        norm_set = {normalize_answer(w) for w in equiv_set}
        if exp_norm in norm_set and act_norm in norm_set:
            return True
    
    return False


def run_all_58_questions():
    """运行全部58题"""
    print("=" * 70)
    print("  快速运行58题测试 (verbose=False)")
    print("=" * 70)
    
    # 初始化 pipeline
    pipeline = VQAPipeline()
    if not pipeline.initialize(quiet=True):
        print("❌ Pipeline 初始化失败")
        return
    
    # 定义场景
    script_dir = os.path.dirname(os.path.abspath(__file__))
    scenes = [
        ('scene-0103_frame38', 'scene-0103_frame38_scene_graph.json', 'scene-0103_frame38_official_qa.json'),
        ('scene-0103_frame25', 'scene-0103_frame25_scene_graph.json', 'scene-0103_frame25_official_qa.json'),
        ('scene-0553_frame8', 'scene-0553_frame8_scene_graph.json', 'scene-0553_frame8_official_qa.json'),
        ('scene-0916_frame8', 'scene-0916_frame8_scene_graph.json', 'scene-0916_frame8_official_qa.json'),
    ]
    
    all_results = []
    total_correct = 0
    total_questions = 0
    
    for scene_name, sg_file, qa_file in scenes:
        sg_path = os.path.join(script_dir, 'output/coverage_analysis/scene_graphs', sg_file)
        qa_path = os.path.join(script_dir, 'output/coverage_analysis/vqa_results', qa_file)
        
        if not os.path.exists(sg_path) or not os.path.exists(qa_path):
            print(f"⚠️ 跳过 {scene_name}: 文件不存在")
            continue
        
        # 加载数据
        with open(sg_path, 'r', encoding='utf-8') as f:
            scene_graph = json.load(f)
        with open(qa_path, 'r', encoding='utf-8') as f:
            qa_data = json.load(f)
        
        # 导入场景到 Neo4j
        print(f"\n📦 导入场景: {scene_name}")
        importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
        try:
            importer.clear_database()
            importer.create_constraints()
            importer.import_scene(scene_graph)
            print(f"   导入完成")
        finally:
            importer.close()
        
        # 获取问题列表
        questions = qa_data.get('questions', [])
        if not questions:
            results_data = qa_data.get('results', [])
            questions = [{'question': r['question'], 'answer': r['expected_answer']} for r in results_data]
        
        print(f"🔄 运行 {len(questions)} 题...")
        
        scene_correct = 0
        scene_results = []
        
        for i, q in enumerate(questions, 1):
            question = q['question']
            expected = q['answer']
            
            # 处理问题（verbose=False 加快速度）
            result = pipeline.process_question(question, verbose=False)
            actual = result.answer if result.success else "ERROR"
            
            # 判断正确性
            is_correct = check_equivalent(expected, actual)
            if is_correct:
                scene_correct += 1
                status = "✓"
            else:
                status = "✗"
            
            print(f"  [{i:2d}/{len(questions)}] {status} | 预期: {expected[:20]:20s} | 实际: {actual[:30]}")
            
            scene_results.append({
                'question': question,
                'expected': expected,
                'actual': actual,
                'correct': is_correct,
            })
        
        total_correct += scene_correct
        total_questions += len(questions)
        
        print(f"   场景正确率: {scene_correct}/{len(questions)} ({100*scene_correct/len(questions):.1f}%)")
        
        all_results.append({
            'scene': scene_name,
            'total': len(questions),
            'correct': scene_correct,
            'results': scene_results,
        })
    
    # 总结
    print("\n" + "=" * 70)
    print("  全局测试总结")
    print("=" * 70)
    print(f"  总问题数: {total_questions}")
    print(f"  答案正确: {total_correct} ({100*total_correct/total_questions:.1f}%)")
    
    # 保存结果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = Path(script_dir) / 'output/coverage_analysis/vqa_results' / f'fast_58q_test_{timestamp}.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total_questions': total_questions,
            'correct_count': total_correct,
            'accuracy': 100*total_correct/total_questions if total_questions > 0 else 0,
            'scenes': all_results,
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n📊 结果已保存: {output_path}")
    
    pipeline.close()


if __name__ == "__main__":
    run_all_58_questions()
