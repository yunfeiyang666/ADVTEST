"""
NuScenes S3C实验配置文件

改进内容：
1. 支持环境变量覆盖
2. 路径验证
3. 配置分组和文档
4. 类型提示
5. 配置验证函数
"""
import os
import sys
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional, List

# 配置日志
logger = logging.getLogger(__name__)

# ==================== 路径配置（与 advtest_paths / unified_site 一致）====================
# 须先 load_advtest_env() 再 import config（入口脚本已按此顺序）。
from advtest_paths import NUSCENES_DATAROOT as _NUSC_DR, NUSCENES_DEVKIT_PATH, NUSCENES_VERSION

NUSCENES_DATAROOT: str = str(_NUSC_DR)

# 项目根目录
PROJECT_ROOT: str = os.path.dirname(os.path.abspath(__file__))

# 输出目录（支持环境变量覆盖）
OUTPUT_DIR: str = os.getenv(
    'OUTPUT_DIR',
    os.path.join(PROJECT_ROOT, "output")
)
SCENE_GRAPHS_DIR: str = os.path.join(OUTPUT_DIR, "scene_graphs")
CLUSTERS_DIR: str = os.path.join(OUTPUT_DIR, "clusters")
STATISTICS_DIR: str = os.path.join(OUTPUT_DIR, "statistics")
FIGURES_DIR: str = os.path.join(OUTPUT_DIR, "figures")

# ==================== S3C参数配置 ====================
# 实体类型（K）- 完整版：包含所有NuScenes对象类型
ENTITY_TYPES: List[str] = [
    'ego', 'car', 'truck', 'pedestrian', 'bicycle', 
    'motorcycle', 'bus', 'trailer', 'barrier'
]

# 距离关系（R - 距离部分）
DISTANCE_PREDICATES: Dict[str, Tuple[float, float]] = {
    'near_coll': (0, 4),      # 极近：0-4米
    'super_near': (4, 7),     # 超近：4-7米
    'very_near': (7, 10),     # 很近：7-10米
    'near': (10, 16),         # 近：10-16米
    'visible': (16, 25)       # 可见：16-25米
}

# 简化的距离级别（用于generate_selected_scenes.py）
NEAR_DISTANCE: float = float(os.getenv('NEAR_DISTANCE', '10.0'))
MID_DISTANCE: float = float(os.getenv('MID_DISTANCE', '25.0'))
MAX_REL_DISTANCE: float = float(os.getenv('MAX_REL_DISTANCE', '100.0'))  # 最大关系距离

# 方向关系（R - 方向部分）
# 4方位
DIRECTION_PREDICATES_4: Dict[str, Tuple[float, float]] = {
    'front': (-45, 45),       # 前方：-45°到+45°
    'left': (45, 135),        # 左侧：45°到135°
    'back': (135, 180),       # 后方：135°到180°（包括-180到-135）
    'right': (-135, -45)      # 右侧：-135°到-45°
}

# 论文口径：6方位（NuScenes-QA Eq.(2)），全局用下划线标签
DIRECTION_PREDICATES_6: Dict[str, Tuple[float, float]] = {
    'front': (-30.0, 30.0),            # -30° < θ <= 30°
    'front_left': (30.0, 90.0),        # 30° < θ <= 90°
    'front_right': (-90.0, -30.0),     # -90° < θ <= -30°
    'back_left': (90.0, 150.0),        # 90° < θ <= 150°
    'back_right': (-150.0, -90.0),     # -150° < θ <= -90°
    'back': (150.0, -150.0)            # else (跨越 ±180°)
}
DIRECTION_PREDICATES_8 = DIRECTION_PREDICATES_6  # backward-compatible alias

# 默认使用论文口径六方向
DIRECTION_PREDICATES: Dict[str, Tuple[float, float]] = DIRECTION_PREDICATES_6

# 属性谓词（M）
ATTRIBUTE_PREDICATES: Dict[str, float] = {
    'moving': 0.5,   # 速度阈值：>0.5 m/s为移动
    'stopped': 0.5   # 速度阈值：<=0.5 m/s为停止
}

# ==================== NuScenes类别映射 ====================
# 将NuScenes的详细类别映射到S3C的简化类型
CATEGORY_MAPPING: Dict[str, Optional[str]] = {
    # 车辆类
    'vehicle.car': 'car',
    'vehicle.truck': 'truck',
    'vehicle.bus.bendy': 'bus',
    'vehicle.bus.rigid': 'bus',
    'vehicle.construction': 'truck',          # 工程车 → truck
    'vehicle.emergency.ambulance': 'car',
    'vehicle.emergency.police': 'car',
    # ⚠️ 不再将 motorcycle / trailer 压缩到其他类型，保留为独立类型，方便与官方QA对齐
    'vehicle.motorcycle': 'motorcycle',       # 摩托车 → motorcycle
    'vehicle.trailer': 'trailer',             # 拖车 → trailer
    
    # 行人类
    'human.pedestrian.adult': 'pedestrian',
    'human.pedestrian.child': 'pedestrian',
    'human.pedestrian.construction_worker': 'pedestrian',
    'human.pedestrian.police_officer': 'pedestrian',
    
    # 自行车类
    'vehicle.bicycle': 'bicycle',
    
    # 障碍物类（修正：保留为独立类型）
    'movable_object.barrier': 'barrier',      # 护栏 → barrier（修正）
    'movable_object.trafficcone': 'barrier',  # 交通锥 → barrier（修正）
    'movable_object.pushable_pullable': None, # 可推拉物体 → 忽略
    'movable_object.debris': None,            # 碎片 → 忽略
    'static_object.bicycle_rack': None,       # 自行车架 → 忽略
}

# ==================== 可视化配置 ====================
# 图表样式
FIGURE_DPI: int = int(os.getenv('FIGURE_DPI', '300'))
FIGURE_SIZE_SINGLE: Tuple[int, int] = (10, 6)
FIGURE_SIZE_DOUBLE: Tuple[int, int] = (14, 6)

# 颜色方案
COLORS: Dict[str, str] = {
    'primary': '#1f77b4',
    'secondary': '#ff7f0e',
    'accent': '#2ca02c',
    'warning': '#d62728',
    'neutral': '#7f7f7f'
}

# ==================== 实验参数 ====================
# 是否保存中间结果
SAVE_INTERMEDIATE: bool = os.getenv('SAVE_INTERMEDIATE', 'True').lower() == 'true'

# 是否显示进度条
SHOW_PROGRESS: bool = os.getenv('SHOW_PROGRESS', 'True').lower() == 'true'

# 随机种子（用于可重复性）
RANDOM_SEED: int = int(os.getenv('RANDOM_SEED', '42'))

# ==================== CARLA对比数据（来自S3C论文） ====================
CARLA_STATS: Dict[str, float] = {
    'total_scenes': 46006,
    'num_clusters': 15000,
    'coverage_rate': 32.6,
    'singleton_rate': 50.0,
    'max_cluster_rate': 26.0
}


# ==================== 配置验证和初始化 ====================
def validate_config() -> bool:
    """验证配置是否有效"""
    errors = []
    warnings = []
    
    # 验证NuScenes路径
    if not os.path.exists(NUSCENES_DATAROOT):
        errors.append(f"NuScenes数据路径不存在: {NUSCENES_DATAROOT}")
    
    # 验证距离阈值逻辑
    if not (0 < NEAR_DISTANCE < MID_DISTANCE < MAX_REL_DISTANCE):
        errors.append(
            f"距离阈值逻辑错误: "
            f"NEAR({NEAR_DISTANCE}) < MID({MID_DISTANCE}) < MAX({MAX_REL_DISTANCE})"
        )
    
    # 验证实体类型与类别映射一致性
    mapped_types = set(v for v in CATEGORY_MAPPING.values() if v is not None)
    missing_types = mapped_types - set(ENTITY_TYPES)
    if missing_types:
        warnings.append(
            f"CATEGORY_MAPPING中的类型 {missing_types} 不在ENTITY_TYPES中"
        )
    
    # 输出验证结果
    if errors:
        logger.error("配置验证失败：")
        for error in errors:
            logger.error(f"  - {error}")
        return False
    
    if warnings:
        logger.warning("配置警告：")
        for warning in warnings:
            logger.warning(f"  - {warning}")
    
    return True


def ensure_output_dirs():
    """确保输出目录存在"""
    dirs_to_create = [
        OUTPUT_DIR, SCENE_GRAPHS_DIR, CLUSTERS_DIR, 
        STATISTICS_DIR, FIGURES_DIR
    ]
    
    for dir_path in dirs_to_create:
        try:
            os.makedirs(dir_path, exist_ok=True)
        except Exception as e:
            logger.error(f"创建目录失败 {dir_path}: {e}")
            raise


def print_config_summary():
    """打印配置摘要"""
    print(f"✓ 配置加载完成")
    print(f"  - NuScenes版本: {NUSCENES_VERSION}")
    print(f"  - 数据路径: {NUSCENES_DATAROOT}")
    print(f"  - 输出目录: {OUTPUT_DIR}")
    print(f"  - 实体类型数: {len(ENTITY_TYPES)}")
    print(f"  - 距离阈值: Near={NEAR_DISTANCE}m, Mid={MID_DISTANCE}m, Max={MAX_REL_DISTANCE}m")
    print(f"  - 方向精度: {len(DIRECTION_PREDICATES)}方位")


# 自动执行初始化
try:
    ensure_output_dirs()
    if validate_config():
        print_config_summary()
    else:
        logger.warning("配置验证未通过，但继续加载")
except Exception as e:
    logger.error(f"配置初始化失败: {e}")
    # 不阻断加载，仅记录错误
