"""
覆盖率驱动的问题生成闭环控制器

核心流程:
1. 计算当前覆盖率 (CoveragePipeline)
2. 识别覆盖率缺口
3. 生成针对性问题 (QAGenerator)
4. 验证问题正确性 (VQAPipeline)
5. 更新覆盖率统计
6. 循环直到达到目标覆盖率
"""

import json
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from .unified_coverage import UnifiedCoverageStats, CoverageAdapter
from .gap_analyzer import GapAnalyzer, print_gap_analysis

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class LoopConfig:
    """闭环配置"""
    target_l0_coverage: float = 0.80  # L0目标覆盖率
    target_l1_coverage: float = 0.50  # L1目标覆盖率
    max_iterations: int = 10          # 最大迭代次数
    questions_per_iteration: int = 20 # 每次迭代生成的问题数
    min_coverage_gain: float = 0.02   # 最小覆盖率增益，低于此值停止
    verify_answers: bool = True       # 是否验证答案
    save_intermediate: bool = True    # 是否保存中间结果
    
    # 覆盖率数据路径
    coverage_data_dir: str = None     # 覆盖率数据目录，默认为output/coverage_final_fixed


class CoverageLoopController:
    """
    覆盖率驱动的问题生成闭环控制器
    
    协调三个Pipeline:
    - coverage_evaluation: 计算覆盖率
    - qa_generator_v2: 生成问题
    - vqa_pipeline: 验证答案
    """
    
    def __init__(self, config: LoopConfig = None):
        self.config = config or LoopConfig()
        self.stats = None
        self.scene_data = None
        self.all_generated_qa = []
        self.iteration_history = []
        
        # 延迟导入，避免循环依赖
        self._coverage_pipeline = None
        self._qa_generator = None
        self._vqa_pipeline = None
        self._gap_analyzer = None
    
    def _init_coverage_pipeline(self):
        """初始化覆盖率计算Pipeline"""
        if self._coverage_pipeline is None:
            try:
                from coverage_evaluation.coverage_pipeline import CoveragePipeline, Neo4jClient
                self._coverage_pipeline_class = CoveragePipeline
                self._neo4j_client_class = Neo4jClient
                logger.info("✓ 覆盖率Pipeline已加载")
            except ImportError as e:
                logger.warning(f"覆盖率Pipeline加载失败: {e}")
                self._coverage_pipeline_class = None
    
    def _init_qa_generator(self):
        """初始化问题生成器 (模板驱动，无需LLM)"""
        if self._qa_generator is None:
            try:
                from qa_generator_v2.coverage_driven_template_generator import (
                    CoverageDrivenTemplateGenerator, CoverageGoal
                )
                if self.scene_data:
                    self._qa_generator = CoverageDrivenTemplateGenerator(
                        self.scene_data, seed=42)
                    logger.info("✓ QA生成器已加载 (模板驱动，无需LLM)")
                else:
                    logger.warning("场景数据未加载，无法初始化QA生成器")
            except ImportError as e:
                logger.warning(f"QA生成器加载失败: {e}")
                self._qa_generator = None
            except Exception as e:
                logger.warning(f"QA生成器初始化失败: {e}")
                self._qa_generator = None
    
    def _init_vqa_pipeline(self):
        """初始化VQA验证Pipeline"""
        if self._vqa_pipeline is None:
            try:
                from vqa_pipeline.pipeline import VQAPipeline
                self._vqa_pipeline = VQAPipeline()
                logger.info("✓ VQA Pipeline已加载")
            except ImportError as e:
                logger.warning(f"VQA Pipeline加载失败: {e}")
                self._vqa_pipeline = None
    
    def run(self, 
            scene_graph_path: str,
            output_dir: str,
            initial_coverage_path: str = None) -> Dict:
        """
        运行完整的闭环流程
        
        Args:
            scene_graph_path: 场景图JSON文件路径
            output_dir: 输出目录
            initial_coverage_path: 初始覆盖率JSON文件路径（NuScenesQA覆盖率分析结果）
                                   如果不提供，会自动从coverage_data_dir查找
        
        Returns:
            最终结果字典
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        logger.info("=" * 70)
        logger.info("  覆盖率驱动问题生成闭环 - 启动")
        logger.info("=" * 70)
        logger.info(f"场景图: {scene_graph_path}")
        logger.info(f"输出目录: {output_dir}")
        logger.info(f"目标覆盖率: L0={self.config.target_l0_coverage:.0%}, L1={self.config.target_l1_coverage:.0%}")
        logger.info(f"最大迭代: {self.config.max_iterations}")
        
        # 1. 加载场景图
        logger.info("\n" + "=" * 70)
        logger.info("  步骤1: 加载场景图")
        logger.info("=" * 70)
        
        self.scene_data = self._load_scene_graph(scene_graph_path)
        if not self.scene_data:
            logger.error("场景图加载失败")
            return {'success': False, 'error': '场景图加载失败'}
        
        scene_name = self.scene_data.get('scene_name', 'unknown')
        frame_idx = self.scene_data.get('frame_idx', 0)
        nodes = self.scene_data.get('nodes', [])
        edges = self.scene_data.get('edges', [])
        
        logger.info(f"场景: {scene_name} 帧{frame_idx}")
        logger.info(f"节点: {len(nodes)}, 边: {len(edges)}")
        
        # 2. 加载初始覆盖率（从NuScenesQA分析结果）
        logger.info("\n" + "=" * 70)
        logger.info("  步骤2: 加载初始覆盖率（NuScenesQA）")
        logger.info("=" * 70)
        
        self.stats = self._load_initial_coverage(initial_coverage_path, scene_name, frame_idx)
        self._print_coverage_summary("初始(NuScenesQA)")
        
        # 初始化缺口分析器
        self._gap_analyzer = GapAnalyzer(self.scene_data)
        
        # 3. 主循环
        logger.info("\n" + "=" * 70)
        logger.info("  步骤3: 开始迭代生成")
        logger.info("=" * 70)
        
        for iteration in range(1, self.config.max_iterations + 1):
            logger.info(f"\n{'─' * 60}")
            logger.info(f"  迭代 {iteration}/{self.config.max_iterations}")
            logger.info(f"{'─' * 60}")
            
            # 检查是否达标
            if self._check_coverage_target():
                logger.info("✓ 覆盖率已达标，停止迭代")
                break
            
            # 执行单次迭代
            iter_result = self._run_single_iteration(iteration, output_dir)
            self.iteration_history.append(iter_result)
            
            # 检查覆盖率增益
            if iteration > 1:
                prev_rate = self.iteration_history[-2].get('l0_rate', 0)
                curr_rate = iter_result.get('l0_rate', 0)
                gain = curr_rate - prev_rate
                
                if gain < self.config.min_coverage_gain:
                    logger.warning(f"覆盖率增益过低 ({gain:.1%} < {self.config.min_coverage_gain:.1%})，考虑停止")
                    if iteration >= 3:  # 至少运行3次
                        logger.info("停止迭代")
                        break
            
            self._print_coverage_summary(f"迭代{iteration}后")
        
        # 4. 保存最终结果
        logger.info("\n" + "=" * 70)
        logger.info("  步骤4: 保存最终结果")
        logger.info("=" * 70)
        
        final_result = self._save_final_results(output_dir, timestamp)
        
        logger.info("\n" + "=" * 70)
        logger.info("  闭环完成!")
        logger.info("=" * 70)
        logger.info(f"总迭代次数: {len(self.iteration_history)}")
        logger.info(f"总生成问题: {len(self.all_generated_qa)}")
        self._print_coverage_summary("最终")
        
        return final_result
    
    def _load_scene_graph(self, path: str) -> Optional[Dict]:
        """加载场景图"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载场景图失败: {e}")
            return None
    
    def _load_initial_coverage(self, coverage_path: str, scene_name: str, frame_idx: int) -> UnifiedCoverageStats:
        """
        从现有覆盖率数据文件加载初始状态
        
        Args:
            coverage_path: 覆盖率JSON文件路径，如果为None则自动查找
            scene_name: 场景名称
            frame_idx: 帧索引
        
        Returns:
            加载了NuScenesQA覆盖率的统计对象
        """
        stats = UnifiedCoverageStats()
        stats.scene_name = scene_name
        stats.frame_idx = frame_idx
        
        # 计算场景图的总数
        nodes = self.scene_data.get('nodes', [])
        edges = self.scene_data.get('edges', [])
        
        # L0: 节点总数（不含ego）
        non_ego_nodes = [n for n in nodes if n.get('unique_id', n.get('id', '')) != 'ego']
        stats.total_nodes = len(non_ego_nodes)
        
        # L1: 边总数 = 空间关系边 + 属性边
        # 属性边: 每个节点有若干属性（status, type等），每个属性算一条边
        ATTRIBUTE_TYPES = ['status', 'type']  # 节点属性类型
        spatial_edges = len(edges)
        attribute_edges = len(non_ego_nodes) * len(ATTRIBUTE_TYPES)
        stats.total_edges = spatial_edges + attribute_edges
        
        # L2: 两连边组合数
        # = 空间边之间的组合 + 空间边与属性边的组合
        avg_out_degree = len(edges) / max(len(nodes), 1)
        spatial_2hop = int(len(edges) * avg_out_degree)
        spatial_attr_2hop = spatial_edges * len(ATTRIBUTE_TYPES)  # 每条空间边可以连接目标节点的属性
        stats.total_2hop_paths = spatial_2hop + spatial_attr_2hop
        
        # 初始化所有节点/边覆盖计数为0
        for node in nodes:
            node_id = node.get('unique_id', node.get('id', ''))
            if node_id and node_id != 'ego':
                stats.node_coverage_count[node_id] = 0
        
        for edge in edges:
            src = edge.get('source', '')
            tgt = edge.get('target', '')
            direction = self._extract_direction(edge)
            if src and tgt:
                edge_key = f"{src}-{direction}->{tgt}"
                stats.edge_coverage_count[edge_key] = 0
        
        # 查找覆盖率数据文件
        if not coverage_path:
            coverage_path = self._find_coverage_file(scene_name, frame_idx)
        
        if coverage_path and Path(coverage_path).exists():
            logger.info(f"加载覆盖率数据: {coverage_path}")
            self._load_coverage_from_file(stats, coverage_path)
        else:
            logger.warning(f"未找到覆盖率数据文件，初始覆盖率为0")
            logger.info(f"提示: 需要先运行 coverage_pipeline 分析 NuScenesQA 问题")
        
        return stats
    
    def _find_coverage_file(self, scene_name: str, frame_idx: int) -> Optional[str]:
        """自动查找覆盖率数据文件"""
        # 默认搜索路径
        search_dirs = [
            Path(self.config.coverage_data_dir) if self.config.coverage_data_dir else None,
            Path(__file__).parent.parent.parent / "output" / "coverage_final_fixed",
            Path(__file__).parent.parent.parent / "output" / "coverage_final",
            Path(__file__).parent.parent / "coverage_evaluation" / "output",
        ]
        
        # 文件名模式
        pattern = f"coverage_{scene_name}_frame{frame_idx}_*.json"
        
        for search_dir in search_dirs:
            if search_dir and search_dir.exists():
                matches = list(search_dir.glob(pattern))
                if matches:
                    # 返回最新的文件
                    matches.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    return str(matches[0])
        
        return None
    
    def _load_coverage_from_file(self, stats: UnifiedCoverageStats, coverage_path: str):
        """从覆盖率JSON文件加载数据到stats"""
        try:
            with open(coverage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 解析coverage_pipeline的输出格式
            coverage = data.get('coverage', {})
            
            # L0: 节点覆盖
            l0 = coverage.get('L0', {})
            covered_nodes = l0.get('nodes', [])
            for node_id in covered_nodes:
                stats.covered_nodes.add(node_id)
                stats.node_coverage_count[node_id] = 1  # 至少覆盖1次
            
            # L1: 边覆盖 - 从details提取
            for detail in data.get('details', []):
                # 提取覆盖的节点
                for node_id in detail.get('covered_nodes', []):
                    stats.add_node_coverage(node_id)
                
                # 提取覆盖的边
                for edge in detail.get('covered_edges', []):
                    if isinstance(edge, list) and len(edge) >= 2:
                        node_id = edge[0]
                        edge_info = edge[1] if len(edge) > 1 else ''
                        # 边格式可能是 ['node_id', 'status:stopped'] 或 ['src', 'dir', 'tgt']
                        if ':' in str(edge_info):
                            # 属性边
                            stats.covered_edges.add((node_id, edge_info, ''))
                            stats.edge_coverage_count[f"{node_id}-{edge_info}"] = 1
                        elif len(edge) == 3:
                            # 关系边
                            src, direction, tgt = edge
                            stats.add_edge_coverage(src, direction, tgt)
                
                # 提取两跳路径
                for path in detail.get('covered_2hop_paths', []):
                    if len(path) == 3:
                        stats.add_2hop_path_coverage(path[0], path[1], path[2])
            
            # 问题统计
            questions = data.get('questions', {})
            stats.total_questions = questions.get('total', 0)
            stats.verified_questions = questions.get('analyzed', 0)
            stats.failed_questions = questions.get('failed', 0)
            
            logger.info(f"  已加载 {stats.total_questions} 个NuScenesQA问题的覆盖率")
            logger.info(f"  覆盖节点: {len(stats.covered_nodes)}/{stats.total_nodes}")
            logger.info(f"  覆盖边: {len(stats.covered_edges)}/{stats.total_edges}")
            
        except Exception as e:
            logger.error(f"加载覆盖率数据失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _extract_direction(self, edge: Dict) -> str:
        """从边提取方向"""
        # 尝试多种字段
        if 'predicates' in edge and isinstance(edge['predicates'], list):
            return edge['predicates'][0] if edge['predicates'] else ''
        if 'direction_8' in edge:
            return edge['direction_8']
        if 'direction_4' in edge:
            return edge['direction_4']
        
        metrics = edge.get('metrics', {})
        if isinstance(metrics, dict):
            ds = metrics.get('direction_source', {})
            if isinstance(ds, dict):
                return ds.get('direction_8', ds.get('direction_4', ''))
        
        return ''
    
    def _save_coverage_update(self, output_dir: Path):
        """
        保存更新后的覆盖率数据
        
        覆盖率数据存储策略:
        1. 每次迭代后更新 output_dir/coverage_current.json (当前状态)
        2. 闭环完成后保存 output_dir/coverage_final_TIMESTAMP.json (最终结果)
        3. 可选: 更新原始覆盖率文件 (追加新问题的覆盖信息)
        """
        # 保存当前覆盖率状态
        current_file = output_dir / "coverage_current.json"
        self.stats.save(str(current_file))
    
    def _append_to_question_bank(self, output_dir: Path, qa_list: List, iteration: int):
        """
        追加问题到统一题库文件
        
        题库文件: output_dir/question_bank.json
        格式: 包含所有迭代生成的问题，带场景和迭代信息
        """
        bank_file = output_dir / "question_bank.json"
        
        # 加载现有题库或创建新的
        if bank_file.exists():
            with open(bank_file, 'r', encoding='utf-8') as f:
                bank = json.load(f)
        else:
            bank = {
                'scene_name': self.stats.scene_name,
                'frame_idx': self.stats.frame_idx,
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'questions': [],
                'total_count': 0,
            }
        
        # 追加新问题
        for qa in qa_list:
            qa_dict = self._qa_to_dict(qa)
            qa_dict['iteration'] = iteration
            qa_dict['added_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            bank['questions'].append(qa_dict)
        
        bank['total_count'] = len(bank['questions'])
        bank['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 保存
        with open(bank_file, 'w', encoding='utf-8') as f:
            json.dump(bank, f, indent=2, ensure_ascii=False)
        
        logger.info(f"题库已更新: {bank_file} (共{bank['total_count']}题)")
    
    def _run_single_iteration(self, iteration: int, output_dir: Path) -> Dict:
        """运行单次迭代"""
        result = {
            'iteration': iteration,
            'generated': 0,
            'verified': 0,
            'failed': 0,
            'l0_rate': 0,
            'l1_rate': 0,
            'l2_rate': 0,
            'focus_level': '',
        }
        
        # 1. 分析覆盖率缺口，决定生成策略
        strategy = self._gap_analyzer.decide_next_generation(
            self.stats,
            target_l0=self.config.target_l0_coverage,
            target_l1=self.config.target_l1_coverage,
        )
        
        result['focus_level'] = strategy['focus_level']
        logger.info(f"缺口分析: 重点={strategy['focus_level']}, 理由={strategy['reasoning']}")
        logger.info(f"建议生成: {strategy['suggested_count']}个 {', '.join(strategy['question_types'])} 类型问题")
        
        # 2. 根据策略生成针对性问题
        generated_qa = self._generate_questions_by_strategy(strategy)
        result['generated'] = len(generated_qa)
        logger.info(f"生成问题: {len(generated_qa)} 个")
        
        if not generated_qa:
            logger.warning("本次迭代未生成问题")
            return result
        
        # 3. 验证问题 (可选)
        if self.config.verify_answers:
            verified_qa, failed_qa = self._verify_questions(generated_qa)
            result['verified'] = len(verified_qa)
            result['failed'] = len(failed_qa)
            logger.info(f"验证结果: {len(verified_qa)} 通过, {len(failed_qa)} 失败")
            
            # 只保留验证通过的问题
            qa_to_add = verified_qa
        else:
            qa_to_add = generated_qa
            result['verified'] = len(generated_qa)
        
        # 4. 更新覆盖率
        for qa in qa_to_add:
            self._update_coverage_from_qa(qa)
        
        self.all_generated_qa.extend(qa_to_add)
        self.stats.total_questions += len(qa_to_add)
        self.stats.verified_questions += result['verified']
        self.stats.failed_questions += result['failed']
        
        # 5. 计算覆盖率更新
        rates = self.stats.get_coverage_rates()
        result['l0_rate'] = rates['L0']
        result['l1_rate'] = rates['L1']
        result['l2_rate'] = rates['L2']
        result['covered_nodes'] = len(self.stats.covered_nodes)
        result['covered_edges'] = len(self.stats.covered_edges)
        result['covered_2hop'] = len(self.stats.covered_2hop_paths)
        
        # 6. 保存中间结果和更新覆盖率
        if self.config.save_intermediate:
            iter_file = output_dir / f"iteration_{iteration:02d}.json"
            with open(iter_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'iteration': iteration,
                    'questions': [self._qa_to_dict(qa) for qa in qa_to_add],
                    'coverage_after': {
                        'L0': {'covered': result['covered_nodes'], 'total': self.stats.total_nodes, 'rate': result['l0_rate']},
                        'L1': {'covered': result['covered_edges'], 'total': self.stats.total_edges, 'rate': result['l1_rate']},
                        'L2': {'covered': result['covered_2hop'], 'total': self.stats.total_2hop_paths, 'rate': result['l2_rate']},
                    },
                    'stats': result,
                }, f, indent=2, ensure_ascii=False)
            
            # 保存更新后的覆盖率状态
            self._save_coverage_update(output_dir)
            
            # 追加到题库文件
            self._append_to_question_bank(output_dir, qa_to_add, iteration)
        
        # 打印详细日志
        logger.info(f"本轮覆盖率更新:")
        logger.info(f"  L0: {result['covered_nodes']}/{self.stats.total_nodes} = {result['l0_rate']:.1%}")
        logger.info(f"  L1: {result['covered_edges']}/{self.stats.total_edges} = {result['l1_rate']:.1%}")
        logger.info(f"  L2: {result['covered_2hop']}/{self.stats.total_2hop_paths} = {result['l2_rate']:.1%}")
        
        return result
    
    def _identify_coverage_gaps(self) -> Dict:
        """识别覆盖率缺口"""
        gaps = {
            'uncovered_nodes': [],   # 完全未覆盖的节点
            'low_nodes': [],         # 低覆盖节点 (覆盖次数 < threshold)
            'uncovered_edges': [],   # 未覆盖的边
            'low_directions': [],    # 低覆盖方向
        }
        
        # 未覆盖节点
        for node_id, count in self.stats.node_coverage_count.items():
            if count == 0:
                gaps['uncovered_nodes'].append(node_id)
            elif count < self.stats.low_coverage_threshold:
                gaps['low_nodes'].append((node_id, count))
        
        # 未覆盖边
        for edge_key, count in self.stats.edge_coverage_count.items():
            if count == 0:
                gaps['uncovered_edges'].append(edge_key)
        
        # 低覆盖方向
        all_directions = ['front', 'front-left', 'left', 'back-left', 
                         'back', 'back-right', 'right', 'front-right']
        for direction in all_directions:
            count = self.stats.direction_coverage.get(direction, 0)
            if count < 3:  # 每个方向至少3个问题
                gaps['low_directions'].append((direction, count))
        
        return gaps
    
    def _generate_questions_by_strategy(self, strategy: Dict) -> List:
        """根据缺口分析策略生成问题 (模板驱动)"""
        generated = []
        focus_level = strategy['focus_level']
        focus_items = strategy['focus_items']
        target_count = strategy['suggested_count'] or self.config.questions_per_iteration
        
        logger.info(f"生成策略: 级别={focus_level}, 目标数={target_count}")
        
        # 使用模板驱动生成器
        self._init_qa_generator()
        
        if self._qa_generator:
            try:
                from qa_generator_v2.coverage_driven_template_generator import CoverageGoal
                
                goal = CoverageGoal(
                    l0_target=self.config.target_l0_coverage,
                    l1_target=self.config.target_l1_coverage,
                    l2_target=0.3,
                    max_questions=target_count,
                )
                
                result = self._qa_generator.generate(
                    coverage_stats=self.stats,
                    goal=goal,
                )
                
                # 将 GeneratedQA dict 转换为兼容格式
                for q in result.questions:
                    from collections import namedtuple
                    QAPair = namedtuple('QAPair', [
                        'question', 'answer', 'question_type',
                        'target_objects', 'reference_objects',
                        'directions_used', 'difficulty', 'metadata'])
                    
                    # 提取方向和参照信息
                    covered = q.get('covered_elements', [])
                    level = q.get('coverage_level', 'L0')
                    
                    qa = QAPair(
                        question=q['question'],
                        answer=q['answer'],
                        question_type=q.get('question_type', ''),
                        target_objects=covered[:1] if covered else [],
                        reference_objects=covered[1:] if len(covered) > 1 else [],
                        directions_used=[],  # 已由模板覆盖
                        difficulty=level,
                        metadata={
                            'generation_method': 'template',
                            'template_id': q.get('template_id', ''),
                            'level': level,
                        }
                    )
                    generated.append(qa)
                    
                logger.info(f"模板生成器: {len(generated)} 题, "
                           f"耗时 {result.generation_time:.2f}s")
                
            except Exception as e:
                logger.error(f"模板生成器调用失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 后备: 简单模板生成
        if not generated:
            generated = self._generate_questions_by_level(focus_level, focus_items, target_count)
        
        return generated
    
    def _generate_questions_by_level(self, level: str, items: List, count: int) -> List:
        """根据难度级别生成问题（备选模板方案）"""
        from collections import namedtuple
        QAPair = namedtuple('QAPair', ['question', 'answer', 'question_type', 
                                       'target_objects', 'reference_objects',
                                       'directions_used', 'difficulty', 'metadata'])
        
        questions = []
        node_map = {n.get('unique_id', n.get('id', '')): n 
                    for n in self.scene_data.get('nodes', [])}
        edges = self.scene_data.get('edges', [])
        
        if level == 'L0':
            # L0: 单节点问题
            for item in items[:count]:
                node = node_map.get(item, {})
                node_type = node.get('type', 'object')
                status = node.get('status', 'unknown')
                
                q = QAPair(
                    question=f"What is the status of {item}?",
                    answer=status,
                    question_type="status",
                    target_objects=[item],
                    reference_objects=[],
                    directions_used=[],
                    difficulty="L0",
                    metadata={'generation_method': 'template', 'level': 'L0'}
                )
                questions.append(q)
        
        elif level == 'L1':
            # L1: 空间关系问题
            for edge in edges[:count]:
                src = edge.get('source', '')
                tgt = edge.get('target', '')
                direction = self._extract_direction(edge)
                
                if src and tgt and direction:
                    q = QAPair(
                        question=f"What is to the {direction} of {src}?",
                        answer=tgt,
                        question_type="position",
                        target_objects=[tgt],
                        reference_objects=[src],
                        directions_used=[direction],
                        difficulty="L1",
                        metadata={'generation_method': 'template', 'level': 'L1'}
                    )
                    questions.append(q)
        
        elif level == 'L2':
            # L2: 两跳路径问题
            ego_edges = [e for e in edges if e.get('source') == 'ego']
            for edge1 in ego_edges[:count]:
                mid = edge1.get('target', '')
                dir1 = self._extract_direction(edge1)
                if not mid or mid == 'ego':
                    continue
                
                mid_edges = [e for e in edges if e.get('source') == mid]
                if mid_edges:
                    edge2 = mid_edges[0]
                    end = edge2.get('target', '')
                    end_node = node_map.get(end, {})
                    status = end_node.get('status', 'unknown')
                    
                    q = QAPair(
                        question=f"What is the status of the object to the {dir1} of ego?",
                        answer=status,
                        question_type="chain",
                        target_objects=[mid],
                        reference_objects=['ego'],
                        directions_used=[dir1],
                        difficulty="L2",
                        metadata={'generation_method': 'template', 'level': 'L2', 'path': f'ego->{mid}'}
                    )
                    questions.append(q)
        
        return questions[:count]
    
    def _generate_questions_for_gaps(self, gaps: Dict) -> List:
        """根据缺口生成问题（旧接口，保持兼容）"""
        strategy = {
            'focus_level': 'L0',
            'focus_items': gaps.get('uncovered_nodes', [])[:15],
            'suggested_count': self.config.questions_per_iteration,
            'question_types': ['status', 'exist'],
        }
        return self._generate_questions_by_strategy(strategy)
    
    def _generate_simple_questions(self, target_nodes: List[str]) -> List:
        """简单模板生成问题（备选方案）"""
        from collections import namedtuple
        QAPair = namedtuple('QAPair', ['question', 'answer', 'question_type', 
                                       'target_objects', 'reference_objects',
                                       'directions_used', 'difficulty', 'metadata'])
        
        questions = []
        
        # 获取节点信息
        node_map = {}
        for node in self.scene_data.get('nodes', []):
            node_id = node.get('unique_id', node.get('id', ''))
            node_map[node_id] = node
        
        for node_id in target_nodes[:self.config.questions_per_iteration]:
            node = node_map.get(node_id, {})
            node_type = node.get('type', 'object')
            status = node.get('status', '')
            
            # 生成存在性问题
            q1 = QAPair(
                question=f"Is there a {node_type} in the scene?",
                answer="Yes",
                question_type="exist",
                target_objects=[node_id],
                reference_objects=[],
                directions_used=[],
                difficulty="L0",
                metadata={'generation_method': 'simple_template', 'gap_type': 'uncovered_node'}
            )
            questions.append(q1)
            
            # 生成状态问题 (如果有状态)
            if status and status not in ['unknown', '']:
                q2 = QAPair(
                    question=f"What is the status of {node_id}?",
                    answer=status,
                    question_type="status",
                    target_objects=[node_id],
                    reference_objects=[],
                    directions_used=[],
                    difficulty="L0",
                    metadata={'generation_method': 'simple_template', 'gap_type': 'uncovered_node'}
                )
                questions.append(q2)
        
        return questions
    
    def _verify_questions(self, qa_list: List) -> Tuple[List, List]:
        """使用VQA Pipeline验证问题"""
        verified = []
        failed = []
        
        self._init_vqa_pipeline()
        
        if not self._vqa_pipeline:
            # VQA不可用，全部视为通过
            logger.warning("VQA Pipeline不可用，跳过验证")
            return qa_list, []
        
        for qa in qa_list:
            try:
                question = qa.question if hasattr(qa, 'question') else qa.get('question', '')
                expected_answer = qa.answer if hasattr(qa, 'answer') else qa.get('answer', '')
                
                # 调用VQA Pipeline
                result = self._vqa_pipeline.process_question(question)
                
                if result.get('success'):
                    predicted = result.get('answer', '')
                    # 简单匹配检查
                    if self._answers_match(predicted, expected_answer):
                        verified.append(qa)
                    else:
                        failed.append(qa)
                else:
                    failed.append(qa)
                    
            except Exception as e:
                logger.debug(f"验证问题失败: {e}")
                failed.append(qa)
        
        return verified, failed
    
    def _answers_match(self, predicted: str, expected: str) -> bool:
        """检查答案是否匹配"""
        if not predicted or not expected:
            return False
        
        pred = predicted.lower().strip()
        exp = expected.lower().strip()
        
        # 完全匹配
        if pred == exp:
            return True
        
        # 包含匹配
        if exp in pred or pred in exp:
            return True
        
        # Yes/No 匹配
        yes_words = {'yes', 'true', '1', 'correct'}
        no_words = {'no', 'false', '0', 'incorrect'}
        
        if pred in yes_words and exp in yes_words:
            return True
        if pred in no_words and exp in no_words:
            return True
        
        return False
    
    def _update_coverage_from_qa(self, qa):
        """
        从QA更新覆盖率
        
        边的类型:
        1. 空间关系边: ref -[direction]-> target (如 ego -[front-left]-> car1)
        2. 属性边: object -[attribute_type]-> value (如 car1 -[status]-> stopped)
        
        两种边都计入L1覆盖率
        """
        # 获取QA属性
        target_objects = []
        if hasattr(qa, 'target_objects'):
            target_objects = qa.target_objects
        elif isinstance(qa, dict):
            target_objects = qa.get('target_objects', [])
        
        reference_objects = []
        if hasattr(qa, 'reference_objects'):
            reference_objects = qa.reference_objects
        elif isinstance(qa, dict):
            reference_objects = qa.get('reference_objects', [])
        
        directions_used = []
        if hasattr(qa, 'directions_used'):
            directions_used = qa.directions_used
        elif isinstance(qa, dict):
            directions_used = qa.get('directions_used', [])
        
        question_type = ''
        if hasattr(qa, 'question_type'):
            question_type = qa.question_type
        elif isinstance(qa, dict):
            question_type = qa.get('question_type', '')
        
        answer = ''
        if hasattr(qa, 'answer'):
            answer = qa.answer
        elif isinstance(qa, dict):
            answer = qa.get('answer', '')
        
        # 更新L0节点覆盖
        for obj_id in target_objects + reference_objects:
            self.stats.add_node_coverage(obj_id)
        
        # 更新方向覆盖
        for direction in directions_used:
            self.stats.add_direction_coverage(direction)
        
        # 更新L1边覆盖
        # 类型1: 空间关系边 (ref -[direction]-> target)
        if reference_objects and target_objects and directions_used:
            for ref in reference_objects:
                for direction in directions_used:
                    for tgt in target_objects:
                        self.stats.add_edge_coverage(ref, direction, tgt)
        
        # 类型2: 属性边 (object -[attribute_type]-> value)
        # status/exist/object类型的问题，构成属性边
        if target_objects and question_type in ['status', 'exist', 'object', 'count']:
            for obj_id in target_objects:
                # 属性边: obj_id -[question_type]-> answer
                attr_edge_key = f"{obj_id}-{question_type}"
                self.stats.covered_edges.add((obj_id, question_type, str(answer)[:20]))
                if attr_edge_key not in self.stats.edge_coverage_count:
                    self.stats.edge_coverage_count[attr_edge_key] = 0
                self.stats.edge_coverage_count[attr_edge_key] += 1
    
    def _qa_to_dict(self, qa) -> Dict:
        """将QA对象转换为字典"""
        if isinstance(qa, dict):
            return qa
        
        return {
            'question': getattr(qa, 'question', ''),
            'answer': getattr(qa, 'answer', ''),
            'question_type': getattr(qa, 'question_type', ''),
            'target_objects': getattr(qa, 'target_objects', []),
            'reference_objects': getattr(qa, 'reference_objects', []),
            'directions_used': getattr(qa, 'directions_used', []),
            'difficulty': getattr(qa, 'difficulty', ''),
            'metadata': getattr(qa, 'metadata', {}),
        }
    
    def _check_coverage_target(self) -> bool:
        """检查是否达到目标覆盖率"""
        rates = self.stats.get_coverage_rates()
        
        l0_ok = rates['L0'] >= self.config.target_l0_coverage
        l1_ok = rates['L1'] >= self.config.target_l1_coverage
        
        return l0_ok and l1_ok
    
    def _print_coverage_summary(self, stage: str):
        """打印覆盖率摘要"""
        rates = self.stats.get_coverage_rates()
        
        logger.info(f"\n{stage}覆盖率:")
        logger.info(f"  L0 (节点): {len(self.stats.covered_nodes)}/{self.stats.total_nodes} = {rates['L0']:.1%}")
        logger.info(f"  L1 (边):   {len(self.stats.covered_edges)}/{self.stats.total_edges} = {rates['L1']:.1%}")
        logger.info(f"  L2 (两跳): {len(self.stats.covered_2hop_paths)}/{self.stats.total_2hop_paths} = {rates['L2']:.1%}")
        logger.info(f"  问题数:   {self.stats.total_questions}")
    
    def _save_final_results(self, output_dir: Path, timestamp: str) -> Dict:
        """保存最终结果"""
        # 保存所有问题
        qa_file = output_dir / f"all_questions_{timestamp}.json"
        with open(qa_file, 'w', encoding='utf-8') as f:
            json.dump({
                'scene_name': self.stats.scene_name,
                'frame_idx': self.stats.frame_idx,
                'total_questions': len(self.all_generated_qa),
                'questions': [self._qa_to_dict(qa) for qa in self.all_generated_qa],
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ 问题已保存: {qa_file}")
        
        # 保存覆盖率统计
        coverage_file = output_dir / f"coverage_final_{timestamp}.json"
        self.stats.save(str(coverage_file))
        logger.info(f"✓ 覆盖率已保存: {coverage_file}")
        
        # 保存迭代历史
        history_file = output_dir / f"iteration_history_{timestamp}.json"
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(self.iteration_history, f, indent=2)
        logger.info(f"✓ 迭代历史已保存: {history_file}")
        
        # 生成报告
        report = self._generate_report()
        report_file = output_dir / f"report_{timestamp}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"✓ 报告已保存: {report_file}")
        
        return {
            'success': True,
            'total_iterations': len(self.iteration_history),
            'total_questions': len(self.all_generated_qa),
            'final_coverage': self.stats.get_coverage_rates(),
            'output_dir': str(output_dir),
        }
    
    def _generate_report(self) -> str:
        """生成文本报告"""
        lines = []
        lines.append("=" * 70)
        lines.append("  覆盖率驱动问题生成 - 最终报告")
        lines.append("=" * 70)
        lines.append("")
        
        lines.append(f"场景: {self.stats.scene_name} 帧{self.stats.frame_idx}")
        lines.append(f"总迭代次数: {len(self.iteration_history)}")
        lines.append(f"总生成问题: {len(self.all_generated_qa)}")
        lines.append("")
        
        lines.append("## 最终覆盖率")
        rates = self.stats.get_coverage_rates()
        lines.append(f"  L0 (节点): {len(self.stats.covered_nodes)}/{self.stats.total_nodes} = {rates['L0']:.1%}")
        lines.append(f"  L1 (边):   {len(self.stats.covered_edges)}/{self.stats.total_edges} = {rates['L1']:.1%}")
        lines.append(f"  L2 (两跳): {len(self.stats.covered_2hop_paths)}/{self.stats.total_2hop_paths} = {rates['L2']:.1%}")
        lines.append("")
        
        lines.append("## 迭代历史")
        for hist in self.iteration_history:
            lines.append(f"  迭代{hist['iteration']}: 生成{hist['generated']}题, "
                        f"验证通过{hist['verified']}题, L0={hist['l0_rate']:.1%}")
        lines.append("")
        
        lines.append("## 覆盖节点")
        lines.append(f"  已覆盖: {sorted(self.stats.covered_nodes)[:20]}...")
        lines.append("")
        
        lines.append("## 低覆盖节点 (Top 10)")
        low_cov = sorted(self.stats.node_coverage_count.items(), key=lambda x: x[1])[:10]
        for node_id, count in low_cov:
            lines.append(f"  {node_id}: {count} 次")
        
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="覆盖率驱动问题生成闭环")
    parser.add_argument("--scene-graph", "-s", required=True, help="场景图JSON文件")
    parser.add_argument("--output", "-o", required=True, help="输出目录")
    parser.add_argument("--existing-questions", "-q", help="已有问题集JSON文件")
    parser.add_argument("--target-l0", type=float, default=0.8, help="L0目标覆盖率")
    parser.add_argument("--target-l1", type=float, default=0.5, help="L1目标覆盖率")
    parser.add_argument("--max-iterations", type=int, default=10, help="最大迭代次数")
    parser.add_argument("--questions-per-iter", type=int, default=20, help="每次迭代问题数")
    parser.add_argument("--no-verify", action="store_true", help="跳过VQA验证")
    
    args = parser.parse_args()
    
    config = LoopConfig(
        target_l0_coverage=args.target_l0,
        target_l1_coverage=args.target_l1,
        max_iterations=args.max_iterations,
        questions_per_iteration=args.questions_per_iter,
        verify_answers=not args.no_verify,
    )
    
    controller = CoverageLoopController(config)
    result = controller.run(
        scene_graph_path=args.scene_graph,
        output_dir=args.output,
        existing_questions_path=args.existing_questions,
    )
    
    print(f"\n完成! 结果: {result}")


if __name__ == "__main__":
    main()
