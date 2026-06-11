"""
QA Generator - 核心问答生成器

基于场景图（Scene Graph）生成问答对：
- 使用Source Frame（以被描述对象的朝向为基准）
- 支持L0/L1/L2三种难度
- 支持给选项/不给选项两种模式
- 输出包含精确的对象ID，便于CV模型定位
"""
import json
import random
import logging
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from pathlib import Path

from .config import (
    DIRECTIONS_8, DIRECTIONS_4, OBJECT_TYPES, TYPE_NAMES,
    STATUS_DISPLAY_NAMES, QA_CONFIG, DISTANCE_THRESHOLDS
)
from .templates import QATemplates, QATemplate
from .cypher_generator import generate_cypher_for_qa

logger = logging.getLogger(__name__)


@dataclass
class QAPair:
    """问答对数据结构"""
    # 基础信息
    question_id: str
    scene_name: str
    frame_idx: int
    sample_token: Optional[str] = None
    
    # 问题元数据
    question_type: str = ""           # exist, status, object, comparison
    template_id: str = ""
    difficulty: str = ""              # L0, L1, L2
    
    # 涉及的对象（关键！CV模型用于定位画面）
    target_objects: List[str] = field(default_factory=list)
    reference_objects: List[str] = field(default_factory=list)
    
    # 方向信息
    direction_frame: str = "source"   # source 或 ego
    directions_used: List[str] = field(default_factory=list)
    
    # 问题和答案
    question: str = ""
    answer: str = ""
    answer_type: str = ""             # bool, type, status
    
    # 选择题模式
    with_options: Optional[Dict[str, Any]] = None
    
    # Neo4j Cypher查询（用于覆盖率计算与缺口检测）
    cypher_query: str = ""
    
    # 附加信息
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class SceneGraphParser:
    """场景图解析器"""
    
    def __init__(self, scene_data: Dict):
        self.scene_name = scene_data.get("scene_name", "unknown")
        self.frame_idx = scene_data.get("frame_idx", 0)
        self.sample_token = scene_data.get("sample_token")
        
        # 解析节点
        self.nodes: Dict[str, Dict] = {}
        self.nodes_by_type: Dict[str, List[str]] = defaultdict(list)
        
        nodes_data = scene_data.get("nodes") or scene_data.get("objects", [])
        for node in nodes_data:
            uid = node["unique_id"]
            self.nodes[uid] = node
            self.nodes_by_type[node["type"]].append(uid)
        
        # 解析边（空间关系）
        self.edges: List[Dict] = scene_data.get("edges") or scene_data.get("relationships", [])
        
        # 构建邻接表（基于Source Frame）
        # source_adjacency[source_id][direction] = [target_ids]
        self.source_adjacency: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
        self.edge_map: Dict[Tuple[str, str], Dict] = {}
        
        for edge in self.edges:
            src = edge["source"]
            tgt = edge["target"]
            self.edge_map[(src, tgt)] = edge
            
            # 获取Source Frame方向
            direction_source = self._get_direction_source(edge)
            if direction_source:
                self.source_adjacency[src][direction_source].append(tgt)
                
                # 同时记录宽松匹配的方向
                angle_matches = edge.get("metrics", {}).get("direction_source", {}).get("angle_matches", [])
                if not angle_matches:
                    angle_matches = edge.get("angle_matches_source", [])
                for dir_match in angle_matches:
                    if dir_match != direction_source:
                        self.source_adjacency[src][dir_match].append(tgt)
    
    def _get_direction_source(self, edge: Dict) -> Optional[str]:
        """获取边的Source Frame方向"""
        # 优先从metrics中获取
        metrics = edge.get("metrics", {})
        direction_source = metrics.get("direction_source", {})
        if isinstance(direction_source, dict):
            return direction_source.get("direction_8")
        
        # 备用：直接从边属性获取
        return edge.get("direction_8_source") or edge.get("direction_8")
    
    def get_node(self, uid: str) -> Optional[Dict]:
        """获取节点"""
        return self.nodes.get(uid)
    
    def get_nodes_by_type(self, obj_type: str) -> List[str]:
        """按类型获取节点ID列表"""
        return self.nodes_by_type.get(obj_type, [])
    
    def get_nodes_by_status(self, status: str) -> List[str]:
        """按状态获取节点ID列表"""
        return [uid for uid, node in self.nodes.items() if node.get("status") == status]
    
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
        targets = self.source_adjacency[ref_id].get(direction, [])
        
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


class QAGenerator:
    """
    问答生成器
    
    使用方法:
        generator = QAGenerator()
        qa_pairs = generator.generate_from_scene_graph(scene_data)
        generator.save_qa_pairs(qa_pairs, "output.json")
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or QA_CONFIG
        self.templates = QATemplates()
        self._question_counter = 0
    
    def generate_from_scene_graph(self, scene_data: Dict, 
                                   max_questions: int = None) -> List[QAPair]:
        """
        从场景图生成问答对
        
        Args:
            scene_data: 场景图JSON数据
            max_questions: 最大问题数量
        
        Returns:
            QAPair列表
        """
        parser = SceneGraphParser(scene_data)
        max_q = max_questions or self.config.get("max_questions_per_scene", 100)
        
        qa_pairs = []
        
        # 生成L0问题
        qa_pairs.extend(self._generate_L0_questions(parser))
        
        # 生成L1问题
        qa_pairs.extend(self._generate_L1_questions(parser))
        
        # 生成L2问题
        qa_pairs.extend(self._generate_L2_questions(parser))
        
        # 限制数量
        if len(qa_pairs) > max_q:
            random.shuffle(qa_pairs)
            qa_pairs = qa_pairs[:max_q]
        
        # 为每个问答对添加选择题选项
        for qa in qa_pairs:
            if qa.answer_type:
                qa.with_options = self.templates.generate_options(
                    qa.answer, qa.answer_type,
                    num_options=self.config.get("num_options", 4)
                )
        
        logger.info(f"Generated {len(qa_pairs)} QA pairs for {parser.scene_name} frame {parser.frame_idx}")
        return qa_pairs
    
    def _make_question_id(self, parser: SceneGraphParser, template_id: str) -> str:
        """生成问题ID"""
        self._question_counter += 1
        return f"{parser.scene_name}_frame{parser.frame_idx}_q{self._question_counter:04d}"
    
    def _create_qa_pair(self, parser: SceneGraphParser, template: QATemplate,
                        question: str, answer: str,
                        target_objects: List[str] = None,
                        reference_objects: List[str] = None,
                        directions: List[str] = None,
                        metadata: Dict = None,
                        cypher_params: Dict = None) -> QAPair:
        """创建QAPair，并自动生成对应的Cypher查询。"""
        cypher = ""
        if cypher_params is not None:
            try:
                cypher = generate_cypher_for_qa(template.template_id, cypher_params) or ""
            except Exception as e:
                logger.debug(f"Cypher generation failed for {template.template_id}: {e}")
        return QAPair(
            question_id=self._make_question_id(parser, template.template_id),
            scene_name=parser.scene_name,
            frame_idx=parser.frame_idx,
            sample_token=parser.sample_token,
            question_type=template.question_type,
            template_id=template.template_id,
            difficulty=template.difficulty,
            target_objects=target_objects or [],
            reference_objects=reference_objects or [],
            direction_frame="source",
            directions_used=directions or [],
            question=question,
            answer=str(answer),
            answer_type=template.answer_type,
            cypher_query=cypher,
            metadata=metadata or {},
        )
    
    # ==================== L0 问题生成 ====================
    def _generate_L0_questions(self, parser: SceneGraphParser) -> List[QAPair]:
        """生成L0级别问题（单对象属性查询）
        
        仅包含 exist 和 status 类型，已移除 count 类型。
        """
        qa_pairs = []
        
        # L0_exist_type: Are there any {type}?
        template = self.templates.get_template("L0_exist_type")
        for obj_type in OBJECT_TYPES:
            nodes = parser.get_nodes_by_type(obj_type)
            if not nodes and random.random() > 0.3:  # 30%概率问不存在的类型
                continue
            singular, plural = TYPE_NAMES.get(obj_type, (obj_type, obj_type + "s"))
            question = self.templates.fill_template(template, type_plural=plural)
            answer = "yes" if nodes else "no"
            qa_pairs.append(self._create_qa_pair(
                parser, template, question, answer,
                target_objects=nodes[:5],
                metadata={"obj_type": obj_type},
                cypher_params={"obj_type": obj_type},
            ))
        
        # L0_status_query: What is the status of {ref_type} ({ref_id})?
        template = self.templates.get_template("L0_status_query")
        for uid, node in parser.nodes.items():
            if uid == "ego":
                continue
            status = node.get("status")
            if not status or status == "unknown":
                continue
            obj_type = node["type"]
            singular, _ = TYPE_NAMES.get(obj_type, (obj_type, obj_type))
            question = self.templates.fill_template(template, ref_type=singular, ref_id=uid)
            qa_pairs.append(self._create_qa_pair(
                parser, template, question, status,
                reference_objects=[uid],
                metadata={"ref_type": obj_type},
                cypher_params={"ref_id": uid},
            ))
        
        return qa_pairs
    
    # ==================== L1 问题生成 ====================
    def _generate_L1_questions(self, parser: SceneGraphParser) -> List[QAPair]:
        """生成L1级别问题（单跳空间关系查询）
        
        已移除 count 类型。保留 exist/status/object/comparison。
        每个QA对附带Cypher查询用于覆盖率计算。
        """
        qa_pairs = []
        directions = DIRECTIONS_8 if self.config.get("use_8_directions", True) else DIRECTIONS_4
        
        ref_candidates = [uid for uid in parser.nodes if uid != "ego"]
        
        for ref_id in ref_candidates:
            ref_node = parser.get_node(ref_id)
            if not ref_node:
                continue
            
            ref_type = ref_node["type"]
            ref_singular, _ = TYPE_NAMES.get(ref_type, (ref_type, ref_type))
            
            for direction in directions:
                targets_all = parser.get_objects_in_direction(ref_id, direction)
                if not targets_all:
                    continue
                
                # L1_exist_direction — 只针对实际存在该方向目标的type出题（减少大量"no"噪声）
                template = self.templates.get_template("L1_exist_direction")
                for target_type in OBJECT_TYPES:
                    targets = parser.get_objects_in_direction(ref_id, direction, obj_type=target_type)
                    if not targets:  # 只生成答案为yes的题，避免大量"no"稀释覆盖
                        continue
                    _, plural = TYPE_NAMES.get(target_type, (target_type, target_type + "s"))
                    question = self.templates.fill_template(
                        template,
                        type_plural=plural,
                        direction=direction,
                        ref_type=ref_singular,
                        ref_id=ref_id
                    )
                    qa_pairs.append(self._create_qa_pair(
                        parser, template, question, "yes",
                        target_objects=targets[:5],
                        reference_objects=[ref_id],
                        directions=[direction],
                        metadata={"target_type": target_type},
                        cypher_params={"ref_id": ref_id, "direction": direction,
                                       "obj_type": target_type},
                    ))
                
                # L1_status_direction — 取最近目标
                target_id = targets_all[0]
                target_node = parser.get_node(target_id)
                if target_node and target_node.get("status") and target_node["status"] != "unknown":
                    template = self.templates.get_template("L1_status_direction")
                    ttype = target_node["type"]
                    t_singular, _ = TYPE_NAMES.get(ttype, (ttype, ttype))
                    question = self.templates.fill_template(
                        template,
                        target_type=t_singular,
                        target_id=target_id,
                        direction=direction,
                        ref_type=ref_singular,
                        ref_id=ref_id
                    )
                    qa_pairs.append(self._create_qa_pair(
                        parser, template, question, target_node["status"],
                        target_objects=[target_id],
                        reference_objects=[ref_id],
                        directions=[direction],
                        cypher_params={"ref_id": ref_id, "direction": direction,
                                       "target_id": target_id},
                    ))
        
        # L1_compare_status — status作为节点属性，直接比较两个节点
        template = self.templates.get_template("L1_compare_status")
        node_list = [uid for uid in parser.nodes if uid != "ego"]
        for i, uid1 in enumerate(node_list):
            for uid2 in node_list[i+1:]:
                node1 = parser.get_node(uid1)
                node2 = parser.get_node(uid2)
                if not node1 or not node2:
                    continue
                s1, s2 = node1.get("status"), node2.get("status")
                if not s1 or not s2 or s1 == "unknown" or s2 == "unknown":
                    continue
                t1_singular, _ = TYPE_NAMES.get(node1["type"], (node1["type"], ""))
                t2_singular, _ = TYPE_NAMES.get(node2["type"], (node2["type"], ""))
                question = self.templates.fill_template(
                    template,
                    obj1_type=t1_singular, obj1_id=uid1,
                    obj2_type=t2_singular, obj2_id=uid2
                )
                answer = "yes" if s1 == s2 else "no"
                qa_pairs.append(self._create_qa_pair(
                    parser, template, question, answer,
                    target_objects=[uid1, uid2],
                    metadata={"status1": s1, "status2": s2},
                    cypher_params={"obj1_id": uid1, "obj2_id": uid2},
                ))
        
        return qa_pairs
    
    # ==================== L2 问题生成 ====================
    def _generate_L2_questions(self, parser: SceneGraphParser) -> List[QAPair]:
        """生成L2级别问题 — 严格首尾相连两连边链式模式。

        模式定义：ref(A) --dir2--> mid(B) --dir1--> target(C)
          - A 是锚点（reference）
          - B 是中间节点（前一条边的尾 = 后一条边的首）
          - C 是目标（target）
          - A ≠ B ≠ C

        生成的问题类型：
          - L2_exist_chain: "Is there a [C_type] to [dir1] of [B_type]
                              that is to [dir2] of [A_type] (A_id)?"
          - L2_status_chain: "What is the status of the [C_type] to [dir1] of
                               [B_type] ([B_id]) that is to [dir2] of [A_type] (A_id)?"
          - L2_compare_chain: 当C有status时，比较A.status与通过链找到的B.status
                               (status作为双向边)

        已移除（与count类及非链式模式）：
          - L2_count_same_status
          - L2_object_two_directions（多锚点交集，非链式）
        """
        qa_pairs = []
        directions = DIRECTIONS_8 if self.config.get("use_8_directions", True) else DIRECTIONS_4
        
        all_nodes = [uid for uid in parser.nodes if uid != "ego"]
        # 限制每对(anchor, mid)最多生成的方向组合数，防止组合爆炸
        max_targets_per_mid = 2
        
        # --- L2_exist_chain / L2_status_chain ---
        t_exist = self.templates.get_template("L2_exist_chain")
        t_status = self.templates.get_template("L2_status_chain")
        t_exist_st = self.templates.get_template("L2_exist_chain_status")
        
        for anchor_id in all_nodes:
            anchor_node = parser.get_node(anchor_id)
            if not anchor_node:
                continue
            anchor_type = anchor_node["type"]
            anchor_singular, _ = TYPE_NAMES.get(anchor_type, (anchor_type, anchor_type))
            
            for dir2 in directions:  # direction from anchor to mid
                mids = parser.get_objects_in_direction(anchor_id, dir2)
                if not mids:
                    continue
                
                mid_id = mids[0]  # 取最近的中间节点
                if mid_id == anchor_id:
                    continue
                mid_node = parser.get_node(mid_id)
                if not mid_node:
                    continue
                mid_type = mid_node["type"]
                mid_singular, _ = TYPE_NAMES.get(mid_type, (mid_type, mid_type))
                
                for dir1 in directions:  # direction from mid to target
                    if dir1 == dir2:  # 避免无意义的同向链
                        continue
                    targets = parser.get_objects_in_direction(mid_id, dir1)
                    if not targets:
                        continue
                    
                    for target_id in targets[:max_targets_per_mid]:
                        if target_id in (anchor_id, mid_id):
                            continue
                        target_node = parser.get_node(target_id)
                        if not target_node:
                            continue
                        target_type = target_node["type"]
                        target_singular, _ = TYPE_NAMES.get(target_type, (target_type, target_type))
                        target_status = target_node.get("status")
                        
                        # — L2_exist_chain —
                        question = self.templates.fill_template(
                            t_exist,
                            type_singular=target_singular,
                            direction1=dir1,
                            mid_type=mid_singular,
                            direction2=dir2,
                            ref_type=anchor_singular,
                            ref_id=anchor_id
                        )
                        qa_pairs.append(self._create_qa_pair(
                            parser, t_exist, question, "yes",
                            target_objects=[target_id],
                            reference_objects=[anchor_id, mid_id],
                            directions=[dir2, dir1],
                            metadata={"anchor_id": anchor_id, "mid_id": mid_id,
                                      "target_id": target_id},
                            cypher_params={"ref_id": anchor_id, "dir2": dir2,
                                           "mid_id": mid_id, "dir1": dir1,
                                           "obj_type": target_type},
                        ))
                        
                        # — L2_status_chain — (只有C有有效status时出题)
                        if target_status and target_status != "unknown":
                            question = self.templates.fill_template(
                                t_status,
                                target_type=target_singular,
                                direction1=dir1,
                                mid_type=mid_singular,
                                mid_id=mid_id,
                                direction2=dir2,
                                ref_type=anchor_singular,
                                ref_id=anchor_id
                            )
                            qa_pairs.append(self._create_qa_pair(
                                parser, t_status, question, target_status,
                                target_objects=[target_id],
                                reference_objects=[anchor_id, mid_id],
                                directions=[dir2, dir1],
                                metadata={"anchor_id": anchor_id, "mid_id": mid_id,
                                          "target_id": target_id},
                                cypher_params={"ref_id": anchor_id, "dir2": dir2,
                                               "mid_id": mid_id, "dir1": dir1,
                                               "obj_type": target_type},
                            ))
                        
                        # — L2_exist_chain_status — status作双向边：
                        #   用C的status约束查询，问anchor方向上mid方向上是否有此status的C
                        if target_status and target_status != "unknown":
                            question = self.templates.fill_template(
                                t_exist_st,
                                status=target_status,
                                type_singular=target_singular,
                                direction1=dir1,
                                mid_type=mid_singular,
                                direction2=dir2,
                                ref_type=anchor_singular,
                                ref_id=anchor_id
                            )
                            qa_pairs.append(self._create_qa_pair(
                                parser, t_exist_st, question, "yes",
                                target_objects=[target_id],
                                reference_objects=[anchor_id, mid_id],
                                directions=[dir2, dir1],
                                metadata={"anchor_id": anchor_id, "mid_id": mid_id,
                                          "target_type": target_type,
                                          "target_status": target_status},
                                cypher_params={"ref_id": anchor_id, "dir2": dir2,
                                               "mid_id": mid_id, "dir1": dir1,
                                               "obj_type": target_type,
                                               "status": target_status},
                            ))
        
        # --- L2_compare_chain: status作双向边 ---
        # 比较锚点A的status与A通过某方向找到的对象B的status
        # 即: A.status == B.status where A--direction-->B
        # （这是单跳的status比较，但status是"对象属性边"，被视为L2维度）
        t_cmp = self.templates.get_template("L2_compare_chain")
        for anchor_id in all_nodes:
            anchor_node = parser.get_node(anchor_id)
            if not anchor_node:
                continue
            anchor_status = anchor_node.get("status")
            if not anchor_status or anchor_status == "unknown":
                continue
            anchor_type = anchor_node["type"]
            anchor_singular, _ = TYPE_NAMES.get(anchor_type, (anchor_type, anchor_type))
            
            for direction in directions:
                neighbors = parser.get_objects_in_direction(anchor_id, direction)
                if not neighbors:
                    continue
                
                nb_id = neighbors[0]
                if nb_id == anchor_id:
                    continue
                nb_node = parser.get_node(nb_id)
                if not nb_node:
                    continue
                nb_status = nb_node.get("status")
                if not nb_status or nb_status == "unknown":
                    continue
                nb_type = nb_node["type"]
                nb_singular, _ = TYPE_NAMES.get(nb_type, (nb_type, nb_type))
                
                question = self.templates.fill_template(
                    t_cmp,
                    obj1_type=anchor_singular, obj1_id=anchor_id,
                    obj2_type=nb_singular,
                    direction=direction,
                    ref_type=anchor_singular, ref_id=anchor_id
                )
                answer = "yes" if anchor_status == nb_status else "no"
                qa_pairs.append(self._create_qa_pair(
                    parser, t_cmp, question, answer,
                    target_objects=[nb_id],
                    reference_objects=[anchor_id],
                    directions=[direction],
                    metadata={"anchor_status": anchor_status, "nb_status": nb_status},
                    cypher_params={"obj1_id": anchor_id, "ref_id": anchor_id,
                                   "direction": direction, "obj2_type": nb_type},
                ))
        
        return qa_pairs
    
    # ==================== 输出方法 ====================
    def save_qa_pairs(self, qa_pairs: List[QAPair], output_path: str):
        """保存问答对到JSON文件"""
        output = {
            "meta": {
                "generator": "QAGenerator",
                "direction_frame": "source",
                "total_questions": len(qa_pairs),
                "config": self.config,
            },
            "qa_pairs": [qa.to_dict() for qa in qa_pairs]
        }
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(qa_pairs)} QA pairs to {output_path}")
    
    def format_for_cv_model(self, qa_pairs: List[QAPair], 
                            with_options: bool = True) -> List[Dict]:
        """
        格式化为CV模型输入格式
        
        Args:
            qa_pairs: 问答对列表
            with_options: 是否包含选项（选择题模式）
        
        Returns:
            格式化后的列表，每项包含question, answer, object_ids等
        """
        result = []
        for qa in qa_pairs:
            item = {
                "question_id": qa.question_id,
                "scene_name": qa.scene_name,
                "frame_idx": qa.frame_idx,
                "sample_token": qa.sample_token,
                
                # 核心对象ID（CV模型定位用）
                "target_object_ids": qa.target_objects,
                "reference_object_ids": qa.reference_objects,
                
                # 方向信息
                "direction_frame": qa.direction_frame,
                "directions": qa.directions_used,
            }
            
            if with_options and qa.with_options:
                item["question"] = qa.question + " " + " ".join(qa.with_options["formatted_options"])
                item["answer"] = qa.with_options["answer_label"]
                item["answer_text"] = qa.answer
                item["options"] = qa.with_options["options"]
            else:
                item["question"] = qa.question
                item["answer"] = qa.answer
            
            result.append(item)
        
        return result


# ==================== 便捷函数 ====================
def generate_qa_from_file(scene_graph_path: str, output_path: str = None,
                          max_questions: int = None) -> List[QAPair]:
    """
    从场景图文件生成问答对
    
    Args:
        scene_graph_path: 场景图JSON文件路径
        output_path: 输出文件路径（可选）
        max_questions: 最大问题数量
    
    Returns:
        QAPair列表
    """
    with open(scene_graph_path, "r", encoding="utf-8") as f:
        scene_data = json.load(f)
    
    generator = QAGenerator()
    qa_pairs = generator.generate_from_scene_graph(scene_data, max_questions)
    
    if output_path:
        generator.save_qa_pairs(qa_pairs, output_path)
    
    return qa_pairs


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    # 示例用法
    if len(sys.argv) > 1:
        scene_graph_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 else None
        qa_pairs = generate_qa_from_file(scene_graph_path, output_path)
        
        print(f"\n生成了 {len(qa_pairs)} 个问答对")
        print("\n示例问答对：")
        for qa in qa_pairs[:5]:
            print(f"\n[{qa.difficulty}] {qa.question}")
            print(f"  答案: {qa.answer}")
            print(f"  涉及对象: {qa.target_objects + qa.reference_objects}")
            if qa.with_options:
                print(f"  选项: {qa.with_options['formatted_options']}")
    else:
        print("用法: python generator.py <scene_graph.json> [output.json]")
