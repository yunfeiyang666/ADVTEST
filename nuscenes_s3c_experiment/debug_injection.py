#!/usr/bin/env python
"""详细调试变量提取和注入"""
import sys
sys.path.insert(0, 'E:\\Project\\ADVTEST\\nuscenes_s3c_experiment')

from core_pipeline.coverage_evaluation.coverage_pipeline import Neo4jClient, CoverageAnalyzer
import json
import re

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

print("="*70)
print("原始 Cypher:")
print("="*70)
print(original_cypher)

# 手动提取变量
print("\n" + "="*70)
print("手动提取变量:")
print("="*70)

node_vars = list(set(m.group(1) for m in re.finditer(r'\((\w+)(?::\w+)?(?:\s*\{[^}]*\})?\)', original_cypher)))
rel_vars = list(set(m.group(1) for m in re.finditer(r'\[(\w+)(?::[\w_]+)?(?:\s*\{[^}]*\})?\]', original_cypher)))
node_vars = [v for v in node_vars if v not in rel_vars]

print(f"节点变量: {node_vars}")
print(f"关系变量: {rel_vars}")

# 构造注入的 RETURN
return_items = [f"{v}.unique_id AS {v}_id" for v in node_vars]
return_items += [f"startNode({r}).unique_id AS {r}_src, endNode({r}).unique_id AS {r}_tgt" for r in rel_vars]
new_return_content = ', '.join(return_items)

print(f"\n新 RETURN 内容:")
print(f"  {new_return_content}")

# 替换 RETURN
pattern = r'RETURN\s+.*?(?=\s+LIMIT|\s+ORDER\s+BY|$)'
injected_cypher = re.sub(pattern, f'RETURN {new_return_content}', original_cypher, count=1, flags=re.I | re.DOTALL)

print("\n" + "="*70)
print("注入后的 Cypher:")
print("="*70)
print(injected_cypher)

# 连接数据库并测试
client = Neo4jClient()
if not client.connect():
    print('\n❌ 数据库连接失败')
    exit(1)

# 加载场景图
sg_path = 'output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json'
with open(sg_path, 'r', encoding='utf-8') as f:
    sg_data = json.load(f)

client.clear_database()
client.import_scene_graph(sg_data)

print("\n" + "="*70)
print("执行注入后的查询:")
print("="*70)

result = client.execute_query(injected_cypher)
print(f"Success: {result['success']}")
print(f"Data count: {len(result['data']) if result['success'] else 0}")

if result['success'] and result['data']:
    print(f"\n返回的数据:")
    for i, row in enumerate(result['data'][:3]):  # 只显示前3条
        print(f"  Row {i+1}: {row}")
    
    # 提取节点和边
    nodes = set()
    edges = set()
    for row in result['data']:
        for k, v in row.items():
            if k.endswith('_id') and v:
                nodes.add(v)
                print(f"    找到节点: {v}")
            elif k.endswith('_src'):
                rel = k[:-4]
                tgt_k = f"{rel}_tgt"
                if tgt_k in row and row[k] and row[tgt_k]:
                    edge = (row[k], row[tgt_k])
                    edges.add(edge)
                    nodes.add(row[k])
                    nodes.add(row[tgt_k])
                    print(f"    找到边: {edge}")
    
    print(f"\n最终统计:")
    print(f"  节点: {nodes}")
    print(f"  边: {edges}")
else:
    print(f"Error: {result.get('error')}")

client.close()
