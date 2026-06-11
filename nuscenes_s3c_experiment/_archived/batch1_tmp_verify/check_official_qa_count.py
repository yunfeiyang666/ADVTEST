"""
检查6个场景分别有多少官方QA问题
"""
import os
import sys
import json
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# 加载NuScenes
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)
from nuscenes.nuscenes import NuScenes

def get_sample_token(nusc, scene_name, frame_idx):
    """获取sample_token"""
    for scene in nusc.scene:
        if scene['name'] == scene_name:
            sample_token = scene['first_sample_token']
            current_frame = 0
            
            while sample_token and current_frame < frame_idx:
                sample = nusc.get('sample', sample_token)
                sample_token = sample['next']
                current_frame += 1
            
            if sample_token:
                return sample_token
    return None

print("=" * 70)
print("  检查6个场景的官方QA问题数量")
print("=" * 70)

# 加载NuScenes
print("\n加载NuScenes...")
nusc = NuScenes(version='v1.0-mini', dataroot=config.NUSCENES_DATAROOT, verbose=False)

# 加载官方QA
print("加载官方QA数据...")
qa_file = "E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json"
with open(qa_file, 'r', encoding='utf-8') as f:
    qa_data = json.load(f)

questions_list = qa_data['questions']
print(f"  总问题数: {len(questions_list)}")

# 按sample_token索引
qa_by_sample = defaultdict(list)
for qa in questions_list:
    sample_token = qa['sample_token']
    qa_by_sample[sample_token].append(qa)

# 加载我们的6个场景
manifest_path = os.path.join(
    config.OUTPUT_DIR, "coverage_analysis", "scene_graphs", "manifest.json"
)

with open(manifest_path, 'r', encoding='utf-8') as f:
    scenes = json.load(f)

print("\n" + "=" * 70)
print("  6个场景的官方QA问题统计")
print("=" * 70)

total_questions = 0
scene_stats = []

for i, scene_info in enumerate(scenes, 1):
    scene_name = scene_info['scene_name']
    frame_idx = scene_info['frame_idx']
    
    # 获取sample_token
    sample_token = get_sample_token(nusc, scene_name, frame_idx)
    
    if sample_token:
        qa_list = qa_by_sample.get(sample_token, [])
        num_questions = len(qa_list)
        total_questions += num_questions
        
        # 统计问题类型
        type_count = defaultdict(int)
        for qa in qa_list:
            type_count[qa['template_type']] += 1
        
        scene_stats.append({
            'idx': i,
            'scene_name': scene_name,
            'frame_idx': frame_idx,
            'sample_token': sample_token,
            'num_questions': num_questions,
            'type_count': dict(type_count)
        })
        
        print(f"\n[{i}] {scene_name} 帧{frame_idx}")
        print(f"    Sample Token: {sample_token}")
        print(f"    问题数: {num_questions}")
        if num_questions > 0:
            print(f"    问题类型分布:")
            for qtype, count in sorted(type_count.items(), key=lambda x: -x[1]):
                print(f"      {qtype}: {count}")
    else:
        print(f"\n[{i}] {scene_name} 帧{frame_idx}")
        print(f"    ❌ 未找到sample_token")
        scene_stats.append({
            'idx': i,
            'scene_name': scene_name,
            'frame_idx': frame_idx,
            'num_questions': 0
        })

print("\n" + "=" * 70)
print("  总结")
print("=" * 70)
print(f"\n总问题数: {total_questions}")
print(f"平均每场景: {total_questions / len(scenes):.1f} 个问题")

# 分组统计
print("\n【按组统计】")
print("\n组1 (低-中-高):")
group1_total = sum(s['num_questions'] for s in scene_stats[:3])
for s in scene_stats[:3]:
    print(f"  {s['scene_name']}: {s['num_questions']} 个")
print(f"  组1合计: {group1_total} 个")

print("\n组2 (低-中-高):")
group2_total = sum(s['num_questions'] for s in scene_stats[3:])
for s in scene_stats[3:]:
    print(f"  {s['scene_name']}: {s['num_questions']} 个")
print(f"  组2合计: {group2_total} 个")

print("\n" + "=" * 70)
print("  建议")
print("=" * 70)

if total_questions <= 500:
    print(f"\n✅ 总问题数 {total_questions} 个，建议测试全部6个场景")
elif group1_total <= 300 or group2_total <= 300:
    if group1_total < group2_total:
        print(f"\n✅ 建议测试组1（{group1_total} 个问题）")
    else:
        print(f"\n✅ 建议测试组2（{group2_total} 个问题）")
else:
    print(f"\n⚠️  问题总数较多，建议:")
    print(f"    1. 测试一个组的全部问题")
    print(f"    2. 或每个场景测试前50个问题")
