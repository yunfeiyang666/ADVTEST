"""验证sample_token与场景/帧的对应关系"""
import json
import os
import sys
sys.path.insert(0, 'E:/Project/ADVTEST/nuscenes_s3c_experiment')

# 加载nuscenes
from nuscenes.nuscenes import NuScenes
nusc = NuScenes(version='v1.0-trainval', dataroot='E:/Project/ADVTEST/data/nuscenes', verbose=False)

# 目标sample_tokens
target_tokens = [
    '6dabc0fb1df045558f802246dd186b3f',  # Q3/Q4
    '9577cf1a1f31414d90358bd7b104b615',  # Q5  
    '73620d31303a47f9a86908f6157370f9',  # Q7
]

print("=" * 60)
print("  验证 sample_token 对应的场景和帧")
print("=" * 60)

for token in target_tokens:
    try:
        sample = nusc.get('sample', token)
        scene = nusc.get('scene', sample['scene_token'])
        
        # 计算帧索引
        frame_idx = 0
        current_token = scene['first_sample_token']
        while current_token != token:
            sample_tmp = nusc.get('sample', current_token)
            current_token = sample_tmp['next']
            frame_idx += 1
            if frame_idx > 50:  # 防止死循环
                break
        
        print(f"\nsample_token: {token[:16]}...")
        print(f"  scene: {scene['name']}")
        print(f"  frame: {frame_idx}")
        print(f"  description: {scene['description'][:50]}...")
    except Exception as e:
        print(f"\nsample_token: {token[:16]}...")
        print(f"  Error: {e}")

# 检查 scene-0553 frame 8 的 sample_token
print("\n" + "=" * 60)
print("  scene-0553 frame 8 的 sample_token")
print("=" * 60)

for scene in nusc.scene:
    if scene['name'] == 'scene-0553':
        print(f"\n场景: {scene['name']}")
        print(f"描述: {scene['description']}")
        
        # 找到第8帧
        current_token = scene['first_sample_token']
        for i in range(9):  # 0-8，共9帧
            sample = nusc.get('sample', current_token)
            if i == 8:
                print(f"\nFrame 8 sample_token: {current_token}")
                
                # 检查这个token对应的QA
                qa_path = 'E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json'
                with open(qa_path, 'r') as f:
                    qa_data = json.load(f)
                
                qa_for_frame = [q for q in qa_data['questions'] if q.get('sample_token') == current_token]
                print(f"该帧有 {len(qa_for_frame)} 个QA问题")
                
                # 列出部分问题
                for q in qa_for_frame[:5]:
                    print(f"  Q: {q['question'][:60]}...")
                    print(f"  A: {q['answer']}")
                break
            
            if sample['next'] == '':
                print(f"场景只有 {i+1} 帧")
                break
            current_token = sample['next']
        break
