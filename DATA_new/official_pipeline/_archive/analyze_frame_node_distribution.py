#!/usr/bin/env python3
import json
import pathlib
import sys
from collections import defaultdict

plan_path = pathlib.Path(__file__).parent.parent / 'deploy' / 'nuscenesqa_val_plan_full.json'
with open(plan_path, 'r', encoding='utf-8') as f:
    plan = json.load(f)

sg_dir = pathlib.Path(__file__).parent / 'output' / 'coverage_analysis' / 'scene_graphs'

print(f'统计 {len(plan["frames"])} 帧的节点分布...')

node_counts = []
missing_count = 0

for i, frame in enumerate(plan['frames']):
    sg_file = sg_dir / frame['sg_filename']
    if sg_file.exists():
        with open(sg_file, 'r', encoding='utf-8') as f:
            sg_data = json.load(f)
            n_nodes = len(sg_data.get('nodes', []))
            node_counts.append((frame['scene_id'], frame['frame_id'], n_nodes))
    else:
        missing_count += 1

print(f'找到: {len(node_counts)} 帧')
print(f'缺失: {missing_count} 帧')

if not node_counts:
    print('没有场景图文件！使用 VQA_BUILD_SCENE_GRAPH_ONTHEFLY=true')
    sys.exit(1)

bins = [0, 5, 10, 15, 20, 25, 30, 40, 50, 100]
bin_counts = defaultdict(int)

for _, _, n in node_counts:
    for i in range(len(bins)-1):
        if bins[i] <= n < bins[i+1]:
            bin_counts[f'{bins[i]}-{bins[i+1]}'] += 1
            break
    else:
        if n >= 100:
            bin_counts['100+'] += 1

print('\n节点区间 | 帧数 | 占比')
total = len(node_counts)
for i in range(len(bins)-1):
    key = f'{bins[i]}-{bins[i+1]}'
    count = bin_counts[key]
    pct = count / total * 100
    print(f'{key:>10} | {count:>6} | {pct:>5.1f}%')

nodes_only = [n for _, _, n in node_counts]
print(f'\n平均: {sum(nodes_only)/len(nodes_only):.1f}')
print(f'中位数: {sorted(nodes_only)[len(nodes_only)//2]}')
