import json

with open('output/coverage_analysis/vqa_results/official_qa_pretest_20260124_103838.json', encoding='utf-8') as f:
    data = json.load(f)

# 找出Cypher逻辑错误的案例
logic_errors = []
for r in data['results']:
    if not r['answer_match'] and r['success']:
        pred = r['predicted_answer']
        exp = r['expected_answer']
        # 排除空结果和语义歧义
        if pred not in ['未找到', '0', 'not found'] or exp in ['0', 'no']:
            if not (('parked' in exp or 'stopped' in exp) and pred in ['stopped', 'parked']):
                if not ('without rider' in exp and pred == 'without_rider'):
                    logic_errors.append(r)

print(f"=== Cypher逻辑错误详细分析 ({len(logic_errors)}题) ===\n")

for i, r in enumerate(logic_errors, 1):
    print(f"【错误{i}】")
    print(f"问题: {r['question']}")
    print(f"期望: {r['expected_answer']} | 预测: {r['predicted_answer']}")
    print(f"题型: {r['question_type']}")
    print(f"\nCypher:\n{r['cypher']}")
    print("\n" + "="*80 + "\n")
