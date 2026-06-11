"""
NuScenesQA 官方题集完整四级分类分析
============================================
第一级 (L): 跳数层级 L0(0-hop) / L1(1-hop)
第二级 (Category): 5种问题类型 exist/count/status/object/comparison
第三级 (Direction): 每种类型下的不同提问方向（结构模式）
第四级 (Variant): 每种方向的语义表达变体

目标：不重不漏，穷举所有模式
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

# ============================================================
# 1. 加载数据
# ============================================================
DATA_PATH = r'E:\Project\ADVTEST\data\nuscenes\qa\NuScenes_val_questions.json'
OUTPUT_DIR = Path(__file__).parent

with open(DATA_PATH, 'r') as f:
    data = json.load(f)

questions = data['questions']
print(f"总问题数: {len(questions)}")

# ============================================================
# 2. 模式提取函数
# ============================================================
# 对象类型（长的先替换，避免子串误替换）
TYPES = sorted([
    'car', 'cars', 'pedestrian', 'pedestrians', 'bicycle', 'bicycles',
    'motorcycle', 'motorcycles', 'truck', 'trucks', 'bus', 'buses',
    'trailer', 'trailers', 'barrier', 'barriers', 'traffic cone', 'traffic cones',
    'construction vehicle', 'construction vehicles', 'thing', 'things'
], key=len, reverse=True)

# 状态
STATUSES = sorted([
    'moving', 'stopped', 'parked', 'standing', 'sitting',
    'not standing', 'with rider', 'without rider'
], key=len, reverse=True)

# 方向（组合方向先替换）
DIRECTIONS = sorted([
    'front left', 'front right', 'back left', 'back right',
    'front', 'back', 'left', 'right'
], key=len, reverse=True)


def extract_pattern(question: str) -> str:
    """提取问题的结构模式，将具体词替换为占位符"""
    p = question
    for t in TYPES:
        p = p.replace(t, '{TYPE}')
    for s in STATUSES:
        p = p.replace(s, '{STATUS}')
    for d in DIRECTIONS:
        p = p.replace(d, '{DIR}')
    return p


def classify_direction(qtype: str, pattern: str) -> str:
    """
    将模式归类为提问方向（第三级）
    同一个提问方向下，不同的语言表达是第四级变体
    """
    p = pattern.lower()

    if qtype == 'exist':
        # ---- EXIST: 是否存在 ----
        if 'same status' in p:
            if 'to the {dir}' in p:
                return 'exist_same_status_directional'
            return 'exist_same_status_global'
        if 'to the {dir} of me' in p:
            return 'exist_type_near_ego'
        if 'to the {dir} of' in p:
            return 'exist_type_near_obj'
        if '{status}' in p and '{type}' in p:
            return 'exist_status_type_global'
        if '{type}' in p:
            return 'exist_type_global'
        return 'exist_other'

    elif qtype == 'count':
        # ---- COUNT: 数量统计 ----
        if 'same status' in p:
            if 'to the {dir}' in p:
                return 'count_same_status_directional'
            return 'count_same_status_global'
        if 'to the {dir} of me' in p:
            return 'count_type_near_ego'
        if 'to the {dir} of' in p:
            return 'count_type_near_obj'
        if '{status}' in p and '{type}' in p:
            return 'count_status_type_global'
        if '{type}' in p:
            return 'count_type_global'
        return 'count_other'

    elif qtype == 'status':
        # ---- STATUS: 查询状态 ----
        if 'to the {dir} of me' in p:
            return 'status_of_obj_near_ego'
        if 'to the {dir} of' in p:
            return 'status_of_obj_near_obj'
        return 'status_of_obj_global'

    elif qtype == 'object':
        # ---- OBJECT: 查询对象类型 ----
        if 'both to the' in p or ('to the {dir} of' in p and p.count('to the {dir} of') >= 2):
            return 'object_multi_constraint'
        if 'to the {dir} of me' in p:
            return 'object_near_ego'
        if 'to the {dir} of' in p:
            return 'object_near_obj'
        return 'object_global'

    elif qtype == 'comparison':
        # ---- COMPARISON: 状态比较 ----
        if p.count('to the {dir} of') >= 2:
            return 'comparison_both_directional'
        if 'to the {dir} of' in p:
            return 'comparison_one_directional'
        return 'comparison_global'

    return f'{qtype}_other'


# ============================================================
# 3. 分析所有问题
# ============================================================
# 全量分析结构
taxonomy = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int))))
# taxonomy[level][category][direction][variant_pattern] = count

# 原始问题按分类分组，便于抽样  key: (level, qtype, direction, variant) -> [examples]
examples = defaultdict(list)

for q in questions:
    qtype = q['template_type']       # 第二级: category
    hop = q['num_hop']               # 第一级: L0/L1
    level = f"L{hop}"
    
    pattern = extract_pattern(q['question'])
    direction = classify_direction(qtype, pattern)  # 第三级
    variant = pattern                                # 第四级
    
    taxonomy[level][qtype][direction][variant] += 1
    
    # 保存示例（每个变体最多3个）
    ex_key = (level, qtype, direction, variant)
    if len(examples[ex_key]) < 3:
        examples[ex_key].append({
            'question': q['question'],
            'answer': q['answer']
        })

# ============================================================
# 4. 输出统计报告
# ============================================================
output_lines = []

def pr(text=""):
    print(text)
    output_lines.append(text)

pr("=" * 100)
pr("NuScenesQA 官方题集 — 完整四级分类统计")
pr("=" * 100)
pr(f"总问题数: {len(questions)}")
pr()

# ---- 顶层摘要 ----
pr("=" * 100)
pr("【摘要】 第一级(L) × 第二级(Category) 分布")
pr("=" * 100)
pr(f"{'Level':<6} {'Category':<14} {'Count':>8} {'Pct':>7}")
pr("-" * 40)

level_totals = defaultdict(int)
cat_totals = defaultdict(int)
for level in sorted(taxonomy.keys()):
    for cat in sorted(taxonomy[level].keys()):
        total = sum(sum(v.values()) for v in taxonomy[level][cat].values())
        level_totals[level] += total
        cat_totals[cat] += total
        pr(f"{level:<6} {cat:<14} {total:>8} {total/len(questions)*100:>6.1f}%")

pr("-" * 40)
for level in sorted(level_totals.keys()):
    pr(f"{level:<6} {'ALL':<14} {level_totals[level]:>8} {level_totals[level]/len(questions)*100:>6.1f}%")
pr()

pr(f"{'ALL':<6} {'Category':<14} {'Count':>8} {'Pct':>7}")
pr("-" * 40)
for cat in sorted(cat_totals.keys()):
    pr(f"{'ALL':<6} {cat:<14} {cat_totals[cat]:>8} {cat_totals[cat]/len(questions)*100:>6.1f}%")
pr()

# ---- 完整四级展开 ----
pr("=" * 100)
pr("【完整展开】 四级分类详情")
pr("=" * 100)

total_directions = 0
total_variants = 0

for level in sorted(taxonomy.keys()):
    pr(f"\n{'='*80}")
    pr(f"  第一级: {level} (共 {level_totals[level]} 题)")
    pr(f"{'='*80}")
    
    for cat in sorted(taxonomy[level].keys()):
        cat_count = sum(sum(v.values()) for v in taxonomy[level][cat].values())
        pr(f"\n  {'─'*70}")
        pr(f"  第二级: {cat.upper()} ({cat_count} 题)")
        pr(f"  {'─'*70}")
        
        # 按数量排序方向
        dir_items = []
        for direction, variants in taxonomy[level][cat].items():
            dir_count = sum(variants.values())
            dir_items.append((direction, variants, dir_count))
        dir_items.sort(key=lambda x: -x[2])
        
        for direction, variants, dir_count in dir_items:
            total_directions += 1
            pr(f"\n    第三级: {direction} ({dir_count} 题)")
            
            # 按数量排序变体
            sorted_variants = sorted(variants.items(), key=lambda x: -x[1])
            for variant_pattern, count in sorted_variants:
                total_variants += 1
                pr(f"      {count:>5}x  {variant_pattern}")

pr()
pr("=" * 100)
pr("【统计汇总】")
pr("=" * 100)
pr(f"  第一级 (Level):     {len(taxonomy)} 个 ({', '.join(sorted(taxonomy.keys()))})")
pr(f"  第二级 (Category):  {sum(len(taxonomy[l]) for l in taxonomy)} 个组合")
pr(f"  第三级 (Direction): {total_directions} 个提问方向")
pr(f"  第四级 (Variant):   {total_variants} 个语义变体模式")
pr(f"  总问题数:           {len(questions)}")

# ============================================================
# 5. 保存报告
# ============================================================
report_path = OUTPUT_DIR / 'nuscenes_qa_full_taxonomy.txt'
with open(report_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(output_lines))
print(f"\n报告已保存: {report_path}")

# ============================================================
# 6. 保存结构化JSON（供后续模板库使用）
# ============================================================
taxonomy_json = {}
for level in sorted(taxonomy.keys()):
    taxonomy_json[level] = {}
    for cat in sorted(taxonomy[level].keys()):
        taxonomy_json[level][cat] = {}
        for direction in sorted(taxonomy[level][cat].keys()):
            variants = taxonomy[level][cat][direction]
            sorted_variants = sorted(variants.items(), key=lambda x: -x[1])
            taxonomy_json[level][cat][direction] = {
                'total': sum(variants.values()),
                'variant_count': len(variants),
                'variants': [
                    {
                        'pattern': pattern,
                        'count': count,
                        'examples': examples.get((level, cat, direction, pattern), [])
                    }
                    for pattern, count in sorted_variants
                ]
            }

json_path = OUTPUT_DIR / 'nuscenes_qa_full_taxonomy.json'
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(taxonomy_json, f, ensure_ascii=False, indent=2)
print(f"结构化JSON已保存: {json_path}")
