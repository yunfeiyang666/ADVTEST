#!/usr/bin/env python3
import json
import pathlib

plan_path = pathlib.Path(__file__).parent.parent / 'deploy' / 'nuscenesqa_val_plan_full.json'
with open(plan_path, 'r', encoding='utf-8') as f:
    plan = json.load(f)

nuscenes_root = pathlib.Path('E:/Project/ADVTEST/data/nuscenes')

with open(nuscenes_root / 'scene.json', 'r') as f:
    scenes = json.load(f)

with open(nuscenes_root / 'sample.json', 'r') as f:
    samples = json.load(f)

scene_dict = {s['name']: s for s in scenes}
sample_dict = {s['token']: s for s in samples}

print(f'统计 {len(plan["frames"])} 帧...')

node_counts = []
for i, frame in enumerate(plan['frames']):
    scene_name = frame['scene_id']
    frame_id = frame['frame_id']

    if scene_name not in scene_dict:
        continue

    scene = scene_dict[scene_name]
    sample_token = scene['first_sample_token']
    for _ in range(frame_id):
        if sample_token not in sample_dict:
            break
        sample = sample_dict[sample_token]
        if sample['next'] == '':
            break
        sample_token = sample['next']

    if sample_token in sample_dict:
        sample = sample_dict[sample_token]
        n_nodes = 1 + len(sample['anns'])
        node_counts.append((scene_name, frame_id, n_nodes))

    if (i + 1) % 500 == 0:
        print(f'{i+1}/{len(plan["frames"])}...')

print(f'\n完成: {len(node_counts)} 帧\n')

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

print('节点区间 | 帧数 | 占比 | 过滤后L2B | 时间/帧')
print('-' * 60)
total = len(node_counts)
for i in range(len(bins)-1):
    key = f'{bins[i]}-{bins[i+1]}'
    count = bin_counts[key]
    pct = count / total * 100
    avg_nodes = (bins[i] + bins[i+1]) / 2
    filtered_nodes = avg_nodes * 0.5
    l2b = int(filtered_nodes * (filtered_nodes - 1))
    time_est = (l2b / 180) * 4
    print(f'{key:>10} | {count:>6} | {pct:>5.1f}% | ~{l2b:>6} | ~{time_est:>4.1f}分')

print('-' * 60)
nodes_only = [n for _, _, n in node_counts]
print(f'平均: {sum(nodes_only)/len(nodes_only):.1f}')
print(f'中位数: {sorted(nodes_only)[len(nodes_only)//2]}')
print(f'\n注意: 过滤后约为原来50%')
