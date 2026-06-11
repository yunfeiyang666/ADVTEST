#!/usr/bin/env python
"""
完整LLM VQA评估脚本 - 带多层Retry机制

Retry层级:
1. LLM生成Cypher (Ego Frame, angle_matches)
2. 语法错误修正重试
3. 切换Source Frame重试
4. 使用direction_8精确匹配重试
5. 切换Source Frame + direction_8重试
"""
import json
import sys
import time
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent / 'core_pipeline'))
from vqa_pipeline import VQAPipeline, LLMClient, Neo4jClient
from vqa_pipeline import config
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig


@dataclass
class RetryResult:
    """单次Retry结果"""
    layer: str
    cypher: str
    result: str
    success: bool
    error: Optional[str] = None


@dataclass
class QuestionResult:
    """单题评估结果"""
    question_id: str
    question: str
    ground_truth: str
    final_answer: str
    correct: bool
    retry_history: List[Dict]
    success_layer: Optional[str] = None
    total_time: float = 0.0


class LLMVQAEvaluator:
    """LLM VQA评估器，带完整Retry机制"""
    
    def __init__(self, questions_file: str):
        self.questions = self._load_questions(questions_file)
        self.llm = LLMClient()
        self.neo4j = Neo4jClient()
        self.neo4j_config = Neo4jConfig.from_env()
        self.importer = None
        
        # 统计
        self.stats = {
            'layer1_ego_matches': 0,
            'layer2_syntax_fix': 0,
            'layer3_source_matches': 0,
            'layer4_ego_dir8': 0,
            'layer5_source_dir8': 0,
            'all_failed': 0
        }
    
    def _load_questions(self, file_path: str) -> List[Dict]:
        """加载问题"""
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
    
    def _get_scene_context(self, scene: str) -> str:
        """获取场景上下文"""
        try:
            return self.neo4j.get_scene_summary()
        except:
            return "[场景上下文不可用]"
    
    def _build_direction_hint(self, use_source: bool, use_dir8: bool) -> str:
        """构建方向提示"""
        frame = "source" if use_source else "ego"
        if use_dir8:
            return f"""
使用Source坐标系精确方向匹配:
- 方向属性: r.direction_8_{frame} (精确的8方位: front, back, left, right, front-left, front-right, back-left, back-right)
- 示例: WHERE r.direction_8_{frame} = 'back-right'
"""
        else:
            return f"""
使用{'Source' if use_source else 'Ego'}坐标系方向匹配:
- 方向属性: r.angle_matches_{frame} (列表，包含多个匹配的方向)
- 示例: WHERE 'back-right' IN r.angle_matches_{frame}
"""
    
    def _execute_cypher(self, cypher: str) -> Tuple[bool, str, Optional[str]]:
        """执行Cypher查询
        
        Returns:
            (success, result, error)
        """
        try:
            with self.importer._session() as session:
                result = session.run(cypher)
                record = result.single()
                if record:
                    # 获取第一个返回值
                    value = list(record.values())[0] if record else None
                    if value is None:
                        return True, "null", None
                    return True, str(value), None
                return True, "no_result", None
        except Exception as e:
            error_msg = str(e)
            return False, "", error_msg
    
    def _check_answer(self, result: str, ground_truth: str) -> bool:
        """检查答案是否正确"""
        result = str(result).strip().lower()
        ground_truth = str(ground_truth).strip().lower()
        
        # Boolean/Yes-No
        if ground_truth in ['yes', 'no', 'true', 'false']:
            result_bool = None
            if result in ['yes', 'true', '1'] or (result not in ['no', 'false', '0', 'null', 'no_result', ''] and result != '0'):
                result_bool = 'yes'
            else:
                result_bool = 'no'
            gt_bool = 'yes' if ground_truth in ['yes', 'true'] else 'no'
            return result_bool == gt_bool
        
        # Numeric
        if ground_truth.isdigit():
            try:
                return int(float(result)) == int(ground_truth)
            except:
                return False
        
        # String match
        return result == ground_truth
    
    def _generate_cypher_with_hints(self, question: str, question_type: str, 
                                    scene_context: str, direction_hint: str,
                                    prev_error: Optional[str] = None) -> str:
        """使用LLM生成Cypher，带方向提示"""
        
        feedback = None
        if prev_error:
            feedback = f"之前的查询出错: {prev_error}\n请修正语法错误后重新生成。"
        
        # 增强的system prompt
        enhanced_prompt = f"""
{direction_hint}

场景上下文:
{scene_context[:1000]}

重要规则:
1. 对象通过 unique_id 唯一标识，格式如 'scene-0103_ego', 'scene-0103_car1'
2. 关系类型为 RELATES_TO
3. 方向匹配必须使用上面指定的属性
4. 返回的结果应该直接可以回答问题（数量用count，是否存在用exists等）
"""
        
        cypher = self.llm.generate_cypher(
            question=question,
            question_type=question_type,
            feedback=feedback,
            scene_context=enhanced_prompt
        )
        return cypher
    
    def _evaluate_single_question(self, q: Dict, verbose: bool = True) -> QuestionResult:
        """评估单个问题，使用多层Retry"""
        start_time = time.time()
        retry_history = []
        scene_context = self._get_scene_context(q['scene'])
        
        if verbose:
            print(f"\n{'='*60}")
            print(f"问题: {q['question'][:80]}...")
            print(f"预期: {q['ground_truth']}")
        
        # ============ Layer 1: Ego + angle_matches ============
        if verbose:
            print(f"\n  [Layer 1] Ego + angle_matches")
        
        direction_hint = self._build_direction_hint(use_source=False, use_dir8=False)
        try:
            cypher = self._generate_cypher_with_hints(
                q['question'], q['question_type'], scene_context, direction_hint
            )
            if verbose:
                print(f"    Cypher: {cypher[:100]}...")
            
            success, result, error = self._execute_cypher(cypher)
            
            retry_history.append({
                'layer': 'ego_matches',
                'cypher': cypher,
                'result': result,
                'success': success,
                'error': error
            })
            
            if success and self._check_answer(result, q['ground_truth']):
                self.stats['layer1_ego_matches'] += 1
                if verbose:
                    print(f"    ✓ 成功: {result}")
                return QuestionResult(
                    question_id=q['id'],
                    question=q['question'],
                    ground_truth=q['ground_truth'],
                    final_answer=result,
                    correct=True,
                    retry_history=retry_history,
                    success_layer='layer1_ego_matches',
                    total_time=time.time() - start_time
                )
            
            if verbose:
                print(f"    ✗ 失败: {result} (error: {error})")
            
        except Exception as e:
            if verbose:
                print(f"    ✗ 异常: {e}")
            retry_history.append({
                'layer': 'ego_matches',
                'cypher': '',
                'result': '',
                'success': False,
                'error': str(e)
            })
        
        # ============ Layer 2: 语法修正重试 ============
        last_error = retry_history[-1].get('error') if retry_history else None
        if last_error and ('syntax' in last_error.lower() or 'invalid' in last_error.lower()):
            if verbose:
                print(f"\n  [Layer 2] 语法修正重试")
            
            try:
                cypher = self._generate_cypher_with_hints(
                    q['question'], q['question_type'], scene_context, direction_hint,
                    prev_error=last_error
                )
                if verbose:
                    print(f"    Cypher: {cypher[:100]}...")
                
                success, result, error = self._execute_cypher(cypher)
                
                retry_history.append({
                    'layer': 'syntax_fix',
                    'cypher': cypher,
                    'result': result,
                    'success': success,
                    'error': error
                })
                
                if success and self._check_answer(result, q['ground_truth']):
                    self.stats['layer2_syntax_fix'] += 1
                    if verbose:
                        print(f"    ✓ 成功: {result}")
                    return QuestionResult(
                        question_id=q['id'],
                        question=q['question'],
                        ground_truth=q['ground_truth'],
                        final_answer=result,
                        correct=True,
                        retry_history=retry_history,
                        success_layer='layer2_syntax_fix',
                        total_time=time.time() - start_time
                    )
                
                if verbose:
                    print(f"    ✗ 失败: {result}")
                    
            except Exception as e:
                if verbose:
                    print(f"    ✗ 异常: {e}")
        
        # ============ Layer 3: Source + angle_matches ============
        if verbose:
            print(f"\n  [Layer 3] Source + angle_matches")
        
        direction_hint = self._build_direction_hint(use_source=True, use_dir8=False)
        try:
            cypher = self._generate_cypher_with_hints(
                q['question'], q['question_type'], scene_context, direction_hint
            )
            if verbose:
                print(f"    Cypher: {cypher[:100]}...")
            
            success, result, error = self._execute_cypher(cypher)
            
            retry_history.append({
                'layer': 'source_matches',
                'cypher': cypher,
                'result': result,
                'success': success,
                'error': error
            })
            
            if success and self._check_answer(result, q['ground_truth']):
                self.stats['layer3_source_matches'] += 1
                if verbose:
                    print(f"    ✓ 成功: {result}")
                return QuestionResult(
                    question_id=q['id'],
                    question=q['question'],
                    ground_truth=q['ground_truth'],
                    final_answer=result,
                    correct=True,
                    retry_history=retry_history,
                    success_layer='layer3_source_matches',
                    total_time=time.time() - start_time
                )
            
            if verbose:
                print(f"    ✗ 失败: {result}")
                
        except Exception as e:
            if verbose:
                print(f"    ✗ 异常: {e}")
        
        # ============ Layer 4: Ego + direction_8 ============
        if verbose:
            print(f"\n  [Layer 4] Ego + direction_8 (精确)")
        
        direction_hint = self._build_direction_hint(use_source=False, use_dir8=True)
        try:
            cypher = self._generate_cypher_with_hints(
                q['question'], q['question_type'], scene_context, direction_hint
            )
            if verbose:
                print(f"    Cypher: {cypher[:100]}...")
            
            success, result, error = self._execute_cypher(cypher)
            
            retry_history.append({
                'layer': 'ego_dir8',
                'cypher': cypher,
                'result': result,
                'success': success,
                'error': error
            })
            
            if success and self._check_answer(result, q['ground_truth']):
                self.stats['layer4_ego_dir8'] += 1
                if verbose:
                    print(f"    ✓ 成功: {result}")
                return QuestionResult(
                    question_id=q['id'],
                    question=q['question'],
                    ground_truth=q['ground_truth'],
                    final_answer=result,
                    correct=True,
                    retry_history=retry_history,
                    success_layer='layer4_ego_dir8',
                    total_time=time.time() - start_time
                )
            
            if verbose:
                print(f"    ✗ 失败: {result}")
                
        except Exception as e:
            if verbose:
                print(f"    ✗ 异常: {e}")
        
        # ============ Layer 5: Source + direction_8 ============
        if verbose:
            print(f"\n  [Layer 5] Source + direction_8 (精确)")
        
        direction_hint = self._build_direction_hint(use_source=True, use_dir8=True)
        try:
            cypher = self._generate_cypher_with_hints(
                q['question'], q['question_type'], scene_context, direction_hint
            )
            if verbose:
                print(f"    Cypher: {cypher[:100]}...")
            
            success, result, error = self._execute_cypher(cypher)
            
            retry_history.append({
                'layer': 'source_dir8',
                'cypher': cypher,
                'result': result,
                'success': success,
                'error': error
            })
            
            if success and self._check_answer(result, q['ground_truth']):
                self.stats['layer5_source_dir8'] += 1
                if verbose:
                    print(f"    ✓ 成功: {result}")
                return QuestionResult(
                    question_id=q['id'],
                    question=q['question'],
                    ground_truth=q['ground_truth'],
                    final_answer=result,
                    correct=True,
                    retry_history=retry_history,
                    success_layer='layer5_source_dir8',
                    total_time=time.time() - start_time
                )
            
            if verbose:
                print(f"    ✗ 失败: {result}")
                
        except Exception as e:
            if verbose:
                print(f"    ✗ 异常: {e}")
        
        # ============ 所有层都失败 ============
        self.stats['all_failed'] += 1
        if verbose:
            print(f"\n  ✗ 所有层都失败")
        
        return QuestionResult(
            question_id=q['id'],
            question=q['question'],
            ground_truth=q['ground_truth'],
            final_answer="all_failed",
            correct=False,
            retry_history=retry_history,
            success_layer=None,
            total_time=time.time() - start_time
        )
    
    def run(self, verbose: bool = True):
        """运行完整评估"""
        print("\n" + "="*80)
        print("LLM VQA评估 (带多层Retry)")
        print("="*80)
        print(f"问题总数: {len(self.questions)}")
        print(f"Retry层级:")
        print(f"  Layer 1: Ego + angle_matches")
        print(f"  Layer 2: 语法修正")
        print(f"  Layer 3: Source + angle_matches")
        print(f"  Layer 4: Ego + direction_8")
        print(f"  Layer 5: Source + direction_8")
        
        # 初始化连接
        print(f"\n连接Neo4j...")
        if not self.neo4j.connect():
            print("✗ Neo4j连接失败")
            return
        print("✓ Neo4j连接成功")
        
        self.importer = Neo4jImporter(self.neo4j_config)
        
        results = []
        total_start = time.time()
        
        try:
            for i, q in enumerate(self.questions):
                print(f"\n[{i+1}/{len(self.questions)}] 评估问题...")
                result = self._evaluate_single_question(q, verbose=verbose)
                results.append(result)
                
                # 中间进度
                if (i + 1) % 10 == 0:
                    correct = sum(1 for r in results if r.correct)
                    print(f"\n--- 进度: {i+1}/{len(self.questions)}, 当前准确率: {correct}/{i+1} ({100*correct/(i+1):.1f}%) ---")
        
        finally:
            self.neo4j.close()
            if self.importer:
                self.importer.close()
        
        total_time = time.time() - total_start
        
        # 统计结果
        correct = sum(1 for r in results if r.correct)
        accuracy = 100 * correct / len(self.questions) if self.questions else 0
        
        print("\n" + "="*80)
        print("评估结果汇总")
        print("="*80)
        print(f"\n总计: {correct}/{len(self.questions)} ({accuracy:.2f}%)")
        print(f"总耗时: {total_time:.1f}秒 (平均 {total_time/len(self.questions):.1f}秒/题)")
        print(f"\n各层成功统计:")
        print(f"  Layer 1 (Ego+angle_matches): {self.stats['layer1_ego_matches']}")
        print(f"  Layer 2 (语法修正): {self.stats['layer2_syntax_fix']}")
        print(f"  Layer 3 (Source+angle_matches): {self.stats['layer3_source_matches']}")
        print(f"  Layer 4 (Ego+direction_8): {self.stats['layer4_ego_dir8']}")
        print(f"  Layer 5 (Source+direction_8): {self.stats['layer5_source_dir8']}")
        print(f"  全部失败: {self.stats['all_failed']}")
        
        # 保存结果
        output_data = {
            'total_questions': len(self.questions),
            'correct': correct,
            'accuracy': accuracy,
            'total_time_seconds': total_time,
            'layer_stats': self.stats,
            'results': [asdict(r) for r in results]
        }
        
        output_path = Path('output/vqa_llm_evaluation_results.json')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 详细结果已保存至: {output_path}")
        
        return output_data


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM VQA评估")
    parser.add_argument("--questions", "-q", default="output/vqa_questions_all_official.json",
                        help="问题文件路径")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    
    args = parser.parse_args()
    
    print(f"加载问题文件: {args.questions}")
    evaluator = LLMVQAEvaluator(args.questions)
    evaluator.run(verbose=not args.quiet)
    print("\n✓ 评估完成")


if __name__ == "__main__":
    main()
