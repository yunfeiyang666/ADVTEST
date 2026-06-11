"""
深入分析剩余4道错题的根本原因
Q5: 计数差异 (28 vs 8)
Q6: truck back方向找不到
Q8: LLM超时
Q13: front-left方向truck找不到
"""
import numpy as np
from neo4j import GraphDatabase
from pyquaternion import Quaternion

d = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))
s = d.session()

print("=" * 70)
print("  剩余4道错题深度分析")
print("=" * 70)

# ============================================================
# Q5: "What number of other things are there of the same status as the trailer?"
# 预期: 8, 实际: 28
# ============================================================
print("\n" + "=" * 70)
print("【Q5分析】trailer状态相同的其他对象数量")
print("预期: 8, 实际: 28")
print("=" * 70)

# 首先检查trailer的status
r = s.run('''
    MATCH (t:Object) WHERE t.category CONTAINS 'trailer'
    RETURN t.unique_id as uid, t.status as status
''')
trailer_info = list(r)
print(f"\nTrailer信息:")
for x in trailer_info:
    print(f"  {x['uid']}: status = {x['status']}")

# 统计同status的对象
if trailer_info:
    trailer_status = trailer_info[0]['status']
    r = s.run('''
        MATCH (o:Object) WHERE o.status = $status
        RETURN o.type as type, count(*) as cnt
        ORDER BY cnt DESC
    ''', status=trailer_status)
    print(f"\nstatus='{trailer_status}' 的对象分布:")
    total = 0
    for x in r:
        print(f"  {x['type']}: {x['cnt']}")
        total += x['cnt']
    print(f"  总计: {total}")
    print(f"  排除trailer自己: {total - 1}")

# 检查官方答案8可能的来源
print(f"\n官方答案8的可能解释:")
print("  假设1: 只计算某些特定类型?")
r = s.run('''
    MATCH (o:Object) WHERE o.status = 'stopped' AND o.type IN ['car', 'truck', 'bus', 'bicycle', 'pedestrian']
    AND NOT o.category CONTAINS 'trailer'
    RETURN count(o) as cnt
''')
cnt = list(r)[0]['cnt']
print(f"    车辆+行人+bicycle (排除trailer): {cnt}")

r = s.run('''
    MATCH (o:Object) WHERE o.status = 'stopped' AND o.type IN ['truck']
    AND NOT o.category CONTAINS 'trailer'
    RETURN count(o) as cnt
''')
cnt = list(r)[0]['cnt']
print(f"    只计算truck (排除trailer): {cnt}")

# ============================================================
# Q6: "There is a truck that is to the back of me; what is its status?"
# 预期: stopped, 实际: 0
# ============================================================
print("\n" + "=" * 70)
print("【Q6分析】ego后方的truck状态")
print("预期: stopped, 实际: 0 (找不到)")
print("=" * 70)

# 检查ego后方的所有对象
print("\nego后方（含back-left, back, back-right）的truck:")
r = s.run('''
    MATCH (e:Object {unique_id:'ego'})-[r:RELATES_TO]->(t:Object {type:'truck'})
    WHERE r.predicates[0] IN ['back', 'back-left', 'back-right']
    RETURN t.unique_id as uid, t.category as cat, r.predicates[0] as dir, t.status as status
''')
for x in r:
    is_trailer = 'trailer' in x['cat']
    print(f"  {x['uid']}: dir={x['dir']}, trailer={is_trailer}, status={x['status']}")

# 官方问题用的是"to the back"，可能包含back-left/back-right
print("\n问题关键词 'to the back' 的解释:")
print("  - 严格: 只有'back' (22.5度范围)")
print("  - 宽松: 包含'back-left', 'back', 'back-right' (135度范围)")
print("  - 官方可能使用宽松解释")

# ============================================================
# Q8: Bus comparison - LLM超时
# ============================================================
print("\n" + "=" * 70)
print("【Q8分析】复杂bus比较查询")
print("Is the status of the bus to the back right of the not standing pedestrian")
print("the same as the bus that is to the front of the stopped trailer?")
print("预期: yes, 实际: LLM生成Cypher超时")
print("=" * 70)

# 手动分解问题
print("\n手动分解:")
print("  Part 1: bus to the back-right of the not-standing pedestrian")
r = s.run('''
    MATCH (p:Object {type:'pedestrian'})-[r:RELATES_TO]->(b:Object {type:'bus'})
    WHERE p.status <> 'standing' AND r.predicates[0] = 'back-right'
    RETURN p.unique_id as ped, b.unique_id as bus, b.status as status
''')
bus1_results = list(r)
print(f"  结果: {len(bus1_results)} 条")
for x in bus1_results:
    print(f"    {x['ped']} --back-right--> {x['bus']} (status={x['status']})")

print("\n  Part 2: bus to the front of the stopped trailer")
r = s.run('''
    MATCH (t:Object)-[r:RELATES_TO]->(b:Object {type:'bus'})
    WHERE t.category CONTAINS 'trailer' AND t.status = 'stopped'
    AND r.predicates[0] = 'front'
    RETURN t.unique_id as trailer, b.unique_id as bus, b.status as status
''')
bus2_results = list(r)
print(f"  结果: {len(bus2_results)} 条")
for x in bus2_results:
    print(f"    {x['trailer']} --front--> {x['bus']} (status={x['status']})")

if bus1_results and bus2_results:
    same = bus1_results[0]['status'] == bus2_results[0]['status']
    print(f"\n  比较结果: {bus1_results[0]['status']} == {bus2_results[0]['status']} → {same}")
else:
    print("\n  ⚠️ 部分查询无结果，可能是方向问题")

# ============================================================
# Q13: "truck to front-left of bicycle" 找不到
# ============================================================
print("\n" + "=" * 70)
print("【Q13分析】bicycle front-left方向的truck")
print("Are there any other cars of the same status as the truck that is")
print("to the front left of the with rider thing?")
print("预期: yes, 实际: no (找不到truck)")
print("=" * 70)

# 检查bicycle周围所有方向的truck
print("\nbicycle到所有truck的方向和角度:")
r = s.run('''
    MATCH (b:Object {type:'bicycle'})-[r:RELATES_TO]->(t:Object {type:'truck'})
    RETURN b.unique_id as b_uid, t.unique_id as t_uid, 
           r.predicates[0] as dir, r.angle as angle, t.status as status,
           t.category as cat
''')
for x in r:
    is_trailer = 'trailer' in x['cat']
    print(f"  {x['b_uid']} --{x['dir']}--> {x['t_uid']}: angle={x['angle']}°, trailer={is_trailer}, status={x['status']}")

# 检查front-left的角度范围
print("\n方向定义:")
print("  front-left: 22.5° ~ 67.5°")
print("  需要检查是否有truck在这个角度范围内")

# 重新计算方向，检查是否有遗漏
print("\n从原始坐标重新计算:")
r = s.run('''
    MATCH (e:Object {unique_id:'ego'})
    MATCH (b:Object {type:'bicycle'})
    MATCH (t:Object {type:'truck'})
    RETURN e.translation_x as ex, e.translation_y as ey,
           b.translation_x as bx, b.translation_y as by, b.unique_id as b_uid,
           t.translation_x as tx, t.translation_y as ty, t.unique_id as t_uid
''')

# 从场景图获取ego的yaw
import json
scene_graph_path = "E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json"
with open(scene_graph_path, 'r') as f:
    sg = json.load(f)

# 找ego的rotation
ego_node = next(n for n in sg['nodes'] if n['unique_id'] == 'ego')
ego_rotation = ego_node['rotation']
ego_q = Quaternion(ego_rotation)
ego_yaw = ego_q.yaw_pitch_roll[0]  # radians
ego_yaw_deg = np.degrees(ego_yaw)
print(f"\nEgo yaw: {ego_yaw_deg:.1f}°")

# 计算bicycle到各truck的角度
bicycle_node = next(n for n in sg['nodes'] if n['unique_id'] == 'bicycle1')
bx, by = bicycle_node['translation']['x'], bicycle_node['translation']['y']

print(f"\nBicycle位置: ({bx}, {by})")
print("\n从bicycle到各truck的角度计算:")
for node in sg['nodes']:
    if node['type'] == 'truck':
        tx, ty = node['translation']['x'], node['translation']['y']
        dx, dy = tx - bx, ty - by
        
        # 全局角度
        global_angle = np.arctan2(dy, dx)
        
        # 相对于ego朝向的角度 (顺时针为正)
        relative_angle_rad = -(global_angle - ego_yaw)
        relative_angle_deg = np.degrees(relative_angle_rad)
        # 归一化到[-180, 180]
        relative_angle_deg = ((relative_angle_deg + 180) % 360) - 180
        
        # 判断方向
        if -22.5 <= relative_angle_deg < 22.5:
            direction = 'front'
        elif 22.5 <= relative_angle_deg < 67.5:
            direction = 'front-left'
        elif 67.5 <= relative_angle_deg < 112.5:
            direction = 'left'
        elif 112.5 <= relative_angle_deg < 157.5:
            direction = 'back-left'
        elif relative_angle_deg >= 157.5 or relative_angle_deg < -157.5:
            direction = 'back'
        elif -157.5 <= relative_angle_deg < -112.5:
            direction = 'back-right'
        elif -112.5 <= relative_angle_deg < -67.5:
            direction = 'right'
        else:
            direction = 'front-right'
        
        is_trailer = 'trailer' in node.get('category', '')
        print(f"  {node['unique_id']}: pos=({tx},{ty}), global={np.degrees(global_angle):.1f}°, "
              f"relative={relative_angle_deg:.1f}° → {direction}, trailer={is_trailer}")

# 检查官方可能的理解
print("\n" + "=" * 70)
print("【进一步分析Q8 - trailer到bus的方向】")
print("=" * 70)

print("\ntrailer(truck2)到所有bus的方向:")
r = s.run('''
    MATCH (t:Object)-[r:RELATES_TO]->(b:Object {type:'bus'})
    WHERE t.category CONTAINS 'trailer'
    RETURN t.unique_id as trailer, b.unique_id as bus, r.predicates[0] as dir, r.angle as angle, b.status as status
''')
for x in r:
    print(f"  {x['trailer']} --{x['dir']}--> {x['bus']}: angle={x['angle']}°, status={x['status']}")

print("\n问题关键: 'bus to the front of the stopped trailer'")
print("需要的是 trailer 的 front 方向有 bus")
print("但我们查询的结果显示...")

# 检查是否有任何对象在trailer的front方向
print("\ntrailer front方向的所有对象:")
r = s.run('''
    MATCH (t:Object)-[r:RELATES_TO]->(o:Object)
    WHERE t.category CONTAINS 'trailer' AND r.predicates[0] = 'front'
    RETURN t.unique_id as trailer, o.unique_id as obj, o.type as type, r.angle as angle
''')
front_objects = list(r)
print(f"  找到 {len(front_objects)} 个对象")
for x in front_objects:
    print(f"    {x['trailer']} --front--> {x['obj']} ({x['type']}): angle={x['angle']}°")

# 检查bus的位置
print("\nbus的位置和trailer的关系:")
r = s.run('''
    MATCH (t:Object), (b:Object {type:'bus'})
    WHERE t.category CONTAINS 'trailer'
    RETURN t.unique_id as trailer, t.translation_x as tx, t.translation_y as ty,
           b.unique_id as bus, b.translation_x as bx, b.translation_y as by
''')
for x in r:
    print(f"  {x['trailer']}: ({x['tx']}, {x['ty']})")
    print(f"  {x['bus']}: ({x['bx']}, {x['by']})")

# 从bicycle的角度检查front-left方向的所有对象
print("\n" + "=" * 70)
print("【进一步分析Q13 - bicycle front-left方向的所有对象】")
print("=" * 70)

print("\nbicycle front-left方向的所有对象:")
r = s.run('''
    MATCH (b:Object {type:'bicycle'})-[r:RELATES_TO]->(o:Object)
    WHERE r.predicates[0] = 'front-left'
    RETURN o.unique_id as uid, o.type as type, r.angle as angle, o.status as status
''')
fl_objects = list(r)
print(f"  找到 {len(fl_objects)} 个对象")
for x in fl_objects:
    print(f"    {x['uid']} ({x['type']}): angle={x['angle']}°, status={x['status']}")

# 如果没有truck，看看是否有其他vehicle类
print("\n检查是否有vehicle类在bicycle的front-left方向:")
for x in fl_objects:
    if x['type'] in ['car', 'truck', 'bus']:
        print(f"  \u2713 {x['uid']} ({x['type']}): status={x['status']}")

print("\n" + "=" * 70)
print("【根本原因总结】")
print("=" * 70)
print("""
Q5 (28 vs 8):
  根本原因: 官方可能使用了不同的计数逻辑
  - 我们: status='stopped'的所有对象 = 28
  - 官方可能: 只计算特定类型（如排除barrier/construction）
  解决方案: 在prompt中明确"things"通常指vehicle/person类

Q6 (找不到):
  根本原因: LLM排除了trailer
  - truck2(trailer)确实在ego的back方向，status=stopped
  - 但LLM生成的Cypher排除了trailer
  解决方案: 在prompt中明确 trailer 在NuScenes中属于truck类型

Q8 (LLM超时):
  根本原因: Part 2没有结果 - trailer front方向没有bus
  - 问题要求 "bus to the front of the stopped trailer"
  - 但我们的场景图中 trailer(truck2)的front方向没有bus
  解决方案: 这可能是方向计算仍有问题，或者官方问题有误

Q13 (yes但实际no):
  根本原因: 确实没有truck在bicycle的front-left方向
  - truck1: right
  - truck2: back-right
  - truck3: back-right
  解决方案: 需要检查官方的原始标注是否有误
""")

d.close()
