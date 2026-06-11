from collections import Counter
import json, re, pathlib

base = pathlib.Path('output/coverage_analysis/vqa_results')
files = [
    'scene-0553_frame8_official_qa.json',
    'scene-0103_frame25_official_qa.json',
    'scene-0103_frame38_official_qa.json',
    'scene-0916_frame8_official_qa.json',
]

stats = Counter()
examples = {}

for fname in files:
    data = json.load(open(base / fname, 'r', encoding='utf-8'))
    for i, r in enumerate(data['results']):
        q = r['question']
        qtype = r['question_type']
        rel_count = len(re.findall(r"to the [a-z ]+ of", q))
        multi_anchor = 1 if ' and the ' in q and 'to the' in q else 0
        if rel_count == 0:
            L = 0
        elif rel_count == 1 and not multi_anchor:
            L = 1
        else:
            L = 2
        stats[(qtype, L)] += 1
        # 保存一个代表性例子
        key = (qtype, L)
        if key not in examples:
            examples[key] = q

print('Counts by (question_type, L):')
for (qt, L), c in sorted(stats.items(), key=lambda x: (x[0][0], x[0][1])):
    print(f"  {qt:10s} L{L}: {c}")

print('\nRepresentative examples:')
for (qt, L), q in sorted(examples.items(), key=lambda x: (x[0][0], x[0][1])):
    print(f"[{qt:10s} L{L}] {q}")
