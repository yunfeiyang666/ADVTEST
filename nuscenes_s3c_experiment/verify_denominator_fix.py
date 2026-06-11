#!/usr/bin/env python
"""验证分母计算修复"""
import sys
sys.path.insert(0, 'E:\\Project\\ADVTEST\\nuscenes_s3c_experiment')

from core_pipeline.coverage_evaluation.coverage_pipeline import Neo4jClient
import json

print("="*70)
print(" 验证分母计算修复")
print("="*70)

# 连接数据库
client = Neo4jClient()
if not client.connect():
    print('❌ 数据库连接失败')
    exit(1)

print("\n✅ 数据库已连接")

# 加载场景图
sg_path = 'output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json'
with open(sg_path, 'r', encoding='utf-8') as f:
    sg_data = json.load(f)

# 清空并导入场景图
client.clear_database()
client.import_scene_graph(sg_data)
print(f"✅ 场景图已导入: {sg_data['scene_name']} frame{sg_data['frame_idx']}")

# 获取分母
totals = client.get_scene_totals()

print("\n" + "-"*70)
print(" 分母统计（Ground Truth）")
print("-"*70)
print(f"节点总数: {totals['nodes']}")
print(f"关系边总数: {totals['relation_edges']}")
print(f"属性边总数: {totals['property_edges']}")
print(f"总边数: {totals['total_edges']}")
print(f"二跳路径总数: {totals['2hop_paths']}")

# 验证二跳分解
print("\n" + "-"*70)
print(" 二跳路径分解验证")
print("-"*70)

r = client.execute_query('''
    MATCH (a)-[:RELATES_TO]->(b)
    RETURN sum(CASE WHEN b.status IS NOT NULL AND b.status <> '' AND b.status <> 'unknown' THEN 1 ELSE 0 END) as c
''')
rel_prop = r['data'][0]['c'] if r['success'] else 0
print(f"Rel→Prop: {rel_prop}")

# 顺序
r = client.execute_query('''
    MATCH (a)-[:RELATES_TO]->(b)-[:RELATES_TO]->(c)
    WHERE a <> c
    RETURN count(*) as c
''')
sequential = r['data'][0]['c'] if r['success'] else 0

# 分叉
r = client.execute_query('''
    MATCH (a)-[:RELATES_TO]->(b), (a)-[:RELATES_TO]->(c)
    WHERE id(b) < id(c)
    RETURN count(*) as c
''')
fork = r['data'][0]['c'] if r['success'] else 0

# 汇聚
r = client.execute_query('''
    MATCH (a)-[:RELATES_TO]->(c), (b)-[:RELATES_TO]->(c)
    WHERE id(a) < id(b)
    RETURN count(*) as c
''')
converge = r['data'][0]['c'] if r['success'] else 0

rel_rel = sequential + fork + converge

print(f"Rel→Rel:")
print(f"  顺序: {sequential}")
print(f"  分叉: {fork}")
print(f"  汇聚: {converge}")
print(f"  小计: {rel_rel}")

print(f"\n总二跳: {rel_prop} + {rel_rel} = {rel_prop + rel_rel}")

if rel_prop + rel_rel == totals['2hop_paths']:
    print("\n✅ 分母计算正确！")
else:
    print(f"\n❌ 分母计算有误: 期望 {totals['2hop_paths']}, 实际 {rel_prop + rel_rel}")

client.close()

print("\n" + "="*70)
print(" 验证完成")
print("="*70)
