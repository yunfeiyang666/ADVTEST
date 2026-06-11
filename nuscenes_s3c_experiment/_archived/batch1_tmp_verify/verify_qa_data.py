"""验证官方QA数据与场景图数据是否一致"""
import json
import os

# 1. 加载官方QA数据
qa_path = 'E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json'
with open(qa_path, 'r') as f:
    qa_data = json.load(f)

print("=" * 60)
print("  官方QA数据分析")
print("=" * 60)

# 检查数据结构
print(f"\n数据类型: {type(qa_data)}")
if isinstance(qa_data, dict):
    print(f"Keys: {list(qa_data.keys())[:10]}")
    # 取第一个场景看结构
    first_key = list(qa_data.keys())[0]
    print(f"\n第一个场景 ({first_key}):")
    print(json.dumps(qa_data[first_key][:2] if isinstance(qa_data[first_key], list) else qa_data[first_key], indent=2, ensure_ascii=False)[:500])

# 2. 找到scene-0553的QA
print("\n" + "=" * 60)
print("  scene-0553 相关QA")
print("=" * 60)

scene_553_qa = None
for key in qa_data.keys():
    if '553' in key or 'scene-0553' in str(key):
        scene_553_qa = qa_data[key]
        print(f"\n找到scene key: {key}")
        break

if scene_553_qa is None:
    # 可能key格式不同，尝试其他方式
    print("\n尝试其他方式查找...")
    for key in list(qa_data.keys())[:5]:
        print(f"  Sample key: {key}")

# 3. 查找包含trailer和bicycle的问题
print("\n" + "=" * 60)
print("  包含 trailer + bicycle 的问题")
print("=" * 60)

count = 0
for scene_key, questions in qa_data.items():
    if not isinstance(questions, list):
        continue
    for q in questions:
        if isinstance(q, dict) and 'question' in q:
            qtext = q['question'].lower()
            if 'trailer' in qtext and 'bicycle' in qtext:
                print(f"\nScene: {scene_key}")
                print(f"Q: {q['question']}")
                print(f"A: {q.get('answer', 'N/A')}")
                count += 1
                if count >= 5:
                    break
    if count >= 5:
        break

# 4. 找到测试中失败的具体问题
print("\n" + "=" * 60)
print("  查找失败问题的官方答案")
print("=" * 60)

failed_questions = [
    "There is a trailer; is it the same status as the truck to the back right of the with rider bicycle?",
    "Does the trailer have the same status as the truck to the back right of the bicycle?",
    "What number of other things are there of the same status as the trailer?",
    "What status is the truck to the back of the moving truck?",
]

for fq in failed_questions:
    print(f"\n查找: {fq[:60]}...")
    found = False
    for scene_key, questions in qa_data.items():
        if not isinstance(questions, list):
            continue
        for q in questions:
            if isinstance(q, dict) and q.get('question', '') == fq:
                print(f"  Scene: {scene_key}")
                print(f"  Answer: {q.get('answer', 'N/A')}")
                # 如果有其他元数据也打印
                for k, v in q.items():
                    if k not in ['question', 'answer']:
                        print(f"  {k}: {v}")
                found = True
                break
        if found:
            break
    if not found:
        print("  未找到完全匹配")
