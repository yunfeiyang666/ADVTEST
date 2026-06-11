"""
S3C谓词评估工具
"""
import numpy as np
from config import DISTANCE_PREDICATES, DIRECTION_PREDICATES, ATTRIBUTE_PREDICATES


def calculate_relative_position(ego_pose, obj_annotation):
    """
    计算对象相对于ego车的位置
    
    Args:
        ego_pose: ego车的位姿信息
        obj_annotation: 对象的标注信息
    
    Returns:
        rel_pos: 相对位置 [x, y, z]
        rel_angle: 相对角度（度）
    """
    # 提取ego车位置
    ego_translation = np.array(ego_pose['translation'])
    ego_rotation = ego_pose['rotation']  # 四元数
    
    # 提取对象位置
    obj_translation = np.array(obj_annotation['translation'])
    
    # 计算相对位置（全局坐标系）
    rel_pos_global = obj_translation - ego_translation
    
    # 转换到ego车坐标系（简化版：只考虑yaw角）
    # 从四元数提取yaw角
    ego_yaw = quaternion_to_yaw(ego_rotation)
    
    # 旋转到ego坐标系
    cos_yaw = np.cos(-ego_yaw)
    sin_yaw = np.sin(-ego_yaw)
    
    rel_x = cos_yaw * rel_pos_global[0] - sin_yaw * rel_pos_global[1]
    rel_y = sin_yaw * rel_pos_global[0] + cos_yaw * rel_pos_global[1]
    rel_z = rel_pos_global[2]
    
    rel_pos = np.array([rel_x, rel_y, rel_z])
    
    # 计算相对角度（ego坐标系中，前方为0度）
    rel_angle = np.arctan2(rel_y, rel_x) * 180 / np.pi
    
    return rel_pos, rel_angle


def quaternion_to_yaw(quaternion):
    """
    从四元数提取yaw角
    
    Args:
        quaternion: [w, x, y, z] 或 [x, y, z, w]
    
    Returns:
        yaw: yaw角（弧度）
    """
    # NuScenes使用 [w, x, y, z] 格式
    if len(quaternion) == 4:
        w, x, y, z = quaternion
        # 计算yaw角
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = np.arctan2(siny_cosp, cosy_cosp)
        return yaw
    else:
        return 0.0


def evaluate_spatial_predicates(rel_pos, rel_angle, velocity):
    """
    评估S3C的空间谓词
    
    Args:
        rel_pos: 相对位置 [x, y, z]
        rel_angle: 相对角度（度）
        velocity: 速度矢量 [vx, vy, vz]
    
    Returns:
        predicates: 激活的谓词列表
    """
    predicates = []
    
    # 1. 评估距离关系
    distance = np.linalg.norm(rel_pos[:2])  # 只考虑水平距离
    
    for pred_name, (min_dist, max_dist) in DISTANCE_PREDICATES.items():
        if min_dist <= distance < max_dist:
            predicates.append(pred_name)
            break  # 只选择一个距离谓词
    
    # 2. 评估方向关系
    # 标准化角度到[-180, 180]
    angle = rel_angle
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    
    for pred_name, (min_angle, max_angle) in DIRECTION_PREDICATES.items():
        if pred_name == 'rear':
            # 后方特殊处理：135到180度 或 -180到-135度
            if angle >= 135 or angle <= -135:
                predicates.append(pred_name)
        else:
            if min_angle <= angle < max_angle:
                predicates.append(pred_name)
    
    # 3. 评估运动状态
    if velocity is not None:
        speed = np.linalg.norm(velocity[:2])  # 只考虑水平速度
        
        if speed > ATTRIBUTE_PREDICATES['moving']:
            predicates.append('moving')
        else:
            predicates.append('stopped')
    
    return predicates


def predicates_to_string(predicates):
    """将谓词列表转换为字符串表示"""
    return '+'.join(sorted(predicates))


def string_to_predicates(pred_string):
    """将字符串表示转换为谓词列表"""
    if not pred_string:
        return []
    return pred_string.split('+')
