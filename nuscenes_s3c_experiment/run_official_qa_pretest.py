"""
官方QA预跑版测试脚本
测试所有有官方QA题目的帧，验证修复效果

包含帧：
- scene-0103_frame25: 11题
- scene-0103_frame38: 14题  
- scene-0553_frame8: 24题
- scene-0916_frame8: 9题
总计: 58题
"""
import os
import sys
import json
from datetime import datetime
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from import_single_scene_to_neo4j import Neo4jImporter
from vqa_pipeline import VQAPipeline
import config


class Logger:
    """日志记录器"""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, 'w', encoding='utf-8')
    
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()
    
    def flush(self):
        self.terminal.flush()
        self.log.flush()
    
    def close(self):
        self.log.close()


# 有官方QA的帧列表
OFFICIAL_QA_SCENES = [
    {
        'scene_name': 'scene-0103',
        'frame_idx': 25,
        'scene_graph_file': 'scene-0103_frame25_scene_graph.json',
        'qa_file': 'scene-0103_frame25_official_qa.json'
    },
    {
        'scene_name': 'scene-0103',
        'frame_idx': 38,
        'scene_graph_file': 'scene-0103_frame38_scene_graph.json',
        'qa_file': 'scene-0103_frame38_official_qa.json'
    },
    {
        'scene_name': 'scene-0553',
        'frame_idx': 8,
        'scene_graph_file': 'scene-0553_frame8_scene_graph.json',
        'qa_file': 'scene-0553_frame8_official_qa.json'
    },
    {
        'scene_name': 'scene-0916',
        'frame_idx': 8,
        'scene_graph_file': 'scene-0916_frame8_scene_graph.json',
        'qa_file': 'scene-0916_frame8_official_qa.json'
    },
]


def load_scene_graph(filepath):
    """加载场景图"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_official_qa(filepath):
    """加载官方QA数据"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 提取问题和预期答案
    qa_pairs = []
    for result in data.get('results', []):
        qa_pairs.append({
            'question': result['question'],
            'expected_answer': result['expected_answer'],
            'question_type': result.get('question_type', 'unknown')
        })
    return qa_pairs


def import_to_neo4j(scene_graph, scene_name, frame_idx):
    """导入场景图到Neo4j"""
    print(f"\n导入场景到Neo4j: {scene_name} 帧{frame_idx}")
    
    importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
    
    try:
        importer.clear_database()
        importer.create_constraints()
        importer.import_scene(scene_graph)
        
        with importer.driver.session() as session:
            result = session.run("MATCH (n:Object) RETURN count(n) as count")
            node_count = result.single()['count']
            result = session.run("MATCH ()-[r:RELATES_TO]->() WHERE r.direction_4 IS NOT NULL RETURN count(r) as count")
            dir4_count = result.single()['count']
            print(f"✓ 导入 {node_count} 节点, {dir4_count} 条关系有direction_4")
        
        return True
    except Exception as e:
        print(f"✗ 导入失败: {e}")
        return False
    finally:
        importer.close()


def test_scene_questions(scene_name, frame_idx, qa_pairs, pipeline):
    """测试单个场景的问题"""
    print(f"\n{'='*70}")
    print(f"  测试场景: {scene_name} 帧{frame_idx}")
    print(f"  问题数量: {len(qa_pairs)}")
    print("="*70)
    
    results = []
    
    for i, qa in enumerate(qa_pairs, 1):
        question = qa['question']
        expected_answer = qa['expected_answer']
        question_type = qa['question_type']
        
        print(f"\n[{i}/{len(qa_pairs)}] Q: {question}")
        print(f"  预期: {expected_answer}")
        
        # 开启verbose=True，详细记录规范化、中间思路、Cypher和查询结果到日志
        result = pipeline.process_question(question, verbose=True)
        
        # 比较答案
        answer_match = False
        if result.success and result.answer:
            answer_lower = result.answer.lower().strip()
            expected_lower = expected_answer.lower().strip()
            # 更灵活的匹配
            answer_match = (
                expected_lower in answer_lower or 
                answer_lower in expected_lower or
                answer_lower == expected_lower
            )
        
        results.append({
            'question': question,
            'expected_answer': expected_answer,
            'predicted_answer': result.answer,
            'question_type': question_type,
            'success': result.success,
            'answer_match': answer_match,
            'cypher': result.cypher_query,
            'error': result.error
        })
        
        if result.success:
            if answer_match:
                print(f"  ✅ 正确: {result.answer}")
            else:
                print(f"  ❌ 错误: {result.answer}")
        else:
            print(f"  ❌ 失败: {result.error}")
    
    # 统计
    total = len(results)
    success_count = sum(1 for r in results if r['success'])
    match_count = sum(1 for r in results if r['answer_match'])
    
    print(f"\n{'='*70}")
    print(f"  场景总结: {scene_name} 帧{frame_idx}")
    print(f"  执行成功: {success_count}/{total} ({success_count/total*100:.1f}%)")
    print(f"  答案正确: {match_count}/{total} ({match_count/total*100:.1f}%)")
    print("="*70)
    
    return results


def main():
    output_dir = os.path.join(config.OUTPUT_DIR, "coverage_analysis", "vqa_results")
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"official_qa_pretest_{timestamp}.txt")
    
    logger = Logger(log_file)
    original_stdout = sys.stdout
    sys.stdout = logger
    
    try:
        print("="*70)
        print("  官方QA预跑测试 - 验证方向修复效果")
        print("="*70)
        print(f"\n📝 日志文件: {log_file}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\n测试场景: {len(OFFICIAL_QA_SCENES)} 个")
        
        # 初始化VQA Pipeline
        print("\n初始化VQA Pipeline...")
        pipeline = VQAPipeline(use_ir=False)
        if not pipeline.initialize():
            print("✗ Pipeline初始化失败")
            return
        
        # 测试所有场景
        all_results = []
        scene_stats = []
        
        for scene_info in OFFICIAL_QA_SCENES:
            scene_name = scene_info['scene_name']
            frame_idx = scene_info['frame_idx']
            
            # 加载场景图
            scene_graph_path = os.path.join(
                config.OUTPUT_DIR, "coverage_analysis", "scene_graphs", 
                scene_info['scene_graph_file']
            )
            print(f"\n加载场景图: {scene_graph_path}")
            scene_graph = load_scene_graph(scene_graph_path)
            
            # 加载官方QA
            qa_path = os.path.join(output_dir, scene_info['qa_file'])
            print(f"加载官方QA: {qa_path}")
            qa_pairs = load_official_qa(qa_path)
            
            # 导入到Neo4j
            if not import_to_neo4j(scene_graph, scene_name, frame_idx):
                print(f"跳过场景 {scene_name}")
                continue
            
            # 测试问题
            results = test_scene_questions(scene_name, frame_idx, qa_pairs, pipeline)
            all_results.extend(results)
            
            # 记录场景统计
            scene_stats.append({
                'scene': f"{scene_name}_frame{frame_idx}",
                'total': len(results),
                'correct': sum(1 for r in results if r['answer_match'])
            })
        
        # 全局统计
        total_questions = len(all_results)
        total_correct = sum(1 for r in all_results if r['answer_match'])
        total_success = sum(1 for r in all_results if r['success'])
        
        print("\n" + "="*70)
        print("  全局测试总结")
        print("="*70)
        print(f"  总问题数: {total_questions}")
        print(f"  执行成功: {total_success} ({total_success/total_questions*100:.1f}%)")
        print(f"  答案正确: {total_correct} ({total_correct/total_questions*100:.1f}%)")
        
        print(f"\n各场景统计:")
        for stat in scene_stats:
            rate = stat['correct']/stat['total']*100 if stat['total'] > 0 else 0
            print(f"  {stat['scene']}: {stat['correct']}/{stat['total']} ({rate:.1f}%)")
        
        # 按题型统计
        by_type = defaultdict(lambda: {'total': 0, 'correct': 0})
        for r in all_results:
            qtype = r['question_type']
            by_type[qtype]['total'] += 1
            if r['answer_match']:
                by_type[qtype]['correct'] += 1
        
        print(f"\n按题型统计:")
        for qtype, stats in sorted(by_type.items()):
            rate = stats['correct']/stats['total']*100 if stats['total'] > 0 else 0
            print(f"  {qtype}: {stats['correct']}/{stats['total']} ({rate:.1f}%)")
        
        # 保存结果
        result_file = os.path.join(output_dir, f"official_qa_pretest_{timestamp}.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': timestamp,
                'total_questions': total_questions,
                'total_correct': total_correct,
                'accuracy': total_correct/total_questions*100,
                'scene_stats': scene_stats,
                'by_type': dict(by_type),
                'results': all_results
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n📊 结果已保存: {result_file}")
        print(f"⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.stdout = original_stdout
        logger.close()
        print(f"\n✓ 日志已保存: {log_file}")


if __name__ == '__main__':
    main()
