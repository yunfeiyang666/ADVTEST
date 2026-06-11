"""比较两次测试结果"""
import json

old = json.load(open('output/coverage_analysis/vqa_results/enhanced_qa_test_20260126_140257.json'))
new = json.load(open('output/coverage_analysis/vqa_results/enhanced_qa_test_20260126_160643.json'))

print("="*70)
print("两次测试结果对比")
print("="*70)
print(f"旧结果(14:02): {old['correct_count']}/{old['total_questions']} = {100*old['correct_count']/old['total_questions']:.1f}%")
print(f"新结果(16:06): {new['correct_count']}/{new['total_questions']} = {100*new['correct_count']/new['total_questions']:.1f}%")

print("\n" + "-"*70)
print("详细对比:")
print("-"*70)

old_results = {r['question'][:50]: r for r in old['scenes'][0]['results']}
new_results = {r['question'][:50]: r for r in new['scenes'][0]['results']}

changed = []
for key in old_results:
    old_r = old_results[key]
    new_r = new_results.get(key)
    if new_r:
        if old_r['correct'] != new_r['correct']:
            changed.append((key, old_r, new_r))

print(f"\n变化的问题 ({len(changed)} 个):")
for key, old_r, new_r in changed:
    old_status = "✓" if old_r['correct'] else "✗"
    new_status = "✓" if new_r['correct'] else "✗"
    print(f"\n  Q: {key}...")
    print(f"    期望: {old_r['expected']}")
    print(f"    旧: {old_status} → {old_r['actual'][:30]}")
    print(f"    新: {new_status} → {new_r['actual'][:30]}")
