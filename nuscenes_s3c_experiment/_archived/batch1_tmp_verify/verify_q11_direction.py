"""验证Q11方向计算"""
import json
import numpy as np
from scipy.spatial.transform import Rotation as R

# 加载场景图
with open('E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json', 'r') as f:
    sg = json.load(f)

# 找到trailer(truck2)和bicycle1
nodes = {n['unique_id']: n for n in sg['nodes']}

trailer = nodes['truck2']  # trailer
bicycle = nodes['bicycle1']

print("=" * 70)
print("Q11方向验证: bicycle相对于trailer的位置")
print("=" * 70)

# 位置
t_pos = (trailer['translation']['x'], trailer['translation']['y'])
b_pos = (bicycle['translation']['x'], bicycle['translation']['y'])

print(f"\nTrailer (truck2) 位置: ({t_pos[0]:.2f}, {t_pos[1]:.2f})")
print(f"Bicycle1 位置: ({b_pos[0]:.2f}, {b_pos[1]:.2f})")

# 相对位置（bicycle相对于trailer）
rel_x = b_pos[0] - t_pos[0]
rel_y = b_pos[1] - t_pos[1]
print(f"\n全局坐标相对位置: ({rel_x:.2f}, {rel_y:.2f})")

# Trailer的朝向
quat = trailer['rotation']  # [w, x, y, z]
r = R.from_quat([quat[1], quat[2], quat[3], quat[0]])
euler = r.as_euler('zyx', degrees=True)
trailer_yaw = euler[0]
print(f"Trailer朝向(yaw): {trailer_yaw:.1f}°")

# 转换到trailer本地坐标系
heading_rad = np.deg2rad(trailer_yaw)
cos_h = np.cos(-heading_rad)
sin_h = np.sin(-heading_rad)
rel_x_local = cos_h * rel_x - sin_h * rel_y
rel_y_local = sin_h * rel_x + cos_h * rel_y

print(f"本地坐标相对位置: ({rel_x_local:.2f}, {rel_y_local:.2f})")

# 计算角度
angle_local = np.arctan2(rel_y_local, rel_x_local) * 180 / np.pi
print(f"本地角度: {angle_local:.1f}°")

# 8方位判断
def get_direction(angle):
    angle = ((angle + 180) % 360) - 180
    if -22.5 <= angle < 22.5:
        return 'front'
    elif 22.5 <= angle < 67.5:
        return 'front-left'
    elif 67.5 <= angle < 112.5:
        return 'left'
    elif 112.5 <= angle < 157.5:
        return 'back-left'
    elif angle >= 157.5 or angle < -157.5:
        return 'back'
    elif -157.5 <= angle < -112.5:
        return 'back-right'
    elif -112.5 <= angle < -67.5:
        return 'right'
    else:
        return 'front-right'

direction = get_direction(angle_local)
print(f"\n计算得到的方位: {direction}")

# 检查场景图中存储的关系
print("\n" + "=" * 70)
print("场景图中存储的关系:")
print("=" * 70)
for edge in sg['edges']:
    if edge['source'] == 'truck2' and edge['target'] == 'bicycle1':
        print(f"  {edge['source']} -[{edge['predicates']}]-> {edge['target']}")
        print(f"  存储角度: {edge['metrics']['angle']}°")

# Q11期望的是bicycle在trailer的front-left
print("\n" + "=" * 70)
print("分析:")
print("=" * 70)
print(f"官方QA期望: bicycle在trailer的 front-left 方向 → 答案yes")
print(f"场景图计算: bicycle在trailer的 {direction} 方向")
print(f"两者是否一致: {'✅ 一致' if direction == 'front-left' else '❌ 不一致'}")

# 看看angle_local是多少，分析边界情况
print(f"\n详细角度分析:")
print(f"  本地角度: {angle_local:.1f}°")
print(f"  front-left范围: 22.5° ~ 67.5°")
print(f"  front-right范围: -67.5° ~ -22.5°")
if -67.5 <= angle_local < -22.5:
    print(f"  → 落在front-right范围内")
elif 22.5 <= angle_local < 67.5:
    print(f"  → 落在front-left范围内")
else:
    print(f"  → 落在其他范围")
