"""临时脚本：统计所有场景图中的 status / attributes / category 值域"""
import json, os
from collections import Counter

sg_dir = os.path.join(os.path.dirname(__file__), "output", "coverage_analysis", "scene_graphs")

status_counter = Counter()
attr_counter = Counter()
cat_counter = Counter()
node_keys = set()

for fname in os.listdir(sg_dir):
    if not fname.endswith(".json"):
        continue
    fpath = os.path.join(sg_dir, fname)
    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"SKIP {fname}: {e}")
        continue
    if not isinstance(data, dict):
        print(f"SKIP {fname}: not a dict, type={type(data)}")
        continue
    for n in data.get("nodes", []):
        status_counter[n.get("status", "")] += 1
        cat_counter[n.get("category", "")] += 1
        for a in n.get("attributes", []):
            attr_counter[a] += 1
        node_keys.update(n.keys())

print("=== NODE KEYS ===")
print(sorted(node_keys))

print("\n=== STATUS VALUES (count) ===")
for k, v in status_counter.most_common():
    print(f"  {k}: {v}")

print("\n=== ATTRIBUTE VALUES (count) ===")
for k, v in attr_counter.most_common():
    print(f"  {k}: {v}")

print("\n=== CATEGORY VALUES (count) ===")
for k, v in cat_counter.most_common():
    print(f"  {k}: {v}")
