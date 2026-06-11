"""检查场景图中的status/attributes/type值域"""
import json, os
from collections import Counter

sg_dir = r'E:\Project\ADVTEST\nuscenes_s3c_experiment\core_pipeline\output\coverage_analysis\scene_graphs'
status_c = Counter()
attr_c = Counter()
type_c = Counter()
cat_c = Counter()

files = [f for f in os.listdir(sg_dir) if f.endswith('scene_graph.json')]
print(f"扫描 {len(files)} 个场景图文件")

for fname in files:
    with open(os.path.join(sg_dir, fname), encoding='utf-8') as fp:
        data = json.load(fp)
    for node in data.get('nodes', []):
        if node.get('status'):
            status_c[node['status']] += 1
        if node.get('type'):
            type_c[node['type']] += 1
        if node.get('category'):
            cat_c[node['category']] += 1
        for attr in node.get('attributes', []):
            attr_c[attr] += 1

print('\n=== status 值域 ===')
for s, c in status_c.most_common():
    print(f'  {s}: {c}')

print(f'\n=== attributes 值域 ({len(attr_c)} 种) ===')
for a, c in attr_c.most_common():
    print(f'  {a}: {c}')

print(f'\n=== type 值域 ({len(type_c)} 种) ===')
for t, c in type_c.most_common():
    print(f'  {t}: {c}')

print(f'\n=== category 值域 (top 20) ===')
for t, c in cat_c.most_common(20):
    print(f'  {t}: {c}')

has_color = any('color' in a.lower() for a in attr_c)
print(f'\n颜色信息: {"有" if has_color else "无"}')
