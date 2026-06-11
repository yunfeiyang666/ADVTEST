"""
VQA Pipeline 主流程
问题 -> 规范化 -> Cypher查询 -> 执行 -> 答案生成 -> 格式化
"""
import json
import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from .llm_client import LLMClient
from .neo4j_client import Neo4jClient
from .question_normalizer import QuestionNormalizer
from .answer_formatter import AnswerFormatter
from .ir_patterns import match_hardcoded_query_plan
from . import config

logger = logging.getLogger(__name__)


@dataclass
class VQAResult:
    """VQA结果数据类"""
    question: str           # 原始问题
    cypher_query: str       # 生成的Cypher查询
    query_result: Dict[str, Any]  # 查询结果
    answer: str             # 最终（格式化后的）答案
    success: bool           # 是否成功
    error: Optional[str]    # 错误信息
    # 额外调试信息（可选）
    normalized_question: str = ""
    question_type: str = ""
    query_plan_json: Optional[Dict[str, Any]] = None
    raw_answer: str = ""   # LLM原始答案
    ir_raw_text: str = ""  # LLM生成的IR原始文本
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class VQAPipeline:
    """
    NuScenes VQA Pipeline
    
    完整流程：
    1. 接收自然语言问题
    2. 调用LLM将问题翻译为Cypher查询
    3. 在Neo4j中执行查询
    4. 调用LLM将查询结果翻译为自然语言答案
    
    支持上下文管理器：
        with VQAPipeline() as pipeline:
            result = pipeline.process_question("...")
    """
    
    def __init__(self, llm_client: LLMClient = None, neo4j_client: Neo4jClient = None, 
                 use_ir: bool = False, ir_mode: str = "rule"):
        """
        Args:
            llm_client: LLM客户端
            neo4j_client: Neo4j客户端
            use_ir: 是否启用IR中间表示
            ir_mode: IR转Cypher的模式
                - "rule": 使用程序规则转换 (默认)
                - "llm": 使用LLM生成Cypher
        """
        self.llm = llm_client or LLMClient()
        self.neo4j = neo4j_client or Neo4jClient()
        self.question_normalizer = QuestionNormalizer()
        self.answer_formatter = AnswerFormatter()
        # 是否启用 IR -> Cypher 的新链路
        self.use_ir = use_ir
        # 强制IR走LLM生成Cypher（程序生成方案弃用）
        if self.use_ir and ir_mode != "llm":
            logger.warning("IR 模式下已强制使用 LLM 生成 Cypher（忽略 rule 模式）")
        self.ir_mode = "llm" if self.use_ir else ir_mode
        self._initialized = False
    
    def __enter__(self) -> 'VQAPipeline':
        """Context manager entry."""
        if not self._initialized:
            self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
        
    def initialize(self, quiet: bool = False) -> bool:
        """初始化连接
        
        Args:
            quiet: 是否静默模式（不打印提示信息）
        
        Returns:
            True if initialization successful
        """
        if self._initialized:
            return True
        
        if not quiet:
            print("="*60)
            print("  VQA Pipeline 初始化")
            print("="*60)
            print("\n⚠️ 请确保Neo4j数据库已启动!")
            print(f"   URI: {self.neo4j.uri}")
            print(f"   或访问: http://localhost:7474\n")
        
        # 连接Neo4j
        if not self.neo4j.connect():
            if not quiet:
                print("\n❌ Neo4j连接失败！请先启动数据库。")
            logger.error(f"Failed to connect to Neo4j at {self.neo4j.uri}")
            return False
        
        self._initialized = True
        if not quiet:
            print("✓ VQA Pipeline 初始化完成")
        logger.info("VQA Pipeline initialized successfully")
        return True
    
    def process_question(self, question: str, verbose: bool = True, cypher_feedback: Optional[str] = None) -> VQAResult:
        """
        处理单个问题
        
        Args:
            question: 自然语言问题
            verbose: 是否打印详细信息
            cypher_feedback: Cypher重试反馈信息（用于修正查询）
            
        Returns:
            VQAResult对象
        """
        # Ensure connection is initialized
        if not self._initialized:
            if not self.initialize(quiet=not verbose):
                return VQAResult(
                    question=question,
                    cypher_query="",
                    query_result={},
                    answer="处理失败: 未连接到Neo4j数据库",
                    success=False,
                    error="Neo4j connection not initialized"
                )
        
        if verbose:
            print(f"\n{'='*60}")
            print(f"问题: {question}")
            print(f"{'='*60}")
        
        try:
            
            # Step 0: 问题规范化
            if verbose:
                print("\n[Step 0] 规范化问题...")
            normalized_question, question_type = self.question_normalizer.normalize(question)
            format_requirement = self.question_normalizer.get_expected_format(question_type)
            if verbose:
                if normalized_question != question:
                    print(f"  原始问题: {question}")
                    print(f"  规范化后: {normalized_question}")
                print(f"  问题类型: {question_type}")
                print(f"  答案格式: {format_requirement}")
            
            # Step 0.5: 场景上下文不需要，LLM只需要Schema就能生成Cypher
            # scene_context = ""  # 已移除
            
            # Step 1: 问题 -> IR -> Cypher 或直接问题 -> Cypher（兼容老流程）
            query_plan = None
            ir_raw_text = ""
            if self.use_ir:
                # 先尝试基于模式的硬编码QueryPlan
                pattern_plan = match_hardcoded_query_plan(normalized_question, question_type)
                if pattern_plan is not None:
                    query_plan = pattern_plan
                    ir_raw_text = json.dumps(pattern_plan, ensure_ascii=False)
                    if verbose:
                        print("\n[Step 1] 命中硬编码QueryPlan模式，跳过LLM生成...")
                        print(json.dumps(query_plan, ensure_ascii=False, indent=2))
                else:
                    if verbose:
                        print("\n[Step 1] 生成QueryPlan (IR)...")
                    ir_raw_text = self.llm.generate_query_plan(normalized_question, question_type)
                    if verbose:
                        print(f"  ⏱️ 耗时: {self.llm.last_elapsed:.2f}秒")
                        print("  📝 原始QueryPlan文本:")
                        print("-" * 50)
                        print(ir_raw_text)
                        print("-" * 50)
                    # 解析JSON
                    try:
                        query_plan = json.loads(ir_raw_text)
                    except Exception as e:
                        raise RuntimeError(f"解析QueryPlan JSON失败: {e} | 原始文本: {ir_raw_text}")

                if verbose and query_plan is not None:
                    print("  ✅ QueryPlan JSON解析成功")
                    print(json.dumps(query_plan, ensure_ascii=False, indent=2))

                # IR -> Cypher
                if verbose:
                    print(f"\n[Step 1.5] QueryPlan -> Cypher 查询 (模式: {self.ir_mode})...")
                
                if self.ir_mode == "llm":
                    # 使用LLM根据IR生成Cypher
                    cypher_query = self.llm.generate_cypher_from_ir(
                        query_plan,
                        normalized_question,
                        cypher_feedback
                    )
                    if verbose:
                        print(f"  ⏱️ 耗时: {self.llm.last_elapsed:.2f}秒")
                        if self.llm.last_thinking:
                            print(f"  💭 AI思维过程:")
                            print("-" * 50)
                            thinking = self.llm.last_thinking
                            if len(thinking) > 500:
                                thinking = thinking[:500] + "...(省略)"
                            for line in thinking.split('\n'):
                                print(f"    {line}")
                            print("-" * 50)
                else:
                    # 程序生成Cypher路径已弃用
                    raise RuntimeError("IR rule-based Cypher generation has been removed; use ir_mode='llm'.")
                
                if verbose:
                    print("  📝 由IR生成的Cypher:")
                    print(cypher_query)
            else:
                # 旧流程：直接由LLM生成Cypher（是否重试由上层控制，这里只接受一次反馈）
                if verbose:
                    print("\n[Step 1] 生成Cypher查询...")
                cypher_query = self.llm.generate_cypher(
                    normalized_question,
                    question_type,
                    feedback=cypher_feedback,
                    scene_context=None,  # 不再传递场景数据
                )
                if verbose:
                    print(f"  ⏱️ 耗时: {self.llm.last_elapsed:.2f}秒")
                    if self.llm.last_thinking:
                        print(f"  💭 AI思维过程:")
                        print("-" * 50)
                        thinking = self.llm.last_thinking
                        if len(thinking) > 800:
                            thinking = thinking[:800] + "...(省略)"
                        for line in thinking.split('\n'):
                            print(f"    {line}")
                        print("-" * 50)
                if verbose:
                    print(f"  📝 Cypher: {cypher_query}")
            
            # Step 2: 执行查询
            if verbose:
                print("\n[Step 2] 执行Neo4j查询...")
            step2_start = time.time()
            query_result = self.neo4j.execute_query(cypher_query)
            step2_elapsed = time.time() - step2_start
            if verbose:
                print(f"  ⏱️ 耗时: {step2_elapsed:.3f}秒")
                print(f"  📊 结果数量: {query_result['count']}")
                if query_result['count'] > 0 and query_result['count'] <= 5:
                    print(f"  📋 数据: {json.dumps(query_result['data'], ensure_ascii=False)}")
            
            # Step 3: 结果 -> 自然语言
            if verbose:
                print("\n[Step 3] 生成自然语言答案...")
            result_json = json.dumps(query_result, ensure_ascii=False)
            raw_answer = self.llm.generate_answer(
                normalized_question,
                result_json,
                question_type,
                format_requirement
            )
            if verbose:
                print(f"  ⏱️ 耗时: {self.llm.last_elapsed:.2f}秒")
                if self.llm.last_thinking:
                    print(f"  💭 AI思维过程:")
                    print("-" * 50)
                    thinking = self.llm.last_thinking
                    if len(thinking) > 800:
                        thinking = thinking[:800] + "...(省略)"
                    for line in thinking.split('\n'):
                        print(f"    {line}")
                    print("-" * 50)
                print(f"  🔄 原始答案: {raw_answer}")
            
            # Step 3.5: 答案格式化和验证
            if verbose:
                print("\n[Step 3.5] 格式化和验证答案...")
            formatted_answer = self.answer_formatter.format(
                raw_answer, 
                question_type, 
                query_result
            )
            is_valid = self.answer_formatter.validate(formatted_answer, question_type)
            if verbose:
                print(f"  📝 格式化后: {formatted_answer}")
                print(f"  ✅ 验证通过: {'是' if is_valid else '否'}")
                if not is_valid:
                    print(f"  ⚠️  答案格式可能不符合要求")
            
            # 使用格式化后的答案
            answer = formatted_answer
            
            return VQAResult(
                question=question,
                cypher_query=cypher_query,
                query_result=query_result,
                answer=answer,
                success=True,
                error=None,
                normalized_question=normalized_question,
                question_type=question_type,
                query_plan_json=query_plan,
                raw_answer=raw_answer,
                ir_raw_text=ir_raw_text,
            )
            
        except (RuntimeError, ValueError, json.JSONDecodeError) as e:
            # Expected exceptions from LLM/parsing failures
            error_msg = str(e)
            logger.warning(f"Question processing failed: {error_msg}")
            if verbose:
                print(f"\n[错误] {error_msg}")
            
            return VQAResult(
                question=question,
                cypher_query="",
                query_result={},
                answer=f"处理失败: {error_msg}",
                success=False,
                error=error_msg
            )
        except Exception as e:
            # Unexpected exceptions - log full traceback
            error_msg = str(e)
            logger.exception(f"Unexpected error processing question: {error_msg}")
            if verbose:
                print(f"\n[严重错误] {error_msg}")
            
            return VQAResult(
                question=question,
                cypher_query="",
                query_result={},
                answer=f"处理失败: {error_msg}",
                success=False,
                error=error_msg
            )
    
    def process_question_with_retry(self, question: str, expected_answer: str = None, 
                                       max_retries: int = 5, verbose: bool = True) -> VQAResult:
        """
        带多层Retry的问题处理
        
        Retry层级:
        1. 基础尝试 (Ego Frame, angle_matches_ego)
        2. 语法错误修正重试
        3. 切换Source Frame (angle_matches_source)
        4. Ego Frame精确匹配 (direction_8_ego)
        5. Source Frame精确匹配 (direction_8_source)
        
        Args:
            question: 自然语言问题
            expected_answer: 预期答案（用于验证，可选）
            max_retries: 最大重试次数
            verbose: 是否打印详细信息
            
        Returns:
            VQAResult对象，包含retry历史
        """
        if not self._initialized:
            if not self.initialize(quiet=not verbose):
                return VQAResult(
                    question=question,
                    cypher_query="",
                    query_result={},
                    answer="处理失败: 未连接到Neo4j数据库",
                    success=False,
                    error="Neo4j connection not initialized"
                )
        
        # 定义retry策略
        retry_strategies = [
            {
                'name': 'ego_angle_matches',
                'description': 'Ego Frame + angle_matches_ego (宽松)',
                'direction_hint': "方向匹配使用: 'DIRECTION' IN r.angle_matches_ego",
                'feedback': None
            },
            {
                'name': 'syntax_fix',
                'description': '语法错误修正',
                'direction_hint': "方向匹配使用: 'DIRECTION' IN r.angle_matches_ego",
                'feedback': None  # 会在运行时填充
            },
            {
                'name': 'source_angle_matches', 
                'description': 'Source Frame + angle_matches_source (宽松)',
                'direction_hint': "方向匹配使用: 'DIRECTION' IN r.angle_matches_source (基于source对象朝向)",
                'feedback': None
            },
            {
                'name': 'ego_direction_8',
                'description': 'Ego Frame + direction_8_ego (精确45度)',
                'direction_hint': "方向匹配使用: r.direction_8_ego = 'DIRECTION' (精确匹配)",
                'feedback': None
            },
            {
                'name': 'source_direction_8',
                'description': 'Source Frame + direction_8_source (精确45度)',
                'direction_hint': "方向匹配使用: r.direction_8_source = 'DIRECTION' (精确匹配, 基于source对象朝向)",
                'feedback': None
            },
        ]
        
        if verbose:
            print(f"\n{'='*60}")
            print(f"问题: {question}")
            if expected_answer:
                print(f"预期答案: {expected_answer}")
            print(f"{'='*60}")
        
        # Step 0: 问题规范化
        normalized_question, question_type = self.question_normalizer.normalize(question)
        format_requirement = self.question_normalizer.get_expected_format(question_type)
        scene_context = self.neo4j.get_scene_summary()
        
        retry_history = []
        last_error = None
        
        for i, strategy in enumerate(retry_strategies[:max_retries]):
            if verbose:
                print(f"\n[Retry {i+1}/{min(max_retries, len(retry_strategies))}] {strategy['description']}")
            
            try:
                # 准备feedback
                feedback = strategy['feedback']
                if strategy['name'] == 'syntax_fix' and last_error:
                    feedback = f"之前的查询出错: {last_error}\n请修正语法错误后重新生成。"
                elif strategy['name'] != 'ego_angle_matches':
                    # 非第一次尝试，添加方向提示
                    feedback = f"之前的方向匹配可能不准确。\n{strategy['direction_hint']}"
                
                # 生成Cypher
                cypher_query = self.llm.generate_cypher(
                    normalized_question,
                    question_type,
                    feedback=feedback,
                    scene_context=scene_context + f"\n\n方向匹配提示: {strategy['direction_hint']}",
                )
                
                if verbose:
                    print(f"  Cypher: {cypher_query[:150]}...")
                
                # 执行查询
                query_result = self.neo4j.execute_query(cypher_query)
                
                # 记录retry历史
                retry_entry = {
                    'layer': strategy['name'],
                    'cypher': cypher_query,
                    'result': query_result,
                    'success': query_result.get('success', False),
                    'error': query_result.get('error')
                }
                retry_history.append(retry_entry)
                
                # 检查查询是否成功
                if not query_result.get('success'):
                    last_error = query_result.get('error', 'Unknown error')
                    if verbose:
                        print(f"  ✗ 查询失败: {last_error}")
                    continue
                
                # 生成答案
                result_json = json.dumps(query_result, ensure_ascii=False)
                raw_answer = self.llm.generate_answer(
                    normalized_question,
                    result_json,
                    question_type,
                    format_requirement
                )
                formatted_answer = self.answer_formatter.format(
                    raw_answer, 
                    question_type, 
                    query_result
                )
                
                if verbose:
                    print(f"  答案: {formatted_answer}")
                
                # 如果有预期答案，检查是否匹配
                if expected_answer:
                    is_correct = self._check_answer_match(formatted_answer, expected_answer, question_type)
                    if is_correct:
                        if verbose:
                            print(f"  ✓ 答案正确!")
                        return VQAResult(
                            question=question,
                            cypher_query=cypher_query,
                            query_result=query_result,
                            answer=formatted_answer,
                            success=True,
                            error=None,
                            normalized_question=normalized_question,
                            question_type=question_type,
                            raw_answer=raw_answer,
                        )
                    else:
                        if verbose:
                            print(f"  ✗ 答案不匹配 (expected: {expected_answer})")
                        last_error = f"答案不匹配: got '{formatted_answer}', expected '{expected_answer}'"
                        continue
                else:
                    # 没有预期答案，查询成功即返回
                    return VQAResult(
                        question=question,
                        cypher_query=cypher_query,
                        query_result=query_result,
                        answer=formatted_answer,
                        success=True,
                        error=None,
                        normalized_question=normalized_question,
                        question_type=question_type,
                        raw_answer=raw_answer,
                    )
                    
            except Exception as e:
                last_error = str(e)
                if verbose:
                    print(f"  ✗ 异常: {last_error}")
                retry_history.append({
                    'layer': strategy['name'],
                    'cypher': '',
                    'result': {},
                    'success': False,
                    'error': last_error
                })
                continue
        
        # 所有retry都失败
        if verbose:
            print(f"\n✗ 所有{min(max_retries, len(retry_strategies))}层retry都失败")
        
        return VQAResult(
            question=question,
            cypher_query=retry_history[-1]['cypher'] if retry_history else '',
            query_result=retry_history[-1]['result'] if retry_history else {},
            answer=f"处理失败: {last_error}",
            success=False,
            error=last_error,
            normalized_question=normalized_question,
            question_type=question_type,
        )
    
    def _check_answer_match(self, actual: str, expected: str, question_type: str) -> bool:
        """检查答案是否匹配"""
        actual = str(actual).strip().lower()
        expected = str(expected).strip().lower()
        
        # 完全匹配
        if actual == expected:
            return True
        
        # Yes/No 答案
        if expected in ['yes', 'no', 'true', 'false']:
            actual_bool = actual in ['yes', 'true', '1'] or (actual not in ['no', 'false', '0', 'null', ''] and actual != '0')
            expected_bool = expected in ['yes', 'true']
            return actual_bool == expected_bool
        
        # 数字答案
        if expected.isdigit():
            try:
                return int(float(actual)) == int(expected)
            except:
                return False
        
        # 状态等价 (parked/stopped, with_rider/with rider)
        if question_type == 'status':
            actual_norm = actual.replace('_', ' ')
            expected_norm = expected.replace('_', ' ')
            if actual_norm == expected_norm:
                return True
            # parked 和 stopped 等价
            if {actual_norm, expected_norm} <= {'parked', 'stopped'}:
                return True
        
        return False

    def process_batch(self, questions: List[str], verbose: bool = True) -> List[VQAResult]:
        """
        批量处理问题
        
        Args:
            questions: 问题列表
            verbose: 是否打印详细信息
            
        Returns:
            VQAResult列表
        """
        results = []
        
        print(f"\n{'='*60}")
        print(f"  批量处理 {len(questions)} 个问题")
        print(f"{'='*60}")
        
        for i, question in enumerate(questions, 1):
            print(f"\n[{i}/{len(questions)}] 处理问题...")
            result = self.process_question(question, verbose=verbose)
            results.append(result)
            
            if result.success:
                print(f"  ✓ 成功")
            else:
                print(f"  ✗ 失败: {result.error}")
        
        # 统计
        success_count = sum(1 for r in results if r.success)
        print(f"\n{'='*60}")
        print(f"  批量处理完成: {success_count}/{len(questions)} 成功")
        print(f"{'='*60}")
        
        return results
    
    def save_results(self, results: List[VQAResult], output_path: str) -> bool:
        """保存结果到JSON文件
        
        Args:
            results: VQAResult列表
            output_path: 输出文件路径
            
        Returns:
            True if save successful
        """
        try:
            import os
            # Ensure output directory exists
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            data = [r.to_dict() for r in results]
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✓ 结果已保存: {output_path}")
            logger.info(f"Results saved to {output_path}")
            return True
        except (IOError, OSError) as e:
            logger.error(f"Failed to save results: {e}")
            print(f"✗ 保存失败: {e}")
            return False
    
    def close(self) -> None:
        """关闭连接"""
        if self.neo4j:
            self.neo4j.close()
        self._initialized = False
        logger.debug("VQA Pipeline closed")


# ============ 示例VQA问题 ============
SAMPLE_QUESTIONS = [
    # 基础计数问题
    "场景中有多少辆车？",
    "场景中有多少个行人？",
    "总共有多少个对象？",
    
    # 空间关系问题
    "ego车前方有哪些对象？",
    "car1左侧有哪些车辆？",
    "离ego最近的行人是谁？距离多远？",
    
    # 属性查询问题
    "哪个车辆距离ego最远？",
    "有多少个对象在ego的10米范围内？",
    "car1和car2之间的距离是多少？",
    
    # 复杂查询问题
    "ego前方最近的车辆是哪个？它距离ego多远？",
    "有多少个行人在ego的前方且距离小于20米？",
]


def run_demo():
    """运行演示"""
    print("\n" + "="*60)
    print("  NuScenes VQA Pipeline 演示")
    print("="*60)
    
    # 使用上下文管理器确保资源正确释放
    with VQAPipeline() as pipeline:
        # 处理示例问题
        results = pipeline.process_batch(SAMPLE_QUESTIONS[:3], verbose=True)
        
        # 保存结果
        import os
        output_dir = os.path.join(os.path.dirname(__file__), "..", "output", "vqa_results")
        output_path = os.path.join(output_dir, "demo_results.json")
        pipeline.save_results(results, output_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_demo()
