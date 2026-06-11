import sys
sys.path.insert(0, 'E:\\Project\\ADVTEST\\nuscenes_s3c_experiment')
from core_pipeline.coverage_evaluation.coverage_pipeline import Neo4jClient

client = Neo4jClient()
if not client.connect():
    print('连接失败')
    exit(1)

# 测试分母计算
totals = client.get_scene_totals()
print('节点总数:', totals['nodes'])
print('关系边总数:', totals['relation_edges'])
print('属性边总数:', totals['property_edges'])
print('总边数:', totals['total_edges'])
print('二跳路径总数:', totals['2hop_paths'])

# 分解查看
print('\n--- 详细分解 ---')
r = client.execute_query('''
    MATCH (a)-[:RELATES_TO]->(b)
    RETURN sum(CASE WHEN b.status IS NOT NULL AND b.status <> '' AND b.status <> 'unknown' THEN 1 ELSE 0 END) as c
''')
rel_prop = r['data'][0]['c'] if r['success'] else 0
print(f'Rel->Prop 路径数: {rel_prop}')

# 测试新的 Rel->Rel 统计方法
print('\nRel->Rel 分解:')

# 顺序连通
r = client.execute_query('''
    MATCH (a)-[:RELATES_TO]->(b)-[:RELATES_TO]->(c)
    WHERE a <> c
    RETURN count(*) as c
''')
sequential = r['data'][0]['c'] if r['success'] else 0
print(f'  顺序 (a->b->c): {sequential}')

# 分叉连通
r = client.execute_query('''
    MATCH (a)-[:RELATES_TO]->(b), (a)-[:RELATES_TO]->(c)
    WHERE id(b) < id(c)
    RETURN count(*) as c
''')
fork = r['data'][0]['c'] if r['success'] else 0
print(f'  分叉 (b<-a->c): {fork}')

# 汇聚连通
r = client.execute_query('''
    MATCH (a)-[:RELATES_TO]->(c), (b)-[:RELATES_TO]->(c)
    WHERE id(a) < id(b)
    RETURN count(*) as c
''')
converge = r['data'][0]['c'] if r['success'] else 0
print(f'  汇聚 (a->c<-b): {converge}')

rel_rel = sequential + fork + converge
print(f'\nRel->Rel 总计: {sequential} + {fork} + {converge} = {rel_rel}')

print(f'\n验证: {rel_prop} + {rel_rel} = {rel_prop + rel_rel} (应该等于 {totals["2hop_paths"]})')
if rel_prop + rel_rel == totals['2hop_paths']:
    print('✅ 分母计算正确！')
else:
    print('❌ 分母计算有误！')

# 查看实际的属性边示例
r = client.execute_query('''
    MATCH (n:Object)
    WHERE n.status IS NOT NULL AND n.status <> '' AND n.status <> 'unknown'
    RETURN n.unique_id, n.status
    LIMIT 5
''')
if r['success']:
    print('\n--- 属性边示例 ---')
    for row in r['data']:
        print(f"  {row['n.unique_id']}: status={row['n.status']}")

client.close()
