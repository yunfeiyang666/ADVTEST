"""
为选定的场景生成场景图（改进版）

改进内容：
1. 更好的错误处理和日志
2. 代码模块化和复用
3. 性能优化（关系过滤）
4. 配置管理改进
5. 数据验证
6. 可测试性
"""
import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
import numpy as np

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# === 配置类 ===
@dataclass
class SceneGraphConfig:
    """场景图生成配置"""
    # 距离阈值
    near_distance: float = 10.0
    mid_distance: float = 25.0
    max_relationship_distance: float = 100.0  # 只生成此距离内的关系
    
    # NuScenes 版本：须与 config.NUSCENES_VERSION / 环境变量 NUSCENES_VERSION 一致（勿默认 mini）
    nuscenes_version: str = 'v1.0-trainval'
    nuscenes_dataroot: str = None  # 从config加载
    
    # 输出配置
    output_dir: str = None  # 从config加载
    save_full_precision: bool = False  # 是否保存完整精度
    
    # devkit路径
    devkit_path: str = None
    
    @classmethod
    def from_config(cls, config_module) -> 'SceneGraphConfig':
        """从配置模块加载"""
        devkit_path = getattr(config_module, 'NUSCENES_DEVKIT_PATH', 
                             r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk")
        
        return cls(
            nuscenes_dataroot=config_module.NUSCENES_DATAROOT,
            nuscenes_version=str(
                getattr(config_module, "NUSCENES_VERSION", None)
                or os.getenv("NUSCENES_VERSION", "v1.0-trainval")
            ),
            output_dir=config_module.OUTPUT_DIR,
            devkit_path=devkit_path,
            near_distance=getattr(config_module, 'NEAR_DISTANCE', 10.0),
            mid_distance=getattr(config_module, 'MID_DISTANCE', 25.0),
            max_relationship_distance=getattr(config_module, 'MAX_REL_DISTANCE', 100.0)
        )


# === 初始化路径和导入 ===
def setup_environment(devkit_path: str):
    """设置环境路径"""
    # 添加devkit路径
    if devkit_path and devkit_path not in sys.path:
        sys.path.insert(0, devkit_path)
        logger.info(f"添加devkit路径: {devkit_path}")
    
    # 添加当前目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)


def _ensure_vqa_pipeline_on_path() -> None:
    """将包含 vqa_pipeline 包的目录加入 sys.path（兼容仅同步 official_pipeline 的 DATA_new 布局）。"""
    here = Path(__file__).resolve().parent
    for root in (here.parent, here.parent.parent):
        if (root / "vqa_pipeline").is_dir():
            s = str(root)
            if s not in sys.path:
                sys.path.insert(0, s)
            return
    override = os.environ.get("ADVTEST_VQA_PIPELINE_ROOT", "").strip()
    if override:
        p = Path(override).expanduser().resolve()
        if (p / "vqa_pipeline").is_dir():
            s = str(p)
            if s not in sys.path:
                sys.path.insert(0, s)


_ensure_vqa_pipeline_on_path()

# 延迟导入（在setup_environment后）
from nuscenes.nuscenes import NuScenes
from pyquaternion import Quaternion
import config as core_config
from vqa_pipeline.status_inference import StatusInferenceEngine
from vqa_pipeline.direction_utils import (
    quaternion_to_yaw,
    compute_direction_features_full,
)


# === 工具函数 ===
def simplify_category(category: str, mapping: Dict[str, str]) -> Optional[str]:
    """简化对象类别"""
    return mapping.get(category, None)


def get_distance_predicate(distance: float, config: SceneGraphConfig) -> str:
    """根据距离判断距离级别"""
    if distance <= config.near_distance:
        return 'near'
    elif distance <= config.mid_distance:
        return 'mid'
    else:
        return 'far'


def safe_get_attribute_names(nusc: NuScenes, attribute_tokens: List[str]) -> List[str]:
    """安全地获取attribute名称列表"""
    attributes = []
    for token in attribute_tokens:
        try:
            attr = nusc.get('attribute', token)
            attributes.append(attr['name'])
        except KeyError:
            logger.warning(f"无法找到attribute: {token}")
        except Exception as e:
            logger.error(f"获取attribute失败: {e}")
    return attributes


def safe_get_velocity(nusc: NuScenes, ann_token: str) -> List[float]:
    """安全地获取对象速度"""
    try:
        velocity = nusc.box_velocity(ann_token)
        if velocity is None or np.any(np.isnan(velocity)):
            return [0.0, 0.0, 0.0]
        return list(velocity)
    except KeyError:
        logger.warning(f"无法获取速度: {ann_token}")
        return [0.0, 0.0, 0.0]
    except Exception as e:
        logger.error(f"获取速度失败: {e}")
        return [0.0, 0.0, 0.0]


# === 数据类 ===
@dataclass
class SceneObject:
    """场景对象"""
    unique_id: str
    obj_type: str
    translation: List[float]
    rotation: List[float]
    is_ego: bool
    category: Optional[str] = None
    size: Optional[List[float]] = None
    velocity: Optional[List[float]] = None
    num_lidar_pts: int = 0
    attributes: List[str] = None
    status: str = 'unknown'
    token: Optional[str] = None
    
    def __post_init__(self):
        if self.attributes is None:
            self.attributes = []


@dataclass
class SceneRelationship:
    """场景关系"""
    source: str
    source_type: str
    target: str
    target_type: str
    predicates: List[str]
    direction_4: str
    direction_8: str
    distance: float
    angle: float
    angle_ego: float
    angle_source: float
    direction_8_source: str
    angle_matches_ego: List[str]
    angle_matches_source: List[str]
    relative_position: Dict[str, float]


# === 场景图生成器 ===
class SceneGraphGenerator:
    """场景图生成器"""
    
    def __init__(self, nusc: NuScenes, config: SceneGraphConfig):
        self.nusc = nusc
        self.config = config
        self.status_engine = StatusInferenceEngine()
        self.category_mapping = getattr(core_config, 'CATEGORY_MAPPING', {})
    
    def find_scene(self, scene_name: str) -> Optional[Dict]:
        """查找场景"""
        for scene in self.nusc.scene:
            if scene['name'] == scene_name:
                return scene
        return None
    
    def get_sample_at_frame(self, scene: Dict, frame_idx: int) -> Optional[Dict]:
        """获取指定帧的sample"""
        sample_token = scene['first_sample_token']
        current_frame = 0
        
        while sample_token and current_frame < frame_idx:
            sample = self.nusc.get('sample', sample_token)
            sample_token = sample['next']
            current_frame += 1
        
        if not sample_token:
            logger.error(f"帧索引超出范围: {frame_idx}")
            return None
        
        return self.nusc.get('sample', sample_token)
    
    def extract_ego_object(self, ego_pose: Dict) -> SceneObject:
        """提取Ego车对象"""
        return SceneObject(
            unique_id='ego',
            obj_type='ego',
            translation=ego_pose['translation'],
            rotation=ego_pose['rotation'],
            is_ego=True
        )
    
    def extract_annotation_object(
        self, 
        ann: Dict, 
        type_counters: Dict[str, int]
    ) -> Optional[SceneObject]:
        """提取标注对象"""
        # 简化类别
        obj_type = simplify_category(ann['category_name'], self.category_mapping)
        if obj_type is None:
            return None
        
        # 生成唯一ID
        type_counters[obj_type] += 1
        unique_id = f"{obj_type}{type_counters[obj_type]}"
        
        # 获取attributes
        attribute_tokens = ann.get('attribute_tokens', [])
        attributes = safe_get_attribute_names(self.nusc, attribute_tokens)
        
        # 获取速度
        velocity = safe_get_velocity(self.nusc, ann['token'])
        
        # 推断状态
        inferred_status = self.status_engine.infer_status({
            'type': obj_type,
            'attributes': attributes,
            'velocity': velocity
        })
        
        return SceneObject(
            unique_id=unique_id,
            obj_type=obj_type,
            category=ann['category_name'],
            translation=ann['translation'],
            rotation=ann['rotation'],
            size=ann['size'],
            velocity=velocity,
            num_lidar_pts=ann.get('num_lidar_pts', 0),
            attributes=attributes,
            status=self.status_engine.format_for_neo4j(inferred_status),
            token=ann['token'],
            is_ego=False
        )
    
    def compute_relationship(
        self,
        obj1: SceneObject,
        obj2: SceneObject,
        ego_rotation: List[float]
    ) -> Optional[SceneRelationship]:
        """计算两个对象之间的关系"""
        features = compute_direction_features_full(
            obj1.translation,
            obj2.translation,
            obj1.rotation,
            ego_rotation
        )
        distance = features["distance"]
        
        # 距离过滤
        if distance > self.config.max_relationship_distance:
            return None
        
        distance_level = get_distance_predicate(distance, self.config)
        rel_pos = features["relative_position"]
        
        return SceneRelationship(
            source=obj1.unique_id,
            source_type=obj1.obj_type,
            target=obj2.unique_id,
            target_type=obj2.obj_type,
            predicates=[features["direction_8_ego"], distance_level],
            direction_4=features["direction_4_ego"],
            direction_8=features["direction_8_ego"],
            distance=round(distance, 2),
            angle=round(float(features["angle_ego"]), 1),
            angle_ego=round(float(features["angle_ego"]), 1),
            angle_source=round(float(features["angle_source"]), 1),
            direction_8_source=features["direction_8_source"],
            angle_matches_ego=features["angle_matches_ego"],
            angle_matches_source=features["angle_matches_source"],
            relative_position={
                'x': round(float(rel_pos[0]), 2),
                'y': round(float(rel_pos[1]), 2),
                'z': round(float(rel_pos[2]), 2)
            }
        )
    
    def generate_relationships(
        self,
        objects: List[SceneObject],
        ego_rotation: List[float]
    ) -> List[SceneRelationship]:
        """生成所有对象关系"""
        relationships = []
        total_pairs = len(objects) * (len(objects) - 1)
        
        logger.info(f"生成关系（最多 {total_pairs} 对）...")
        
        for i, obj1 in enumerate(objects):
            for j, obj2 in enumerate(objects):
                if i == j:
                    continue
                
                rel = self.compute_relationship(obj1, obj2, ego_rotation)
                if rel:
                    relationships.append(rel)
        
        logger.info(f"✓ 生成了 {len(relationships)} 条关系（过滤后）")
        return relationships
    
    def format_node_for_output(self, obj: SceneObject) -> Dict:
        """格式化节点输出"""
        node = {
            'unique_id': obj.unique_id,
            'type': obj.obj_type,
            'category': obj.category or obj.obj_type,
            'translation': {
                'x': round(float(obj.translation[0]), 2),
                'y': round(float(obj.translation[1]), 2),
                'z': round(float(obj.translation[2]), 2)
            },
            'rotation': [round(float(r), 4) for r in obj.rotation],
            'status': obj.status,
            'attributes': obj.attributes
        }
        
        # 添加可选字段
        if not obj.is_ego:
            if obj.size:
                node['size'] = {
                    'width': round(float(obj.size[0]), 2),
                    'length': round(float(obj.size[1]), 2),
                    'height': round(float(obj.size[2]), 2)
                }
            
            if obj.velocity:
                node['velocity'] = {
                    'vx': round(float(obj.velocity[0]), 2),
                    'vy': round(float(obj.velocity[1]), 2),
                    'vz': round(float(obj.velocity[2]), 2)
                }
            
            node['num_lidar_pts'] = obj.num_lidar_pts
        else:
            node['size'] = None
            node['velocity'] = None
            node['num_lidar_pts'] = 0
        
        return node
    
    def format_edge_for_output(self, rel: SceneRelationship) -> Dict:
        """格式化关系输出"""
        return {
            'source': rel.source,
            'source_type': rel.source_type,
            'target': rel.target,
            'target_type': rel.target_type,
            'predicates': rel.predicates,
            'direction_4': rel.direction_4,
            'direction_8': rel.direction_8,
            'metrics': {
                'distance': rel.distance,
                'angle': rel.angle,
                'angle_ego': rel.angle_ego,
                'angle_source': rel.angle_source,
                'direction_ego': {
                    'direction_8': rel.direction_8,
                    'angle_matches': rel.angle_matches_ego
                },
                'direction_source': {
                    'direction_8': rel.direction_8_source,
                    'angle_matches': rel.angle_matches_source
                },
                'relative_position': rel.relative_position,
                'relative_position_ego': rel.relative_position,
                'relative_position_source': rel.relative_position
            }
        }
    
    def generate(self, scene_name: str, frame_idx: int) -> Optional[Dict]:
        """生成场景图"""
        logger.info(f"开始生成场景图: {scene_name} 帧{frame_idx}")
        
        # 1. 查找场景
        scene = self.find_scene(scene_name)
        if not scene:
            logger.error(f"未找到场景: {scene_name}")
            return None
        
        # 2. 获取sample
        sample = self.get_sample_at_frame(scene, frame_idx)
        if not sample:
            return None
        
        # 3. 获取Ego车姿态
        lidar_token = sample['data']['LIDAR_TOP']
        lidar_data = self.nusc.get('sample_data', lidar_token)
        ego_pose = self.nusc.get('ego_pose', lidar_data['ego_pose_token'])
        
        # 4. 提取对象
        objects = []
        type_counters = defaultdict(int)
        
        # 添加Ego车
        ego_obj = self.extract_ego_object(ego_pose)
        objects.append(ego_obj)
        
        # 处理标注对象
        logger.info(f"处理 {len(sample['anns'])} 个标注对象...")
        for ann_token in sample['anns']:
            ann = self.nusc.get('sample_annotation', ann_token)
            obj = self.extract_annotation_object(ann, type_counters)
            if obj:
                objects.append(obj)
        
        logger.info(f"✓ 提取了 {len(objects)} 个有效对象")
        
        # 5. 生成关系
        relationships = self.generate_relationships(objects, ego_obj.rotation)
        
        # 6. 构建场景图
        scene_graph = {
            'scene_name': scene_name,
            'frame_idx': frame_idx,
            'timestamp': sample['timestamp'],
            'description': scene['description'],
            'nodes': [self.format_node_for_output(obj) for obj in objects],
            'edges': [self.format_edge_for_output(rel) for rel in relationships],
            'statistics': {
                'total_objects': len(objects),
                'total_relationships': len(relationships),
                'object_type_count': dict(type_counters)
            }
        }
        
        logger.info("✓ 场景图生成完成")
        return scene_graph


# === 批处理管理器 ===
class SceneGraphBatchProcessor:
    """批量处理场景图生成"""
    
    def __init__(self, nusc: NuScenes, config: SceneGraphConfig):
        self.nusc = nusc
        self.config = config
        self.generator = SceneGraphGenerator(nusc, config)
    
    def load_selected_scenes(self, selection_file: Path) -> List[Dict]:
        """加载选定的场景"""
        if not selection_file.exists():
            raise FileNotFoundError(f"找不到选定场景文件: {selection_file}")
        
        with open(selection_file, 'r', encoding='utf-8') as f:
            scenes = json.load(f)
        
        logger.info(f"✓ 加载了 {len(scenes)} 个选定场景")
        return scenes
    
    def process_scene(self, scene_info: Dict, output_dir: Path) -> Optional[Dict]:
        """处理单个场景"""
        scene_name = scene_info['scene_name']
        frame_idx = scene_info['frame_idx']
        
        logger.info("=" * 70)
        logger.info(f"处理场景: {scene_name} 帧{frame_idx}")
        logger.info(f"描述: {scene_info.get('scene_description', 'N/A')}")
        logger.info("=" * 70)
        
        # 生成场景图
        scene_graph = self.generator.generate(scene_name, frame_idx)
        
        if not scene_graph:
            logger.error("❌ 场景图生成失败")
            return None
        
        # 保存场景图
        filename = f"{scene_name}_frame{frame_idx}_scene_graph.json"
        filepath = output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(scene_graph, f, indent=2, ensure_ascii=False)
        
        file_size = filepath.stat().st_size / 1024
        logger.info(f"✓ 场景图已保存: {filepath} ({file_size:.1f} KB)")
        
        # 统计信息
        stats = scene_graph['statistics']
        logger.info(f"  对象数量: {stats['total_objects']}")
        logger.info(f"  关系数量: {stats['total_relationships']}")
        
        return {
            'scene_name': scene_name,
            'frame_idx': frame_idx,
            'description': scene_info.get('scene_description', ''),
            'total_objects': stats['total_objects'],
            'total_relationships': stats['total_relationships'],
            'type_count': stats['object_type_count'],
            'filepath': str(filepath)
        }
    
    def process_all(self, selected_scenes: List[Dict], output_dir: Path) -> List[Dict]:
        """处理所有场景"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        generated = []
        for i, scene_info in enumerate(selected_scenes, 1):
            logger.info(f"\n[{i}/{len(selected_scenes)}]")
            
            result = self.process_scene(scene_info, output_dir)
            if result:
                generated.append(result)
        
        # 保存清单
        manifest_path = output_dir / "manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(generated, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n✓ 清单已保存: {manifest_path}")
        return generated


def print_summary(generated: List[Dict]):
    """打印生成摘要"""
    print("\n" + "=" * 70)
    print("  生成完成")
    print("=" * 70)
    print(f"\n✓ 共生成 {len(generated)} 个场景的场景图")
    
    print("\n【生成的场景】")
    for i, scene in enumerate(generated, 1):
        print(f"\n{i}. {scene['scene_name']} 帧{scene['frame_idx']}")
        print(f"   对象: {scene['total_objects']}, 关系: {scene['total_relationships']}")
        print(f"   描述: {scene['description']}")


def main():
    """主函数"""
    print("=" * 70)
    print("  生成选定场景的场景图（改进版）")
    print("=" * 70)
    
    try:
        # 加载配置
        import config as core_config
        cfg = SceneGraphConfig.from_config(core_config)
        
        # 设置环境
        setup_environment(cfg.devkit_path)
        
        # 加载NuScenes
        logger.info("\n加载NuScenes数据集...")
        nusc = NuScenes(
            version=cfg.nuscenes_version,
            dataroot=cfg.nuscenes_dataroot,
            verbose=False
        )
        logger.info(f"✓ 已加载 {len(nusc.scene)} 个场景")
        
        # 创建处理器
        processor = SceneGraphBatchProcessor(nusc, cfg)
        
        # 加载选定场景
        selection_file = Path(cfg.output_dir) / "coverage_analysis" / "selected_scenes.json"
        selected_scenes = processor.load_selected_scenes(selection_file)
        
        # 处理所有场景
        output_dir = Path(cfg.output_dir) / "coverage_analysis" / "scene_graphs"
        generated = processor.process_all(selected_scenes, output_dir)
        
        # 打印摘要
        print_summary(generated)
        
        print("\n下一步:")
        print("  python test_coverage_vqa_v2.py")
        
    except FileNotFoundError as e:
        logger.error(f"✗ 文件未找到: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"✗ 处理失败: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
