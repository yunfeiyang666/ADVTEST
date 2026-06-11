"""
L0 Question Generator - L0级别问题生成器
基于场景图自动生成单对象属性查询问题
"""
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass, field, asdict
import random
import json

try:
    from .templates import TemplateManager, QATemplate, OptionGenerator
    from .camera_mapper import CameraMapper
    from .config import OBJECT_TYPES, TYPE_NAMES, QA_CONFIG
except ImportError:
    from templates import TemplateManager, QATemplate, OptionGenerator
    from camera_mapper import CameraMapper
    from config import OBJECT_TYPES, TYPE_NAMES, QA_CONFIG


@dataclass
class QAPair:
    """问答对数据结构"""
    # 基础信息
    question_id: str
    scene_name: str
    frame_idx: int
    sample_token: Optional[str] = None
    
    # 问题元数据
    question_type: str = ""           # exist, count, status, object, comparison
    template_id: str = ""
    difficulty: str = "L0"
    
    # 涉及的对象（关键！CV模型用于定位画面）
    target_objects: List[str] = field(default_factory=list)
    reference_objects: List[str] = field(default_factory=list)
    
    # 方向信息
    direction_frame: str = "source"   # source 或 ego
    directions_used: List[str] = field(default_factory=list)
    
    # 问题和答案
    question: str = ""
    answer: str = ""
    answer_type: str = ""             # bool, number, type, status
    
    # 时序信息
    requires_temporal: bool = False
    recommended_frame_window: int = 5
    
    # 相机信息（仅用于内部分析，不给CV模型）
    cameras_for_analysis: List[str] = field(default_factory=list)
    
    # 选择题模式（可选）
    with_options: Optional[Dict] = None
    
    # 附加信息
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
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
        nodes_data = scene_data.get("nodes") or scene_data.get("objects", [])
        self.nodes: Dict[str, Dict] = {
            node["unique_id"]: node for node in nodes_data
        }
        
        # 按类型索引
        self.nodes_by_type: Dict[str, List[str]] = defaultdict(list)
        for uid, node in self.nodes.items():
            if uid != "ego":
                self.nodes_by_type[node["type"]].append(uid)
        
        # 按状态索引
        self.nodes_by_status: Dict[str, List[str]] = defaultdict(list)
        for uid, node in self.nodes.items():
            if uid != "ego" and node.get("status"):
                status = node["status"]
                if status != "unknown":
                    self.nodes_by_status[status].append(uid)
        
        # 统计信息
        self.total_objects = len(self.nodes) - 1  # 排除ego
        self.object_types_present = set(self.nodes_by_type.keys())
        self.statuses_present = set(self.nodes_by_status.keys())
    
    def get_node(self, uid: str) -> Optional[Dict]:
        """获取节点"""
        return self.nodes.get(uid)
    
    def get_nodes_by_type(self, obj_type: str) -> List[str]:
        """获取指定类型的节点ID列表"""
        return self.nodes_by_type.get(obj_type, [])
    
    def get_nodes_by_status(self, status: str) -> List[str]:
        """获取指定状态的节点ID列表"""
        return self.nodes_by_status.get(status, [])
    
    def get_nodes_by_type_and_status(self, obj_type: str, status: str) -> List[str]:
        """获取指定类型和状态的节点ID列表"""
        type_nodes = set(self.get_nodes_by_type(obj_type))
        status_nodes = set(self.get_nodes_by_status(status))
        return list(type_nodes & status_nodes)


class L0QuestionGenerator:
    """
    L0问题生成器
    
    生成单对象属性查询问题（不涉及空间关系）
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or QA_CONFIG
        self.template_manager = TemplateManager()
        self._question_counter = 0
    
    def generate(self, scene_data: Dict, camera_mapper: Optional[CameraMapper] = None) -> List[QAPair]:
        """
        从场景图生成L0问答对
        
        Args:
            scene_data: 场景图JSON数据
            camera_mapper: 相机映射器（可选，用于标注相机信息）
        
        Returns:
            QAPair列表
        """
        self._question_counter = 0
        parser = SceneGraphParser(scene_data)
        
        if camera_mapper is None:
            camera_mapper = CameraMapper(scene_data)
        
        qa_pairs = []
        
        # 生成各类型问题
        qa_pairs.extend(self._generate_exist_type_questions(parser, camera_mapper))
        qa_pairs.extend(self._generate_exist_status_questions(parser, camera_mapper))
        qa_pairs.extend(self._generate_count_type_questions(parser, camera_mapper))
        qa_pairs.extend(self._generate_count_status_questions(parser, camera_mapper))
        qa_pairs.extend(self._generate_status_query_questions(parser, camera_mapper))
        qa_pairs.extend(self._generate_object_status_questions(parser, camera_mapper))
        
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
    
    def _make_question_id(self, parser: SceneGraphParser) -> str:
        """生成问题ID"""
        self._question_counter += 1
        return f"{parser.scene_name}_frame{parser.frame_idx}_q{self._question_counter:04d}"
    
    def _create_qa_pair(self, parser: SceneGraphParser, template: QATemplate,
                       question: str, answer: str,
                       target_objects: List[str] = None,
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
            question=question,
            answer=answer,
            answer_type=template.answer_type,
            requires_temporal=template.requires_temporal,
            cameras_for_analysis=cameras or [],
            metadata=metadata or {},
        )
    
    # ==================== 存在性问题 ====================
    def _generate_exist_type_questions(self, parser: SceneGraphParser, 
                                       camera_mapper: CameraMapper) -> List[QAPair]:
        """生成类型存在性问题：Are there any {type}?"""
        qa_pairs = []
        template = self.template_manager.get_template("L0_exist_type")
        
        for obj_type in OBJECT_TYPES:
            nodes = parser.get_nodes_by_type(obj_type)
            
            # 30%概率也问不存在的类型
            if not nodes and random.random() > 0.3:
                continue
            
            singular, plural = TYPE_NAMES.get(obj_type, (obj_type, obj_type + "s"))
            question = self.template_manager.fill_template(template, type_plural=plural)
            answer = "yes" if nodes else "no"
            
            # 收集相机信息
            cameras = set()
            for uid in nodes[:10]:  # 最多记录10个对象的相机
                cameras.update(camera_mapper.get_object_cameras(uid))
            
            qa = self._create_qa_pair(
                parser, template, question, answer,
                target_objects=nodes[:10],
                cameras=list(cameras),
                metadata={"obj_type": obj_type, "count": len(nodes)}
            )
            qa_pairs.append(qa)
        
        return qa_pairs
    
    def _generate_exist_status_questions(self, parser: SceneGraphParser,
                                         camera_mapper: CameraMapper) -> List[QAPair]:
        """生成状态存在性问题：Are any {status} {type} visible?"""
        qa_pairs = []
        template = self.template_manager.get_template("L0_exist_status")
        
        # 遍历类型和状态的组合
        for obj_type in OBJECT_TYPES:
            for status in parser.statuses_present:
                nodes = parser.get_nodes_by_type_and_status(obj_type, status)
                
                # 只生成部分组合（避免太多）
                if random.random() > 0.5:
                    continue
                
                singular, plural = TYPE_NAMES.get(obj_type, (obj_type, obj_type + "s"))
                question = self.template_manager.fill_template(
                    template, 
                    status=status,
                    type_plural=plural
                )
                answer = "yes" if nodes else "no"
                
                cameras = set()
                for uid in nodes[:10]:
                    cameras.update(camera_mapper.get_object_cameras(uid))
                
                qa = self._create_qa_pair(
                    parser, template, question, answer,
                    target_objects=nodes[:10],
                    cameras=list(cameras),
                    metadata={"obj_type": obj_type, "status": status, "count": len(nodes)}
                )
                qa_pairs.append(qa)
        
        return qa_pairs
    
    # ==================== 计数问题 ====================
    def _generate_count_type_questions(self, parser: SceneGraphParser,
                                       camera_mapper: CameraMapper) -> List[QAPair]:
        """生成类型计数问题：How many {type} are there?"""
        qa_pairs = []
        template = self.template_manager.get_template("L0_count_type")
        
        for obj_type in OBJECT_TYPES:
            nodes = parser.get_nodes_by_type(obj_type)
            
            if len(nodes) == 0:
                continue
            
            singular, plural = TYPE_NAMES.get(obj_type, (obj_type, obj_type + "s"))
            question = self.template_manager.fill_template(template, type_plural=plural)
            
            # 答案最大为10（与NuScenesQA一致）
            answer = str(min(len(nodes), 10))
            
            cameras = set()
            for uid in nodes[:10]:
                cameras.update(camera_mapper.get_object_cameras(uid))
            
            qa = self._create_qa_pair(
                parser, template, question, answer,
                target_objects=nodes,
                cameras=list(cameras),
                metadata={"obj_type": obj_type, "actual_count": len(nodes)}
            )
            qa_pairs.append(qa)
        
        return qa_pairs
    
    def _generate_count_status_questions(self, parser: SceneGraphParser,
                                         camera_mapper: CameraMapper) -> List[QAPair]:
        """生成状态计数问题：What number of {status} {type} are there?"""
        qa_pairs = []
        template = self.template_manager.get_template("L0_count_status")
        
        for obj_type in OBJECT_TYPES:
            for status in parser.statuses_present:
                nodes = parser.get_nodes_by_type_and_status(obj_type, status)
                
                if len(nodes) == 0:
                    continue
                
                # 采样率50%
                if random.random() > 0.5:
                    continue
                
                singular, plural = TYPE_NAMES.get(obj_type, (obj_type, obj_type + "s"))
                question = self.template_manager.fill_template(
                    template,
                    status=status,
                    type_plural=plural
                )
                answer = str(min(len(nodes), 10))
                
                cameras = set()
                for uid in nodes[:10]:
                    cameras.update(camera_mapper.get_object_cameras(uid))
                
                qa = self._create_qa_pair(
                    parser, template, question, answer,
                    target_objects=nodes,
                    cameras=list(cameras),
                    metadata={"obj_type": obj_type, "status": status, "actual_count": len(nodes)}
                )
                qa_pairs.append(qa)
        
        return qa_pairs
    
    # ==================== 状态查询问题 ====================
    def _generate_status_query_questions(self, parser: SceneGraphParser,
                                         camera_mapper: CameraMapper) -> List[QAPair]:
        """生成状态查询问题：What is the status of {obj_id}?"""
        qa_pairs = []
        template = self.template_manager.get_template("L0_status_query")
        
        for uid, node in parser.nodes.items():
            if uid == "ego":
                continue
            
            status = node.get("status")
            if not status or status == "unknown":
                continue
            
            # 采样率30%（避免太多）
            if random.random() > 0.3:
                continue
            
            question = self.template_manager.fill_template(template, obj_id=uid)
            answer = status
            
            cameras = camera_mapper.get_object_cameras(uid)
            
            qa = self._create_qa_pair(
                parser, template, question, answer,
                target_objects=[uid],
                cameras=cameras,
                metadata={"obj_type": node["type"]}
            )
            qa_pairs.append(qa)
        
        return qa_pairs
    
    # ==================== 对象查询问题 ====================
    def _generate_object_status_questions(self, parser: SceneGraphParser,
                                          camera_mapper: CameraMapper) -> List[QAPair]:
        """生成对象查询问题：What is the {status} thing?"""
        qa_pairs = []
        template = self.template_manager.get_template("L0_object_status")
        
        for status in parser.statuses_present:
            nodes = parser.get_nodes_by_status(status)
            
            if len(nodes) == 0:
                continue
            
            # 只在该状态下对象唯一时生成（否则答案不明确）
            if len(nodes) != 1:
                continue
            
            uid = nodes[0]
            node = parser.get_node(uid)
            
            question = self.template_manager.fill_template(template, status=status)
            
            # 答案是对象类型
            obj_type = node["type"]
            singular, _ = TYPE_NAMES.get(obj_type, (obj_type, obj_type))
            answer = singular
            
            cameras = camera_mapper.get_object_cameras(uid)
            
            qa = self._create_qa_pair(
                parser, template, question, answer,
                target_objects=[uid],
                cameras=cameras,
                metadata={"obj_id": uid, "status": status}
            )
            qa_pairs.append(qa)
        
        return qa_pairs


def test_generator():
    """测试L0生成器"""
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
    print("Testing L0 Question Generator")
    print("="*60)
    
    # 创建生成器
    generator = L0QuestionGenerator()
    
    # 生成问答对
    qa_pairs = generator.generate(scene_data)
    
    print(f"\nGenerated {len(qa_pairs)} QA pairs\n")
    
    # 按类型统计
    from collections import Counter
    type_counts = Counter(qa.question_type for qa in qa_pairs)
    print("By question type:")
    for qtype, count in type_counts.items():
        print(f"  {qtype:12s}: {count:3d}")
    
    temporal_count = sum(1 for qa in qa_pairs if qa.requires_temporal)
    print(f"\nRequires temporal: {temporal_count}/{len(qa_pairs)}")
    
    # 显示示例
    print("\n" + "="*60)
    print("Sample QA Pairs")
    print("="*60)
    
    for i, qa in enumerate(qa_pairs[:5], 1):
        print(f"\n[{i}] {qa.question_type.upper()}")
        print(f"Q: {qa.question}")
        print(f"A: {qa.answer}")
        print(f"Template: {qa.template_id}")
        print(f"Temporal: {qa.requires_temporal}")
        print(f"Targets: {qa.target_objects[:3]}{'...' if len(qa.target_objects) > 3 else ''}")
        print(f"Cameras: {qa.cameras_for_analysis}")
        if qa.with_options:
            print(f"Options: {qa.with_options['formatted_options']}")
            print(f"Answer: {qa.with_options['answer_label']}")
    
    # 保存结果
    output_path = Path(__file__).parent / "test_output_L0.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump([qa.to_dict() for qa in qa_pairs], f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Results saved to: {output_path}")


if __name__ == "__main__":
    test_generator()
