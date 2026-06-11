"""
调试 Q7: pedestrian to back-right of truck; status?
"""
import json
from neo4j import GraphDatabase

# 连接数据库
driver = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))

# 加载场景图
with open(r'E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json', 'r') as f:
    sg = json.load(f)

# 清空并导入
with driver.session() as session:
    session.run('MATCH (n) DETACH DELETE n')
    
    # 导入节点
    for node in sg['nodes']:
        session.run('''
            CREATE (o:Object {
                unique_id: $uid,
                type: $type,
                category: $category,
                status: $status
            })
        ''', uid=node['unique_id'], type=node['type'], 
           category=node.get('category',''), status=node.get('status',''))
    
    # 导入边
    for edge in sg['edges']:
        dist = edge.get('metrics', {}).get('distance', 0) if 'metrics' in edge else edge.get('distance', 0)
        session.run('''
            MATCH (a:Object {unique_id: $src})
            MATCH (b:Object {unique_id: $tgt})
            CREATE (a)-[r:RELATES_TO {
                predicates: $pred,
                direction_4: $d4,
                direction_8: $d8,
                distance: $dist
            }]->(b)
        ''', src=edge['source'], tgt=edge['target'],
           pred=edge.get('predicates',[]), d4=edge.get('direction_4',''),
           d8=edge.get('direction_8',''), dist=dist)
    
    # 验证
    r = session.run('MATCH (n:Object) RETURN count(n) as c').single()
    print(f'导入节点: {r["c"]}')
    r = session.run('MATCH ()-[r]->() RETURN count(r) as c').single()
    print(f'导入边: {r["c"]}')

print('\n=== 查询1: 查看所有truck ===')
with driver.session() as session:
    result = session.run('''
        MATCH (t:Object) WHERE t.type='truck'
        RETURN t.unique_id, t.category, t.status
    ''')
    for r in result:
        print(dict(r))

print('\n=== 查询2: 查看所有pedestrian ===')
with driver.session() as session:
    result = session.run('''
        MATCH (p:Object) WHERE p.type='pedestrian'
        RETURN p.unique_id, p.status
    ''')
    for r in result:
        print(dict(r))

print('\n=== 查询3: truck的所有关系中指向pedestrian的 ===')
with driver.session() as session:
    result = session.run('''
        MATCH (truck:Object)-[r:RELATES_TO]->(ped:Object)
        WHERE truck.type='truck' AND ped.type='pedestrian'
        RETURN truck.unique_id, ped.unique_id, ped.status, 
               r.predicates as pred, r.direction_4, r.direction_8, r.distance
        ORDER BY r.distance
        LIMIT 10
    ''')
    for r in result:
        print(dict(r))

print('\n=== 查询4: 检查有没有predicates[0]=back-right的关系 ===')
with driver.session() as session:
    result = session.run('''
        MATCH (a:Object)-[r:RELATES_TO]->(b:Object)
        WHERE r.predicates[0]='back-right'
        RETURN a.unique_id, a.type, b.unique_id, b.type, r.predicates
        LIMIT 5
    ''')
    rows = list(result)
    if rows:
        for r in rows:
            print(dict(r))
    else:
        print("没有找到 predicates[0]='back-right' 的关系!")

print('\n=== 查询5: 检查predicates数组的实际内容样例 ===')
with driver.session() as session:
    result = session.run('''
        MATCH (truck:Object)-[r:RELATES_TO]->(ped:Object)
        WHERE truck.type='truck' AND ped.type='pedestrian'
        RETURN truck.unique_id, ped.unique_id, r.predicates, r.direction_8
        LIMIT 5
    ''')
    for r in result:
        print(f"predicates={r['r.predicates']}, direction_8={r['r.direction_8']}")

print('\n=== 查询6: 检查direction_8=back-right的关系 ===')
with driver.session() as session:
    result = session.run('''
        MATCH (truck:Object)-[r:RELATES_TO]->(ped:Object)
        WHERE truck.type='truck' AND ped.type='pedestrian'
          AND r.direction_8='back-right'
        RETURN truck.unique_id, ped.unique_id, ped.status, r.predicates, r.direction_8
    ''')
    rows = list(result)
    if rows:
        for r in rows:
            print(dict(r))
    else:
        print("没有找到 direction_8='back-right' 的 truck->pedestrian 关系!")

print('\n=== 查询7: 看看truck后方(back方向)有哪些pedestrian ===')
with driver.session() as session:
    result = session.run('''
        MATCH (truck:Object)-[r:RELATES_TO]->(ped:Object)
        WHERE truck.type='truck' AND ped.type='pedestrian'
          AND r.direction_4='back'
        RETURN truck.unique_id, ped.unique_id, ped.status, r.predicates, r.direction_8, r.distance
        ORDER BY r.distance
    ''')
    rows = list(result)
    if rows:
        for r in rows:
            print(dict(r))
    else:
        print("没有找到 direction_4='back' 的 truck->pedestrian 关系!")

print('\n=== 查询8: 看看truck右方(right方向)有哪些pedestrian ===')
with driver.session() as session:
    result = session.run('''
        MATCH (truck:Object)-[r:RELATES_TO]->(ped:Object)
        WHERE truck.type='truck' AND ped.type='pedestrian'
          AND r.direction_4='right'
        RETURN truck.unique_id, ped.unique_id, ped.status, r.predicates, r.direction_8, r.distance
        ORDER BY r.distance
    ''')
    rows = list(result)
    if rows:
        for r in rows:
            print(dict(r))
    else:
        print("没有找到 direction_4='right' 的 truck->pedestrian 关系!")

print('\n=== 查询9: 统计所有 direction_8 的分布 ===')
with driver.session() as session:
    result = session.run('''
        MATCH ()-[r:RELATES_TO]->()
        RETURN r.direction_8 as dir8, count(*) as cnt
        ORDER BY cnt DESC
    ''')
    for r in result:
        print(f"{r['dir8']}: {r['cnt']}")

driver.close()
print('\n调试完成!')
