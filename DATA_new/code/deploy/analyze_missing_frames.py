#!/usr/bin/env python3
import json

# 读取所有计划
full = set()
with open('nuscenesqa_val_plan_full.json', encoding='utf-8') as f:
    full_data = json.load(f)
    for frame in full_data['frames']:
        full.add((frame['scene_id'], frame['frame_id']))

s1 = set()
with open('nuscenesqa_val_plan_server1.json', encoding='utf-8') as f:
    for frame in json.load(f)['frames']:
        s1.add((frame['scene_id'], frame['frame_id']))

s2 = set()
with open('nuscenesqa_val_plan_server2.json', encoding='utf-8') as f:
    for frame in json.load(f)['frames']:
        s2.add((frame['scene_id'], frame['frame_id']))

s3 = set()
with open('nuscenesqa_val_plan_server3.json', encoding='utf-8') as f:
    for frame in json.load(f)['frames']:
        s3.add((frame['scene_id'], frame['frame_id']))

# 找出未分配的帧
assigned = s1 | s2 | s3
missing = full - assigned

print(f'Full: {len(full)} frames')
print(f'Assigned: {len(assigned)} frames')
print(f'Missing: {len(missing)} frames')
print(f'\nFirst 20 missing frames:')
for i, (scene, frame) in enumerate(sorted(missing)[:20]):
    print(f'  {scene}/frame-{frame}')

# 创建缺失帧的计划文件
missing_frames = []
for frame_data in full_data['frames']:
    key = (frame_data['scene_id'], frame_data['frame_id'])
    if key in missing:
        missing_frames.append(frame_data)

output = {
    "description": "补齐帧（超大节点，40+节点）",
    "n_frames": len(missing_frames),
    "frames": missing_frames
}

with open('nuscenesqa_val_plan_server4.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f'\nCreated: nuscenesqa_val_plan_server4.json ({len(missing_frames)} frames)')
