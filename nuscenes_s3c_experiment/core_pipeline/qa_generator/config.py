"""
QA Generator 配置文件

定义：
- 方向词汇（基于六相机视图 + Source Frame）
- 对象类型
- 状态类型
- 答案词表
"""
from typing import Dict, List, Tuple

# ==================== 方向配置 (Source Frame) ====================
# 基于六相机视图的8方位划分
# 所有方向都以描述对象（source object）的朝向为零度线

DIRECTIONS_8 = [
    "front",        # 正前方 (-22.5°, 22.5°]
    "front-left",   # 前左 (22.5°, 67.5°]
    "left",         # 左侧 (67.5°, 112.5°]
    "back-left",    # 后左 (112.5°, 157.5°]
    "back",         # 正后方 (157.5°, 180°] ∪ (-180°, -157.5°]
    "back-right",   # 后右 (-157.5°, -112.5°]
    "right",        # 右侧 (-112.5°, -67.5°]
    "front-right",  # 前右 (-67.5°, -22.5°]
]

DIRECTIONS_4 = ["front", "left", "back", "right"]

# 六相机与方向的对应关系
CAMERA_DIRECTION_MAP = {
    "CAM_FRONT": "front",
    "CAM_FRONT_LEFT": "front-left",
    "CAM_FRONT_RIGHT": "front-right",
    "CAM_BACK": "back",
    "CAM_BACK_LEFT": "back-left",
    "CAM_BACK_RIGHT": "back-right",
}

# ==================== 对象类型 ====================
OBJECT_TYPES = [
    "car",
    "truck", 
    "bus",
    "trailer",
    "motorcycle",
    "bicycle",
    "pedestrian",
    "barrier",
    "traffic_cone",
    "construction_vehicle",
]

# 用于自然语言的类型名称映射（单数/复数）
TYPE_NAMES = {
    "car": ("car", "cars"),
    "truck": ("truck", "trucks"),
    "bus": ("bus", "buses"),
    "trailer": ("trailer", "trailers"),
    "motorcycle": ("motorcycle", "motorcycles"),  # 复数正确
    "bicycle": ("bicycle", "bicycles"),
    "pedestrian": ("pedestrian", "pedestrians"),
    "barrier": ("barrier", "barriers"),
    "traffic_cone": ("traffic cone", "traffic cones"),
    "construction_vehicle": ("construction vehicle", "construction vehicles"),
}

# ==================== 状态类型 ====================
# 车辆状态
VEHICLE_STATUSES = ["moving", "stopped", "parked"]

# 行人状态
PEDESTRIAN_STATUSES = ["moving", "standing", "sitting", "not standing"]

# 自行车/摩托车状态
CYCLE_STATUSES = ["with_rider", "without_rider"]

# 状态显示名称（用于自然语言）
STATUS_DISPLAY_NAMES = {
    "moving": "moving",
    "stopped": "stopped",
    "parked": "parked",
    "standing": "standing",
    "sitting": "sitting",
    "not standing": "not standing",
    "with_rider": "with rider",
    "without_rider": "without rider",
}

# ==================== 答案词表 (与NuScenes-QA对齐) ====================
ANSWER_VOCAB = {
    # 数字
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4,
    "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10,
    # 布尔
    "no": 11, "yes": 12,
    # 对象类型
    "barrier": 13, "bicycle": 14, "bus": 15, "car": 16,
    "construction vehicle": 17, "motorcycle": 18, "pedestrian": 22,
    "traffic cone": 25, "trailer": 26, "truck": 27,
    # 状态
    "moving": 19, "not standing": 20, "parked": 21,
    "standing": 23, "stopped": 24, "with rider": 28, "without rider": 29,
}

# ==================== 问题难度等级 ====================
DIFFICULTY_LEVELS = {
    "L0": "单对象属性查询",      # What is the status of car1?
    "L1": "单跳空间关系查询",    # Is there a car to the front of truck1?
    "L2": "两跳链式查询",          # What is the status of the car to the left of the truck that is in front of ego?
}

# ==================== 距离阈值 ====================
DISTANCE_THRESHOLDS = {
    "near": (0, 10),       # 近距离
    "mid": (10, 25),       # 中距离  
    "far": (25, 50),       # 远距离
    "visible": (0, 50),    # 可见范围内
}

# ==================== 生成参数 ====================
# CV可见属性说明：
#   保留： type / status (stopped/moving/parked/with_rider/without_rider/standing)
#           direction (8方位) / distance_level (near/mid/far)
#   移除： 速度/TTC等数字属性、count类问题类型
QA_CONFIG = {
    # 方向系统
    "direction_frame": "source",  # "source" 或 "ego"
    "use_8_directions": True,     # True=8方位, False=4方位

    # 生成控制
    "max_questions_per_scene": 100,

    # 选项生成
    "num_options": 4,             # 选择题选项数量
    "option_labels": ["A", "B", "C", "D"],

    # 问题类型权重（用于采样）— 已移除 count
    "type_weights": {
        "exist": 0.3,
        "status": 0.3,
        "object": 0.2,
        "comparison": 0.2,
    },

    # 包含对象ID
    "include_object_id": True,    # 问题中是否包含精确 ID
}
