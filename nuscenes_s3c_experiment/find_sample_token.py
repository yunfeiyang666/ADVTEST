"""查找sample_token对应的scene和frame"""
import json
from nuscenes.nuscenes import NuScenes

# 目标sample_token
target_token = "6dabc0fb1df045558f802246dd186b3f"

# 加载NuScenes
print("加载NuScenes数据集...")
nusc = NuScenes(version='v1.0-trainval', dataroot='E:/Project/ADVTEST/data/nuscenes', verbose=False)

# 查找sample
print(f"\n查找sample_token: {target_token}")
sample = nusc.get('sample', target_token)

# 获取scene信息
scene = nusc.get('scene', sample['scene_token'])
scene_name = scene['name']

# 计算是第几帧
frame_idx = 0
current_token = scene['first_sample_token']
while current_token != target_token:
    current_sample = nusc.get('sample', current_token)
    current_token = current_sample['next']
    frame_idx += 1
    if current_token == '':
        print("ERROR: 未找到目标sample")
        break

print(f"\n=== 结果 ===")
print(f"Sample token: {target_token}")
print(f"Scene: {scene_name}")
print(f"Frame index: {frame_idx}")
print(f"Expected scene graph file: {scene_name}_frame{frame_idx}_scene_graph.json")

# 检查scene-0553的所有sample
print(f"\n\n=== Scene-0553 的所有sample ===")
scene_0553 = None
for s in nusc.scene:
    if s['name'] == 'scene-0553':
        scene_0553 = s
        break

if scene_0553:
    print(f"Scene-0553 token: {scene_0553['token']}")
    current = scene_0553['first_sample_token']
    idx = 0
    while current:
        sample_info = nusc.get('sample', current)
        marker = " <-- TARGET" if current == target_token else ""
        print(f"  Frame {idx}: {current}{marker}")
        current = sample_info['next']
        idx += 1
        if current == '':
            break
else:
    print("未找到scene-0553")
