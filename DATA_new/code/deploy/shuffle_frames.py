#!/usr/bin/env python3
import json
import random

# 读取 Server 2 和 Server 3 的完整计划
with open('nuscenesqa_val_plan_server2_full.json', encoding='utf-8') as f:
    s2_data = json.load(f)

with open('nuscenesqa_val_plan_server3_full.json', encoding='utf-8') as f:
    s3_data = json.load(f)

# 打乱帧顺序
random.seed(42)  # 固定随机种子，保证可重现
random.shuffle(s2_data['frames'])
random.shuffle(s3_data['frames'])

# 保存打乱后的计划
with open('nuscenesqa_val_plan_server2_full.json', 'w', encoding='utf-8') as f:
    json.dump(s2_data, f, ensure_ascii=False, indent=2)

with open('nuscenesqa_val_plan_server3_full.json', 'w', encoding='utf-8') as f:
    json.dump(s3_data, f, ensure_ascii=False, indent=2)

print("打乱完成：")
print(f"Server 2: {len(s2_data['frames'])} 帧已打乱")
print(f"Server 3: {len(s3_data['frames'])} 帧已打乱")
print()
print("前5帧示例：")
print("Server 2:")
for i, frame in enumerate(s2_data['frames'][:5]):
    print(f"  {i+1}. {frame['scene_id']}/frame-{frame['frame_id']}")
print()
print("Server 3:")
for i, frame in enumerate(s3_data['frames'][:5]):
    print(f"  {i+1}. {frame['scene_id']}/frame-{frame['frame_id']}")
