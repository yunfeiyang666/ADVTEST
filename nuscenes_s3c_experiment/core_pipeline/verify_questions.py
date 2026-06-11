"""手动验证错题"""
import json
import sys
sys.path.insert(0, r'E:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline')
from neo4j import GraphDatabase
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig

def load_scene(scene_file):
    with open(scene_file) as f:
        scene = json.load(f)
    config = Neo4jConfig.from_env()
    importer = Neo4jImporter(config)
    importer.clear_database()
    importer.create_schema()
    importer.import_scene(scene)
    importer.close()
    return scene['scene_name'], scene['frame_idx']

driver = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))

# ========== scene-0553 frame 8 ==========
print('\n' + '='*70)
print('Loading scene-0553 frame 8...')
load_scene(r'E:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline\output\coverage_analysis\scene_graphs\scene-0553_frame8_scene_graph.json')

with driver.session() as s:
    print('\nQ15: Are there any trailers?')
    r = s.run('MATCH (n:Object) WHERE n.category CONTAINS "trailer" RETURN count(n) as cnt')
    cnt = r.single()['cnt']
    print(f'  trailers count: {cnt} -> Answer: {"yes" if cnt > 0 else "no"}')
    
    print('\nQ12: How many barriers are to the front of the trailer?')
    r = s.run('MATCH (t:Object) WHERE t.category CONTAINS "trailer" RETURN t.unique_id LIMIT 1')
    tid = r.single()['t.unique_id']
    
    r = s.run('MATCH (t:Object {unique_id: $tid})-[r:RELATES_TO]->(b:Object {type: "barrier"}) WHERE "front" IN r.angle_matches_source RETURN count(b) as cnt', tid=tid)
    print(f'  宽松匹配: {r.single()["cnt"]}')
    
    r = s.run('MATCH (t:Object {unique_id: $tid})-[r:RELATES_TO]->(b:Object {type: "barrier"}) WHERE r.direction_8_source = "front" RETURN count(b) as cnt', tid=tid)
    print(f'  精确匹配: {r.single()["cnt"]}')

# ========== scene-0103 frame 38 ==========
print('\n' + '='*70)
print('Loading scene-0103 frame 38...')
load_scene(r'E:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline\output\coverage_analysis\scene_graphs\scene-0103_frame38_scene_graph.json')

with driver.session() as s:
    print('\nQ13: Are there any parked cars to the back of the motorcycle?')
    
    # 先看motorcycle
    r = s.run('MATCH (m:Object) WHERE m.type="motorcycle" OR m.category CONTAINS "motorcycle" RETURN m.unique_id, m.status')
    for rec in r:
        print(f'  Motorcycle: {rec["m.unique_id"]}, status={rec["m.status"]}')
    
    # motorcycle后方的cars
    print('\n  Cars to back of motorcycle:')
    r = s.run('''
        MATCH (m:Object)-[r:RELATES_TO]->(c:Object {type: "car"})
        WHERE (m.type="motorcycle" OR m.category CONTAINS "motorcycle")
            AND "back" IN r.angle_matches_source
        RETURN c.unique_id, c.status
    ''')
    for rec in r:
        print(f'    {rec["c.unique_id"]}: status={rec["c.status"]}')
    
    # 按status统计
    r = s.run('''
        MATCH (m:Object)-[r:RELATES_TO]->(c:Object {type: "car"})
        WHERE (m.type="motorcycle" OR m.category CONTAINS "motorcycle")
            AND "back" IN r.angle_matches_source
        RETURN c.status, count(*) as cnt
    ''')
    print('\n  Status distribution:')
    for rec in r:
        print(f'    {rec["c.status"]}: {rec["cnt"]}')

driver.close()
print('\nDone!')
