"""
探索NuScenes官方QA数据集
"""
import json
import random

# 加载官方QA数据
qa_file = "E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json"

print("=" * 70)
print("  NuScenes官方QA数据集分析")
print("=" * 70)

with open(qa_file, 'r', encoding='utf-8') as f:
    qa_data = json.load(f)

print(f"\n数据类型: {type(qa_data)}")

if isinstance(qa_data, dict):
    print(f"字典键数量: {len(qa_data.keys())}")
    print(f"\n前10个键:")
    for i, key in enumerate(list(qa_data.keys())[:10]):
        print(f"  {i+1}. {key}")
    
    # 随机选择一个场景查看
    sample_key = list(qa_data.keys())[0]
    print(f"\n【示例场景】: {sample_key}")
    sample_data = qa_data[sample_key]
    
    print(f"\n该场景的数据类型: {type(sample_data)}")
    
    if isinstance(sample_data, list):
        print(f"该场景问题数: {len(sample_data)}")
        print(f"\n前3个问题:")
        for i, qa in enumerate(sample_data[:3], 1):
            print(f"\n问题 {i}:")
            for k, v in qa.items():
                if isinstance(v, str) and len(v) > 100:
                    print(f"  {k}: {v[:100]}...")
                else:
                    print(f"  {k}: {v}")
    elif isinstance(sample_data, dict):
        print(f"\n该场景的字段:")
        for k, v in sample_data.items():
            print(f"  {k}: {type(v)}")

elif isinstance(qa_data, list):
    print(f"列表长度: {len(qa_data)}")
    print(f"\n前3个问题:")
    for i, qa in enumerate(qa_data[:3], 1):
        print(f"\n问题 {i}:")
        for k, v in qa.items():
            print(f"  {k}: {v}")

# 统计问题类型
print("\n" + "=" * 70)
print("  统计分析")
print("=" * 70)

all_questions = []
if isinstance(qa_data, dict):
    for scene_key, questions in qa_data.items():
        if isinstance(questions, list):
            all_questions.extend(questions)
        elif isinstance(questions, dict) and 'questions' in questions:
            all_questions.extend(questions['questions'])

print(f"\n总问题数: {len(all_questions)}")

if all_questions:
    # 分析问题类型
    question_types = {}
    for qa in all_questions[:100]:  # 只看前100个
        if isinstance(qa, dict) and 'question_type' in qa:
            qtype = qa['question_type']
            question_types[qtype] = question_types.get(qtype, 0) + 1
    
    if question_types:
        print(f"\n问题类型分布（前100题）:")
        for qtype, count in sorted(question_types.items(), key=lambda x: -x[1]):
            print(f"  {qtype}: {count}")
    
    # 展示5个完整示例
    print("\n" + "=" * 70)
    print("  完整问题示例")
    print("=" * 70)
    
    sample_questions = random.sample(all_questions, min(5, len(all_questions)))
    for i, qa in enumerate(sample_questions, 1):
        print(f"\n【示例 {i}】")
        if isinstance(qa, dict):
            for k, v in qa.items():
                if isinstance(v, str) and len(v) > 150:
                    print(f"  {k}: {v[:150]}...")
                else:
                    print(f"  {k}: {v}")
        else:
            print(f"  {qa}")
