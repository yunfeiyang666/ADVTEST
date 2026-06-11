#!/usr/bin/env python
"""
场景图对象筛选工具
根据 nuScenes 官方标准和 nuImages 标准筛选有效对象
"""
import json
import os
import sys
from typing import Dict, List, Set, Optional
from pathlib import Path
import logging

# 添加 nuScenes devkit 路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

try:
    from nuscenes.nuscenes import NuScenes
    NUSCENES_AVAILABLE = True
except ImportError:
    NUSCENES_AVAILABLE = False
    NuScenes = None

logger = logging.getLogger(__name__)


class SceneGraphFilter:
    """场景图筛选器"""
    
    # nuScenes 官方检测范围（米）
    DETECTION_RANGES = {
        'barrier': 30,
        'traffic_cone': 30,
        'bicycle': 40,
        'motorcycle': 40,
        'pedestrian': 40,
        'car': 50,
        'bus': 50,
        'construction_vehicle': 50,
        'trailer': 50,
        'truck': 50
    }
    
    # nuImages 最小像素高度阈值
    MIN_PIXEL_HEIGHT_LENIENT = 10   # 宽松标准 (参考 nuImages 官方)
    MIN_PIXEL_HEIGHT_STRICT  = 15   # 严格标准 (如需更清晰目标)
    
    # 可见度阈值
    MIN_VISIBILITY_NUSCENES = 0.4  # nuScenes: 40%，低于此值难以确定目标
    MIN_VISIBILITY_NUIMAGES = 0.2  # nuImages: 20%，官方标注标准
    
    # 使用 nuImages 的更严格标准（同时满足两个数据集）
    MIN_VISIBILITY = MIN_VISIBILITY_NUSCENES  # 使用 nuScenes 40% 作为主标准
    
    def __init__(self, mode: str = 'filtered', nusc: Optional[NuScenes] = None, 
                 scene_token: Optional[str] = None, sample_token: Optional[str] = None):
        """
        初始化筛选器
        
        Args:
            mode: 'filtered' 或 'unfiltered'
                - filtered: 应用所有筛选条件
                - unfiltered: 不筛选，保留所有对象
            nusc: NuScenes 实例（可选），用于读取 visibility 信息
            scene_token: 场景 token（可选）
            sample_token: 样本 token（可选）
        """
        self.mode = mode
        self.nusc = nusc
        self.scene_token = scene_token
        self.sample_token = sample_token
        self._visibility_cache = {}  # 缓存 visibility 数据
    
    def filter_scene_graph(self, scene_graph: Dict) -> Dict:
        """
        筛选场景图
        
        Args:
            scene_graph: 原始场景图数据
        
        Returns:
            筛选后的场景图
        """
        if self.mode == 'unfiltered':
            logger.info("未筛选模式：保留所有对象")
            return scene_graph
        
        # 筛选模式
        logger.info("筛选模式：应用 nuScenes + nuImages 标准")
        
        original_nodes = scene_graph.get('nodes', [])
        
        # 获取ego节点坐标
        ego_node = next((n for n in original_nodes if n.get('type') == 'ego'), None)
        if ego_node:
            ego_trans = ego_node.get('translation', {})
            self.ego_x = ego_trans.get('x', 0)
            self.ego_y = ego_trans.get('y', 0)
            logger.info(f"ego节点坐标: ({self.ego_x:.2f}, {self.ego_y:.2f})")
        else:
            self.ego_x = 0
            self.ego_y = 0
            logger.warning("未ego节点，假设原点")
        
        filtered_nodes = []
        removed_count = 0
        removal_reasons = {
            'distance': 0,
            'visibility': 0,
            'pixels': 0
        }
        
        for node in original_nodes:
            # ego 节点保留
            if node.get('type') == 'ego':
                filtered_nodes.append(node)
                continue
            
            # 检查筛选条件
            keep, reason = self._should_keep_node(node)
            
            if keep:
                filtered_nodes.append(node)
            else:
                removed_count += 1
                if reason:
                    removal_reasons[reason] = removal_reasons.get(reason, 0) + 1
        
        logger.info(f"筛选结果: 保留 {len(filtered_nodes)}/{len(original_nodes)} 个节点")
        logger.info(f"移除原因: 距离={removal_reasons.get('distance', 0)}, "
                   f"可见度={removal_reasons.get('visibility', 0)}, "
                   f"像素={removal_reasons.get('pixels', 0)}")
        
        # 更新场景图
        filtered_scene = scene_graph.copy()
        filtered_scene['nodes'] = filtered_nodes
        
        # 筛选关系边（移除涉及被删除节点的边）
        valid_node_ids = {n['unique_id'] for n in filtered_nodes}
        filtered_scene['edges'] = [
            e for e in scene_graph.get('edges', [])
            if e.get('source') in valid_node_ids and e.get('target') in valid_node_ids
        ]
        
        logger.info(f"关系边: {len(filtered_scene['edges'])}/{len(scene_graph.get('edges', []))}")
        
        return filtered_scene
    
    def _should_keep_node(self, node: Dict) -> tuple:
        """
        判断节点是否应该保留
        
        Returns:
            (bool, str): (是否保留, 移除原因)
        """
        node_type = node.get('type', 'unknown')
        
        # 1. 检查 3D 距离（nuScenes 官方标准）
        if not self._check_distance(node):
            return False, 'distance'
        
        # 2. 检查可见度（nuScenes 官方标准）
        if not self._check_visibility(node):
            return False, 'visibility'
        
        # 3. 检查像素大小（nuImages 标准）
        if not self._check_pixels(node):
            return False, 'pixels'
        
        return True, None
    
    def _check_distance(self, node: Dict) -> bool:
        """检查 3D 距离是否在范围内"""
        node_type = node.get('type', 'unknown')
        max_range = self.DETECTION_RANGES.get(node_type, 50)
        
        # 计算相对于 ego 的距离
        translation = node.get('translation', {})
        x = translation.get('x', 0)
        y = translation.get('y', 0)
        
        # 使用相对坐标
        dx = x - getattr(self, 'ego_x', 0)
        dy = y - getattr(self, 'ego_y', 0)
        distance = (dx**2 + dy**2) ** 0.5
        
        return distance <= max_range
    
    def _check_visibility(self, node: Dict) -> bool:
        """
        检查可见度
        
        优先级：
        1. 场景图中的 visibility 字段
        2. 从 nuScenes API 查询（如果可用）
        3. 默认假设可见
        """
        node_id = node.get('unique_id', 'unknown')
        
        # nuScenes 可见度分级: [0, 1, 2, 3, 4]
        # 0: v <= 40%  (不可见/严重遮挡)
        # 1: 40% < v <= 60%
        # 2: 60% < v <= 80%
        # 3: 80% < v <= 100%
        
        # 尝试从场景图中读取 visibility
        if 'visibility' in node:
            visibility = node.get('visibility', 1.0)
            
            # 归一化为 [0, 1]
            if visibility > 1:
                visibility = visibility / 4.0  # nuScenes 使用 0-4 级别
            
            return visibility >= self.MIN_VISIBILITY
        
        # 尝试从 nuScenes API 查询
        if self.nusc is not None and self.sample_token:
            logger.debug(f"尝试查询 {node_id} 的 visibility")
            visibility = self._get_visibility_from_nuscenes(node)
            if visibility is not None:
                logger.debug(f"{node_id} visibility={visibility:.2f}, 阈值={self.MIN_VISIBILITY}")
                return visibility >= self.MIN_VISIBILITY
        
        # 默认假设可见（保守策略）
        logger.debug(f"{node_id} 未查询到 visibility，默认可见")
        return True
    
    def _get_visibility_from_nuscenes(self, node: Dict) -> Optional[float]:
        """
        从 nuScenes API 查询对象的可见度
        
        Returns:
            可见度 [0, 1] 或 None（如果查询失败）
        """
        node_id = node.get('unique_id', 'unknown')
        logger.debug(f"尝试从 nuScenes 查询 {node_id} 的 visibility")
        
        if not NUSCENES_AVAILABLE:
            logger.debug("nuScenes SDK 不可用")
            return None
        
        if self.nusc is None:
            logger.debug("nuScenes 实例为 None")
            return None
        
        if not self.sample_token:
            logger.debug("sample_token 未提供")
            return None
        
        try:
            # 从缓存中获取
            if node_id in self._visibility_cache:
                return self._visibility_cache[node_id]
            
            # 获取 sample 的所有标注
            sample = self.nusc.get('sample', self.sample_token)
            
            # 遍历标注，匹配当前节点
            # 匹配策略：根据位置、类别、尺寸
            node_trans = node.get('translation', {})
            node_x = node_trans.get('x', 0)
            node_y = node_trans.get('y', 0)
            node_z = node_trans.get('z', 0)
            
            # 获取节点类别（先尝试 category，再尝试 type）
            node_category = node.get('category', '')
            node_type = node.get('type', '')
            
            best_match = None
            min_distance = float('inf')
            
            matched_count = 0
            for ann_token in sample['anns']:
                ann = self.nusc.get('sample_annotation', ann_token)
                ann_category = ann['category_name']
                
                # 匹配类别：完整匹配或类型前缀匹配
                # 例如：'car' 匹配 'vehicle.car'
                category_match = False
                if node_category and ann_category == node_category:
                    category_match = True
                elif node_type:
                    # 尝试匹配简化类型（如 'car' 匹配 'vehicle.car'）
                    if ann_category.endswith('.' + node_type) or ann_category == node_type:
                        category_match = True
                    # 特殊情况：pedestrian 匹配所有 human.pedestrian.*
                    elif node_type == 'pedestrian' and 'pedestrian' in ann_category:
                        category_match = True
                
                if not category_match:
                    continue
                
                matched_count += 1
                
                # 计算位置距离
                ann_x, ann_y, ann_z = ann['translation']
                dist = ((ann_x - node_x)**2 + (ann_y - node_y)**2 + (ann_z - node_z)**2) ** 0.5
                
                if dist < min_distance and dist < 2.0:  # 容差 2米
                    min_distance = dist
                    best_match = ann
            
            logger.debug(f"节点 {node_id}: 匹配到 {matched_count} 个同类型对象，最小距离={min_distance:.2f}m")
            
            if best_match and best_match.get('visibility_token'):
                vis_token = best_match['visibility_token']
                vis_record = self.nusc.get('visibility', vis_token)
                vis_level_str = vis_record['level']  # 'v0-40', 'v40-60', etc.
                
                # 解析 visibility level
                # v0-40 -> 0, v40-60 -> 1, v60-80 -> 2, v80-100 -> 3
                vis_level_map = {
                    'v0-40': 0,
                    'v40-60': 1,
                    'v60-80': 2,
                    'v80-100': 3
                }
                vis_level = vis_level_map.get(vis_level_str, 0)
                
                # 转换为归一化值 [0, 1]
                # v0-40: 0.2, v40-60: 0.5, v60-80: 0.7, v80-100: 0.9
                visibility_map = {0: 0.2, 1: 0.5, 2: 0.7, 3: 0.9}
                visibility = visibility_map.get(vis_level, 1.0)
                
                # 缓存结果
                self._visibility_cache[node_id] = visibility
                return visibility
            
        except Exception as e:
            import traceback
            logger.warning(f"无法从 nuScenes 获取 visibility: {e}")
            logger.warning(traceback.format_exc())
        
        return None
    
    def _check_pixels(self, node: Dict) -> bool:
        """
        检查投影像素高度（nuImages 标准）
        
        使用 3D 高度 + 距离估算 2D 投影高度：
          approx_height_px ≈ (height_3d * focal_length) / distance
        
        nuScenes 典型相机焦距 ≈ 1266 px (CAM_FRONT)
        阈值：高度 >= 10 px (宽松) 或 >= 15 px (严格)
        """
        size = node.get('size')
        if not size:
            return True  # 没有尺寸信息，保留
        
        # 计算到 ego 的距离
        translation = node.get('translation', {})
        x = translation.get('x', 0)
        y = translation.get('y', 0)
        dx = x - getattr(self, 'ego_x', 0)
        dy = y - getattr(self, 'ego_y', 0)
        distance = max((dx**2 + dy**2) ** 0.5, 1.0)  # 避免除以0
        
        # 使用 3D 高度估算投影像素高度
        height_3d = size.get('height', 0)
        if height_3d <= 0:
            return True  # 没有高度信息，保留
        
        # 估算公式：pixels ≈ (height_3d * focal_length) / distance
        # nuScenes CAM_FRONT 焦距 fy ≈ 1266 pixels
        focal_length = 1266
        approx_height_px = (height_3d * focal_length) / distance
        
        return approx_height_px >= self.MIN_PIXEL_HEIGHT_LENIENT
    
    def get_filter_stats(self, original: Dict, filtered: Dict) -> Dict:
        """获取筛选统计信息"""
        orig_nodes = len(original.get('nodes', []))
        filt_nodes = len(filtered.get('nodes', []))
        orig_edges = len(original.get('edges', []))
        filt_edges = len(filtered.get('edges', []))
        
        return {
            'mode': self.mode,
            'original': {
                'nodes': orig_nodes,
                'edges': orig_edges
            },
            'filtered': {
                'nodes': filt_nodes,
                'edges': filt_edges
            },
            'removed': {
                'nodes': orig_nodes - filt_nodes,
                'edges': orig_edges - filt_edges,
                'node_ratio': (orig_nodes - filt_nodes) / max(orig_nodes, 1),
                'edge_ratio': (orig_edges - filt_edges) / max(orig_edges, 1)
            }
        }


class QAFilter:
    """
    原始 QA 错题过滤器
    
    加载经 5 层 retry 验证后确认的错题黑名单，在使用原始 NuScenesQA 时
    自动跳过这些已知有误的题目。
    
    黑名单文件: skip_questions.json
    格式: [scene_name, frame_idx, question_index_1based, reason]
    """
    
    _DEFAULT_PATH = Path(__file__).parent / "skip_questions.json"
    
    def __init__(self, blacklist_path: Optional[str] = None):
        self._skip_set: Set[tuple] = set()
        self._reasons: Dict[tuple, str] = {}
        path = Path(blacklist_path) if blacklist_path else self._DEFAULT_PATH
        self._load(path)
    
    def _load(self, path: Path):
        if not path.exists():
            logger.warning(f"错题黑名单文件不存在: {path}")
            return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for entry in data.get("skip_list", []):
            scene, frame, qidx = entry[0], entry[1], entry[2]
            reason = entry[3] if len(entry) > 3 else ""
            key = (scene, frame, qidx)
            self._skip_set.add(key)
            self._reasons[key] = reason
        logger.info(f"加载错题黑名单: {len(self._skip_set)} 条")
    
    def should_skip(self, scene_name: str, frame_idx: int, question_idx: int) -> bool:
        """检查题目是否在黑名单中 (question_idx 为 1-based)"""
        return (scene_name, frame_idx, question_idx) in self._skip_set
    
    def get_reason(self, scene_name: str, frame_idx: int, question_idx: int) -> str:
        return self._reasons.get((scene_name, frame_idx, question_idx), "")
    
    def filter_qa_list(self, qa_list: List[Dict], scene_name: str, frame_idx: int) -> List[Dict]:
        """
        过滤 QA 列表，移除黑名单中的题目
        
        Args:
            qa_list: 原始 QA 列表 (每项至少有 question 字段)
            scene_name: 场景名
            frame_idx: 帧索引
        
        Returns:
            过滤后的 QA 列表
        """
        filtered = []
        removed = 0
        for i, qa in enumerate(qa_list, 1):
            if self.should_skip(scene_name, frame_idx, i):
                removed += 1
                logger.debug(f"跳过错题 Q{i}: {self.get_reason(scene_name, frame_idx, i)}")
            else:
                filtered.append(qa)
        if removed:
            logger.info(f"[{scene_name} frame{frame_idx}] 过滤 {removed} 道错题，保留 {len(filtered)}/{len(qa_list)}")
        return filtered
    
    @property
    def skip_count(self) -> int:
        return len(self._skip_set)


def filter_scene_graph_file(input_path: str, output_path: str, mode: str = 'filtered',
                            nusc: Optional[NuScenes] = None, sample_token: Optional[str] = None):
    """
    筛选场景图文件
    
    Args:
        input_path: 输入场景图路径
        output_path: 输出场景图路径
        mode: 筛选模式
        nusc: NuScenes 实例（可选），用于查询 visibility
        sample_token: 样本 token（可选）
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    
    # 如果没有提供 sample_token，尝试从场景图中获取
    if nusc is not None and sample_token is None:
        scene_name = scene_graph.get('scene_name')
        frame_idx = scene_graph.get('frame_idx')
        if scene_name and frame_idx is not None:
            # 查找对应的 sample_token
            try:
                scene_rec = nusc.get('scene', nusc.field2token('scene', 'name', scene_name)[0])
                sample = nusc.get('sample', scene_rec['first_sample_token'])
                for _ in range(frame_idx):
                    if sample['next']:
                        sample = nusc.get('sample', sample['next'])
                sample_token = sample['token']
            except:
                logger.warning(f"无法查找 scene {scene_name} frame {frame_idx} 的 sample_token")
    
    filter_obj = SceneGraphFilter(mode=mode, nusc=nusc, sample_token=sample_token)
    filtered_graph = filter_obj.filter_scene_graph(scene_graph)
    
    # 保存筛选后的场景图
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(filtered_graph, f, indent=2, ensure_ascii=False)
    
    stats = filter_obj.get_filter_stats(scene_graph, filtered_graph)
    return stats


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python scene_filter.py <input.json> <output.json> [filtered|unfiltered]")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else 'filtered'
    
    logging.basicConfig(level=logging.INFO)
    stats = filter_scene_graph_file(input_path, output_path, mode)
    
    print(f"\n筛选完成:")
    print(f"  模式: {stats['mode']}")
    print(f"  原始: {stats['original']['nodes']} 节点, {stats['original']['edges']} 边")
    print(f"  结果: {stats['filtered']['nodes']} 节点, {stats['filtered']['edges']} 边")
    print(f"  移除: {stats['removed']['nodes']} 节点 ({stats['removed']['node_ratio']*100:.1f}%), "
          f"{stats['removed']['edges']} 边 ({stats['removed']['edge_ratio']*100:.1f}%)")
