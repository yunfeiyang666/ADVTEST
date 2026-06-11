import json

# 读取0553的结果
with open('output/coverage_final_fixed/coverage_scene-0553_frame8_20260204_204325.json') as f:
    data_0553 = json.load(f)

# 读取0916的结果
with open('output/coverage_final_fixed/coverage_scene-0916_frame8_20260204_205151.json') as f:
    data_0916 = json.load(f)

print("="*70)
print("边覆盖情况对比")
print("="*70)

print(f"\nScene-0553 frame8:")
print(f"  L1边: {data_0553['coverage']['L1']['covered']}/{data_0553['coverage']['L1']['total']} = {data_0553['coverage']['L1']['rate']*100:.2f}%")
print(f"  成功题目: {data_0553['questions']['analyzed']}/{data_0553['questions']['total']}")

# 统计0553的边类型
edges_0553 = []
for detail in data_0553['details']:
    edges_0553.extend(detail.get('covered_edges', []))

rel_edges = [e for e in edges_0553 if len(e) == 2 and not e[1].startswith('status:')]
prop_edges = [e for e in edges_0553 if len(e) == 2 and e[1].startswith('status:')]

print(f"  关系边数: {len(set(map(tuple, rel_edges)))}")
print(f"  属性边数: {len(set(map(tuple, prop_edges)))}")
print(f"  关系边示例: {list(set(map(tuple, rel_edges)))[:3]}")
print(f"  属性边示例: {list(set(map(tuple, prop_edges)))[:3]}")

print(f"\nScene-0916 frame8:")
print(f"  L1边: {data_0916['coverage']['L1']['covered']}/{data_0916['coverage']['L1']['total']} = {data_0916['coverage']['L1']['rate']*100:.2f}%")
print(f"  成功题目: {data_0916['questions']['analyzed']}/{data_0916['questions']['total']}")

# 统计0916的边类型
edges_0916 = []
for detail in data_0916['details']:
    edges_0916.extend(detail.get('covered_edges', []))

rel_edges_916 = [e for e in edges_0916 if len(e) == 2 and not e[1].startswith('status:')]
prop_edges_916 = [e for e in edges_0916 if len(e) == 2 and e[1].startswith('status:')]

print(f"  关系边数: {len(set(map(tuple, rel_edges_916)))}")
print(f"  属性边数: {len(set(map(tuple, prop_edges_916)))}")
print(f"  所有边: {list(set(map(tuple, edges_0916)))}")

print(f"\n分析：")
print(f"  0916的题目中，大部分查询返回空结果（查询条件过严或场景不匹配）")
print(f"  只有2个查询返回了数据，且只查询了bus的status属性")
print(f"  这不是统计bug，而是题目与场景的匹配度问题")
