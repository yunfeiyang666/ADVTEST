"""分析失败的方向相关问题"""
import json

# 加载结果
results = json.load(open('output/coverage_analysis/vqa_results/enhanced_qa_test_20260126_140257.json'))

print("="*80)
print("方向相关问题分析 (Source Frame 方法)")
print("="*80)

# 分析每个问题
direction_keywords = ['back', 'front', 'left', 'right']
direction_questions = []
other_questions = []

for r in results['scenes'][0]['results']:
    q = r['question'].lower()
    has_direction = any(kw in q for kw in direction_keywords)
    
    if has_direction:
        direction_questions.append(r)
    else:
        other_questions.append(r)

print(f"\n方向相关问题: {len(direction_questions)} 个")
print(f"非方向问题: {len(other_questions)} 个")

print("\n" + "-"*80)
print("方向相关问题详情:")
print("-"*80)

correct_dir = 0
for r in direction_questions:
    status = "✓" if r['correct'] else "✗"
    if r['correct']:
        correct_dir += 1
    print(f"\n{status} Q: {r['question'][:80]}...")
    print(f"  期望: {r['expected']}")
    print(f"  实际: {r['actual'][:50]}...")
    print(f"  原因: {r['reason']}, 尝试次数: {r['attempts']}")

print(f"\n方向问题正确率: {correct_dir}/{len(direction_questions)} = {100*correct_dir/len(direction_questions):.1f}%")

print("\n" + "-"*80)
print("非方向问题详情:")
print("-"*80)

correct_other = 0
for r in other_questions:
    status = "✓" if r['correct'] else "✗"
    if r['correct']:
        correct_other += 1
    print(f"{status} Q: {r['question'][:60]}... → {r['expected']} / {r['actual'][:20]}")

print(f"\n非方向问题正确率: {correct_other}/{len(other_questions)} = {100*correct_other/len(other_questions):.1f}%")

print("\n" + "="*80)
print("总结")
print("="*80)
print(f"总正确率: {results['correct_count']}/{results['total_questions']} = {100*results['correct_count']/results['total_questions']:.1f}%")
print(f"方向问题正确率: {correct_dir}/{len(direction_questions)} = {100*correct_dir/len(direction_questions):.1f}%")
print(f"非方向问题正确率: {correct_other}/{len(other_questions)} = {100*correct_other/len(other_questions):.1f}%")
