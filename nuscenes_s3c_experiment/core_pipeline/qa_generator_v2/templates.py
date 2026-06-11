"""
QA Templates - 问答模板定义
参照NuScenesQA的5种问题类型，使用Source Frame和精确对象ID
"""
from typing import Dict, List, Optional
from dataclasses import dataclass
import random

try:
    from .config import TYPE_NAMES, STATUS_DISPLAY_NAMES
except ImportError:
    from config import TYPE_NAMES, STATUS_DISPLAY_NAMES


@dataclass
class QATemplate:
    """问答模板"""
    template_id: str
    question_type: str      # exist, count, status, object, comparison
    difficulty: str         # L0, L1, L2
    template: str           # 问题模板字符串
    answer_type: str        # bool, number, type, status
    requires_temporal: bool = False  # 是否需要多帧判断
    description: str = ""


class TemplateManager:
    """模板管理器"""
    
    # ==================== L0: 单对象属性查询 ====================
    L0_TEMPLATES = [
        # 存在性查询
        QATemplate(
            template_id="L0_exist_type",
            question_type="exist",
            difficulty="L0",
            template="Are there any {type_plural}?",
            answer_type="bool",
            description="查询某类型对象是否存在"
        ),
        QATemplate(
            template_id="L0_exist_type_visible",
            question_type="exist",
            difficulty="L0",
            template="Are any {type_plural} visible?",
            answer_type="bool",
            description="查询某类型对象是否可见"
        ),
        QATemplate(
            template_id="L0_exist_status",
            question_type="exist",
            difficulty="L0",
            template="Are any {status} {type_plural} visible?",
            answer_type="bool",
            requires_temporal=True,
            description="查询某状态的对象是否存在"
        ),
        QATemplate(
            template_id="L0_exist_status_alt",
            question_type="exist",
            difficulty="L0",
            template="Are there any {status} {type_plural}?",
            answer_type="bool",
            requires_temporal=True,
            description="查询某状态的对象是否存在(变体)"
        ),
        QATemplate(
            template_id="L0_exist_things",
            question_type="exist",
            difficulty="L0",
            template="Are there any things?",
            answer_type="bool",
            description="查询是否有任何对象（泛指）"
        ),
        
        # 计数查询
        QATemplate(
            template_id="L0_count_type",
            question_type="count",
            difficulty="L0",
            template="How many {type_plural} are there?",
            answer_type="number",
            description="统计某类型对象数量"
        ),
        QATemplate(
            template_id="L0_count_status",
            question_type="count",
            difficulty="L0",
            template="What number of {status} {type_plural} are there?",
            answer_type="number",
            requires_temporal=True,
            description="统计某状态的对象数量"
        ),
        QATemplate(
            template_id="L0_count_status_alt",
            question_type="count",
            difficulty="L0",
            template="How many {status} {type_plural} are there?",
            answer_type="number",
            requires_temporal=True,
            description="统计某状态的对象数量(变体)"
        ),
        
        # 状态查询
        QATemplate(
            template_id="L0_status_query",
            question_type="status",
            difficulty="L0",
            template="What is the status of {obj_id}?",
            answer_type="status",
            requires_temporal=True,
            description="查询指定对象的状态"
        ),
        QATemplate(
            template_id="L0_status_query_alt",
            question_type="status",
            difficulty="L0",
            template="The {obj_type} ({obj_id}) is in what status?",
            answer_type="status",
            requires_temporal=True,
            description="查询指定对象的状态（变体）"
        ),
        QATemplate(
            template_id="L0_status_query_alt2",
            question_type="status",
            difficulty="L0",
            template="What status is {obj_id}?",
            answer_type="status",
            requires_temporal=True,
            description="查询指定对象的状态（变体2）"
        ),
        QATemplate(
            template_id="L0_status_query_thereis",
            question_type="status",
            difficulty="L0",
            template="There is a {obj_type} ({obj_id}); what status is it?",
            answer_type="status",
            requires_temporal=True,
            description="查询指定对象的状态(There is句式)"
        ),
        
        # 对象类型查询
        QATemplate(
            template_id="L0_object_status",
            question_type="object",
            difficulty="L0",
            template="What is the {status} thing?",
            answer_type="type",
            requires_temporal=True,
            description="查询某状态的对象类型"
        ),
        QATemplate(
            template_id="L0_object_status_alt",
            question_type="object",
            difficulty="L0",
            template="There is a {status} thing; what is it?",
            answer_type="type",
            requires_temporal=True,
            description="查询某状态的对象类型(There is句式)"
        ),
        QATemplate(
            template_id="L0_object_status_alt2",
            question_type="object",
            difficulty="L0",
            template="The {status} {obj_type} is what?",
            answer_type="type",
            requires_temporal=True,
            description="查询某状态对象类型(is what句式)"
        ),
        
        # 比较查询 - L0也应该有简单的same status查询
        QATemplate(
            template_id="L0_compare_status",
            question_type="comparison",
            difficulty="L0",
            template="Do {obj1_id} and {obj2_id} have the same status?",
            answer_type="bool",
            requires_temporal=True,
            description="比较两个对象的状态是否相同"
        ),
        QATemplate(
            template_id="L0_compare_status_alt",
            question_type="comparison",
            difficulty="L0",
            template="Is the status of {obj1_id} the same as {obj2_id}?",
            answer_type="bool",
            requires_temporal=True,
            description="比较两个对象的状态(变体)"
        ),
    ]
    
    # ==================== L1: 单跳空间关系查询 ====================
    L1_TEMPLATES = [
        # 存在性查询（涉及方向）
        QATemplate(
            template_id="L1_exist_direction",
            question_type="exist",
            difficulty="L1",
            template="Are there any {type_plural} to the {direction} of {ref_id}?",
            answer_type="bool",
            description="查询某方向是否有某类型对象"
        ),
        QATemplate(
            template_id="L1_exist_direction_status",
            question_type="exist",
            difficulty="L1",
            template="Are there any {status} {type_plural} to the {direction} of {ref_id}?",
            answer_type="bool",
            requires_temporal=True,
            description="查询某方向是否有某状态的对象"
        ),
        QATemplate(
            template_id="L1_exist_direction_thereis",
            question_type="exist",
            difficulty="L1",
            template="There is a {ref_status} {ref_type}; are there any {type_plural} to the {direction} of it?",
            answer_type="bool",
            requires_temporal=True,
            description="There is句式的方向存在性查询"
        ),
        QATemplate(
            template_id="L1_exist_direction_status_thereis",
            question_type="exist",
            difficulty="L1",
            template="There is a {ref_status} {ref_type}; are there any {status} {type_plural} to the {direction} of it?",
            answer_type="bool",
            requires_temporal=True,
            description="There is句式的方向+状态存在性查询"
        ),
        
        # 计数查询（涉及方向）
        QATemplate(
            template_id="L1_count_direction",
            question_type="count",
            difficulty="L1",
            template="How many {type_plural} are to the {direction} of {ref_id}?",
            answer_type="number",
            description="统计某方向的对象数量"
        ),
        QATemplate(
            template_id="L1_count_direction_status",
            question_type="count",
            difficulty="L1",
            template="What number of {status} {type_plural} are to the {direction} of {ref_id}?",
            answer_type="number",
            requires_temporal=True,
            description="统计某方向某状态的对象数量"
        ),
        QATemplate(
            template_id="L1_count_direction_thereis",
            question_type="count",
            difficulty="L1",
            template="There is a {ref_status} {ref_type}; what number of {type_plural} are to the {direction} of it?",
            answer_type="number",
            requires_temporal=True,
            description="There is句式的方向计数"
        ),
        QATemplate(
            template_id="L1_count_direction_things",
            question_type="count",
            difficulty="L1",
            template="What number of things are to the {direction} of {ref_id}?",
            answer_type="number",
            description="统计某方向的所有对象数量(thing泛指)"
        ),
        
        # 状态查询（涉及方向）
        QATemplate(
            template_id="L1_status_direction",
            question_type="status",
            difficulty="L1",
            template="There is a {target_type} to the {direction} of {ref_id}; what is its status?",
            answer_type="status",
            requires_temporal=True,
            description="查询某方向对象的状态"
        ),
        QATemplate(
            template_id="L1_status_direction_alt",
            question_type="status",
            difficulty="L1",
            template="What is the status of the {target_type} that is to the {direction} of {ref_id}?",
            answer_type="status",
            requires_temporal=True,
            description="查询某方向对象的状态(that is句式)"
        ),
        QATemplate(
            template_id="L1_status_direction_alt2",
            question_type="status",
            difficulty="L1",
            template="What status is the {target_type} to the {direction} of {ref_id}?",
            answer_type="status",
            requires_temporal=True,
            description="查询某方向对象的状态(变体)"
        ),
        
        # 对象查询（涉及方向）
        QATemplate(
            template_id="L1_object_direction",
            question_type="object",
            difficulty="L1",
            template="There is a {status} thing to the {direction} of {ref_id}; what is it?",
            answer_type="type",
            requires_temporal=True,
            description="查询某方向某状态的对象类型"
        ),
        QATemplate(
            template_id="L1_object_direction_alt",
            question_type="object",
            difficulty="L1",
            template="What is the {status} {target_type} to the {direction} of {ref_id}?",
            answer_type="type",
            requires_temporal=True,
            description="查询某方向某状态的对象类型(变体)"
        ),
        QATemplate(
            template_id="L1_object_direction_iswhat",
            question_type="object",
            difficulty="L1",
            template="The {status} thing that is to the {direction} of {ref_id} is what?",
            answer_type="type",
            requires_temporal=True,
            description="查询某方向某状态的对象类型(is what句式)"
        ),
        
        # 比较查询（L1中的comparison通常涉及方向）
        QATemplate(
            template_id="L1_compare_direction",
            question_type="comparison",
            difficulty="L1",
            template="There is a {type1} to the {direction} of {ref_id}; does it have the same status as {obj2_id}?",
            answer_type="bool",
            requires_temporal=True,
            description="比较方向对象与另一对象的状态"
        ),
        QATemplate(
            template_id="L1_compare_direction_alt",
            question_type="comparison",
            difficulty="L1",
            template="Is the status of {obj1_id} the same as the {type2} to the {direction} of {ref_id}?",
            answer_type="bool",
            requires_temporal=True,
            description="比较对象与方向对象的状态(变体)"
        ),
    ]
    
    # ==================== L2: 两跳空间关系查询 ====================
    L2_TEMPLATES = [
        # ========== 链式存在性查询 ==========
        QATemplate(
            template_id="L2_exist_chain",
            question_type="exist",
            difficulty="L2",
            template="Is there a {target_type} to the {direction1} of the {mid_type} that is to the {direction2} of {ref_id}?",
            answer_type="bool",
            description="链式方位存在性查询（两跳）"
        ),
        QATemplate(
            template_id="L2_exist_chain_status",
            question_type="exist",
            difficulty="L2",
            template="Is there a {status} {target_type} to the {direction1} of the {mid_id} that is to the {direction2} of {ref_id}?",
            answer_type="bool",
            requires_temporal=True,
            description="链式方位+状态存在性查询"
        ),
        QATemplate(
            template_id="L2_exist_chain_with_mid_status",
            question_type="exist",
            difficulty="L2",
            template="There is a {mid_status} {mid_type}; are there any {target_type} to the {direction} of it?",
            answer_type="bool",
            requires_temporal=True,
            description="先确定中间对象状态，再查询方位"
        ),
        
        # ========== 链式对象查询 ==========
        QATemplate(
            template_id="L2_object_chain",
            question_type="object",
            difficulty="L2",
            template="There is a thing to the {direction1} of the {mid_type} that is to the {direction2} of {ref_id}; what is it?",
            answer_type="type",
            description="链式方位对象查询（两跳）"
        ),
        QATemplate(
            template_id="L2_object_chain_with_status",
            question_type="object",
            difficulty="L2",
            template="There is a {status} thing to the {direction1} of the {mid_id} that is to the {direction2} of {ref_id}; what is it?",
            answer_type="type",
            requires_temporal=True,
            description="链式方位+状态对象查询"
        ),
        
        # ========== 复合方向查询 ==========
        QATemplate(
            template_id="L2_object_two_directions",
            question_type="object",
            difficulty="L2",
            template="There is a thing that is both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}; what is it?",
            answer_type="type",
            description="查询同时满足两个方位条件的对象"
        ),
        QATemplate(
            template_id="L2_exist_two_directions",
            question_type="exist",
            difficulty="L2",
            template="Is there a {target_type} that is both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}?",
            answer_type="bool",
            description="两个方位交集存在性查询"
        ),
        QATemplate(
            template_id="L2_count_two_directions",
            question_type="count",
            difficulty="L2",
            template="How many {type_plural} are both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}?",
            answer_type="number",
            description="两个方位交集计数查询"
        ),
        
        # ========== 同状态相关查询 ==========
        QATemplate(
            template_id="L2_count_same_status",
            question_type="count",
            difficulty="L2",
            template="How many other things have the same status as {ref_id}?",
            answer_type="number",
            requires_temporal=True,
            description="统计与指定对象相同状态的其他对象数量"
        ),
        QATemplate(
            template_id="L2_count_same_status_alt",
            question_type="count",
            difficulty="L2",
            template="What number of other {type_plural} are there of the same status as {ref_id}?",
            answer_type="number",
            requires_temporal=True,
            description="统计与指定对象相同状态的其他同类对象数量"
        ),
        QATemplate(
            template_id="L2_count_same_status_alt2",
            question_type="count",
            difficulty="L2",
            template="How many other {type_plural} are in the same status as {ref_id}?",
            answer_type="number",
            requires_temporal=True,
            description="统计与指定对象相同状态的其他同类对象(in same status)"
        ),
        QATemplate(
            template_id="L2_exist_same_status",
            question_type="exist",
            difficulty="L2",
            template="Is there another {ref_type} that has the same status as {ref_id}?",
            answer_type="bool",
            requires_temporal=True,
            description="查询是否有另一个同类型同状态对象"
        ),
        QATemplate(
            template_id="L2_count_same_status_in_direction",
            question_type="count",
            difficulty="L2",
            template="What number of things in the same status as {ref1_id} are to the {direction} of {ref2_id}?",
            answer_type="number",
            requires_temporal=True,
            description="统计某方向与参考对象同状态的对象"
        ),
        
        # ========== 链式状态查询 ==========
        QATemplate(
            template_id="L2_status_chain",
            question_type="status",
            difficulty="L2",
            template="What is the status of the {target_type} to the {direction1} of the {mid_id} that is to the {direction2} of {ref_id}?",
            answer_type="status",
            requires_temporal=True,
            description="链式方位状态查询（两跳）"
        ),
        QATemplate(
            template_id="L2_status_chain_simple",
            question_type="status",
            difficulty="L2",
            template="There is a {target_type} to the {direction} of {ref_id}; what is its status?",
            answer_type="status",
            requires_temporal=True,
            description="链式方位状态查询（简化版）"
        ),
        
        # ========== 链式比较查询 ==========
        QATemplate(
            template_id="L2_compare_chain",
            question_type="comparison",
            difficulty="L2",
            template="Does {obj1_id} have the same status as the {obj2_type} to the {direction} of {ref_id}?",
            answer_type="bool",
            requires_temporal=True,
            description="比较对象与链式方位对象的状态"
        ),
        QATemplate(
            template_id="L2_compare_chain_thereis",
            question_type="comparison",
            difficulty="L2",
            template="There is a {type1} to the {direction} of {ref_id}; is it the same status as {obj2_id}?",
            answer_type="bool",
            requires_temporal=True,
            description="比较链式方位对象与另一对象的状态(There is句式)"
        ),
        QATemplate(
            template_id="L2_compare_two_chains",
            question_type="comparison",
            difficulty="L2",
            template="Does the {type1} to the {direction1} of {ref1_id} have the same status as the {type2} to the {direction2} of {ref2_id}?",
            answer_type="bool",
            requires_temporal=True,
            description="比较两个链式方位对象的状态"
        ),
        QATemplate(
            template_id="L2_compare_two_chains_alt",
            question_type="comparison",
            difficulty="L2",
            template="Do the {type1} to the {direction1} of {ref1_id} and the {type2} to the {direction2} of {ref2_id} have the same status?",
            answer_type="bool",
            requires_temporal=True,
            description="比较两个链式方位对象的状态(Do...and...句式)"
        ),
        QATemplate(
            template_id="L2_compare_isstatus_same",
            question_type="comparison",
            difficulty="L2",
            template="Is the status of {obj1_id} the same as the {type2} to the {direction} of {ref_id}?",
            answer_type="bool",
            requires_temporal=True,
            description="比较对象与链式方位对象的状态(is status same句式)"
        ),
        
        # ========== 特殊复杂查询 ==========
        QATemplate(
            template_id="L2_exist_another_same_status",
            question_type="exist",
            difficulty="L2",
            template="There is a {ref_type} ({ref_id}); is there another {ref_type} in the same status?",
            answer_type="bool",
            requires_temporal=True,
            description="查询是否有另一个同类型同状态对象"
        ),
        QATemplate(
            template_id="L2_count_direction_filter_status",
            question_type="count",
            difficulty="L2",
            template="What number of things to the {direction} of {ref_id} are in the same status as {status_ref_id}?",
            answer_type="number",
            requires_temporal=True,
            description="统计某方向且与另一对象同状态的对象"
        ),
        
        # ========== 两个方向复合查询(both...and...) ==========
        QATemplate(
            template_id="L2_object_both_directions",
            question_type="object",
            difficulty="L2",
            template="There is a thing that is both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}; what is it?",
            answer_type="type",
            description="查询同时满足两个方位的对象(There is both句式)"
        ),
        QATemplate(
            template_id="L2_status_both_directions",
            question_type="status",
            difficulty="L2",
            template="There is a {target_type} that is both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}; what is its status?",
            answer_type="status",
            requires_temporal=True,
            description="查询同时满足两个方位的对象状态"
        ),
    ]
    
    def __init__(self):
        """初始化模板管理器"""
        self.templates: Dict[str, QATemplate] = {}
        self.templates_by_type: Dict[str, List[QATemplate]] = {}
        self.templates_by_difficulty: Dict[str, List[QATemplate]] = {}
        
        self._register_templates()
    
    def _register_templates(self):
        """注册所有模板"""
        all_templates = self.L0_TEMPLATES + self.L1_TEMPLATES + self.L2_TEMPLATES
        
        for template in all_templates:
            self.templates[template.template_id] = template
            
            # 按类型索引
            if template.question_type not in self.templates_by_type:
                self.templates_by_type[template.question_type] = []
            self.templates_by_type[template.question_type].append(template)
            
            # 按难度索引
            if template.difficulty not in self.templates_by_difficulty:
                self.templates_by_difficulty[template.difficulty] = []
            self.templates_by_difficulty[template.difficulty].append(template)
    
    def get_template(self, template_id: str) -> Optional[QATemplate]:
        """获取指定模板"""
        return self.templates.get(template_id)
    
    def get_templates(self, 
                     question_type: Optional[str] = None,
                     difficulty: Optional[str] = None,
                     requires_temporal: Optional[bool] = None) -> List[QATemplate]:
        """
        获取模板列表（支持过滤）
        
        Args:
            question_type: 问题类型过滤
            difficulty: 难度过滤
            requires_temporal: 是否需要多帧
        """
        templates = list(self.templates.values())
        
        if question_type:
            templates = [t for t in templates if t.question_type == question_type]
        
        if difficulty:
            templates = [t for t in templates if t.difficulty == difficulty]
        
        if requires_temporal is not None:
            templates = [t for t in templates if t.requires_temporal == requires_temporal]
        
        return templates
    
    def sample_template(self,
                       question_type: Optional[str] = None,
                       difficulty: Optional[str] = None) -> Optional[QATemplate]:
        """
        随机采样一个模板
        
        Args:
            question_type: 问题类型过滤
            difficulty: 难度过滤
        """
        templates = self.get_templates(question_type=question_type, difficulty=difficulty)
        return random.choice(templates) if templates else None
    
    def fill_template(self, template: QATemplate, **kwargs) -> str:
        """
        填充模板生成问题
        
        Args:
            template: 模板对象
            **kwargs: 模板参数
                - type_plural: 对象类型复数形式
                - type_singular: 对象类型单数形式
                - obj_type: 对象类型
                - obj_id: 对象ID
                - status: 状态
        
        Returns:
            生成的问题文本
        """
        params = dict(kwargs)
        
        # 处理类型名称
        if "type_plural" in kwargs:
            obj_type = kwargs.get("type_plural", "")
            # 查找正确的复数形式
            for t, (singular, plural) in TYPE_NAMES.items():
                if obj_type == t or obj_type == plural or obj_type == singular:
                    params["type_plural"] = plural
                    params["type_singular"] = singular
                    break
        
        if "obj_type" in kwargs:
            obj_type = kwargs["obj_type"]
            singular, plural = TYPE_NAMES.get(obj_type, (obj_type, obj_type + "s"))
            params["type_singular"] = singular
            params["type_plural"] = plural
        
        # 处理状态显示名称
        if "status" in kwargs:
            status = kwargs["status"]
            params["status"] = STATUS_DISPLAY_NAMES.get(status, status)
        
        # 填充模板
        try:
            question = template.template.format(**params)
        except KeyError as e:
            raise ValueError(f"Missing template parameter: {e}, required params: {template.template}")
        
        return question
    
    def get_summary(self) -> Dict:
        """获取模板统计信息"""
        return {
            "total_templates": len(self.templates),
            "by_type": {qtype: len(temps) for qtype, temps in self.templates_by_type.items()},
            "by_difficulty": {diff: len(temps) for diff, temps in self.templates_by_difficulty.items()},
            "temporal_required": len([t for t in self.templates.values() if t.requires_temporal]),
        }
    
    @classmethod
    def export_templates_for_llm(cls, level: str = None) -> str:
        """
        导出模板文档供LLM参考
        
        Args:
            level: 指定级别 L0/L1/L2，None则导出全部
        
        Returns:
            格式化的模板文档字符串
        """
        lines = []
        
        if level is None or level == 'L0':
            lines.append("## L0模板（单对象属性查询）")
            for tmpl in cls.L0_TEMPLATES:
                lines.append(f'- [{tmpl.question_type}] "{tmpl.template}"')
            lines.append("")
        
        if level is None or level == 'L1':
            lines.append("## L1模板（单跳空间关系）")
            for tmpl in cls.L1_TEMPLATES:
                lines.append(f'- [{tmpl.question_type}] "{tmpl.template}"')
            lines.append("")
        
        if level is None or level == 'L2':
            lines.append("## L2模板（两跳路径查询）")
            for tmpl in cls.L2_TEMPLATES:
                lines.append(f'- [{tmpl.question_type}] "{tmpl.template}"')
        
        return '\n'.join(lines)


# ==================== 选项生成器 ====================
class OptionGenerator:
    """选择题选项生成器"""
    
    @staticmethod
    def generate_options(answer: str, 
                        answer_type: str,
                        scene_context: Optional[Dict] = None,
                        num_options: int = 4) -> Dict:
        """
        生成选择题选项
        
        Args:
            answer: 正确答案
            answer_type: 答案类型 (bool, number, type, status)
            scene_context: 场景上下文（用于生成更真实的干扰项）
            num_options: 选项数量
        
        Returns:
            包含options和answer_idx的字典
        """
        if answer_type == "bool":
            return OptionGenerator._generate_bool_options(answer)
        elif answer_type == "number":
            return OptionGenerator._generate_number_options(answer, num_options)
        elif answer_type == "type":
            return OptionGenerator._generate_type_options(answer, scene_context, num_options)
        elif answer_type == "status":
            return OptionGenerator._generate_status_options(answer, num_options)
        else:
            return {"options": [answer], "answer_idx": 0}
    
    @staticmethod
    def _generate_bool_options(answer: str) -> Dict:
        """生成是非题选项"""
        options = ["yes", "no"]
        answer_idx = 0 if answer.lower() in ["yes", "true"] else 1
        
        return {
            "options": options,
            "formatted_options": ["(A) yes", "(B) no"],
            "answer_idx": answer_idx,
            "answer_label": "A" if answer_idx == 0 else "B",
        }
    
    @staticmethod
    def _generate_number_options(answer: str, num_options: int) -> Dict:
        """生成数字选项"""
        try:
            correct_num = int(answer)
        except ValueError:
            return {"options": [answer], "answer_idx": 0}
        
        # 生成干扰项：±1, ±2, 0, 10等
        candidates = set()
        candidates.add(correct_num)
        
        # 添加邻近数字
        for delta in [-2, -1, 1, 2]:
            val = correct_num + delta
            if val >= 0 and val <= 10:
                candidates.add(val)
        
        # 添加特殊值
        candidates.add(0)
        if correct_num > 0:
            candidates.add(10)
        
        # 转为列表并排序
        options = sorted(list(candidates))[:num_options]
        if correct_num not in options:
            options[-1] = correct_num
            options = sorted(options)
        
        options = [str(x) for x in options]
        answer_idx = options.index(str(correct_num))
        
        labels = ["A", "B", "C", "D"][:len(options)]
        formatted = [f"({label}) {opt}" for label, opt in zip(labels, options)]
        
        return {
            "options": options,
            "formatted_options": formatted,
            "answer_idx": answer_idx,
            "answer_label": labels[answer_idx],
        }
    
    @staticmethod
    def _generate_type_options(answer: str, scene_context: Optional[Dict], num_options: int) -> Dict:
        """生成对象类型选项"""
        from config import OBJECT_TYPES
        
        candidates = [answer]
        
        # 优先从场景中的对象类型选择（更真实）
        if scene_context and "object_types" in scene_context:
            scene_types = [t for t in scene_context["object_types"] if t != answer]
            candidates.extend(scene_types[:num_options-1])
        
        # 不足则从全部类型中随机选择
        while len(candidates) < num_options:
            obj_type = random.choice(OBJECT_TYPES)
            singular, _ = TYPE_NAMES.get(obj_type, (obj_type, obj_type))
            if singular not in candidates:
                candidates.append(singular)
        
        options = candidates[:num_options]
        random.shuffle(options)
        answer_idx = options.index(answer)
        
        labels = ["A", "B", "C", "D"][:len(options)]
        formatted = [f"({label}) {opt}" for label, opt in zip(labels, options)]
        
        return {
            "options": options,
            "formatted_options": formatted,
            "answer_idx": answer_idx,
            "answer_label": labels[answer_idx],
        }
    
    @staticmethod
    def _generate_status_options(answer: str, num_options: int) -> Dict:
        """生成状态选项"""
        from config import VEHICLE_STATUSES, PEDESTRIAN_STATUSES, CYCLE_STATUSES
        
        all_statuses = list(set(VEHICLE_STATUSES + PEDESTRIAN_STATUSES + CYCLE_STATUSES))
        
        # 映射到显示名称
        display_answer = STATUS_DISPLAY_NAMES.get(answer, answer)
        candidates = [display_answer]
        
        for status in all_statuses:
            display_status = STATUS_DISPLAY_NAMES.get(status, status)
            if display_status != display_answer and display_status not in candidates:
                candidates.append(display_status)
                if len(candidates) >= num_options:
                    break
        
        options = candidates[:num_options]
        random.shuffle(options)
        answer_idx = options.index(display_answer)
        
        labels = ["A", "B", "C", "D"][:len(options)]
        formatted = [f"({label}) {opt}" for label, opt in zip(labels, options)]
        
        return {
            "options": options,
            "formatted_options": formatted,
            "answer_idx": answer_idx,
            "answer_label": labels[answer_idx],
        }


def test_templates():
    """测试模板系统"""
    manager = TemplateManager()
    
    print("="*60)
    print("Template Manager Summary")
    print("="*60)
    print(manager.get_summary())
    
    print("\n" + "="*60)
    print("Sample L0 Templates")
    print("="*60)
    
    # 测试填充
    template = manager.get_template("L0_exist_type")
    q1 = manager.fill_template(template, type_plural="cars")
    print(f"Q: {q1}")
    
    template = manager.get_template("L0_status_query")
    q2 = manager.fill_template(template, obj_id="car1")
    print(f"Q: {q2}")
    
    template = manager.get_template("L0_count_status")
    q3 = manager.fill_template(template, status="moving", type_plural="pedestrians")
    print(f"Q: {q3}")
    
    print("\n" + "="*60)
    print("Sample Options")
    print("="*60)
    
    opts = OptionGenerator.generate_options("yes", "bool")
    print(f"Bool: {opts}")
    
    opts = OptionGenerator.generate_options("5", "number")
    print(f"Number: {opts}")
    
    opts = OptionGenerator.generate_options("moving", "status")
    print(f"Status: {opts}")


if __name__ == "__main__":
    test_templates()
