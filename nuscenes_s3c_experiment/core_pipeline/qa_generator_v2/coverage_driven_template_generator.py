"""
Coverage-Driven Template Generator — 覆盖率驱动的模板问题生成器

完全基于模板库 + 场景图数据确定性生成，不依赖 LLM。

核心流程 (覆盖率驱动):
  1. Goal:     设定 L0/L1/L2 覆盖率目标
  2. 候选集:   从当前覆盖率提取未覆盖的节点/边/路径
  3. 预算:     设定生成数量上限或目标覆盖率
  4. 打乱:     随机化候选集顺序
  5. 逐个调用:  对每个候选元素选择模板并填充
  6. 生成:     输出满足需求的测试套件

取代之前的 LLM 生成方式，提供:
  - 更高的确定性和可重复性
  - 更快的生成速度 (无 API 调用)
  - 100% 答案准确率 (从场景图直接计算)
  - 完全受覆盖率指标驱动
"""

import json
import random
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict

from .template_library import get_template_library, TemplateEntry
from .template_filler import TemplateFiller, GeneratedQA, SceneGraphIndex
from .coverage_tracker import CoverageTracker
from .config import TYPE_NAMES, QUESTION_TYPES

logger = logging.getLogger(__name__)


@dataclass
class CoverageGoal:
    """覆盖率目标（单层级聚焦模式）
    
    设计理念:
      每轮只聚焦一个覆盖层级 (L0/L1/L2)，预算全部分配给该层级。
      高层级问题会自然附带提升低层级覆盖率:
        - 聚焦 L2 → L1, L0 附带提升
        - 聚焦 L1 → L0 附带提升
        - 聚焦 L0 → 仅 L0 提升
      建议顺序: 先 L2 → 再 L1 → 最后补 L0
    """
    focus_level: str = "L0"     # 本轮聚焦的层级: "L0" / "L1" / "L2"
    target: float = 1.0         # 该层级的目标覆盖率 (0~1)
    max_questions: int = 200    # 最大生成题数
    question_type_weights: Dict[str, float] = field(default_factory=lambda: {
        "exist": 0.30,
        "status": 0.30,
        "object": 0.20,
        "comparison": 0.20,
    })


@dataclass
class GenerationResult:
    """生成结果"""
    questions: List[Dict]           # 生成的问答对列表
    coverage_before: Dict           # 生成前覆盖率
    coverage_after: Dict            # 生成后覆盖率
    gaps_total: int                 # 总缺口数
    gaps_filled: int                # 已填补缺口数
    generation_time: float          # 生成耗时(秒)
    template_stats: Dict            # 模板使用统计


class CoverageDrivenTemplateGenerator:
    """
    覆盖率驱动的模板问题生成器

    Usage:
        generator = CoverageDrivenTemplateGenerator(scene_data)
        result = generator.generate(coverage_stats, goal)
        result.questions  # [{question, answer, template_id, ...}]
    """

    def __init__(self, scene_data: Dict, seed: int = None):
        """
        Args:
            scene_data: 场景图数据 (含 nodes 和 edges)
            seed: 随机种子 (用于可重复性)
        """
        self.scene_data = scene_data
        self.filler = TemplateFiller(scene_data)
        self.library = get_template_library()

        if seed is not None:
            random.seed(seed)

        scene_name = scene_data.get("scene_name", "unknown")
        frame_idx = scene_data.get("frame_idx", 0)
        logger.info(f"初始化模板生成器: scene={scene_name}, frame={frame_idx}, "
                    f"nodes={len(self.filler.index.non_ego_nodes)}, "
                    f"edges={len(self.filler.index.edges)}")

    # ========================================================================
    #  主入口
    # ========================================================================

    def generate(self, coverage_stats=None, goal: CoverageGoal = None) -> GenerationResult:
        """
        根据覆盖率缺口生成问题

        Args:
            coverage_stats: 当前覆盖率数据 (UnifiedCoverageStats 或 dict)
                            若为 None，视为全空覆盖
            goal: 覆盖率目标，若为 None 使用默认目标

        Returns:
            GenerationResult 包含生成的问答对和覆盖率变化
        """
        start_time = time.time()
        goal = goal or CoverageGoal()

        # Step 1: 明确聚焦层级
        focus = goal.focus_level
        coverage_before = self._compute_coverage_rates(coverage_stats)
        logger.info(f"本轮聚焦: {focus}, 目标: {goal.target:.0%}")
        logger.info(f"当前覆盖率: L0={coverage_before['L0']:.1%}, "
                    f"L1={coverage_before['L1']:.1%}, L2={coverage_before['L2']:.1%}")

        # Step 2: 提取聚焦层级的候选缺口
        all_gaps = self.filler.extract_gaps_from_coverage(coverage_stats)
        focus_gaps = [g for g in all_gaps if g["level"] == focus]
        logger.info(f"{focus} 缺口数: {len(focus_gaps)}")

        # Step 3: 定预算 (全部给聚焦层级，不超过缺口数)
        budget = min(goal.max_questions, len(focus_gaps))
        logger.info(f"预算: {budget} 题 (max={goal.max_questions}, gaps={len(focus_gaps)})")

        # Step 4: 打乱候选集
        random.shuffle(focus_gaps)
        focus_gaps = focus_gaps[:budget]

        # Step 5: 逐个生成
        all_qa: List[GeneratedQA] = []
        template_usage: Dict[str, int] = defaultdict(int)
        covered_set: Set[str] = set()  # 本轮已覆盖的元素

        all_qa = self._generate_for_level(
            focus, focus_gaps, budget, goal, template_usage, covered_set)

        # Step 6: 构建结果
        questions = [self._qa_to_dict(qa) for qa in all_qa]

        # 计算新覆盖率
        coverage_after = self._estimate_coverage_after(coverage_stats, all_qa)

        elapsed = time.time() - start_time
        result = GenerationResult(
            questions=questions,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            gaps_total=len(all_gaps),
            gaps_filled=len(all_qa),
            generation_time=elapsed,
            template_stats=dict(template_usage),
        )

        logger.info(f"生成完成: {len(questions)} 题, 耗时 {elapsed:.2f}s")
        logger.info(f"覆盖率变化: L0 {coverage_before['L0']:.1%}→{coverage_after['L0']:.1%}, "
                    f"L1 {coverage_before['L1']:.1%}→{coverage_after['L1']:.1%}, "
                    f"L2 {coverage_before['L2']:.1%}→{coverage_after['L2']:.1%}")

        return result

    # ========================================================================
    #  Step 2: 计算覆盖率
    # ========================================================================

    def _compute_coverage_rates(self, coverage_stats) -> Dict[str, float]:
        """计算当前 L0/L1/L2 覆盖率"""
        index = self.filler.index

        total_nodes = len(index.non_ego_nodes)
        total_edges = len(index.edges)
        # 计算所有可能的两跳路径数
        total_2hop = 0
        for edge in index.edges:
            mid_id = edge.get("target", "")
            total_2hop += len(index.edges_from.get(mid_id, []))

        covered_nodes = 0
        covered_edges = 0
        covered_2hop = 0

        if coverage_stats is not None:
            if hasattr(coverage_stats, 'covered_nodes'):
                covered_nodes = len(coverage_stats.covered_nodes)
                covered_edges = len(coverage_stats.covered_edges)
                covered_2hop = len(getattr(coverage_stats, 'covered_2hop_paths', set()))
            elif isinstance(coverage_stats, dict):
                covered_nodes = len(coverage_stats.get('covered_nodes', []))
                covered_edges = len(coverage_stats.get('covered_edges', []))
                covered_2hop = len(coverage_stats.get('covered_2hop_paths', []))

        return {
            "L0": covered_nodes / max(total_nodes, 1),
            "L1": covered_edges / max(total_edges, 1),
            "L2": covered_2hop / max(total_2hop, 1),
            "L0_detail": {"covered": covered_nodes, "total": total_nodes},
            "L1_detail": {"covered": covered_edges, "total": total_edges},
            "L2_detail": {"covered": covered_2hop, "total": total_2hop},
        }

    # ========================================================================
    #  Step 3: 预算分配
    # ========================================================================

    def _compute_focus_budget(self, coverage_before: Dict, goal: CoverageGoal,
                               focus_gap_count: int) -> int:
        """计算聚焦层级的生成预算
        
        简单逻辑: min(max_questions, 实际缺口数)
        """
        return min(goal.max_questions, focus_gap_count)

    # ========================================================================
    #  Step 4: 分组打乱
    # ========================================================================

    def _group_and_shuffle_gaps(self, gaps: List[Dict]) -> Dict[str, List[Dict]]:
        """按级别分组并打乱"""
        grouped = defaultdict(list)
        for g in gaps:
            grouped[g["level"]].append(g)

        for level in grouped:
            random.shuffle(grouped[level])

        return dict(grouped)

    # ========================================================================
    #  Step 5: 逐级生成
    # ========================================================================

    def _generate_for_level(self, level: str, gaps: List[Dict], budget: int,
                            goal: CoverageGoal, template_usage: Dict[str, int],
                            covered_set: Set[str]) -> List[GeneratedQA]:
        """为某一覆盖级别生成问题"""
        results = []

        # 按问题类型权重确定每种类型的配额
        type_budgets = {}
        for qtype, weight in goal.question_type_weights.items():
            type_budgets[qtype] = max(1, int(budget * weight))

        for gap in gaps:
            if len(results) >= budget:
                break

            # 选择未满配额的问题类型
            available_types = [qt for qt, b in type_budgets.items()
                               if sum(1 for r in results if r.question_type == qt) < b]
            if not available_types:
                available_types = list(goal.question_type_weights.keys())

            # 为该缺口直接生成一个 QA (不生成多个候选)
            qa = self._generate_one_qa_for_gap(gap, available_types, template_usage)

            if qa:
                results.append(qa)
                template_usage[qa.template_id] = template_usage.get(qa.template_id, 0) + 1
                for elem in qa.covered_elements:
                    covered_set.add(elem)

        return results

    def _generate_one_qa_for_gap(self, gap: Dict, question_types: List[str],
                                  template_usage: Dict[str, int]) -> Optional[GeneratedQA]:
        """为单个缺口直接生成一个 QA
        
        策略: 随机选一个问题类型，优先选使用次数少的模板
        """
        level = gap.get("level", "")
        
        # 随机选一个问题类型
        if not question_types:
            question_types = list(self.library.templates_by_type.keys())
        qtype = random.choice(question_types)
        
        # 生成该类型的所有候选，选使用次数最少的
        candidates = []
        if level == "L0":
            candidates = self.filler.fill_for_node_gap(gap["node_id"], [qtype])
        elif level == "L1":
            candidates = self.filler.fill_for_edge_gap(
                gap["source"], gap["target"], gap["direction"], [qtype])
        elif level == "L2":
            candidates = self.filler.fill_for_2hop_gap(
                gap["node1"], gap["node2"], gap["node3"], [qtype])
        
        if not candidates:
            return None
        
        # 选使用次数最少的模板
        candidates.sort(key=lambda qa: (template_usage.get(qa.template_id, 0), random.random()))
        return candidates[0]


    # ========================================================================
    #  覆盖率估算
    # ========================================================================

    def _estimate_coverage_after(self, coverage_stats, new_qa: List[GeneratedQA]) -> Dict[str, float]:
        """估算生成后的覆盖率"""
        index = self.filler.index

        # 基础覆盖集合
        covered_nodes = set()
        covered_edges = set()
        covered_2hop = set()

        if coverage_stats is not None:
            if hasattr(coverage_stats, 'covered_nodes'):
                covered_nodes = set(coverage_stats.covered_nodes)
                covered_edges = set(coverage_stats.covered_edges)
                covered_2hop = set(getattr(coverage_stats, 'covered_2hop_paths', set()))
            elif isinstance(coverage_stats, dict):
                covered_nodes = set(coverage_stats.get('covered_nodes', []))
                raw_edges = coverage_stats.get('covered_edges', [])
                covered_edges = set(tuple(e) if isinstance(e, list) else e for e in raw_edges)
                raw_paths = coverage_stats.get('covered_2hop_paths', [])
                covered_2hop = set(tuple(p) if isinstance(p, list) else p for p in raw_paths)

        # 新增覆盖
        for qa in new_qa:
            for elem in qa.covered_elements:
                covered_nodes.add(elem)

            if qa.coverage_level == "L1" and "direction" in qa.params:
                src = qa.params.get("ref_id", "")
                tgt = qa.params.get("obj_id", "")
                d = qa.params.get("direction", "")
                if src and tgt and d:
                    covered_edges.add((src, d, tgt))

        total_nodes = len(index.non_ego_nodes)
        total_edges = len(index.edges)
        total_2hop = sum(len(index.edges_from.get(e.get("target", ""), []))
                         for e in index.edges)

        return {
            "L0": len(covered_nodes) / max(total_nodes, 1),
            "L1": len(covered_edges) / max(total_edges, 1),
            "L2": len(covered_2hop) / max(total_2hop, 1),
            "L0_detail": {"covered": len(covered_nodes), "total": total_nodes},
            "L1_detail": {"covered": len(covered_edges), "total": total_edges},
            "L2_detail": {"covered": len(covered_2hop), "total": total_2hop},
        }

    # ========================================================================
    #  输出格式化
    # ========================================================================

    def _qa_to_dict(self, qa: GeneratedQA) -> Dict:
        return {
            "question": qa.question,
            "answer": qa.answer,
            "template_id": qa.template_id,
            "coverage_level": qa.coverage_level,
            "question_type": qa.question_type,
            "answer_type": qa.answer_type,
            "covered_elements": qa.covered_elements,
        }

    # ========================================================================
    #  便捷方法
    # ========================================================================

    def generate_and_save(self, coverage_stats=None, goal: CoverageGoal = None,
                          output_path: str = None) -> GenerationResult:
        """生成并保存到文件"""
        result = self.generate(coverage_stats, goal)

        if output_path is None:
            scene_name = self.scene_data.get("scene_name", "unknown")
            frame_idx = self.scene_data.get("frame_idx", 0)
            output_path = f"output/generated_qa/{scene_name}_frame{frame_idx}_qa.json"

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        output_data = {
            "scene_name": self.scene_data.get("scene_name", ""),
            "frame_idx": self.scene_data.get("frame_idx", 0),
            "generation_time": result.generation_time,
            "coverage_before": result.coverage_before,
            "coverage_after": result.coverage_after,
            "gaps_total": result.gaps_total,
            "gaps_filled": result.gaps_filled,
            "template_stats": result.template_stats,
            "questions": result.questions,
        }

        with open(out, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"保存到: {out}")
        return result

    @staticmethod
    def from_scene_graph_file(scene_graph_path: str, seed: int = None) -> 'CoverageDrivenTemplateGenerator':
        """从场景图文件创建生成器"""
        with open(scene_graph_path, "r", encoding="utf-8") as f:
            scene_data = json.load(f)
        return CoverageDrivenTemplateGenerator(scene_data, seed=seed)

    # ========================================================================
    #  CoverageTracker 集成
    # ========================================================================

    def generate_with_tracker(self, tracker: CoverageTracker = None,
                              goal: CoverageGoal = None,
                              output_dir: str = None) -> GenerationResult:
        """
        使用 CoverageTracker 驱动的完整生成流程（单层级聚焦模式）

        流程:
          1. 明确聚焦层级 (goal.focus_level)
          2. 从 tracker 提取该层级的缺口
          3. 定预算 (全部给聚焦层级, 不超过缺口数)
          4. 打乱候选集 + 模板选择 + 生成
          5. 回写 tracker (同时更新 L0/L1/L2, 高层级附带覆盖低层级)
          6. 保存 tracker JSON + QA JSON

        Args:
            tracker: 已有的 CoverageTracker，若为 None 则自动创建
            goal:    覆盖率目标
            output_dir: 输出目录

        Returns:
            GenerationResult
        """
        start_time = time.time()
        goal = goal or CoverageGoal()

        # Step 1: 初始化 tracker + 明确聚焦层级
        focus = goal.focus_level
        if tracker is None:
            tracker = CoverageTracker.from_scene_graph(self.scene_data)

        # Step 2: 从 tracker 提取聚焦层级的缺口
        coverage_before = tracker.coverage_rates()
        gaps = tracker.gaps_as_list()
        focus_gaps = [g for g in gaps if g["level"] == focus]
        logger.info(f"本轮聚焦: {focus}, 目标: {goal.target:.0%}")
        logger.info(f"Tracker 缺口: L0={len(tracker.uncovered_l0())}, "
                    f"L1={len(tracker.uncovered_l1())}, L2={len(tracker.uncovered_l2())}")
        logger.info(f"{focus} 缺口数: {len(focus_gaps)}")

        # Step 3: 定预算 (全部给聚焦层级，不超过缺口数)
        budget = min(goal.max_questions, len(focus_gaps))
        logger.info(f"预算: {budget} 题 (max={goal.max_questions}, gaps={len(focus_gaps)})")

        # Step 4: 打乱 + 生成
        random.shuffle(focus_gaps)
        focus_gaps = focus_gaps[:budget]
        all_qa: List[GeneratedQA] = []
        template_usage: Dict[str, int] = defaultdict(int)
        covered_set: Set[str] = set()

        all_qa = self._generate_for_level(
            focus, focus_gaps, budget, goal, template_usage, covered_set)

        # Step 5: 回写 tracker (record_from_qa 会同时更新 L0/L1/L2 三组 Map)
        for qa in all_qa:
            qa_dict = self._qa_to_dict(qa)
            qa_dict["params"] = qa.params
            tracker.record_from_qa(qa_dict)

        coverage_after = tracker.coverage_rates()
        elapsed = time.time() - start_time

        questions = [self._qa_to_dict(qa) for qa in all_qa]
        result = GenerationResult(
            questions=questions,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            gaps_total=len(gaps),
            gaps_filled=len(all_qa),
            generation_time=elapsed,
            template_stats=dict(template_usage),
        )

        # Step 6: 保存
        if output_dir:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            scene_name = self.scene_data.get("scene_name", "unknown")
            frame_idx = self.scene_data.get("frame_idx", 0)
            prefix = f"{scene_name}_frame{frame_idx}"

            # 保存 tracker
            tracker.save(str(out / f"{prefix}_coverage.json"))
            # 保存 QA
            qa_data = {
                "scene_name": scene_name,
                "frame_idx": frame_idx,
                "generation_time": elapsed,
                "coverage_before": coverage_before,
                "coverage_after": coverage_after,
                "gaps_total": len(gaps),
                "gaps_filled": len(all_qa),
                "template_stats": dict(template_usage),
                "questions": questions,
            }
            with open(out / f"{prefix}_qa.json", "w", encoding="utf-8") as f:
                json.dump(qa_data, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存到: {out / prefix}_*.json")

        logger.info(f"生成完成: {len(questions)} 题, 耗时 {elapsed:.2f}s")
        logger.info(f"覆盖率: L0 {coverage_before['L0']:.1%}→{coverage_after['L0']:.1%}, "
                    f"L1 {coverage_before['L1']:.1%}→{coverage_after['L1']:.1%}, "
                    f"L2 {coverage_before['L2']:.1%}→{coverage_after['L2']:.1%}")

        return result
