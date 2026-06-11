"""
分析官方QA使用的坐标系定义
- 是全局坐标系 (相对ego) 还是局部坐标系 (相对问题主体)?
- 朝向是如何定义的?
"""
import json
import math
import matplotlib.pyplot as plt
import numpy as np

def quaternion_to_yaw(q):
    """四元数转yaw角(弧度) - NuScenes格式 [w, x, y, z]"""
    w, x, y, z = q[0], q[1], q[2], q[3]
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return yaw

def angle_to_direction_8(angle):
    """8方位角度转方向 (angle in [-180, 180])"""
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

def calculate_direction(src_pos, src_yaw_deg, tgt_pos):
    """计算从source看target的方向"""
    dx = tgt_pos[0] - src_pos[0]
    dy = tgt_pos[1] - src_pos[1]
    
    # 全局角度
    global_angle = math.degrees(math.atan2(dy, dx))
    
    # 相对角度 (考虑source朝向)
    relative_angle = global_angle - src_yaw_deg
    while relative_angle > 180: relative_angle -= 360
    while relative_angle < -180: relative_angle += 360
    
    return global_angle, relative_angle

def load_scene(scene_path):
    """加载场景图"""
    with open(scene_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_scene(scene_name, scene_graph, questions):
    """分析一个场景"""
    nodes = {n['unique_id']: n for n in scene_graph['nodes']}
    edges = scene_graph['edges']
    
    print(f"\n{'='*100}")
    print(f"场景: {scene_name}")
    print(f"{'='*100}")
    
    # 获取ego信息
    ego = nodes.get('ego')
    if ego:
        ego_pos = (ego['translation']['x'], ego['translation']['y'])
        ego_yaw = math.degrees(quaternion_to_yaw(ego['rotation'])) if ego['rotation'] else 0
        print(f"\nEgo: pos={ego_pos}, yaw={ego_yaw:.1f}°")
    
    # 分析每个问题
    for q in questions:
        print(f"\n{'-'*80}")
        print(f"问题: {q['question']}")
        print(f"官方答案: {q['expected_answer']}")
        
        if 'objects' in q:
            analyze_direction_relationship(nodes, edges, ego_pos, ego_yaw, q)

def analyze_direction_relationship(nodes, edges, ego_pos, ego_yaw, q):
    """分析方向关系"""
    objs = q['objects']
    ref_obj_id = objs.get('reference')  # 参考对象
    tgt_obj_id = objs.get('target')     # 目标对象
    expected_dir = objs.get('direction') # 期望方向
    
    if not ref_obj_id or not tgt_obj_id:
        return
    
    ref_obj = nodes.get(ref_obj_id)
    tgt_obj = nodes.get(tgt_obj_id)
    
    if not ref_obj or not tgt_obj:
        print(f"  ⚠️ 对象不存在: ref={ref_obj_id}, tgt={tgt_obj_id}")
        return
    
    ref_pos = (ref_obj['translation']['x'], ref_obj['translation']['y'])
    tgt_pos = (tgt_obj['translation']['x'], tgt_obj['translation']['y'])
    ref_yaw = math.degrees(quaternion_to_yaw(ref_obj['rotation'])) if ref_obj['rotation'] else 0
    
    print(f"\n  参考对象 {ref_obj_id}: pos={ref_pos}, yaw={ref_yaw:.1f}°")
    print(f"  目标对象 {tgt_obj_id}: pos={tgt_pos}")
    
    # 方法1: 使用参考对象的局部坐标系
    global_ang, local_ang = calculate_direction(ref_pos, ref_yaw, tgt_pos)
    local_dir = angle_to_direction_8(local_ang)
    
    # 方法2: 使用ego的坐标系 (全局)
    _, ego_relative_ang = calculate_direction(ego_pos, ego_yaw, tgt_pos)
    _, ego_relative_ang_ref = calculate_direction(ego_pos, ego_yaw, ref_pos)
    
    # 方法3: 不考虑任何朝向的全局坐标
    global_dir = angle_to_direction_8(global_ang)
    
    print(f"\n  方向计算:")
    print(f"    方法1 (局部坐标系,考虑{ref_obj_id}朝向): 相对角度={local_ang:.1f}° → {local_dir}")
    print(f"    方法2 (全局坐标,不考虑朝向): 全局角度={global_ang:.1f}° → {global_dir}")
    print(f"    官方期望: {expected_dir}")
    
    # 判断官方使用的是哪种坐标系
    if local_dir == expected_dir:
        print(f"    ✓ 匹配方法1 (局部坐标系)")
    elif global_dir == expected_dir:
        print(f"    ✓ 匹配方法2 (全局坐标系)")
    else:
        print(f"    ✗ 都不匹配!")

def generate_bev(scene_name, scene_graph, key_objects, output_path):
    """生成BEV图"""
    nodes = {n['unique_id']: n for n in scene_graph['nodes']}
    
    fig, ax = plt.subplots(1, 1, figsize=(14, 12))
    
    colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan']
    
    for i, uid in enumerate(key_objects):
        if uid not in nodes:
            continue
        n = nodes[uid]
        x, y = n['translation']['x'], n['translation']['y']
        
        # 画点
        ax.scatter(x, y, c=colors[i % len(colors)], s=200, zorder=5, 
                   label=f"{uid} ({n.get('status', 'N/A')})")
        
        # 画朝向箭头
        if n['rotation']:
            yaw = quaternion_to_yaw(n['rotation'])
            arrow_len = 5
            dx = arrow_len * math.cos(yaw)
            dy = arrow_len * math.sin(yaw)
            ax.arrow(x, y, dx, dy, head_width=1.5, head_length=0.8, 
                     fc=colors[i % len(colors)], ec=colors[i % len(colors)], zorder=4)
        
        # 标注
        ax.annotate(uid, (x, y), xytext=(5, 5), textcoords='offset points', 
                    fontsize=9, fontweight='bold')
    
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_title(f'{scene_name} - BEV View\n(Arrows show heading direction)')
    ax.legend(loc='upper left', fontsize=8)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"BEV图已保存: {output_path}")
    plt.close()

# ============================================================
# 场景1: scene-0103_frame38
# ============================================================
print("\n" + "="*100)
print("加载 Scene-0103 Frame 38")
print("="*100)

scene_0103 = load_scene('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json')
nodes_0103 = {n['unique_id']: n for n in scene_0103['nodes']}

# 找出关键对象
print("\n关键对象:")
for uid, n in nodes_0103.items():
    if n['type'] in ['ego', 'truck', 'motorcycle', 'bicycle', 'pedestrian']:
        pos = (n['translation']['x'], n['translation']['y'])
        yaw = math.degrees(quaternion_to_yaw(n['rotation'])) if n['rotation'] else 0
        print(f"  {uid}: type={n['type']}, status={n.get('status', 'N/A')}, pos=({pos[0]:.1f}, {pos[1]:.1f}), yaw={yaw:.1f}°")

# 分析问题
# Q7: "There is a pedestrian to the back right of the truck; what is its status?" → moving
# Q8: "What is the status of the bicycle to the front left of the truck?" → without rider
questions_0103 = [
    {
        'question': 'There is a pedestrian to the back right of the truck',
        'expected_answer': 'moving',
        'objects': {
            'reference': 'truck1',
            'target': None,  # 需要找到是哪个pedestrian
            'direction': 'back-right'
        }
    },
    {
        'question': 'bicycle to the front left of the truck',
        'expected_answer': 'without rider',
        'objects': {
            'reference': 'truck1',
            'target': None,  # 需要找到是哪个bicycle
            'direction': 'front-left'
        }
    }
]

# 找所有pedestrian和bicycle相对truck的方向
print("\n" + "="*80)
print("分析 truck 与 其他对象的方向关系")
print("="*80)

truck1 = nodes_0103.get('truck1')
if truck1:
    truck1_pos = (truck1['translation']['x'], truck1['translation']['y'])
    truck1_yaw = math.degrees(quaternion_to_yaw(truck1['rotation'])) if truck1['rotation'] else 0
    print(f"\nTruck1: pos={truck1_pos}, yaw={truck1_yaw:.1f}°")
    
    ego = nodes_0103.get('ego')
    ego_pos = (ego['translation']['x'], ego['translation']['y'])
    ego_yaw = math.degrees(quaternion_to_yaw(ego['rotation'])) if ego['rotation'] else 0
    print(f"Ego: pos={ego_pos}, yaw={ego_yaw:.1f}°")
    
    print(f"\n从Truck1看其他对象 (使用truck1局部坐标系):")
    for uid, n in nodes_0103.items():
        if n['type'] in ['pedestrian', 'bicycle']:
            tgt_pos = (n['translation']['x'], n['translation']['y'])
            global_ang, local_ang = calculate_direction(truck1_pos, truck1_yaw, tgt_pos)
            local_dir = angle_to_direction_8(local_ang)
            
            # 同时计算从ego看这个对象
            _, ego_rel_ang = calculate_direction(ego_pos, ego_yaw, tgt_pos)
            ego_dir = angle_to_direction_8(ego_rel_ang)
            
            if n['type'] == 'pedestrian' and 'right' in local_dir and 'back' in local_dir:
                print(f"  ★ {uid}: truck1视角={local_dir}, ego视角={ego_dir}, status={n.get('status', 'N/A')}")
            elif n['type'] == 'bicycle' and 'left' in local_dir and 'front' in local_dir:
                print(f"  ★ {uid}: truck1视角={local_dir}, ego视角={ego_dir}, status={n.get('status', 'N/A')}")
            else:
                print(f"    {uid}: truck1视角={local_dir}, ego视角={ego_dir}, status={n.get('status', 'N/A')}")

# 生成BEV图
key_objs_0103 = ['ego', 'truck1'] + [uid for uid, n in nodes_0103.items() if n['type'] in ['motorcycle', 'bicycle']][:3]
key_objs_0103 += [uid for uid, n in nodes_0103.items() if n['type'] == 'pedestrian'][:5]
generate_bev('scene-0103_frame38', scene_0103, key_objs_0103, 
             'output/coverage_analysis/scene_0103_frame38_bev.png')

# ============================================================
# 场景2: scene-0916_frame8
# ============================================================
print("\n" + "="*100)
print("加载 Scene-0916 Frame 8")
print("="*100)

scene_0916 = load_scene('output/coverage_analysis/scene_graphs/scene-0916_frame8_scene_graph.json')
nodes_0916 = {n['unique_id']: n for n in scene_0916['nodes']}

print("\n关键对象:")
for uid, n in nodes_0916.items():
    if n['type'] in ['ego', 'bus', 'truck', 'bicycle', 'pedestrian']:
        pos = (n['translation']['x'], n['translation']['y'])
        yaw = math.degrees(quaternion_to_yaw(n['rotation'])) if n['rotation'] else 0
        if n['type'] in ['ego', 'bus', 'truck', 'bicycle']:
            print(f"  {uid}: type={n['type']}, status={n.get('status', 'N/A')}, pos=({pos[0]:.1f}, {pos[1]:.1f}), yaw={yaw:.1f}°")

# Q4: "What status is the truck that is to the front left of the bus?" → parked
# Q5: "There is a truck that is to the front of the bus" → parked
print("\n" + "="*80)
print("分析 bus 与 truck 的方向关系")
print("="*80)

bus1 = nodes_0916.get('bus1')
if bus1:
    bus1_pos = (bus1['translation']['x'], bus1['translation']['y'])
    bus1_yaw = math.degrees(quaternion_to_yaw(bus1['rotation'])) if bus1['rotation'] else 0
    print(f"\nBus1: pos={bus1_pos}, yaw={bus1_yaw:.1f}°")
    
    ego = nodes_0916.get('ego')
    ego_pos = (ego['translation']['x'], ego['translation']['y'])
    ego_yaw = math.degrees(quaternion_to_yaw(ego['rotation'])) if ego['rotation'] else 0
    print(f"Ego: pos={ego_pos}, yaw={ego_yaw:.1f}°")
    
    print(f"\n从Bus1看Trucks (使用bus1局部坐标系):")
    for uid, n in nodes_0916.items():
        if n['type'] == 'truck':
            tgt_pos = (n['translation']['x'], n['translation']['y'])
            global_ang, local_ang = calculate_direction(bus1_pos, bus1_yaw, tgt_pos)
            local_dir = angle_to_direction_8(local_ang)
            
            # 同时计算从ego看
            _, ego_rel_ang = calculate_direction(ego_pos, ego_yaw, tgt_pos)
            ego_dir = angle_to_direction_8(ego_rel_ang)
            
            # 不考虑朝向的全局方向
            global_dir = angle_to_direction_8(global_ang)
            
            print(f"  {uid}: bus1局部={local_dir} (相对角度={local_ang:.1f}°), 全局={global_dir}, ego视角={ego_dir}, status={n.get('status', 'N/A')}")

# Q8: "What is the without rider thing that is to the back of me?" → bicycle
print(f"\n从Ego看Bicycles:")
for uid, n in nodes_0916.items():
    if n['type'] == 'bicycle':
        tgt_pos = (n['translation']['x'], n['translation']['y'])
        _, ego_rel_ang = calculate_direction(ego_pos, ego_yaw, tgt_pos)
        ego_dir = angle_to_direction_8(ego_rel_ang)
        print(f"  {uid}: ego视角={ego_dir} (相对角度={ego_rel_ang:.1f}°), status={n.get('status', 'N/A')}")

# 生成BEV图
key_objs_0916 = ['ego', 'bus1'] + [uid for uid, n in nodes_0916.items() if n['type'] == 'truck'][:3]
key_objs_0916 += [uid for uid, n in nodes_0916.items() if n['type'] == 'bicycle'][:3]
generate_bev('scene-0916_frame8', scene_0916, key_objs_0916,
             'output/coverage_analysis/scene_0916_frame8_bev.png')

print("\n" + "="*100)
print("总结")
print("="*100)
