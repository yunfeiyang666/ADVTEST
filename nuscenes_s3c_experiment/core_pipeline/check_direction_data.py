"""检查方向数据的实际值"""
from neo4j import GraphDatabase

driver = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))

with driver.session() as session:
    # 检查 motorcycle 的关系中的方向数据
    print('=== motorcycle 的关系方向数据 ===')
    result = session.run('''
        MATCH (m:Object)-[r:RELATES_TO]->(obj:Object)
        WHERE m.type='motorcycle'
        RETURN obj.unique_id, obj.type, 
               r.direction_8_source, r.angle_matches_source,
               r.direction_8_ego, r.angle_matches_ego
        LIMIT 5
    ''')
    for r in result:
        print(f"  -> {r['obj.unique_id']} ({r['obj.type']})")
        print(f"     source: dir8={r['r.direction_8_source']}, matches={r['r.angle_matches_source']}")
        print(f"     ego:    dir8={r['r.direction_8_ego']}, matches={r['r.angle_matches_ego']}")
    
    # 检查 angle_matches_source 中有哪些方向
    print('\n=== motorcycle 关系中 angle_matches_source 的所有方向 ===')
    result = session.run('''
        MATCH (m:Object)-[r:RELATES_TO]->(obj:Object)
        WHERE m.type='motorcycle'
        UNWIND r.angle_matches_source AS dir
        RETURN DISTINCT dir
    ''')
    dirs = [r['dir'] for r in result]
    print(f"  方向: {dirs}")
    
    # 检查 motorcycle 的任意方向
    print('\n=== motorcycle 所有方向的统计 ===')
    result = session.run('''
        MATCH (m:Object)-[r:RELATES_TO]->(obj:Object)
        WHERE m.type='motorcycle'
        RETURN r.direction_8_source AS dir_source, r.direction_8_ego AS dir_ego, count(*) AS cnt
        ORDER BY cnt DESC
    ''')
    for r in result:
        print(f"  source={r['dir_source']}, ego={r['dir_ego']}: {r['cnt']}个")

driver.close()
