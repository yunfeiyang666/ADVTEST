#!/usr/bin/env python3
import json

# 读取现有计划
with open('nuscenesqa_val_plan_server1.json', encoding='utf-8') as f:
    s1_data = json.load(f)
    s1_frames = s1_data['frames']

with open('nuscenesqa_val_plan_server2.json', encoding='utf-8') as f:
    s2_data = json.load(f)
    s2_frames = s2_data['frames']

with open('nuscenesqa_val_plan_server3.json', encoding='utf-8') as f:
    s3_data = json.load(f)
    s3_frames = s3_data['frames']

with open('nuscenesqa_val_plan_server4.json', encoding='utf-8') as f:
    s4_data = json.load(f)
    s4_frames = s4_data['frames']

# 分配 server4 的 2954 帧
# Server 1 加 300 帧（最少）
# Server 2 加 800 帧（其次）
# Server 3 加 1854 帧（最多）

s1_add = s4_frames[:300]
s2_add = s4_frames[300:1100]
s3_add = s4_frames[1100:]

# 创建新的计划
new_s1 = {
    "description": "小节点帧（0-15节点）+ 补充超大节点帧",
    "n_frames": len(s1_frames) + len(s1_add),
    "frames": s1_frames + s1_add
}

new_s2 = {
    "description": "中等节点帧（15-25节点）+ 补充超大节点帧",
    "n_frames": len(s2_frames) + len(s2_add),
    "frames": s2_frames + s2_add
}

new_s3 = {
    "description": "大节点帧（25-40节点）+ 补充超大节点帧",
    "n_frames": len(s3_frames) + len(s3_add),
    "frames": s3_frames + s3_add
}

# 保存新计划
with open('nuscenesqa_val_plan_server1_full.json', 'w', encoding='utf-8') as f:
    json.dump(new_s1, f, ensure_ascii=False, indent=2)

with open('nuscenesqa_val_plan_server2_full.json', 'w', encoding='utf-8') as f:
    json.dump(new_s2, f, ensure_ascii=False, indent=2)

with open('nuscenesqa_val_plan_server3_full.json', 'w', encoding='utf-8') as f:
    json.dump(new_s3, f, ensure_ascii=False, indent=2)

print("重新分配完成：")
print(f"Server 1: {len(s1_frames)} + {len(s1_add)} = {new_s1['n_frames']} 帧")
print(f"Server 2: {len(s2_frames)} + {len(s2_add)} = {new_s2['n_frames']} 帧")
print(f"Server 3: {len(s3_frames)} + {len(s3_add)} = {new_s3['n_frames']} 帧")
print(f"总计: {new_s1['n_frames'] + new_s2['n_frames'] + new_s3['n_frames']} 帧")
print()
print("已创建:")
print("  nuscenesqa_val_plan_server1_full.json")
print("  nuscenesqa_val_plan_server2_full.json")
print("  nuscenesqa_val_plan_server3_full.json")
