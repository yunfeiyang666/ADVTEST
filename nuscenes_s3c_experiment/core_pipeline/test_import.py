"""测试场景图导入是否正确保留方向属性"""
import json
from pathlib import Path
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig

# 加载场景图
scene_path = Path(r"E:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline\output\coverage_analysis\scene_graphs\scene-0103_frame25_scene_graph.json")
with open(scene_path, 'r', encoding='utf-8') as f:
    scene_graph = json.load(f)

print(f"场景: {scene_graph['scene_name']} 帧{scene_graph['frame_idx']}")
print(f"对象数: {len(scene_graph['nodes'])}")
print(f"关系数: {len(scene_graph['edges'])}")

# 检查原始数据中是否有direction_source
print("\n=== 原始JSON中的方向属性 ===")
edge = scene_graph['edges'][0]
metrics = edge.get('metrics', {})
print(f"direction_source: {metrics.get('direction_source')}")
print(f"direction_ego: {metrics.get('direction_ego')}")

# 测试提取属性
print("\n=== 提取的属性 ===")
props = Neo4jImporter._extract_relationship_properties(edge)
print(f"angle_matches_source: {props.get('angle_matches_source')}")
print(f"angle_matches_ego: {props.get('angle_matches_ego')}")
print(f"direction_8_source: {props.get('direction_8_source')}")
print(f"direction_8_ego: {props.get('direction_8_ego')}")

# 导入并验证
print("\n=== 导入到Neo4j ===")
config = Neo4jConfig.from_env()
importer = Neo4jImporter(config)
try:
    importer.clear_database()
    importer.create_schema()
    importer.import_scene(scene_graph)
    
    # 检查导入后的数据
    print("\n=== 导入后的数据库查询 ===")
    with importer._session() as session:
        result = session.run('''
            MATCH (a:Object)-[r:RELATES_TO]->(b:Object)
            RETURN a.unique_id, b.unique_id,
                   r.angle_matches_source, r.angle_matches_ego,
                   r.direction_8_source, r.direction_8_ego
            LIMIT 3
        ''')
        for row in result:
            print(f"  {row['a.unique_id']} -> {row['b.unique_id']}")
            print(f"    angle_matches_source: {row['r.angle_matches_source']}")
            print(f"    angle_matches_ego: {row['r.angle_matches_ego']}")
            print(f"    direction_8_source: {row['r.direction_8_source']}")
            print(f"    direction_8_ego: {row['r.direction_8_ego']}")
finally:
    importer.close()
