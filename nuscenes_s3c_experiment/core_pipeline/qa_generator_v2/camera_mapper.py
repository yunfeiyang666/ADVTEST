"""
Camera Mapper - 六相机方位映射器
将场景中的对象映射到其可见的相机视图
"""
import math
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict

try:
    from .config import CAMERA_NAMES, CAMERA_FOV_RANGES
except ImportError:
    from config import CAMERA_NAMES, CAMERA_FOV_RANGES


class CameraMapper:
    """
    六相机方位映射器
    
    功能：
    1. 根据对象相对于ego的方位，判断其在哪个相机可见
    2. 为每个对象标注其可见的相机列表
    3. 支持反向查询：给定相机，返回可见的对象列表
    """
    
    def __init__(self, scene_data: Dict):
        """
        Args:
            scene_data: 场景图JSON数据
        """
        self.scene_name = scene_data.get("scene_name", "unknown")
        self.frame_idx = scene_data.get("frame_idx", 0)
        
        # 解析节点
        nodes_data = scene_data.get("nodes") or scene_data.get("objects", [])
        self.nodes = {node["unique_id"]: node for node in nodes_data}
        
        # 获取ego位置和朝向
        self.ego_node = self.nodes.get("ego")
        if not self.ego_node:
            raise ValueError("Scene graph must contain ego node")
        
        self.ego_pos = self.ego_node["translation"]
        self.ego_rotation = self.ego_node["rotation"]  # quaternion [w, x, y, z]
        
        # 计算每个对象到相机的映射
        self.object_to_cameras: Dict[str, List[str]] = {}
        self.camera_to_objects: Dict[str, List[str]] = defaultdict(list)
        
        self._compute_mappings()
    
    def _compute_mappings(self):
        """计算所有对象的相机映射"""
        for uid, node in self.nodes.items():
            if uid == "ego":
                continue
            
            # 计算对象相对于ego的方位角
            angle = self._compute_angle_to_ego(node)
            
            # 判断该角度对应哪些相机
            cameras = self._angle_to_cameras(angle)
            
            self.object_to_cameras[uid] = cameras
            for cam in cameras:
                self.camera_to_objects[cam].append(uid)
    
    def _compute_angle_to_ego(self, node: Dict) -> float:
        """
        计算对象相对于ego的方位角（以ego朝向为0度）
        
        Returns:
            角度（-180到180度），0度表示ego正前方
        """
        obj_pos = node["translation"]
        
        # 相对位置向量
        dx = obj_pos["x"] - self.ego_pos["x"]
        dy = obj_pos["y"] - self.ego_pos["y"]
        
        # 计算世界坐标系中的角度
        world_angle = math.degrees(math.atan2(dy, dx))
        
        # 计算ego的朝向角度（从quaternion）
        ego_yaw = self._quaternion_to_yaw(self.ego_rotation)
        
        # 转换到ego坐标系（ego朝向为0度）
        relative_angle = world_angle - ego_yaw
        
        # 归一化到 [-180, 180]
        while relative_angle > 180:
            relative_angle -= 360
        while relative_angle < -180:
            relative_angle += 360
        
        return relative_angle
    
    def _quaternion_to_yaw(self, quat: List[float]) -> float:
        """
        从quaternion提取yaw角度（绕z轴旋转）
        
        Args:
            quat: [w, x, y, z] 格式的四元数
        
        Returns:
            yaw角度（度）
        """
        w, x, y, z = quat
        
        # 计算yaw (绕z轴的旋转)
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        
        return math.degrees(yaw)
    
    def _angle_to_cameras(self, angle: float) -> List[str]:
        """
        根据角度判断对象在哪些相机可见
        
        Args:
            angle: 相对于ego的角度（-180到180）
        
        Returns:
            相机名称列表
        """
        cameras = []
        
        for cam_name in CAMERA_NAMES:
            min_angle, max_angle = CAMERA_FOV_RANGES[cam_name]
            
            # 特殊处理跨越180度边界的情况（如BACK相机）
            if min_angle > max_angle:
                # 跨越180度边界：角度在[min, 180]或[-180, max]范围内
                if angle >= min_angle or angle <= max_angle:
                    cameras.append(cam_name)
            else:
                # 正常范围
                if min_angle <= angle <= max_angle:
                    cameras.append(cam_name)
        
        return cameras
    
    def get_object_cameras(self, object_id: str) -> List[str]:
        """
        获取对象可见的相机列表
        
        Args:
            object_id: 对象ID（如 "car1"）
        
        Returns:
            相机名称列表
        """
        return self.object_to_cameras.get(object_id, [])
    
    def get_camera_objects(self, camera_name: str) -> List[str]:
        """
        获取相机可见的对象列表
        
        Args:
            camera_name: 相机名称（如 "CAM_FRONT"）
        
        Returns:
            对象ID列表
        """
        return self.camera_to_objects.get(camera_name, [])
    
    def get_objects_by_type_in_camera(self, camera_name: str, obj_type: str) -> List[str]:
        """
        获取相机中特定类型的对象
        
        Args:
            camera_name: 相机名称
            obj_type: 对象类型（如 "car"）
        
        Returns:
            对象ID列表
        """
        objects = self.get_camera_objects(camera_name)
        return [
            uid for uid in objects 
            if self.nodes[uid].get("type") == obj_type
        ]
    
    def get_summary(self) -> Dict:
        """
        获取映射统计信息
        
        Returns:
            包含统计数据的字典
        """
        return {
            "scene": self.scene_name,
            "frame": self.frame_idx,
            "total_objects": len(self.object_to_cameras),
            "camera_distribution": {
                cam: len(objs) 
                for cam, objs in self.camera_to_objects.items()
            }
        }
    
    def print_summary(self):
        """打印映射统计信息"""
        print(f"\n{'='*60}")
        print(f"Camera Mapping Summary: {self.scene_name} Frame {self.frame_idx}")
        print(f"{'='*60}")
        print(f"Total objects: {len(self.object_to_cameras)}")
        print(f"\nObjects per camera:")
        for cam in CAMERA_NAMES:
            objs = self.camera_to_objects[cam]
            print(f"  {cam:20s}: {len(objs):3d} objects")
        print(f"{'='*60}\n")


def test_camera_mapper():
    """测试相机映射器"""
    import json
    from pathlib import Path
    
    # 加载示例场景图
    sg_path = Path(__file__).parent.parent.parent / "output" / "coverage_analysis" / "scene_graphs" / "scene-0103_frame38_scene_graph.json"
    
    if not sg_path.exists():
        print(f"Test scene graph not found: {sg_path}")
        return
    
    with open(sg_path, 'r', encoding='utf-8') as f:
        scene_data = json.load(f)
    
    # 创建映射器
    mapper = CameraMapper(scene_data)
    mapper.print_summary()
    
    # 测试查询
    print("\nExample queries:")
    print(f"car1 visible in: {mapper.get_object_cameras('car1')}")
    print(f"CAM_FRONT objects: {mapper.get_camera_objects('CAM_FRONT')[:5]}...")
    print(f"Cars in CAM_BACK: {mapper.get_objects_by_type_in_camera('CAM_BACK', 'car')}")


if __name__ == "__main__":
    test_camera_mapper()
