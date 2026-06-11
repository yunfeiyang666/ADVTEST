"""
NuScenes S3C实验配置文件
"""
import os

# ==================== 路径配置 ====================
# NuScenes数据集路径
NUSCENES_DATAROOT = r"E:\Project\ADVTEST\data\nuscenes"
NUSCENES_VERSION = "v1.0-mini"  # 使用mini版本（404个场景）

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 输出目录
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
SCENE_GRAPHS_DIR = os.path.join(OUTPUT_DIR, "scene_graphs")
CLUSTERS_DIR = os.path.join(OUTPUT_DIR, "clusters")
STATISTICS_DIR = os.path.join(OUTPUT_DIR, "statistics")
FIGURES_DIR = os.path.join(OUTPUT_DIR, "figures")

# 创建输出目录
for dir_path in [OUTPUT_DIR, SCENE_GRAPHS_DIR, CLUSTERS_DIR, STATISTICS_DIR, FIGURES_DIR]:
    os.makedirs(dir_path, exist_ok=True)

# ==================== S3C参数配置 ====================
# 实体类型（K）- 完整版：包含所有NuScenes对象类型
ENTITY_TYPES = ['ego', 'car', 'truck', 'pedestrian', 'bicycle', 'motorcycle', 'bus', 'trailer', 'barrier']

# 距离关系（R - 距离部分）
DISTANCE_PREDICATES = {
    'near_coll': (0, 4),      # 极近：0-4米
    'super_near': (4, 7),     # 超近：4-7米
    'very_near': (7, 10),     # 很近：7-10米
    'near': (10, 16),         # 近：10-16米
    'visible': (16, 25)       # 可见：16-25米
}

# 方向关系（R - 方向部分）
# 4方位
DIRECTION_PREDICATES_4 = {
    'front': (-45, 45),       # 前方：-45°到+45°
    'left': (45, 135),        # 左侧：45°到135°
    'back': (135, 180),       # 后方：135°到180°（包括-180到-135）
    'right': (-135, -45)      # 右侧：-135°到-45°
}

# 8方位（更精确的方向划分）
DIRECTION_PREDICATES_8 = {
    'front': (-22.5, 22.5),           # 正前方：-22.5°到+22.5°
    'front-left': (22.5, 67.5),       # 前左：22.5°到67.5°
    'left': (67.5, 112.5),            # 左侧：67.5°到112.5°
    'back-left': (112.5, 157.5),      # 后左：112.5°到157.5°
    'back': (157.5, 180),             # 正后方：157.5°到180°（包括-180到-157.5）
    'back-right': (-157.5, -112.5),   # 后右：-157.5°到-112.5°
    'right': (-112.5, -67.5),         # 右侧：-112.5°到-67.5°
    'front-right': (-67.5, -22.5)     # 前右：-67.5°到-22.5°
}

# 默认使用8方位（与direction_utils.py保持一致）
DIRECTION_PREDICATES = DIRECTION_PREDICATES_8

# 属性谓词（M）
ATTRIBUTE_PREDICATES = {
    'moving': 0.5,   # 速度阈值：>0.5 m/s为移动
    'stopped': 0.5   # 速度阈值：<=0.5 m/s为停止
}

# ==================== NuScenes类别映射 ====================
# 将NuScenes的详细类别映射到S3C的简化类型
CATEGORY_MAPPING = {
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
FIGURE_DPI = 300
FIGURE_SIZE_SINGLE = (10, 6)
FIGURE_SIZE_DOUBLE = (14, 6)

# 颜色方案
COLORS = {
    'primary': '#1f77b4',
    'secondary': '#ff7f0e',
    'accent': '#2ca02c',
    'warning': '#d62728',
    'neutral': '#7f7f7f'
}

# ==================== 实验参数 ====================
# 是否保存中间结果
SAVE_INTERMEDIATE = True

# 是否显示进度条
SHOW_PROGRESS = True

# 随机种子（用于可重复性）
RANDOM_SEED = 42

# ==================== CARLA对比数据（来自S3C论文） ====================
CARLA_STATS = {
    'total_scenes': 46006,
    'num_clusters': 15000,
    'coverage_rate': 32.6,
    'singleton_rate': 50.0,
    'max_cluster_rate': 26.0
}

print(f"✓ 配置加载完成")
print(f"  - NuScenes数据路径: {NUSCENES_DATAROOT}")
print(f"  - 输出目录: {OUTPUT_DIR}")
