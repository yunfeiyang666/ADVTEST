"""查找trailer相关的QA问题"""
import json

with open('E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json', 'r') as f:
    data = json.load(f)

print("=== Trailer + same status 相关问题 ===")
for i, q in enumerate(data['questions']):
    if 'trailer' in q['question'].lower() and 'same status' in q['question'].lower():
        print(f"Index: {i}")
        print(f"Sample: {q['sample_token']}")
        print(f"Q: {q['question']}")
        print(f"A: {q['answer']}")
        print(f"Type: {q['template_type']}, Hops: {q['num_hop']}")
        print()

print("\n=== Trailer + back of bicycle 相关问题 ===")
for i, q in enumerate(data['questions']):
    if 'trailer' in q['question'].lower() and 'back' in q['question'].lower() and 'bicycle' in q['question'].lower():
        print(f"Index: {i}")
        print(f"Sample: {q['sample_token']}")
        print(f"Q: {q['question']}")
        print(f"A: {q['answer']}")
        print()

# 检查是否有关于这个sample的其他问题
target_sample = "6dabc0fb1df045558f802246dd186b3f"
print(f"\n=== Sample {target_sample[:16]}... 的所有问题 ===")
for i, q in enumerate(data['questions']):
    if q['sample_token'] == target_sample:
        print(f"Index: {i}")
        print(f"Q: {q['question']}")
        print(f"A: {q['answer']}")
        print(f"Type: {q['template_type']}, Hops: {q['num_hop']}")
        print()
