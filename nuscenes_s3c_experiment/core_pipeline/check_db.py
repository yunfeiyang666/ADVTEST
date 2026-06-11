from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7600", auth=("neo4j", "87017563"))

with driver.session() as session:
    # 1. 检查trailer相关对象
    print('=== Trailer相关对象 ===')
    result = session.run('''
        MATCH (n:Object)
        WHERE n.category CONTAINS 'trailer' OR n.type = 'trailer'
        RETURN n.unique_id, n.type, n.category, n.status
        LIMIT 10
    ''')
    count = 0
    for r in result:
        count += 1
        print(f"  {r['n.unique_id']}: type={r['n.type']}, category={r['n.category']}, status={r['n.status']}")
    if count == 0:
        print("  (无结果)")
    
    # 2. 检查所有不同的category值
    print('\n=== 所有Category值 ===')
    result = session.run('''
        MATCH (n:Object)
        RETURN DISTINCT n.category as cat
        ORDER BY cat
    ''')
    for r in result:
        print(f"  {r['cat']}")
    
    # 3. 检查motorcycle相关对象
    print('\n=== Motorcycle对象 ===')
    result = session.run('''
        MATCH (n:Object)
        WHERE n.type = 'motorcycle' OR n.category CONTAINS 'motorcycle'
        RETURN n.unique_id, n.type, n.category
    ''')
    count = 0
    for r in result:
        count += 1
        print(f"  {r['n.unique_id']}: type={r['n.type']}, category={r['n.category']}")
    if count == 0:
        print("  (无结果)")
    
    # 4. 检查方向属性
    print('\n=== 关系的方向属性样例 ===')
    result = session.run('''
        MATCH (a:Object)-[r:RELATES_TO]->(b:Object)
        RETURN a.unique_id, b.unique_id, r.direction_8_source, r.direction_8_ego, 
               r.angle_matches_source, r.angle_matches_ego
        LIMIT 3
    ''')
    for r in result:
        print(f"  {r['a.unique_id']} -> {r['b.unique_id']}")
        print(f"    direction_8_source: {r['r.direction_8_source']}")
        print(f"    direction_8_ego: {r['r.direction_8_ego']}")
        print(f"    angle_matches_source: {r['r.angle_matches_source']}")
        print(f"    angle_matches_ego: {r['r.angle_matches_ego']}")

driver.close()
