"""
系统测试：官方QA使用的是ego朝向还是参考对象朝向？
收集所有涉及方向的问题，对比两种计算方式的匹配率
"""
import json
import math

def quaternion_to_yaw(q):
    """四元数转yaw角(弧度)"""
    w, x, y, z = q[0], q[1], q[2], q[3]
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return yaw

def angle_to_direction_8(angle, clockwise_positive=False):
    """
    8方位角度转方向
    clockwise_positive=False: 逆时针为正（数学标准）
    clockwise_positive=True: 顺时针为正（可能是官方定义）
    """
    if clockwise_positive:
        angle = -angle  # 反转
    
    # 归一化到[-180, 180]
    while angle > 180: angle -= 360
    while angle < -180: angle += 360
    
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

def calculate_direction(src_pos, tgt_pos, reference_yaw):
    """计算方向"""
    dx = tgt_pos[0] - src_pos[0]
    dy = tgt_pos[1] - src_pos[1]
    global_angle = math.degrees(math.atan2(dy, dx))
    relative_angle = global_angle - reference_yaw
    while relative_angle > 180: relative_angle -= 360
    while relative_angle < -180: relative_angle += 360
    return relative_angle

def load_scene(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_nodes_dict(scene_graph):
    return {n['unique_id']: n for n in scene_graph['nodes']}

# 定义测试用例：每个用例包含场景、参考对象、目标对象、官方期望方向
# 格式: (场景文件, 参考对象ID, 目标对象ID, 官方期望方向, 问题描述)
test_cases = []

# ============================================================
# 从官方QA中提取方向相关的问题
# ============================================================

# Scene-0553
scene_0553 = load_scene('output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json')
nodes_0553 = get_nodes_dict(scene_0553)
ego_0553 = nodes_0553['ego']
ego_0553_pos = (ego_0553['translation']['x'], ego_0553['translation']['y'])
ego_0553_yaw = math.degrees(quaternion_to_yaw(ego_0553['rotation']))

# Q11: "stopped trailer的front-left有没有bicycle" → yes
# trailer=truck2, bicycle=bicycle1
test_cases.append({
    'scene': '0553',
    'ref_id': 'truck2',
    'tgt_id': 'bicycle1', 
    'expected_dir': 'front-left',
    'question': 'bicycle to front-left of trailer'
})

# Q7: "truck to the back of the moving truck" → stopped
# moving truck=truck1, target应该是truck3
test_cases.append({
    'scene': '0553',
    'ref_id': 'truck1',
    'tgt_id': 'truck3',
    'expected_dir': 'back',
    'question': 'truck to back of moving truck'
})

# Q6: "truck to the back of me" → stopped
# ref=ego, 应该找到truck3 (back-left) 或 truck2 (back, trailer)
test_cases.append({
    'scene': '0553',
    'ref_id': 'ego',
    'tgt_id': 'truck3',  # 真正的truck
    'expected_dir': 'back',
    'question': 'truck to back of ego'
})

# Q3/Q4: "truck to back right of bicycle" 
test_cases.append({
    'scene': '0553',
    'ref_id': 'bicycle1',
    'tgt_id': 'truck3',
    'expected_dir': 'back-right',
    'question': 'truck to back-right of bicycle'
})

# Scene-0916
scene_0916 = load_scene('output/coverage_analysis/scene_graphs/scene-0916_frame8_scene_graph.json')
nodes_0916 = get_nodes_dict(scene_0916)
ego_0916 = nodes_0916['ego']
ego_0916_pos = (ego_0916['translation']['x'], ego_0916['translation']['y'])
ego_0916_yaw = math.degrees(quaternion_to_yaw(ego_0916['rotation']))

# Q4/Q5: "truck to front-left of bus" → parked
# 找到哪个truck满足条件
for truck_id in ['truck1', 'truck2']:
    if truck_id in nodes_0916:
        test_cases.append({
            'scene': '0916',
            'ref_id': 'bus1',
            'tgt_id': truck_id,
            'expected_dir': 'front-left',  # Q4
            'question': f'{truck_id} to front-left of bus'
        })
        test_cases.append({
            'scene': '0916',
            'ref_id': 'bus1',
            'tgt_id': truck_id,
            'expected_dir': 'front',  # Q5
            'question': f'{truck_id} to front of bus'
        })

# Q8: "without rider thing to back of me" → bicycle
for bicycle_id in [uid for uid in nodes_0916.keys() if 'bicycle' in uid][:3]:
    test_cases.append({
        'scene': '0916',
        'ref_id': 'ego',
        'tgt_id': bicycle_id,
        'expected_dir': 'back',
        'question': f'{bicycle_id} to back of ego'
    })

# Scene-0103
scene_0103 = load_scene('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json')
nodes_0103 = get_nodes_dict(scene_0103)
ego_0103 = nodes_0103['ego']
ego_0103_pos = (ego_0103['translation']['x'], ego_0103['translation']['y'])
ego_0103_yaw = math.degrees(quaternion_to_yaw(ego_0103['rotation']))

# Q7: "pedestrian to back-right of truck" → moving
for ped_id in [uid for uid in nodes_0103.keys() if 'pedestrian' in uid][:5]:
    test_cases.append({
        'scene': '0103',
        'ref_id': 'truck1',
        'tgt_id': ped_id,
        'expected_dir': 'back-right',
        'question': f'{ped_id} to back-right of truck'
    })

# Q8: "bicycle to front-left of truck" → without_rider
for bicycle_id in [uid for uid in nodes_0103.keys() if 'bicycle' in uid][:3]:
    test_cases.append({
        'scene': '0103',
        'ref_id': 'truck1',
        'tgt_id': bicycle_id,
        'expected_dir': 'front-left',
        'question': f'{bicycle_id} to front-left of truck'
    })

# ============================================================
# 测试两种坐标系
# ============================================================

scenes = {
    '0553': (scene_0553, nodes_0553, ego_0553_pos, ego_0553_yaw),
    '0916': (scene_0916, nodes_0916, ego_0916_pos, ego_0916_yaw),
    '0103': (scene_0103, nodes_0103, ego_0103_pos, ego_0103_yaw),
}

print("=" * 100)
print("测试官方QA坐标系类型")
print("=" * 100)

results = {
    'ref_obj_ccw': 0,  # 参考对象朝向 + 逆时针为正
    'ref_obj_cw': 0,   # 参考对象朝向 + 顺时针为正
    'ego_ccw': 0,      # Ego朝向 + 逆时针为正  
    'ego_cw': 0,       # Ego朝向 + 顺时针为正
}
total = 0

print(f"\n{'问题':<50} {'官方期望':<12} {'ref+CCW':<12} {'ref+CW':<12} {'ego+CCW':<12} {'ego+CW':<12}")
print("-" * 130)

for case in test_cases:
    scene_data = scenes[case['scene']]
    scene_graph, nodes, ego_pos, ego_yaw = scene_data
    
    ref_obj = nodes.get(case['ref_id'])
    tgt_obj = nodes.get(case['tgt_id'])
    
    if not ref_obj or not tgt_obj:
        continue
    
    ref_pos = (ref_obj['translation']['x'], ref_obj['translation']['y'])
    tgt_pos = (tgt_obj['translation']['x'], tgt_obj['translation']['y'])
    ref_yaw = math.degrees(quaternion_to_yaw(ref_obj['rotation'])) if ref_obj['rotation'] else 0
    
    # 计算相对角度
    # 方法1: 使用参考对象的朝向
    rel_angle_ref = calculate_direction(ref_pos, tgt_pos, ref_yaw)
    # 方法2: 使用ego的朝向
    rel_angle_ego = calculate_direction(ref_pos, tgt_pos, ego_yaw)
    
    # 转换为方向
    dir_ref_ccw = angle_to_direction_8(rel_angle_ref, clockwise_positive=False)
    dir_ref_cw = angle_to_direction_8(rel_angle_ref, clockwise_positive=True)
    dir_ego_ccw = angle_to_direction_8(rel_angle_ego, clockwise_positive=False)
    dir_ego_cw = angle_to_direction_8(rel_angle_ego, clockwise_positive=True)
    
    expected = case['expected_dir']
    
    # 检查匹配
    match_ref_ccw = '✓' if dir_ref_ccw == expected else ''
    match_ref_cw = '✓' if dir_ref_cw == expected else ''
    match_ego_ccw = '✓' if dir_ego_ccw == expected else ''
    match_ego_cw = '✓' if dir_ego_cw == expected else ''
    
    if dir_ref_ccw == expected: results['ref_obj_ccw'] += 1
    if dir_ref_cw == expected: results['ref_obj_cw'] += 1
    if dir_ego_ccw == expected: results['ego_ccw'] += 1
    if dir_ego_cw == expected: results['ego_cw'] += 1
    total += 1
    
    print(f"{case['question']:<50} {expected:<12} {dir_ref_ccw:<10}{match_ref_ccw:<2} {dir_ref_cw:<10}{match_ref_cw:<2} {dir_ego_ccw:<10}{match_ego_ccw:<2} {dir_ego_cw:<10}{match_ego_cw:<2}")

print("\n" + "=" * 100)
print("统计结果")
print("=" * 100)
print(f"\n总测试用例数: {total}")
print(f"\n各方法匹配数:")
print(f"  参考对象朝向 + 逆时针为正 (ref+CCW): {results['ref_obj_ccw']}/{total} ({100*results['ref_obj_ccw']/total:.1f}%)")
print(f"  参考对象朝向 + 顺时针为正 (ref+CW):  {results['ref_obj_cw']}/{total} ({100*results['ref_obj_cw']/total:.1f}%)")
print(f"  Ego朝向 + 逆时针为正 (ego+CCW):      {results['ego_ccw']}/{total} ({100*results['ego_ccw']/total:.1f}%)")
print(f"  Ego朝向 + 顺时针为正 (ego+CW):       {results['ego_cw']}/{total} ({100*results['ego_cw']/total:.1f}%)")

best_method = max(results, key=results.get)
print(f"\n最佳匹配方法: {best_method} ({results[best_method]}/{total})")

if results['ref_obj_cw'] > results['ego_cw'] and results['ref_obj_cw'] > results['ego_ccw']:
    print("\n结论: 官方使用【参考对象朝向】+ 【顺时针为正】")
elif results['ego_cw'] > results['ref_obj_cw'] and results['ego_cw'] > results['ref_obj_ccw']:
    print("\n结论: 官方使用【Ego朝向】+ 【顺时针为正】")
elif results['ego_ccw'] > results['ref_obj_ccw'] and results['ego_ccw'] > results['ref_obj_cw']:
    print("\n结论: 官方使用【Ego朝向】+ 【逆时针为正】")
else:
    print("\n结论: 无法明确判断，可能是混用或其他定义方式")
