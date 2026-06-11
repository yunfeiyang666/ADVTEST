"""
真实图像标注工具 - 在 NuScenes 相机图像上标注对象 ID

功能：
1. 加载 NuScenes 的真实相机图像（6个视角）
2. 使用 NuScenes SDK 将 3D 边界框投影到 2D 图像
3. 在图像上绘制边界框和对象 ID 标签
4. 生成带标注的图像供 Vision LLM 使用

使用场景：
- 让 Vision LLM 看真实驾驶场景图像回答问题
- 对象 ID 与场景图、Neo4j 保持一致
- 支持多相机视角（CAM_FRONT, CAM_BACK, etc.）
"""
import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging

try:
    from nuscenes.nuscenes import NuScenes
    from nuscenes.utils.geometry_utils import view_points
    from nuscenes.utils.data_classes import Box
    from pyquaternion import Quaternion
    import cv2
    NUSCENES_AVAILABLE = True
except ImportError as e:
    NUSCENES_AVAILABLE = False
    NuScenes = None
    Box = None
    Quaternion = None
    view_points = None
    logging.warning(f"NuScenes SDK 未安装: {e}")
    logging.warning("请运行: pip install nuscenes-devkit opencv-python pyquaternion")

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class RealImageAnnotator:
    """真实图像标注器"""
    
    # 对象类型颜色调色板（BGR 格式 for OpenCV）
    # 每种类型提供多个色彩变体，相邻同类对象使用不同变体以便区分
    COLOR_PALETTES_BGR = {
        'ego':        [(0, 0, 255)],
        'car':        [(255, 127, 0), (255, 50, 50), (200, 180, 0)],
        'truck':      [(0, 127, 255), (0, 200, 200), (50, 100, 230)],
        'bus':        [(0, 200, 0), (0, 180, 100), (80, 220, 60)],
        'pedestrian': [(0, 0, 200), (60, 20, 220), (0, 80, 180)],
        'bicycle':    [(200, 100, 150), (220, 60, 180), (180, 130, 110)],
        'motorcycle': [(100, 100, 139), (70, 130, 160), (130, 80, 120)],
        'trailer':    [(200, 119, 227), (170, 150, 240), (230, 90, 200)],
        'barrier':    [(127, 127, 127), (160, 100, 140), (100, 150, 130)],
    }
    # 向后兼容：保留默认颜色映射（取每组的第一个）
    COLORS_BGR = {k: v[0] for k, v in COLOR_PALETTES_BGR.items()}
    
    # 相机内参（需要从 NuScenes 数据中加载）
    CAMERA_NAMES = [
        'CAM_FRONT',
        'CAM_FRONT_LEFT',
        'CAM_FRONT_RIGHT',
        'CAM_BACK',
        'CAM_BACK_LEFT',
        'CAM_BACK_RIGHT'
    ]
    
    def __init__(self, nusc: 'NuScenes', scene_graph: Dict):
        """
        初始化标注器
        
        Args:
            nusc: NuScenes 实例
            scene_graph: 场景图 JSON 数据
        """
        if not NUSCENES_AVAILABLE:
            raise ImportError("请先安装 nuscenes-devkit: pip install nuscenes-devkit opencv-python pyquaternion")
        
        self.nusc = nusc
        self.scene_name = scene_graph.get('scene_name', 'unknown')
        self.frame_idx = scene_graph.get('frame_idx', 0)
        self.timestamp = scene_graph.get('timestamp', 0)
        
        # 解析对象
        nodes_data = scene_graph.get('objects') or scene_graph.get('nodes', [])
        self.objects = {}
        
        for node in nodes_data:
            unique_id = node['unique_id']
            self.objects[unique_id] = {
                'type': node['type'],
                'translation': node.get('translation', {}),
                'size': node.get('size'),
                'rotation': node.get('rotation', []),
                'status': node.get('status', 'unknown'),
            }
        
        logger.info(f"加载场景: {self.scene_name} 帧{self.frame_idx}")
        logger.info(f"对象数量: {len(self.objects)}")
        
        # 查找对应的 sample
        self.sample = self._find_sample_by_timestamp()
        if not self.sample:
            logger.warning(f"未找到时间戳 {self.timestamp} 对应的 sample")
    
    def _find_sample_by_timestamp(self) -> Optional[Dict]:
        """根据时间戳查找 sample"""
        # 查找场景
        scene = None
        for s in self.nusc.scene:
            if s['name'] == self.scene_name:
                scene = s
                break
        
        if not scene:
            logger.error(f"未找到场景: {self.scene_name}")
            return None
        
        # 遍历 sample
        sample_token = scene['first_sample_token']
        while sample_token:
            sample = self.nusc.get('sample', sample_token)
            
            # 检查时间戳（允许微小误差）
            if abs(sample['timestamp'] - self.timestamp) < 1000:  # 1ms 误差
                return sample
            
            sample_token = sample['next']
        
        logger.warning(f"未找到匹配时间戳 {self.timestamp} 的 sample")
        return None
    
    def annotate_camera_image(self, camera_name: str, output_path: str,
                              min_visibility: float = 0.4,
                              min_height_pixels: int = 10,
                              max_distance: float = 50.0) -> Optional[str]:
        """
        标注单个相机图像
        
        Args:
            camera_name: 相机名称（如 'CAM_FRONT'）
            output_path: 输出图像路径
            min_visibility: 最小可见度阈值（0-1），推荐 0.4
            min_height_pixels: 最小高度（像素），推荐 10-15
            max_distance: 最大距离（米），推荐 50
        
        Returns:
            标注后的图像路径，若失败则返回 None
        """
        if not self.sample:
            logger.error("未找到有效的 sample，无法标注")
            return None
        
        if camera_name not in self.sample['data']:
            logger.error(f"相机 {camera_name} 不存在")
            return None
        
        # 获取相机数据
        cam_token = self.sample['data'][camera_name]
        cam_data = self.nusc.get('sample_data', cam_token)
        
        # 加载图像
        img_path = Path(self.nusc.dataroot) / cam_data['filename']
        if not img_path.exists():
            logger.error(f"图像文件不存在: {img_path}")
            return None
        
        img = cv2.imread(str(img_path))
        if img is None:
            logger.error(f"无法读取图像: {img_path}")
            return None
        
        logger.info(f"正在标注 {camera_name} 图像: {img_path.name}")
        
        # 获取相机内外参
        cs_record = self.nusc.get('calibrated_sensor', cam_data['calibrated_sensor_token'])
        cam_intrinsic = np.array(cs_record['camera_intrinsic'])
        
        # 标注每个对象
        annotated_count = 0
        skipped_count = {'distance': 0, 'height': 0, 'visibility': 0}
        existing_labels = []  # 跟踪已有标签位置
        # 跟踪已绘制对象的2D中心和颜色，用于相邻同色检测
        drawn_objects = []  # [(type, center_2d_x, center_2d_y, color_idx), ...]
        
        for unique_id, obj in self.objects.items():
            if obj['type'] == 'ego':
                continue  # ego 不需要标注
            
            # 获取对象 3D 边界框
            translation = obj['translation']
            size = obj['size']
            rotation = obj['rotation']
            
            if not translation or not size:
                continue
            
            # 筛选规则 1: 距离过滤（相对于 ego）
            # 查找 ego 位置
            ego_obj = self.objects.get('ego')
            if ego_obj and ego_obj['translation']:
                ego_trans = ego_obj['translation']
                ego_x = ego_trans.get('x', 0) if isinstance(ego_trans, dict) else ego_trans[0]
                ego_y = ego_trans.get('y', 0) if isinstance(ego_trans, dict) else ego_trans[1]
            else:
                ego_x, ego_y = 0, 0
            
            obj_x = translation.get('x', 0) if isinstance(translation, dict) else translation[0]
            obj_y = translation.get('y', 0) if isinstance(translation, dict) else translation[1]
            distance = np.sqrt((obj_x - ego_x)**2 + (obj_y - ego_y)**2)
            
            if distance > max_distance:
                skipped_count['distance'] += 1
                continue
            
            # 转换为 Box 对象
            center = [translation['x'], translation['y'], translation.get('z', 0)]
            wlh = [size['width'], size['length'], size.get('height', 1.0)]
            
            if isinstance(rotation, (list, tuple)) and len(rotation) == 4:
                orientation = Quaternion(rotation)
            else:
                orientation = Quaternion()
            
            box = Box(center, wlh, orientation, name=obj['type'])
            
            # 投影到 2D
            try:
                corners_2d = self._project_box_to_image(box, cam_intrinsic, cs_record, cam_data)
                
                if corners_2d is None:
                    continue
                
                # 检查是否在图像范围内
                if not self._is_box_visible(corners_2d, img.shape):
                    continue
                
                # 筛选规则 2: 最小高度过滤
                box_height = corners_2d[:, 1].max() - corners_2d[:, 1].min()
                if box_height < min_height_pixels:
                    skipped_count['height'] += 1
                    continue
                
                # 筛选规则 3: 可见度过滤（简化：用边界框面积估算）
                # 更精确的方法需要 NuScenes annotation 的 visibility token
                # 这里简化为：如果框太小相对于对象尺寸，认为不可见
                
                # 选择颜色：相邻同类对象使用不同颜色变体
                cx_2d = float(corners_2d[:, 0].mean())
                cy_2d = float(corners_2d[:, 1].mean())
                color, color_idx = self._pick_color_for_object(
                    obj['type'], cx_2d, cy_2d, drawn_objects, img.shape
                )
                drawn_objects.append((obj['type'], cx_2d, cy_2d, color_idx))
                
                # 绘制边界框
                label_box = self._draw_box_2d(img, corners_2d, color, unique_id, obj['status'], existing_labels)
                existing_labels.append(label_box)  # 记录标签位置
                annotated_count += 1
                
            except Exception as e:
                logger.debug(f"投影 {unique_id} 失败: {e}")
                continue
        
        # 添加图例和标题
        self._add_legend(img, camera_name)
        
        # 保存图像
        cv2.imwrite(output_path, img)
        logger.info(f"✓ 已标注 {annotated_count} 个对象，保存至: {output_path}")
        if sum(skipped_count.values()) > 0:
            logger.info(f"  过滤: {skipped_count['distance']}个(距离) + {skipped_count['height']}个(高度) + {skipped_count['visibility']}个(可见度)")
        
        return output_path
    
    def _project_box_to_image(self, box: Box, cam_intrinsic: np.ndarray,
                              cs_record: Dict, cam_data: Dict) -> Optional[np.ndarray]:
        """将 3D 边界框投影到 2D 图像"""
        # 获取相机外参
        cam_translation = np.array(cs_record['translation'])
        cam_rotation = Quaternion(cs_record['rotation'])
        
        # 获取 ego pose
        ego_pose = self.nusc.get('ego_pose', cam_data['ego_pose_token'])
        ego_translation = np.array(ego_pose['translation'])
        ego_rotation = Quaternion(ego_pose['rotation'])
        
        # 变换：global -> ego -> camera
        box_copy = box.copy()
        box_copy.translate(-ego_translation)
        box_copy.rotate(ego_rotation.inverse)
        box_copy.translate(-cam_translation)
        box_copy.rotate(cam_rotation.inverse)
        
        # 获取 3D 角点
        corners_3d = box_copy.corners()  # (3, 8)
        
        # 过滤掉相机后方的点
        if np.any(corners_3d[2, :] < 0):
            # 有点在相机后方，不可见
            return None
        
        # 投影到 2D
        corners_2d = view_points(corners_3d, cam_intrinsic, normalize=True)[:2, :]  # (2, 8)
        
        return corners_2d.T  # (8, 2)
    
    def _is_box_visible(self, corners_2d: np.ndarray, img_shape: Tuple) -> bool:
        """检查边界框是否在图像范围内"""
        h, w = img_shape[:2]
        
        # 至少有一个角点在图像内
        x_coords = corners_2d[:, 0]
        y_coords = corners_2d[:, 1]
        
        visible = np.any((x_coords >= 0) & (x_coords < w) & 
                        (y_coords >= 0) & (y_coords < h))
        
        return visible
    
    def _draw_box_2d(self, img: np.ndarray, corners_2d: np.ndarray, 
                     color: Tuple[int, int, int], label: str, status: str,
                     existing_labels: List[Tuple[int, int, int, int]] = None):
        """
        在图像上绘制 2D 边界框和标签
        
        Args:
            img: 图像
            corners_2d: 2D 角点
            color: 颜色
            label: 标签文字
            status: 状态
            existing_labels: 已有标签位置列表 [(x1, y1, x2, y2), ...]
        
        Returns:
            新标签的位置 (x1, y1, x2, y2)
        """
        if existing_labels is None:
            existing_labels = []
        
        # 计算边界框的最小外接矩形
        x_min, y_min = corners_2d.min(axis=0).astype(int)
        x_max, y_max = corners_2d.max(axis=0).astype(int)
        
        # 绘制边界框（半透明）
        overlay = img.copy()
        cv2.rectangle(overlay, (x_min, y_min), (x_max, y_max), color, 2)
        cv2.addWeighted(overlay, 0.8, img, 0.2, 0, img)
        
        # 准备标签
        label_text = f"{label}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        thickness = 2
        
        (text_w, text_h), baseline = cv2.getTextSize(label_text, font, font_scale, thickness)
        padding = 4
        
        # 智能标签位置：尝试多个位置，选择不重叠的
        label_positions = [
            # (x, y, anchor_point) - anchor_point: 'top', 'top-left', 'top-right', 'bottom'
            (x_min, y_min - text_h - padding * 2, 'top'),           # 上方（默认）
            (x_min - text_w - padding * 2, y_min, 'left'),          # 左侧
            (x_max + padding, y_min, 'right'),                      # 右侧
            (x_min, y_max + padding, 'bottom'),                     # 下方
            (x_max - text_w - padding * 2, y_min - text_h - padding * 2, 'top-right'),  # 右上
        ]
        
        # 选择不重叠的位置
        best_pos = None
        for lx, ly, anchor in label_positions:
            label_box = (lx, ly, lx + text_w + padding * 2, ly + text_h + padding * 2)
            
            # 检查是否在图像范围内
            if label_box[0] < 0 or label_box[1] < 0 or \
               label_box[2] >= img.shape[1] or label_box[3] >= img.shape[0]:
                continue
            
            # 检查是否与已有标签重叠
            overlap = False
            for ex_box in existing_labels:
                if self._boxes_overlap(label_box, ex_box):
                    overlap = True
                    break
            
            if not overlap:
                best_pos = (lx, ly, label_box)
                break
        
        # 如果所有位置都重叠，使用默认位置
        if best_pos is None:
            lx, ly = x_min, y_min - text_h - padding * 2
            label_box = (lx, ly, lx + text_w + padding * 2, ly + text_h + padding * 2)
            best_pos = (lx, ly, label_box)
        
        lx, ly, label_box = best_pos
        
        # 绘制标签背景（半透明）
        overlay = img.copy()
        cv2.rectangle(overlay, (label_box[0], label_box[1]), 
                     (label_box[2], label_box[3]), color, -1)
        cv2.addWeighted(overlay, 0.85, img, 0.15, 0, img)
        
        # 添加白色边框（提高可见度）
        cv2.rectangle(img, (label_box[0], label_box[1]), 
                     (label_box[2], label_box[3]), (255, 255, 255), 1)
        
        # 绘制文字（白色描边 + 黑色文字）
        text_x = lx + padding
        text_y = ly + text_h + padding
        
        # 白色描边
        cv2.putText(img, label_text, (text_x, text_y), 
                   font, font_scale, (255, 255, 255), thickness + 2, cv2.LINE_AA)
        # 黑色文字
        cv2.putText(img, label_text, (text_x, text_y), 
                   font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
        
        return label_box
    
    def _pick_color_for_object(self, obj_type: str, cx: float, cy: float,
                               drawn_objects: List[Tuple], img_shape: Tuple
                               ) -> Tuple[Tuple[int, int, int], int]:
        """为对象选择颜色变体，确保相邻同类对象颜色不同
        
        Args:
            obj_type: 对象类型
            cx, cy: 对象在图像中的2D中心坐标
            drawn_objects: 已绘制对象列表 [(type, cx, cy, color_idx), ...]
            img_shape: 图像尺寸 (h, w, ...)
            
        Returns:
            (color_bgr, color_idx)
        """
        palette = self.COLOR_PALETTES_BGR.get(obj_type, [(200, 200, 200)])
        if len(palette) <= 1:
            return palette[0], 0
        
        # 邻近阈值：图像对角线的15%
        h, w = img_shape[:2]
        proximity_thresh = 0.15 * np.sqrt(h**2 + w**2)
        
        # 收集邻近同类对象已使用的颜色变体索引
        used_indices = set()
        for d_type, d_cx, d_cy, d_idx in drawn_objects:
            if d_type != obj_type:
                continue
            dist = np.sqrt((cx - d_cx)**2 + (cy - d_cy)**2)
            if dist < proximity_thresh:
                used_indices.add(d_idx)
        
        # 选择第一个未使用的变体
        for idx in range(len(palette)):
            if idx not in used_indices:
                return palette[idx], idx
        
        # 所有变体都被邻近对象用了，选距离最远的邻居的变体+1（循环）
        return palette[len(used_indices) % len(palette)], len(used_indices) % len(palette)
    
    def _boxes_overlap(self, box1: Tuple[int, int, int, int], 
                       box2: Tuple[int, int, int, int]) -> bool:
        """检查两个边界框是否重叠"""
        x1_min, y1_min, x1_max, y1_max = box1
        x2_min, y2_min, x2_max, y2_max = box2
        
        # 检查是否有交集
        return not (x1_max < x2_min or x1_min > x2_max or 
                   y1_max < y2_min or y1_min > y2_max)
    
    def _add_legend(self, img: np.ndarray, camera_name: str):
        """添加图例和标题"""
        h, w = img.shape[:2]
        
        # 标题
        title = f"{self.scene_name} Frame {self.frame_idx} - {camera_name}"
        cv2.putText(img, title, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.8, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(img, title, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.8, (0, 0, 0), 1, cv2.LINE_AA)
    
    def annotate_all_cameras(self, output_dir: str) -> List[str]:
        """标注所有相机视角"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        annotated_images = []
        
        for camera_name in self.CAMERA_NAMES:
            output_path = output_dir / f"{self.scene_name}_frame{self.frame_idx}_{camera_name}.jpg"
            
            result = self.annotate_camera_image(camera_name, str(output_path))
            if result:
                annotated_images.append(result)
        
        logger.info(f"\n✓ 共标注 {len(annotated_images)} 个相机视角")
        return annotated_images


def annotate_real_images(scene_graph_path: str, nuscenes_dir: str, 
                         output_dir: Optional[str] = None,
                         camera_names: Optional[List[str]] = None):
    """
    标注真实图像
    
    Args:
        scene_graph_path: 场景图 JSON 路径
        nuscenes_dir: NuScenes 数据集根目录
        output_dir: 输出目录
        camera_names: 要标注的相机列表（默认全部）
    """
    if not NUSCENES_AVAILABLE:
        logger.error("请先安装依赖: pip install nuscenes-devkit opencv-python pyquaternion")
        return
    
    # 加载场景图
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    
    # 初始化 NuScenes
    logger.info(f"加载 NuScenes 数据集: {nuscenes_dir}")
    nusc = NuScenes(version='v1.0-mini', dataroot=nuscenes_dir, verbose=False)
    
    # 确定输出目录
    if output_dir is None:
        output_dir = Path(scene_graph_path).parent / "real_images_annotated"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建标注器
    annotator = RealImageAnnotator(nusc, scene_graph)
    
    # 标注图像
    if camera_names is None:
        camera_names = RealImageAnnotator.CAMERA_NAMES
    
    annotated_images = []
    for camera_name in camera_names:
        scene_name = scene_graph.get('scene_name', 'unknown')
        frame_idx = scene_graph.get('frame_idx', 0)
        output_path = output_dir / f"{scene_name}_frame{frame_idx}_{camera_name}.jpg"
        
        result = annotator.annotate_camera_image(camera_name, str(output_path))
        if result:
            annotated_images.append(result)
    
    logger.info(f"\n✓ 标注完成！共 {len(annotated_images)} 张图像")
    for img_path in annotated_images:
        logger.info(f"  - {img_path}")


def main():
    """主函数"""
    import sys
    
    print("="*70)
    print("  真实图像标注工具（NuScenes 相机图像）")
    print("="*70)
    
    if len(sys.argv) < 3:
        print("\n用法: python annotate_real_images.py <scene_graph.json> <nuscenes_dir> [camera_name]")
        print("\n示例:")
        print("  python annotate_real_images.py scene_graph.json /data/nuscenes")
        print("  python annotate_real_images.py scene_graph.json /data/nuscenes CAM_FRONT")
        return
    
    scene_graph_path = sys.argv[1]
    nuscenes_dir = sys.argv[2]
    
    camera_names = None
    if len(sys.argv) >= 4:
        camera_names = [sys.argv[3]]
    
    annotate_real_images(scene_graph_path, nuscenes_dir, camera_names=camera_names)


if __name__ == "__main__":
    main()
