#!/usr/bin/env python
"""调试第4题查询"""
import sys
sys.path.insert(0, 'E:\\Project\\ADVTEST\\nuscenes_s3c_experiment')

from core_pipeline.coverage_evaluation.coverage_pipeline import Neo4jClient, CoverageAnalyzer
import json

# 连接数据库
client = Neo4jClient()
if not client.connect():
    print('❌ 数据库连接失败')
    exit(1)

# 加载场景图
sg_path = 'output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json'
with open(sg_path, 'r', encoding='utf-8') as f:
    sg_data = json.load(f)

client.clear_database()
client.import_scene_graph(sg_data)
print(f"✅ 场景图已导入")

# 原始 Cypher
original_cypher = """MATCH (trailer:Object)
WHERE trailer.category CONTAINS 'trailer'
WITH trailer.status AS trailer_status LIMIT 1
MATCH (bicycle:Object)-[r:RELATES_TO]->(truck:Object)
WHERE bicycle.type='bicycle' AND bicycle.status='with_rider'
  AND truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
  AND 'back-right' IN r.angle_matches_ego
WITH trailer_status, truck.status AS truck_status LIMIT 1
RETURN trailer_status = truck_status AS result"""

print("\n" + "="*70)
print("原始 Cypher:")
print("="*70)
print(original_cypher)

# 1. 先执行原始查询看看结果
print("\n" + "-"*70)
print("1. 执行原始查询")
print("-"*70)
result = client.execute_query(original_cypher)
print(f"Success: {result['success']}")
print(f"Data: {result['data']}")
if not result['success']:
    print(f"Error: {result.get('error')}")

# 2. 分解查询：检查 trailer
print("\n" + "-"*70)
print("2. 检查 trailer")
print("-"*70)
r = client.execute_query("""
    MATCH (trailer:Object)
    WHERE trailer.category CONTAINS 'trailer'
    RETURN trailer.unique_id, trailer.category, trailer.status
""")
if r['success']:
    print(f"找到 {len(r['data'])} 个 trailer:")
    for row in r['data']:
        print(f"  - {row}")
else:
    print("查询失败")

# 3. 检查 bicycle
print("\n" + "-"*70)
print("3. 检查 bicycle")
print("-"*70)
r = client.execute_query("""
    MATCH (bicycle:Object)
    WHERE bicycle.type='bicycle' AND bicycle.status='with_rider'
    RETURN bicycle.unique_id, bicycle.type, bicycle.status
""")
if r['success']:
    print(f"找到 {len(r['data'])} 个 with_rider bicycle:")
    for row in r['data']:
        print(f"  - {row}")

# 4. 检查 bicycle 到 truck 的关系
print("\n" + "-"*70)
print("4. 检查 bicycle 到 truck 的关系")
print("-"*70)
r = client.execute_query("""
    MATCH (bicycle:Object)-[r:RELATES_TO]->(truck:Object)
    WHERE bicycle.type='bicycle' AND bicycle.status='with_rider'
      AND truck.type='truck'
    RETURN bicycle.unique_id, truck.unique_id, r.angle_matches_ego, r.predicates
""")
if r['success']:
    print(f"找到 {len(r['data'])} 条关系:")
    for row in r['data']:
        print(f"  - {row}")
else:
    print(f"查询失败: {r.get('error')}")

# 5. 检查 'back-right' 匹配问题
print("\n" + "-"*70)
print("5. 检查 'back-right' 匹配")
print("-"*70)
r = client.execute_query("""
    MATCH (bicycle:Object)-[r:RELATES_TO]->(truck:Object)
    WHERE bicycle.type='bicycle' AND bicycle.status='with_rider'
      AND truck.type='truck'
      AND 'back-right' IN r.angle_matches_ego
    RETURN bicycle.unique_id, truck.unique_id, r.angle_matches_ego
""")
if r['success']:
    print(f"找到 {len(r['data'])} 条 back-right 关系:")
    for row in r['data']:
        print(f"  - {row}")
else:
    print(f"查询失败: {r.get('error')}")

# 6. 使用 CoverageAnalyzer 分析
print("\n" + "="*70)
print("6. 使用 CoverageAnalyzer 分析")
print("="*70)

valid_nodes = {n['unique_id'] for n in sg_data.get('nodes', [])}
analyzer = CoverageAnalyzer(client, valid_nodes)

try:
    nodes, edges, paths = analyzer.analyze(original_cypher)
    print(f"✅ 分析成功")
    print(f"节点数: {len(nodes)}")
    print(f"边数: {len(edges)}")
    print(f"二跳数: {len(paths)}")
    
    if nodes:
        print(f"\n节点列表: {sorted(nodes)}")
    if edges:
        print(f"\n边列表:")
        for e in sorted(edges):
            print(f"  - {e}")
    if paths:
        print(f"\n二跳路径:")
        for p in sorted(paths):
            print(f"  - {p}")
except Exception as e:
    print(f"❌ 分析失败: {e}")
    import traceback
    traceback.print_exc()

client.close()
