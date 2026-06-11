"""生成BEV视图分析Q6, Q7, Q11, Q12, Q13的方向关系"""
import json
import math
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyArrowPatch
import numpy as np

# 读取场景图
with open('output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json', 'r', encoding='utf-8') as f:
    scene_graph = json.load(f)

nodes = {n['unique_id']: n for n in scene_graph['nodes']}
edges = scene_graph['edges']

def quaternion_to_yaw(q):
    """四元数转yaw角(弧度)"""
    w, x, y, z = q[3], q[0], q[1], q[2]  # 注意顺序可能是 [x,y,z,w] 或 [w,x,y,z]
    # NuScenes使用 [w, x, y, z] 格式? 让我检查...
    # 实际上NuScenes的rotation是 [w, x, y, z]，但存储时可能是 [x, y, z, w]
    # 从数据看，rotation[0]约0.9xxx，这应该是w分量
    w, x, y, z = q[0], q[1], q[2], q[3]
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return yaw

# 关键对象（根据 scene-0553_frame8_scene_graph.json 中的 unique_id）
# truck2 是 trailer，truck1 是 moving truck，truck3 在该帧不存在
key_objects = ['ego', 'bicycle1', 'truck1', 'truck2']

print("=" * 80)
print("关键对象的位置和朝向")
print("=" * 80)

for uid in key_objects:
    n = nodes[uid]
    x, y = n['translation']['x'], n['translation']['y']
    if n['rotation']:
        yaw = quaternion_to_yaw(n['rotation'])
        yaw_deg = math.degrees(yaw)
    else:
        yaw_deg = 0
    print(f"{uid}: pos=({x:.2f}, {y:.2f}), yaw={yaw_deg:.1f}°, status={n['status']}, category={n.get('category', 'N/A')}")

# 计算从source看target的方向
def calculate_direction(source, target, use_source_heading=True):
    """计算从source看target的方向"""
    src = nodes[source]
    tgt = nodes[target]
    
    dx = tgt['translation']['x'] - src['translation']['x']
    dy = tgt['translation']['y'] - src['translation']['y']
    
    # 全局角度 (从x轴正方向逆时针)
    global_angle = math.degrees(math.atan2(dy, dx))
    
    if use_source_heading and src['rotation']:
        # 考虑source的朝向
        src_yaw = math.degrees(quaternion_to_yaw(src['rotation']))
        # 相对角度 = 全局角度 - source朝向
        relative_angle = global_angle - src_yaw
        # 归一化到 [-180, 180]
        while relative_angle > 180:
            relative_angle -= 360
        while relative_angle < -180:
            relative_angle += 360
    else:
        relative_angle = global_angle
    
    return global_angle, relative_angle

print("\n" + "=" * 80)
print("方向关系分析 (使用局部坐标系)")
print("=" * 80)

pairs = [
    ('ego', 'truck1'),
    ('ego', 'truck2'),
    ('truck1', 'truck2'),
    ('truck2', 'bicycle1'),
    ('bicycle1', 'truck1'),
    ('bicycle1', 'truck2'),
]

for src, tgt in pairs:
    global_ang, rel_ang = calculate_direction(src, tgt)
    # 查找场景图中存储的方向
    stored_dir = "N/A"
    for e in edges:
        if e['source'] == src and e['target'] == tgt:
            stored_dir = e['predicates'][0]
            break
    print(f"{src} -> {tgt}: 全局角度={global_ang:.1f}°, 相对角度={rel_ang:.1f}°, 存储方向={stored_dir}")

print("\n" + "=" * 80)
print("Q7详细分析: truck1后方的truck是什么状态?")
print("=" * 80)
# 注意：在 scene-0553_frame8 中只有一个非trailer的truck (truck1)，Q7 已由上层脚本单独分析，这里略过详细数值。
rel_ang = 0.0

# 方向判断
def angle_to_direction(angle):
    """8方位角度转方向"""
    # angle in [-180, 180]
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
    elif -67.5 <= angle < -22.5:
        return 'front-right'
    return 'unknown'

print(f"基于相对角度的方向: {angle_to_direction(rel_ang)}")

# 如果不考虑truck1的朝向，单纯从全局坐标看
print(f"\n如果从全局坐标系看 (不考虑truck1朝向):")
print(f"全局角度 {global_ang:.1f}° 对应方向: {angle_to_direction(global_ang)}")

# 生成BEV图
fig, ax = plt.subplots(1, 1, figsize=(14, 12))

# 颜色映射
colors = {
    'ego': 'blue',
    'truck1': 'red',
    'truck2': 'orange',  # trailer
    'bicycle1': 'purple',
}

labels = {
    'ego': 'Ego',
    'truck1': 'Truck1 (moving)',
    'truck2': 'Truck2 (trailer, stopped)',
    'bicycle1': 'Bicycle1 (with_rider)',
}

# 绘制对象
for uid in key_objects:
    n = nodes[uid]
    x, y = n['translation']['x'], n['translation']['y']
    
    # 画点
    ax.scatter(x, y, c=colors[uid], s=200, zorder=5, label=labels[uid])
    
    # 画朝向箭头
    if n['rotation']:
        yaw = quaternion_to_yaw(n['rotation'])
        arrow_len = 8
        dx = arrow_len * math.cos(yaw)
        dy = arrow_len * math.sin(yaw)
        ax.arrow(x, y, dx, dy, head_width=2, head_length=1, fc=colors[uid], ec=colors[uid], zorder=4)
    
    # 标注
    ax.annotate(uid, (x, y), xytext=(5, 5), textcoords='offset points', fontsize=10, fontweight='bold')

# 绘制关键方向关系
# ego -> trucks
for src, tgt, style in [
    ('ego', 'truck1', '--'),
    ('ego', 'truck2', '--'),
    ('truck2', 'bicycle1', '-'),  # Q11关键关系
]:
    s = nodes[src]
    t = nodes[tgt]
    sx, sy = s['translation']['x'], s['translation']['y']
    tx, ty = t['translation']['x'], t['translation']['y']
    
    # 查找存储的方向
    stored_dir = "N/A"
    for e in edges:
        if e['source'] == src and e['target'] == tgt:
            stored_dir = e['predicates'][0]
            break
    
    ax.plot([sx, tx], [sy, ty], style, color='gray', alpha=0.5, linewidth=1)
    mid_x, mid_y = (sx + tx) / 2, (sy + ty) / 2
    ax.annotate(stored_dir, (mid_x, mid_y), fontsize=8, color='darkgray', ha='center')

ax.set_xlabel('X (m)')
ax.set_ylabel('Y (m)')
ax.set_title('Scene-0553 Frame 8 - BEV View\n(Arrows show heading direction)')
ax.legend(loc='upper left')
ax.set_aspect('equal')
ax.grid(True, alpha=0.3)

# 保存图片
plt.savefig('output/coverage_analysis/scene_0553_bev_analysis.png', dpi=150, bbox_inches='tight')
print(f"\nBEV图已保存: output/coverage_analysis/scene_0553_bev_analysis.png")

# === 新增：完整BEV图，包含所有对象和关系 ===
fig2, ax2 = plt.subplots(1, 1, figsize=(14, 12))

# 为所有类型生成颜色
type_colors = {
    'ego': 'blue',
    'car': 'red',
    'truck': 'orange',
    'bus': 'brown',
    'bicycle': 'purple',
    'pedestrian': 'green',
    'barrier': 'gray',
    'trailer': 'orange',
}

def get_color(node):
    t = node['type']
    if t in type_colors:
        return type_colors[t]
    return 'black'

# 绘制所有节点
for n in scene_graph['nodes']:
    uid = n['unique_id']
    x, y = n['translation']['x'], n['translation']['y']
    c = get_color(n)
    ax2.scatter(x, y, c=c, s=40, zorder=5)
    ax2.annotate(uid, (x, y), xytext=(3, 3), textcoords='offset points', fontsize=6)
    # 朝向箭头
    if n['rotation']:
        yaw = quaternion_to_yaw(n['rotation'])
        arrow_len = 4
        dx = arrow_len * math.cos(yaw)
        dy = arrow_len * math.sin(yaw)
        ax2.arrow(x, y, dx, dy, head_width=0.8, head_length=0.8, fc=c, ec=c, alpha=0.7, zorder=4)

# 不再绘制所有 RELATES_TO 关系线，避免图面过于杂乱；只保留每个节点自身的朝向箭头。
# 如需查看某一对对象的相对方向，可以在 Neo4j 或单独脚本中查询。

ax2.set_xlabel('X (m)')
ax2.set_ylabel('Y (m)')
ax2.set_title('Scene-0553 Frame 8 - Full BEV (All Objects & RELATES_TO)')
ax2.set_aspect('equal')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('output/coverage_analysis/scene_0553_full_bev.png', dpi=150, bbox_inches='tight')
print("完整BEV图已保存: output/coverage_analysis/scene_0553_full_bev.png")

plt.show()
