#!/usr/bin/env python3
"""从过滤后的场景图统计节点分布并生成任务计划"""
import json
import pathlib
import sys
import os
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from advtest_env import load_advtest_env
load_advtest_env()

plan_path = pathlib.Path(__file__).parent.parent / 'deploy' / 'nuscenesqa_val_plan_full.json'
with open(plan_path, 'r', encoding='utf-8') as f:
    plan = json.load(f)

from advtest_paths import FILTERED_SG_DIR
sg_dir = pathlib.Path(FILTERED_SG_DIR)

print(f'场景图目录: {sg_dir}')
print(f'统计 {len(plan["frames"])} 帧...\n')

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

    if (i + 1) % 500 == 0:
        print(f'{i+1}/{len(plan["frames"])}...')

print(f'\n完成: {len(node_counts)} 帧')
print(f'缺失: {missing_count} 帧\n')

if not node_counts:
    print('错误: 没有找到场景图文件！')
    print(f'请确认场景图目录: {sg_dir}')
    sys.exit(1)

bins = [0, 2, 5, 10, 15, 20, 25, 30, 40, 50, 100]
bin_counts = {f'{bins[i]}-{bins[i+1]}': 0 for i in range(len(bins)-1)}
bin_counts['100+'] = 0
bin_frames = {f'{bins[i]}-{bins[i+1]}': [] for i in range(len(bins)-1)}
bin_frames['100+'] = []

for scene, frame, n in node_counts:
    for i in range(len(bins)-1):
        if bins[i] <= n < bins[i+1]:
            key = f'{bins[i]}-{bins[i+1]}'
            bin_counts[key] += 1
            bin_frames[key].append((scene, frame, n))
            break
    else:
        if n >= 100:
            bin_counts['100+'] += 1
            bin_frames['100+'].append((scene, frame, n))

print('节点区间 | 帧数 | 占比')
print('-' * 50)
total = len(node_counts)
for i in range(len(bins)-1):
    key = f'{bins[i]}-{bins[i+1]}'
    count = bin_counts[key]
    pct = count / total * 100
    print(f'{key:>10} | {count:>6} | {pct:>5.1f}%')

print('-' * 50)
nodes_only = [n for _, _, n in node_counts]
print(f'平均: {sum(nodes_only)/len(nodes_only):.1f}')
print(f'中位数: {sorted(nodes_only)[len(nodes_only)//2]}')

# 过滤掉空帧和极小帧（<2节点）
valid_frames = [(s, f, n) for s, f, n in node_counts if n >= 2]
print(f'\n有效帧（>=2节点）: {len(valid_frames)} 帧')

# 重新分组
small_frames = [x for x in valid_frames if 2 <= x[2] < 10]
medium_frames = [x for x in valid_frames if 10 <= x[2] < 20]
large_frames = [x for x in valid_frames if 20 <= x[2] < 35]

print(f'小节点帧(2-10): {len(small_frames)} 帧')
print(f'中节点帧(10-20): {len(medium_frames)} 帧')
print(f'大节点帧(20-35): {len(large_frames)} 帧')

# 三服务器任务分配
server1_frames = small_frames
server2_frames = medium_frames
server3_frames = large_frames[:min(len(large_frames), 500)]

print(f'\n=== 三服务器任务分配（基于过滤后场景图）===')
print(f'Server 1 (小节点2-10): {len(server1_frames)} 帧')
print(f'Server 2 (中节点10-20): {len(server2_frames)} 帧')
print(f'Server 3 (大节点20-35): {len(server3_frames)} 帧')

# 保存三个计划文件
plans = [
    ('server1', server1_frames, '小节点帧（2-10节点，过滤后）'),
    ('server2', server2_frames, '中节点帧（10-20节点，过滤后）'),
    ('server3', server3_frames, '大节点帧（20-35节点，过滤后）')
]

for server_name, frames, desc in plans:
    plan = {
        'description': desc,
        'n_frames': len(frames),
        'frames': [
            {'scene_id': s, 'frame_id': f, 'sg_filename': f'{s}_frame{f}_scene_graph.json'}
            for s, f, _ in frames
        ]
    }
    out = pathlib.Path(__file__).parent.parent / 'deploy' / f'nuscenesqa_val_plan_{server_name}.json'
    with open(out, 'w', encoding='utf-8') as fp:
        json.dump(plan, fp, indent=2, ensure_ascii=False)
    print(f'已保存 {server_name}: {out}')
