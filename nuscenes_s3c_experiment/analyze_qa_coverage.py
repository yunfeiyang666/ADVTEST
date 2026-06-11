"""
分析官方QA数据集的覆盖范围
解答：为什么有些场景没有问题？83337个问题对应多少场景？
"""
import json
from collections import defaultdict

print("=" * 70)
print("  NuScenes官方QA数据集覆盖范围分析")
print("=" * 70)

# 加载官方QA
qa_file = "E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json"
print(f"\n加载: {qa_file}")

with open(qa_file, 'r', encoding='utf-8') as f:
    qa_data = json.load(f)

questions_list = qa_data['questions']
print(f"  总问题数: {len(questions_list)}")

# 按sample_token统计
qa_by_sample = defaultdict(list)
for qa in questions_list:
    sample_token = qa['sample_token']
    qa_by_sample[sample_token].append(qa)

print(f"\n【覆盖的场景/帧数】")
print(f"  唯一sample数量: {len(qa_by_sample)} 个")
print(f"  平均每个sample: {len(questions_list) / len(qa_by_sample):.1f} 个问题")

# 统计问题数量分布
question_counts = [len(qas) for qas in qa_by_sample.values()]
question_counts.sort(reverse=True)

print(f"\n【问题数量分布】")
print(f"  最多问题的sample: {question_counts[0]} 个")
print(f"  最少问题的sample: {question_counts[-1]} 个")
print(f"  中位数: {question_counts[len(question_counts)//2]} 个")

print(f"\n前10个sample的问题数:")
for i, count in enumerate(question_counts[:10], 1):
    print(f"  {i}. {count} 个")

print(f"\n后10个sample的问题数:")
for i, count in enumerate(question_counts[-10:], 1):
    print(f"  {len(question_counts)-10+i}. {count} 个")

# 统计问题类型
print(f"\n【问题类型统计】")
type_count = defaultdict(int)
for qa in questions_list:
    type_count[qa['template_type']] += 1

print(f"  总类型数: {len(type_count)}")
for qtype, count in sorted(type_count.items(), key=lambda x: -x[1]):
    print(f"  {qtype}: {count} ({count/len(questions_list)*100:.1f}%)")

# 检查我们的6个场景
print(f"\n" + "=" * 70)
print("  我们的6个场景为什么有些没问题？")
print("=" * 70)

# 加载NuScenes mini
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)
from nuscenes.nuscenes import NuScenes

print("\n加载NuScenes v1.0-mini...")
nusc = NuScenes(version='v1.0-mini', dataroot=config.NUSCENES_DATAROOT, verbose=False)

print(f"  v1.0-mini场景数: {len(nusc.scene)}")

# 检查mini中有多少sample有QA
mini_samples_with_qa = 0
mini_total_samples = 0

for scene in nusc.scene:
    sample_token = scene['first_sample_token']
    while sample_token:
        mini_total_samples += 1
        sample = nusc.get('sample', sample_token)
        if sample_token in qa_by_sample:
            mini_samples_with_qa += 1
        sample_token = sample['next']

print(f"\nv1.0-mini统计:")
print(f"  总sample数: {mini_total_samples}")
print(f"  有QA的sample数: {mini_samples_with_qa}")
print(f"  覆盖率: {mini_samples_with_qa/mini_total_samples*100:.1f}%")

print(f"\n" + "=" * 70)
print("  结论")
print("=" * 70)
print(f"""
1. 官方QA验证集有 83,337 个问题
2. 这些问题覆盖 {len(qa_by_sample)} 个不同的sample（场景帧）
3. 平均每个sample有 {len(questions_list) / len(qa_by_sample):.1f} 个问题
4. v1.0-mini只有 {mini_total_samples} 个sample
5. 其中只有 {mini_samples_with_qa} 个sample有官方QA（覆盖率 {mini_samples_with_qa/mini_total_samples*100:.1f}%）

【为什么scene-0757和scene-1077没有问题？】
答：官方QA数据集并非覆盖所有场景，只覆盖了v1.0-mini中部分有代表性的场景。
这两个场景可能不在官方QA的测试范围内。

【83,337个问题怎么来的？】
答：官方QA覆盖了 {len(qa_by_sample)} 个不同的sample，这些可能来自：
   - v1.0-trainval完整数据集（约850个场景）
   - 而不是v1.0-mini（只有10个场景）
   - 每个sample平均生成约 {len(questions_list) / len(qa_by_sample):.1f} 个问题
""")
