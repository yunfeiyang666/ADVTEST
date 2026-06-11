"""检查Neo4j中存储的方向关系"""
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7600", auth=("neo4j", "87017563"))

print("="*80)
print("检查Neo4j中的方向关系 (Source Frame)")
print("="*80)

with driver.session() as session:
    # Q4/Q5: motorcycle -> ? (back-right) 且 ego -> ? (front-left)
    print("\n1. 检查 motorcycle 的 back-right 方向有什么对象:")
    result = session.run("""
        MATCH (m:Object {type:'motorcycle'})-[r:RELATES_TO]->(target:Object)
        WHERE r.predicates[0] = 'back-right'
        RETURN target.unique_id, target.type, r.predicates, r.angle
        LIMIT 10
    """)
    for record in result:
        print(f"   {record['target.unique_id']} ({record['target.type']}): {record['r.predicates']}, angle={record['r.angle']}")
    
    print("\n2. 检查 ego 的 front-left 方向有什么对象:")
    result = session.run("""
        MATCH (e:Object {unique_id:'ego'})-[r:RELATES_TO]->(target:Object)
        WHERE r.predicates[0] = 'front-left'
        RETURN target.unique_id, target.type, r.predicates, r.angle
        LIMIT 10
    """)
    for record in result:
        print(f"   {record['target.unique_id']} ({record['target.type']}): {record['r.predicates']}, angle={record['r.angle']}")
    
    # Q7: truck -> pedestrian (back-right)
    print("\n3. 检查 truck 的 back-right 方向有什么 pedestrian:")
    result = session.run("""
        MATCH (t:Object {type:'truck'})-[r:RELATES_TO]->(p:Object {type:'pedestrian'})
        WHERE r.predicates[0] = 'back-right'
        RETURN p.unique_id, p.status, r.predicates, r.angle
        LIMIT 10
    """)
    records = list(result)
    if not records:
        print("   没有找到!")
    for record in records:
        print(f"   {record['p.unique_id']} (status={record['p.status']}): {record['r.predicates']}, angle={record['r.angle']}")
    
    # 看看 truck 实际上有哪些方向的 pedestrian
    print("\n   truck 的所有 pedestrian 方向关系:")
    result = session.run("""
        MATCH (t:Object {type:'truck'})-[r:RELATES_TO]->(p:Object {type:'pedestrian'})
        RETURN p.unique_id, p.status, r.predicates[0] as direction, r.angle
        ORDER BY r.angle
    """)
    for record in result:
        print(f"   {record['p.unique_id']}: {record['direction']} ({record['r.angle']}°)")
    
    # Q8: truck -> bicycle (front-left)
    print("\n4. 检查 truck 的 front-left 方向有什么 bicycle:")
    result = session.run("""
        MATCH (t:Object {type:'truck'})-[r:RELATES_TO]->(b:Object {type:'bicycle'})
        WHERE r.predicates[0] = 'front-left'
        RETURN b.unique_id, b.status, r.predicates, r.angle
        LIMIT 10
    """)
    records = list(result)
    if not records:
        print("   没有找到!")
    for record in records:
        print(f"   {record['b.unique_id']} (status={record['b.status']}): {record['r.predicates']}, angle={record['r.angle']}")
    
    # 看看 truck 实际上有哪些方向的 bicycle
    print("\n   truck 的所有 bicycle 方向关系:")
    result = session.run("""
        MATCH (t:Object {type:'truck'})-[r:RELATES_TO]->(b:Object {type:'bicycle'})
        RETURN b.unique_id, b.status, r.predicates[0] as direction, r.angle
        ORDER BY r.angle
    """)
    for record in result:
        print(f"   {record['b.unique_id']} ({record['b.status']}): {record['direction']} ({record['r.angle']}°)")

    # Q13: motorcycle -> car (back)
    print("\n5. 检查 motorcycle 的 back 方向有什么 car (parked/stopped):")
    result = session.run("""
        MATCH (m:Object {type:'motorcycle'})-[r:RELATES_TO]->(c:Object {type:'car'})
        WHERE r.predicates[0] = 'back'
        RETURN c.unique_id, c.status, r.predicates, r.angle
        LIMIT 5
    """)
    for record in result:
        print(f"   {record['c.unique_id']} (status={record['c.status']}): {record['r.predicates']}, angle={record['r.angle']}")

driver.close()
print("\n" + "="*80)
