"""验证Q3/Q4查询结果"""
from neo4j import GraphDatabase

driver = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))

with driver.session() as session:
    print('=== Trailer状态 ===')
    r = session.run('MATCH (t:Object) WHERE t.category CONTAINS "trailer" RETURN t.unique_id, t.status')
    for rec in r:
        print(f'  {rec["t.unique_id"]}: status={rec["t.status"]}')
    
    print()
    print('=== Bicycle back-right方向的truck（排除trailer）===')
    r = session.run('''
        MATCH (b:Object {type:"bicycle"})-[r:RELATES_TO]->(t:Object)
        WHERE r.predicates[0] = "back-right" 
        AND t.type = "truck" 
        AND NOT t.category CONTAINS "trailer"
        RETURN t.unique_id, t.status, t.category
    ''')
    for rec in r:
        print(f'  {rec["t.unique_id"]}: status={rec["t.status"]}, category={rec["t.category"]}')
    
    print()
    print('=== Q3/Q4完整查询 ===')
    r = session.run('''
        MATCH (trailer:Object) WHERE trailer.category CONTAINS "trailer"
        WITH trailer LIMIT 1
        MATCH (bicycle:Object) WHERE bicycle.type="bicycle" AND bicycle.status="with_rider"
        WITH trailer, bicycle LIMIT 1
        MATCH (bicycle)-[r:RELATES_TO]->(truck:Object)
        WHERE r.predicates[0] = "back-right"
        AND truck.type = "truck"
        AND NOT truck.category CONTAINS "trailer"
        WITH trailer, truck LIMIT 1
        RETURN trailer.status AS trailer_status, truck.status AS truck_status, trailer.status = truck.status AS same_status
    ''')
    results = list(r)
    if results:
        for rec in results:
            print(f'  trailer_status={rec["trailer_status"]}, truck_status={rec["truck_status"]}, same_status={rec["same_status"]}')
    else:
        print('  无结果!')

    print()
    print('=== 检查bicycle status ===')
    r = session.run('MATCH (b:Object {type:"bicycle"}) RETURN b.unique_id, b.status')
    for rec in r:
        print(f'  {rec["b.unique_id"]}: status={rec["b.status"]}')

driver.close()
