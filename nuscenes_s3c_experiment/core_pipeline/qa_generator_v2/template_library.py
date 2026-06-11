"""
Comprehensive QA Template Library — 四级结构 (4-Level Hierarchy)

设计原则:
  1. 题目面向CV模型，模型看到的是6相机标注视图，每个对象标有唯一ID（如 car1, ped3）
  2. 已知对象通过 {obj_id}/{ref_id} 引用，保证指代无歧义
  3. 聚合类查询（exist/count）使用 {type_plural}/{obj_type} 描述对象类别
  4. 程序可从场景图自动填充所有占位符，生成完整确定性问题
  5. 每个模板的 answer_logic 标签对应一个确定性计算函数
  6. required_params 是完整的“配方”，包含问题生成+答案计算所需的全部参数

占位符规范:
  {obj_id}              已知目标对象ID（如 "car1"）— 图片上可见
  {ref_id}              已知参照对象ID（如 "truck2"）— 图片上可见
  {obj_type}            对象类型单数（如 "car"）
  {type_plural}         对象类型复数（如 "cars"）
  {status}              运动状态（如 "moving", "stopped"）
  {direction}           8方向（如 "front", "front-left"）
  {distance_threshold}  距离阈值，米（如 "10", "20"）

四级结构:
  Level 1 (L):       L0 (节点覆盖), L1 (边覆盖), L2 (两跳路径覆盖)
  Level 2 (类型):    exist, count, status, object, comparison
  Level 3 (方向):    提问方向/句式结构模式 (major_pattern)
  Level 4 (变体):    同一方向的语言变体，后续大规模扩充
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import defaultdict


@dataclass
class TemplateEntry:
    """模板条目"""
    template_id: str           # 唯一标识: {L}_{type}_{pattern}_{variant}
    template: str              # 问题模板 (含占位符)
    answer_type: str           # bool / number / type / status
    answer_logic: str          # 答案计算逻辑标签
    coverage_level: str        # L0 / L1 / L2
    question_type: str         # exist / count / status / object / comparison
    major_pattern: str         # 大样子名称
    variant_idx: int           # 变体编号
    required_params: List[str] # 所需填充参数
    frequency: int = 0         # NuScenesQA 中的出现频率
    description: str = ""
    cv_friendly: bool = True    # CV模型是否能从视觉回答（False=需精确数值）


# ============================================================================
#  L0: 节点覆盖模板  (单对象属性查询, 不涉及空间关系)
# ============================================================================

L0_EXIST_TEMPLATES = [
    # --- 大样子 A: 纯类型存在性 ---
    TemplateEntry(
        template_id="L0_exist_A1",
        template="Are there any {type_plural}?",
        answer_type="bool", answer_logic="exists_type",
        coverage_level="L0", question_type="exist",
        major_pattern="type_exist", variant_idx=1,
        required_params=["type_plural", "obj_type"],
        frequency=1299, description="查询某类型对象是否存在"
    ),
    TemplateEntry(
        template_id="L0_exist_A2",
        template="Are any {type_plural} visible?",
        answer_type="bool", answer_logic="exists_type",
        coverage_level="L0", question_type="exist",
        major_pattern="type_exist", variant_idx=2,
        required_params=["type_plural", "obj_type"],
        frequency=1347, description="查询某类型对象是否可见"
    ),
    # --- 大样子 B: 状态+类型存在性 ---
    TemplateEntry(
        template_id="L0_exist_B1",
        template="Are there any {status} {type_plural}?",
        answer_type="bool", answer_logic="exists_status_type",
        coverage_level="L0", question_type="exist",
        major_pattern="status_type_exist", variant_idx=1,
        required_params=["status", "type_plural", "obj_type"],
        frequency=2455, description="查询某状态+类型对象是否存在"
    ),
    TemplateEntry(
        template_id="L0_exist_B2",
        template="Are any {status} {type_plural} visible?",
        answer_type="bool", answer_logic="exists_status_type",
        coverage_level="L0", question_type="exist",
        major_pattern="status_type_exist", variant_idx=2,
        required_params=["status", "type_plural", "obj_type"],
        frequency=2293, description="查询某状态+类型对象是否可见"
    ),
    # type_exist v3-v5
    TemplateEntry(
        template_id="L0_exist_A3",
        template="Can you see any {type_plural}?",
        answer_type="bool", answer_logic="exists_type",
        coverage_level="L0", question_type="exist",
        major_pattern="type_exist", variant_idx=3,
        required_params=["type_plural", "obj_type"],
        frequency=0, description="某类型是否存在(Can you see)"
    ),
    TemplateEntry(
        template_id="L0_exist_A4",
        template="Is there a {obj_type} in the scene?",
        answer_type="bool", answer_logic="exists_type",
        coverage_level="L0", question_type="exist",
        major_pattern="type_exist", variant_idx=4,
        required_params=["obj_type"],
        frequency=0, description="某类型是否存在(in the scene)"
    ),
    TemplateEntry(
        template_id="L0_exist_A5",
        template="Is a {obj_type} present?",
        answer_type="bool", answer_logic="exists_type",
        coverage_level="L0", question_type="exist",
        major_pattern="type_exist", variant_idx=5,
        required_params=["obj_type"],
        frequency=0, description="某类型是否存在(present)"
    ),
    # status_type_exist v3-v5
    TemplateEntry(
        template_id="L0_exist_B3",
        template="Can you see any {status} {type_plural}?",
        answer_type="bool", answer_logic="exists_status_type",
        coverage_level="L0", question_type="exist",
        major_pattern="status_type_exist", variant_idx=3,
        required_params=["status", "type_plural", "obj_type"],
        frequency=0, description="某状态+类型是否存在(Can you see)"
    ),
    TemplateEntry(
        template_id="L0_exist_B4",
        template="Is there a {obj_type} that is {status}?",
        answer_type="bool", answer_logic="exists_status_type",
        coverage_level="L0", question_type="exist",
        major_pattern="status_type_exist", variant_idx=4,
        required_params=["status", "obj_type"],
        frequency=0, description="某状态+类型(that is句式)"
    ),
    TemplateEntry(
        template_id="L0_exist_B5",
        template="Do you see a {status} {obj_type}?",
        answer_type="bool", answer_logic="exists_status_type",
        coverage_level="L0", question_type="exist",
        major_pattern="status_type_exist", variant_idx=5,
        required_params=["status", "obj_type"],
        frequency=0, description="某状态+类型(Do you see)"
    ),
    # --- 大样子 C: 泛指存在性 ---
    TemplateEntry(
        template_id="L0_exist_C1",
        template="Are there any things?",
        answer_type="bool", answer_logic="exists_any",
        coverage_level="L0", question_type="exist",
        major_pattern="things_exist", variant_idx=1,
        required_params=[],
        frequency=500, description="查询是否有任何对象"
    ),
    TemplateEntry(
        template_id="L0_exist_C2",
        template="Are there any objects in the scene?",
        answer_type="bool", answer_logic="exists_any",
        coverage_level="L0", question_type="exist",
        major_pattern="things_exist", variant_idx=2,
        required_params=[],
        frequency=0, description="是否有任何对象(objects句式)"
    ),
    TemplateEntry(
        template_id="L0_exist_C3",
        template="Can you see any objects?",
        answer_type="bool", answer_logic="exists_any",
        coverage_level="L0", question_type="exist",
        major_pattern="things_exist", variant_idx=3,
        required_params=[],
        frequency=0, description="是否有任何对象(Can you see)"
    ),
]

L0_COUNT_TEMPLATES = [
    # --- 大样子 A: 纯类型计数 ---
    TemplateEntry(
        template_id="L0_count_A1",
        template="How many {type_plural} are there?",
        answer_type="number", answer_logic="count_type",
        coverage_level="L0", question_type="count",
        major_pattern="type_count", variant_idx=1,
        required_params=["type_plural", "obj_type"],
        frequency=1168, description="统计某类型对象数量"
    ),
    TemplateEntry(
        template_id="L0_count_A2",
        template="What number of {type_plural} are there?",
        answer_type="number", answer_logic="count_type",
        coverage_level="L0", question_type="count",
        major_pattern="type_count", variant_idx=2,
        required_params=["type_plural", "obj_type"],
        frequency=1127, description="统计某类型对象数量(What number句式)"
    ),
    # --- 大样子 B: 状态+类型计数 ---
    TemplateEntry(
        template_id="L0_count_B1",
        template="How many {status} {type_plural} are there?",
        answer_type="number", answer_logic="count_status_type",
        coverage_level="L0", question_type="count",
        major_pattern="status_type_count", variant_idx=1,
        required_params=["status", "type_plural", "obj_type"],
        frequency=1610, description="统计某状态+类型对象数量"
    ),
    TemplateEntry(
        template_id="L0_count_B2",
        template="What number of {status} {type_plural} are there?",
        answer_type="number", answer_logic="count_status_type",
        coverage_level="L0", question_type="count",
        major_pattern="status_type_count", variant_idx=2,
        required_params=["status", "type_plural", "obj_type"],
        frequency=1587, description="统计某状态+类型对象数量(What number句式)"
    ),
    # type_count v3-v5
    TemplateEntry(
        template_id="L0_count_A3",
        template="How many {type_plural} can you see?",
        answer_type="number", answer_logic="count_type",
        coverage_level="L0", question_type="count",
        major_pattern="type_count", variant_idx=3,
        required_params=["type_plural", "obj_type"],
        frequency=0, description="统计某类型数量(can you see)"
    ),
    TemplateEntry(
        template_id="L0_count_A4",
        template="Count the {type_plural} in the scene.",
        answer_type="number", answer_logic="count_type",
        coverage_level="L0", question_type="count",
        major_pattern="type_count", variant_idx=4,
        required_params=["type_plural", "obj_type"],
        frequency=0, description="统计某类型数量(祈使句)"
    ),
    TemplateEntry(
        template_id="L0_count_A5",
        template="What is the total number of {type_plural}?",
        answer_type="number", answer_logic="count_type",
        coverage_level="L0", question_type="count",
        major_pattern="type_count", variant_idx=5,
        required_params=["type_plural", "obj_type"],
        frequency=0, description="统计某类型数量(total number)"
    ),
    # status_type_count v3-v5
    TemplateEntry(
        template_id="L0_count_B3",
        template="How many {type_plural} are {status}?",
        answer_type="number", answer_logic="count_status_type",
        coverage_level="L0", question_type="count",
        major_pattern="status_type_count", variant_idx=3,
        required_params=["status", "type_plural", "obj_type"],
        frequency=0, description="统计某状态类型(are status句式)"
    ),
    TemplateEntry(
        template_id="L0_count_B4",
        template="Count the {status} {type_plural}.",
        answer_type="number", answer_logic="count_status_type",
        coverage_level="L0", question_type="count",
        major_pattern="status_type_count", variant_idx=4,
        required_params=["status", "type_plural", "obj_type"],
        frequency=0, description="统计某状态类型(祈使句)"
    ),
    TemplateEntry(
        template_id="L0_count_B5",
        template="How many {status} {type_plural} can you see?",
        answer_type="number", answer_logic="count_status_type",
        coverage_level="L0", question_type="count",
        major_pattern="status_type_count", variant_idx=5,
        required_params=["status", "type_plural", "obj_type"],
        frequency=0, description="统计某状态类型(can you see)"
    ),
]

L0_STATUS_TEMPLATES = [
    # --- 大样子 A: 直接查询对象状态 ---
    TemplateEntry(
        template_id="L0_status_A1",
        template="What is the status of the {obj_type}?",
        answer_type="status", answer_logic="node_status_by_type",
        coverage_level="L0", question_type="status",
        major_pattern="direct_status", variant_idx=1,
        required_params=["obj_type", "obj_id"],
        frequency=993, description="查询指定类型对象的状态"
    ),
    TemplateEntry(
        template_id="L0_status_A2",
        template="What status is the {obj_type}?",
        answer_type="status", answer_logic="node_status_by_type",
        coverage_level="L0", question_type="status",
        major_pattern="direct_status", variant_idx=2,
        required_params=["obj_type", "obj_id"],
        frequency=1018, description="查询指定类型对象的状态(What status句式)"
    ),
    TemplateEntry(
        template_id="L0_status_A3",
        template="The {obj_type} is in what status?",
        answer_type="status", answer_logic="node_status_by_type",
        coverage_level="L0", question_type="status",
        major_pattern="direct_status", variant_idx=3,
        required_params=["obj_type", "obj_id"],
        frequency=1012, description="查询指定类型对象的状态(倒装句式)"
    ),
    # --- 大样子 B: There is 句式 ---
    TemplateEntry(
        template_id="L0_status_B1",
        template="There is a {obj_type}; what status is it?",
        answer_type="status", answer_logic="node_status_by_type",
        coverage_level="L0", question_type="status",
        major_pattern="thereis_status", variant_idx=1,
        required_params=["obj_type", "obj_id"],
        frequency=1047, description="查询指定对象的状态(There is句式)"
    ),
    TemplateEntry(
        template_id="L0_status_B2",
        template="There is a {obj_type}; what is its status?",
        answer_type="status", answer_logic="node_status_by_type",
        coverage_level="L0", question_type="status",
        major_pattern="thereis_status", variant_idx=2,
        required_params=["obj_type", "obj_id"],
        frequency=500, description="查询指定对象的状态(There is + its句式)"
    ),
    # --- 大样子 C: 用unique_id查询 (我们系统特有) ---
    TemplateEntry(
        template_id="L0_status_C1",
        template="What is the status of {obj_id}?",
        answer_type="status", answer_logic="node_status_by_id",
        coverage_level="L0", question_type="status",
        major_pattern="id_status", variant_idx=1,
        required_params=["obj_id"],
        frequency=0, description="用unique_id查询对象状态"
    ),
    TemplateEntry(
        template_id="L0_status_C2",
        template="What status is {obj_id}?",
        answer_type="status", answer_logic="node_status_by_id",
        coverage_level="L0", question_type="status",
        major_pattern="id_status", variant_idx=2,
        required_params=["obj_id"],
        frequency=0, description="用unique_id查询对象状态(变体)"
    ),
    # id_status v3-v5
    TemplateEntry(
        template_id="L0_status_C3",
        template="Is {obj_id} moving or stopped?",
        answer_type="status", answer_logic="node_status_by_id",
        coverage_level="L0", question_type="status",
        major_pattern="id_status", variant_idx=3,
        required_params=["obj_id"],
        frequency=0, description="查询对象状态(binary句式)"
    ),
    TemplateEntry(
        template_id="L0_status_C4",
        template="What is {obj_id} doing?",
        answer_type="status", answer_logic="node_status_by_id",
        coverage_level="L0", question_type="status",
        major_pattern="id_status", variant_idx=4,
        required_params=["obj_id"],
        frequency=0, description="查询对象状态(doing句式)"
    ),
    TemplateEntry(
        template_id="L0_status_C5",
        template="Describe the status of {obj_id}.",
        answer_type="status", answer_logic="node_status_by_id",
        coverage_level="L0", question_type="status",
        major_pattern="id_status", variant_idx=5,
        required_params=["obj_id"],
        frequency=0, description="查询对象状态(祈使句)"
    ),
    # direct_status v4-v5
    TemplateEntry(
        template_id="L0_status_A4",
        template="What state is the {obj_type} in?",
        answer_type="status", answer_logic="node_status_by_type",
        coverage_level="L0", question_type="status",
        major_pattern="direct_status", variant_idx=4,
        required_params=["obj_type", "obj_id"],
        frequency=0, description="查询对象状态(state句式)"
    ),
    TemplateEntry(
        template_id="L0_status_A5",
        template="Is the {obj_type} moving or stopped?",
        answer_type="status", answer_logic="node_status_by_type",
        coverage_level="L0", question_type="status",
        major_pattern="direct_status", variant_idx=5,
        required_params=["obj_type", "obj_id"],
        frequency=0, description="查询对象状态(binary句式)"
    ),
    # thereis_status v3
    TemplateEntry(
        template_id="L0_status_B3",
        template="There is a {obj_type}; what is it doing?",
        answer_type="status", answer_logic="node_status_by_type",
        coverage_level="L0", question_type="status",
        major_pattern="thereis_status", variant_idx=3,
        required_params=["obj_type", "obj_id"],
        frequency=0, description="查询对象状态(There is + doing)"
    ),
]

L0_OBJECT_TEMPLATES = [
    # --- 大样子 A: 查询某状态的对象是什么 ---
    TemplateEntry(
        template_id="L0_object_A1",
        template="What is the {status} {obj_type}?",
        answer_type="type", answer_logic="what_is_status_type",
        coverage_level="L0", question_type="object",
        major_pattern="what_status_type", variant_idx=1,
        required_params=["status", "obj_type", "obj_id"],
        frequency=850, description="查询某状态+类型的对象是什么"
    ),
    TemplateEntry(
        template_id="L0_object_A2",
        template="The {status} {obj_type} is what?",
        answer_type="type", answer_logic="what_is_status_type",
        coverage_level="L0", question_type="object",
        major_pattern="what_status_type", variant_idx=2,
        required_params=["status", "obj_type", "obj_id"],
        frequency=863, description="查询某状态+类型的对象(is what句式)"
    ),
    # --- 大样子 B: There is 句式 ---
    TemplateEntry(
        template_id="L0_object_B1",
        template="There is a {status} {obj_type}; what is it?",
        answer_type="type", answer_logic="what_is_status_type",
        coverage_level="L0", question_type="object",
        major_pattern="thereis_object", variant_idx=1,
        required_params=["status", "obj_type", "obj_id"],
        frequency=855, description="查询某状态对象类型(There is句式)"
    ),
    # --- 大样子 C: 泛指 thing ---
    TemplateEntry(
        template_id="L0_object_C1",
        template="What is the {status} thing?",
        answer_type="type", answer_logic="what_is_status_thing",
        coverage_level="L0", question_type="object",
        major_pattern="what_status_thing", variant_idx=1,
        required_params=["status", "obj_id"],
        frequency=800, description="查询某状态的thing是什么"
    ),
    TemplateEntry(
        template_id="L0_object_C2",
        template="There is a {status} thing; what is it?",
        answer_type="type", answer_logic="what_is_status_thing",
        coverage_level="L0", question_type="object",
        major_pattern="what_status_thing", variant_idx=2,
        required_params=["status", "obj_id"],
        frequency=700, description="查询某状态的thing(There is句式)"
    ),
    # what_status_type v3-v4
    TemplateEntry(
        template_id="L0_object_A3",
        template="What type of object is {status}?",
        answer_type="type", answer_logic="what_is_status_type",
        coverage_level="L0", question_type="object",
        major_pattern="what_status_type", variant_idx=3,
        required_params=["status", "obj_type", "obj_id"],
        frequency=0, description="查询某状态对象类型(What type)"
    ),
    TemplateEntry(
        template_id="L0_object_A4",
        template="Identify the {status} {obj_type}.",
        answer_type="type", answer_logic="what_is_status_type",
        coverage_level="L0", question_type="object",
        major_pattern="what_status_type", variant_idx=4,
        required_params=["status", "obj_type", "obj_id"],
        frequency=0, description="查询某状态对象(祈使句)"
    ),
    # what_status_thing v3-v4
    TemplateEntry(
        template_id="L0_object_C3",
        template="What type is the {status} thing?",
        answer_type="type", answer_logic="what_is_status_thing",
        coverage_level="L0", question_type="object",
        major_pattern="what_status_thing", variant_idx=3,
        required_params=["status", "obj_id"],
        frequency=0, description="查询某状态thing类型(What type)"
    ),
    TemplateEntry(
        template_id="L0_object_C4",
        template="Something is {status}; what type of object is it?",
        answer_type="type", answer_logic="what_is_status_thing",
        coverage_level="L0", question_type="object",
        major_pattern="what_status_thing", variant_idx=4,
        required_params=["status", "obj_id"],
        frequency=0, description="查询某状态thing(Something is句式)"
    ),
    # thereis_object v2
    TemplateEntry(
        template_id="L0_object_B2",
        template="I see a {status} {obj_type}; what is it?",
        answer_type="type", answer_logic="what_is_status_type",
        coverage_level="L0", question_type="object",
        major_pattern="thereis_object", variant_idx=2,
        required_params=["status", "obj_type", "obj_id"],
        frequency=0, description="查询某状态对象(I see句式)"
    ),
]

# ============================================================================
#  L0: 朝向属性模板 (Heading — CV可见: 车头朝向图片中可判断)
# ============================================================================

L0_HEADING_TEMPLATES = [
    # --- 大样子 A: 查询对象朝向 ---
    TemplateEntry(
        template_id="L0_heading_A1",
        template="Is {obj_id} facing towards me?",
        answer_type="bool", answer_logic="is_facing_ego",
        coverage_level="L0", question_type="exist",
        major_pattern="heading_verify", variant_idx=1,
        required_params=["obj_id"],
        frequency=0, description="查询对象是否面朝ego"
    ),
    TemplateEntry(
        template_id="L0_heading_A2",
        template="Is {obj_id} facing away from me?",
        answer_type="bool", answer_logic="is_facing_away",
        coverage_level="L0", question_type="exist",
        major_pattern="heading_verify", variant_idx=2,
        required_params=["obj_id"],
        frequency=0, description="查询对象是否背朝ego"
    ),
    TemplateEntry(
        template_id="L0_heading_A3",
        template="Which way is {obj_id} facing?",
        answer_type="heading", answer_logic="heading_of_id",
        coverage_level="L0", question_type="status",
        major_pattern="heading_query", variant_idx=1,
        required_params=["obj_id"],
        frequency=0, description="查询对象朝向"
    ),
    TemplateEntry(
        template_id="L0_heading_A4",
        template="What direction is {obj_id} pointed at?",
        answer_type="heading", answer_logic="heading_of_id",
        coverage_level="L0", question_type="status",
        major_pattern="heading_query", variant_idx=2,
        required_params=["obj_id"],
        frequency=0, description="查询对象朝向(pointed at句式)"
    ),
]


L0_VERIFY_TEMPLATES = [
    # --- 大样子 A: 验证特定对象是否处于某状态 ---
    TemplateEntry(
        template_id="L0_verify_A1",
        template="Is {obj_id} {status}?",
        answer_type="bool", answer_logic="verify_status_by_id",
        coverage_level="L0", question_type="exist",
        major_pattern="status_verification", variant_idx=1,
        required_params=["obj_id", "status"],
        frequency=0, description="验证指定对象是否处于某状态"
    ),
    TemplateEntry(
        template_id="L0_verify_A2",
        template="Is the {obj_type} {status}?",
        answer_type="bool", answer_logic="verify_status_by_type",
        coverage_level="L0", question_type="exist",
        major_pattern="status_verification", variant_idx=2,
        required_params=["obj_type", "obj_id", "status"],
        frequency=0, description="验证某类型对象是否处于某状态"
    ),
    TemplateEntry(
        template_id="L0_verify_A3",
        template="Is {obj_id} currently {status}?",
        answer_type="bool", answer_logic="verify_status_by_id",
        coverage_level="L0", question_type="exist",
        major_pattern="status_verification", variant_idx=3,
        required_params=["obj_id", "status"],
        frequency=0, description="验证状态(currently句式)"
    ),
    TemplateEntry(
        template_id="L0_verify_A4",
        template="Can you confirm that {obj_id} is {status}?",
        answer_type="bool", answer_logic="verify_status_by_id",
        coverage_level="L0", question_type="exist",
        major_pattern="status_verification", variant_idx=4,
        required_params=["obj_id", "status"],
        frequency=0, description="验证状态(confirm句式)"
    ),
    # --- 大样子 B: 总数相关 ---
    TemplateEntry(
        template_id="L0_verify_B1",
        template="How many objects are there in total?",
        answer_type="number", answer_logic="count_all_objects",
        coverage_level="L0", question_type="count",
        major_pattern="count_all", variant_idx=1,
        required_params=[],
        frequency=0, description="场景中所有对象总数"
    ),
    TemplateEntry(
        template_id="L0_verify_B2",
        template="What is the total number of objects in the scene?",
        answer_type="number", answer_logic="count_all_objects",
        coverage_level="L0", question_type="count",
        major_pattern="count_all", variant_idx=2,
        required_params=[],
        frequency=0, description="场景对象总数(total number句式)"
    ),
    TemplateEntry(
        template_id="L0_verify_B3",
        template="Count all objects in the scene.",
        answer_type="number", answer_logic="count_all_objects",
        coverage_level="L0", question_type="count",
        major_pattern="count_all", variant_idx=3,
        required_params=[],
        frequency=0, description="场景对象总数(祈使句)"
    ),
    # --- 大样子 C: 类型列举 ---
    TemplateEntry(
        template_id="L0_verify_C1",
        template="What types of objects are in the scene?",
        answer_type="type_list", answer_logic="list_all_types",
        coverage_level="L0", question_type="object",
        major_pattern="type_list", variant_idx=1,
        required_params=[],
        frequency=0, description="列举场景中所有对象类型"
    ),
    TemplateEntry(
        template_id="L0_verify_C2",
        template="What kinds of objects can you see?",
        answer_type="type_list", answer_logic="list_all_types",
        coverage_level="L0", question_type="object",
        major_pattern="type_list", variant_idx=2,
        required_params=[],
        frequency=0, description="列举对象类型(kinds句式)"
    ),
    TemplateEntry(
        template_id="L0_verify_C3",
        template="List the different types of objects visible.",
        answer_type="type_list", answer_logic="list_all_types",
        coverage_level="L0", question_type="object",
        major_pattern="type_list", variant_idx=3,
        required_params=[],
        frequency=0, description="列举对象类型(祈使句)"
    ),
    # --- 大样子 D: 多少种类型 ---
    TemplateEntry(
        template_id="L0_verify_D1",
        template="How many different types of objects are there?",
        answer_type="number", answer_logic="count_distinct_types",
        coverage_level="L0", question_type="count",
        major_pattern="count_types", variant_idx=1,
        required_params=[],
        frequency=0, description="场景中有多少种不同类型"
    ),
    TemplateEntry(
        template_id="L0_verify_D2",
        template="How many kinds of objects can you see?",
        answer_type="number", answer_logic="count_distinct_types",
        coverage_level="L0", question_type="count",
        major_pattern="count_types", variant_idx=2,
        required_params=[],
        frequency=0, description="不同类型数量(kinds句式)"
    ),
]

L0_COMPARISON_TEMPLATES = [
    # --- 方向: compare_two_status — 两对象状态比较 ---
    TemplateEntry(
        template_id="L0_compare_A1",
        template="Do {obj1_id} and {obj2_id} have the same status?",
        answer_type="bool", answer_logic="compare_status_two",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_two_status", variant_idx=1,
        required_params=["obj1_id", "obj2_id"],
        frequency=452, description="比较两个对象的状态是否相同"
    ),
    TemplateEntry(
        template_id="L0_compare_A2",
        template="Does {obj1_id} have the same status as {obj2_id}?",
        answer_type="bool", answer_logic="compare_status_two",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_two_status", variant_idx=2,
        required_params=["obj1_id", "obj2_id"],
        frequency=249, description="比较两对象状态(Does...as句式)"
    ),
    TemplateEntry(
        template_id="L0_compare_A3",
        template="Is the status of {obj1_id} the same as {obj2_id}?",
        answer_type="bool", answer_logic="compare_status_two",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_two_status", variant_idx=3,
        required_params=["obj1_id", "obj2_id"],
        frequency=234, description="比较两对象状态(Is the status句式)"
    ),
    # --- 方向: compare_two_type — 两对象类型比较 ---
    TemplateEntry(
        template_id="L0_compare_B1",
        template="Are {obj1_id} and {obj2_id} the same type of object?",
        answer_type="bool", answer_logic="compare_type_two",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_two_type", variant_idx=1,
        required_params=["obj1_id", "obj2_id"],
        frequency=0, description="比较两对象是否同类型"
    ),
    # compare_two_status v4-v5
    TemplateEntry(
        template_id="L0_compare_A4",
        template="Are {obj1_id} and {obj2_id} in the same state?",
        answer_type="bool", answer_logic="compare_status_two",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_two_status", variant_idx=4,
        required_params=["obj1_id", "obj2_id"],
        frequency=0, description="比较两对象状态(in the same state)"
    ),
    TemplateEntry(
        template_id="L0_compare_A5",
        template="Do {obj1_id} and {obj2_id} share the same status?",
        answer_type="bool", answer_logic="compare_status_two",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_two_status", variant_idx=5,
        required_params=["obj1_id", "obj2_id"],
        frequency=0, description="比较两对象状态(share句式)"
    ),
    # compare_two_type v2-v3
    TemplateEntry(
        template_id="L0_compare_B2",
        template="Is {obj1_id} the same type as {obj2_id}?",
        answer_type="bool", answer_logic="compare_type_two",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_two_type", variant_idx=2,
        required_params=["obj1_id", "obj2_id"],
        frequency=0, description="比较两对象类型(same type as)"
    ),
    TemplateEntry(
        template_id="L0_compare_B3",
        template="Do {obj1_id} and {obj2_id} belong to the same category?",
        answer_type="bool", answer_logic="compare_type_two",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_two_type", variant_idx=3,
        required_params=["obj1_id", "obj2_id"],
        frequency=0, description="比较两对象类型(belong to category)"
    ),
    # --- 方向: compare_count_types — 两类型数量比较 ---
    TemplateEntry(
        template_id="L0_compare_C1",
        template="Are there more {type1_plural} than {type2_plural}?",
        answer_type="bool", answer_logic="compare_count_two_types",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_count_types", variant_idx=1,
        required_params=["type1_plural", "type1", "type2_plural", "type2"],
        frequency=0, description="比较两种类型数量"
    ),
    TemplateEntry(
        template_id="L0_compare_C2",
        template="Which are there more of, {type1_plural} or {type2_plural}?",
        answer_type="type", answer_logic="compare_count_two_types_which",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_count_types", variant_idx=2,
        required_params=["type1_plural", "type1", "type2_plural", "type2"],
        frequency=0, description="比较两种类型数量(which句式)"
    ),
    TemplateEntry(
        template_id="L0_compare_C3",
        template="Do you see more {type1_plural} or {type2_plural}?",
        answer_type="type", answer_logic="compare_count_two_types_which",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_count_types", variant_idx=3,
        required_params=["type1_plural", "type1", "type2_plural", "type2"],
        frequency=0, description="比较两种类型数量(Do you see句式)"
    ),
    # --- 方向: compare_count_status — 某状态数量vs另一状态 ---
    TemplateEntry(
        template_id="L0_compare_D1",
        template="Are there more {status1} {type_plural} than {status2} {type_plural}?",
        answer_type="bool", answer_logic="compare_count_two_statuses",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_count_status", variant_idx=1,
        required_params=["status1", "status2", "type_plural", "obj_type"],
        frequency=0, description="比较同类型两种状态的数量"
    ),
    TemplateEntry(
        template_id="L0_compare_D2",
        template="Are more {type_plural} {status1} or {status2}?",
        answer_type="status", answer_logic="compare_count_two_statuses_which",
        coverage_level="L0", question_type="comparison",
        major_pattern="compare_count_status", variant_idx=2,
        required_params=["status1", "status2", "type_plural", "obj_type"],
        frequency=0, description="比较同类型两种状态数量(which句式)"
    ),
]


# ============================================================================
#  L1: 边覆盖模板  (单跳空间关系查询, 涉及方向)
# ============================================================================

L1_EXIST_TEMPLATES = [
    # --- 大样子 A: 某方向是否有某类型 (参照ego) ---
    TemplateEntry(
        template_id="L1_exist_A1",
        template="Are there any {type_plural} to the {direction} of me?",
        answer_type="bool", answer_logic="exists_direction_from_ego",
        coverage_level="L1", question_type="exist",
        major_pattern="ego_direction_exist", variant_idx=1,
        required_params=["type_plural", "obj_type", "direction"],
        frequency=800, description="查询ego某方向是否有某类型对象"
    ),
    TemplateEntry(
        template_id="L1_exist_A2",
        template="Are there any {type_plural} to the {direction} of {ref_id}?",
        answer_type="bool", answer_logic="exists_direction_from_ref",
        coverage_level="L1", question_type="exist",
        major_pattern="ego_direction_exist", variant_idx=2,
        required_params=["type_plural", "obj_type", "direction", "ref_id"],
        frequency=600, description="查询ref某方向是否有某类型对象"
    ),
    # --- 大样子 B: 某方向是否有某状态+类型 (参照ego) ---
    TemplateEntry(
        template_id="L1_exist_B1",
        template="Are there any {status} {type_plural} to the {direction} of me?",
        answer_type="bool", answer_logic="exists_status_direction_from_ego",
        coverage_level="L1", question_type="exist",
        major_pattern="ego_status_direction_exist", variant_idx=1,
        required_params=["status", "type_plural", "obj_type", "direction"],
        frequency=956, description="查询ego某方向是否有某状态+类型"
    ),
    # --- 方向: ref_direction_exist — 参照对象方向存在性 ---
    TemplateEntry(
        template_id="L1_exist_C1",
        template="Are there any {type_plural} to the {direction} of {ref_id}?",
        answer_type="bool", answer_logic="exists_direction_from_ref",
        coverage_level="L1", question_type="exist",
        major_pattern="ref_direction_exist", variant_idx=1,
        required_params=["type_plural", "obj_type", "direction", "ref_id"],
        frequency=965, description="参照对象某方向是否有某类型"
    ),
    TemplateEntry(
        template_id="L1_exist_C2",
        template="Are there any {status} {type_plural} to the {direction} of {ref_id}?",
        answer_type="bool", answer_logic="exists_status_direction_from_ref",
        coverage_level="L1", question_type="exist",
        major_pattern="ref_direction_exist", variant_idx=2,
        required_params=["status", "type_plural", "obj_type", "direction", "ref_id"],
        frequency=1166, description="参照对象方向查某状态类型存在性"
    ),
    # ego_direction_exist v3-v5
    TemplateEntry(
        template_id="L1_exist_A3",
        template="Can you see any {type_plural} to the {direction} of me?",
        answer_type="bool", answer_logic="exists_direction_from_ego",
        coverage_level="L1", question_type="exist",
        major_pattern="ego_direction_exist", variant_idx=3,
        required_params=["type_plural", "obj_type", "direction"],
        frequency=0, description="ego方向存在性(Can you see)"
    ),
    TemplateEntry(
        template_id="L1_exist_A4",
        template="Do you see any {type_plural} to the {direction}?",
        answer_type="bool", answer_logic="exists_direction_from_ego",
        coverage_level="L1", question_type="exist",
        major_pattern="ego_direction_exist", variant_idx=4,
        required_params=["type_plural", "obj_type", "direction"],
        frequency=0, description="ego方向存在性(Do you see)"
    ),
    TemplateEntry(
        template_id="L1_exist_A5",
        template="Is there a {obj_type} to the {direction} of me?",
        answer_type="bool", answer_logic="exists_direction_from_ego",
        coverage_level="L1", question_type="exist",
        major_pattern="ego_direction_exist", variant_idx=5,
        required_params=["obj_type", "direction"],
        frequency=0, description="ego方向存在性(单数句式)"
    ),
    # ego_status_direction_exist v2-v3
    TemplateEntry(
        template_id="L1_exist_B2",
        template="Can you see any {status} {type_plural} to the {direction}?",
        answer_type="bool", answer_logic="exists_status_direction_from_ego",
        coverage_level="L1", question_type="exist",
        major_pattern="ego_status_direction_exist", variant_idx=2,
        required_params=["status", "type_plural", "obj_type", "direction"],
        frequency=0, description="ego方向状态存在性(Can you see)"
    ),
    TemplateEntry(
        template_id="L1_exist_B3",
        template="Is there a {status} {obj_type} to the {direction} of me?",
        answer_type="bool", answer_logic="exists_status_direction_from_ego",
        coverage_level="L1", question_type="exist",
        major_pattern="ego_status_direction_exist", variant_idx=3,
        required_params=["status", "obj_type", "direction"],
        frequency=0, description="ego方向状态存在性(单数句式)"
    ),
    # ref_direction_exist v3-v4
    TemplateEntry(
        template_id="L1_exist_C3",
        template="Can you see any {type_plural} to the {direction} of {ref_id}?",
        answer_type="bool", answer_logic="exists_direction_from_ref",
        coverage_level="L1", question_type="exist",
        major_pattern="ref_direction_exist", variant_idx=3,
        required_params=["type_plural", "obj_type", "direction", "ref_id"],
        frequency=0, description="ref方向存在性(Can you see)"
    ),
    TemplateEntry(
        template_id="L1_exist_C4",
        template="Is there a {obj_type} to the {direction} of {ref_id}?",
        answer_type="bool", answer_logic="exists_direction_from_ref",
        coverage_level="L1", question_type="exist",
        major_pattern="ref_direction_exist", variant_idx=4,
        required_params=["obj_type", "direction", "ref_id"],
        frequency=0, description="ref方向存在性(单数句式)"
    ),
    # --- 大样子 E: 泛指 things ---
    TemplateEntry(
        template_id="L1_exist_E1",
        template="Are there any things to the {direction} of me?",
        answer_type="bool", answer_logic="exists_any_direction_from_ego",
        coverage_level="L1", question_type="exist",
        major_pattern="things_direction_exist", variant_idx=1,
        required_params=["direction"],
        frequency=862, description="查询ego某方向是否有任何对象"
    ),
    TemplateEntry(
        template_id="L1_exist_E2",
        template="Can you see any objects to the {direction}?",
        answer_type="bool", answer_logic="exists_any_direction_from_ego",
        coverage_level="L1", question_type="exist",
        major_pattern="things_direction_exist", variant_idx=2,
        required_params=["direction"],
        frequency=0, description="ego方向是否有对象(Can you see)"
    ),
    TemplateEntry(
        template_id="L1_exist_E3",
        template="Is there anything to the {direction} of me?",
        answer_type="bool", answer_logic="exists_any_direction_from_ego",
        coverage_level="L1", question_type="exist",
        major_pattern="things_direction_exist", variant_idx=3,
        required_params=["direction"],
        frequency=0, description="ego方向是否有对象(anything句式)"
    ),
]

L1_COUNT_TEMPLATES = [
    # --- 大样子 A: ego方向计数 ---
    TemplateEntry(
        template_id="L1_count_A1",
        template="How many {type_plural} are to the {direction} of me?",
        answer_type="number", answer_logic="count_direction_from_ego",
        coverage_level="L1", question_type="count",
        major_pattern="ego_direction_count", variant_idx=1,
        required_params=["type_plural", "obj_type", "direction"],
        frequency=500, description="统计ego某方向某类型数量"
    ),
    TemplateEntry(
        template_id="L1_count_A2",
        template="What number of {type_plural} are to the {direction} of me?",
        answer_type="number", answer_logic="count_direction_from_ego",
        coverage_level="L1", question_type="count",
        major_pattern="ego_direction_count", variant_idx=2,
        required_params=["type_plural", "obj_type", "direction"],
        frequency=440, description="统计ego某方向某类型数量(What number句式)"
    ),
    # --- 方向: ref_direction_count — 参照对象方向计数 ---
    TemplateEntry(
        template_id="L1_count_B1",
        template="What number of {type_plural} are to the {direction} of {ref_id}?",
        answer_type="number", answer_logic="count_direction_from_ref",
        coverage_level="L1", question_type="count",
        major_pattern="ref_direction_count", variant_idx=1,
        required_params=["type_plural", "obj_type", "direction", "ref_id"],
        frequency=440, description="参照对象某方向某类型数量"
    ),
    TemplateEntry(
        template_id="L1_count_B2",
        template="How many {type_plural} are to the {direction} of {ref_id}?",
        answer_type="number", answer_logic="count_direction_from_ref",
        coverage_level="L1", question_type="count",
        major_pattern="ref_direction_count", variant_idx=2,
        required_params=["type_plural", "obj_type", "direction", "ref_id"],
        frequency=400, description="参照对象方向数量(How many句式)"
    ),
    # --- 大样子 D: 泛指 things 计数 ---
    TemplateEntry(
        template_id="L1_count_D1",
        template="What number of things are to the {direction} of me?",
        answer_type="number", answer_logic="count_any_direction_from_ego",
        coverage_level="L1", question_type="count",
        major_pattern="things_direction_count", variant_idx=1,
        required_params=["direction"],
        frequency=400, description="统计ego某方向所有对象数量"
    ),
    TemplateEntry(
        template_id="L1_count_D2",
        template="How many things are to the {direction} of me?",
        answer_type="number", answer_logic="count_any_direction_from_ego",
        coverage_level="L1", question_type="count",
        major_pattern="things_direction_count", variant_idx=2,
        required_params=["direction"],
        frequency=350, description="统计ego某方向所有对象数量(How many句式)"
    ),
    # --- 大样子 E: 状态+方向计数 ---
    TemplateEntry(
        template_id="L1_count_E1",
        template="What number of {status} {type_plural} are to the {direction} of me?",
        answer_type="number", answer_logic="count_status_direction_from_ego",
        coverage_level="L1", question_type="count",
        major_pattern="ego_status_direction_count", variant_idx=1,
        required_params=["status", "type_plural", "obj_type", "direction"],
        frequency=300, description="统计ego某方向某状态+类型数量"
    ),
    TemplateEntry(
        template_id="L1_count_E2",
        template="What number of {status} things are to the {direction} of me?",
        answer_type="number", answer_logic="count_status_any_direction_from_ego",
        coverage_level="L1", question_type="count",
        major_pattern="ego_status_direction_count", variant_idx=2,
        required_params=["status", "direction"],
        frequency=300, description="统计ego某方向某状态所有对象数量"
    ),
    # ego_direction_count v3-v4
    TemplateEntry(
        template_id="L1_count_A3",
        template="How many {type_plural} can you see to the {direction} of me?",
        answer_type="number", answer_logic="count_direction_from_ego",
        coverage_level="L1", question_type="count",
        major_pattern="ego_direction_count", variant_idx=3,
        required_params=["type_plural", "obj_type", "direction"],
        frequency=0, description="ego方向计数(can you see)"
    ),
    TemplateEntry(
        template_id="L1_count_A4",
        template="Count the {type_plural} to the {direction} of me.",
        answer_type="number", answer_logic="count_direction_from_ego",
        coverage_level="L1", question_type="count",
        major_pattern="ego_direction_count", variant_idx=4,
        required_params=["type_plural", "obj_type", "direction"],
        frequency=0, description="ego方向计数(祈使句)"
    ),
    # ref_direction_count v3-v4
    TemplateEntry(
        template_id="L1_count_B3",
        template="How many {type_plural} can you see to the {direction} of {ref_id}?",
        answer_type="number", answer_logic="count_direction_from_ref",
        coverage_level="L1", question_type="count",
        major_pattern="ref_direction_count", variant_idx=3,
        required_params=["type_plural", "obj_type", "direction", "ref_id"],
        frequency=0, description="ref方向计数(can you see)"
    ),
    TemplateEntry(
        template_id="L1_count_B4",
        template="Count the {type_plural} to the {direction} of {ref_id}.",
        answer_type="number", answer_logic="count_direction_from_ref",
        coverage_level="L1", question_type="count",
        major_pattern="ref_direction_count", variant_idx=4,
        required_params=["type_plural", "obj_type", "direction", "ref_id"],
        frequency=0, description="ref方向计数(祈使句)"
    ),
    # things_direction_count v3
    TemplateEntry(
        template_id="L1_count_D3",
        template="How many objects can you see to the {direction}?",
        answer_type="number", answer_logic="count_any_direction_from_ego",
        coverage_level="L1", question_type="count",
        major_pattern="things_direction_count", variant_idx=3,
        required_params=["direction"],
        frequency=0, description="ego方向全部对象计数(can you see)"
    ),
    # ego_status_direction_count v3
    TemplateEntry(
        template_id="L1_count_E3",
        template="How many {status} {type_plural} can you see to the {direction}?",
        answer_type="number", answer_logic="count_status_direction_from_ego",
        coverage_level="L1", question_type="count",
        major_pattern="ego_status_direction_count", variant_idx=3,
        required_params=["status", "type_plural", "obj_type", "direction"],
        frequency=0, description="ego方向状态计数(can you see)"
    ),
]

L1_STATUS_TEMPLATES = [
    # --- 大样子 A: 查询某方向对象状态 (参照ego) ---
    TemplateEntry(
        template_id="L1_status_A1",
        template="What is the status of the {obj_type} that is to the {direction} of me?",
        answer_type="status", answer_logic="status_direction_from_ego",
        coverage_level="L1", question_type="status",
        major_pattern="ego_direction_status", variant_idx=1,
        required_params=["obj_type", "direction", "obj_id"],
        frequency=340, description="查询ego某方向对象状态"
    ),
    TemplateEntry(
        template_id="L1_status_A2",
        template="What status is the {obj_type} that is to the {direction} of me?",
        answer_type="status", answer_logic="status_direction_from_ego",
        coverage_level="L1", question_type="status",
        major_pattern="ego_direction_status", variant_idx=2,
        required_params=["obj_type", "direction", "obj_id"],
        frequency=344, description="查询ego某方向对象状态(What status句式)"
    ),
    TemplateEntry(
        template_id="L1_status_A3",
        template="The {obj_type} that is to the {direction} of me is in what status?",
        answer_type="status", answer_logic="status_direction_from_ego",
        coverage_level="L1", question_type="status",
        major_pattern="ego_direction_status", variant_idx=3,
        required_params=["obj_type", "direction", "obj_id"],
        frequency=366, description="查询ego某方向对象状态(倒装句式)"
    ),
    # --- 方向: ref_direction_status — 参照对象方向查状态 ---
    TemplateEntry(
        template_id="L1_status_B1",
        template="What is the status of the {obj_type} that is to the {direction} of {ref_id}?",
        answer_type="status", answer_logic="status_direction_from_ref",
        coverage_level="L1", question_type="status",
        major_pattern="ref_direction_status", variant_idx=1,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=340, description="参照对象某方向对象状态"
    ),
    TemplateEntry(
        template_id="L1_status_B2",
        template="What status is the {obj_type} to the {direction} of {ref_id}?",
        answer_type="status", answer_logic="status_direction_from_ref",
        coverage_level="L1", question_type="status",
        major_pattern="ref_direction_status", variant_idx=2,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=374, description="参照对象方向状态(What status句式)"
    ),
    # --- 方向: thereis_direction_status — There is句式查状态 ---
    TemplateEntry(
        template_id="L1_status_C1",
        template="There is a {obj_type} to the {direction} of me; what is its status?",
        answer_type="status", answer_logic="status_direction_from_ego",
        coverage_level="L1", question_type="status",
        major_pattern="thereis_direction_status", variant_idx=1,
        required_params=["obj_type", "direction", "obj_id"],
        frequency=367, description="There is句式查ego方向对象状态"
    ),
    TemplateEntry(
        template_id="L1_status_C2",
        template="There is a {obj_type} to the {direction} of {ref_id}; what status is it?",
        answer_type="status", answer_logic="status_direction_from_ref",
        coverage_level="L1", question_type="status",
        major_pattern="thereis_direction_status", variant_idx=2,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=367, description="There is句式查参照对象方向状态"
    ),
    # ego_direction_status v4-v5
    TemplateEntry(
        template_id="L1_status_A4",
        template="What state is the {obj_type} to the {direction} of me in?",
        answer_type="status", answer_logic="status_direction_from_ego",
        coverage_level="L1", question_type="status",
        major_pattern="ego_direction_status", variant_idx=4,
        required_params=["obj_type", "direction", "obj_id"],
        frequency=0, description="ego方向状态(state句式)"
    ),
    TemplateEntry(
        template_id="L1_status_A5",
        template="Is the {obj_type} to the {direction} of me moving or stopped?",
        answer_type="status", answer_logic="status_direction_from_ego",
        coverage_level="L1", question_type="status",
        major_pattern="ego_direction_status", variant_idx=5,
        required_params=["obj_type", "direction", "obj_id"],
        frequency=0, description="ego方向状态(binary句式)"
    ),
    # ref_direction_status v3-v4
    TemplateEntry(
        template_id="L1_status_B3",
        template="Is the {obj_type} to the {direction} of {ref_id} moving or stopped?",
        answer_type="status", answer_logic="status_direction_from_ref",
        coverage_level="L1", question_type="status",
        major_pattern="ref_direction_status", variant_idx=3,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=0, description="ref方向状态(binary句式)"
    ),
    TemplateEntry(
        template_id="L1_status_B4",
        template="What is the {obj_type} to the {direction} of {ref_id} doing?",
        answer_type="status", answer_logic="status_direction_from_ref",
        coverage_level="L1", question_type="status",
        major_pattern="ref_direction_status", variant_idx=4,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=0, description="ref方向状态(doing句式)"
    ),
    # thereis_direction_status v3-v4
    TemplateEntry(
        template_id="L1_status_C3",
        template="There is a {obj_type} to the {direction} of me; is it moving or stopped?",
        answer_type="status", answer_logic="status_direction_from_ego",
        coverage_level="L1", question_type="status",
        major_pattern="thereis_direction_status", variant_idx=3,
        required_params=["obj_type", "direction", "obj_id"],
        frequency=0, description="There is句式ego方向(binary)"
    ),
    TemplateEntry(
        template_id="L1_status_C4",
        template="I see a {obj_type} to the {direction} of {ref_id}; what is its status?",
        answer_type="status", answer_logic="status_direction_from_ref",
        coverage_level="L1", question_type="status",
        major_pattern="thereis_direction_status", variant_idx=4,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=0, description="I see句式ref方向状态"
    ),
]

L1_OBJECT_TEMPLATES = [
    # --- 大样子 A: 查询ego方向某状态对象是什么 ---
    TemplateEntry(
        template_id="L1_object_A1",
        template="What is the {status} {obj_type} to the {direction} of me?",
        answer_type="type", answer_logic="what_direction_from_ego",
        coverage_level="L1", question_type="object",
        major_pattern="ego_direction_object", variant_idx=1,
        required_params=["status", "obj_type", "direction", "obj_id"],
        frequency=451, description="查询ego某方向某状态对象是什么"
    ),
    TemplateEntry(
        template_id="L1_object_A2",
        template="The {status} {obj_type} that is to the {direction} of me is what?",
        answer_type="type", answer_logic="what_direction_from_ego",
        coverage_level="L1", question_type="object",
        major_pattern="ego_direction_object", variant_idx=2,
        required_params=["status", "obj_type", "direction", "obj_id"],
        frequency=473, description="查询ego某方向某状态对象(is what句式)"
    ),
    # --- 大样子 B: There is 句式查ego方向对象 ---
    TemplateEntry(
        template_id="L1_object_B1",
        template="There is a {status} {obj_type} that is to the {direction} of me; what is it?",
        answer_type="type", answer_logic="what_direction_from_ego",
        coverage_level="L1", question_type="object",
        major_pattern="thereis_ego_direction_object", variant_idx=1,
        required_params=["status", "obj_type", "direction", "obj_id"],
        frequency=465, description="There is句式查ego方向对象"
    ),
    TemplateEntry(
        template_id="L1_object_B2",
        template="There is a {status} thing to the {direction} of me; what is it?",
        answer_type="type", answer_logic="what_thing_direction_from_ego",
        coverage_level="L1", question_type="object",
        major_pattern="thereis_ego_direction_object", variant_idx=2,
        required_params=["status", "direction", "obj_id"],
        frequency=400, description="There is句式查ego方向thing"
    ),
    # --- 方向: ref_direction_object — 参照对象方向查对象 ---
    TemplateEntry(
        template_id="L1_object_C1",
        template="What is the {obj_type} that is to the {direction} of {ref_id}?",
        answer_type="type", answer_logic="what_direction_from_ref",
        coverage_level="L1", question_type="object",
        major_pattern="ref_direction_object", variant_idx=1,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=465, description="参照对象某方向对象是什么"
    ),
    TemplateEntry(
        template_id="L1_object_C2",
        template="The {obj_type} to the {direction} of {ref_id} is what?",
        answer_type="type", answer_logic="what_direction_from_ref",
        coverage_level="L1", question_type="object",
        major_pattern="ref_direction_object", variant_idx=2,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=471, description="参照对象方向查对象(is what句式)"
    ),
    # --- 方向: thereis_ref_direction_object — There is句式 ---
    TemplateEntry(
        template_id="L1_object_D1",
        template="There is a {obj_type} to the {direction} of {ref_id}; what is it?",
        answer_type="type", answer_logic="what_direction_from_ref",
        coverage_level="L1", question_type="object",
        major_pattern="thereis_ref_direction_object", variant_idx=1,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=461, description="There is句式查参照对象方向对象"
    ),
    # ego_direction_object v3
    TemplateEntry(
        template_id="L1_object_A3",
        template="What type of object is {status} to the {direction} of me?",
        answer_type="type", answer_logic="what_direction_from_ego",
        coverage_level="L1", question_type="object",
        major_pattern="ego_direction_object", variant_idx=3,
        required_params=["status", "obj_type", "direction", "obj_id"],
        frequency=0, description="ego方向对象(What type)"
    ),
    TemplateEntry(
        template_id="L1_object_A4",
        template="Identify the {status} {obj_type} to the {direction} of me.",
        answer_type="type", answer_logic="what_direction_from_ego",
        coverage_level="L1", question_type="object",
        major_pattern="ego_direction_object", variant_idx=4,
        required_params=["status", "obj_type", "direction", "obj_id"],
        frequency=0, description="ego方向对象(祈使句)"
    ),
    # thereis_ego_direction_object v3
    TemplateEntry(
        template_id="L1_object_B3",
        template="I see a {status} {obj_type} to the {direction} of me; what type is it?",
        answer_type="type", answer_logic="what_direction_from_ego",
        coverage_level="L1", question_type="object",
        major_pattern="thereis_ego_direction_object", variant_idx=3,
        required_params=["status", "obj_type", "direction", "obj_id"],
        frequency=0, description="I see句式ego方向对象"
    ),
    # ref_direction_object v3
    TemplateEntry(
        template_id="L1_object_C3",
        template="What type of object is to the {direction} of {ref_id}?",
        answer_type="type", answer_logic="what_direction_from_ref",
        coverage_level="L1", question_type="object",
        major_pattern="ref_direction_object", variant_idx=3,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=0, description="ref方向对象(What type)"
    ),
    TemplateEntry(
        template_id="L1_object_C4",
        template="Identify the {obj_type} to the {direction} of {ref_id}.",
        answer_type="type", answer_logic="what_direction_from_ref",
        coverage_level="L1", question_type="object",
        major_pattern="ref_direction_object", variant_idx=4,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=0, description="ref方向对象(祈使句)"
    ),
    # thereis_ref_direction_object v2
    TemplateEntry(
        template_id="L1_object_D2",
        template="I see a {obj_type} to the {direction} of {ref_id}; what type is it?",
        answer_type="type", answer_logic="what_direction_from_ref",
        coverage_level="L1", question_type="object",
        major_pattern="thereis_ref_direction_object", variant_idx=2,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=0, description="I see句式ref方向对象"
    ),
]

L1_COMPARISON_TEMPLATES = [
    # --- 方向: direction_obj_compare — 方向对象 vs 另一对象 状态比较 ---
    TemplateEntry(
        template_id="L1_compare_A1",
        template="Does the {obj_type} to the {direction} of {ref_id} have the same status as {obj2_id}?",
        answer_type="bool", answer_logic="compare_direction_ref_vs_id",
        coverage_level="L1", question_type="comparison",
        major_pattern="direction_obj_compare", variant_idx=1,
        required_params=["obj_type", "direction", "ref_id", "obj_id", "obj2_id"],
        frequency=232, description="方向对象与指定对象状态比较"
    ),
    TemplateEntry(
        template_id="L1_compare_A2",
        template="Is the status of the {obj_type} to the {direction} of {ref_id} the same as {obj2_id}?",
        answer_type="bool", answer_logic="compare_direction_ref_vs_id",
        coverage_level="L1", question_type="comparison",
        major_pattern="direction_obj_compare", variant_idx=2,
        required_params=["obj_type", "direction", "ref_id", "obj_id", "obj2_id"],
        frequency=226, description="方向对象与指定对象状态(Is the status句式)"
    ),
    # --- 方向: two_id_compare — 两个ID对象的状态比较(其中一个用方向描述) ---
    TemplateEntry(
        template_id="L1_compare_B1",
        template="Do {obj1_id} and the {obj_type} to the {direction} of {ref_id} have the same status?",
        answer_type="bool", answer_logic="compare_id_vs_direction_ref",
        coverage_level="L1", question_type="comparison",
        major_pattern="two_id_compare", variant_idx=1,
        required_params=["obj1_id", "obj_type", "direction", "ref_id", "obj2_id"],
        frequency=230, description="ID对象与方向对象状态比较"
    ),
    # --- 方向: thereis_direction_compare — There is句式 ---
    TemplateEntry(
        template_id="L1_compare_C1",
        template="There is a {obj_type} to the {direction} of {ref_id}; does it have the same status as {obj2_id}?",
        answer_type="bool", answer_logic="compare_direction_ref_vs_id",
        coverage_level="L1", question_type="comparison",
        major_pattern="thereis_direction_compare", variant_idx=1,
        required_params=["obj_type", "direction", "ref_id", "obj_id", "obj2_id"],
        frequency=219, description="There is句式方向对象状态比较"
    ),
    # direction_obj_compare v3
    TemplateEntry(
        template_id="L1_compare_A3",
        template="Are the {obj_type} to the {direction} of {ref_id} and {obj2_id} in the same state?",
        answer_type="bool", answer_logic="compare_direction_ref_vs_id",
        coverage_level="L1", question_type="comparison",
        major_pattern="direction_obj_compare", variant_idx=3,
        required_params=["obj_type", "direction", "ref_id", "obj_id", "obj2_id"],
        frequency=0, description="方向对象与指定对象(in the same state)"
    ),
    # two_id_compare v2
    TemplateEntry(
        template_id="L1_compare_B2",
        template="Do {obj1_id} and the {obj_type} to the {direction} of {ref_id} share the same status?",
        answer_type="bool", answer_logic="compare_id_vs_direction_ref",
        coverage_level="L1", question_type="comparison",
        major_pattern="two_id_compare", variant_idx=2,
        required_params=["obj1_id", "obj_type", "direction", "ref_id", "obj2_id"],
        frequency=0, description="ID对象与方向对象(share句式)"
    ),
    # thereis_direction_compare v2
    TemplateEntry(
        template_id="L1_compare_C2",
        template="I see a {obj_type} to the {direction} of {ref_id}; is it in the same state as {obj2_id}?",
        answer_type="bool", answer_logic="compare_direction_ref_vs_id",
        coverage_level="L1", question_type="comparison",
        major_pattern="thereis_direction_compare", variant_idx=2,
        required_params=["obj_type", "direction", "ref_id", "obj_id", "obj2_id"],
        frequency=0, description="I see句式方向对象状态比较"
    ),
    # direction_obj_compare v4-v5
    TemplateEntry(
        template_id="L1_compare_A4",
        template="Does the {obj_type} to the {direction} of {ref_id} share the same status as {obj2_id}?",
        answer_type="bool", answer_logic="compare_direction_ref_vs_id",
        coverage_level="L1", question_type="comparison",
        major_pattern="direction_obj_compare", variant_idx=4,
        required_params=["obj_type", "direction", "ref_id", "obj_id", "obj2_id"],
        frequency=0, description="方向对象与指定对象(share句式)"
    ),
    TemplateEntry(
        template_id="L1_compare_A5",
        template="Is the {obj_type} to the {direction} of {ref_id} doing the same thing as {obj2_id}?",
        answer_type="bool", answer_logic="compare_direction_ref_vs_id",
        coverage_level="L1", question_type="comparison",
        major_pattern="direction_obj_compare", variant_idx=5,
        required_params=["obj_type", "direction", "ref_id", "obj_id", "obj2_id"],
        frequency=0, description="方向对象与指定对象(doing the same thing)"
    ),
    # two_id_compare v3-v4
    TemplateEntry(
        template_id="L1_compare_B3",
        template="Are {obj1_id} and the {obj_type} to the {direction} of {ref_id} in the same state?",
        answer_type="bool", answer_logic="compare_id_vs_direction_ref",
        coverage_level="L1", question_type="comparison",
        major_pattern="two_id_compare", variant_idx=3,
        required_params=["obj1_id", "obj_type", "direction", "ref_id", "obj2_id"],
        frequency=0, description="ID对象与方向对象(in the same state)"
    ),
    TemplateEntry(
        template_id="L1_compare_B4",
        template="Is {obj1_id} doing the same thing as the {obj_type} to the {direction} of {ref_id}?",
        answer_type="bool", answer_logic="compare_id_vs_direction_ref",
        coverage_level="L1", question_type="comparison",
        major_pattern="two_id_compare", variant_idx=4,
        required_params=["obj1_id", "obj_type", "direction", "ref_id", "obj2_id"],
        frequency=0, description="ID对象与方向对象(doing same thing)"
    ),
    # --- 方向: ego_direction_compare — ego方向对象 vs 另一对象 ---
    TemplateEntry(
        template_id="L1_compare_D1",
        template="Does the {obj_type} to the {direction} of me have the same status as {obj2_id}?",
        answer_type="bool", answer_logic="compare_direction_ego_vs_id",
        coverage_level="L1", question_type="comparison",
        major_pattern="ego_direction_compare", variant_idx=1,
        required_params=["obj_type", "direction", "obj_id", "obj2_id"],
        frequency=0, description="ego方向对象与指定对象状态比较"
    ),
    TemplateEntry(
        template_id="L1_compare_D2",
        template="Is the {obj_type} to the {direction} of me in the same state as {obj2_id}?",
        answer_type="bool", answer_logic="compare_direction_ego_vs_id",
        coverage_level="L1", question_type="comparison",
        major_pattern="ego_direction_compare", variant_idx=2,
        required_params=["obj_type", "direction", "obj_id", "obj2_id"],
        frequency=0, description="ego方向对象与指定对象(in the same state)"
    ),
    TemplateEntry(
        template_id="L1_compare_D3",
        template="There is a {obj_type} to the {direction} of me; does it have the same status as {obj2_id}?",
        answer_type="bool", answer_logic="compare_direction_ego_vs_id",
        coverage_level="L1", question_type="comparison",
        major_pattern="ego_direction_compare", variant_idx=3,
        required_params=["obj_type", "direction", "obj_id", "obj2_id"],
        frequency=0, description="ego方向There is句式状态比较"
    ),
    # --- 方向: type_direction_compare — 同类型不同方向比较 ---
    TemplateEntry(
        template_id="L1_compare_E1",
        template="Does the {obj_type} to the {direction} of me have the same status as the {obj_type} to the {direction} of {ref_id}?",
        answer_type="bool", answer_logic="compare_ego_dir_vs_ref_dir",
        coverage_level="L1", question_type="comparison",
        major_pattern="type_direction_compare", variant_idx=1,
        required_params=["obj_type", "direction", "ref_id", "obj_id", "obj2_id"],
        frequency=0, description="同类型ego方向vs ref方向状态比较"
    ),
]


# ============================================================================
#  L2: 两跳路径覆盖模板
#
#  核心子图模式: "A的B的C" — 严格首尾相连两连边
#    (A) --[edge1]--> (B) --[edge2]--> (C)
#    edge1的尾(B) = edge2的头(B)
#    edge 可以是: 空间关系边(direction_8) 或 status属性边(双向)
#
#  模式分类:
#    [CHAIN]  严格链式: ref→[dir]→mid→[dir]→target
#    [STATUS] status双向边: A→[status]→X←[status]←B (同状态链)
#    [COMPLEX] 复杂情境: 包含两连边但结构更复杂 (intersection/comparison)
#             — 从NuScenesQA引入，增加题集高度
# ============================================================================

L2_EXIST_TEMPLATES = [
    # === [CHAIN] 严格链式方向存在性: ref→[dir2]→mid→[dir1]→target ===
    TemplateEntry(
        template_id="L2_exist_A1",
        template="Is there a {target_type} to the {direction1} of the {mid_type} that is to the {direction2} of {ref_id}?",
        answer_type="bool", answer_logic="exists_2hop_chain",
        coverage_level="L2", question_type="exist",
        major_pattern="chain_direction_exist", variant_idx=1,
        required_params=["target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=300, description="链式两跳方向存在性查询"
    ),
    # === [STATUS] 同状态存在性: A→[status]→X←[status]←B (双向边) ===
    TemplateEntry(
        template_id="L2_exist_B1",
        template="Is there another {obj_type} that has the same status as {ref_id}?",
        answer_type="bool", answer_logic="exists_same_status_another",
        coverage_level="L2", question_type="exist",
        major_pattern="same_status_exist", variant_idx=1,
        required_params=["obj_type", "ref_id"],
        frequency=860, description="查询是否有同类型同状态的另一个对象"
    ),
    # === [COMPLEX] 双方向交集: ref1→[dir1]→target ←[dir2]←ref2 ===
    TemplateEntry(
        template_id="L2_exist_C1",
        template="Is there a {target_type} that is both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}?",
        answer_type="bool", answer_logic="exists_both_directions",
        coverage_level="L2", question_type="exist",
        major_pattern="both_directions_exist", variant_idx=1,
        required_params=["target_type", "direction1", "ref1_id", "direction2", "ref2_id"],
        frequency=300, description="双方向交集存在性查询"
    ),
    # chain_direction_exist v2
    TemplateEntry(
        template_id="L2_exist_A2",
        template="Can you see a {target_type} to the {direction1} of the {mid_type} that is to the {direction2} of {ref_id}?",
        answer_type="bool", answer_logic="exists_2hop_chain",
        coverage_level="L2", question_type="exist",
        major_pattern="chain_direction_exist", variant_idx=2,
        required_params=["target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=0, description="链式两跳存在性(Can you see)"
    ),
    # same_status_exist v2-v3
    TemplateEntry(
        template_id="L2_exist_B2",
        template="Can you see another {obj_type} with the same status as {ref_id}?",
        answer_type="bool", answer_logic="exists_same_status_another",
        coverage_level="L2", question_type="exist",
        major_pattern="same_status_exist", variant_idx=2,
        required_params=["obj_type", "ref_id"],
        frequency=0, description="同状态存在性(Can you see)"
    ),
    TemplateEntry(
        template_id="L2_exist_B3",
        template="Does any other {obj_type} share the same status as {ref_id}?",
        answer_type="bool", answer_logic="exists_same_status_another",
        coverage_level="L2", question_type="exist",
        major_pattern="same_status_exist", variant_idx=3,
        required_params=["obj_type", "ref_id"],
        frequency=0, description="同状态存在性(share句式)"
    ),
    # both_directions_exist v2
    TemplateEntry(
        template_id="L2_exist_C2",
        template="Can you see a {target_type} to the {direction1} of {ref1_id} and also to the {direction2} of {ref2_id}?",
        answer_type="bool", answer_logic="exists_both_directions",
        coverage_level="L2", question_type="exist",
        major_pattern="both_directions_exist", variant_idx=2,
        required_params=["target_type", "direction1", "ref1_id", "direction2", "ref2_id"],
        frequency=0, description="双方向交集存在性(Can you see)"
    ),
    # chain_direction_exist v3-v4
    TemplateEntry(
        template_id="L2_exist_A3",
        template="There is a {mid_type} to the {direction2} of {ref_id}; is there a {target_type} to the {direction1} of it?",
        answer_type="bool", answer_logic="exists_2hop_chain",
        coverage_level="L2", question_type="exist",
        major_pattern="chain_direction_exist", variant_idx=3,
        required_params=["target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=0, description="链式两跳存在性(There is句式)"
    ),
    TemplateEntry(
        template_id="L2_exist_A4",
        template="I see a {mid_type} to the {direction2} of {ref_id}; is there a {target_type} to the {direction1}?",
        answer_type="bool", answer_logic="exists_2hop_chain",
        coverage_level="L2", question_type="exist",
        major_pattern="chain_direction_exist", variant_idx=4,
        required_params=["target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=0, description="链式两跳存在性(I see句式)"
    ),
    # same_status_exist v4-v5
    TemplateEntry(
        template_id="L2_exist_B4",
        template="Is there a {obj_type} other than {ref_id} that is also {status}?",
        answer_type="bool", answer_logic="exists_same_status_another",
        coverage_level="L2", question_type="exist",
        major_pattern="same_status_exist", variant_idx=4,
        required_params=["obj_type", "ref_id", "status"],
        frequency=0, description="同状态另一对象存在性(also句式)"
    ),
    TemplateEntry(
        template_id="L2_exist_B5",
        template="Are there other {type_plural} with the same status as {ref_id}?",
        answer_type="bool", answer_logic="exists_same_status_another",
        coverage_level="L2", question_type="exist",
        major_pattern="same_status_exist", variant_idx=5,
        required_params=["type_plural", "obj_type", "ref_id"],
        frequency=0, description="同状态另一对象存在性(with句式)"
    ),
    # both_directions_exist v3-v4
    TemplateEntry(
        template_id="L2_exist_C3",
        template="Is there anything that is both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}?",
        answer_type="bool", answer_logic="exists_any_both_directions",
        coverage_level="L2", question_type="exist",
        major_pattern="both_directions_exist", variant_idx=3,
        required_params=["direction1", "ref1_id", "direction2", "ref2_id"],
        frequency=0, description="双方向交集泛指存在性"
    ),
    TemplateEntry(
        template_id="L2_exist_C4",
        template="Do you see a {target_type} that is to the {direction1} of {ref1_id} and at the same time to the {direction2} of {ref2_id}?",
        answer_type="bool", answer_logic="exists_both_directions",
        coverage_level="L2", question_type="exist",
        major_pattern="both_directions_exist", variant_idx=4,
        required_params=["target_type", "direction1", "ref1_id", "direction2", "ref2_id"],
        frequency=0, description="双方向交集存在性(at the same time)"
    ),
    # === [CHAIN] 链式+状态约束: ref→[dir2]→mid→[dir1]→target{status} ===
    TemplateEntry(
        template_id="L2_exist_D1",
        template="Is there a {status} {target_type} to the {direction1} of the {mid_type} that is to the {direction2} of {ref_id}?",
        answer_type="bool", answer_logic="exists_2hop_chain_status",
        coverage_level="L2", question_type="exist",
        major_pattern="chain_status_exist", variant_idx=1,
        required_params=["status", "target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id"],
        frequency=0, description="链式两跳+状态存在性"
    ),
    TemplateEntry(
        template_id="L2_exist_D2",
        template="Can you see a {status} {target_type} to the {direction1} of the {mid_type} to the {direction2} of {ref_id}?",
        answer_type="bool", answer_logic="exists_2hop_chain_status",
        coverage_level="L2", question_type="exist",
        major_pattern="chain_status_exist", variant_idx=2,
        required_params=["status", "target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id"],
        frequency=0, description="链式两跳+状态存在性(Can you see)"
    ),
    # === [CHAIN] 链式+朝向: ref→[dir2]→mid→[dir1]→target, 约束target.heading ===
    TemplateEntry(
        template_id="L2_exist_E1",
        template="Is the {target_type} to the {direction1} of the {mid_type} to the {direction2} of {ref_id} facing towards me?",
        answer_type="bool", answer_logic="heading_2hop_chain",
        coverage_level="L2", question_type="exist",
        major_pattern="chain_heading_exist", variant_idx=1,
        required_params=["target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=0, description="链式两跳+朝向查询(facing towards)"
    ),
    TemplateEntry(
        template_id="L2_exist_E2",
        template="Is there a {target_type} facing towards me to the {direction1} of the {mid_type} to the {direction2} of {ref_id}?",
        answer_type="bool", answer_logic="exists_2hop_chain_heading",
        coverage_level="L2", question_type="exist",
        major_pattern="chain_heading_exist", variant_idx=2,
        required_params=["target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id"],
        frequency=0, description="链式两跳+朝向约束存在性"
    ),
    TemplateEntry(
        template_id="L2_exist_E3",
        template="Which way is the {target_type} to the {direction1} of the {mid_type} to the {direction2} of {ref_id} facing?",
        answer_type="heading", answer_logic="heading_2hop_chain_query",
        coverage_level="L2", question_type="status",
        major_pattern="chain_heading_query", variant_idx=1,
        required_params=["target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=0, description="链式两跳+朝向查询(Which way)"
    ),
]

L2_COUNT_TEMPLATES = [
    # --- 大样子 A: 同状态计数 ---
    TemplateEntry(
        template_id="L2_count_A1",
        template="How many other {type_plural} are there of the same status as {ref_id}?",
        answer_type="number", answer_logic="count_same_status",
        coverage_level="L2", question_type="count",
        major_pattern="same_status_count", variant_idx=1,
        required_params=["type_plural", "obj_type", "ref_id"],
        frequency=643, description="统计与参照对象同状态的其他同类对象数量"
    ),
    TemplateEntry(
        template_id="L2_count_A2",
        template="What number of other {type_plural} are there of the same status as {ref_id}?",
        answer_type="number", answer_logic="count_same_status",
        coverage_level="L2", question_type="count",
        major_pattern="same_status_count", variant_idx=2,
        required_params=["type_plural", "obj_type", "ref_id"],
        frequency=645, description="统计同状态其他同类数量(What number句式)"
    ),
    TemplateEntry(
        template_id="L2_count_A3",
        template="How many other {type_plural} are in the same status as {ref_id}?",
        answer_type="number", answer_logic="count_same_status",
        coverage_level="L2", question_type="count",
        major_pattern="same_status_count", variant_idx=3,
        required_params=["type_plural", "obj_type", "ref_id"],
        frequency=620, description="统计同状态其他同类数量(in the same句式)"
    ),
    TemplateEntry(
        template_id="L2_count_A4",
        template="What number of other {type_plural} are in the same status as {ref_id}?",
        answer_type="number", answer_logic="count_same_status",
        coverage_level="L2", question_type="count",
        major_pattern="same_status_count", variant_idx=4,
        required_params=["type_plural", "obj_type", "ref_id"],
        frequency=609, description="统计同状态其他同类数量(What number + in句式)"
    ),
    # --- 大样子 B: 泛指同状态计数 ---
    TemplateEntry(
        template_id="L2_count_B1",
        template="How many other things have the same status as {ref_id}?",
        answer_type="number", answer_logic="count_same_status_any",
        coverage_level="L2", question_type="count",
        major_pattern="same_status_things_count", variant_idx=1,
        required_params=["ref_id"],
        frequency=500, description="统计与参照对象同状态的所有其他对象数量"
    ),
    TemplateEntry(
        template_id="L2_count_B2",
        template="What number of other things are in the same status as {ref_id}?",
        answer_type="number", answer_logic="count_same_status_any",
        coverage_level="L2", question_type="count",
        major_pattern="same_status_things_count", variant_idx=2,
        required_params=["ref_id"],
        frequency=450, description="统计同状态所有其他对象数量(What number句式)"
    ),
    # same_status_count v5
    TemplateEntry(
        template_id="L2_count_A5",
        template="Count the other {type_plural} that share the same status as {ref_id}.",
        answer_type="number", answer_logic="count_same_status",
        coverage_level="L2", question_type="count",
        major_pattern="same_status_count", variant_idx=5,
        required_params=["type_plural", "obj_type", "ref_id"],
        frequency=0, description="统计同状态同类(祈使句)"
    ),
    # same_status_things_count v3
    TemplateEntry(
        template_id="L2_count_B3",
        template="Count the other objects that share the same status as {ref_id}.",
        answer_type="number", answer_logic="count_same_status_any",
        coverage_level="L2", question_type="count",
        major_pattern="same_status_things_count", variant_idx=3,
        required_params=["ref_id"],
        frequency=0, description="统计同状态所有对象(祈使句)"
    ),
    # --- 大样子 C: 双方向交集计数 ---
    TemplateEntry(
        template_id="L2_count_C1",
        template="How many {type_plural} are both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}?",
        answer_type="number", answer_logic="count_both_directions",
        coverage_level="L2", question_type="count",
        major_pattern="both_directions_count", variant_idx=1,
        required_params=["type_plural", "obj_type", "direction1", "ref1_id", "direction2", "ref2_id"],
        frequency=200, description="双方向交集计数"
    ),
    TemplateEntry(
        template_id="L2_count_C2",
        template="What number of {type_plural} are to the {direction1} of {ref1_id} and also to the {direction2} of {ref2_id}?",
        answer_type="number", answer_logic="count_both_directions",
        coverage_level="L2", question_type="count",
        major_pattern="both_directions_count", variant_idx=2,
        required_params=["type_plural", "obj_type", "direction1", "ref1_id", "direction2", "ref2_id"],
        frequency=0, description="双方向交集计数(What number)"
    ),
]

L2_STATUS_TEMPLATES = [
    # === [CHAIN] 链式方向状态查询: ref→[dir2]→mid→[dir1]→target, ask target.status ===
    TemplateEntry(
        template_id="L2_status_A1",
        template="What is the status of the {target_type} to the {direction1} of the {mid_type} that is to the {direction2} of {ref_id}?",
        answer_type="status", answer_logic="status_2hop_chain",
        coverage_level="L2", question_type="status",
        major_pattern="chain_direction_status", variant_idx=1,
        required_params=["target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=200, description="链式两跳方向状态查询"
    ),
    TemplateEntry(
        template_id="L2_status_A2",
        template="Is the {target_type} to the {direction1} of the {mid_type} to the {direction2} of {ref_id} moving or stopped?",
        answer_type="status", answer_logic="status_2hop_chain",
        coverage_level="L2", question_type="status",
        major_pattern="chain_direction_status", variant_idx=2,
        required_params=["target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=0, description="链式两跳状态(binary句式)"
    ),
    TemplateEntry(
        template_id="L2_status_A3",
        template="What state is the {target_type} to the {direction1} of the {mid_type} to the {direction2} of {ref_id} in?",
        answer_type="status", answer_logic="status_2hop_chain",
        coverage_level="L2", question_type="status",
        major_pattern="chain_direction_status", variant_idx=3,
        required_params=["target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=0, description="链式两跳状态(What state句式)"
    ),
    TemplateEntry(
        template_id="L2_status_A4",
        template="There is a {target_type} to the {direction1} of the {mid_type} to the {direction2} of {ref_id}; what is its status?",
        answer_type="status", answer_logic="status_2hop_chain",
        coverage_level="L2", question_type="status",
        major_pattern="chain_direction_status", variant_idx=4,
        required_params=["target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=0, description="链式两跳状态(There is句式)"
    ),
    TemplateEntry(
        template_id="L2_status_A5",
        template="Describe the status of the {target_type} to the {direction1} of the {mid_type} to the {direction2} of {ref_id}.",
        answer_type="status", answer_logic="status_2hop_chain",
        coverage_level="L2", question_type="status",
        major_pattern="chain_direction_status", variant_idx=5,
        required_params=["target_type", "direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=0, description="链式两跳状态(祈使句)"
    ),
    # === [COMPLEX] 双方向交集状态: ref1→[dir1]→target←[dir2]←ref2, ask target.status ===
    TemplateEntry(
        template_id="L2_status_B1",
        template="What is the status of the {target_type} that is both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}?",
        answer_type="status", answer_logic="status_both_directions",
        coverage_level="L2", question_type="status",
        major_pattern="both_directions_status", variant_idx=1,
        required_params=["target_type", "direction1", "ref1_id", "direction2", "ref2_id", "target_id"],
        frequency=0, description="双方向交集对象状态查询"
    ),
    TemplateEntry(
        template_id="L2_status_B2",
        template="Is the {target_type} to the {direction1} of {ref1_id} and the {direction2} of {ref2_id} moving or stopped?",
        answer_type="status", answer_logic="status_both_directions",
        coverage_level="L2", question_type="status",
        major_pattern="both_directions_status", variant_idx=2,
        required_params=["target_type", "direction1", "ref1_id", "direction2", "ref2_id", "target_id"],
        frequency=0, description="双方向交集状态(binary句式)"
    ),
    TemplateEntry(
        template_id="L2_status_B3",
        template="There is a {target_type} to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}; what is it doing?",
        answer_type="status", answer_logic="status_both_directions",
        coverage_level="L2", question_type="status",
        major_pattern="both_directions_status", variant_idx=3,
        required_params=["target_type", "direction1", "ref1_id", "direction2", "ref2_id", "target_id"],
        frequency=0, description="双方向交集状态(doing句式)"
    ),
    # === [STATUS] 同状态对象查询: A→[status]→X←[status]←B, ask shared status ===
    TemplateEntry(
        template_id="L2_status_C1",
        template="What status do {ref_id} and the other {obj_type} of the same type share?",
        answer_type="status", answer_logic="shared_status_same_type",
        coverage_level="L2", question_type="status",
        major_pattern="shared_status_query", variant_idx=1,
        required_params=["ref_id", "obj_type"],
        frequency=0, description="同类型对象共有状态查询"
    ),
    TemplateEntry(
        template_id="L2_status_C2",
        template="What is the common status among the {type_plural} near {ref_id}?",
        answer_type="status", answer_logic="common_status_near_ref",
        coverage_level="L2", question_type="status",
        major_pattern="shared_status_query", variant_idx=2,
        required_params=["type_plural", "obj_type", "ref_id"],
        frequency=0, description="参照对象附近同类共有状态"
    ),
]

L2_OBJECT_TEMPLATES = [
    # === [CHAIN] 链式方向对象查询: ref→[dir2]→mid→[dir1]→target, ask target.type ===
    TemplateEntry(
        template_id="L2_object_A1",
        template="There is a thing to the {direction1} of the {mid_type} that is to the {direction2} of {ref_id}; what is it?",
        answer_type="type", answer_logic="what_2hop_chain",
        coverage_level="L2", question_type="object",
        major_pattern="chain_direction_object", variant_idx=1,
        required_params=["direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=300, description="链式两跳方向对象查询"
    ),
    # === [COMPLEX] 双方向交集对象: ref1→[dir1]→target←[dir2]←ref2, ask target.type ===
    TemplateEntry(
        template_id="L2_object_B1",
        template="There is a thing that is both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}; what is it?",
        answer_type="type", answer_logic="what_both_directions",
        coverage_level="L2", question_type="object",
        major_pattern="both_directions_object", variant_idx=1,
        required_params=["direction1", "ref1_id", "direction2", "ref2_id", "target_id"],
        frequency=400, description="双方向交集对象查询"
    ),
    # === [COMPLEX] 双方向+状态对象: ref1→[dir1]→target{status}←[dir2]←ref2 ===
    TemplateEntry(
        template_id="L2_object_C1",
        template="There is a {status} thing that is both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}; what is it?",
        answer_type="type", answer_logic="what_status_both_directions",
        coverage_level="L2", question_type="object",
        major_pattern="both_directions_status_object", variant_idx=1,
        required_params=["status", "direction1", "ref1_id", "direction2", "ref2_id", "target_id"],
        frequency=300, description="双方向+状态对象查询"
    ),
    # chain_direction_object v2
    TemplateEntry(
        template_id="L2_object_A2",
        template="What is the thing to the {direction1} of the {mid_type} that is to the {direction2} of {ref_id}?",
        answer_type="type", answer_logic="what_2hop_chain",
        coverage_level="L2", question_type="object",
        major_pattern="chain_direction_object", variant_idx=2,
        required_params=["direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=0, description="链式两跳对象(What is the thing)"
    ),
    # both_directions_object v2
    TemplateEntry(
        template_id="L2_object_B2",
        template="What is to the {direction1} of {ref1_id} and also to the {direction2} of {ref2_id}?",
        answer_type="type", answer_logic="what_both_directions",
        coverage_level="L2", question_type="object",
        major_pattern="both_directions_object", variant_idx=2,
        required_params=["direction1", "ref1_id", "direction2", "ref2_id", "target_id"],
        frequency=0, description="双方向交集对象(What is)"
    ),
    # both_directions_status_object v2
    TemplateEntry(
        template_id="L2_object_C2",
        template="What {status} object is both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}?",
        answer_type="type", answer_logic="what_status_both_directions",
        coverage_level="L2", question_type="object",
        major_pattern="both_directions_status_object", variant_idx=2,
        required_params=["status", "direction1", "ref1_id", "direction2", "ref2_id", "target_id"],
        frequency=0, description="双方向+状态对象(What object)"
    ),
    # chain_direction_object v3-v4
    TemplateEntry(
        template_id="L2_object_A3",
        template="I see a {mid_type} to the {direction2} of {ref_id}; what is to the {direction1} of it?",
        answer_type="type", answer_logic="what_2hop_chain",
        coverage_level="L2", question_type="object",
        major_pattern="chain_direction_object", variant_idx=3,
        required_params=["direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=0, description="链式两跳对象(I see句式)"
    ),
    TemplateEntry(
        template_id="L2_object_A4",
        template="Identify the object to the {direction1} of the {mid_type} to the {direction2} of {ref_id}.",
        answer_type="type", answer_logic="what_2hop_chain",
        coverage_level="L2", question_type="object",
        major_pattern="chain_direction_object", variant_idx=4,
        required_params=["direction1", "mid_type", "direction2", "ref_id", "mid_id", "target_id"],
        frequency=0, description="链式两跳对象(祈使句)"
    ),
    # both_directions_object v3-v4
    TemplateEntry(
        template_id="L2_object_B3",
        template="Identify the object that is both to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}.",
        answer_type="type", answer_logic="what_both_directions",
        coverage_level="L2", question_type="object",
        major_pattern="both_directions_object", variant_idx=3,
        required_params=["direction1", "ref1_id", "direction2", "ref2_id", "target_id"],
        frequency=0, description="双方向交集对象(祈使句)"
    ),
    TemplateEntry(
        template_id="L2_object_B4",
        template="I see something to the {direction1} of {ref1_id} and the {direction2} of {ref2_id}; what type is it?",
        answer_type="type", answer_logic="what_both_directions",
        coverage_level="L2", question_type="object",
        major_pattern="both_directions_object", variant_idx=4,
        required_params=["direction1", "ref1_id", "direction2", "ref2_id", "target_id"],
        frequency=0, description="双方向交集对象(I see句式)"
    ),
    # === [STATUS] 同状态对象: A→[status]→X←[status]←B, ask B.type ===
    TemplateEntry(
        template_id="L2_object_D1",
        template="What is the other object that has the same status as {ref_id}?",
        answer_type="type", answer_logic="what_same_status_other",
        coverage_level="L2", question_type="object",
        major_pattern="same_status_object", variant_idx=1,
        required_params=["ref_id"],
        frequency=0, description="与参照对象同状态的另一对象"
    ),
    TemplateEntry(
        template_id="L2_object_D2",
        template="What type of object shares the same status as {ref_id}?",
        answer_type="type", answer_logic="what_same_status_other",
        coverage_level="L2", question_type="object",
        major_pattern="same_status_object", variant_idx=2,
        required_params=["ref_id"],
        frequency=0, description="同状态另一对象类型(shares句式)"
    ),
]

L2_COMPARISON_TEMPLATES = [
    # === [COMPLEX] 两方向对象比较: ref1→[dir1]→obj1 vs ref2→[dir2]→obj2, compare status ===
    TemplateEntry(
        template_id="L2_compare_A1",
        template="Does the {obj1_type} to the {direction1} of {ref1_id} have the same status as the {obj2_type} to the {direction2} of {ref2_id}?",
        answer_type="bool", answer_logic="compare_two_direction_refs",
        coverage_level="L2", question_type="comparison",
        major_pattern="two_direction_compare", variant_idx=1,
        required_params=["obj1_type", "obj1_id", "direction1", "ref1_id",
                         "obj2_type", "obj2_id", "direction2", "ref2_id"],
        frequency=200, description="比较两个方向对象的状态"
    ),
    TemplateEntry(
        template_id="L2_compare_A2",
        template="Do the {obj1_type} to the {direction1} of {ref1_id} and the {obj2_type} to the {direction2} of {ref2_id} have the same status?",
        answer_type="bool", answer_logic="compare_two_direction_refs",
        coverage_level="L2", question_type="comparison",
        major_pattern="two_direction_compare", variant_idx=2,
        required_params=["obj1_type", "obj1_id", "direction1", "ref1_id",
                         "obj2_type", "obj2_id", "direction2", "ref2_id"],
        frequency=200, description="比较两个方向对象状态(Do句式)"
    ),
    # two_direction_compare v3
    TemplateEntry(
        template_id="L2_compare_A3",
        template="Are the {obj1_type} to the {direction1} of {ref1_id} and the {obj2_type} to the {direction2} of {ref2_id} in the same state?",
        answer_type="bool", answer_logic="compare_two_direction_refs",
        coverage_level="L2", question_type="comparison",
        major_pattern="two_direction_compare", variant_idx=3,
        required_params=["obj1_type", "obj1_id", "direction1", "ref1_id",
                         "obj2_type", "obj2_id", "direction2", "ref2_id"],
        frequency=0, description="比较两方向对象状态(in the same state)"
    ),
    # === [COMPLEX] 方向对象 vs 直接对象: obj1 vs ref→[dir]→obj2, compare status ===
    TemplateEntry(
        template_id="L2_compare_B1",
        template="Does {obj1_id} have the same status as the {obj2_type} to the {direction} of {ref_id}?",
        answer_type="bool", answer_logic="compare_id_vs_direction_ref",
        coverage_level="L2", question_type="comparison",
        major_pattern="id_vs_direction_compare", variant_idx=1,
        required_params=["obj1_id", "obj2_type", "obj2_id", "direction", "ref_id"],
        frequency=200, description="ID对象与方向对象状态比较"
    ),
    TemplateEntry(
        template_id="L2_compare_B2",
        template="Is {obj1_id} in the same state as the {obj2_type} to the {direction} of {ref_id}?",
        answer_type="bool", answer_logic="compare_id_vs_direction_ref",
        coverage_level="L2", question_type="comparison",
        major_pattern="id_vs_direction_compare", variant_idx=2,
        required_params=["obj1_id", "obj2_type", "obj2_id", "direction", "ref_id"],
        frequency=0, description="ID对象与方向对象(in the same state)"
    ),
    TemplateEntry(
        template_id="L2_compare_B3",
        template="Do {obj1_id} and the {obj2_type} to the {direction} of {ref_id} share the same status?",
        answer_type="bool", answer_logic="compare_id_vs_direction_ref",
        coverage_level="L2", question_type="comparison",
        major_pattern="id_vs_direction_compare", variant_idx=3,
        required_params=["obj1_id", "obj2_type", "obj2_id", "direction", "ref_id"],
        frequency=0, description="ID对象与方向对象(share句式)"
    ),
]


# ============================================================================
#  NEW-L1: 方向查询模板 (Direction Query)
# ============================================================================

L1_DIRECTION_QUERY_TEMPLATES = [
    # --- 大样子 A: 查询对象相对ego的方向 ---
    TemplateEntry(
        template_id="L1_dirq_A1",
        template="In what direction is {obj_id} relative to me?",
        answer_type="direction", answer_logic="direction_of_id_from_ego",
        coverage_level="L1", question_type="object",
        major_pattern="direction_query_ego", variant_idx=1,
        required_params=["obj_id"],
        frequency=0, description="查询指定对象相对ego的方向"
    ),
    TemplateEntry(
        template_id="L1_dirq_A2",
        template="Where is {obj_id} relative to me?",
        answer_type="direction", answer_logic="direction_of_id_from_ego",
        coverage_level="L1", question_type="object",
        major_pattern="direction_query_ego", variant_idx=2,
        required_params=["obj_id"],
        frequency=0, description="查询对象方位(Where句式)"
    ),
    TemplateEntry(
        template_id="L1_dirq_A3",
        template="Which direction is {obj_id} from me?",
        answer_type="direction", answer_logic="direction_of_id_from_ego",
        coverage_level="L1", question_type="object",
        major_pattern="direction_query_ego", variant_idx=3,
        required_params=["obj_id"],
        frequency=0, description="查询对象方位(Which direction句式)"
    ),
    TemplateEntry(
        template_id="L1_dirq_A4",
        template="On which side is {obj_id}?",
        answer_type="direction", answer_logic="direction_of_id_from_ego",
        coverage_level="L1", question_type="object",
        major_pattern="direction_query_ego", variant_idx=4,
        required_params=["obj_id"],
        frequency=0, description="查询对象方位(On which side句式)"
    ),
    # --- 大样子 B: 查询对象相对ref的方向 ---
    TemplateEntry(
        template_id="L1_dirq_B1",
        template="In what direction is {obj_id} relative to {ref_id}?",
        answer_type="direction", answer_logic="direction_of_id_from_ref",
        coverage_level="L1", question_type="object",
        major_pattern="direction_query_ref", variant_idx=1,
        required_params=["obj_id", "ref_id"],
        frequency=0, description="查询指定对象相对ref的方向"
    ),
    TemplateEntry(
        template_id="L1_dirq_B2",
        template="Where is {obj_id} relative to {ref_id}?",
        answer_type="direction", answer_logic="direction_of_id_from_ref",
        coverage_level="L1", question_type="object",
        major_pattern="direction_query_ref", variant_idx=2,
        required_params=["obj_id", "ref_id"],
        frequency=0, description="查询对象相对ref方位(Where句式)"
    ),
    TemplateEntry(
        template_id="L1_dirq_B3",
        template="Which direction is {obj_id} from {ref_id}?",
        answer_type="direction", answer_logic="direction_of_id_from_ref",
        coverage_level="L1", question_type="object",
        major_pattern="direction_query_ref", variant_idx=3,
        required_params=["obj_id", "ref_id"],
        frequency=0, description="查询对象相对ref方位(Which direction句式)"
    ),
]

# ============================================================================
#  NEW-L1: 朝向+方向组合模板 (Heading + Direction — CV可见)
# ============================================================================

L1_HEADING_TEMPLATES = [
    # --- 大样子 A: 某方向对象的朝向 ---
    TemplateEntry(
        template_id="L1_heading_A1",
        template="Is the {obj_type} to the {direction} of me facing towards me?",
        answer_type="bool", answer_logic="is_facing_ego_direction",
        coverage_level="L1", question_type="exist",
        major_pattern="direction_heading_verify", variant_idx=1,
        required_params=["obj_type", "direction", "obj_id"],
        frequency=0, description="某方向对象是否面朝ego"
    ),
    TemplateEntry(
        template_id="L1_heading_A2",
        template="Is the {obj_type} to the {direction} of {ref_id} facing towards me?",
        answer_type="bool", answer_logic="is_facing_ego_ref_direction",
        coverage_level="L1", question_type="exist",
        major_pattern="direction_heading_verify", variant_idx=2,
        required_params=["obj_type", "direction", "ref_id", "obj_id"],
        frequency=0, description="ref某方向对象是否面朝ego"
    ),
    TemplateEntry(
        template_id="L1_heading_A3",
        template="Which way is the {obj_type} to the {direction} of me facing?",
        answer_type="heading", answer_logic="heading_of_direction_obj",
        coverage_level="L1", question_type="status",
        major_pattern="direction_heading_query", variant_idx=1,
        required_params=["obj_type", "direction", "obj_id"],
        frequency=0, description="查询某方向对象的朝向"
    ),
    TemplateEntry(
        template_id="L1_heading_A4",
        template="What direction is the {obj_type} to the {direction} of me pointed at?",
        answer_type="heading", answer_logic="heading_of_direction_obj",
        coverage_level="L1", question_type="status",
        major_pattern="direction_heading_query", variant_idx=2,
        required_params=["obj_type", "direction", "obj_id"],
        frequency=0, description="查询某方向对象朝向(pointed at)"
    ),
    # --- 大样子 B: 用朝向约束存在性 ---
    TemplateEntry(
        template_id="L1_heading_B1",
        template="Is there a {obj_type} facing towards me to the {direction}?",
        answer_type="bool", answer_logic="exists_facing_ego_in_direction",
        coverage_level="L1", question_type="exist",
        major_pattern="heading_constrained_exist", variant_idx=1,
        required_params=["obj_type", "direction"],
        frequency=0, description="某方向是否有面朝ego的对象"
    ),
    TemplateEntry(
        template_id="L1_heading_B2",
        template="Can you see a {obj_type} facing away from me to the {direction}?",
        answer_type="bool", answer_logic="exists_facing_away_in_direction",
        coverage_level="L1", question_type="exist",
        major_pattern="heading_constrained_exist", variant_idx=2,
        required_params=["obj_type", "direction"],
        frequency=0, description="某方向是否有背朝ego的对象"
    ),
]

# ============================================================================
#  NEW-L1: 距离相关模板 (Distance-based, 我们独有)
# ============================================================================

L1_DISTANCE_TEMPLATES = [
    # --- 方向: distance_bin_exist — 距离范围存在性 ---
    TemplateEntry(
        template_id="L1_dist_exist_A1",
        template="Is there a {obj_type} within {distance_threshold} meters?",
        answer_type="bool", answer_logic="exists_within_distance",
        coverage_level="L1", question_type="exist",
        major_pattern="distance_bin_exist", variant_idx=1,
        required_params=["obj_type", "distance_threshold"],
        frequency=0, description="某距离范围内是否存在某类型"
    ),
    TemplateEntry(
        template_id="L1_dist_exist_A2",
        template="Are there any {type_plural} closer than {distance_threshold} meters?",
        answer_type="bool", answer_logic="exists_within_distance",
        coverage_level="L1", question_type="exist",
        major_pattern="distance_bin_exist", variant_idx=2,
        required_params=["type_plural", "obj_type", "distance_threshold"],
        frequency=0, description="某距离范围内存在性(变体)"
    ),
    # --- 方向: distance_bin_direction_exist — 方向+距离存在性 ---
    TemplateEntry(
        template_id="L1_dist_exist_B1",
        template="Is there a {obj_type} within {distance_threshold} meters to the {direction} of me?",
        answer_type="bool", answer_logic="exists_within_distance_direction",
        coverage_level="L1", question_type="exist",
        major_pattern="distance_bin_direction_exist", variant_idx=1,
        required_params=["obj_type", "distance_threshold", "direction"],
        frequency=0, description="某方向某距离内是否有某类型"
    ),
    # --- 方向: count_in_distance_bin — 距离范围计数 ---
    TemplateEntry(
        template_id="L1_dist_count_A1",
        template="How many {type_plural} are within {distance_threshold} meters?",
        answer_type="number", answer_logic="count_within_distance",
        coverage_level="L1", question_type="count",
        major_pattern="count_in_distance_bin", variant_idx=1,
        required_params=["type_plural", "obj_type", "distance_threshold"],
        frequency=0, description="某距离范围内某类型数量"
    ),
    TemplateEntry(
        template_id="L1_dist_count_A2",
        template="What number of {type_plural} are within {distance_threshold} meters of me?",
        answer_type="number", answer_logic="count_within_distance",
        coverage_level="L1", question_type="count",
        major_pattern="count_in_distance_bin", variant_idx=2,
        required_params=["type_plural", "obj_type", "distance_threshold"],
        frequency=0, description="某距离范围内某类型数量(变体)"
    ),
    # --- 方向: count_in_distance_direction — 方向+距离计数 ---
    TemplateEntry(
        template_id="L1_dist_count_B1",
        template="How many {type_plural} are within {distance_threshold} meters to the {direction} of me?",
        answer_type="number", answer_logic="count_within_distance_direction",
        coverage_level="L1", question_type="count",
        major_pattern="count_in_distance_direction", variant_idx=1,
        required_params=["type_plural", "obj_type", "distance_threshold", "direction"],
        frequency=0, description="某方向某距离内数量"
    ),
    # --- 方向: nearest_type — 最近的某类型是谁 ---
    TemplateEntry(
        template_id="L1_dist_object_A1",
        template="What is the nearest {obj_type}?",
        answer_type="type", answer_logic="nearest_of_type",
        coverage_level="L1", question_type="object",
        major_pattern="nearest_type", variant_idx=1,
        required_params=["obj_type"],
        frequency=0, description="最近的某类型对象"
    ),
    TemplateEntry(
        template_id="L1_dist_object_A2",
        template="Which {obj_type} is closest to me?",
        answer_type="type", answer_logic="nearest_of_type",
        coverage_level="L1", question_type="object",
        major_pattern="nearest_type", variant_idx=2,
        required_params=["obj_type"],
        frequency=0, description="最近的某类型对象(变体)"
    ),
    # --- 方向: nearest_in_direction — 某方向最近的是什么 ---
    TemplateEntry(
        template_id="L1_dist_object_B1",
        template="What is the nearest thing to the {direction} of me?",
        answer_type="type", answer_logic="nearest_in_direction",
        coverage_level="L1", question_type="object",
        major_pattern="nearest_in_direction", variant_idx=1,
        required_params=["direction"],
        frequency=0, description="某方向最近的对象类型"
    ),
    TemplateEntry(
        template_id="L1_dist_object_B2",
        template="What is the closest object to the {direction}?",
        answer_type="type", answer_logic="nearest_in_direction",
        coverage_level="L1", question_type="object",
        major_pattern="nearest_in_direction", variant_idx=2,
        required_params=["direction"],
        frequency=0, description="某方向最近对象(变体)"
    ),
    # distance_bin_exist v3
    TemplateEntry(
        template_id="L1_dist_exist_A3",
        template="Can you see a {obj_type} within {distance_threshold} meters?",
        answer_type="bool", answer_logic="exists_within_distance",
        coverage_level="L1", question_type="exist",
        major_pattern="distance_bin_exist", variant_idx=3,
        required_params=["obj_type", "distance_threshold"],
        frequency=0, description="距离范围存在性(Can you see)"
    ),
    # distance_bin_direction_exist v2
    TemplateEntry(
        template_id="L1_dist_exist_B2",
        template="Can you see a {obj_type} within {distance_threshold} meters to the {direction}?",
        answer_type="bool", answer_logic="exists_within_distance_direction",
        coverage_level="L1", question_type="exist",
        major_pattern="distance_bin_direction_exist", variant_idx=2,
        required_params=["obj_type", "distance_threshold", "direction"],
        frequency=0, description="方向+距离存在性(Can you see)"
    ),
    # count_in_distance_bin v3
    TemplateEntry(
        template_id="L1_dist_count_A3",
        template="Count the {type_plural} within {distance_threshold} meters.",
        answer_type="number", answer_logic="count_within_distance",
        coverage_level="L1", question_type="count",
        major_pattern="count_in_distance_bin", variant_idx=3,
        required_params=["type_plural", "obj_type", "distance_threshold"],
        frequency=0, description="距离范围计数(祈使句)"
    ),
    # nearest_type v3
    TemplateEntry(
        template_id="L1_dist_object_A3",
        template="Identify the closest {obj_type} to me.",
        answer_type="type", answer_logic="nearest_of_type",
        coverage_level="L1", question_type="object",
        major_pattern="nearest_type", variant_idx=3,
        required_params=["obj_type"],
        frequency=0, description="最近某类型(祈使句)"
    ),
    # nearest_in_direction v3
    TemplateEntry(
        template_id="L1_dist_object_B3",
        template="What is the closest object to the {direction} of me?",
        answer_type="type", answer_logic="nearest_in_direction",
        coverage_level="L1", question_type="object",
        major_pattern="nearest_in_direction", variant_idx=3,
        required_params=["direction"],
        frequency=0, description="某方向最近对象(closest)"
    ),
    # --- 方向: farthest_type — 最远的某类型 ---
    TemplateEntry(
        template_id="L1_dist_object_C1",
        template="What is the farthest {obj_type}?",
        answer_type="type", answer_logic="farthest_of_type",
        coverage_level="L1", question_type="object",
        major_pattern="farthest_type", variant_idx=1,
        required_params=["obj_type"],
        frequency=0, description="最远的某类型对象"
    ),
    TemplateEntry(
        template_id="L1_dist_object_C2",
        template="Which {obj_type} is farthest from me?",
        answer_type="type", answer_logic="farthest_of_type",
        coverage_level="L1", question_type="object",
        major_pattern="farthest_type", variant_idx=2,
        required_params=["obj_type"],
        frequency=0, description="最远某类型(变体)"
    ),
]

# ============================================================================
#  NEW-L1: 速度相关模板 (Velocity-based, 我们独有)
# ============================================================================

L1_VELOCITY_TEMPLATES = [
    # --- 方向: is_approaching — 是否正在接近 ---
    TemplateEntry(
        template_id="L1_vel_C1",
        template="Is the {obj_type} to the {direction} of me approaching or moving away?",
        answer_type="approach", answer_logic="is_approaching_direction",
        coverage_level="L1", question_type="status",
        major_pattern="is_approaching", variant_idx=1,
        required_params=["obj_type", "direction", "obj_id"],
        frequency=0, description="某方向对象是否正在接近"
    ),
    TemplateEntry(
        template_id="L1_vel_C2",
        template="Is {obj_id} getting closer or moving away from me?",
        answer_type="approach", answer_logic="is_approaching_id",
        coverage_level="L1", question_type="status",
        major_pattern="is_approaching", variant_idx=2,
        required_params=["obj_id"],
        frequency=0, description="指定对象是否接近(getting closer)"
    ),
    TemplateEntry(
        template_id="L1_vel_C3",
        template="Is {obj_id} approaching me?",
        answer_type="bool", answer_logic="is_approaching_id",
        coverage_level="L1", question_type="status",
        major_pattern="is_approaching", variant_idx=3,
        required_params=["obj_id"],
        frequency=0, description="指定对象是否接近(bool)"
    ),
    TemplateEntry(
        template_id="L1_vel_C4",
        template="Is {obj_id} coming towards me or going away?",
        answer_type="approach", answer_logic="is_approaching_id",
        coverage_level="L1", question_type="status",
        major_pattern="is_approaching", variant_idx=4,
        required_params=["obj_id"],
        frequency=0, description="指定对象接近/远离(coming towards)"
    ),
    TemplateEntry(
        template_id="L1_vel_C5",
        template="Is the {obj_type} to the {direction} of me getting closer?",
        answer_type="bool", answer_logic="is_approaching_direction",
        coverage_level="L1", question_type="status",
        major_pattern="is_approaching", variant_idx=5,
        required_params=["obj_type", "direction", "obj_id"],
        frequency=0, description="某方向对象是否接近(getting closer)"
    ),
    # --- 方向: speed_compare — 两对象速度比较 ---
    TemplateEntry(
        template_id="L1_vel_D1",
        template="Is {obj1_id} moving faster than {obj2_id}?",
        answer_type="bool", answer_logic="compare_speed_two_ids",
        coverage_level="L1", question_type="comparison",
        major_pattern="speed_compare", variant_idx=1,
        required_params=["obj1_id", "obj2_id"],
        frequency=0, description="比较两对象速度"
    ),
    TemplateEntry(
        template_id="L1_vel_D2",
        template="Which is faster, {obj1_id} or {obj2_id}?",
        answer_type="id", answer_logic="compare_speed_two_ids_which",
        coverage_level="L1", question_type="comparison",
        major_pattern="speed_compare", variant_idx=2,
        required_params=["obj1_id", "obj2_id"],
        frequency=0, description="比较两对象速度(which句式)"
    ),
    TemplateEntry(
        template_id="L1_vel_D3",
        template="Between {obj1_id} and {obj2_id}, which one is moving faster?",
        answer_type="id", answer_logic="compare_speed_two_ids_which",
        coverage_level="L1", question_type="comparison",
        major_pattern="speed_compare", variant_idx=3,
        required_params=["obj1_id", "obj2_id"],
        frequency=0, description="比较两对象速度(Between句式)"
    ),
    # --- 方向: moving_direction — 运动方向查询 ---
    TemplateEntry(
        template_id="L1_vel_E1",
        template="In what direction is {obj_id} moving?",
        answer_type="direction", answer_logic="moving_direction_of_id",
        coverage_level="L1", question_type="status",
        major_pattern="moving_direction", variant_idx=1,
        required_params=["obj_id"],
        frequency=0, description="指定对象运动方向"
    ),
    TemplateEntry(
        template_id="L1_vel_E2",
        template="Which way is {obj_id} heading?",
        answer_type="direction", answer_logic="moving_direction_of_id",
        coverage_level="L1", question_type="status",
        major_pattern="moving_direction", variant_idx=2,
        required_params=["obj_id"],
        frequency=0, description="指定对象行进方向(heading)"
    ),
]

# ============================================================================
#  NEW-L2: 跨属性组合模板 (Cross-attribute, 复杂情境变体)
#  保留CV可见的相对判断(closer/farthest/between), 去掉velocity/approaching/count/精确米数
# ============================================================================

L2_CROSS_TEMPLATES = [
    # --- 方向: compare_distance — 距离比较 ---
    TemplateEntry(
        template_id="L2_cross_A1",
        template="Is {obj1_id} closer to me than {obj2_id}?",
        answer_type="bool", answer_logic="compare_distance_two_ids",
        coverage_level="L2", question_type="comparison",
        major_pattern="compare_distance", variant_idx=1,
        required_params=["obj1_id", "obj2_id"],
        frequency=0, description="比较两对象到ego的距离"
    ),
    TemplateEntry(
        template_id="L2_cross_A2",
        template="Which is closer to me, {obj1_id} or {obj2_id}?",
        answer_type="id", answer_logic="compare_distance_two_ids_which",
        coverage_level="L2", question_type="comparison",
        major_pattern="compare_distance", variant_idx=2,
        required_params=["obj1_id", "obj2_id"],
        frequency=0, description="比较两对象到ego的距离(which句式)"
    ),
    # --- 方向: nearest_direction_status — 某方向最近对象的状态 ---
    TemplateEntry(
        template_id="L2_cross_D1",
        template="What is the status of the nearest {obj_type} to the {direction} of me?",
        answer_type="status", answer_logic="status_nearest_direction",
        coverage_level="L2", question_type="status",
        major_pattern="nearest_direction_status", variant_idx=1,
        required_params=["obj_type", "direction"],
        frequency=0, description="某方向最近对象的状态"
    ),
    TemplateEntry(
        template_id="L2_cross_D2",
        template="What status is the closest {obj_type} to the {direction}?",
        answer_type="status", answer_logic="status_nearest_direction",
        coverage_level="L2", question_type="status",
        major_pattern="nearest_direction_status", variant_idx=2,
        required_params=["obj_type", "direction"],
        frequency=0, description="某方向最近对象状态(变体)"
    ),
    # --- 方向: nearest_status — 最近对象的状态 ---
    TemplateEntry(
        template_id="L2_cross_E1",
        template="What is the status of the nearest {obj_type}?",
        answer_type="status", answer_logic="status_of_nearest",
        coverage_level="L2", question_type="status",
        major_pattern="nearest_status", variant_idx=1,
        required_params=["obj_type"],
        frequency=0, description="最近某类型对象的状态"
    ),
    # --- 方向: same_status_nearest — 最近同状态同类 ---
    TemplateEntry(
        template_id="L2_cross_H1",
        template="Is the nearest {obj_type} in the same status as the farthest {obj_type}?",
        answer_type="bool", answer_logic="compare_nearest_farthest_status",
        coverage_level="L2", question_type="comparison",
        major_pattern="compare_nearest_farthest", variant_idx=1,
        required_params=["obj_type"],
        frequency=0, description="最近vs最远同类对象状态比较"
    ),
    # --- 方向: object_between — 两对象之间的对象 ---
    TemplateEntry(
        template_id="L2_cross_J1",
        template="Is there any {obj_type} between {ref1_id} and {ref2_id}?",
        answer_type="bool", answer_logic="exists_between_two",
        coverage_level="L2", question_type="exist",
        major_pattern="object_between", variant_idx=1,
        required_params=["obj_type", "ref1_id", "ref2_id"],
        frequency=0, description="两对象之间是否有某类型"
    ),
    # compare_distance v3
    TemplateEntry(
        template_id="L2_cross_A3",
        template="Between {obj1_id} and {obj2_id}, which one is nearer to me?",
        answer_type="id", answer_logic="compare_distance_two_ids_which",
        coverage_level="L2", question_type="comparison",
        major_pattern="compare_distance", variant_idx=3,
        required_params=["obj1_id", "obj2_id"],
        frequency=0, description="比较两对象距离(Between句式)"
    ),
    # nearest_direction_status v3
    TemplateEntry(
        template_id="L2_cross_D3",
        template="Is the nearest {obj_type} to the {direction} moving or stopped?",
        answer_type="status", answer_logic="status_nearest_direction",
        coverage_level="L2", question_type="status",
        major_pattern="nearest_direction_status", variant_idx=3,
        required_params=["obj_type", "direction"],
        frequency=0, description="某方向最近对象状态(binary)"
    ),
    # nearest_status v2
    TemplateEntry(
        template_id="L2_cross_E2",
        template="Is the nearest {obj_type} moving or stopped?",
        answer_type="status", answer_logic="status_of_nearest",
        coverage_level="L2", question_type="status",
        major_pattern="nearest_status", variant_idx=2,
        required_params=["obj_type"],
        frequency=0, description="最近某类型状态(binary)"
    ),
    # object_between v2
    TemplateEntry(
        template_id="L2_cross_J2",
        template="Can you see a {obj_type} between {ref1_id} and {ref2_id}?",
        answer_type="bool", answer_logic="exists_between_two",
        coverage_level="L2", question_type="exist",
        major_pattern="object_between", variant_idx=2,
        required_params=["obj_type", "ref1_id", "ref2_id"],
        frequency=0, description="两对象之间(Can you see)"
    ),
]


# ============================================================================
#  模板注册表 (Template Registry)
# ============================================================================

ALL_TEMPLATES: List[TemplateEntry] = (
    # --- L0: 节点覆盖 (exist/status/object/comparison + heading) ---
    L0_EXIST_TEMPLATES + L0_STATUS_TEMPLATES +
    L0_OBJECT_TEMPLATES + L0_HEADING_TEMPLATES + L0_COMPARISON_TEMPLATES +
    # --- L1: 边覆盖 (exist/status/object/comparison + direction_query + heading) ---
    L1_EXIST_TEMPLATES + L1_STATUS_TEMPLATES +
    L1_OBJECT_TEMPLATES + L1_COMPARISON_TEMPLATES +
    L1_DIRECTION_QUERY_TEMPLATES + L1_HEADING_TEMPLATES +
    # --- L2: 两跳路径覆盖 ---
    #   核心 = 首尾相连两连边 A→[edge1]→B→[edge2]→C (chain 模式)
    #   辅助 = 包含两连边的复杂情境 (intersection/comparison/nearest)
    #   去掉: count, velocity/approaching, 精确距离米数
    L2_EXIST_TEMPLATES + L2_STATUS_TEMPLATES +
    L2_OBJECT_TEMPLATES + L2_COMPARISON_TEMPLATES +
    L2_CROSS_TEMPLATES
)


class TemplateLibrary:
    """
    模板库管理器 — 提供按各级结构检索模板的接口
    """

    def __init__(self):
        self._templates: Dict[str, TemplateEntry] = {}
        self._by_level: Dict[str, List[TemplateEntry]] = defaultdict(list)
        self._by_type: Dict[str, List[TemplateEntry]] = defaultdict(list)
        self._by_pattern: Dict[str, List[TemplateEntry]] = defaultdict(list)
        self._by_level_type: Dict[Tuple[str, str], List[TemplateEntry]] = defaultdict(list)
        self._register_all()

    def _register_all(self):
        for t in ALL_TEMPLATES:
            self._templates[t.template_id] = t
            self._by_level[t.coverage_level].append(t)
            self._by_type[t.question_type].append(t)
            self._by_pattern[t.major_pattern].append(t)
            self._by_level_type[(t.coverage_level, t.question_type)].append(t)

    # ---- 检索接口 ----

    def get(self, template_id: str) -> Optional[TemplateEntry]:
        return self._templates.get(template_id)

    def get_by_level(self, level: str) -> List[TemplateEntry]:
        return self._by_level.get(level, [])

    def get_by_type(self, qtype: str) -> List[TemplateEntry]:
        return self._by_type.get(qtype, [])

    def get_by_level_type(self, level: str, qtype: str) -> List[TemplateEntry]:
        return self._by_level_type.get((level, qtype), [])

    def get_by_pattern(self, pattern: str) -> List[TemplateEntry]:
        return self._by_pattern.get(pattern, [])

    def get_all(self) -> List[TemplateEntry]:
        return list(ALL_TEMPLATES)

    def get_cv_friendly(self, level: str = None, qtype: str = None) -> List[TemplateEntry]:
        """获取CV可答模板（可选按level/qtype过滤）"""
        if level and qtype:
            candidates = self.get_by_level_type(level, qtype)
        elif level:
            candidates = self.get_by_level(level)
        elif qtype:
            candidates = self.get_by_type(qtype)
        else:
            candidates = list(ALL_TEMPLATES)
        return [t for t in candidates if t.cv_friendly]

    def get_non_cv_friendly(self) -> List[TemplateEntry]:
        """获取非CV可答模板列表"""
        return [t for t in ALL_TEMPLATES if not t.cv_friendly]

    # ---- 统计 ----

    def summary(self) -> Dict:
        """返回四级结构统计"""
        stats = {
            "total": len(ALL_TEMPLATES),
            "by_level": {},
            "by_type": {},
            "by_level_type": {},
            "patterns": {},
        }
        for level in ["L0", "L1", "L2"]:
            templates = self._by_level.get(level, [])
            stats["by_level"][level] = len(templates)
            for qtype in ["exist", "count", "status", "object", "comparison"]:
                key = f"{level}_{qtype}"
                lt = self._by_level_type.get((level, qtype), [])
                stats["by_level_type"][key] = len(lt)
                # 按 major_pattern 细分
                patterns = defaultdict(int)
                for t in lt:
                    patterns[t.major_pattern] += 1
                if patterns:
                    stats["patterns"][key] = dict(patterns)
        for qtype in ["exist", "count", "status", "object", "comparison"]:
            stats["by_type"][qtype] = len(self._by_type.get(qtype, []))
        return stats

    def print_hierarchy(self):
        """打印四级结构层次"""
        print("=" * 70)
        print("  QA Template Library — 四级结构总览")
        print("=" * 70)
        summary = self.summary()
        print(f"\n总模板数: {summary['total']} (全部CV可答)")
        for level in ["L0", "L1", "L2"]:
            print(f"\n{'─' * 50}")
            print(f"  {level} ({summary['by_level'][level]} templates)")
            print(f"{'─' * 50}")
            for qtype in ["exist", "count", "status", "object", "comparison"]:
                key = f"{level}_{qtype}"
                count = summary["by_level_type"].get(key, 0)
                if count == 0:
                    continue
                print(f"    {qtype}: {count} templates")
                patterns = summary["patterns"].get(key, {})
                for pattern, pcount in patterns.items():
                    print(f"      └── {pattern}: {pcount} variants")


# 模块级单例
_library_instance: Optional[TemplateLibrary] = None


def get_template_library() -> TemplateLibrary:
    """获取模板库单例"""
    global _library_instance
    if _library_instance is None:
        _library_instance = TemplateLibrary()
    return _library_instance
