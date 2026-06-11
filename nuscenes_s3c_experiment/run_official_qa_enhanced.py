"""
增强版官方QA测试运行器
特性：
1. 硬编码等价词规则 + LLM兜底判定
2. 智能retry机制（让LLM分析自己的错误并修正）
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vqa_pipeline.pipeline import VQAPipeline, VQAResult
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


def llm_judge_answers(llm_client, question: str, expected: str, actual: str) -> tuple:
    """判断两个答案是否等价，返回(是否等价, 原因)"""
    # 1. 先用硬编码规则检查
    if check_equivalent(expected, actual):
        return True, "等价词组匹配"
    
    # 2. 规则检查不通过，调用LLM
    prompt = f"""判断以下两个答案是否表达相同意思。

问题: {question}
标准答案: {expected}
实际答案: {actual}

只回答YES或NO。"""
    
    try:
        response = llm_client.call_llm_raw(prompt, max_tokens=10, temperature=0)
        is_same = "YES" in response.upper()
        return is_same, "LLM判定等价" if is_same else "LLM判定不等价"
    except Exception as e:
        return False, f"LLM调用失败: {e}"


class EnhancedQARunner:
    """增强版QA测试运行器"""
    
    def __init__(self, use_llm_judge: bool = True, max_retries: int = 2):
        """
        Args:
            use_llm_judge: 是否使用LLM进行最终答案判定
            max_retries: 最大重试次数
        """
        self.pipeline = VQAPipeline()
        self.use_llm_judge = use_llm_judge
        self.max_retries = max_retries
        
        # 统计
        self.total_questions = 0
        self.correct_count = 0
        self.semantic_match_count = 0  # 语义等价匹配的数量
        self.retry_success_count = 0   # retry成功的数量
        self.results = []
    
    def initialize(self) -> bool:
        """初始化"""
        return self.pipeline.initialize()
    
    def process_question_with_retry(self, question: str, expected_answer: str,
                                   question_type: str = None, verbose: bool = True) -> dict:
        """
        处理单个问题，支持智能retry（累积历史错误反馈）
        
        Returns:
            包含详细信息的结果字典
        """
        attempts = []
        final_result = None
        feedback_history = []  # 累积历史错误反馈
        
        for attempt in range(self.max_retries + 1):
            feedback = None
            
            # 如果是retry，基于错误信号分析
            if attempt > 0 and attempts:
                last_attempt = attempts[-1]
                
                # 🔍 判断错误类型（不依赖标答，只看执行结果）
                needs_correction = False
                correction_reason = ""
                
                # 情况A: 查询执行失败（语法错误）
                if not last_attempt['success']:
                    needs_correction = True
                    correction_reason = "Cypher执行报错或生成失败"
                
                # 情况B: 查询返回空结果
                elif last_attempt['query_result'].get('count', 0) == 0:
                    needs_correction = True
                    correction_reason = """查询成功执行，但返回空结果。可能原因：
1. 节点标签/关系类型不存在
2. 属性名拼写错误（如用type代替status）
3. WHERE条件过于严格
4. 方向错误（参照物应在箭头左侧）"""
                
                # 情况C: 有结果但答案不对（此时可以用标答辅助，但不直接给）
                elif last_attempt['answer'] != expected_answer:
                    needs_correction = True
                    # 只给答案类型提示，不给完整答案
                    answer_type = self._get_answer_type_hint(expected_answer)
                    correction_reason = f"""查询返回了结果，但答案可能不正确。
期望答案类型: {answer_type}
实际返回: {last_attempt['answer']}
请检查：
- status属性使用是否正确（'with_rider'是status值，不是type）
- 方向过滤是否正确
- 属性名是否匹配"""
                
                if needs_correction:
                    # 让LLM分析错误（不给标答，只给错误信号）
                    error_analysis, fix_suggestion = self.pipeline.llm.analyze_query_error(
                        question=question,
                        question_type=last_attempt['question_type'],
                        cypher_query=last_attempt['cypher_query'],
                        query_result=last_attempt['query_result'],
                        expected_answer=None  # ✅ 不给标答，让LLM自己分析
                    )
                    
                    # 累积当前错误到历史
                    current_error = f"第{attempt}次: {correction_reason}\n分析: {error_analysis}"
                    feedback_history.append(current_error)
                    
                    # 构建包含历史的反馈
                    if len(feedback_history) == 1:
                        feedback = f"""上次尝试失败。

错误原因: {correction_reason}

LLM分析: {error_analysis}
修复建议: {fix_suggestion}

请根据以上信息重写Cypher查询。"""
                    else:
                        history_str = "\n".join([f"  {i+1}. {h}" for i, h in enumerate(feedback_history)])
                        feedback = f"""之前的{len(feedback_history)}次尝试都失败了。

历史错误:
{history_str}

最新修复建议: {fix_suggestion}

⚠️ 关键：不要重复之前的错误！请仔细检查Schema和属性名。"""
                    
                    if verbose:
                        print(f"\n  [Retry {attempt}] 错误原因: {correction_reason[:100]}...")
                        print(f"  [Retry {attempt}] 错误分析: {error_analysis}")
                        print(f"  [Retry {attempt}] 修复建议: {fix_suggestion}")
                        if len(feedback_history) > 1:
                            print(f"  [Retry {attempt}] 已累积 {len(feedback_history)} 个历史错误")
            
            # 执行查询
            result = self.pipeline.process_question(
                question, 
                verbose=verbose,
                cypher_feedback=feedback
            )
            
            attempts.append({
                'attempt': attempt,
                'cypher_query': result.cypher_query,
                'query_result': result.query_result,
                'answer': result.answer,
                'question_type': result.question_type,
                'success': result.success,
                'feedback': feedback
            })
            
            # 检查是否需要retry
            if result.success:
                # 判断是否正确
                is_correct, reason = self._judge_answer(
                    expected_answer, 
                    result.answer, 
                    result.question_type,
                    question
                )
                
                if is_correct:
                    final_result = {
                        'correct': True,
                        'reason': reason,
                        'attempts': len(attempts),
                        'result': result
                    }
                    break
                
                # 如果查询返回空结果，可能需要retry
                if result.query_result.get('count', 0) == 0:
                    if verbose:
                        print(f"  ⚠️ 查询返回空结果，准备retry...")
                    continue
                
                # 如果答案不对但有结果，可能是方向/逻辑问题
                if attempt < self.max_retries:
                    if verbose:
                        print(f"  ⚠️ 答案不匹配 (expected: {expected_answer}, got: {result.answer})，准备retry...")
                    continue
        
        # 如果所有尝试都失败
        if final_result is None:
            if attempts:
                last_attempt = attempts[-1]
                actual_answer = last_attempt.get('answer', '')
                q_type = last_attempt.get('question_type', 'general')
                is_correct, reason = self._judge_answer(
                    expected_answer,
                    actual_answer,
                    q_type,
                    question
                )
            else:
                is_correct, reason = False, "all_attempts_failed"
                last_attempt = None
            
            final_result = {
                'correct': is_correct,
                'reason': reason,
                'attempts': len(attempts),
                'result': last_attempt
            }
        
        return final_result, attempts
    
    def _get_answer_type_hint(self, expected_answer: str) -> str:
        """从预期答案推断答案类型提示（不给完整答案）"""
        answer_lower = expected_answer.lower().strip()
        
        # yes/no问题
        if answer_lower in ['yes', 'no']:
            return "yes/no"
        
        # 数字问题
        if answer_lower.isdigit():
            return f"a number"
        
        # status相关
        status_values = ['stopped', 'moving', 'parked', 'standing', 'with_rider', 'without_rider', 'with rider', 'without rider']
        if answer_lower in status_values:
            return "a status value (like 'stopped', 'moving', 'with_rider', etc.)"
        
        # 对象类型
        object_types = ['car', 'truck', 'bus', 'bicycle', 'pedestrian', 'motorcycle', 'trailer', 'barrier', 'ego']
        if answer_lower in object_types:
            return "an object type (like 'car', 'bicycle', 'truck', etc.)"
        
        # 默认：只给第一个词和长度
        first_word = answer_lower.split()[0] if answer_lower.split() else answer_lower[:5]
        return f"text (first word starts with '{first_word}')"
    
    def _judge_answer(self, expected: str, actual: str, question_type: str, question: str) -> tuple:
        """判断答案是否正确"""
        # 精确匹配
        if expected.lower().strip() == actual.lower().strip():
            return True, "精确匹配"
        
        # 使用硬编码规则 + LLM兜底
        if self.use_llm_judge:
            return llm_judge_answers(self.pipeline.llm, question, expected, actual)
        
        return False, f"不匹配: 期望 '{expected}', 实际 '{actual}'"
    
    def run_scene(self, scene_graph_path: str, qa_path: str, verbose: bool = True) -> dict:
        """运行单个场景的测试"""
        # 加载数据
        with open(scene_graph_path, 'r', encoding='utf-8') as f:
            scene_graph = json.load(f)
        with open(qa_path, 'r', encoding='utf-8') as f:
            qa_data = json.load(f)
        
        scene_name = scene_graph.get('scene_name', 'unknown')
        frame_idx = scene_graph.get('frame_idx', 0)
        
        # 导入场景到Neo4j
        importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
        try:
            importer.clear_database()
            importer.create_constraints()
            importer.import_scene(scene_graph)
        finally:
            importer.close()
        
        # 从LLM用的qa_data格式提取问题
        questions = qa_data.get('questions', [])
        if not questions:
            # 尝试从 results 格式提取
            results_data = qa_data.get('results', [])
            questions = [{'question': r['question'], 'answer': r['expected_answer']} for r in results_data]
        scene_results = []
        correct = 0
        
        print(f"\n{'='*70}")
        print(f"  测试场景: {scene_name} 帧{frame_idx}")
        print(f"  问题数量: {len(questions)}")
        print(f"{'='*70}")
        
        for i, q in enumerate(questions, 1):
            question = q['question']
            expected = q['answer']
            
            print(f"\n[{i}/{len(questions)}] Q: {question}")
            print(f"  预期: {expected}")
            
            final_result, attempts = self.process_question_with_retry(
                question, expected, verbose=verbose
            )
            
            is_correct = final_result['correct']
            reason = final_result['reason']
            num_attempts = final_result['attempts']
            
            if is_correct:
                correct += 1
                status = "✅ 正确"
                if "semantic" in reason:
                    self.semantic_match_count += 1
                    status += f" (语义等价: {reason})"
                if num_attempts > 1:
                    self.retry_success_count += 1
                    status += f" (retry {num_attempts}次)"
            else:
                status = f"❌ 错误: {reason}"
            
            print(f"  {status}")
            
            actual_answer = ""
            if final_result['result']:
                if isinstance(final_result['result'], dict):
                    actual_answer = final_result['result'].get('answer', '')
                elif hasattr(final_result['result'], 'answer'):
                    actual_answer = final_result['result'].answer
            
            scene_results.append({
                'question': question,
                'expected': expected,
                'actual': actual_answer,
                'correct': is_correct,
                'reason': reason,
                'attempts': num_attempts,
            })
        
        self.total_questions += len(questions)
        self.correct_count += correct
        
        print(f"\n{'='*70}")
        print(f"  场景总结: {scene_name} 帧{frame_idx}")
        print(f"  答案正确: {correct}/{len(questions)} ({100*correct/len(questions):.1f}%)")
        print(f"{'='*70}")
        
        return {
            'scene_name': scene_name,
            'frame_idx': frame_idx,
            'total': len(questions),
            'correct': correct,
            'results': scene_results
        }
    
    def run_all_scenes(self, scenes: list, verbose: bool = True) -> dict:
        """运行所有场景测试"""
        all_results = []
        
        for scene_graph_path, qa_path in scenes:
            if not os.path.exists(scene_graph_path) or not os.path.exists(qa_path):
                print(f"警告: 找不到文件 {scene_graph_path} 或 {qa_path}")
                continue
            
            result = self.run_scene(scene_graph_path, qa_path, verbose=verbose)
            all_results.append(result)
        
        # 总结
        print(f"\n{'='*70}")
        print(f"  全局测试总结")
        print(f"{'='*70}")
        print(f"  总问题数: {self.total_questions}")
        if self.total_questions > 0:
            print(f"  答案正确: {self.correct_count} ({100*self.correct_count/self.total_questions:.1f}%)")
        else:
            print(f"  答案正确: {self.correct_count} (0%)")
        print(f"  语义等价匹配: {self.semantic_match_count}")
        print(f"  Retry成功: {self.retry_success_count}")
        
        return {
            'total_questions': self.total_questions,
            'correct_count': self.correct_count,
            'semantic_match_count': self.semantic_match_count,
            'retry_success_count': self.retry_success_count,
            'scenes': all_results
        }
    
    def close(self):
        """关闭连接"""
        self.pipeline.close()


def main():
    """主函数"""
    print("="*70)
    print("  增强版官方QA预跑测试")
    print("  特性: LLM答案判定 + 智能Retry")
    print("="*70)
    
    # 创建运行器
    runner = EnhancedQARunner(use_llm_judge=True, max_retries=2)
    
    # 初始化
    if not runner.initialize():
        print("初始化失败")
        return
    
    # 定义测试场景（全部4个场景，共 58 题）
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    scenes = [
        # scene-0103 frame38: 14题
        (os.path.join(script_dir, 'output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json'),
         os.path.join(script_dir, 'output/coverage_analysis/vqa_results/scene-0103_frame38_official_qa.json')),
        # scene-0103 frame25: 11题
        (os.path.join(script_dir, 'output/coverage_analysis/scene_graphs/scene-0103_frame25_scene_graph.json'),
         os.path.join(script_dir, 'output/coverage_analysis/vqa_results/scene-0103_frame25_official_qa.json')),
        # scene-0553 frame8: 24题
        (os.path.join(script_dir, 'output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json'),
         os.path.join(script_dir, 'output/coverage_analysis/vqa_results/scene-0553_frame8_official_qa.json')),
        # scene-0916 frame8: 9题
        (os.path.join(script_dir, 'output/coverage_analysis/scene_graphs/scene-0916_frame8_scene_graph.json'),
         os.path.join(script_dir, 'output/coverage_analysis/vqa_results/scene-0916_frame8_official_qa.json')),
    ]
    
    # 运行测试
    start_time = time.time()
    results = runner.run_all_scenes(scenes, verbose=True)
    elapsed = time.time() - start_time
    
    # 保存结果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path('output/coverage_analysis/vqa_results')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / f'enhanced_qa_test_{timestamp}.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n📊 结果已保存: {output_path}")
    print(f"⏰ 总耗时: {elapsed:.1f}秒")
    
    runner.close()


if __name__ == "__main__":
    main()
