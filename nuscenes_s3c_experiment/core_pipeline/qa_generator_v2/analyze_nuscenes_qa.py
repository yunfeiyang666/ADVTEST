"""
分析NuScenesQA原题集的问题模式
提取关键的表达方式、句式结构和问题类型
"""
import json
import re
from collections import Counter, defaultdict

# 加载数据
with open(r'E:\Project\ADVTEST\data\nuscenes\qa\NuScenes_val_questions.json', 'r') as f:
    data = json.load(f)

questions = data['questions']

print("="*80)
print("NuScenesQA 问题分析")
print("="*80)
print(f"\n总问题数: {len(questions)}")

# 1. 按类型和跳数统计
print("\n" + "="*80)
print("1. 问题类型 × 跳数分布")
print("="*80)
type_hop_dist = defaultdict(lambda: defaultdict(int))
for q in questions:
    type_hop_dist[q['template_type']][q['num_hop']] += 1

for qtype in sorted(type_hop_dist.keys()):
    print(f"\n{qtype}:")
    for hop in sorted(type_hop_dist[qtype].keys()):
        count = type_hop_dist[qtype][hop]
        print(f"  {hop}-hop: {count:6d}")

# 2. 提取常见问题开头
print("\n" + "="*80)
print("2. 常见问题开头（前20个）")
print("="*80)
question_starts = []
for q in questions:
    # 提取前4-6个词
    words = q['question'].split()
    start = ' '.join(words[:min(6, len(words))])
    question_starts.append(start)

start_counter = Counter(question_starts)
for start, count in start_counter.most_common(20):
    print(f"{count:5d}x  {start}")

# 3. 提取所有唯一问题模式（去掉具体对象）
print("\n" + "="*80)
print("3. 问题模式分析（替换具体词为占位符）")
print("="*80)

def extract_pattern(question):
    """提取问题模式，替换对象类型和状态为占位符"""
    pattern = question
    
    # 替换对象类型
    types = ['car', 'cars', 'pedestrian', 'pedestrians', 'bicycle', 'bicycles', 
             'motorcycle', 'motorcycles', 'truck', 'trucks', 'bus', 'buses',
             'trailer', 'trailers', 'barrier', 'barriers', 'traffic cone', 'traffic cones',
             'construction vehicle', 'construction vehicles', 'thing', 'things']
    for t in sorted(types, key=len, reverse=True):  # 长的先替换
        pattern = pattern.replace(t, '{TYPE}')
    
    # 替换状态
    statuses = ['moving', 'stopped', 'parked', 'standing', 'sitting', 
                'not standing', 'with rider', 'without rider']
    for s in sorted(statuses, key=len, reverse=True):
        pattern = pattern.replace(s, '{STATUS}')
    
    # 替换方向
    directions = ['front left', 'front right', 'back left', 'back right',
                  'front', 'back', 'left', 'right']
    for d in sorted(directions, key=len, reverse=True):
        pattern = pattern.replace(d, '{DIR}')
    
    return pattern

patterns = [extract_pattern(q['question']) for q in questions]
pattern_counter = Counter(patterns)

print("\n按类型分组的模式（前10个）:\n")

for qtype in ['exist', 'count', 'status', 'object', 'comparison']:
    print(f"\n{qtype.upper()} 类型:")
    type_patterns = [extract_pattern(q['question']) 
                     for q in questions if q['template_type'] == qtype]
    type_counter = Counter(type_patterns)
    for pattern, count in type_counter.most_common(10):
        print(f"  {count:4d}x  {pattern}")

# 4. 分析关键短语
print("\n" + "="*80)
print("4. 关键短语分析")
print("="*80)

# 提取"to the X of"模式
to_the_patterns = []
for q in questions:
    matches = re.findall(r'to the (\w+(?:\s+\w+)?) of', q['question'])
    to_the_patterns.extend(matches)

print("\n'to the X of' 模式:")
for phrase, count in Counter(to_the_patterns).most_common(15):
    print(f"  {count:5d}x  to the {phrase} of")

# 提取特殊句式
print("\n特殊句式:")
special_phrases = [
    "There is a",
    "Are there any",
    "How many",
    "What number of",
    "What is",
    "Does",
    "Is there",
    "Are any",
]

for phrase in special_phrases:
    count = sum(1 for q in questions if phrase in q['question'])
    print(f"  {count:5d}x  {phrase}...")

# 5. 提取实际问题示例（每种类型每个跳数）
print("\n" + "="*80)
print("5. 实际问题示例")
print("="*80)

for qtype in ['exist', 'count', 'status', 'object', 'comparison']:
    print(f"\n{qtype.upper()}:")
    for hop in [0, 1]:
        samples = [q for q in questions 
                   if q['template_type'] == qtype and q['num_hop'] == hop]
        if samples:
            print(f"\n  {hop}-hop 示例:")
            for q in samples[:3]:
                print(f"    Q: {q['question']}")
                print(f"    A: {q['answer']}")

print("\n" + "="*80)
