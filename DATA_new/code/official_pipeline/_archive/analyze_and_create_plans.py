#!/usr/bin/env python3
import json
import pathlib
import sys
import os

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from advtest_env import load_advtest_env
load_advtest_env()

plan_path = pathlib.Path(__file__).parent.parent / 'deploy' / 'nuscenesqa_val_plan_full.json'
with open(plan_path, 'r', encoding='utf-8') as f:
    plan = json.load(f)

from advtest_paths import NUSCENES_DATAROOT
nuscenes_root = pathlib.Path(NUSCENES_DATAROOT) / 'v1.0-trainval'

# 如果路径不存在，尝试本地路径
if not nuscenes_root.exists():
    local_root = pathlib.Path(__file__).parent.parent.parent.parent / 'dataset' / 'Trainval' / 'v1.0-trainval'
    if local_root.exists():
        nuscenes_root = local_root

print(f'加载NuScenes: {nuscenes_root}')

with open(nuscenes_root / 'scene.json', 'r') as f:
    scenes = json.load(f)
with open(nuscenes_root / 'sample.json', 'r') as f:
    samples = json.load(f)
with open(nuscenes_root / 'sample_annotation.json', 'r') as f:
    annotations = json.load(f)

scene_dict = {s['name']: s for s in scenes}
sample_dict = {s['token']: s for s in samples}

# 统计每个sample的annotation数量
from collections import defaultdict
sample_ann_count = defaultdict(int)
for ann in annotations:
    sample_ann_count[ann['sample_token']] += 1

print(f'统计 {len(plan["frames"])} 帧...\n')

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
        n_nodes = 1 + sample_ann_count[sample_token]
        node_counts.append((scene_name, frame_id, n_nodes))

    if (i + 1) % 500 == 0:
        print(f'{i+1}/{len(plan["frames"])}...')

print(f'\n完成: {len(node_counts)} 帧\n')

bins = [0, 10, 15, 20, 25, 30, 40, 50, 100]
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

print('节点区间 | 帧数 | 占比 | L2总量估算 | 预计轮次 | 预计时间/帧')
print('-' * 80)
total = len(node_counts)
for i in range(len(bins)-1):
    key = f'{bins[i]}-{bins[i+1]}'
    count = bin_counts[key]
    pct = count / total * 100
    avg = (bins[i] + bins[i+1]) / 2
    filtered = avg * 0.5

    # L2总量 = L2A + L2B
    # 根据实际场景图：平均每个节点3-4条边
    avg_edges = filtered * 3.5
    # L2A ≈ 边数 * 平均出度
    l2a_est = int(avg_edges * 3)
    # L2B = 节点对数 = n*(n-1)/2
    l2b_est = int(filtered * (filtered - 1) / 2)
    l2_total = l2a_est + l2b_est

    # 预计轮次：基于实际观察
    # - 小节点(<15)：10-20轮
    # - 中节点(15-30)：30-60轮
    # - 大节点(30-50)：80-150轮
    # - 超大节点(50+)：150-200轮
    if l2_total < 200:
        rounds_est = max(10, int(l2_total / 15))
    elif l2_total < 500:
        rounds_est = max(20, int(l2_total / 10))
    elif l2_total < 1500:
        rounds_est = max(40, int(l2_total / 8))
    else:
        rounds_est = max(80, min(200, int(l2_total / 6)))

    # 每轮94题，每题0.7秒
    time_per_round = 94 * 0.7 / 60  # 约1.1分钟
    time_est = rounds_est * time_per_round

    print(f'{key:>10} | {count:>6} | {pct:>5.1f}% | ~{l2_total:>8} | ~{rounds_est:>4}轮 | ~{time_est:>6.0f}分钟')

print('-' * 60)
nodes_only = [n for _, _, n in node_counts]
print(f'平均: {sum(nodes_only)/len(nodes_only):.1f}')
print(f'中位数: {sorted(nodes_only)[len(nodes_only)//2]}\n')

small_frames = bin_frames['0-10'] + bin_frames['10-15']
medium_frames = bin_frames['15-20'] + bin_frames['20-25']
large_frames = bin_frames['25-30'] + bin_frames['30-40']

print(f'\n小节点帧(<15): {len(small_frames)} 帧')
print(f'中节点帧(15-25): {len(medium_frames)} 帧')
print(f'大节点帧(25-40): {len(large_frames)} 帧')

# 计算总工作量（以预计分钟数为单位）
def calc_workload(frames):
    total_time = 0
    for _, _, n in frames:
        filtered = n * 0.5
        avg_edges = filtered * 3.5
        l2a_est = int(avg_edges * 3)
        l2b_est = int(filtered * (filtered - 1) / 2)
        l2_total = l2a_est + l2b_est

        if l2_total < 200:
            rounds_est = max(10, int(l2_total / 15))
        elif l2_total < 500:
            rounds_est = max(20, int(l2_total / 10))
        elif l2_total < 1500:
            rounds_est = max(40, int(l2_total / 8))
        else:
            rounds_est = max(80, min(200, int(l2_total / 6)))

        time_est = rounds_est * 94 * 0.7 / 60
        total_time += time_est
    return total_time

# 三份任务分配策略：
# Server 1: 所有小节点帧 (0-15节点) - 工作量较大但单帧快
# Server 2: 所有中节点帧 (15-25节点) - 工作量较大
# Server 3: 部分大节点帧 (25-40节点) - 工作量稍少但单帧慢

server1_frames = small_frames
server2_frames = medium_frames
server3_frames = large_frames[:600]  # 取前600帧大节点

workload1 = calc_workload(server1_frames)
workload2 = calc_workload(server2_frames)
workload3 = calc_workload(server3_frames)

print(f'\n=== 三服务器任务分配 ===')
print(f'Server 1 (小节点): {len(server1_frames)} 帧, 预计 {workload1/60:.1f} 小时')
print(f'Server 2 (中节点): {len(server2_frames)} 帧, 预计 {workload2/60:.1f} 小时')
print(f'Server 3 (大节点): {len(server3_frames)} 帧, 预计 {workload3/60:.1f} 小时')

# 保存三个计划文件
plans = [
    ('server1', server1_frames, '小节点帧（0-15节点）'),
    ('server2', server2_frames, '中节点帧（15-25节点）'),
    ('server3', server3_frames, '大节点帧（25-40节点，前600帧）')
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
