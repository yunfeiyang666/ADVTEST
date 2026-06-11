"""找出scene-0553的所有官方QA问题"""
import json

# 加载官方QA数据
qa_path = 'E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json'
with open(qa_path, 'r') as f:
    qa_data = json.load(f)

# 加载scene信息 (从之前58题测试可以推断)
# 首先找出所有包含 scene-0553 关键词的sample_token

print("=" * 60)
print("  查找包含 trailer + bicycle 相关的问题")
print("=" * 60)

# 找出测试用例中的问题
test_questions = [
    "There is a trailer; is it the same status as the truck to the back right of the with rider bicycle?",
    "Does the trailer have the same status as the truck to the back right of the bicycle?",
    "What number of other things are there of the same status as the trailer?",
    "What status is the truck to the back of the moving truck?",
]

# 收集这些问题对应的sample_token
sample_tokens = {}
for q in qa_data['questions']:
    for tq in test_questions:
        if q['question'] == tq:
            token = q['sample_token']
            if token not in sample_tokens:
                sample_tokens[token] = []
            sample_tokens[token].append({
                'question': q['question'][:50] + '...',
                'answer': q['answer']
            })

print(f"\n这些问题来自 {len(sample_tokens)} 个不同的 sample_token:")
for token, questions in sample_tokens.items():
    print(f"\n{token}:")
    for q in questions:
        print(f"  Q: {q['question']}")
        print(f"  A: {q['answer']}")

# 现在查看这些token是否属于同一个场景
print("\n" + "=" * 60)
print("  查找同一个sample_token的所有问题")
print("=" * 60)

# 取Q3/Q4的token深入分析
token_q3 = '6dabc0fb1df045558f802246dd186b3f'
print(f"\ntoken: {token_q3}")
print(f"该token的所有问题:")

questions_for_token = [q for q in qa_data['questions'] if q['sample_token'] == token_q3]
print(f"共 {len(questions_for_token)} 个问题\n")

# 打印与trailer/truck/bicycle相关的问题
for q in questions_for_token:
    qtext = q['question'].lower()
    if 'trailer' in qtext or 'truck' in qtext or 'bicycle' in qtext:
        print(f"Q: {q['question']}")
        print(f"A: {q['answer']}")
        print()
