"""
QA Templates - 问答模板定义

设计原则（已更新）：
- L0: 单对象属性查询（exist/status/comparison，无count）
- L1: 单跳空间关系查询（exist/status/object/comparison，无count）
- L2: 严格首尾相连两连边查询（A→B→C链式，无count类，无多锚点交集）
  * 严格L2 = 前一条关系边的尾 = 后一条关系边的首
  * 即：ref(A)--dir1-->mid(B)--dir2-->target(C)，问C的属性
  * 复杂情境变体（含status双向边）也保留
- 属性约束：只使用CV模型可视判断的属性
  * 保留：type, status (stopped/moving/parked/with_rider/without_rider/standing), direction
  * 移除：速度数值、TTC、精确距离数值（仅保留near/mid/far级别）

所有模板基于Source Frame：
- 方向描述以被描述对象（reference object）的朝向为基准
- 例如："to the back-right of truck1" 表示在truck1自身朝向的右后方
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from .config import TYPE_NAMES, STATUS_DISPLAY_NAMES


@dataclass
class QATemplate:
    """问答模板"""
    template_id: str
    question_type: str      # exist, count, status, object, comparison
    difficulty: str         # L0, L1, L2
    template: str           # 问题模板字符串
    answer_type: str        # bool, number, type, status
    description: str        # 模板描述


class QATemplates:
    """问答模板管理器"""
    
    # ==================== L0: 单对象属性查询 ====================
    # 注：已移除 L0_count_type 和 L0_count_status（count类不符合缺口即为答案原则）
    L0_TEMPLATES = [
        QATemplate(
            template_id="L0_exist_type",
            question_type="exist",
            difficulty="L0",
            template="Are there any {type_plural}?",
            answer_type="bool",
            description="查询某类型对象是否存在"
        ),
        QATemplate(
            template_id="L0_exist_status",
            question_type="exist",
            difficulty="L0",
            template="Are there any {status} {type_plural}?",
            answer_type="bool",
            description="查询某状态的对象是否存在"
        ),
        QATemplate(
            template_id="L0_status_query",
            question_type="status",
            difficulty="L0",
            template="What is the status of {ref_type} ({ref_id})?",
            answer_type="status",
            description="查询指定对象的状态"
        ),
    ]
    
    # ==================== L1: 单跳空间关系查询 ====================
    # 注：已移除 L1_count_direction 和 L1_count_direction_status（count类）
    L1_TEMPLATES = [
        # 存在性查询
        QATemplate(
            template_id="L1_exist_direction",
            question_type="exist",
            difficulty="L1",
            template="Are there any {type_plural} to the {direction} of {ref_type} ({ref_id})?",
            answer_type="bool",
            description="查询某方位是否有某类型对象"
        ),
        QATemplate(
            template_id="L1_exist_direction_status",
            question_type="exist",
            difficulty="L1",
            template="Are there any {status} {type_plural} to the {direction} of {ref_type} ({ref_id})?",
            answer_type="bool",
            description="查询某方位是否有某状态的对象"
        ),
        # 对象查询
        QATemplate(
            template_id="L1_object_direction",
            question_type="object",
            difficulty="L1",
            template="What is to the {direction} of {ref_type} ({ref_id})?",
            answer_type="type",
            description="查询某方位的对象类型"
        ),
        QATemplate(
            template_id="L1_object_direction_specific",
            question_type="object",
            difficulty="L1",
            template="What is the {target_type} to the {direction} of {ref_type} ({ref_id})?",
            answer_type="type",
            description="查询某方位特定类型的对象"
        ),
        # 状态查询
        QATemplate(
            template_id="L1_status_direction",
            question_type="status",
            difficulty="L1",
            template="What is the status of the {target_type} ({target_id}) to the {direction} of {ref_type} ({ref_id})?",
            answer_type="status",
            description="查询某方位对象的状态"
        ),
        # 比较查询
        QATemplate(
            template_id="L1_compare_status",
            question_type="comparison",
            difficulty="L1",
            template="Does {obj1_type} ({obj1_id}) have the same status as {obj2_type} ({obj2_id})?",
            answer_type="bool",
            description="比较两个对象的状态是否相同"
        ),
        QATemplate(
            template_id="L1_compare_direction",
            question_type="comparison",
            difficulty="L1",
            template="Is {obj1_type} ({obj1_id}) to the {direction} of {ref_type} ({ref_id}) the same status as {obj2_type} ({obj2_id})?",
            answer_type="bool",
            description="比较方位对象与另一对象的状态"
        ),
    ]
    
    # ==================== L2: 严格首尾相连两连边查询 ====================
    # 模式定义：ref(A) --dir2--> mid(B) --dir1--> target(C)
    # 即 A是锚点，B是中间节点（前一边的尾=后一边的首），C是目标
    # 自然语言表达："the [C_type] to dir1 of the [B_type] that is to dir2 of [A_type] (A_id)"
    #
    # 已移除：
    #   L2_count_same_status  —— count类，且并非链式两连边模式
    #   L2_object_two_directions —— 多锚点交集（两L1的AND），非首尾相连链
    #
    # status可视作双向边：一侧可做约束条件，另一侧可做答案，增加覆盖维度
    L2_TEMPLATES = [
        QATemplate(
            template_id="L2_exist_chain",
            question_type="exist",
            difficulty="L2",
            template="Is there a {type_singular} to the {direction1} of the {mid_type} that is to the {direction2} of {ref_type} ({ref_id})?",
            answer_type="bool",
            description="链式方位存在性查询：ref--dir2-->mid--dir1-->target？"
        ),
        QATemplate(
            template_id="L2_status_chain",
            question_type="status",
            difficulty="L2",
            template="What is the status of the {target_type} to the {direction1} of the {mid_type} ({mid_id}) that is to the {direction2} of {ref_type} ({ref_id})?",
            answer_type="status",
            description="链式方位状态查询：A--dir2-->B--dir1-->C，问C的status"
        ),
        QATemplate(
            template_id="L2_compare_chain",
            question_type="comparison",
            difficulty="L2",
            template="Does the {obj1_type} ({obj1_id}) have the same status as the {obj2_type} to the {direction} of {ref_type} ({ref_id})?",
            answer_type="bool",
            description="比较直接对象与链式方位对象的status（status作双向边）"
        ),
        QATemplate(
            template_id="L2_exist_chain_status",
            question_type="exist",
            difficulty="L2",
            template="Is there a {status} {type_singular} to the {direction1} of the {mid_type} that is to the {direction2} of {ref_type} ({ref_id})?",
            answer_type="bool",
            description="链式方位+状态约束存在性查询（status作辅助边）"
        ),
    ]
    
    def __init__(self):
        """初始化模板管理器"""
        self.templates = {}
        self._register_templates()
    
    def _register_templates(self):
        """注册所有模板"""
        for template in self.L0_TEMPLATES + self.L1_TEMPLATES + self.L2_TEMPLATES:
            self.templates[template.template_id] = template
    
    def get_template(self, template_id: str) -> Optional[QATemplate]:
        """获取模板"""
        return self.templates.get(template_id)
    
    def get_templates_by_type(self, question_type: str) -> List[QATemplate]:
        """按问题类型获取模板"""
        return [t for t in self.templates.values() if t.question_type == question_type]
    
    def get_templates_by_difficulty(self, difficulty: str) -> List[QATemplate]:
        """按难度获取模板"""
        return [t for t in self.templates.values() if t.difficulty == difficulty]
    
    def fill_template(self, template: QATemplate, **kwargs) -> str:
        """填充模板生成问题"""
        question = template.template
        
        # 处理类型名称（单数/复数）
        if "type_singular" in kwargs:
            obj_type = kwargs["type_singular"]
            singular, plural = TYPE_NAMES.get(obj_type, (obj_type, obj_type + "s"))
            kwargs["type_singular"] = singular
            kwargs["type_plural"] = plural
        
        if "type_plural" in kwargs and "type_singular" not in kwargs:
            # type_plural 可能已经是复数形式，需要查找对应的正确复数
            input_plural = kwargs.get("type_plural", "")
            # 先检查是否已经是正确的复数形式
            found = False
            for obj_type, (singular, plural) in TYPE_NAMES.items():
                if input_plural == plural or input_plural == obj_type:
                    kwargs["type_plural"] = plural
                    found = True
                    break
            if not found:
                kwargs["type_plural"] = input_plural
        
        # 处理状态显示名称
        if "status" in kwargs:
            kwargs["status"] = STATUS_DISPLAY_NAMES.get(kwargs["status"], kwargs["status"])
        
        # 填充模板
        try:
            question = question.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing template parameter: {e}")
        
        return question
    
    def generate_options(self, answer: str, answer_type: str, 
                        num_options: int = 4, 
                        option_labels: List[str] = None) -> Dict[str, Any]:
        """
        生成选择题选项
        
        Args:
            answer: 正确答案
            answer_type: 答案类型 (bool, number, type, status)
            num_options: 选项数量
            option_labels: 选项标签 ["A", "B", "C", "D"]
        
        Returns:
            包含options和answer_idx的字典
        """
        if option_labels is None:
            option_labels = ["A", "B", "C", "D"][:num_options]
        
        options = []
        
        if answer_type == "bool":
            options = ["yes", "no"]
            answer_idx = 0 if answer.lower() == "yes" else 1
            
        elif answer_type == "number":
            correct_num = int(answer)
            # 生成干扰项
            candidates = list(range(max(0, correct_num - 2), correct_num + 3))
            candidates = [str(c) for c in candidates if c != correct_num and c >= 0 and c <= 10]
            # 确保正确答案在选项中
            options = [answer] + candidates[:num_options-1]
            options = sorted(options, key=lambda x: int(x))
            answer_idx = options.index(answer)
            
        elif answer_type == "type":
            from .config import OBJECT_TYPES
            options = [answer]
            for t in OBJECT_TYPES:
                if t != answer and len(options) < num_options:
                    singular, _ = TYPE_NAMES.get(t, (t, t))
                    if singular not in options:
                        options.append(singular)
            import random
            random.shuffle(options)
            answer_idx = options.index(answer)
            
        elif answer_type == "status":
            from .config import VEHICLE_STATUSES, PEDESTRIAN_STATUSES, CYCLE_STATUSES
            all_statuses = list(set(VEHICLE_STATUSES + PEDESTRIAN_STATUSES + CYCLE_STATUSES))
            display_answer = STATUS_DISPLAY_NAMES.get(answer, answer)
            options = [display_answer]
            for s in all_statuses:
                display_s = STATUS_DISPLAY_NAMES.get(s, s)
                if display_s != display_answer and len(options) < num_options:
                    options.append(display_s)
            import random
            random.shuffle(options)
            answer_idx = options.index(display_answer)
        
        # 格式化选项
        formatted_options = [f"({label}) {opt}" for label, opt in zip(option_labels, options)]
        
        return {
            "options": options,
            "formatted_options": formatted_options,
            "answer_idx": answer_idx,
            "answer_label": option_labels[answer_idx],
        }
