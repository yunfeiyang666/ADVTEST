"""验证方向匹配问题"""
from neo4j import GraphDatabase

uri = "bolt://localhost:7600"
user = "neo4j"
password = "87017563"

driver = GraphDatabase.driver(uri, auth=(user, password))

with driver.session() as session:
    # 1. 检查 truck 的信息
    print("=== 1. Truck 信息 ===")
    result = session.run("""
        MATCH (truck:Object)
        WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
        RETURN truck.unique_id, truck.status
    """)
    for r in result:
        print(f"  truck: {r['truck.unique_id']}, status: {r['truck.status']}")
    
    # 2. 检查 truck 的 back-right 方向有哪些对象（source坐标系）
    print("\n=== 2. truck 的 back-right (angle_matches_source) ===")
    result = session.run("""
        MATCH (truck:Object)-[r:RELATES_TO]->(obj:Object)
        WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
          AND 'back-right' IN r.angle_matches_source
        RETURN obj.unique_id, obj.type, obj.status, r.direction_8_source
        LIMIT 10
    """)
    for r in result:
        print(f"  {r['obj.unique_id']}: type={r['obj.type']}, status={r['obj.status']}, dir8={r['r.direction_8_source']}")
    
    # 3. 检查 truck 的 back-right 方向有哪些对象（ego坐标系）
    print("\n=== 3. truck 的 back-right (angle_matches_ego) ===")
    result = session.run("""
        MATCH (truck:Object)-[r:RELATES_TO]->(obj:Object)
        WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
          AND 'back-right' IN r.angle_matches_ego
        RETURN obj.unique_id, obj.type, obj.status, r.direction_8_ego
        LIMIT 10
    """)
    for r in result:
        print(f"  {r['obj.unique_id']}: type={r['obj.type']}, status={r['obj.status']}, dir8={r['r.direction_8_ego']}")
    
    # 4. 检查 pedestrian 在 truck back-right 的情况
    print("\n=== 4. pedestrian 在 truck back-right (两种坐标系) ===")
    print("  Source坐标系:")
    result = session.run("""
        MATCH (truck:Object)-[r:RELATES_TO]->(ped:Object)
        WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
          AND ped.type='pedestrian'
          AND 'back-right' IN r.angle_matches_source
        RETURN ped.unique_id, ped.status, r.direction_8_source
    """)
    count_source = 0
    for r in result:
        count_source += 1
        print(f"    {r['ped.unique_id']}: status={r['ped.status']}, dir8={r['r.direction_8_source']}")
    print(f"  共 {count_source} 个")
    
    print("  Ego坐标系:")
    result = session.run("""
        MATCH (truck:Object)-[r:RELATES_TO]->(ped:Object)
        WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
          AND ped.type='pedestrian'
          AND 'back-right' IN r.angle_matches_ego
        RETURN ped.unique_id, ped.status, r.direction_8_ego
    """)
    count_ego = 0
    for r in result:
        count_ego += 1
        print(f"    {r['ped.unique_id']}: status={r['ped.status']}, dir8={r['r.direction_8_ego']}")
    print(f"  共 {count_ego} 个")
    
    # 5. 检查 motorcycle 的信息
    print("\n=== 5. Motorcycle 信息 ===")
    result = session.run("""
        MATCH (m:Object)
        WHERE m.type='motorcycle'
        RETURN m.unique_id, m.type, m.category, m.status
    """)
    for r in result:
        print(f"  {r['m.unique_id']}: type={r['m.type']}, category={r['m.category']}, status={r['m.status']}")
    
    # 6. 检查 motorcycle 的 back-right 方向有哪些对象
    print("\n=== 6. motorcycle back-right (source坐标系) ===")
    result = session.run("""
        MATCH (m:Object)-[r:RELATES_TO]->(obj:Object)
        WHERE m.type='motorcycle' AND m.status='without_rider'
          AND 'back-right' IN r.angle_matches_source
        RETURN obj.unique_id, obj.type, obj.status
        LIMIT 10
    """)
    count = 0
    for r in result:
        count += 1
        print(f"  {r['obj.unique_id']}: type={r['obj.type']}, status={r['obj.status']}")
    print(f"  共 {count} 个")
    
    print("\n=== 7. motorcycle back-right (ego坐标系) ===")
    result = session.run("""
        MATCH (m:Object)-[r:RELATES_TO]->(obj:Object)
        WHERE m.type='motorcycle' AND m.status='without_rider'
          AND 'back-right' IN r.angle_matches_ego
        RETURN obj.unique_id, obj.type, obj.status
        LIMIT 15
    """)
    count = 0
    for r in result:
        count += 1
        print(f"  {r['obj.unique_id']}: type={r['obj.type']}, status={r['obj.status']}")
    print(f"  共 {count} 个")
    
    # 8. 检查 Q4/Q5 的复合条件
    print("\n=== 8. Q4/Q5: motorcycle back-right AND ego front-left ===")
    print("  Source坐标系:")
    result = session.run("""
        MATCH (motorcycle:Object)
        WHERE motorcycle.type='motorcycle' AND motorcycle.status='without_rider'
        WITH motorcycle LIMIT 1
        MATCH (ego:Object {unique_id:'ego'})
        MATCH (motorcycle)-[r1:RELATES_TO]->(obj:Object),
              (ego)-[r2:RELATES_TO]->(obj)
        WHERE 'back-right' IN r1.angle_matches_source 
          AND 'front-left' IN r2.angle_matches_source
          AND obj.type <> 'barrier'
        RETURN obj.unique_id, obj.type, obj.status
    """)
    for r in result:
        print(f"    {r['obj.unique_id']}: type={r['obj.type']}, status={r['obj.status']}")
    
    print("  Ego坐标系:")
    result = session.run("""
        MATCH (motorcycle:Object)
        WHERE motorcycle.type='motorcycle' AND motorcycle.status='without_rider'
        WITH motorcycle LIMIT 1
        MATCH (ego:Object {unique_id:'ego'})
        MATCH (motorcycle)-[r1:RELATES_TO]->(obj:Object),
              (ego)-[r2:RELATES_TO]->(obj)
        WHERE 'back-right' IN r1.angle_matches_ego 
          AND 'front-left' IN r2.angle_matches_ego
          AND obj.type <> 'barrier'
        RETURN obj.unique_id, obj.type, obj.status
    """)
    for r in result:
        print(f"    {r['obj.unique_id']}: type={r['obj.type']}, status={r['obj.status']}")

driver.close()
