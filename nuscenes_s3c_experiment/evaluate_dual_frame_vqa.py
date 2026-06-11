#!/usr/bin/env python
"""
双坐标系VQA评估框架

评估三种策略：
1. 仅使用Ego Frame
2. 仅使用Source Frame  
3. Retry机制（Ego失败则切换Source）
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent / 'core_pipeline'))
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig


@dataclass
class EvaluationResult:
    """评估结果"""
    strategy: str
    total_questions: int
    correct: int
    incorrect: int
    accuracy: float
    details: List[Dict]


class DualFrameEvaluator:
    """双坐标系VQA评估器"""
    
    def __init__(self, questions_file: str):
        """初始化评估器
        
        Args:
            questions_file: VQA问题文件路径（JSON格式）
        """
        self.questions = self._load_questions(questions_file)
        self.config = Neo4jConfig.from_env()
        
    def _load_questions(self, file_path: str) -> List[Dict]:
        """加载VQA问题"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 转换为列表格式
        questions = []
        for q_id, q_data in data.items():
            questions.append({
                'id': q_id,
                'question': q_data['question'],
                'ground_truth': q_data['ground_truth'],
                'scene': q_data['metadata']['scene_name'],
                'frame': q_data['metadata'].get('frame_index', 0)
            })
        
        return questions
    
    def _query_neo4j_ego_frame(self, question_data: Dict) -> Tuple[bool, str]:
        """使用Ego Frame查询
        
        Returns:
            (success, result): 查询是否成功，查询结果
        """
        # TODO: 实现具体的Ego Frame查询逻辑
        # 这里需要根据问题类型生成不同的Cypher查询
        # 使用 r.angle_matches_ego 匹配方向
        
        return False, "Not implemented"
    
    def _query_neo4j_source_frame(self, question_data: Dict) -> Tuple[bool, str]:
        """使用Source Frame查询
        
        Returns:
            (success, result): 查询是否成功，查询结果
        """
        # TODO: 实现具体的Source Frame查询逻辑
        # 使用 r.angle_matches_source 匹配方向
        
        return False, "Not implemented"
    
    def _query_with_retry(self, question_data: Dict) -> Tuple[bool, str, str]:
        """Retry策略：先Ego，失败则Source
        
        Returns:
            (success, result, used_frame): 查询是否成功，查询结果，使用的坐标系
        """
        # 1. 先尝试Ego Frame
        success, result = self._query_neo4j_ego_frame(question_data)
        if success:
            return True, result, "ego"
        
        # 2. Ego失败，尝试Source Frame
        success, result = self._query_neo4j_source_frame(question_data)
        if success:
            return True, result, "source"
        
        return False, result, "both_failed"
    
    def _check_answer(self, result: str, ground_truth: str) -> bool:
        """检查答案是否正确
        
        Args:
            result: 查询结果
            ground_truth: 正确答案
            
        Returns:
            是否正确
        """
        # TODO: 实现答案匹配逻辑
        # 可能需要模糊匹配或语义匹配
        return result.lower().strip() == ground_truth.lower().strip()
    
    def evaluate_ego_only(self) -> EvaluationResult:
        """评估仅使用Ego Frame的策略"""
        print("\n" + "="*60)
        print("评估策略1: 仅使用Ego Frame")
        print("="*60)
        
        correct = 0
        details = []
        
        for i, q in enumerate(self.questions):
            print(f"\n[{i+1}/{len(self.questions)}] {q['id']}: {q['question'][:50]}...")
            
            success, result = self._query_neo4j_ego_frame(q)
            is_correct = success and self._check_answer(result, q['ground_truth'])
            
            if is_correct:
                correct += 1
                print(f"  ✓ 正确")
            else:
                print(f"  ✗ 错误 (result: {result})")
            
            details.append({
                'question_id': q['id'],
                'question': q['question'],
                'ground_truth': q['ground_truth'],
                'result': result,
                'success': success,
                'correct': is_correct
            })
        
        accuracy = correct / len(self.questions) * 100
        return EvaluationResult(
            strategy="Ego Frame Only",
            total_questions=len(self.questions),
            correct=correct,
            incorrect=len(self.questions) - correct,
            accuracy=accuracy,
            details=details
        )
    
    def evaluate_source_only(self) -> EvaluationResult:
        """评估仅使用Source Frame的策略"""
        print("\n" + "="*60)
        print("评估策略2: 仅使用Source Frame")
        print("="*60)
        
        correct = 0
        details = []
        
        for i, q in enumerate(self.questions):
            print(f"\n[{i+1}/{len(self.questions)}] {q['id']}: {q['question'][:50]}...")
            
            success, result = self._query_neo4j_source_frame(q)
            is_correct = success and self._check_answer(result, q['ground_truth'])
            
            if is_correct:
                correct += 1
                print(f"  ✓ 正确")
            else:
                print(f"  ✗ 错误 (result: {result})")
            
            details.append({
                'question_id': q['id'],
                'question': q['question'],
                'ground_truth': q['ground_truth'],
                'result': result,
                'success': success,
                'correct': is_correct
            })
        
        accuracy = correct / len(self.questions) * 100
        return EvaluationResult(
            strategy="Source Frame Only",
            total_questions=len(self.questions),
            correct=correct,
            incorrect=len(self.questions) - correct,
            accuracy=accuracy,
            details=details
        )
    
    def evaluate_retry(self) -> EvaluationResult:
        """评估Retry策略"""
        print("\n" + "="*60)
        print("评估策略3: Retry机制（Ego -> Source）")
        print("="*60)
        
        correct = 0
        details = []
        ego_success_count = 0
        source_success_count = 0
        
        for i, q in enumerate(self.questions):
            print(f"\n[{i+1}/{len(self.questions)}] {q['id']}: {q['question'][:50]}...")
            
            success, result, used_frame = self._query_with_retry(q)
            is_correct = success and self._check_answer(result, q['ground_truth'])
            
            if is_correct:
                correct += 1
                print(f"  ✓ 正确 (使用{used_frame}坐标系)")
            else:
                print(f"  ✗ 错误 (result: {result})")
            
            if used_frame == "ego":
                ego_success_count += 1
            elif used_frame == "source":
                source_success_count += 1
            
            details.append({
                'question_id': q['id'],
                'question': q['question'],
                'ground_truth': q['ground_truth'],
                'result': result,
                'success': success,
                'correct': is_correct,
                'used_frame': used_frame
            })
        
        accuracy = correct / len(self.questions) * 100
        print(f"\n统计: Ego成功{ego_success_count}次, Source成功{source_success_count}次")
        
        return EvaluationResult(
            strategy="Retry (Ego -> Source)",
            total_questions=len(self.questions),
            correct=correct,
            incorrect=len(self.questions) - correct,
            accuracy=accuracy,
            details=details
        )
    
    def run_full_evaluation(self) -> Dict:
        """运行完整评估"""
        print("\n" + "="*80)
        print("双坐标系VQA评估")
        print("="*80)
        print(f"问题总数: {len(self.questions)}")
        
        # 评估三种策略
        result_ego = self.evaluate_ego_only()
        result_source = self.evaluate_source_only()
        result_retry = self.evaluate_retry()
        
        # 打印汇总结果
        print("\n" + "="*80)
        print("评估结果汇总")
        print("="*80)
        
        results = [result_ego, result_source, result_retry]
        for result in results:
            print(f"\n{result.strategy}:")
            print(f"  正确: {result.correct}/{result.total_questions}")
            print(f"  准确率: {result.accuracy:.2f}%")
        
        # 保存详细结果
        output_data = {
            'total_questions': len(self.questions),
            'results': {
                'ego_only': {
                    'accuracy': result_ego.accuracy,
                    'correct': result_ego.correct,
                    'details': result_ego.details
                },
                'source_only': {
                    'accuracy': result_source.accuracy,
                    'correct': result_source.correct,
                    'details': result_source.details
                },
                'retry': {
                    'accuracy': result_retry.accuracy,
                    'correct': result_retry.correct,
                    'details': result_retry.details
                }
            }
        }
        
        output_path = Path('output/vqa_dual_frame_evaluation.json')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n详细结果已保存至: {output_path}")
        
        return output_data


def main():
    """主函数"""
    # TODO: 替换为实际的VQA问题文件路径
    questions_file = "path/to/vqa_questions.json"
    
    print(f"加载VQA问题: {questions_file}")
    
    evaluator = DualFrameEvaluator(questions_file)
    results = evaluator.run_full_evaluation()
    
    print("\n✓ 评估完成")


if __name__ == "__main__":
    # 当前框架已搭建完成，需要：
    # 1. 实现_query_neo4j_ego_frame和_query_neo4j_source_frame的具体查询逻辑
    # 2. 准备VQA问题文件
    # 3. 实现答案匹配逻辑
    
    print("双坐标系VQA评估框架已创建")
    print("\n下一步:")
    print("1. 实现具体的Cypher查询逻辑")
    print("2. 准备VQA问题文件（包含58道题目）")
    print("3. 实现答案匹配逻辑")
    print("4. 运行完整评估")
