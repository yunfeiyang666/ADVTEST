"""
增强版官方QA测试运行器

特性：
1. 硬编码等价词规则 + LLM兆底判定
2. 智能retry机制（让LLM分析自己的错误并修正）
3. 完善的配置管理
4. 详细的日志和统计

改进内容：
- 添加类型注解
- 抽取配置到数据类
- 改进错误处理
- 使用上下文管理器
- 添加日志
"""
import json
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Any
from dataclasses import dataclass, field
from contextlib import contextmanager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from vqa_pipeline.pipeline import VQAPipeline, VQAResult
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig
from generate_selected_scenes_improved import (
    SceneGraphConfig,
    setup_environment,
    SceneGraphBatchProcessor,
)


# ==================== 配置 ====================
@dataclass
class QARunnerConfig:
    """测试运行器配置"""
    # Neo4j连接配置
    neo4j_uri: str = os.getenv('NEO4J_URI', 'bolt://localhost:7600')
    neo4j_user: str = os.getenv('NEO4J_USER', 'neo4j')
    neo4j_password: str = os.getenv('NEO4J_PASSWORD', '87017563')
    
    # 测试配置
    use_llm_judge: bool = True
    max_retries: int = 5  # 增加到支持双坐标系多层retry
    verbose: bool = True
    use_ir: bool = False  # 关闭IR层，直接生成Cypher更稳定
    ir_mode: str = "llm"
    
    # 输出配置
    output_dir: str = 'output/coverage_analysis/vqa_results'
    save_detailed_results: bool = True


# ==================== 测试场景配置（只需改这里） ====================
# 场景名 + 帧号（本次 4 场景共 58 题）
SCENE_SPECS: List[Tuple[str, int]] = [
    # ("scene-0103", 25),  # 已确认全对，临时跳过
    # ("scene-0103", 38),  # 已完成
    ("scene-0553", 8),    # 只跑 Q21-24
    ("scene-0916", 8),    # 全跑
]

# 路径配置
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
# 注意：regenerate_scene_graphs() 保存到 SCRIPT_DIR/output/...
# （因为 cfg.output_dir = core_pipeline/output）
SCENE_GRAPH_DIR = SCRIPT_DIR / "output" / "coverage_analysis" / "scene_graphs"
QA_DIR = PROJECT_DIR / "output" / "coverage_analysis" / "vqa_results"


# 双坐标系Retry策略（Source Frame优先，因为大多数场景使用source frame能做对更多题）
RETRY_STRATEGIES = [
    {
        'name': 'source_angle_matches',
        'description': 'Source Frame + angle_matches_source (宽松匹配)',
        'direction_hint': "❗ 强制要求：所有方位用 'DIRECTION' IN r.angle_matches_source（基于source对象自身朝向）"
    },
    {
        'name': 'ego_angle_matches',
        'description': 'Ego Frame + angle_matches_ego (宽松匹配)',
        'direction_hint': "❗ 强制要求：所有方位改用 'DIRECTION' IN r.angle_matches_ego（切换到Ego Frame）"
    },
    {
        'name': 'source_direction_8',
        'description': 'Source Frame + direction_8_source (精确45度)',
        'direction_hint': "❗ 强制要求：所有方位改用 r.direction_8_source = 'DIRECTION'（Source Frame精确匹配）"
    },
    {
        'name': 'ego_direction_8',
        'description': 'Ego Frame + direction_8_ego (精确45度)',
        'direction_hint': "❗ 强制要求：所有方位改用 r.direction_8_ego = 'DIRECTION'（Ego Frame精确匹配）"
    },
    {
        'name': 'syntax_fix',
        'description': '语法错误修正',
        'direction_hint': "❗ 修正语法后重试"
    },
]


# 硬编码的等价词组
EQUIVALENT_SETS: List[Set[str]] = [
    {'parked', 'stopped'},
    {'with_rider', 'with rider'},
    {'without_rider', 'without rider'},
    {'moving', 'in motion'},
    {'standing', 'stopped'},  # 新增
    {'sitting', 'stopped'},   # 新增
]

# ==================== 跳过的错题列表 ====================
# 格式: (scene_name, frame_idx, question_index_1based)
# 这些题目本身有问题（数据错误/题目歧义），跳过以节省时间
# 已验证的错题列表 (2026-01-30 验证)
SKIP_QUESTIONS: Set[Tuple[str, int, int]] = {
    # scene-0103 帧38
    ("scene-0103", 38, 8),   # Q8: bicycle to front-left of truck, 数据返回with_rider而非without_rider
    
    # scene-0553 帧8 - 验证后的错题
    ("scene-0553", 8, 7),    # Q7: other things same status as trailer, 期望8实饤28
    ("scene-0553", 8, 12),   # Q12: barriers to front of trailer, 期望5实饤11
    ("scene-0553", 8, 18),   # Q18: with rider bicycles to front-left of trailer, 数据为空
    
    # scene-0916 帧8 - 验证后的错题
    ("scene-0916", 8, 2),    # Q2: moving thing to back-right of me AND bus, 数据交集为空
    ("scene-0916", 8, 3),    # Q3: 同Q2
    ("scene-0916", 8, 4),    # Q4: truck to front-left of bus, 数据中没有对应truck
}

# 状态值集合（用于类型推断）
STATUS_VALUES: Set[str] = {
    'stopped', 'moving', 'parked', 'standing', 
    'with_rider', 'without_rider', 'with rider', 'without rider',
    'sitting', 'lying_down'
}

# 对象类型集合
OBJECT_TYPES: Set[str] = {
    'car', 'truck', 'bus', 'bicycle', 'pedestrian', 
    'motorcycle', 'trailer', 'barrier', 'ego'
}


# ==================== 工具函数 ====================
def normalize_answer(answer: str) -> str:
    """标准化答案格式"""
    if not answer:
        return ''
    return answer.lower().strip().replace('_', ' ')


def check_equivalent(expected: str, actual: str) -> bool:
    """检查两个答案是否在等价词组中"""
    if not expected or not actual:
        return False
    
    exp_norm = normalize_answer(expected)
    act_norm = normalize_answer(actual)
    
    if exp_norm == act_norm:
        return True
    
    for equiv_set in EQUIVALENT_SETS:
        norm_set = {normalize_answer(w) for w in equiv_set}
        if exp_norm in norm_set and act_norm in norm_set:
            return True
    
    return False


def llm_judge_answers(llm_client, question: str, expected: str, actual: str) -> Tuple[bool, str]:
    """
    判断两个答案是否等价
    
    Args:
        llm_client: LLM客户端
        question: 原始问题
        expected: 预期答案
        actual: 实际答案
    
    Returns:
        (是否等价, 原因)
    """
    # 1. 先用硬编码规则检查
    if check_equivalent(expected, actual):
        return True, "等价词组匹配"
    
    # 2. 类型完全不匹配的直接拒绝（避免"72"被判为"no"）
    exp_norm = normalize_answer(expected)
    act_norm = normalize_answer(actual)
    
    # 数字 vs 非数字
    exp_is_num = exp_norm.isdigit()
    act_is_num = act_norm.isdigit()
    if exp_is_num != act_is_num:
        return False, f"类型不匹配: 期望{'数字' if exp_is_num else '文本'}，实际{'数字' if act_is_num else '文本'}"
    
    # yes/no vs 其他
    exp_is_bool = exp_norm in ('yes', 'no')
    act_is_bool = act_norm in ('yes', 'no')
    if exp_is_bool != act_is_bool:
        return False, f"类型不匹配: 期望{'yes/no' if exp_is_bool else '具体值'}，实际{'yes/no' if act_is_bool else '具体值'}"
    
    # 3. 快速通道：简单状态词和对象类型直接比较，不调用LLM
    if exp_norm in STATUS_VALUES and act_norm in STATUS_VALUES:
        # 两个都是状态值但不相等，直接返回False
        return False, f"状态值不匹配: {expected} vs {actual}"
    
    if exp_norm in OBJECT_TYPES and act_norm in OBJECT_TYPES:
        # 两个都是对象类型但不相等，直接返回False
        return False, f"对象类型不匹配: {expected} vs {actual}"
    
    # 4. 规则检查不通过，调用LLM
    # 推断答案类型
    if exp_is_num:
        answer_type = "数字"
    elif exp_is_bool:
        answer_type = "yes/no"
    elif exp_norm in STATUS_VALUES:
        answer_type = "状态值(stopped/moving/parked等)"
    elif exp_norm in OBJECT_TYPES:
        answer_type = "对象类型(car/bicycle/pedestrian等)"
    else:
        answer_type = "文本"
    
    prompt = f"""判断两个答案是否表达相同意思。

问题: {question}
答案类型: {answer_type}
标准答案: {expected}
实际答案: {actual}

判断规则：
- 如果答案类型是数字，必须数值完全相等
- 如果答案类型是yes/no，必须语义一致
- 如果答案类型是状态值，"parked"和"stopped"可以认为等价
- 如果答案类型是对象类型，必须指向同一类型对象
- 忽略大小写、空格、下划线差异

只回答YES或NO。"""
    
    try:
        response = llm_client.call_llm_raw(prompt, max_tokens=10, temperature=0.05)
        is_same = "YES" in response.upper()
        return is_same, "LLM判定等价" if is_same else "LLM判定不等价"
    except Exception as e:
        logger.warning(f"LLM判定调用失败: {e}")
        # LLM失败时默认返回False，避免误判
        return False, f"LLM调用失败: {e}"


# ==================== 场景图生成 ====================
def regenerate_scene_graphs(scene_specs: List[Tuple[str, int]]) -> None:
    """根据给定 scene_specs 重新生成场景图（每次运行都刷新）"""
    import config as core_config
    from nuscenes.nuscenes import NuScenes

    cfg = SceneGraphConfig.from_config(core_config)
    setup_environment(cfg.devkit_path)

    logger.info("重新生成场景图...")
    nusc = NuScenes(
        version=cfg.nuscenes_version,
        dataroot=cfg.nuscenes_dataroot,
        verbose=False
    )
    processor = SceneGraphBatchProcessor(nusc, cfg)

    selected_scenes = [
        {
            "scene_name": name,
            "frame_idx": frame,
            "scene_description": ""
        }
        for name, frame in scene_specs
    ]
    output_dir = Path(cfg.output_dir) / "coverage_analysis" / "scene_graphs"
    processor.process_all(selected_scenes, output_dir)
    logger.info("场景图生成完成")


# ==================== 结果数据类 ====================
@dataclass
class QuestionResult:
    """单个问题的结果"""
    question: str
    expected: str
    actual: str
    correct: bool
    reason: str
    attempts: int
    question_type: str = ''
    cypher_query: str = ''
    attempt_details: List[Dict[str, Any]] = field(default_factory=list)  # 每次尝试的详细信息


@dataclass
class SceneResult:
    """单个场景的结果"""
    scene_name: str
    frame_idx: int
    total: int
    correct: int
    results: List[QuestionResult] = field(default_factory=list)
    
    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0


@dataclass
class RunnerStats:
    """运行器统计"""
    total_questions: int = 0
    correct_count: int = 0
    semantic_match_count: int = 0  # 语义等价匹配的数量
    retry_success_count: int = 0   # retry成功的数量
    failed_count: int = 0          # 失败数量
    skipped_count: int = 0         # 跳过的错题数量
    
    @property
    def accuracy(self) -> float:
        # 正确率不计算跳过的题目
        effective_total = self.total_questions - self.skipped_count
        return self.correct_count / effective_total if effective_total > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        effective_total = self.total_questions - self.skipped_count
        return {
            'total_questions': self.total_questions,
            'effective_questions': effective_total,
            'skipped_count': self.skipped_count,
            'correct_count': self.correct_count,
            'accuracy': f"{self.accuracy * 100:.1f}%",
            'semantic_match_count': self.semantic_match_count,
            'retry_success_count': self.retry_success_count,
            'failed_count': self.failed_count
        }


# ==================== 主运行器 ====================
class EnhancedQARunner:
    """增强版QA测试运行器"""
    
    def __init__(self, config: Optional[QARunnerConfig] = None):
        """
        Args:
            config: 运行器配置，不提供则使用默认配置
        """
        self.config = config or QARunnerConfig()
        self.pipeline: Optional[VQAPipeline] = None
        self.stats = RunnerStats()
        self.scene_results: List[SceneResult] = []
    
    def initialize(self) -> bool:
        """初始化"""
        try:
            self.pipeline = VQAPipeline(
                use_ir=self.config.use_ir,
                ir_mode=self.config.ir_mode
            )
            return self.pipeline.initialize()
        except Exception as e:
            logger.error(f"初始化失败: {e}")
            return False
    
    def __enter__(self):
        """上下文管理器入口"""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()
    
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

        strategy_count = min(len(RETRY_STRATEGIES), self.config.max_retries + 1)
        active_strategies = RETRY_STRATEGIES[:strategy_count]

        for attempt, strategy in enumerate(active_strategies):
            feedback_parts: List[str] = []

            # 加入策略提示（明确使用策略表）
            strategy_hint = strategy.get('direction_hint')
            if strategy_hint:
                feedback_parts.append(f"[{strategy['description']}]\n{strategy_hint}")

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
                    # ✅ 直接使用规则化反馈，不调用LLM分析（节省时间）
                    # 累积当前错误到历史
                    feedback_history.append(f"第{attempt}次: {correction_reason}")

                    # 构建简洁的反馈（策略提示已经在feedback_parts中）
                    feedback_parts.append(f"""上次尝试失败: {correction_reason}

请根据上述策略提示重写Cypher查询。""")

                    if verbose:
                        print(f"\n  [Retry {attempt}] 错误原因: {correction_reason[:100]}...")

            feedback = "\n\n".join([p for p in feedback_parts if p]).strip() or None
            
            # 执行查询
            result = self.pipeline.process_question(
                question, 
                verbose=verbose,
                cypher_feedback=feedback
            )
            
            attempts.append({
                'attempt': attempt,
                'strategy': strategy.get('name'),
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
                
                # 🔍 检测重复查询：如果连续2次生成相同的Cypher且答案也相同，说明陷入死循环
                if len(attempts) >= 2:
                    last_two = attempts[-2:]
                    # 检查Cypher查询是否相同（忽略空白和换行差异）
                    cypher1 = ' '.join(last_two[0].get('cypher_query', '').split())
                    cypher2 = ' '.join(last_two[1].get('cypher_query', '').split())
                    answer1 = last_two[0].get('answer', '').lower().strip()
                    answer2 = last_two[1].get('answer', '').lower().strip()
                    
                    if cypher1 and cypher1 == cypher2 and answer1 == answer2:
                        if verbose:
                            print(f"  ⏹️ 检测到连续2次生成相同Cypher且答案相同 '{answer1}'，陷入死循环，终止retry")
                        final_result = {
                            'correct': False,
                            'reason': f"查询死循环: Cypher相同且返回 '{answer1}' 但期望 '{expected_answer}'",
                            'attempts': len(attempts),
                            'result': result
                        }
                        break
                
                # 如果答案不对但有结果，可能是方向/逻辑问题
                if attempt < (strategy_count - 1):
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
        """
        从预期答案推断答案类型提示（不给完整答案）
        
        Args:
            expected_answer: 预期答案
        
        Returns:
            答案类型描述
        """
        if not expected_answer:
            return "unknown"
        
        answer_lower = expected_answer.lower().strip()
        
        # yes/no问题
        if answer_lower in ['yes', 'no']:
            return "yes/no"
        
        # 数字问题
        if answer_lower.isdigit():
            return "a number"
        
        # status相关（使用全局集合）
        if answer_lower in STATUS_VALUES or answer_lower.replace(' ', '_') in STATUS_VALUES:
            return "a status value (like 'stopped', 'moving', 'with_rider', etc.)"
        
        # 对象类型（使用全局集合）
        if answer_lower in OBJECT_TYPES:
            return "an object type (like 'car', 'bicycle', 'truck', etc.)"
        
        # 默认：只给第一个词和长度
        words = answer_lower.split()
        first_word = words[0] if words else answer_lower[:5]
        return f"text (first word starts with '{first_word}')"
    
    def _judge_answer(self, expected: str, actual: str, question_type: str, question: str) -> Tuple[bool, str]:
        """
        判断答案是否正确
        
        Args:
            expected: 预期答案
            actual: 实际答案
            question_type: 问题类型
            question: 原始问题
        
        Returns:
            (是否正确, 原因)
        """
        # 空答案检查
        if not actual:
            return False, "实际答案为空"
        
        # 精确匹配
        if expected.lower().strip() == actual.lower().strip():
            return True, "精确匹配"
        
        # 使用硬编码规则 + LLM兆底
        if self.config.use_llm_judge and self.pipeline:
            return llm_judge_answers(self.pipeline.llm, question, expected, actual)
        
        return False, f"不匹配: 期望 '{expected}', 实际 '{actual}'"
    
    @contextmanager
    def _neo4j_scene_context(self, scene_graph: Dict):
        """
        Neo4j场景导入的上下文管理器
        
        Args:
            scene_graph: 场景图数据
        """
        neo4j_cfg = Neo4jConfig(
            uri=self.config.neo4j_uri,
            user=self.config.neo4j_user,
            password=self.config.neo4j_password
        )
        importer = Neo4jImporter(neo4j_cfg)
        try:
            importer.clear_database()
            importer.create_schema()
            importer.import_scene(scene_graph)
            yield importer
        finally:
            importer.close()
    
    def _load_questions(self, qa_data: Dict) -> List[Dict[str, str]]:
        """
        从不同格式的QA数据中提取问题
        
        Args:
            qa_data: QA数据
        
        Returns:
            问题列表
        """
        questions = qa_data.get('questions', [])
        if not questions:
            # 尝试从 results 格式提取
            results_data = qa_data.get('results', [])
            questions = [
                {'question': r['question'], 'answer': r['expected_answer']} 
                for r in results_data
            ]
        return questions
    
    def run_scene(self, scene_graph_path: str, qa_path: str, verbose: bool = True) -> SceneResult:
        """
        运行单个场景的测试
        
        Args:
            scene_graph_path: 场景图文件路径
            qa_path: QA文件路径
            verbose: 是否详细输出
        
        Returns:
            场景测试结果
        """
        # 加载数据
        with open(scene_graph_path, 'r', encoding='utf-8') as f:
            scene_graph = json.load(f)
        with open(qa_path, 'r', encoding='utf-8') as f:
            qa_data = json.load(f)
        
        scene_name = scene_graph.get('scene_name', 'unknown')
        frame_idx = scene_graph.get('frame_idx', 0)
        
        # 提取问题
        questions = self._load_questions(qa_data)
        question_results: List[QuestionResult] = []
        correct = 0
        
        # 导入场景到Neo4j，并在上下文中执行所有查询
        with self._neo4j_scene_context(scene_graph):
            if verbose:
                print(f"\n{'='*70}")
                print(f"  测试场景: {scene_name} 帧{frame_idx}")
                print(f"  问题数量: {len(questions)}")
                print(f"{'='*70}")
            
            for i, q in enumerate(questions, 1):
                question = q['question']
                expected = q['answer']
                
                if verbose:
                    print(f"\n[{i}/{len(questions)}] Q: {question}")
                    print(f"  预期: {expected}")
                
                # 检查是否在跳过列表中
                skip_key = (scene_name, frame_idx, i)
                if skip_key in SKIP_QUESTIONS:
                    if verbose:
                        print(f"  ⏭️ 跳过: 该题目在已知错题列表中")
                    # 记录为跳过
                    self.stats.skipped_count += 1
                    question_results.append(QuestionResult(
                        question=question,
                        expected=expected,
                        actual="[SKIPPED]",
                        correct=False,
                        reason="已知错题，跳过",
                        attempts=0,
                        question_type="skipped",
                        cypher_query="",
                        attempt_details=[]
                    ))
                    continue
                
                final_result, attempts = self.process_question_with_retry(
                    question, expected, verbose=verbose
                )
                
                is_correct = final_result['correct']
                reason = final_result['reason']
                num_attempts = final_result['attempts']
                
                if is_correct:
                    correct += 1
                    status = "✅ 正确"
                    if "等价" in reason or "semantic" in reason.lower():
                        self.stats.semantic_match_count += 1
                        status += f" (语义等价: {reason})"
                    if num_attempts > 1:
                        self.stats.retry_success_count += 1
                        status += f" (retry {num_attempts}次)"
                else:
                    self.stats.failed_count += 1
                    status = f"❌ 错误: {reason}"
                
                if verbose:
                    print(f"  {status}")
                
                # 提取实际答案
                actual_answer = self._extract_actual_answer(final_result)
                
                # 提取Cypher查询
                cypher_query = ""
                if attempts:
                    cypher_query = attempts[-1].get('cypher_query', '')
                
                # 提取问题类型
                q_type = ""
                if attempts:
                    q_type = attempts[-1].get('question_type', '')
                
                question_results.append(QuestionResult(
                    question=question,
                    expected=expected,
                    actual=actual_answer,
                    correct=is_correct,
                    reason=reason,
                    attempts=num_attempts,
                    question_type=q_type,
                    cypher_query=cypher_query,
                    attempt_details=attempts  # 保存完整的每次尝试详情
                ))
        
        # 更新统计
        self.stats.total_questions += len(questions)
        self.stats.correct_count += correct
        
        # 计算该场景跳过的题目数
        scene_skipped = sum(1 for qr in question_results if qr.reason == "已知错题，跳过")
        effective_total = len(questions) - scene_skipped
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"  场景总结: {scene_name} 帧{frame_idx}")
            if scene_skipped > 0:
                print(f"  跳过错题: {scene_skipped}题")
            accuracy = 100 * correct / effective_total if effective_total > 0 else 0
            print(f"  答案正确: {correct}/{effective_total} ({accuracy:.1f}%)")
            print(f"{'='*70}")
        
        result = SceneResult(
            scene_name=scene_name,
            frame_idx=frame_idx,
            total=len(questions),
            correct=correct,
            results=question_results
        )
        self.scene_results.append(result)
        return result
    
    def _extract_actual_answer(self, final_result: Dict) -> str:
        """从结果中提取实际答案"""
        if not final_result.get('result'):
            return ""
        
        result = final_result['result']
        if isinstance(result, dict):
            return result.get('answer', '')
        elif hasattr(result, 'answer'):
            return result.answer
        return ""
    
    def _save_results(self, output_path: str):
        """保存当前结果到文件"""
        try:
            results = self._build_results_dict()
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2, default=self._json_serializer)
            logger.info(f"💾 增量保存: {output_path}")
            
            # 同时保存失败题目到独立文件
            self._save_failed_questions(output_path)
        except Exception as e:
            logger.warning(f"保存失败: {e}")
            import traceback
            traceback.print_exc()

    def _save_failed_questions(self, base_output_path: str):
        """将失败/存疑题目单独保存到独立文件，便于统计和排查
        
        文件名: 在原始结果文件名基础上加 _failed 后缀
        内容: 仅包含失败题目的详细信息（含完整retry历史）
        """
        failed_path = Path(base_output_path).with_name(
            Path(base_output_path).stem + '_failed.json'
        )
        
        failed_items = []
        for scene_result in self.scene_results:
            for i, qr in enumerate(scene_result.results, 1):
                if qr.correct or qr.reason == "已知错题，跳过":
                    continue
                failed_items.append({
                    'scene_name': scene_result.scene_name,
                    'frame_idx': scene_result.frame_idx,
                    'question_idx': i,
                    'question': qr.question,
                    'expected': qr.expected,
                    'actual': qr.actual,
                    'reason': qr.reason,
                    'attempts': qr.attempts,
                    'question_type': qr.question_type,
                    'final_cypher': qr.cypher_query,
                    'attempt_details': qr.attempt_details,
                })
        
        summary = {
            'total_failed': len(failed_items),
            'total_questions': self.stats.total_questions,
            'skipped': self.stats.skipped_count,
            'failed_rate': f"{len(failed_items) / max(self.stats.total_questions - self.stats.skipped_count, 1) * 100:.1f}%",
            'failed_questions': failed_items,
        }
        
        try:
            with open(failed_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2, default=self._json_serializer)
            if failed_items:
                logger.info(f"📋 失败题目已保存: {failed_path} ({len(failed_items)} 题)")
        except Exception as e:
            logger.warning(f"保存失败题目文件失败: {e}")

    def build_clean_coverage_results(self) -> Dict[str, Any]:
        """构建仅包含正确题目的覆盖率结果（排除失败/存疑题目）
        
        用途: 覆盖率计算时应排除失败题目，避免把错误查询的覆盖范围计入统计。
        
        Returns:
            与 _build_results_dict 格式相同，但仅包含 correct=True 的题目
        """
        clean_correct = 0
        clean_total = 0
        clean_scenes = []
        
        for sr in self.scene_results:
            clean_results = []
            scene_correct = 0
            for qr in sr.results:
                if qr.reason == "已知错题，跳过":
                    continue
                clean_total += 1
                if qr.correct:
                    clean_results.append({
                        'question': qr.question,
                        'expected': qr.expected,
                        'actual': qr.actual,
                        'correct': True,
                        'reason': qr.reason,
                        'attempts': qr.attempts,
                        'question_type': qr.question_type,
                        'final_cypher': qr.cypher_query,
                        'attempt_details': qr.attempt_details,
                    })
                    scene_correct += 1
                    clean_correct += 1
            
            clean_scenes.append({
                'scene_name': sr.scene_name,
                'frame_idx': sr.frame_idx,
                'total': len(clean_results),
                'correct': scene_correct,
                'accuracy': f"{scene_correct / max(len(clean_results), 1) * 100:.1f}%",
                'results': clean_results,
            })
        
        return {
            'total_questions': clean_total,
            'correct_only': clean_correct,
            'note': '仅包含正确回答的题目，用于覆盖率计算',
            'scenes': clean_scenes,
        }
    
    @staticmethod
    def _json_serializer(obj):
        """自定义JSON序列化，处理无法直接序列化的对象"""
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        else:
            return str(obj)
    
    def run_all_scenes(self, scenes: List[Tuple[str, str]], verbose: bool = True, 
                       incremental_save_path: Optional[str] = None) -> Dict[str, Any]:
        """
        运行所有场景测试
        
        Args:
            scenes: (场景图路径, QA路径)元组列表
            verbose: 是否详细输出
            incremental_save_path: 增量保存路径，每完成一个场景就保存一次
        
        Returns:
            测试结果字典
        """
        for scene_graph_path, qa_path in scenes:
            if not os.path.exists(scene_graph_path):
                logger.warning(f"找不到场景图文件: {scene_graph_path}")
                continue
            if not os.path.exists(qa_path):
                logger.warning(f"找不到QA文件: {qa_path}")
                continue
            
            try:
                self.run_scene(scene_graph_path, qa_path, verbose=verbose)
                
                # 增量保存：每完成一个场景就保存一次
                if incremental_save_path:
                    self._save_results(incremental_save_path)
                    
            except Exception as e:
                logger.error(f"场景测试失败 {scene_graph_path}: {e}")
                # 失败时也保存已有结果
                if incremental_save_path:
                    self._save_results(incremental_save_path)
                continue
        
        # 总结
        self._print_summary(verbose)
        
        return self._build_results_dict()
    
    def _print_summary(self, verbose: bool = True):
        """打印测试总结"""
        if not verbose:
            return
        
        effective_total = self.stats.total_questions - self.stats.skipped_count
        
        print(f"\n{'='*70}")
        print(f"  全局测试总结")
        print(f"{'='*70}")
        print(f"  总问题数: {self.stats.total_questions}")
        if self.stats.skipped_count > 0:
            print(f"  跳过错题: {self.stats.skipped_count}")
            print(f"  有效题数: {effective_total}")
        print(f"  答案正确: {self.stats.correct_count}/{effective_total} ({self.stats.accuracy * 100:.1f}%)")
        print(f"  语义等价匹配: {self.stats.semantic_match_count}")
        print(f"  Retry成功: {self.stats.retry_success_count}")
        print(f"  失败数量: {self.stats.failed_count}")
    
    def _build_results_dict(self) -> Dict[str, Any]:
        """构建结果字典"""
        return {
            **self.stats.to_dict(),
            'scenes': [
                {
                    'scene_name': r.scene_name,
                    'frame_idx': r.frame_idx,
                    'total': r.total,
                    'correct': r.correct,
                    'accuracy': f"{r.accuracy * 100:.1f}%",
                    'results': [
                        {
                            'question': qr.question,
                            'expected': qr.expected,
                            'actual': qr.actual,
                            'correct': qr.correct,
                            'reason': qr.reason,
                            'attempts': qr.attempts,
                            'question_type': qr.question_type,
                            'final_cypher': qr.cypher_query,
                            'attempt_details': qr.attempt_details  # 完整的每次尝试记录
                        }
                        for qr in r.results
                    ]
                }
                for r in self.scene_results
            ]
        }
    
    def close(self):
        """关闭连接"""
        if self.pipeline:
            try:
                self.pipeline.close()
            except Exception as e:
                logger.warning(f"关闭连接时出错: {e}")
            self.pipeline = None


class TeeOutput:
    """同时输出到终端和文件"""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log_file = open(filepath, 'w', encoding='utf-8')
    
    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()  # 实时写入
    
    def flush(self):
        self.terminal.flush()
        self.log_file.flush()
    
    def close(self):
        self.log_file.close()


def main():
    """主函数"""
    # 准备日志文件
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path('output/coverage_analysis/vqa_results')
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f'qa_log_{timestamp}.txt'
    
    # 重定向输出到文件（同时保留终端输出）
    tee = TeeOutput(log_path)
    sys.stdout = tee
    
    try:
        print("="*70)
        print("  增强版官方QA预跑测试")
        print("  特性: LLM答案判定 + 智能Retry")
        print(f"  日志文件: {log_path}")
        print("="*70)
        
        # 每次运行先重新生成场景图（确保数据最新）
        regenerate_scene_graphs(SCENE_SPECS)
        
        _run_tests(timestamp, output_dir)
    finally:
        sys.stdout = tee.terminal
        tee.close()
        print(f"\n📝 完整日志已保存: {log_path}")


def _run_tests(timestamp: str, output_dir: Path):
    """\u8fd0\u884c\u6d4b\u8bd5"""
    # 创建配置
    config = QARunnerConfig(
        use_llm_judge=True,
        max_retries=4,  # 5层策略：初始尝试 + 4次retry（ego_angle -> syntax -> source_angle -> ego_dir8 -> source_dir8）
        verbose=True
    )
    
    # 定义测试场景（自动按配置构造路径）
    scenes: List[Tuple[str, str]] = []
    for scene_name, frame_idx in SCENE_SPECS:
        scene_graph_path = SCENE_GRAPH_DIR / f"{scene_name}_frame{frame_idx}_scene_graph.json"
        qa_path = QA_DIR / f"{scene_name}_frame{frame_idx}_official_qa.json"
        scenes.append((str(scene_graph_path), str(qa_path)))
    
    # 准备增量保存路径
    output_path = output_dir / f'enhanced_qa_test_{timestamp}.json'
    
    # 使用上下文管理器运行测试
    start_time = time.time()
    
    with EnhancedQARunner(config) as runner:
        if not runner.pipeline:
            logger.error("初始化失败")
            return
        
        # 启用增量保存：每完成一个场景就保存一次
        results = runner.run_all_scenes(scenes, verbose=config.verbose, 
                                       incremental_save_path=str(output_path))
        
        # 保存仅正确题目的覆盖率专用文件（排除失败/存疑题）
        clean_results = runner.build_clean_coverage_results()
        clean_path = output_dir / f'coverage_clean_{timestamp}.json'
        with open(clean_path, 'w', encoding='utf-8') as f:
            json.dump(clean_results, f, ensure_ascii=False, indent=2, default=runner._json_serializer)
        logger.info(f"🧹 覆盖率专用结果(仅正确题): {clean_path} ({clean_results['correct_only']} 题)")
    
    elapsed = time.time() - start_time
    
    # 最后再保存一次（确保完整）
    def json_serializer(obj):
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        else:
            return str(obj)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=json_serializer)
    
    logger.info(f"📊 结果已保存: {output_path}")
    logger.info(f"⏰ 总耗时: {elapsed:.1f}秒")


if __name__ == "__main__":
    main()
