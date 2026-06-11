"""
Deterministic Template Filler — 确定性模板填充与答案计算

从场景图数据直接填充模板并计算答案，完全不需要 LLM。

工作流程:
  1. 接收覆盖缺口 (uncovered node / edge / 2-hop path)
  2. 从模板库选择合适的模板
  3. 用场景图数据填充模板占位符
  4. 基于场景图确定性计算答案

支持的覆盖缺口类型:
  - L0: 未覆盖的节点 → 生成单对象查询
  - L1: 未覆盖的边 (source, direction, target) → 生成方向关系查询
  - L2: 未覆盖的两跳路径 → 生成复合查询
"""

import random
import logging
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from collections import defaultdict

from .template_library import TemplateEntry, get_template_library
from .config import TYPE_NAMES, STATUS_DISPLAY_NAMES

logger = logging.getLogger(__name__)


@dataclass
class GeneratedQA:
    """生成的问答对"""
    question: str
    answer: str
    template_id: str
    coverage_level: str        # L0 / L1 / L2
    question_type: str         # exist / count / status / object / comparison
    answer_type: str           # bool / number / type / status
    covered_elements: List[str]  # 该问题覆盖的场景图元素
    params: Dict[str, str] = field(default_factory=dict)  # 填充参数


class SceneGraphIndex:
    """
    场景图索引 — 预计算常用查询的索引以加速模板填充
    """

    def __init__(self, scene_data: Dict):
        self.scene_data = scene_data
        self.nodes: List[Dict] = scene_data.get("nodes", [])
        self.edges: List[Dict] = scene_data.get("edges", [])

        # 索引: unique_id -> node
        self.node_by_id: Dict[str, Dict] = {}
        # 索引: type -> [node]
        self.nodes_by_type: Dict[str, List[Dict]] = defaultdict(list)
        # 索引: status -> [node]
        self.nodes_by_status: Dict[str, List[Dict]] = defaultdict(list)
        # 索引: (type, status) -> [node]
        self.nodes_by_type_status: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
        # 索引: source_id -> [(edge, target_node)]
        self.edges_from: Dict[str, List[Tuple[Dict, Dict]]] = defaultdict(list)
        # 索引: target_id -> [(edge, source_node)]
        self.edges_to: Dict[str, List[Tuple[Dict, Dict]]] = defaultdict(list)
        # 索引: (source_id, direction_8) -> [target_node]
        self.targets_by_direction: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
        # 所有非 ego 节点
        self.non_ego_nodes: List[Dict] = []

        self._build_indices()

    def _build_indices(self):
        for node in self.nodes:
            uid = node.get("unique_id", "")
            self.node_by_id[uid] = node
            ntype = node.get("type", "unknown")
            status = node.get("status", "unknown")
            self.nodes_by_type[ntype].append(node)
            self.nodes_by_status[status].append(node)
            self.nodes_by_type_status[(ntype, status)].append(node)
            if ntype != "ego":
                self.non_ego_nodes.append(node)

        for edge in self.edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            src_node = self.node_by_id.get(src)
            tgt_node = self.node_by_id.get(tgt)
            if tgt_node:
                self.edges_from[src].append((edge, tgt_node))
            if src_node:
                self.edges_to[tgt].append((edge, src_node))

            direction_8 = self._get_direction_8(edge)
            if direction_8 and tgt_node:
                self.targets_by_direction[(src, direction_8)].append(tgt_node)
            # 也索引 angle_matches 宽松匹配
            for d in self._get_angle_matches(edge):
                if tgt_node:
                    key = (src, d)
                    if tgt_node not in self.targets_by_direction.get(key, []):
                        self.targets_by_direction[key].append(tgt_node)

    def _get_direction_8(self, edge: Dict) -> Optional[str]:
        if "direction_8" in edge:
            return edge["direction_8"]
        metrics = edge.get("metrics", {})
        if isinstance(metrics, dict):
            ds = metrics.get("direction_source", {})
            if isinstance(ds, dict):
                return ds.get("direction_8")
            de = metrics.get("direction_ego", {})
            if isinstance(de, dict):
                return de.get("direction_8")
        return None

    def _get_angle_matches(self, edge: Dict) -> List[str]:
        metrics = edge.get("metrics", {})
        if isinstance(metrics, dict):
            ds = metrics.get("direction_source", {})
            if isinstance(ds, dict):
                return ds.get("angle_matches", [])
            de = metrics.get("direction_ego", {})
            if isinstance(de, dict):
                return de.get("angle_matches", [])
        return []

    def get_edge_between(self, source_id: str, target_id: str) -> Optional[Dict]:
        for edge, tgt in self.edges_from.get(source_id, []):
            if tgt.get("unique_id") == target_id:
                return edge
        return None


class TemplateFiller:
    """
    确定性模板填充器

    核心方法:
      - fill_for_node_gap(node_id) → 生成覆盖该节点的 QA
      - fill_for_edge_gap(source, target, direction) → 生成覆盖该边的 QA
      - fill_for_2hop_gap(node1, node2, node3) → 生成覆盖该两跳路径的 QA
      - generate_batch(gaps, budget) → 批量生成覆盖给定缺口的 QA
    """

    def __init__(self, scene_data: Dict):
        self.index = SceneGraphIndex(scene_data)
        self.library = get_template_library()
        self._type_names = TYPE_NAMES
        self._status_names = STATUS_DISPLAY_NAMES

    # ========================================================================
    #  公共接口
    # ========================================================================

    def fill_for_node_gap(self, node_id: str, question_types: List[str] = None) -> List[GeneratedQA]:
        """为未覆盖的节点生成 L0 问题"""
        node = self.index.node_by_id.get(node_id)
        if not node:
            return []

        results = []
        obj_type = node.get("type", "unknown")
        status = node.get("status", "unknown")
        obj_id = node.get("unique_id", "")

        if obj_type == "ego":
            return []

        qtypes = question_types or ["exist", "status", "object", "comparison"]
        templates = []
        for qt in qtypes:
            templates.extend(self.library.get_by_level_type("L0", qt))

        # 唯一性检查: 同类型有多个对象时，跳过 type-only 模板 (避免歧义)
        type_count = len(self.index.nodes_by_type.get(obj_type, []))
        status_type_count = len(self.index.nodes_by_type_status.get((obj_type, status), []))

        for tmpl in templates:
            if self._is_ambiguous_reference(tmpl, type_count, status_type_count):
                continue
            qa = self._try_fill_l0(tmpl, node)
            if qa:
                results.append(qa)

        return results

    def fill_for_edge_gap(self, source_id: str, target_id: str, direction: str,
                          question_types: List[str] = None) -> List[GeneratedQA]:
        """为未覆盖的边生成 L1 问题"""
        source_node = self.index.node_by_id.get(source_id)
        target_node = self.index.node_by_id.get(target_id)
        edge = self.index.get_edge_between(source_id, target_id)

        if not source_node or not target_node:
            return []

        results = []
        qtypes = question_types or ["exist", "status", "object", "comparison"]
        templates = []
        for qt in qtypes:
            templates.extend(self.library.get_by_level_type("L1", qt))

        for tmpl in templates:
            qa = self._try_fill_l1(tmpl, source_node, target_node, direction, edge)
            if qa:
                results.append(qa)

        return results

    def fill_for_2hop_gap(self, node1_id: str, node2_id: str, node3_id: str,
                          question_types: List[str] = None) -> List[GeneratedQA]:
        """为未覆盖的两跳路径生成 L2 问题"""
        n1 = self.index.node_by_id.get(node1_id)
        n2 = self.index.node_by_id.get(node2_id)
        n3 = self.index.node_by_id.get(node3_id)

        if not n1 or not n2 or not n3:
            return []

        e1 = self.index.get_edge_between(node1_id, node2_id)
        e2 = self.index.get_edge_between(node2_id, node3_id)

        results = []
        qtypes = question_types or ["exist", "status", "object", "comparison"]
        templates = []
        for qt in qtypes:
            templates.extend(self.library.get_by_level_type("L2", qt))

        for tmpl in templates:
            qa = self._try_fill_l2(tmpl, n1, n2, n3, e1, e2)
            if qa:
                results.append(qa)

        return results

    def generate_batch(self, gaps: List[Dict], budget: int = 100,
                       question_types: List[str] = None) -> List[GeneratedQA]:
        """
        批量生成问题，覆盖给定的缺口列表

        Args:
            gaps: 缺口列表，每项为 {"level": "L0/L1/L2", "elements": [...]}
                L0: {"level": "L0", "node_id": str}
                L1: {"level": "L1", "source": str, "target": str, "direction": str}
                L2: {"level": "L2", "node1": str, "node2": str, "node3": str}
            budget: 最大生成数量
            question_types: 限定问题类型

        Returns:
            GeneratedQA 列表
        """
        all_qa = []
        random.shuffle(gaps)

        for gap in gaps:
            if len(all_qa) >= budget:
                break

            level = gap.get("level", "")
            candidates = []

            if level == "L0":
                candidates = self.fill_for_node_gap(
                    gap["node_id"], question_types)
            elif level == "L1":
                candidates = self.fill_for_edge_gap(
                    gap["source"], gap["target"], gap["direction"], question_types)
            elif level == "L2":
                candidates = self.fill_for_2hop_gap(
                    gap["node1"], gap["node2"], gap["node3"], question_types)

            if candidates:
                selected = random.choice(candidates)
                all_qa.append(selected)

        logger.info(f"批量生成完成: {len(all_qa)}/{budget} 题 (缺口 {len(gaps)} 个)")
        return all_qa

    # ========================================================================
    #  歧义检查
    # ========================================================================

    # 引用特定对象但只用 {obj_type} 的 answer_logic (多同类时歧义)
    _TYPE_ONLY_LOGICS = {"node_status_by_type", "what_is_status_type"}
    # 引用特定对象用 {status}+thing 的 answer_logic (多同状态时歧义)
    _STATUS_THING_LOGICS = {"what_is_status_thing"}

    def _is_ambiguous_reference(self, tmpl: TemplateEntry,
                                 type_count: int, status_type_count: int) -> bool:
        """
        检查模板是否会产生歧义引用。

        当场景中有多个同类型/同状态对象时，type-only 模板
        (如 "What is the status of the car?") 会让 CV 模型无法确定指哪个对象。

        Returns:
            True 表示该模板在当前场景下会产生歧义，应跳过
        """
        logic = tmpl.answer_logic
        if logic in self._TYPE_ONLY_LOGICS and type_count > 1:
            return True
        if logic in self._STATUS_THING_LOGICS and status_type_count > 1:
            return True
        return False

    # ========================================================================
    #  L0 填充逻辑
    # ========================================================================

    def _try_fill_l0(self, tmpl: TemplateEntry, node: Dict) -> Optional[GeneratedQA]:
        obj_type = node.get("type", "unknown")
        obj_id = node.get("unique_id", "")
        status = node.get("status", "unknown")
        type_singular, type_plural = self._get_type_names(obj_type)
        status_display = self._status_names.get(status, status)

        params = {
            "obj_type": type_singular,
            "type_plural": type_plural,
            "obj_id": obj_id,
            "status": status_display,
        }

        answer = self._compute_l0_answer(tmpl, node, params)
        if answer is None:
            return None

        try:
            question = tmpl.template.format(**params)
        except KeyError:
            # 需要 comparison 参数但没有
            return self._try_fill_l0_comparison(tmpl, node, params)

        return GeneratedQA(
            question=question,
            answer=str(answer),
            template_id=tmpl.template_id,
            coverage_level="L0",
            question_type=tmpl.question_type,
            answer_type=tmpl.answer_type,
            covered_elements=[obj_id],
            params=params,
        )

    def _try_fill_l0_comparison(self, tmpl: TemplateEntry, node: Dict,
                                 base_params: Dict) -> Optional[GeneratedQA]:
        """处理 L0 comparison 模板"""
        if tmpl.question_type != "comparison":
            return None

        obj_type = node.get("type", "unknown")
        obj_id = node.get("unique_id", "")
        obj_status = node.get("status", "unknown")

        # 找另一个不同的对象进行比较
        other_nodes = [n for n in self.index.non_ego_nodes
                       if n.get("unique_id") != obj_id]
        if not other_nodes:
            return None

        other = random.choice(other_nodes)
        other_type = other.get("type", "unknown")
        other_id = other.get("unique_id", "")
        other_status = other.get("status", "unknown")

        type1_s, _ = self._get_type_names(obj_type)
        type2_s, _ = self._get_type_names(other_type)

        params = {
            **base_params,
            "obj1_type": type1_s,
            "obj1_id": obj_id,
            "obj2_type": type2_s,
            "obj2_id": other_id,
        }

        logic = tmpl.answer_logic
        if logic == "compare_type_two":
            same = (obj_type == other_type)
        else:
            same = (obj_status == other_status)
        answer = "yes" if same else "no"

        try:
            question = tmpl.template.format(**params)
        except KeyError:
            return None

        return GeneratedQA(
            question=question,
            answer=answer,
            template_id=tmpl.template_id,
            coverage_level="L0",
            question_type="comparison",
            answer_type="bool",
            covered_elements=[obj_id, other_id],
            params=params,
        )

    def _compute_l0_answer(self, tmpl: TemplateEntry, node: Dict,
                            params: Dict) -> Optional[str]:
        logic = tmpl.answer_logic
        obj_type = node.get("type", "unknown")
        status = node.get("status", "unknown")

        if logic == "exists_type":
            count = len(self.index.nodes_by_type.get(obj_type, []))
            return "yes" if count > 0 else "no"

        elif logic == "exists_status_type":
            count = len(self.index.nodes_by_type_status.get((obj_type, status), []))
            return "yes" if count > 0 else "no"

        elif logic == "exists_any":
            return "yes" if self.index.non_ego_nodes else "no"

        elif logic == "count_type":
            return str(len(self.index.nodes_by_type.get(obj_type, [])))

        elif logic == "count_status_type":
            return str(len(self.index.nodes_by_type_status.get((obj_type, status), [])))

        elif logic in ("node_status_by_type", "node_status_by_id"):
            return self._status_names.get(status, status)

        elif logic == "what_is_status_type":
            _, type_singular = self._get_type_names(obj_type)
            return obj_type

        elif logic == "what_is_status_thing":
            return obj_type

        elif logic in ("compare_status_two", "compare_type_two"):
            return None  # 需要额外处理

        # --- Heading-based (CV可见: 图片可见车头朝向) ---
        elif logic == "is_facing_ego":
            heading = node.get("heading_class", "unknown")
            return "yes" if heading == "facing_ego" else "no"

        elif logic == "is_facing_away":
            heading = node.get("heading_class", "unknown")
            return "yes" if heading == "away_from_ego" else "no"

        elif logic == "heading_of_id":
            heading = node.get("heading_class", "unknown")
            return heading.replace("_", " ")

        return None

    # ========================================================================
    #  L1 填充逻辑
    # ========================================================================

    def _try_fill_l1(self, tmpl: TemplateEntry, source_node: Dict, target_node: Dict,
                     direction: str, edge: Optional[Dict]) -> Optional[GeneratedQA]:
        src_type = source_node.get("type", "unknown")
        src_id = source_node.get("unique_id", "")
        src_status = source_node.get("status", "unknown")
        tgt_type = target_node.get("type", "unknown")
        tgt_id = target_node.get("unique_id", "")
        tgt_status = target_node.get("status", "unknown")

        tgt_singular, tgt_plural = self._get_type_names(tgt_type)
        src_singular, src_plural = self._get_type_names(src_type)
        src_status_display = self._status_names.get(src_status, src_status)
        tgt_status_display = self._status_names.get(tgt_status, tgt_status)

        params = {
            "obj_type": tgt_singular,
            "type_plural": tgt_plural,
            "obj_id": tgt_id,
            "status": tgt_status_display,
            "direction": direction,
            "ref_id": src_id,
            "ref_type": src_singular,
            "ref_status": src_status_display,
        }

        # 处理 ego 引用: 如果 source 是 ego, 模板里用 "me"
        is_ego_ref = (src_type == "ego")

        # 根据模板 major_pattern 判断是否匹配
        pattern = tmpl.major_pattern

        # ego方向模板只适用于 ego 做源
        if "ego_" in pattern and not is_ego_ref:
            return None
        # ref方向模板不适用于 ego (用 thereis 或 ref 模式)
        if "ref_" in pattern and is_ego_ref:
            return None

        # comparison 需要特殊处理
        if tmpl.question_type == "comparison":
            return self._try_fill_l1_comparison(tmpl, source_node, target_node, direction, params)

        answer = self._compute_l1_answer(tmpl, source_node, target_node, direction, params)
        if answer is None:
            return None

        try:
            question = tmpl.template.format(**params)
        except KeyError:
            return None

        covered = [src_id, tgt_id] if src_type != "ego" else [tgt_id]
        return GeneratedQA(
            question=question,
            answer=str(answer),
            template_id=tmpl.template_id,
            coverage_level="L1",
            question_type=tmpl.question_type,
            answer_type=tmpl.answer_type,
            covered_elements=covered,
            params=params,
        )

    def _try_fill_l1_comparison(self, tmpl: TemplateEntry, source_node: Dict,
                                 target_node: Dict, direction: str,
                                 base_params: Dict) -> Optional[GeneratedQA]:
        tgt_id = target_node.get("unique_id", "")
        tgt_status = target_node.get("status", "unknown")

        # 找另一个对象进行比较
        other_nodes = [n for n in self.index.non_ego_nodes
                       if n.get("unique_id") != tgt_id
                       and n.get("unique_id") != source_node.get("unique_id")]
        if not other_nodes:
            return None

        other = random.choice(other_nodes)
        other_type = other.get("type", "unknown")
        other_id = other.get("unique_id", "")
        other_status = other.get("status", "unknown")
        other_singular, _ = self._get_type_names(other_type)
        tgt_singular, _ = self._get_type_names(target_node.get("type", "unknown"))

        params = {
            **base_params,
            "obj1_type": tgt_singular,
            "obj1_id": tgt_id,
            "obj2_type": other_singular,
            "obj2_id": other_id,
        }

        same_status = (tgt_status == other_status)
        answer = "yes" if same_status else "no"

        try:
            question = tmpl.template.format(**params)
        except KeyError:
            return None

        return GeneratedQA(
            question=question,
            answer=answer,
            template_id=tmpl.template_id,
            coverage_level="L1",
            question_type="comparison",
            answer_type="bool",
            covered_elements=[tgt_id, other_id],
            params=params,
        )

    def _compute_l1_answer(self, tmpl: TemplateEntry, source_node: Dict,
                            target_node: Dict, direction: str,
                            params: Dict) -> Optional[str]:
        logic = tmpl.answer_logic
        src_id = source_node.get("unique_id", "")
        tgt_type = target_node.get("type", "unknown")
        tgt_status = target_node.get("status", "unknown")

        if logic in ("exists_direction_from_ego", "exists_direction_from_ref"):
            # 检查从 source 的 direction 方向是否有 tgt_type 类型的对象
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            matching = [t for t in targets if t.get("type") == tgt_type]
            return "yes" if matching else "no"

        elif logic == "exists_status_direction_from_ego":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            matching = [t for t in targets
                        if t.get("type") == tgt_type and t.get("status") == tgt_status]
            return "yes" if matching else "no"

        elif logic in ("exists_direction_from_status_ref",
                        "exists_status_direction_from_status_ref"):
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            if "status" in logic.split("_")[1:3]:
                matching = [t for t in targets
                            if t.get("type") == tgt_type and t.get("status") == tgt_status]
            else:
                matching = [t for t in targets if t.get("type") == tgt_type]
            return "yes" if matching else "no"

        elif logic == "exists_any_direction_from_ego":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            return "yes" if targets else "no"

        elif logic in ("count_direction_from_ego", "count_direction_from_status_ref"):
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            matching = [t for t in targets if t.get("type") == tgt_type]
            return str(len(matching))

        elif logic == "count_any_direction_from_ego":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            return str(len(targets))

        elif logic == "count_status_direction_from_ego":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            status = params.get("status", "")
            raw_status = self._reverse_status_display(status)
            matching = [t for t in targets
                        if t.get("type") == tgt_type and t.get("status") == raw_status]
            return str(len(matching))

        elif logic == "count_status_any_direction_from_ego":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            status = params.get("status", "")
            raw_status = self._reverse_status_display(status)
            matching = [t for t in targets if t.get("status") == raw_status]
            return str(len(matching))

        elif logic in ("status_direction_from_ego", "status_direction_from_status_ref",
                        "status_direction_from_ref"):
            return self._status_names.get(tgt_status, tgt_status)

        elif logic in ("what_direction_from_ego", "what_direction_from_status_ref",
                        "what_thing_direction_from_ego", "what_direction_from_ref"):
            return tgt_type

        elif logic == "count_direction_from_ref":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            matching = [t for t in targets if t.get("type") == tgt_type]
            return str(len(matching))

        elif logic == "exists_status_direction_from_ref":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            matching = [t for t in targets
                        if t.get("type") == tgt_type and t.get("status") == tgt_status]
            return "yes" if matching else "no"

        # --- Distance-based ---
        elif logic == "exists_within_distance":
            threshold = float(params.get("distance_threshold", 10))
            matching = [n for n in self.index.nodes_by_type.get(tgt_type, [])
                        if self._node_distance(n) <= threshold]
            return "yes" if matching else "no"

        elif logic == "exists_within_distance_direction":
            threshold = float(params.get("distance_threshold", 10))
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            matching = [t for t in targets
                        if t.get("type") == tgt_type and self._node_distance(t) <= threshold]
            return "yes" if matching else "no"

        elif logic == "count_within_distance":
            threshold = float(params.get("distance_threshold", 10))
            matching = [n for n in self.index.nodes_by_type.get(tgt_type, [])
                        if self._node_distance(n) <= threshold]
            return str(len(matching))

        elif logic == "count_within_distance_direction":
            threshold = float(params.get("distance_threshold", 10))
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            matching = [t for t in targets
                        if t.get("type") == tgt_type and self._node_distance(t) <= threshold]
            return str(len(matching))

        elif logic == "distance_to_nearest_type":
            nodes_of_type = self.index.nodes_by_type.get(tgt_type, [])
            if not nodes_of_type:
                return None
            dists = [(self._node_distance(n), n) for n in nodes_of_type]
            dists.sort(key=lambda x: x[0])
            return f"{dists[0][0]:.1f}"

        elif logic == "distance_to_obj_id":
            obj_id = params.get("obj_id", "")
            node = self.index.node_by_id.get(obj_id)
            if not node:
                return None
            return f"{self._node_distance(node):.1f}"

        elif logic == "nearest_of_type":
            nodes_of_type = self.index.nodes_by_type.get(tgt_type, [])
            if not nodes_of_type:
                return None
            dists = [(self._node_distance(n), n) for n in nodes_of_type]
            dists.sort(key=lambda x: x[0])
            return dists[0][1].get("unique_id", tgt_type)

        elif logic == "nearest_in_direction":
            targets = self.index.targets_by_direction.get(("ego", direction), [])
            if not targets:
                return None
            dists = [(self._node_distance(t), t) for t in targets]
            dists.sort(key=lambda x: x[0])
            return dists[0][1].get("unique_id", dists[0][1].get("type", "unknown"))

        elif logic == "farthest_of_type":
            nodes_of_type = self.index.nodes_by_type.get(tgt_type, [])
            if not nodes_of_type:
                return None
            dists = [(self._node_distance(n), n) for n in nodes_of_type]
            dists.sort(key=lambda x: -x[0])
            return dists[0][1].get("unique_id", tgt_type)

        # --- Velocity-based ---
        elif logic in ("speed_of_obj", "speed_of_type"):
            obj_id = params.get("obj_id", "")
            node = self.index.node_by_id.get(obj_id, target_node)
            return f"{self._node_speed(node):.1f}"

        elif logic == "fastest_of_type":
            nodes_of_type = self.index.nodes_by_type.get(tgt_type, [])
            if not nodes_of_type:
                return None
            speeds = [(self._node_speed(n), n) for n in nodes_of_type]
            speeds.sort(key=lambda x: -x[0])
            return speeds[0][1].get("unique_id", tgt_type)

        elif logic == "is_approaching_direction":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            matching = [t for t in targets if t.get("type") == tgt_type]
            if not matching:
                return None
            return "approaching" if self._is_approaching(matching[0]) else "moving away"

        elif logic == "is_approaching_id":
            obj_id = params.get("obj_id", "")
            node = self.index.node_by_id.get(obj_id, target_node)
            return "yes" if self._is_approaching(node) else "no"

        # --- Heading-based (CV可见) ---
        elif logic == "is_facing_ego_direction":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            tgt_type = target_node.get("type", "unknown")
            matching = [t for t in targets if t.get("type") == tgt_type]
            if not matching:
                return None
            heading = matching[0].get("heading_class", "unknown")
            return "yes" if heading == "facing_ego" else "no"

        elif logic == "is_facing_ego_ref_direction":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            tgt_type = target_node.get("type", "unknown")
            matching = [t for t in targets if t.get("type") == tgt_type]
            if not matching:
                return None
            heading = matching[0].get("heading_class", "unknown")
            return "yes" if heading == "facing_ego" else "no"

        elif logic == "heading_of_direction_obj":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            tgt_type = target_node.get("type", "unknown")
            matching = [t for t in targets if t.get("type") == tgt_type]
            if not matching:
                return None
            heading = matching[0].get("heading_class", "unknown")
            return heading.replace("_", " ")

        elif logic == "exists_facing_ego_in_direction":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            tgt_type = target_node.get("type", "unknown")
            matching = [t for t in targets
                        if t.get("type") == tgt_type
                        and t.get("heading_class") == "facing_ego"]
            return "yes" if matching else "no"

        elif logic == "exists_facing_away_in_direction":
            targets = self.index.targets_by_direction.get((src_id, direction), [])
            tgt_type = target_node.get("type", "unknown")
            matching = [t for t in targets
                        if t.get("type") == tgt_type
                        and t.get("heading_class") == "away_from_ego"]
            return "yes" if matching else "no"

        # --- Size-based ---
        elif logic == "largest_of_type":
            nodes_of_type = self.index.nodes_by_type.get(tgt_type, [])
            if not nodes_of_type:
                return None
            vols = [(self._node_volume(n), n) for n in nodes_of_type]
            vols.sort(key=lambda x: -x[0])
            return vols[0][1].get("unique_id", tgt_type)

        elif logic == "smallest_of_type":
            nodes_of_type = self.index.nodes_by_type.get(tgt_type, [])
            if not nodes_of_type:
                return None
            vols = [(self._node_volume(n), n) for n in nodes_of_type]
            vols.sort(key=lambda x: x[0])
            return vols[0][1].get("unique_id", tgt_type)

        return None

    # ========================================================================
    #  L2 填充逻辑
    # ========================================================================

    def _try_fill_l2(self, tmpl: TemplateEntry, n1: Dict, n2: Dict, n3: Dict,
                     e1: Optional[Dict], e2: Optional[Dict]) -> Optional[GeneratedQA]:
        d1 = self.index._get_direction_8(e1) if e1 else None
        d2 = self.index._get_direction_8(e2) if e2 else None

        n1_type = n1.get("type", "unknown")
        n2_type = n2.get("type", "unknown")
        n3_type = n3.get("type", "unknown")
        n1_id = n1.get("unique_id", "")
        n2_id = n2.get("unique_id", "")
        n3_id = n3.get("unique_id", "")
        n1_status = n1.get("status", "unknown")
        n2_status = n2.get("status", "unknown")
        n3_status = n3.get("status", "unknown")

        n1_s, n1_p = self._get_type_names(n1_type)
        n2_s, n2_p = self._get_type_names(n2_type)
        n3_s, n3_p = self._get_type_names(n3_type)

        params = {
            "ref_id": n1_id,
            "ref_type": n1_s,
            "ref_status": self._status_names.get(n1_status, n1_status),
            "mid_type": n2_s,
            "mid_id": n2_id,
            "mid_status": self._status_names.get(n2_status, n2_status),
            "target_type": n3_s,
            "target_id": n3_id,
            "target_status": self._status_names.get(n3_status, n3_status),
            "type_plural": n3_p,
            "obj_type": n3_s,
            "status": self._status_names.get(n3_status, n3_status),
            "direction1": d2 or "front",
            "direction2": d1 or "front",
            "ref1_id": n1_id,
            "ref2_id": n2_id,
            "ref1_type": n1_s,
            "ref2_type": n2_s,
            "ref1_status": self._status_names.get(n1_status, n1_status),
            "ref2_status": self._status_names.get(n2_status, n2_status),
            "direction": d1 or "front",
        }

        # comparison 特殊处理
        if tmpl.question_type == "comparison":
            return self._try_fill_l2_comparison(tmpl, n1, n2, n3, e1, e2, params)

        answer = self._compute_l2_answer(tmpl, n1, n2, n3, d1, d2, params)
        if answer is None:
            return None

        try:
            question = tmpl.template.format(**params)
        except KeyError:
            return None

        return GeneratedQA(
            question=question,
            answer=str(answer),
            template_id=tmpl.template_id,
            coverage_level="L2",
            question_type=tmpl.question_type,
            answer_type=tmpl.answer_type,
            covered_elements=[n1_id, n2_id, n3_id],
            params=params,
        )

    def _try_fill_l2_comparison(self, tmpl: TemplateEntry, n1: Dict, n2: Dict, n3: Dict,
                                 e1: Optional[Dict], e2: Optional[Dict],
                                 base_params: Dict) -> Optional[GeneratedQA]:
        logic = tmpl.answer_logic

        if logic == "compare_two_direction_refs":
            # 比较两个方向对象的状态
            n2_status = n2.get("status", "unknown")
            n3_status = n3.get("status", "unknown")
            same = (n2_status == n3_status)

            n2_s, _ = self._get_type_names(n2.get("type", "unknown"))
            n3_s, _ = self._get_type_names(n3.get("type", "unknown"))

            params = {
                **base_params,
                "obj1_type": n2_s,
                "obj1_id": n2.get("unique_id", ""),
                "obj2_type": n3_s,
                "obj2_id": n3.get("unique_id", ""),
            }

            try:
                question = tmpl.template.format(**params)
            except KeyError:
                return None

            return GeneratedQA(
                question=question,
                answer="yes" if same else "no",
                template_id=tmpl.template_id,
                coverage_level="L2",
                question_type="comparison",
                answer_type="bool",
                covered_elements=[n1.get("unique_id", ""),
                                  n2.get("unique_id", ""),
                                  n3.get("unique_id", "")],
                params=params,
            )

        elif logic == "compare_id_vs_direction_ref":
            n1_status = n1.get("status", "unknown")
            n3_status = n3.get("status", "unknown")
            same = (n1_status == n3_status)

            params = {
                **base_params,
                "obj1_id": n1.get("unique_id", ""),
                "obj2_type": self._get_type_names(n3.get("type", "unknown"))[0],
                "obj2_id": n3.get("unique_id", ""),
            }

            try:
                question = tmpl.template.format(**params)
            except KeyError:
                return None

            return GeneratedQA(
                question=question,
                answer="yes" if same else "no",
                template_id=tmpl.template_id,
                coverage_level="L2",
                question_type="comparison",
                answer_type="bool",
                covered_elements=[n1.get("unique_id", ""),
                                  n3.get("unique_id", "")],
                params=params,
            )

        return None

    def _compute_l2_answer(self, tmpl: TemplateEntry, n1: Dict, n2: Dict, n3: Dict,
                            d1: Optional[str], d2: Optional[str],
                            params: Dict) -> Optional[str]:
        logic = tmpl.answer_logic
        n2_type = n2.get("type", "unknown")
        n3_type = n3.get("type", "unknown")
        n2_id = n2.get("unique_id", "")
        n3_id = n3.get("unique_id", "")
        n1_id = n1.get("unique_id", "")
        n3_status = n3.get("status", "unknown")

        if logic == "exists_2hop_chain":
            # n1→(d1)→n2→(d2)→n3 是否存在
            return "yes"  # 路径已确认存在

        elif logic == "exists_same_status_another":
            ref_id = n1_id
            ref_status = n1.get("status", "unknown")
            ref_type = n1.get("type", "unknown")
            others = [n for n in self.index.nodes_by_type.get(ref_type, [])
                       if n.get("unique_id") != ref_id
                       and n.get("status") == ref_status]
            return "yes" if others else "no"

        elif logic == "exists_both_directions":
            return "yes"  # 双方向交集已确认存在

        elif logic == "count_same_status":
            ref_id = params.get("ref_id", n1_id)
            ref_node = self.index.node_by_id.get(ref_id, n1)
            ref_status = ref_node.get("status", "unknown")
            ref_type = ref_node.get("type", "unknown")
            obj_type_key = n3_type if n3_type != "unknown" else ref_type
            others = [n for n in self.index.nodes_by_type.get(obj_type_key, [])
                       if n.get("unique_id") != ref_id
                       and n.get("status") == ref_status]
            return str(len(others))

        elif logic == "count_same_status_any":
            ref_id = params.get("ref_id", n1_id)
            ref_node = self.index.node_by_id.get(ref_id, n1)
            ref_status = ref_node.get("status", "unknown")
            others = [n for n in self.index.non_ego_nodes
                       if n.get("unique_id") != ref_id
                       and n.get("status") == ref_status]
            return str(len(others))

        elif logic == "count_both_directions":
            return "1"  # 通常双方向交集只有一个

        elif logic == "status_2hop_chain":
            return self._status_names.get(n3_status, n3_status)

        elif logic == "what_2hop_chain":
            return n3_type

        elif logic in ("what_both_directions", "what_status_both_directions"):
            return n3_type

        # --- Cross-attribute: distance comparison ---
        elif logic == "compare_distance_two_ids":
            d1_val = self._node_distance(n1)
            d2_val = self._node_distance(n3)
            return "yes" if d1_val < d2_val else "no"

        elif logic == "compare_distance_two_ids_which":
            d1_val = self._node_distance(n1)
            d2_val = self._node_distance(n3)
            closer = n1 if d1_val <= d2_val else n3
            return closer.get("unique_id", "unknown")

        # --- Cross-attribute: speed comparison ---
        elif logic == "compare_speed_two_ids":
            s1 = self._node_speed(n1)
            s2 = self._node_speed(n3)
            return "yes" if s1 > s2 else "no"

        elif logic == "compare_speed_two_ids_which":
            s1 = self._node_speed(n1)
            s2 = self._node_speed(n3)
            faster = n1 if s1 >= s2 else n3
            return faster.get("unique_id", "unknown")

        # --- Cross-attribute: size comparison ---
        elif logic == "compare_size_two":
            v1 = self._node_volume(n1)
            v2 = self._node_volume(n3)
            return "yes" if v1 > v2 else "no"

        elif logic == "compare_size_two_which":
            v1 = self._node_volume(n1)
            v2 = self._node_volume(n3)
            bigger = n1 if v1 >= v2 else n3
            return bigger.get("unique_id", "unknown")

        # --- Cross-attribute: nearest status ---
        elif logic == "status_nearest_direction":
            d = params.get("direction", "front")
            obj_t = params.get("obj_type", "")
            targets = self.index.targets_by_direction.get(("ego", d), [])
            if obj_t:
                targets = [t for t in targets if t.get("type") == self._reverse_type_name(obj_t)]
            if not targets:
                return None
            dists = [(self._node_distance(t), t) for t in targets]
            dists.sort(key=lambda x: x[0])
            st = dists[0][1].get("status", "unknown")
            return self._status_names.get(st, st)

        elif logic == "status_of_nearest":
            obj_t = params.get("obj_type", "")
            raw_type = self._reverse_type_name(obj_t)
            nodes_of_type = self.index.nodes_by_type.get(raw_type, [])
            if not nodes_of_type:
                return None
            dists = [(self._node_distance(n), n) for n in nodes_of_type]
            dists.sort(key=lambda x: x[0])
            st = dists[0][1].get("status", "unknown")
            return self._status_names.get(st, st)

        elif logic == "compare_nearest_farthest_status":
            obj_t = params.get("obj_type", "")
            raw_type = self._reverse_type_name(obj_t)
            nodes_of_type = self.index.nodes_by_type.get(raw_type, [])
            if len(nodes_of_type) < 2:
                return None
            dists = [(self._node_distance(n), n) for n in nodes_of_type]
            dists.sort(key=lambda x: x[0])
            nearest_st = dists[0][1].get("status", "unknown")
            farthest_st = dists[-1][1].get("status", "unknown")
            return "yes" if nearest_st == farthest_st else "no"

        # --- Cross-attribute: approaching ---
        elif logic == "exists_approaching_direction":
            d = params.get("direction", "front")
            obj_t = params.get("obj_type", "")
            raw_type = self._reverse_type_name(obj_t)
            targets = self.index.targets_by_direction.get(("ego", d), [])
            matching = [t for t in targets
                        if t.get("type") == raw_type and self._is_approaching(t)]
            return "yes" if matching else "no"

        elif logic == "count_approaching":
            obj_t = params.get("obj_type", "")
            raw_type = self._reverse_type_name(obj_t)
            nodes_of_type = self.index.nodes_by_type.get(raw_type, [])
            approaching = [n for n in nodes_of_type if self._is_approaching(n)]
            return str(len(approaching))

        # --- Cross-attribute: distance + status ---
        elif logic == "count_status_within_distance":
            threshold = float(params.get("distance_threshold", 10))
            status = params.get("status", "")
            raw_status = self._reverse_status_display(status)
            obj_t = params.get("obj_type", "")
            raw_type = self._reverse_type_name(obj_t)
            nodes_of_type = self.index.nodes_by_type.get(raw_type, [])
            matching = [n for n in nodes_of_type
                        if n.get("status") == raw_status
                        and self._node_distance(n) <= threshold]
            return str(len(matching))

        # --- Chain + heading ---
        elif logic == "heading_2hop_chain":
            heading = n3.get("heading_class", "unknown")
            return "yes" if heading == "facing_ego" else "no"

        elif logic == "exists_2hop_chain_heading":
            # Check if target in chain is facing ego
            heading = n3.get("heading_class", "unknown")
            return "yes" if heading == "facing_ego" else "no"

        elif logic == "heading_2hop_chain_query":
            heading = n3.get("heading_class", "unknown")
            return heading.replace("_", " ")

        elif logic == "exists_2hop_chain_status":
            # Chain with status constraint on target
            required_status = params.get("status", "")
            raw_status = self._reverse_status_display(required_status)
            return "yes" if n3_status == raw_status else "no"

        elif logic == "status_both_directions":
            return self._status_names.get(n3_status, n3_status)

        elif logic in ("shared_status_same_type", "common_status_near_ref"):
            # Find shared status among same-type objects near ref
            ref_type = n1.get("type", "unknown")
            ref_status = n1.get("status", "unknown")
            return self._status_names.get(ref_status, ref_status)

        elif logic == "what_same_status_other":
            # Find another object with same status
            ref_id = n1.get("unique_id", "")
            ref_status = n1.get("status", "unknown")
            others = [n for n in self.index.non_ego_nodes
                       if n.get("unique_id") != ref_id
                       and n.get("status") == ref_status]
            if not others:
                return None
            return others[0].get("type", "unknown")

        # --- Cross-attribute: between ---
        elif logic == "exists_between_two":
            ref1 = self.index.node_by_id.get(params.get("ref1_id", ""))
            ref2 = self.index.node_by_id.get(params.get("ref2_id", ""))
            obj_t = params.get("obj_type", "")
            raw_type = self._reverse_type_name(obj_t)
            if not ref1 or not ref2:
                return None
            x1, y1, _ = self._get_xyz(ref1.get("translation"))
            x2, y2, _ = self._get_xyz(ref2.get("translation"))
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            half_dist = ((x1-x2)**2 + (y1-y2)**2) ** 0.5 / 2
            if half_dist < 0.1:
                return "no"
            nodes_of_type = self.index.nodes_by_type.get(raw_type, [])
            for n in nodes_of_type:
                nx, ny, _ = self._get_xyz(n.get("translation"))
                d_to_mid = ((nx-mid_x)**2 + (ny-mid_y)**2) ** 0.5
                if d_to_mid <= half_dist:
                    return "yes"
            return "no"

        return None

    # ========================================================================
    #  工具方法
    # ========================================================================

    def _get_type_names(self, obj_type: str) -> Tuple[str, str]:
        if obj_type in self._type_names:
            return self._type_names[obj_type]
        return (obj_type, obj_type + "s")

    # ========================================================================
    #  距离 / 速度 / 尺寸 计算工具
    # ========================================================================

    @staticmethod
    def _get_xyz(t) -> Tuple[float, float, float]:
        """从 dict {'x':..,'y':..} 或 list [x,y,z] 提取坐标"""
        if isinstance(t, dict):
            return (float(t.get('x', 0)), float(t.get('y', 0)), float(t.get('z', 0)))
        if isinstance(t, (list, tuple)) and len(t) >= 2:
            return (float(t[0]), float(t[1]), float(t[2]) if len(t) > 2 else 0.0)
        return (0.0, 0.0, 0.0)

    def _node_distance(self, node: Dict) -> float:
        """节点到 ego 的距离"""
        tx, ty, _ = self._get_xyz(node.get("translation"))
        ego = self.index.node_by_id.get("ego", {})
        ex, ey, _ = self._get_xyz(ego.get("translation"))
        dx = tx - ex
        dy = ty - ey
        return (dx * dx + dy * dy) ** 0.5

    def _edge_distance(self, src_id: str, tgt_id: str) -> Optional[float]:
        """两节点之间的距离 (从边 metrics)"""
        edge = self.index.get_edge_between(src_id, tgt_id)
        if edge:
            m = edge.get("metrics", {})
            if "distance" in m:
                return float(m["distance"])
        # fallback: 用坐标
        n1 = self.index.node_by_id.get(src_id)
        n2 = self.index.node_by_id.get(tgt_id)
        if n1 and n2:
            x1, y1, _ = self._get_xyz(n1.get("translation"))
            x2, y2, _ = self._get_xyz(n2.get("translation"))
            return ((x1-x2)**2 + (y1-y2)**2) ** 0.5
        return None

    def _node_speed(self, node: Dict) -> float:
        """节点速度标量"""
        v = node.get("velocity", [0, 0, 0])
        vx, vy, _ = self._get_xyz(v)
        return (vx**2 + vy**2) ** 0.5

    def _node_volume(self, node: Dict) -> float:
        """节点体积 (w*l*h)"""
        s = node.get("size", [1, 1, 1])
        sx, sy, sz = self._get_xyz(s)
        vol = abs(sx * sy * sz)
        return vol if vol > 0 else 1.0

    def _is_approaching(self, node: Dict) -> bool:
        """判断节点是否正在接近 ego"""
        vx, vy, _ = self._get_xyz(node.get("velocity", [0, 0, 0]))
        tx, ty, _ = self._get_xyz(node.get("translation", [0, 0, 0]))
        ego = self.index.node_by_id.get("ego", {})
        ex, ey, _ = self._get_xyz(ego.get("translation", [0, 0, 0]))
        dx = ex - tx
        dy = ey - ty
        # 速度在指向 ego 方向上的投影 > 0 → 接近
        dot = vx * dx + vy * dy
        return dot > 0

    def _reverse_status_display(self, display_status: str) -> str:
        for raw, display in self._status_names.items():
            if display == display_status:
                return raw
        return display_status

    def _reverse_type_name(self, display_name: str) -> str:
        """将显示名称 (如 'traffic cone') 转回原始类型键 (如 'traffic_cone')"""
        for raw, (singular, plural) in self._type_names.items():
            if display_name in (singular, plural, raw):
                return raw
        return display_name

    # ========================================================================
    #  缺口提取工具
    # ========================================================================

    def extract_gaps_from_coverage(self, coverage_stats) -> List[Dict]:
        """
        从 UnifiedCoverageStats 提取缺口列表

        Args:
            coverage_stats: UnifiedCoverageStats 或兼容的 dict

        Returns:
            缺口列表，格式与 generate_batch 接口兼容
        """
        gaps = []

        # L0: 未覆盖的节点
        covered_nodes = set()
        if hasattr(coverage_stats, 'covered_nodes'):
            covered_nodes = coverage_stats.covered_nodes
        elif isinstance(coverage_stats, dict):
            covered_nodes = set(coverage_stats.get('covered_nodes', []))

        for node in self.index.non_ego_nodes:
            nid = node.get("unique_id", "")
            if nid and nid not in covered_nodes:
                gaps.append({"level": "L0", "node_id": nid})

        # L1: 未覆盖的边
        covered_edges = set()
        if hasattr(coverage_stats, 'covered_edges'):
            covered_edges = coverage_stats.covered_edges
        elif isinstance(coverage_stats, dict):
            raw_edges = coverage_stats.get('covered_edges', [])
            covered_edges = set(tuple(e) if isinstance(e, list) else e for e in raw_edges)

        for edge in self.index.edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            d8 = self.index._get_direction_8(edge)
            if d8:
                edge_key = (src, d8, tgt)
                if edge_key not in covered_edges:
                    gaps.append({
                        "level": "L1",
                        "source": src,
                        "target": tgt,
                        "direction": d8,
                    })

        # L2: 未覆盖的两跳路径
        covered_paths = set()
        if hasattr(coverage_stats, 'covered_2hop_paths'):
            covered_paths = coverage_stats.covered_2hop_paths
        elif isinstance(coverage_stats, dict):
            raw_paths = coverage_stats.get('covered_2hop_paths', [])
            covered_paths = set(tuple(p) if isinstance(p, list) else p for p in raw_paths)

        for edge1 in self.index.edges:
            mid_id = edge1.get("target", "")
            for edge2, tgt_node in self.index.edges_from.get(mid_id, []):
                src_id = edge1.get("source", "")
                tgt_id = tgt_node.get("unique_id", "")
                path_key = (src_id, mid_id, tgt_id)
                if path_key not in covered_paths:
                    gaps.append({
                        "level": "L2",
                        "node1": src_id,
                        "node2": mid_id,
                        "node3": tgt_id,
                    })

        logger.info(f"提取缺口: L0={sum(1 for g in gaps if g['level']=='L0')}, "
                    f"L1={sum(1 for g in gaps if g['level']=='L1')}, "
                    f"L2={sum(1 for g in gaps if g['level']=='L2')}")
        return gaps
