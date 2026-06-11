#!/usr/bin/env python
"""调试scene-0916查询为何返回空"""
import sys
sys.path.insert(0, 'E:\\Project\\ADVTEST\\nuscenes_s3c_experiment')

from core_pipeline.coverage_evaluation.coverage_pipeline import Neo4jClient
import json

client = Neo4jClient()
if not client.connect():
    print('❌ 数据库连接失败')
    exit(1)

# 加载场景图
sg_path = 'output/coverage_analysis/scene_graphs/scene-0916_frame8_scene_graph.json'
with open(sg_path, 'r', encoding='utf-8') as f:
    sg_data = json.load(f)

client.clear_database()
client.import_scene_graph(sg_data)

print("="*70)
print("Scene-0916 Frame8 调试")
print("="*70)

# 检查场景中的对象
print("\n1. 场景中有哪些对象？")
r = client.execute_query("MATCH (n:Object) RETURN n.type, COUNT(*) as count ORDER BY count DESC")
if r['success']:
    for row in r['data']:
        print(f"  {row['n.type']}: {row['count']}")

# 检查是否有ego到其他对象的关系
print("\n2. ego车辆有关系边吗？")
r = client.execute_query("""
    MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(x:Object)
    RETURN COUNT(*) as count
""")
if r['success']:
    count = r['data'][0]['count']
    print(f"  ego的关系边数: {count}")

# 检查bus到truck的关系
print("\n3. bus到truck的关系？")
r = client.execute_query("""
    MATCH (bus:Object)-[r:RELATES_TO]->(truck:Object)
    WHERE bus.type = 'bus'
      AND truck.type = 'truck'
      AND NOT truck.category CONTAINS 'trailer'
    RETURN r.angle_matches_ego, COUNT(*) as count
""")
if r['success']:
    if r['data']:
        for row in r['data']:
            print(f"  方向 {row['r.angle_matches_ego']}: {row['count']}")
    else:
        print("  没有bus到truck的关系")

# 检查具体的失败查询
print("\n4. 测试失败的查询（问题2）")
failed_query = """MATCH (ego:Object {unique_id:'ego'})-[r1:RELATES_TO]->(x:Object),
      (bus:Object)-[r2:RELATES_TO]->(x)
WHERE bus.type = 'bus'
  AND 'back-right' IN r1.angle_matches_ego
  AND 'back-right' IN r2.angle_matches_ego
  AND x.status = 'moving'
  AND x.type <> 'barrier'
RETURN x.type AS result
LIMIT 1"""

print("查询:")
print(failed_query)

r = client.execute_query(failed_query)
print(f"\n成功: {r['success']}")
print(f"结果数: {len(r['data']) if r['success'] else 0}")

# 分解检查
print("\n5. 分解检查：")

# ego的back-right关系
r = client.execute_query("""
    MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(x:Object)
    WHERE 'back-right' IN r.angle_matches_ego
    RETURN x.unique_id, x.type, x.status
""")
print(f"  ego的back-right对象: {len(r['data']) if r['success'] else 0}")
if r['success'] and r['data']:
    for row in r['data'][:5]:
        print(f"    - {row}")

# bus的back-right关系
r = client.execute_query("""
    MATCH (bus:Object)-[r:RELATES_TO]->(x:Object)
    WHERE bus.type = 'bus' AND 'back-right' IN r.angle_matches_ego
    RETURN x.unique_id, x.type, x.status
""")
print(f"\n  bus的back-right对象: {len(r['data']) if r['success'] else 0}")
if r['success'] and r['data']:
    for row in r['data'][:5]:
        print(f"    - {row}")

client.close()
