"""验证scene-0553帧8的QA预期答案"""
import json
from pathlib import Path
from neo4j import GraphDatabase
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig

# 首先加载正确的场景
scene_path = Path(r"E:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline\output\coverage_analysis\scene_graphs\scene-0553_frame8_scene_graph.json")
with open(scene_path, 'r', encoding='utf-8') as f:
    scene_graph = json.load(f)

config = Neo4jConfig.from_env()
importer = Neo4jImporter(config)

print(f"加载场景: {scene_graph['scene_name']} 帧{scene_graph['frame_idx']}")
importer.clear_database()
importer.create_schema()
importer.import_scene(scene_graph)

# 验证关键问题
print("\n" + "="*70)
print("验证 scene-0553 帧8 的关键QA问题")
print("="*70)

with importer._session() as session:
    # Q15: Are there any trailers? 预期: yes
    print("\n[Q15] Are there any trailers?")
    print("  预期答案: yes")
    r = session.run("MATCH (n:Object) WHERE n.category CONTAINS 'trailer' RETURN count(n) as cnt")
    cnt = r.single()['cnt']
    print(f"  实际: 有{cnt}个trailer")
    print(f"  验证: {'✅ 匹配' if cnt > 0 else '❌ 不匹配'}")
    
    # Q12: How many barriers are to the front of the trailer? 预期: 5
    print("\n[Q12] How many barriers are to the front of the trailer?")
    print("  预期答案: 5")
    r = session.run("""
        MATCH (trailer:Object) 
        WHERE trailer.category CONTAINS 'trailer'
        WITH trailer LIMIT 1
        MATCH (trailer)-[r:RELATES_TO]->(barrier:Object)
        WHERE barrier.type = 'barrier' AND 'front' IN r.angle_matches_source
        RETURN count(barrier) AS cnt
    """)
    cnt = r.single()['cnt']
    print(f"  实际: {cnt}个barrier在trailer前方 (angle_matches_source)")
    
    # 检查不同方向匹配方式
    r = session.run("""
        MATCH (trailer:Object) 
        WHERE trailer.category CONTAINS 'trailer'
        WITH trailer LIMIT 1
        MATCH (trailer)-[r:RELATES_TO]->(barrier:Object)
        WHERE barrier.type = 'barrier' AND 'front' IN r.angle_matches_ego
        RETURN count(barrier) AS cnt
    """)
    cnt_ego = r.single()['cnt']
    print(f"  实际: {cnt_ego}个barrier在trailer前方 (angle_matches_ego)")
    
    # 只用front精确匹配
    r = session.run("""
        MATCH (trailer:Object) 
        WHERE trailer.category CONTAINS 'trailer'
        WITH trailer LIMIT 1
        MATCH (trailer)-[r:RELATES_TO]->(barrier:Object)
        WHERE barrier.type = 'barrier' AND r.direction_8_source = 'front'
        RETURN count(barrier) AS cnt
    """)
    cnt_d8 = r.single()['cnt']
    print(f"  实际: {cnt_d8}个barrier在trailer前方 (direction_8_source精确)")
    
    # Q7: What number of other things are there of the same status as the trailer? 预期: 8
    print("\n[Q7] What number of other things are there of the same status as the trailer?")
    print("  预期答案: 8")
    r = session.run("""
        MATCH (trailer:Object) 
        WHERE trailer.category CONTAINS 'trailer'
        WITH trailer.status AS refStatus, trailer.unique_id AS refId LIMIT 1
        MATCH (other:Object)
        WHERE other.status = refStatus AND other.unique_id <> refId AND other.type <> 'barrier'
        RETURN count(other) AS cnt, refStatus
    """)
    row = r.single()
    print(f"  Trailer状态: {row['refStatus']}")
    print(f"  实际: {row['cnt']}个其他物体具有相同状态 (排除barrier)")
    
    # 不排除barrier的话
    r = session.run("""
        MATCH (trailer:Object) 
        WHERE trailer.category CONTAINS 'trailer'
        WITH trailer.status AS refStatus, trailer.unique_id AS refId LIMIT 1
        MATCH (other:Object)
        WHERE other.status = refStatus AND other.unique_id <> refId
        RETURN count(other) AS cnt
    """)
    cnt_all = r.single()['cnt']
    print(f"  实际: {cnt_all}个其他物体具有相同状态 (包含barrier)")
    
    # Q18: There is a stopped trailer; are there any with rider bicycles to the front left of it? 预期: yes
    print("\n[Q18] Are there any with rider bicycles to the front left of the stopped trailer?")
    print("  预期答案: yes")
    r = session.run("""
        MATCH (trailer:Object)
        WHERE trailer.category CONTAINS 'trailer' AND trailer.status = 'stopped'
        WITH trailer LIMIT 1
        MATCH (trailer)-[r:RELATES_TO]->(bicycle:Object)
        WHERE bicycle.type = 'bicycle' AND bicycle.status = 'with_rider' 
              AND 'front-left' IN r.angle_matches_source
        RETURN count(bicycle) > 0 AS exists
    """)
    exists = r.single()['exists']
    print(f"  实际: {'有' if exists else '没有'}符合条件的bicycle")
    
    # 检查bicycle的位置
    r = session.run("""
        MATCH (trailer:Object)
        WHERE trailer.category CONTAINS 'trailer'
        WITH trailer LIMIT 1
        MATCH (trailer)-[r:RELATES_TO]->(bicycle:Object)
        WHERE bicycle.type = 'bicycle'
        RETURN bicycle.unique_id, bicycle.status, r.angle_matches_source, r.direction_8_source
    """)
    print("  详细bicycle位置信息:")
    for row in r:
        print(f"    {row['bicycle.unique_id']}: status={row['bicycle.status']}, "
              f"direction={row['r.direction_8_source']}, matches={row['r.angle_matches_source']}")
    
    # 检查所有对象状态分布
    print("\n[统计] 各状态的对象数量:")
    r = session.run("""
        MATCH (n:Object)
        RETURN n.status as status, count(*) as cnt
        ORDER BY cnt DESC
    """)
    for row in r:
        print(f"  {row['status']}: {row['cnt']}个")

importer.close()
print("\n验证完成!")
