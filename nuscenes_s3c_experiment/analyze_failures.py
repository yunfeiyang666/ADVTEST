import json
from collections import defaultdict

# 读取结果 - 使用最新的结果
import os
import glob

result_files = glob.glob('output/coverage_analysis/vqa_results/official_qa_pretest_*.json')
latest_file = max(result_files, key=os.path.getmtime)
print(f"使用文件: {latest_file}\n")

with open(latest_file, encoding='utf-8') as f:
    data = json.load(f)

# 分类失败案例
failed = [r for r in data['results'] if not r['answer_match']]
print(f"=== 失败案例分析 ===")
print(f"总失败数: {len(failed)}/58\n")

# 分类
categories = {
    'empty_result': [],  # Cypher正确但返回空结果
    'semantic_ambiguity': [],  # 语义歧义(parked/stopped等)
    'cypher_logic_error': [],  # Cypher逻辑错误
    'llm_output_error': [],  # LLM输出失败
    'other': []
}

for r in failed:
    q = r['question']
    exp = r['expected_answer']
    pred = r['predicted_answer']
    cypher = r.get('cypher', '')
    
    # 分类逻辑
    if not cypher or not r['success']:
        categories['llm_output_error'].append(r)
    elif pred in ['未找到', '0', 'not found'] and exp not in ['0', 'no']:
        categories['empty_result'].append(r)
    elif ('parked' in exp or 'stopped' in exp) and (pred in ['stopped', 'parked'] and exp in ['stopped', 'parked']):
        categories['semantic_ambiguity'].append(r)
    elif 'without rider' in exp and pred == 'without_rider':
        categories['semantic_ambiguity'].append(r)
    else:
        categories['cypher_logic_error'].append(r)

# 输出分类结果
print("【1】空结果问题 (Cypher正确但数据缺失):")
print(f"数量: {len(categories['empty_result'])}")
for r in categories['empty_result']:
    print(f"  - {r['question'][:50]}... | 期望:{r['expected_answer']}")
print()

print("【2】语义歧义 (parked/stopped混淆、空格问题):")
print(f"数量: {len(categories['semantic_ambiguity'])}")
for r in categories['semantic_ambiguity']:
    print(f"  - {r['question'][:50]}... | 期望:{r['expected_answer']} 预测:{r['predicted_answer']}")
print()

print("【3】Cypher逻辑错误:")
print(f"数量: {len(categories['cypher_logic_error'])}")
for r in categories['cypher_logic_error']:
    print(f"  - {r['question'][:50]}...")
    print(f"    期望:{r['expected_answer']} 预测:{r['predicted_answer']}")
    print(f"    Cypher: {r.get('cypher', 'N/A')[:100]}...")
print()

print("【4】LLM输出失败:")
print(f"数量: {len(categories['llm_output_error'])}")
for r in categories['llm_output_error']:
    print(f"  - {r['question'][:50]}...")
    if r.get('error'):
        print(f"    错误: {r['error'][:100]}...")
print()

# 按题型统计失败情况
print("【按题型统计失败】:")
by_type = defaultdict(lambda: {'total': 0, 'failed': 0})
for r in data['results']:
    qtype = r['question_type']
    by_type[qtype]['total'] += 1
    if not r['answer_match']:
        by_type[qtype]['failed'] += 1

for qtype, stats in sorted(by_type.items()):
    acc = (stats['total'] - stats['failed']) / stats['total'] * 100
    print(f"  {qtype}: {stats['failed']}/{stats['total']} 失败 (准确率:{acc:.1f}%)")
