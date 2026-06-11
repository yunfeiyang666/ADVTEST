"""分析Q5和Q11的原始QA数据"""
import json

# 加载官方QA
with open('E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json', 'r') as f:
    data = json.load(f)

target_sample = "6dabc0fb1df045558f802246dd186b3f"

print("=" * 80)
print("Sample token:", target_sample)
print("=" * 80)

# 找到该sample的所有问题
sample_questions = [q for q in data['questions'] if q['sample_token'] == target_sample]

print(f"\n该sample共有 {len(sample_questions)} 个问题\n")

# 找Q5相关问题
print("=" * 80)
print("Q5相关: 查找包含 'same status as the trailer' 的问题")
print("=" * 80)
for q in sample_questions:
    if 'same status' in q['question'].lower() and 'trailer' in q['question'].lower():
        print(f"\nQuestion: {q['question']}")
        print(f"Answer: {q['answer']}")
        print(f"Type: {q['template_type']}")
        print(f"Hops: {q['num_hop']}")

# 找Q11相关问题
print("\n" + "=" * 80)
print("Q11相关: 查找包含 'front left' 和 'trailer' 的问题")
print("=" * 80)
for q in sample_questions:
    if 'front left' in q['question'].lower() and 'trailer' in q['question'].lower():
        print(f"\nQuestion: {q['question']}")
        print(f"Answer: {q['answer']}")
        print(f"Type: {q['template_type']}")
        print(f"Hops: {q['num_hop']}")

# 找Q11更宽泛的搜索
print("\n" + "=" * 80)
print("Q11更宽泛: 查找包含 'bicycle' 和 'trailer' 的问题")
print("=" * 80)
for q in sample_questions:
    if 'bicycle' in q['question'].lower() and 'trailer' in q['question'].lower():
        print(f"\nQuestion: {q['question']}")
        print(f"Answer: {q['answer']}")
        print(f"Type: {q['template_type']}")

# 查看所有包含 "number of other things" 的问题
print("\n" + "=" * 80)
print("Q5精确搜索: 'number of other things' 的问题")
print("=" * 80)
for q in sample_questions:
    if 'number of other things' in q['question'].lower():
        print(f"\nQuestion: {q['question']}")
        print(f"Answer: {q['answer']}")
        print(f"Type: {q['template_type']}")
        print(f"Hops: {q['num_hop']}")

# 查看所有count_same_status类型的问题
print("\n" + "=" * 80)
print("所有count相关问题")
print("=" * 80)
for q in sample_questions:
    if q['template_type'] == 'count':
        print(f"\nQ: {q['question']}")
        print(f"A: {q['answer']}")
