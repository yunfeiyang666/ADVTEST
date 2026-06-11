#!/usr/bin/env python
"""分析各个筛选条件的单独影响"""
import sys
sys.path.insert(0, 'E:\\Project\\ADVTEST\\nuscenes_s3c_experiment')

from core_pipeline.coverage_evaluation.scene_filter import SceneGraphFilter
import json

sg_path = 'output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json'
with open(sg_path, 'r', encoding='utf-8') as f:
    sg_data = json.load(f)

print("="*70)
print("筛选条件影响分析 - scene-0553_frame8")
print("="*70)

# 获取ego坐标
ego = next(n for n in sg_data['nodes'] if n['type'] == 'ego')
ego_x = ego['translation']['x']
ego_y = ego['translation']['y']

nodes = [n for n in sg_data['nodes'] if n['type'] != 'ego']
total = len(nodes)

print(f"\n总节点数（不含ego）: {total}")

# 统计各条件的移除情况
fail_distance = []
fail_visibility = []
fail_pixels = []
pass_all = []

for node in nodes:
    # 检查距离
    trans = node['translation']
    dx = trans['x'] - ego_x
    dy = trans['y'] - ego_y
    distance = (dx**2 + dy**2) ** 0.5
    max_range = SceneGraphFilter.DETECTION_RANGES.get(node['type'], 50)
    check_distance = distance <= max_range
    
    # 检查可见度
    visibility = node.get('visibility', 1.0)
    if visibility > 1:
        visibility = visibility / 4.0
    check_visibility = visibility >= SceneGraphFilter.MIN_VISIBILITY
    
    # 检查像素（使用改进的估算公式）
    size = node.get('size')
    if size:
        width_3d = size.get('width', 0)
        focal_length = 1000  # 假设焦距
        approx_pixels = (width_3d * focal_length) / max(distance, 1.0)
        check_pixels = approx_pixels >= SceneGraphFilter.MIN_PIXELS_STRICT
    else:
        check_pixels = True
    
    # 分类
    if not check_distance:
        fail_distance.append(node)
    elif not check_visibility:
        fail_visibility.append(node)
    elif not check_pixels:
        fail_pixels.append(node)
    else:
        pass_all.append(node)

print(f"\n筛选结果分解:")
print(f"  ✅ 通过所有条件: {len(pass_all)} ({len(pass_all)/total*100:.1f}%)")
print(f"  ❌ 距离不合格: {len(fail_distance)} ({len(fail_distance)/total*100:.1f}%)")
print(f"  ❌ 可见度不合格: {len(fail_visibility)} ({len(fail_visibility)/total*100:.1f}%)")
print(f"  ❌ 像素不合格: {len(fail_pixels)} ({len(fail_pixels)/total*100:.1f}%)")

print(f"\n距离不合格节点示例（前5个）:")
for node in fail_distance[:5]:
    trans = node['translation']
    dx = trans['x'] - ego_x
    dy = trans['y'] - ego_y
    distance = (dx**2 + dy**2) ** 0.5
    max_range = SceneGraphFilter.DETECTION_RANGES.get(node['type'], 50)
    print(f"  {node['unique_id']} ({node['type']}): {distance:.1f}m > {max_range}m")

if fail_visibility:
    print(f"\n可见度不合格节点示例:")
    for node in fail_visibility[:5]:
        visibility = node.get('visibility', 1.0)
        if visibility > 1:
            visibility = visibility / 4.0
        print(f"  {node['unique_id']} ({node['type']}): visibility={visibility:.2f} < 0.40")

if fail_pixels:
    print(f"\n像素不合格节点示例:")
    for node in fail_pixels[:5]:
        size = node.get('size', {})
        width = size.get('width', 0)
        approx_pixels = width * 30
        print(f"  {node['unique_id']} ({node['type']}): ~{approx_pixels:.0f} pixels < 10")

print(f"\n通过所有条件的节点类型分布:")
type_counts = {}
for node in pass_all:
    t = node['type']
    type_counts[t] = type_counts.get(t, 0) + 1

for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"  {t}: {count}")
