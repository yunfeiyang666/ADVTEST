"""检查ego到truck的方向"""
from neo4j import GraphDatabase

d = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))
s = d.session()

print("=== Ego到Truck的方向关系 ===")
r = s.run('''
    MATCH (e:Object {unique_id:'ego'})-[r:RELATES_TO]->(t:Object {type:'truck'}) 
    WHERE NOT t.category CONTAINS 'trailer'
    RETURN t.unique_id as uid, r.predicates[0] as dir, t.status as status
''')
for x in r:
    print(f"  {x['uid']}: dir={x['dir']}, status={x['status']}")

print("\n=== 检查所有'back'方向的对象 ===")
r = s.run('''
    MATCH (e:Object {unique_id:'ego'})-[r:RELATES_TO]->(t:Object) 
    WHERE r.predicates[0] = 'back'
    RETURN t.unique_id as uid, t.type as type, t.status as status
''')
for x in r:
    print(f"  {x['uid']} ({x['type']}): status={x['status']}")

print("\n=== Q11: trailer front-left 方向的bicycle ===")
r = s.run('''
    MATCH (t:Object)-[r:RELATES_TO]->(b:Object {type:'bicycle'}) 
    WHERE t.category CONTAINS 'trailer' AND t.status = 'stopped'
    AND r.predicates[0] = 'front-left'
    RETURN t.unique_id as t_uid, b.unique_id as b_uid, b.status as b_status
''')
for x in r:
    print(f"  {x['t_uid']} --front-left--> {x['b_uid']} (status={x['b_status']})")

print("\n=== Q13: bicycle front-left 方向的truck及其status ===")
r = s.run('''
    MATCH (b:Object {type:'bicycle', status:'with_rider'})-[r:RELATES_TO]->(t:Object {type:'truck'}) 
    WHERE r.predicates[0] = 'front-left' AND NOT t.category CONTAINS 'trailer'
    RETURN b.unique_id as b_uid, t.unique_id as t_uid, t.status as t_status
''')
for x in r:
    print(f"  {x['b_uid']} --front-left--> {x['t_uid']} (status={x['t_status']})")

# 再查一下同status的car
print("\n=== 同status的car数量 ===")
r = s.run('''
    MATCH (b:Object {type:'bicycle', status:'with_rider'})-[r:RELATES_TO]->(t:Object {type:'truck'}) 
    WHERE r.predicates[0] = 'front-left' AND NOT t.category CONTAINS 'trailer'
    WITH t.status as truck_status
    MATCH (c:Object {type:'car'})
    WHERE c.status = truck_status
    RETURN truck_status, count(c) as car_count
''')
for x in r:
    print(f"  truck_status={x['truck_status']}, matching cars={x['car_count']}")

print("\n=== bicycle到所有truck的方向 ===")
r = s.run('''
    MATCH (b:Object {type:'bicycle'})-[r:RELATES_TO]->(t:Object {type:'truck'}) 
    RETURN b.unique_id as b_uid, t.unique_id as t_uid, t.category as cat, r.predicates[0] as dir, t.status as status
''')
for x in r:
    is_trailer = 'trailer' in x['cat']
    print(f"  {x['b_uid']} --{x['dir']}--> {x['t_uid']} (trailer={is_trailer}, status={x['status']})")

print("\n=== 检查truck2的详细信息 ===")
r = s.run('MATCH (t:Object {unique_id:"truck2"}) RETURN t.type as type, t.category as cat, t.status as status')
for x in r:
    print(f"  truck2: type={x['type']}, category={x['cat']}, status={x['status']}")

print("\n=== 坐标检查 ===")
r = s.run('''
    MATCH (e:Object {unique_id:'ego'})
    OPTIONAL MATCH (b:Object {type:'bicycle'})
    OPTIONAL MATCH (t1:Object {unique_id:'truck1'})
    OPTIONAL MATCH (t2:Object {unique_id:'truck2'})
    OPTIONAL MATCH (t3:Object {unique_id:'truck3'})
    RETURN e.translation_x as ego_x, e.translation_y as ego_y,
           b.translation_x as b_x, b.translation_y as b_y, b.unique_id as b_id,
           t1.translation_x as t1_x, t1.translation_y as t1_y,
           t2.translation_x as t2_x, t2.translation_y as t2_y,
           t3.translation_x as t3_x, t3.translation_y as t3_y
''')
for x in r:
    print(f"  ego: ({x['ego_x']}, {x['ego_y']})")
    print(f"  bicycle1: ({x['b_x']}, {x['b_y']})")
    print(f"  truck1: ({x['t1_x']}, {x['t1_y']})")
    print(f"  truck2: ({x['t2_x']}, {x['t2_y']})")
    print(f"  truck3: ({x['t3_x']}, {x['t3_y']})")

# 获取ego的rotation来计算yaw
print("\n=== Ego Rotation ===")
r = s.run('MATCH (e:Object {unique_id:"ego"}) RETURN e.rotation')

d.close()
