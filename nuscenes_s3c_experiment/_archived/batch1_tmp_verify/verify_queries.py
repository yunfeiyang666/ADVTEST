"""验证Cypher查询结果，检查数据层面问题"""
from import_single_scene_to_neo4j import Neo4jImporter
from vqa_pipeline.neo4j_client import Neo4jClient
import json
import os

# 初始化
neo4j_client = Neo4jClient()
importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")

# 场景图目录
SCENE_GRAPH_DIR = "output/coverage_analysis/scene_graphs"

# 定义要测试的场景和查询
test_cases = [
    {
        "scene_graph_file": "scene-0103_frame25_scene_graph.json",
        "description": "错误1&2: car to back-right of not standing ped (scene-0103)",
        "queries": [
            # 查看所有not standing ped和其back-right的car
            """
            MATCH (ped:Object) WHERE ped.type='pedestrian' AND ped.status<>'standing'
            MATCH (ped)-[r:RELATES_TO]->(car:Object) WHERE car.type='car' AND r.predicates[0]='back-right'
            RETURN ped.unique_id AS ped_id, car.unique_id AS car_id, car.status, r.distance
            ORDER BY r.distance ASC
            """,
        ]
    },
    {
        "scene_graph_file": "scene-0553_frame8_scene_graph.json",
        "description": "错误6: truck to front-left of with_rider, then other cars same status",
        "queries": [
            # 先看truck的状态
            """
            MATCH (refObj:Object) WHERE refObj.status='with_rider'
            MATCH (refObj)-[r:RELATES_TO]->(truck:Object)
            WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer' AND r.predicates[0]='front-left'
            RETURN truck.unique_id, truck.status, r.distance
            ORDER BY r.distance ASC
            """,
            # 然后看有多少car的状态一样
            """
            MATCH (c:Object) WHERE c.type='car'
            RETURN c.unique_id, c.status
            """
        ]
    }
]

print("="*80)
print("验证Cypher查询结果")
print("="*80)

for tc in test_cases:
    scene_graph_file = tc["scene_graph_file"]
    filepath = os.path.join(SCENE_GRAPH_DIR, scene_graph_file)
    
    print(f"\n场景图: {scene_graph_file}")
    print(f"描述: {tc['description']}")
    
    # 导入场景数据
    with open(filepath, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    
    importer.clear_database()
    importer.create_constraints()
    importer.import_scene(scene_graph)
    
    for i, query in enumerate(tc["queries"], 1):
        print(f"\n  查询{i}:")
        result = neo4j_client.execute_query(query)
        if result['success']:
            print(f"  结果 ({len(result['data'])}条):")
            for row in result['data'][:10]:  # 最多显示10条
                print(f"    {row}")
        else:
            print(f"  错误: {result.get('error', 'Unknown')}")
    
    print("-"*60)

importer.close()
neo4j_client.close()
