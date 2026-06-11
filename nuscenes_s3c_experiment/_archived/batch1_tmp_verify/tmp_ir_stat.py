import json, re, pathlib

base = pathlib.Path('output/coverage_analysis/vqa_results')
files = [
    'scene-0553_frame8_official_qa.json',
    'scene-0103_frame25_official_qa.json',
    'scene-0103_frame38_official_qa.json',
    'scene-0916_frame8_official_qa.json',
]

questions = []
for fname in files:
    data = json.load(open(base / fname, 'r', encoding='utf-8'))
    for i, r in enumerate(data['results']):
        q = r['question']
        qtype = r['question_type']
        # 粗糙估计关系级数：统计 "to the ... of" 结构数量
        rel_count = len(re.findall(r"to the [a-z ]+ of", q))
        multi_anchor = 1 if ' and the ' in q and 'to the' in q else 0
        questions.append({
            'scene': data['scene_name'],
            'frame': data['frame_idx'],
            'idx': i + 1,
            'question': q,
            'qtype': qtype,
            'rel_phrases': rel_count,
            'multi_anchor': multi_anchor,
        })

for q in questions:
    if q['rel_phrases'] == 0:
        L = 0
    elif q['rel_phrases'] == 1 and not q['multi_anchor']:
        L = 1
    else:
        L = 2
    print(f"[{q['scene']}:{q['frame']}]#{q['idx']:02d} L{L} {q['qtype']:<10} | {q['question']}")
