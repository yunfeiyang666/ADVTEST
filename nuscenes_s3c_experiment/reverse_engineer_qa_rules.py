"""
反向工程：测试QA数据集的方位计算规则

三种假设：
1. Ego-centric: 以source对象朝向为准（对于ego是ego朝向，对于其他对象是该对象朝向）
2. Ego-aligned: 统一以ego朝向为准（即使问的是object-to-object）
3. Map-aligned: 统一以地图坐标为准（北=前，东=右）

通过对比scene-0103 frame 38的失败案例来验证
"""
import json
import numpy as np
import math

def quaternion_to_yaw(quaternion):
    """从四元数提取yaw角"""
    if len(quaternion) == 4:
        w, x, y, z = quaternion
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        return yaw
    return 0.0

def get_direction_from_angle(angle):
    """根据角度判断8方位"""
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

def hypothesis1_ego_centric(source_pos, source_rotation, target_pos):
    """假设1: 以source对象自身朝向为准"""
    rel_x_global = target_pos[0] - source_pos[0]
    rel_y_global = target_pos[1] - source_pos[1]
    
    source_yaw = quaternion_to_yaw(source_rotation)
    cos_yaw = math.cos(-source_yaw)
    sin_yaw = math.sin(-source_yaw)
    
    rel_x_local = cos_yaw * rel_x_global - sin_yaw * rel_y_global
    rel_y_local = sin_yaw * rel_x_global + cos_yaw * rel_y_global
    
    angle = math.atan2(rel_y_local, rel_x_local) * 180 / math.pi
    return get_direction_from_angle(angle)

def hypothesis2_ego_aligned(source_pos, ego_rotation, target_pos):
    """假设2: 统一以ego朝向为准"""
    rel_x_global = target_pos[0] - source_pos[0]
    rel_y_global = target_pos[1] - source_pos[1]
    
    ego_yaw = quaternion_to_yaw(ego_rotation)
    cos_yaw = math.cos(-ego_yaw)
    sin_yaw = math.sin(-ego_yaw)
    
    rel_x_local = cos_yaw * rel_x_global - sin_yaw * rel_y_global
    rel_y_local = sin_yaw * rel_x_global + cos_yaw * rel_y_global
    
    angle = math.atan2(rel_y_local, rel_x_local) * 180 / math.pi
    return get_direction_from_angle(angle)

def hypothesis3_map_aligned(source_pos, target_pos):
    """假设3: 以地图坐标为准（北=前=y正方向，东=右=x正方向）"""
    rel_x = target_pos[0] - source_pos[0]
    rel_y = target_pos[1] - source_pos[1]
    
    # NuScenes坐标系：x=东，y=北
    # 北=前(0度)，东=右(-90度)，南=后(180度)，西=左(90度)
    angle = math.atan2(rel_y, rel_x) * 180 / math.pi
    return get_direction_from_angle(angle)

# 加载scene graph
with open('output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json', 'r', encoding='utf-8') as f:
    scene_graph = json.load(f)

# 构建对象字典
objects = {}
for node in scene_graph['nodes']:
    objects[node['unique_id']] = node

ego = objects['ego']
truck = None
pedestrian1 = objects.get('pedestrian1')
bicycle1 = objects.get('bicycle1')
motorcycle1 = objects.get('motorcycle1')

# 找truck（排除trailer）
for obj_id, obj in objects.items():
    if obj['type'] == 'truck' and 'trailer' not in obj['category']:
        truck = obj
        break

print("=" * 100)
print("反向工程：测试QA生成规则")
print("=" * 100)
print()

# 关键测试案例
test_cases = [
    {
        'description': 'Q: "There is a thing that is to the back right of the without rider motorcycle and the front left of me; what is it?" Expected: truck',
        'relation1': ('motorcycle -> truck', motorcycle1, truck),
        'expected_direction1': 'back-right',
        'relation2': ('ego -> truck', ego, truck),
        'expected_direction2': 'front-left'
    },
    {
        'description': 'Q: "There is a pedestrian to the back right of the truck; what is its status?" Expected: moving',
        'relation1': ('truck -> pedestrian1', truck, pedestrian1),
        'expected_direction1': 'back-right',
        'relation2': None,
        'expected_direction2': None
    },
    {
        'description': 'Q: "What is the status of the bicycle to the front left of the truck?" Expected: without rider',
        'relation1': ('truck -> bicycle1', truck, bicycle1),
        'expected_direction1': 'front-left',
        'relation2': None,
        'expected_direction2': None
    }
]

for i, test_case in enumerate(test_cases, 1):
    print(f"【测试案例 {i}】")
    print(test_case['description'])
    print("-" * 100)
    
    # 测试relation1
    if test_case['relation1']:
        desc, source, target = test_case['relation1']
        expected_dir = test_case['expected_direction1']
        
        if source is None or target is None:
            print(f"❌ {desc}: 对象不存在")
            continue
            
        source_pos = [source['translation']['x'], source['translation']['y'], source['translation']['z']]
        target_pos = [target['translation']['x'], target['translation']['y'], target['translation']['z']]
        source_rot = source['rotation']
        
        h1 = hypothesis1_ego_centric(source_pos, source_rot, target_pos)
        h2 = hypothesis2_ego_aligned(source_pos, ego['rotation'], target_pos)
        h3 = hypothesis3_map_aligned(source_pos, target_pos)
        
        print(f"\n关系: {desc}")
        print(f"  期望方位: {expected_dir}")
        print(f"  假设1 (source朝向): {h1:12s} {'✓' if h1 == expected_dir else '✗'}")
        print(f"  假设2 (ego朝向):    {h2:12s} {'✓' if h2 == expected_dir else '✗'}")
        print(f"  假设3 (地图坐标):   {h3:12s} {'✓' if h3 == expected_dir else '✗'}")
    
    # 测试relation2（如果有）
    if test_case['relation2']:
        desc, source, target = test_case['relation2']
        expected_dir = test_case['expected_direction2']
        
        if source is None or target is None:
            print(f"❌ {desc}: 对象不存在")
            continue
            
        source_pos = [source['translation']['x'], source['translation']['y'], source['translation']['z']]
        target_pos = [target['translation']['x'], target['translation']['y'], target['translation']['z']]
        source_rot = source['rotation']
        
        h1 = hypothesis1_ego_centric(source_pos, source_rot, target_pos)
        h2 = hypothesis2_ego_aligned(source_pos, ego['rotation'], target_pos)
        h3 = hypothesis3_map_aligned(source_pos, target_pos)
        
        print(f"\n关系: {desc}")
        print(f"  期望方位: {expected_dir}")
        print(f"  假设1 (source朝向): {h1:12s} {'✓' if h1 == expected_dir else '✗'}")
        print(f"  假设2 (ego朝向):    {h2:12s} {'✓' if h2 == expected_dir else '✗'}")
        print(f"  假设3 (地图坐标):   {h3:12s} {'✓' if h3 == expected_dir else '✗'}")
    
    print()

print("=" * 100)
print("结论判断：")
print("- 如果假设1全✓ → QA使用的是各对象自身朝向（正确的物理意义）")
print("- 如果假设2全✓ → QA偷懒了，统一用ego朝向（常见bug）")
print("- 如果假设3全✓ → QA使用的是地图绝对坐标（你猜测的情况）")
print("- 如果都不全✓ → QA生成脚本有多处不一致或bug")
print("=" * 100)
