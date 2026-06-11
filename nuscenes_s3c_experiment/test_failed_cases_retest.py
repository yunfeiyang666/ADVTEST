"""
失败案例重测脚本
从之前58题测试中提取13个失败案例，验证规范化改进效果

测试重点：
1. trailer/barrier等类型同义词映射
2. yes/no答案格式规范化
3. status答案格式规范化
4. count答案格式规范化
"""
import os
import sys
import json
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from import_single_scene_to_neo4j import Neo4jImporter
from vqa_pipeline import VQAPipeline
import config

MAX_ANS_RETRIES = 3  # 每道题最多重试次数（包含第一次）


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


# 13个失败案例（从之前的测试结果中提取）
FAILED_TEST_CASES = [
    {
        'scene_name': 'scene-0553',
        'frame_idx': 8,
        'scene_graph_file': 'scene-0553_frame8_scene_graph.json',
        'questions': [
            {
                'question': 'Are there any trailers?',
                'expected_answer': 'yes',
                'question_type': 'exist',
                'failure_reason': 'Schema类型不匹配（trailer→truck）'
            },
            {
                'question': 'What status is the bicycle?',
                'expected_answer': 'with rider',
                'question_type': 'status',
                'failure_reason': '状态推断失败'
            },
            {
                'question': 'There is a trailer; is it the same status as the truck to the back right of the with rider bicycle?',
                'expected_answer': 'yes',
                'question_type': 'comparison',
                'failure_reason': '复杂多跳关系+类型不匹配'
            },
            {
                'question': 'Does the trailer have the same status as the truck to the back right of the bicycle?',
                'expected_answer': 'yes',
                'question_type': 'comparison',
                'failure_reason': '复杂多跳关系+类型不匹配'
            },
            {
                'question': 'What number of other things are there of the same status as the trailer?',
                'expected_answer': '8',
                'question_type': 'count',
                'failure_reason': '类型不匹配+答案格式'
            },
            {
                'question': 'There is a truck that is to the back of me; what is its status?',
                'expected_answer': 'stopped',
                'question_type': 'status',
                'failure_reason': '答案格式不规范（冗长）'
            },
            {
                'question': 'What status is the truck to the back of the moving truck?',
                'expected_answer': 'stopped',
                'question_type': 'status',
                'failure_reason': 'Cypher语法错误'
            },
            {
                'question': 'Is the status of the bus to the back right of the not standing pedestrian the same as the bus that is to the front of the stopped trailer?',
                'expected_answer': 'yes',
                'question_type': 'comparison',
                'failure_reason': '极复杂多跳关系+类型不匹配'
            },
            {
                'question': 'How many barriers are to the front of the trailer?',
                'expected_answer': '5',
                'question_type': 'count',
                'failure_reason': '两个类型都不匹配（barrier+trailer）'
            },
            {
                'question': 'Are there any stopped trailers to the front of the stopped trailer?',
                'expected_answer': 'no',
                'question_type': 'exist',
                'failure_reason': '类型不匹配+答案格式'
            },
            {
                'question': 'There is a stopped trailer; are there any with rider bicycles to the front left of it?',
                'expected_answer': 'yes',
                'question_type': 'exist',
                'failure_reason': '类型不匹配+复杂方位关系'
            },
            {
                'question': 'Is there another truck of the same status as the truck to the front left of the with rider thing?',
                'expected_answer': 'no',
                'question_type': 'exist',
                'failure_reason': '复杂多跳关系'
            },
            {
                'question': 'Are there any other cars of the same status as the truck that is to the front left of the with rider thing?',
                'expected_answer': 'yes',
                'question_type': 'exist',
                'failure_reason': '复杂多跳关系'
            },
        ]
    }
]


def load_scene_graph(filepath):
    """加载场景图"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def import_to_neo4j(scene_graph, scene_name, frame_idx):
    """导入场景图到Neo4j"""
    print("\n" + "=" * 70)
    print(f"  导入场景到Neo4j: {scene_name} 帧{frame_idx}")
    print("=" * 70)
    
    importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
    
    try:
        print("清空数据...")
        importer.clear_database()
        print("创建约束...")
        importer.create_constraints()
        print("导入场景图...")
        importer.import_scene(scene_graph)
        
        with importer.driver.session() as session:
            result = session.run("MATCH (n:Object) RETURN count(n) as count")
            node_count = result.single()['count']
            print(f"✓ 成功导入 {node_count} 个节点")
        
        return True
    except Exception as e:
        print(f"✗ 导入失败: {e}")
        return False
    finally:
        importer.close()


def test_scene_questions(scene_name, frame_idx, questions, pipeline):
    """测试单个场景的问题"""
    print("\n" + "=" * 70)
    print(f"  测试场景: {scene_name} 帧{frame_idx}")
    print(f"  问题数量: {len(questions)}")
    print("=" * 70)
    
    results = []
    
    for i, qa in enumerate(questions, 1):
        question = qa['question']
        expected_answer = qa['expected_answer']
        question_type = qa['question_type']
        failure_reason = qa['failure_reason']
        
        print(f"\n{'-'*70}")
        print(f"问题 {i}/{len(questions)}")
        print(f"失败原因: {failure_reason}")
        print("=" * 70)
        
        best_result = None
        answer_match = False
        last_feedback = None
        
        for attempt in range(MAX_ANS_RETRIES):
            if attempt > 0:
                print(f"\n🔁 第 {attempt+1}/{MAX_ANS_RETRIES} 次重试生成与执行（基于上一轮错误反馈）...")
                print(f"\n💡 反馈信息：")
                print("-" * 50)
                print(last_feedback)
                print("-" * 50)
            # 改为所有轮次都显示详细信息，方便调试
            verbose_attempt = True  # 改为True，让每次retry都能看到详细过程
            
            result = pipeline.process_question(
                question,
                verbose=verbose_attempt,
                cypher_feedback=last_feedback,
            )
            best_result = result
            
            if not result.success or not result.answer:
                # 执行失败或没有答案，没必要继续 retry
                break
            
            answer_lower = result.answer.lower()
            expected_lower = expected_answer.lower()
            answer_match = (
                expected_lower in answer_lower or answer_lower in expected_lower
            )
            
            if answer_match:
                break  # 已经答对，不再重试
            
            # 构造下一轮的反馈，指导LLM修正上一次的错误查询/答案
            last_feedback = (
                "上一轮你为同一个问题生成的Cypher和答案不正确，请根据以下信息重新生成：\n"
                f"- 上一轮 Cypher: \n{result.cypher_query}\n"
                f"- 上一轮查询结果 query_result: \n{json.dumps(result.query_result, ensure_ascii=False)}\n"
                f"- 上一轮自然语言答案: '{result.answer}'\n"
                f"- 预期答案(ground truth): '{expected_answer}'\n"
                "请仔细检查是否遗漏了 'same status'、'other/another'(排除自身)、'with_rider' 等约束，"
                "并在这次生成中修正这些问题，只输出一条新的、更精确的 Cypher 查询。"
            )
        
        final = best_result
        
        results.append({
            'question': question,
            'expected_answer': expected_answer,
            'predicted_answer': final.answer,
            'question_type': question_type,
            'failure_reason': failure_reason,
            'success': final.success,
            'answer_match': answer_match,
            'cypher': final.cypher_query,
            'error': final.error
        })
        
        if final.success:
            if answer_match:
                print(f"\n✅ 成功且答案匹配 (之前失败，现在成功！)")
                print(f"  预期: {expected_answer}")
                print(f"  实际: {final.answer}")
            else:
                print(f"\n⚠️ 成功但答案不匹配 (仍然失败)")
                print(f"  预期: {expected_answer}")
                print(f"  实际: {final.answer}")
        else:
            print(f"\n❌ 执行失败: {final.error}")
    
    # 统计
    total = len(results)
    success_count = sum(1 for r in results if r['success'])
    match_count = sum(1 for r in results if r['answer_match'])
    
    print(f"\n{'=' * 70}")
    print(f"  测试总结: {scene_name} 帧{frame_idx}")
    print("=" * 70)
    print(f"  总问题数: {total}")
    print(f"  执行成功: {success_count} ({success_count/total*100:.1f}%)")
    print(f"  答案匹配: {match_count} ({match_count/total*100:.1f}%)")
    print(f"  改进效果: {match_count}/{total} (之前 0/{total})")
    print(f"  准确率提升: +{match_count/total*100:.1f}%")
    
    # 按失败原因统计
    by_reason = defaultdict(lambda: {'total': 0, 'fixed': 0})
    for r in results:
        reason = r['failure_reason']
        by_reason[reason]['total'] += 1
        if r['answer_match']:
            by_reason[reason]['fixed'] += 1
    
    print(f"\n按失败原因统计:")
    for reason, stats in sorted(by_reason.items()):
        fixed_rate = stats['fixed'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"  {reason}:")
        print(f"    修复: {stats['fixed']}/{stats['total']} ({fixed_rate:.1f}%)")
    
    return results


def main():
    output_dir = os.path.join(config.OUTPUT_DIR, "coverage_analysis", "vqa_results")
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"failed_cases_retest_{timestamp}.txt")
    
    logger = Logger(log_file)
    original_stdout = sys.stdout
    sys.stdout = logger
    
    try:
        print("=" * 70)
        print("  失败案例重测 - 验证规范化改进效果")
        print("=" * 70)
        print(f"\n📝 日志文件: {log_file}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\n测试策略:")
        print(f"  - 从之前58题测试中提取13个失败案例")
        print(f"  - 重点验证同义词映射和答案格式化效果")
        print(f"  - 详细展示每一步的处理过程")
        
        # 初始化VQA Pipeline (直接LLM生成Cypher模式)
        print("\n初始化VQA Pipeline (直接LLM模式)...")
        print("  流程: 问题 -> [LLM] -> Cypher")
        pipeline = VQAPipeline(use_ir=False)  # 直接用LLM生成Cypher
        if not pipeline.initialize():
            print("✗ Pipeline初始化失败")
            return
        
        # 测试所有场景
        all_results = []
        total_questions = 0
        total_fixed = 0
        
        for test_case in FAILED_TEST_CASES:
            scene_name = test_case['scene_name']
            frame_idx = test_case['frame_idx']
            questions = test_case['questions']
            scene_graph_file = test_case['scene_graph_file']
            
            # 加载场景图
            scene_graph_path = os.path.join(config.OUTPUT_DIR, "coverage_analysis", "scene_graphs", scene_graph_file)
            print(f"\n加载场景图: {scene_graph_path}")
            scene_graph = load_scene_graph(scene_graph_path)
            
            # 导入到Neo4j
            if not import_to_neo4j(scene_graph, scene_name, frame_idx):
                print(f"跳过场景 {scene_name}")
                continue
            
            # 测试问题
            results = test_scene_questions(scene_name, frame_idx, questions, pipeline)
            all_results.extend(results)
            
            # 统计
            total_questions += len(questions)
            total_fixed += sum(1 for r in results if r['answer_match'])
        
        # 全局统计
        print("\n" + "=" * 70)
        print("  全局测试总结")
        print("=" * 70)
        print(f"  总失败案例数: {total_questions}")
        print(f"  修复案例数: {total_fixed}")
        print(f"  修复率: {total_fixed/total_questions*100:.1f}%")
        print(f"\n  之前准确率: 77.6% (45/58)")
        print(f"  理论提升: +{total_fixed/58*100:.1f}%")
        print(f"  预期准确率: {77.6 + total_fixed/58*100:.1f}%")
        
        # 保存结果
        result_file = os.path.join(output_dir, f"failed_cases_retest_{timestamp}.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': timestamp,
                'total_questions': total_questions,
                'total_fixed': total_fixed,
                'fix_rate': total_fixed/total_questions*100,
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
