"""逐题分析所有失败问题"""
from neo4j import GraphDatabase

driver = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))

with driver.session() as session:
    
    # ========== Q5: 与trailer同状态的对象数量 ==========
    print("=" * 70)
    print("Q5: What number of other things are there of the same status as the trailer?")
    print("期望: 8, 实际返回: 28")
    print("=" * 70)
    
    # 检查trailer状态
    r = session.run('MATCH (t:Object) WHERE t.category CONTAINS "trailer" RETURN t.status')
    trailer_status = list(r)[0]['t.status']
    print(f"Trailer状态: {trailer_status}")
    
    # 统计所有同状态对象（排除trailer自己）
    r = session.run('''
        MATCH (t:Object) WHERE t.category CONTAINS "trailer"
        WITH t.status AS ts, t.unique_id AS tid
        MATCH (o:Object) WHERE o.status = ts AND o.unique_id <> tid
        RETURN o.type AS type, count(*) AS cnt
        ORDER BY cnt DESC
    ''')
    print("\n同状态(stopped)的对象分布:")
    total = 0
    for rec in r:
        print(f"  {rec['type']}: {rec['cnt']}")
        total += rec['cnt']
    print(f"总计: {total}")
    
    print("\n分析: 官方答案'8'可能只统计特定类型(如vehicle类)，而不是所有对象")
    
    # ========== Q6: ego后方的truck ==========
    print("\n" + "=" * 70)
    print("Q6: There is a truck that is to the back of me; what is its status?")
    print("期望: stopped, 实际: 未找到")
    print("=" * 70)
    
    # 检查ego后方所有对象
    r = session.run('''
        MATCH (ego:Object {unique_id:"ego"})-[r:RELATES_TO]->(obj:Object)
        WHERE r.predicates[0] = "back"
        RETURN obj.unique_id, obj.type, obj.status, obj.category
    ''')
    results = list(r)
    print(f"Ego后方(back)的所有对象: {len(results)}个")
    for rec in results:
        print(f"  {rec['obj.unique_id']}: type={rec['obj.type']}, status={rec['obj.status']}")
    
    # 检查ego后方的truck（排除trailer）
    r = session.run('''
        MATCH (ego:Object {unique_id:"ego"})-[r:RELATES_TO]->(t:Object)
        WHERE r.predicates[0] = "back" 
        AND t.type = "truck" 
        AND NOT t.category CONTAINS "trailer"
        RETURN t.unique_id, t.status
    ''')
    results = list(r)
    print(f"\nEgo后方(back)的truck（排除trailer）: {len(results)}个")
    for rec in results:
        print(f"  {rec['t.unique_id']}: status={rec['t.status']}")
    
    # 检查ego与所有truck的关系
    print("\nEgo与所有truck的关系:")
    r = session.run('''
        MATCH (ego:Object {unique_id:"ego"})-[r:RELATES_TO]->(t:Object)
        WHERE t.type = "truck"
        RETURN t.unique_id, t.category, r.predicates[0] AS direction, t.status
    ''')
    for rec in r:
        trailer_mark = " (trailer)" if "trailer" in rec['t.category'] else ""
        print(f"  ego -[{rec['direction']}]-> {rec['t.unique_id']}{trailer_mark}: status={rec['t.status']}")
    
    # ========== Q7: moving truck后方的truck ==========
    print("\n" + "=" * 70)
    print("Q7: What status is the truck to the back of the moving truck?")
    print("期望: stopped, 实际: 未找到")
    print("=" * 70)
    
    # 找moving truck
    r = session.run('''
        MATCH (t:Object) 
        WHERE t.type = "truck" AND t.status = "moving" AND NOT t.category CONTAINS "trailer"
        RETURN t.unique_id, t.status
    ''')
    moving_trucks = list(r)
    print(f"Moving trucks (排除trailer): {len(moving_trucks)}个")
    for rec in moving_trucks:
        print(f"  {rec['t.unique_id']}: status={rec['t.status']}")
    
    # 检查moving truck后方的对象
    if moving_trucks:
        truck_id = moving_trucks[0]['t.unique_id']
        r = session.run(f'''
            MATCH (t1:Object {{unique_id:"{truck_id}"}})-[r:RELATES_TO]->(t2:Object)
            WHERE r.predicates[0] = "back"
            RETURN t2.unique_id, t2.type, t2.status, t2.category
        ''')
        results = list(r)
        print(f"\n{truck_id}后方(back)的所有对象: {len(results)}个")
        for rec in results:
            print(f"  {rec['t2.unique_id']}: type={rec['t2.type']}, status={rec['t2.status']}")
        
        # 检查moving truck后方的truck
        r = session.run(f'''
            MATCH (t1:Object {{unique_id:"{truck_id}"}})-[r:RELATES_TO]->(t2:Object)
            WHERE r.predicates[0] = "back" 
            AND t2.type = "truck" 
            AND NOT t2.category CONTAINS "trailer"
            RETURN t2.unique_id, t2.status
        ''')
        results = list(r)
        print(f"\n{truck_id}后方(back)的truck（排除trailer）: {len(results)}个")
        for rec in results:
            print(f"  {rec['t2.unique_id']}: status={rec['t2.status']}")
        
        # 检查moving truck与所有truck的关系
        print(f"\n{truck_id}与其他truck的所有关系:")
        r = session.run(f'''
            MATCH (t1:Object {{unique_id:"{truck_id}"}})-[r:RELATES_TO]->(t2:Object)
            WHERE t2.type = "truck"
            RETURN t2.unique_id, t2.category, r.predicates[0] AS direction, t2.status
        ''')
        for rec in r:
            trailer_mark = " (trailer)" if "trailer" in rec['t2.category'] else ""
            print(f"  {truck_id} -[{rec['direction']}]-> {rec['t2.unique_id']}{trailer_mark}: status={rec['t2.status']}")
    
    # ========== Q11: trailer前左方的with_rider bicycle ==========
    print("\n" + "=" * 70)
    print("Q11: There is a stopped trailer; are there any with rider bicycles to the front left of it?")
    print("期望: yes, 实际: no")
    print("=" * 70)
    
    # 检查trailer前左方的所有对象
    r = session.run('''
        MATCH (t:Object)-[r:RELATES_TO]->(b:Object)
        WHERE t.category CONTAINS "trailer" AND t.status = "stopped"
        AND r.predicates[0] = "front-left"
        RETURN b.unique_id, b.type, b.status
    ''')
    results = list(r)
    print(f"Trailer前左方(front-left)的所有对象: {len(results)}个")
    for rec in results:
        print(f"  {rec['b.unique_id']}: type={rec['b.type']}, status={rec['b.status']}")
    
    # 检查trailer与bicycle的所有关系
    print("\nTrailer与bicycle的所有关系:")
    r = session.run('''
        MATCH (t:Object)-[r:RELATES_TO]->(b:Object)
        WHERE t.category CONTAINS "trailer" AND b.type = "bicycle"
        RETURN t.unique_id, r.predicates[0] AS direction, b.unique_id, b.status
    ''')
    for rec in r:
        print(f"  {rec['t.unique_id']} -[{rec['direction']}]-> {rec['b.unique_id']}: status={rec['b.status']}")
    
    # ========== Q12: with_rider thing前左方的truck ==========
    print("\n" + "=" * 70)
    print("Q12: Is there another truck of the same status as the truck to the front left of the with rider thing?")
    print("期望: no, 实际: 生成失败")
    print("=" * 70)
    
    # 检查bicycle前左方的truck
    r = session.run('''
        MATCH (b:Object {type:"bicycle", status:"with_rider"})-[r:RELATES_TO]->(t:Object)
        WHERE r.predicates[0] = "front-left" 
        AND t.type = "truck" 
        AND NOT t.category CONTAINS "trailer"
        RETURN t.unique_id, t.status
    ''')
    results = list(r)
    print(f"With_rider bicycle前左方(front-left)的truck: {len(results)}个")
    for rec in results:
        print(f"  {rec['t.unique_id']}: status={rec['t.status']}")
    
    # 检查bicycle与所有truck的关系
    print("\nWith_rider bicycle与所有truck的关系:")
    r = session.run('''
        MATCH (b:Object {type:"bicycle", status:"with_rider"})-[r:RELATES_TO]->(t:Object)
        WHERE t.type = "truck"
        RETURN r.predicates[0] AS direction, t.unique_id, t.status, t.category
    ''')
    for rec in r:
        trailer_mark = " (trailer)" if "trailer" in rec['t.category'] else ""
        print(f"  bicycle -[{rec['direction']}]-> {rec['t.unique_id']}{trailer_mark}: status={rec['t.status']}")

driver.close()
