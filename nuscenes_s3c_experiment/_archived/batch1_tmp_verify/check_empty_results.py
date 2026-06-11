import json

data=json.load(open('output/coverage_analysis/vqa_results/official_qa_pretest_20260124_113950.json', encoding='utf-8'))

# 找出"空结果"案例（包含"未找到"、"0"但期望非0、status题返回0等）
empty_cases = []
for r in data['results']:
    if not r['answer_match']:
        pred = r['predicted_answer']
        exp = r['expected_answer']
        if pred in ['未找到', 'not found', '0'] and exp not in ['0', 'no']:
            empty_cases.append(r)
        elif r['question_type'] == 'status' and pred == '0':
            empty_cases.append(r)

print(f"=== 空结果/未找到案例分析 ({len(empty_cases)}个) ===\n")

for i, r in enumerate(empty_cases, 1):
    print(f"[{i}] {r['question']}")
    print(f"  类型: {r['question_type']}")
    print(f"  期望: {r['expected_answer']} | 预测: {r['predicted_answer']}")
    print(f"  Cypher:")
    for line in r['cypher'].split('\n'):
        print(f"    {line}")
    print()
