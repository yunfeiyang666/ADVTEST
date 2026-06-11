"""手动重新导入场景图并验证方向数据"""
import json
import sys
sys.path.insert(0, '.')

from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig

# 1. 加载场景图
path = r'E:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline\output\coverage_analysis\scene_graphs\scene-0103_frame38_scene_graph.json'
print(f"加载场景图: {path}")
with open(path, 'r', encoding='utf-8') as f:
    scene_graph = json.load(f)

# 2. 检查场景图中的关系数据
edges = scene_graph.get('edges', [])
print(f"\n场景图中有 {len(edges)} 条关系")

# 找一条 motorcycle 关系
moto_edge = None
for e in edges:
    if e.get('source', '').startswith('motorcycle'):
        moto_edge = e
        break

if moto_edge:
    print(f"\n示例 motorcycle 关系:")
    print(f"  source: {moto_edge['source']}")
    print(f"  target: {moto_edge['target']}")
    metrics = moto_edge.get('metrics', {})
    dir_source = metrics.get('direction_source', {})
    dir_ego = metrics.get('direction_ego', {})
    print(f"  direction_source: {dir_source}")
    print(f"  direction_ego: {dir_ego}")

# 3. 测试提取函数
print("\n=== 测试 _extract_relationship_properties ===")
props = Neo4jImporter._extract_relationship_properties(moto_edge)
print(f"提取的属性:")
for k, v in props.items():
    print(f"  {k}: {v}")

# 4. 重新导入到 Neo4j
print("\n=== 重新导入 Neo4j ===")
config = Neo4jConfig(
    uri='bolt://localhost:7600',
    user='neo4j',
    password='87017563'
)

with Neo4jImporter(config) as importer:
    importer.clear_database()
    importer.create_schema()
    importer.import_scene(scene_graph)
    
    # 5. 验证导入结果
    print("\n=== 验证导入后的数据 ===")
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(config.uri, auth=(config.user, config.password))
    with driver.session() as session:
        result = session.run('''
            MATCH (m:Object)-[r:RELATES_TO]->(obj:Object)
            WHERE m.type='motorcycle'
            RETURN obj.unique_id, 
                   r.direction_8_source, r.angle_matches_source,
                   r.direction_8_ego, r.angle_matches_ego
            LIMIT 3
        ''')
        for rec in result:
            print(f"\n  -> {rec['obj.unique_id']}")
            print(f"     direction_8_source: {rec['r.direction_8_source']}")
            print(f"     angle_matches_source: {rec['r.angle_matches_source']}")
            print(f"     direction_8_ego: {rec['r.direction_8_ego']}")
            print(f"     angle_matches_ego: {rec['r.angle_matches_ego']}")
    driver.close()

print("\n完成！")
