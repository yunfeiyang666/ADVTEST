"""
进一步调试 Q7 - 检查ego视角
"""
import json
from neo4j import GraphDatabase

driver = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))

print('=== 查询: ego后右方有哪些pedestrian? ===')
with driver.session() as session:
    result = session.run('''
        MATCH (ego:Object)-[r:RELATES_TO]->(ped:Object)
        WHERE ego.type='ego' AND ped.type='pedestrian'
          AND r.direction_8='back-right'
        RETURN ego.unique_id, ped.unique_id, ped.status, r.predicates, r.direction_8, r.distance
        ORDER BY r.distance
    ''')
    rows = list(result)
    if rows:
        for r in rows:
            print(dict(r))
    else:
        print("没有找到!")

print('\n=== 查询: ego的所有pedestrian关系 ===')
with driver.session() as session:
    result = session.run('''
        MATCH (ego:Object)-[r:RELATES_TO]->(ped:Object)
        WHERE ego.type='ego' AND ped.type='pedestrian'
        RETURN ped.unique_id, ped.status, r.predicates, r.direction_8, r.distance
        ORDER BY r.distance
    ''')
    for r in result:
        print(dict(r))

print('\n=== 查询: predicates[0]=back-right 的 pedestrian 关系 ===')
with driver.session() as session:
    result = session.run('''
        MATCH (a:Object)-[r:RELATES_TO]->(ped:Object)
        WHERE ped.type='pedestrian' AND r.predicates[0]='back-right'
        RETURN a.unique_id, a.type, ped.unique_id, ped.status, r.predicates, r.direction_8
    ''')
    rows = list(result)
    if rows:
        for r in rows:
            print(dict(r))
    else:
        print("没有找到 predicates[0]='back-right' 指向 pedestrian 的关系!")

driver.close()
