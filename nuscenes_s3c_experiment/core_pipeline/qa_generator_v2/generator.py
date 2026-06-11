"""
Unified QA Generator - 统一问答生成器
支持L0/L1/L2三个难度级别的问题生成
"""
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass, field, asdict
import random
import json

try:
    from .templates import TemplateManager, QATemplate, OptionGenerator
    from .camera_mapper import CameraMapper
    from .config import OBJECT_TYPES, TYPE_NAMES, DIRECTIONS_8, DIRECTIONS_4, QA_CONFIG
    from .generator_L0 import QAPair, SceneGraphParser, L0QuestionGenerator
except ImportError:
    from templates import TemplateManager, QATemplate, OptionGenerator
    from camera_mapper import CameraMapper
    from config import OBJECT_TYPES, TYPE_NAMES, DIRECTIONS_8, DIRECTIONS_4, QA_CONFIG
    from generator_L0 import QAPair, SceneGraphParser, L0QuestionGenerator


class SceneGraphWithEdges(SceneGraphParser):
    """扩展的场景图解析器 - 支持边（空间关系）"""
    
    def __init__(self, scene_data: Dict):
        super().__init__(scene_data)
        
        # 解析边（空间关系）
        edges_data = scene_data.get("edges") or scene_data.get("relationships", [])
        self.edges: List[Dict] = edges_data
        
        # 构建邻接表（基于Source Frame）
        # adjacency[source_id][direction] = [target_ids]
        self.adjacency: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
        self.edge_map: Dict[Tuple[str, str], Dict] = {}
        
        for edge in self.edges:
            src = edge["source"]
            tgt = edge["target"]
            self.edge_map[(src, tgt)] = edge
            
            # 获取Source Frame方向
            direction = self._get_direction_source(edge)
            if direction:
                self.adjacency[src][direction].append(tgt)
                
                # 同时记录宽松匹配的方向（如果有）
                angle_matches = self._get_angle_matches_source(edge)
                for dir_match in angle_matches:
                    if dir_match != direction and dir_match in DIRECTIONS_8:
                        self.adjacency[src][dir_match].append(tgt)
    
    def _get_direction_source(self, edge: Dict) -> Optional[str]:
        """获取边的Source Frame方向（8方向）"""
        # 优先从metrics中获取
        metrics = edge.get("metrics", {})
        direction_source = metrics.get("direction_source", {})
        if isinstance(direction_source, dict):
            dir_8 = direction_source.get("direction_8")
            if dir_8:
                return dir_8
        
        # 备用：直接从边属性获取
        return edge.get("direction_8_source") or edge.get("direction_8")
    
    def _get_angle_matches_source(self, edge: Dict) -> List[str]:
        """获取边的所有可能方向匹配（宽松匹配）"""
        metrics = edge.get("metrics", {})
        direction_source = metrics.get("direction_source", {})
        if isinstance(direction_source, dict):
            matches = direction_source.get("angle_matches", [])
            if matches:
                return matches
        
        # 备用
        return edge.get("angle_matches_source", [])
    
    def get_objects_in_direction(self, ref_id: str, direction: str,
                                  obj_type: Optional[str] = None,
                                  status: Optional[str] = None) -> List[str]:
        """
        获取某对象某方向的其他对象（基于Source Frame）
        
        Args:
            ref_id: 参考对象ID
            direction: 方向（基于ref对象的朝向）
            obj_type: 可选的类型过滤
            status: 可选的状态过滤
        """
        targets = self.adjacency[ref_id].get(direction, [])
        
        result = []
        for tgt in targets:
            node = self.nodes.get(tgt)
            if not node:
                continue
            if obj_type and node["type"] != obj_type:
                continue
            if status and node.get("status") != status:
                continue
            result.append(tgt)
        
        return result
    
    def get_edge(self, source: str, target: str) -> Optional[Dict]:
        """获取边"""
        return self.edge_map.get((source, target))


class L1QuestionGenerator:
    """
    L1问题生成器
    
    生成单跳空间关系查询问题（涉及一个方向关系）
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or QA_CONFIG
        self.template_manager = TemplateManager()
        self._question_counter = 0
    
    def generate(self, scene_data: Dict, parser: SceneGraphWithEdges,
                 camera_mapper: CameraMapper, start_counter: int = 0) -> List[QAPair]:
        """
        从场景图生成L1问答对
        
        Args:
            scene_data: 场景图JSON数据
            parser: 扩展的场景图解析器
            camera_mapper: 相机映射器
            start_counter: 起始问题编号
        
        Returns:
            QAPair列表
        """
        self._question_counter = start_counter
        
        qa_pairs = []
        
        # 选择使用8方向还是4方向
        directions = DIRECTIONS_8 if self.config.get("use_8_directions", True) else DIRECTIONS_4
        
        # 生成各类型问题
        qa_pairs.extend(self._generate_exist_direction_questions(parser, camera_mapper, directions))
        qa_pairs.extend(self._generate_count_direction_questions(parser, camera_mapper, directions))
        qa_pairs.extend(self._generate_status_direction_questions(parser, camera_mapper, directions))
        qa_pairs.extend(self._generate_object_direction_questions(parser, camera_mapper, directions))
        qa_pairs.extend(self._generate_comparison_questions(parser, camera_mapper))
        
        # 为每个问答对生成选项
        for qa in qa_pairs:
            scene_context = {
                "object_types": list(parser.object_types_present)
            }
            qa.with_options = OptionGenerator.generate_options(
                qa.answer,
                qa.answer_type,
                scene_context,
                self.config.get("num_options", 4)
            )
        
        return qa_pairs
    
    def _make_question_id(self, parser: SceneGraphWithEdges) -> str:
        """生成问题ID"""
        self._question_counter += 1
        return f"{parser.scene_name}_frame{parser.frame_idx}_q{self._question_counter:04d}"
    
    def _create_qa_pair(self, parser: SceneGraphWithEdges, template: QATemplate,
                       question: str, answer: str,
                       target_objects: List[str] = None,
                       reference_objects: List[str] = None,
                       directions: List[str] = None,
                       cameras: List[str] = None,
                       metadata: Dict = None) -> QAPair:
        """创建QAPair对象"""
        return QAPair(
            question_id=self._make_question_id(parser),
            scene_name=parser.scene_name,
            frame_idx=parser.frame_idx,
            sample_token=parser.sample_token,
            question_type=template.question_type,
            template_id=template.template_id,
            difficulty=template.difficulty,
            target_objects=target_objects or [],
            reference_objects=reference_objects or [],
            directions_used=directions or [],
            question=question,
            answer=answer,
            answer_type=template.answer_type,
            requires_temporal=template.requires_temporal,
            cameras_for_analysis=cameras or [],
            metadata=metadata or {},
        )
    
    def _generate_exist_direction_questions(self, parser: SceneGraphWithEdges,
                                           camera_mapper: CameraMapper,
                                           directions: List[str]) -> List[QAPair]:
        """生成方向存在性问题"""
        qa_pairs = []
        template = self.template_manager.get_template("L1_exist_direction")
        
        # 采样参考对象（避免太多）
        ref_candidates = [uid for uid in parser.nodes if uid != "ego"]
        sampled_refs = random.sample(ref_candidates, min(10, len(ref_candidates)))
        
        for ref_id in sampled_refs:
            ref_node = parser.get_node(ref_id)
            
            for direction in directions:
                # 采样对象类型
                for obj_type in random.sample(OBJECT_TYPES, min(3, len(OBJECT_TYPES))):
                    targets = parser.get_objects_in_direction(ref_id, direction, obj_type=obj_type)
                    
                    # 50%概率也问不存在的
                    if not targets and random.random() > 0.5:
                        continue
                    
                    singular, plural = TYPE_NAMES.get(obj_type, (obj_type, obj_type + "s"))
                    question = self.template_manager.fill_template(
                        template,
                        type_plural=plural,
                        direction=direction,
                        ref_id=ref_id
                    )
                    answer = "yes" if targets else "no"
                    
                    cameras = set(camera_mapper.get_object_cameras(ref_id))
                    for tgt in targets[:5]:
                        cameras.update(camera_mapper.get_object_cameras(tgt))
                    
                    qa = self._create_qa_pair(
                        parser, template, question, answer,
                        target_objects=targets[:10],
                        reference_objects=[ref_id],
                        directions=[direction],
                        cameras=list(cameras),
                        metadata={"ref_type": ref_node["type"], "obj_type": obj_type, "direction": direction}
                    )
                    qa_pairs.append(qa)
        
        return qa_pairs
    
    def _generate_count_direction_questions(self, parser: SceneGraphWithEdges,
                                           camera_mapper: CameraMapper,
                                           directions: List[str]) -> List[QAPair]:
        """生成方向计数问题"""
        qa_pairs = []
        template = self.template_manager.get_template("L1_count_direction")
        
        ref_candidates = [uid for uid in parser.nodes if uid != "ego"]
        sampled_refs = random.sample(ref_candidates, min(5, len(ref_candidates)))
        
        for ref_id in sampled_refs:
            ref_node = parser.get_node(ref_id)
            
            for direction in random.sample(directions, min(2, len(directions))):
                for obj_type in random.sample(OBJECT_TYPES, min(2, len(OBJECT_TYPES))):
                    targets = parser.get_objects_in_direction(ref_id, direction, obj_type=obj_type)
                    
                    if len(targets) == 0:
                        continue
                    
                    singular, plural = TYPE_NAMES.get(obj_type, (obj_type, obj_type + "s"))
                    question = self.template_manager.fill_template(
                        template,
                        type_plural=plural,
                        direction=direction,
                        ref_id=ref_id
                    )
                    answer = str(min(len(targets), 10))
                    
                    cameras = set(camera_mapper.get_object_cameras(ref_id))
                    for tgt in targets[:5]:
                        cameras.update(camera_mapper.get_object_cameras(tgt))
                    
                    qa = self._create_qa_pair(
                        parser, template, question, answer,
                        target_objects=targets,
                        reference_objects=[ref_id],
                        directions=[direction],
                        cameras=list(cameras),
                        metadata={"ref_type": ref_node["type"], "obj_type": obj_type, "direction": direction, "actual_count": len(targets)}
                    )
                    qa_pairs.append(qa)
        
        return qa_pairs
    
    def _generate_status_direction_questions(self, parser: SceneGraphWithEdges,
                                            camera_mapper: CameraMapper,
                                            directions: List[str]) -> List[QAPair]:
        """生成方向状态查询问题"""
        qa_pairs = []
        template = self.template_manager.get_template("L1_status_direction")
        
        ref_candidates = [uid for uid in parser.nodes if uid != "ego"]
        sampled_refs = random.sample(ref_candidates, min(5, len(ref_candidates)))
        
        for ref_id in sampled_refs:
            for direction in random.sample(directions, min(2, len(directions))):
                for obj_type in random.sample(OBJECT_TYPES, min(2, len(OBJECT_TYPES))):
                    targets = parser.get_objects_in_direction(ref_id, direction, obj_type=obj_type)
                    
                    # 只在唯一目标时生成（否则答案不明确）
                    if len(targets) != 1:
                        continue
                    
                    target_id = targets[0]
                    target_node = parser.get_node(target_id)
                    status = target_node.get("status")
                    
                    if not status or status == "unknown":
                        continue
                    
                    singular, _ = TYPE_NAMES.get(obj_type, (obj_type, obj_type))
                    question = self.template_manager.fill_template(
                        template,
                        target_type=singular,
                        direction=direction,
                        ref_id=ref_id
                    )
                    answer = status
                    
                    cameras = set(camera_mapper.get_object_cameras(ref_id))
                    cameras.update(camera_mapper.get_object_cameras(target_id))
                    
                    qa = self._create_qa_pair(
                        parser, template, question, answer,
                        target_objects=[target_id],
                        reference_objects=[ref_id],
                        directions=[direction],
                        cameras=list(cameras),
                        metadata={"target_type": obj_type, "ref_type": parser.get_node(ref_id)["type"], "direction": direction}
                    )
                    qa_pairs.append(qa)
        
        return qa_pairs
    
    def _generate_object_direction_questions(self, parser: SceneGraphWithEdges,
                                            camera_mapper: CameraMapper,
                                            directions: List[str]) -> List[QAPair]:
        """生成方向对象查询问题"""
        qa_pairs = []
        template = self.template_manager.get_template("L1_object_direction")
        
        ref_candidates = [uid for uid in parser.nodes if uid != "ego"]
        sampled_refs = random.sample(ref_candidates, min(5, len(ref_candidates)))
        
        for ref_id in sampled_refs:
            for direction in random.sample(directions, min(2, len(directions))):
                for status in parser.statuses_present:
                    targets = parser.get_objects_in_direction(ref_id, direction, status=status)
                    
                    if len(targets) != 1:
                        continue
                    
                    target_id = targets[0]
                    target_node = parser.get_node(target_id)
                    obj_type = target_node["type"]
                    
                    singular, _ = TYPE_NAMES.get(obj_type, (obj_type, obj_type))
                    question = self.template_manager.fill_template(
                        template,
                        status=status,
                        direction=direction,
                        ref_id=ref_id
                    )
                    answer = singular
                    
                    cameras = set(camera_mapper.get_object_cameras(ref_id))
                    cameras.update(camera_mapper.get_object_cameras(target_id))
                    
                    qa = self._create_qa_pair(
                        parser, template, question, answer,
                        target_objects=[target_id],
                        reference_objects=[ref_id],
                        directions=[direction],
                        cameras=list(cameras),
                        metadata={"status": status, "ref_type": parser.get_node(ref_id)["type"], "direction": direction}
                    )
                    qa_pairs.append(qa)
        
        return qa_pairs
    
    def _generate_comparison_questions(self, parser: SceneGraphWithEdges,
                                       camera_mapper: CameraMapper) -> List[QAPair]:
        """生成比较问题 - L1比较涉及方向关系"""
        qa_pairs = []
        
        # 获取L1比较模板
        comparison_templates = self.template_manager.get_templates(
            question_type="comparison",
            difficulty="L1"
        )
        
        if not comparison_templates:
            return qa_pairs
        
        # 生成L1_compare_direction类型的问题:
        # "There is a {type1} to the {direction} of {ref_id}; does it have the same status as {obj2_id}?"
        template = self.template_manager.get_template("L1_compare_direction")
        if not template:
            template = comparison_templates[0]  # 备用
        
        # 采样一些具有方向关系的对象对
        nodes_with_status = [uid for uid, node in parser.nodes.items()
                            if uid != "ego" and node.get("status") and node.get("status") != "unknown"]
        
        if len(nodes_with_status) < 2:
            return qa_pairs
        
        # 从边中采样
        sampled_edges = random.sample(parser.edges, min(5, len(parser.edges)))
        
        for edge in sampled_edges:
            src_id = edge["source"]
            tgt_id = edge["target"]
            
            if src_id == "ego" or tgt_id == "ego":
                continue
            
            src_node = parser.get_node(src_id)
            tgt_node = parser.get_node(tgt_id)
            
            if not src_node or not tgt_node:
                continue
            
            if not src_node.get("status") or not tgt_node.get("status"):
                continue
            
            # 获取方向
            direction = self._get_direction_from_edge(edge)
            if not direction:
                continue
            
            # 随机选择另一个对象进行比较
            other_objs = [uid for uid in nodes_with_status if uid not in [src_id, tgt_id]]
            if not other_objs:
                continue
            
            obj2_id = random.choice(other_objs)
            obj2_node = parser.get_node(obj2_id)
            
            type1_singular, _ = TYPE_NAMES.get(tgt_node["type"], (tgt_node["type"], tgt_node["type"]))
            
            question = self.template_manager.fill_template(
                template,
                type1=type1_singular,
                direction=direction,
                ref_id=src_id,
                obj2_id=obj2_id
            )
            
            answer = "yes" if tgt_node["status"] == obj2_node["status"] else "no"
            
            cameras = set(camera_mapper.get_object_cameras(src_id))
            cameras.update(camera_mapper.get_object_cameras(tgt_id))
            cameras.update(camera_mapper.get_object_cameras(obj2_id))
            
            qa = self._create_qa_pair(
                parser, template, question, answer,
                target_objects=[tgt_id, obj2_id],
                reference_objects=[src_id],
                directions=[direction],
                cameras=list(cameras),
                metadata={
                    "obj1_type": tgt_node["type"], 
                    "obj2_type": obj2_node["type"],
                    "ref_type": src_node["type"],
                    "obj1_status": tgt_node["status"], 
                    "obj2_status": obj2_node["status"],
                    "direction": direction
                }
            )
            qa_pairs.append(qa)
        
        return qa_pairs
    
    def _get_direction_from_edge(self, edge: Dict) -> Optional[str]:
        """从边获取Source Frame方向"""
        metrics = edge.get("metrics", {})
        direction_source = metrics.get("direction_source", {})
        if isinstance(direction_source, dict):
            dir_8 = direction_source.get("direction_8")
            if dir_8:
                return dir_8
        return edge.get("direction_8_source") or edge.get("direction_8")


class L2QuestionGenerator:
    """
    L2问题生成器
    
    生成两跳空间关系查询问题（涉及链式或复合方向关系）
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or QA_CONFIG
        self.template_manager = TemplateManager()
        self._question_counter = 0
    
    def generate(self, scene_data: Dict, parser: SceneGraphWithEdges,
                 camera_mapper: CameraMapper, start_counter: int = 0) -> List[QAPair]:
        """从场景图生成L2问答对"""
        self._question_counter = start_counter
        
        qa_pairs = []
        directions = DIRECTIONS_8 if self.config.get("use_8_directions", True) else DIRECTIONS_4
        
        # 生成各类型问题
        qa_pairs.extend(self._generate_count_same_status_questions(parser, camera_mapper))
        qa_pairs.extend(self._generate_exist_same_status_questions(parser, camera_mapper))
        qa_pairs.extend(self._generate_two_directions_questions(parser, camera_mapper, directions))
        qa_pairs.extend(self._generate_chain_questions(parser, camera_mapper, directions))
        qa_pairs.extend(self._generate_compare_chain_questions(parser, camera_mapper, directions))
        qa_pairs.extend(self._generate_compare_two_chains_questions(parser, camera_mapper, directions))
        
        # 为每个问答对生成选项
        for qa in qa_pairs:
            scene_context = {
                "object_types": list(parser.object_types_present)
            }
            qa.with_options = OptionGenerator.generate_options(
                qa.answer,
                qa.answer_type,
                scene_context,
                self.config.get("num_options", 4)
            )
        
        return qa_pairs
    
    def _make_question_id(self, parser: SceneGraphWithEdges) -> str:
        """生成问题ID"""
        self._question_counter += 1
        return f"{parser.scene_name}_frame{parser.frame_idx}_q{self._question_counter:04d}"
    
    def _create_qa_pair(self, parser: SceneGraphWithEdges, template: QATemplate,
                       question: str, answer: str,
                       target_objects: List[str] = None,
                       reference_objects: List[str] = None,
                       directions: List[str] = None,
                       cameras: List[str] = None,
                       metadata: Dict = None) -> QAPair:
        """创建QAPair对象"""
        return QAPair(
            question_id=self._make_question_id(parser),
            scene_name=parser.scene_name,
            frame_idx=parser.frame_idx,
            sample_token=parser.sample_token,
            question_type=template.question_type,
            template_id=template.template_id,
            difficulty=template.difficulty,
            target_objects=target_objects or [],
            reference_objects=reference_objects or [],
            directions_used=directions or [],
            question=question,
            answer=answer,
            answer_type=template.answer_type,
            requires_temporal=template.requires_temporal,
            cameras_for_analysis=cameras or [],
            metadata=metadata or {},
        )
    
    def _generate_count_same_status_questions(self, parser: SceneGraphWithEdges,
                                             camera_mapper: CameraMapper) -> List[QAPair]:
        """生成同状态计数问题"""
        qa_pairs = []
        template = self.template_manager.get_template("L2_count_same_status")
        
        # 采样对象
        nodes_with_status = [uid for uid, node in parser.nodes.items()
                            if uid != "ego" and node.get("status") and node.get("status") != "unknown"]
        
        sampled = random.sample(nodes_with_status, min(5, len(nodes_with_status)))
        
        for ref_id in sampled:
            ref_node = parser.get_node(ref_id)
            ref_status = ref_node["status"]
            
            # 统计其他相同状态的对象
            same_status_objects = [uid for uid in parser.nodes
                                  if uid != "ego" and uid != ref_id
                                  and parser.nodes[uid].get("status") == ref_status]
            
            question = self.template_manager.fill_template(template, ref_id=ref_id)
            answer = str(min(len(same_status_objects), 10))
            
            cameras = set(camera_mapper.get_object_cameras(ref_id))
            for obj in same_status_objects[:5]:
                cameras.update(camera_mapper.get_object_cameras(obj))
            
            qa = self._create_qa_pair(
                parser, template, question, answer,
                target_objects=same_status_objects,
                reference_objects=[ref_id],
                cameras=list(cameras),
                metadata={"ref_type": ref_node["type"], "status": ref_status, "actual_count": len(same_status_objects)}
            )
            qa_pairs.append(qa)
        
        return qa_pairs
    
    def _generate_compare_chain_questions(self, parser: SceneGraphWithEdges,
                                         camera_mapper: CameraMapper,
                                         directions: List[str]) -> List[QAPair]:
        """生成链式比较问题"""
        qa_pairs = []
        template = self.template_manager.get_template("L2_compare_chain")
        
        # 采样参考对象
        ref_candidates = [uid for uid in parser.nodes if uid != "ego"]
        sampled_refs = random.sample(ref_candidates, min(3, len(ref_candidates)))
        
        for ref_id in sampled_refs:
            for direction in random.sample(directions, min(1, len(directions))):
                for obj_type in random.sample(OBJECT_TYPES, min(2, len(OBJECT_TYPES))):
                    targets = parser.get_objects_in_direction(ref_id, direction, obj_type=obj_type)
                    
                    if len(targets) != 1:
                        continue
                    
                    target_id = targets[0]
                    target_node = parser.get_node(target_id)
                    target_status = target_node.get("status")
                    
                    if not target_status or target_status == "unknown":
                        continue
                    
                    # 找另一个对象比较
                    comparison_candidates = [uid for uid in parser.nodes
                                           if uid != "ego" and uid != ref_id and uid != target_id
                                           and parser.nodes[uid].get("status") and parser.nodes[uid].get("status") != "unknown"]
                    
                    if not comparison_candidates:
                        continue
                    
                    obj1_id = random.choice(comparison_candidates)
                    obj1_node = parser.get_node(obj1_id)
                    
                    singular, _ = TYPE_NAMES.get(obj_type, (obj_type, obj_type))
                    question = self.template_manager.fill_template(
                        template,
                        obj1_id=obj1_id,
                        obj2_type=singular,
                        direction=direction,
                        ref_id=ref_id
                    )
                    answer = "yes" if obj1_node["status"] == target_status else "no"
                    
                    cameras = set(camera_mapper.get_object_cameras(ref_id))
                    cameras.update(camera_mapper.get_object_cameras(target_id))
                    cameras.update(camera_mapper.get_object_cameras(obj1_id))
                    
                    qa = self._create_qa_pair(
                        parser, template, question, answer,
                        target_objects=[obj1_id, target_id],
                        reference_objects=[ref_id],
                        directions=[direction],
                        cameras=list(cameras),
                        metadata={
                            "obj1_type": obj1_node["type"],
                            "obj2_type": obj_type,
                            "ref_type": parser.get_node(ref_id)["type"],
                            "direction": direction,
                            "obj1_status": obj1_node["status"],
                            "obj2_status": target_status
                        }
                    )
                    qa_pairs.append(qa)
        
        return qa_pairs
    
    def _generate_exist_same_status_questions(self, parser: SceneGraphWithEdges,
                                             camera_mapper: CameraMapper) -> List[QAPair]:
        """生成同状态存在性问题"""
        qa_pairs = []
        template = self.template_manager.get_template("L2_exist_same_status")
        
        nodes_with_status = [uid for uid, node in parser.nodes.items()
                            if uid != "ego" and node.get("status") and node.get("status") != "unknown"]
        
        sampled = random.sample(nodes_with_status, min(3, len(nodes_with_status)))
        
        for ref_id in sampled:
            ref_node = parser.get_node(ref_id)
            ref_type = ref_node["type"]
            ref_status = ref_node["status"]
            
            # 统计其他同类型同状态的对象
            same_objects = [uid for uid in parser.nodes
                           if uid != "ego" and uid != ref_id
                           and parser.nodes[uid].get("type") == ref_type
                           and parser.nodes[uid].get("status") == ref_status]
            
            singular, plural = TYPE_NAMES.get(ref_type, (ref_type, ref_type + "s"))
            question = self.template_manager.fill_template(
                template,
                ref_type=singular,
                ref_id=ref_id
            )
            answer = "yes" if same_objects else "no"
            
            cameras = set(camera_mapper.get_object_cameras(ref_id))
            for obj in same_objects[:5]:
                cameras.update(camera_mapper.get_object_cameras(obj))
            
            qa = self._create_qa_pair(
                parser, template, question, answer,
                target_objects=same_objects,
                reference_objects=[ref_id],
                cameras=list(cameras),
                metadata={"ref_type": ref_type, "status": ref_status}
            )
            qa_pairs.append(qa)
        
        return qa_pairs
    
    def _generate_two_directions_questions(self, parser: SceneGraphWithEdges,
                                          camera_mapper: CameraMapper,
                                          directions: List[str]) -> List[QAPair]:
        """生成复合方向问题（两个方位交集）"""
        qa_pairs = []
        
        # 随机采样两个参考对象
        ref_candidates = [uid for uid in parser.nodes if uid != "ego"]
        if len(ref_candidates) < 2:
            return qa_pairs
        
        sampled_pairs = []
        for _ in range(min(3, len(ref_candidates) * (len(ref_candidates) - 1) // 2)):
            ref1, ref2 = random.sample(ref_candidates, 2)
            sampled_pairs.append((ref1, ref2))
        
        for ref1_id, ref2_id in sampled_pairs:
            direction1 = random.choice(directions)
            direction2 = random.choice(directions)
            
            # 找同时在两个方向的对象
            targets1 = set(parser.get_objects_in_direction(ref1_id, direction1))
            targets2 = set(parser.get_objects_in_direction(ref2_id, direction2))
            intersection = list(targets1 & targets2)
            
            if not intersection:
                continue
            
            # 生成存在性问题
            template = self.template_manager.get_template("L2_exist_two_directions")
            for obj_type in random.sample(OBJECT_TYPES, min(2, len(OBJECT_TYPES))):
                type_targets = [t for t in intersection if parser.get_node(t)["type"] == obj_type]
                
                singular, plural = TYPE_NAMES.get(obj_type, (obj_type, obj_type))
                question = self.template_manager.fill_template(
                    template,
                    target_type=singular,
                    direction1=direction1,
                    ref1_id=ref1_id,
                    direction2=direction2,
                    ref2_id=ref2_id
                )
                answer = "yes" if type_targets else "no"
                
                cameras = set(camera_mapper.get_object_cameras(ref1_id))
                cameras.update(camera_mapper.get_object_cameras(ref2_id))
                for t in type_targets[:5]:
                    cameras.update(camera_mapper.get_object_cameras(t))
                
                qa = self._create_qa_pair(
                    parser, template, question, answer,
                    target_objects=type_targets,
                    reference_objects=[ref1_id, ref2_id],
                    directions=[direction1, direction2],
                    cameras=list(cameras),
                    metadata={"obj_type": obj_type}
                )
                qa_pairs.append(qa)
                break  # 每对只生成一个
        
        return qa_pairs
    
    def _generate_chain_questions(self, parser: SceneGraphWithEdges,
                                 camera_mapper: CameraMapper,
                                 directions: List[str]) -> List[QAPair]:
        """生成链式查询问题（两跳）"""
        qa_pairs = []
        
        # 采样参考对象
        ref_candidates = [uid for uid in parser.nodes if uid != "ego"]
        sampled_refs = random.sample(ref_candidates, min(2, len(ref_candidates)))
        
        for ref_id in sampled_refs:
            direction1 = random.choice(directions)
            
            # 找中间对象
            mid_candidates = parser.get_objects_in_direction(ref_id, direction1)
            if not mid_candidates:
                continue
            
            mid_id = random.choice(mid_candidates)
            mid_node = parser.get_node(mid_id)
            mid_type = mid_node["type"]
            
            direction2 = random.choice(directions)
            
            # 找目标对象
            final_targets = parser.get_objects_in_direction(mid_id, direction2)
            if not final_targets:
                continue
            
            # 生成链式存在性问题
            template = self.template_manager.get_template("L2_exist_chain")
            for obj_type in random.sample(OBJECT_TYPES, min(2, len(OBJECT_TYPES))):
                type_targets = [t for t in final_targets if parser.get_node(t)["type"] == obj_type]
                
                singular, _ = TYPE_NAMES.get(obj_type, (obj_type, obj_type))
                mid_singular, _ = TYPE_NAMES.get(mid_type, (mid_type, mid_type))
                question = self.template_manager.fill_template(
                    template,
                    target_type=singular,
                    direction1=direction2,
                    mid_type=mid_singular,
                    direction2=direction1,
                    ref_id=ref_id
                )
                answer = "yes" if type_targets else "no"
                
                cameras = set(camera_mapper.get_object_cameras(ref_id))
                cameras.update(camera_mapper.get_object_cameras(mid_id))
                for t in type_targets[:5]:
                    cameras.update(camera_mapper.get_object_cameras(t))
                
                qa = self._create_qa_pair(
                    parser, template, question, answer,
                    target_objects=type_targets,
                    reference_objects=[ref_id, mid_id],
                    directions=[direction1, direction2],
                    cameras=list(cameras),
                    metadata={"obj_type": obj_type, "mid_type": mid_type}
                )
                qa_pairs.append(qa)
                break
        
        return qa_pairs
    
    def _generate_compare_two_chains_questions(self, parser: SceneGraphWithEdges,
                                              camera_mapper: CameraMapper,
                                              directions: List[str]) -> List[QAPair]:
        """生成两个链式对象比较问题"""
        qa_pairs = []
        template = self.template_manager.get_template("L2_compare_two_chains")
        
        ref_candidates = [uid for uid in parser.nodes if uid != "ego"]
        if len(ref_candidates) < 2:
            return qa_pairs
        
        sampled_pairs = []
        for _ in range(min(2, len(ref_candidates) * (len(ref_candidates) - 1) // 2)):
            ref1, ref2 = random.sample(ref_candidates, 2)
            sampled_pairs.append((ref1, ref2))
        
        for ref1_id, ref2_id in sampled_pairs:
            direction1 = random.choice(directions)
            direction2 = random.choice(directions)
            
            for obj_type1, obj_type2 in random.sample(list(zip(OBJECT_TYPES, OBJECT_TYPES)), min(1, len(OBJECT_TYPES))):
                targets1 = parser.get_objects_in_direction(ref1_id, direction1, obj_type=obj_type1)
                targets2 = parser.get_objects_in_direction(ref2_id, direction2, obj_type=obj_type2)
                
                if len(targets1) != 1 or len(targets2) != 1:
                    continue
                
                target1 = targets1[0]
                target2 = targets2[0]
                
                node1 = parser.get_node(target1)
                node2 = parser.get_node(target2)
                
                status1 = node1.get("status")
                status2 = node2.get("status")
                
                if not status1 or not status2 or status1 == "unknown" or status2 == "unknown":
                    continue
                
                singular1, _ = TYPE_NAMES.get(obj_type1, (obj_type1, obj_type1))
                singular2, _ = TYPE_NAMES.get(obj_type2, (obj_type2, obj_type2))
                
                question = self.template_manager.fill_template(
                    template,
                    type1=singular1,
                    direction1=direction1,
                    ref1_id=ref1_id,
                    type2=singular2,
                    direction2=direction2,
                    ref2_id=ref2_id
                )
                answer = "yes" if status1 == status2 else "no"
                
                cameras = set(camera_mapper.get_object_cameras(ref1_id))
                cameras.update(camera_mapper.get_object_cameras(ref2_id))
                cameras.update(camera_mapper.get_object_cameras(target1))
                cameras.update(camera_mapper.get_object_cameras(target2))
                
                qa = self._create_qa_pair(
                    parser, template, question, answer,
                    target_objects=[target1, target2],
                    reference_objects=[ref1_id, ref2_id],
                    directions=[direction1, direction2],
                    cameras=list(cameras),
                    metadata={
                        "type1": obj_type1,
                        "type2": obj_type2,
                        "status1": status1,
                        "status2": status2
                    }
                )
                qa_pairs.append(qa)
                break
        
        return qa_pairs


class UnifiedQAGenerator:
    """
    统一问答生成器
    
    整合L0/L1/L2所有级别的问题生成
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or QA_CONFIG
        self.l0_generator = L0QuestionGenerator(config)
        self.l1_generator = L1QuestionGenerator(config)
        self.l2_generator = L2QuestionGenerator(config)
    
    def generate(self, scene_data: Dict,
                 difficulties: List[str] = None,
                 max_questions: int = None) -> List[QAPair]:
        """
        从场景图生成问答对
        
        Args:
            scene_data: 场景图JSON数据
            difficulties: 要生成的难度列表 ["L0", "L1", "L2"]
            max_questions: 最大问题数量
        
        Returns:
            QAPair列表
        """
        if difficulties is None:
            difficulties = ["L0", "L1", "L2"]
        
        parser = SceneGraphWithEdges(scene_data)
        camera_mapper = CameraMapper(scene_data)
        
        all_qa_pairs = []
        counter = 0
        
        if "L0" in difficulties:
            l0_pairs = self.l0_generator.generate(scene_data, camera_mapper)
            # 更新question_id
            for qa in l0_pairs:
                counter += 1
                qa.question_id = f"{parser.scene_name}_frame{parser.frame_idx}_q{counter:04d}"
            all_qa_pairs.extend(l0_pairs)
        
        if "L1" in difficulties:
            l1_pairs = self.l1_generator.generate(scene_data, parser, camera_mapper, counter)
            counter += len(l1_pairs)
            all_qa_pairs.extend(l1_pairs)
        
        if "L2" in difficulties:
            l2_pairs = self.l2_generator.generate(scene_data, parser, camera_mapper, counter)
            all_qa_pairs.extend(l2_pairs)
        
        # 限制数量
        if max_questions and len(all_qa_pairs) > max_questions:
            random.shuffle(all_qa_pairs)
            all_qa_pairs = all_qa_pairs[:max_questions]
        
        return all_qa_pairs
    
    def save_qa_pairs(self, qa_pairs: List[QAPair], output_path: str):
        """保存问答对到JSON文件"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump([qa.to_dict() for qa in qa_pairs], f, ensure_ascii=False, indent=2)


def test_unified_generator():
    """测试统一生成器"""
    import json
    from pathlib import Path
    
    # 加载示例场景图
    sg_path = Path(__file__).parent.parent.parent / "output" / "coverage_analysis" / "scene_graphs" / "scene-0103_frame38_scene_graph.json"
    
    if not sg_path.exists():
        print(f"Test scene graph not found: {sg_path}")
        return
    
    with open(sg_path, 'r', encoding='utf-8') as f:
        scene_data = json.load(f)
    
    print("="*60)
    print("Testing Unified QA Generator (L0 + L1 + L2)")
    print("="*60)
    
    # 创建生成器
    generator = UnifiedQAGenerator()
    
    # 生成所有难度的问答对
    qa_pairs = generator.generate(scene_data)
    
    print(f"\nGenerated {len(qa_pairs)} QA pairs\n")
    
    # 按难度统计
    from collections import Counter
    difficulty_counts = Counter(qa.difficulty for qa in qa_pairs)
    print("By difficulty:")
    for diff, count in sorted(difficulty_counts.items()):
        print(f"  {diff}: {count:3d}")
    
    # 按类型统计
    type_counts = Counter(qa.question_type for qa in qa_pairs)
    print("\nBy question type:")
    for qtype, count in type_counts.items():
        print(f"  {qtype:12s}: {count:3d}")
    
    temporal_count = sum(1 for qa in qa_pairs if qa.requires_temporal)
    print(f"\nRequires temporal: {temporal_count}/{len(qa_pairs)}")
    
    # 显示各难度示例
    print("\n" + "="*60)
    print("Sample QA Pairs")
    print("="*60)
    
    for difficulty in ["L0", "L1", "L2"]:
        samples = [qa for qa in qa_pairs if qa.difficulty == difficulty][:2]
        if samples:
            print(f"\n{'='*60}")
            print(f"{difficulty} Examples")
            print('='*60)
            for qa in samples:
                print(f"\nQ: {qa.question}")
                print(f"A: {qa.answer}")
                print(f"Type: {qa.question_type}, Template: {qa.template_id}")
                if qa.directions_used:
                    print(f"Directions: {qa.directions_used}")
                print(f"Targets: {qa.target_objects[:3]}{'...' if len(qa.target_objects) > 3 else ''}")
                if qa.reference_objects:
                    print(f"References: {qa.reference_objects}")
    
    # 保存结果
    output_path = Path(__file__).parent / "test_output_unified.json"
    generator.save_qa_pairs(qa_pairs, str(output_path))
    
    print(f"\n✓ Results saved to: {output_path}")


if __name__ == "__main__":
    test_unified_generator()
