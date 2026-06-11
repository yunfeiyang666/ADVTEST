"""
QA Generator V2 - Configuration
基于NuScenesQA风格，使用Source Frame和六相机方位映射
"""
from typing import Dict, List, Tuple

# ==================== 六相机定义 ====================
CAMERA_NAMES = [
    "CAM_FRONT",
    "CAM_FRONT_LEFT", 
    "CAM_FRONT_RIGHT",
    "CAM_BACK",
    "CAM_BACK_LEFT",
    "CAM_BACK_RIGHT"
]

# 相机视角范围（以Ego为中心的角度范围，单位：度）
# 用于将对象方位映射到可能出现的相机
CAMERA_FOV_RANGES = {
    "CAM_FRONT": (-30, 30),           # 正前方 ±30°
    "CAM_FRONT_LEFT": (30, 90),       # 左前方 30°-90°
    "CAM_FRONT_RIGHT": (-90, -30),    # 右前方 -90°到-30°
    "CAM_BACK": (150, -150),          # 正后方 150°到-150°（跨越180°）
    "CAM_BACK_LEFT": (90, 150),       # 左后方 90°-150°
    "CAM_BACK_RIGHT": (-150, -90),    # 右后方 -150°到-90°
}

# ==================== 对象类型 ====================
OBJECT_TYPES = [
    "car",
    "pedestrian", 
    "bicycle",
    "motorcycle",
    "truck",
    "bus",
    "trailer",
    "barrier",
    "traffic_cone",
    "construction_vehicle"
]

# 对象类型显示名称（单数，复数）
TYPE_NAMES = {
    "car": ("car", "cars"),
    "pedestrian": ("pedestrian", "pedestrians"),
    "bicycle": ("bicycle", "bicycles"),
    "motorcycle": ("motorcycle", "motorcycles"),
    "truck": ("truck", "trucks"),
    "bus": ("bus", "buses"),
    "trailer": ("trailer", "trailers"),
    "barrier": ("barrier", "barriers"),
    "traffic_cone": ("traffic cone", "traffic cones"),
    "construction_vehicle": ("construction vehicle", "construction vehicles"),
    "thing": ("thing", "things"),  # 泛指
}

# ==================== 状态定义 ====================
VEHICLE_STATUSES = ["moving", "stopped", "parked"]
PEDESTRIAN_STATUSES = ["moving", "standing", "sitting", "not standing"]
CYCLE_STATUSES = ["with_rider", "without_rider", "with rider", "without rider"]

# 状态显示名称映射
STATUS_DISPLAY_NAMES = {
    "moving": "moving",
    "stopped": "stopped",
    "parked": "parked",
    "standing": "standing",
    "sitting": "sitting",
    "not_standing": "not standing",
    "with_rider": "with rider",
    "without_rider": "without rider",
    "with rider": "with rider",
    "without rider": "without rider",
}

# ==================== 方向定义 (Source Frame) ====================
# 8方向（基于被描述对象自身朝向）
DIRECTIONS_8 = [
    "front",
    "front-left",
    "left", 
    "back-left",
    "back",
    "back-right",
    "right",
    "front-right"
]

# 4方向（简化版）
DIRECTIONS_4 = ["front", "left", "back", "right"]

# ==================== 问题类型 (v3: 去掉count) ====================
QUESTION_TYPES = [
    "exist",       # 存在性判断
    "status",      # 状态查询
    "object",      # 对象识别
    "comparison"   # 状态比较
]

# ==================== 朝向分类 (CV可见 — 图片可见车头朝向) ====================
HEADING_CLASSES = [
    "facing_ego",       # 面朝ego
    "away_from_ego",    # 背朝ego
    "lateral_left",     # 侧向左
    "lateral_right",    # 侧向右
]

# ==================== 可见度分级 (NuScenes visibility) ====================
VISIBILITY_LEVELS = [
    "v0-40",     # 严重遮挡
    "v40-60",    # 部分遮挡
    "v60-80",    # 轻微遮挡
    "v80-100",   # 几乎完全可见
]

# ==================== 尺寸分类 ====================
SIZE_CLASSES = ["small", "medium", "large"]

# ==================== 生成参数 ====================
QA_CONFIG = {
    # 每个场景最大生成问题数
    "max_questions_per_scene": 100,
    
    # 每个覆盖层级的比例
    "difficulty_distribution": {
        "L0": 0.25,  # 25%
        "L1": 0.45,  # 45%
        "L2": 0.30,  # 30% (提升L2比例，强化两连边覆盖)
    },
    
    # 选择题选项数量
    "num_options": 4,
    
    # 是否使用8方向（False则用4方向）
    "use_8_directions": True,
    
    # 问题模板采样策略
    "template_sampling": "balanced",  # balanced / weighted / random
    
    # LLM生成参数
    "llm_temperature": 0.7,
    "llm_max_tokens": 512,
    
    # 答案验证
    "verify_answers_with_vqa": True,  # 是否用VQA pipeline验证答案
    "max_retries": 3,  # 答案错误时的最大重试次数
}

# ==================== LLM配置 ====================
import os

LLM_CONFIG = {
    "api_key": os.getenv("VQA_API_KEY", "sk-ecd91655d033446b9ae8ea390e65d923"),
    "api_base": os.getenv("VQA_API_BASE_URL", "https://maas-api.ai-yuanjing.com/openapi/compatible-mode/v1"),
    "model": os.getenv("VQA_MODEL_NAME", "deepseek-r1"),
    "verify_ssl": os.getenv("VQA_VERIFY_SSL", "false").lower() in ("true", "1"),
}
