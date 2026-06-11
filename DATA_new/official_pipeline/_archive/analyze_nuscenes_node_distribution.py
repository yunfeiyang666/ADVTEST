#!/usr/bin/env python3
"""直接从 NuScenes 数据统计节点数分布"""
import json
import pathlib
import sys
import os

devkit_path = pathlib.Path('E:/Project/ADVTEST/nuscenes-devkit/nuscenes-devkit-master/python-sdk')
if devkit_path.exists():
    sys.path.insert(0, str(devkit_path))
from nuscenes.nuscenes import NuScenes

plan_path = pathlib.Path(__file__).parent.parent / 'deploy' / 'nuscenesqa_val_plan_full.json'
with open(plan_path, 'r', encoding='utf-8') as f:
    plan = json.load(f)

nuscenes_root = os.getenv('NUSCENES_DATAROOT', 'E:/Project/ADVTEST/data')
print(f'加载 NuScenes: {nuscenes_root}')
nusc = NuScenes(version='v1.0-trainval', dataroot=nuscenes_root, verbose=False)

print(f'统计 {len(plan["frames"])} 帧...')

node_counts = []
for i, frame in enumerate(plan['frames']):
    scene_name = frame['scene_id']
    frame_id = frame['frame_id']

    scene = None
    for s in nusc.scene:
        if s['name'] == scene_name:
            scene = s
            break

    if not scene:
        continue

    sample_token = scene['first_sample_token']
    for _ in range(frame_id):
        sample = nusc.get('sample', sample_token)
        if sample['next'] == '':
            break
        sample_token = sample['next']

    sample = nusc.get('sample', sample_token)
    n_nodes = 1 + len(sample['anns'])
    node_counts.append((scene_name, frame_id, n_nodes))

    if (i + 1) % 100 == 0:
        print(f'{i+1}/{len(plan["frames"])}...')

print(f'\n统计完成: {len(node_counts)} 帧\n')

bins = [0, 5, 10, 15, 20, 25, 30, 40, 50, 100]
bin_counts = {f'{bins[i]}-{bins[i+1]}': 0 for i in range(len(bins)-1)}
bin_counts['100+'] = 0

for _, _, n in node_counts:
    for i in range(len(bins)-1):
        if bins[i] <= n < bins[i+1]:
            bin_counts[f'{bins[i]}-{bins[i+1]}'] += 1
            break
    else:
        if n >= 100:
            bin_counts['100+'] += 1

print('节点区间 | 帧数 | 占比 | L2B估算 | 时间/帧')
print('-' * 60)
total = len(node_counts)
for i in range(len(bins)-1):
    key = f'{bins[i]}-{bins[i+1]}'
    count = bin_counts[key]
    pct = count / total * 100
    avg_nodes = (bins[i] + bins[i+1]) / 2
    l2b = int(avg_nodes * (avg_nodes - 1))
    time_est = (l2b / 180) * 4
    print(f'{key:>10} | {count:>6} | {pct:>5.1f}% | ~{l2b:>6} | ~{time_est:>4.1f}分')

print('-' * 60)
nodes_only = [n for _, _, n in node_counts]
print(f'平均: {sum(nodes_only)/len(nodes_only):.1f}')
print(f'中位数: {sorted(nodes_only)[len(nodes_only)//2]}')
print(f'\n注意: 过滤后节点数会减少40-60%')
