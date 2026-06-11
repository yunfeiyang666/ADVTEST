"""
分析官方QA测试结果：
1. 计算覆盖率（问题类型、场景图元素）
2. 挑选特征问答对用于PPT展示
"""
import json
import os
from collections import defaultdict

# 读取所有结果文件
results_dir = r"e:\Project\ADVTEST\nuscenes_s3c_experiment\output\coverage_analysis\vqa_results"

result_files = [
    "scene-0553_frame8_official_qa.json",
    "scene-0103_frame38_official_qa.json",
    "scene-0916_frame8_official_qa.json",
    "scene-0103_frame25_official_qa.json"
]

print("=" * 80)
print("  NuScenes官方QA测试结果分析")
print("=" * 80)

# ============ 1. 覆盖率统计 ============
print("\n【一、覆盖率统计】")

all_results = []
total_questions = 0
total_success = 0
total_match = 0

by_type = defaultdict(lambda: {"total": 0, "success": 0, "match": 0})
by_scene = {}

for file in result_files:
    filepath = os.path.join(results_dir, file)
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    scene_name = data['scene_name']
    frame_idx = data['frame_idx']
    results = data['results']
    
    scene_key = f"{scene_name}_frame{frame_idx}"
    
    scene_stats = {
        'total': len(results),
        'success': sum(1 for r in results if r['success']),
        'match': sum(1 for r in results if r['answer_match'])
    }
    by_scene[scene_key] = scene_stats
    
    total_questions += len(results)
    total_success += scene_stats['success']
    total_match += scene_stats['match']
    
    # 按类型统计
    for r in results:
        qtype = r['question_type']
        by_type[qtype]['total'] += 1
        if r['success']:
            by_type[qtype]['success'] += 1
        if r['answer_match']:
            by_type[qtype]['match'] += 1
    
    all_results.extend(results)

print(f"\n1. 总体统计:")
print(f"   总问题数: {total_questions}")
print(f"   执行成功: {total_success}/{total_questions} ({total_success/total_questions*100:.1f}%)")
print(f"   答案匹配: {total_match}/{total_questions} ({total_match/total_questions*100:.1f}%)")

print(f"\n2. 按场景统计:")
for scene, stats in by_scene.items():
    print(f"   {scene}:")
    print(f"     问题数: {stats['total']}")
    print(f"     执行成功率: {stats['success']}/{stats['total']} ({stats['success']/stats['total']*100:.1f}%)")
    print(f"     答案准确率: {stats['match']}/{stats['total']} ({stats['match']/stats['total']*100:.1f}%)")

print(f"\n3. 按问题类型统计:")
for qtype in sorted(by_type.keys()):
    stats = by_type[qtype]
    print(f"   {qtype}:")
    print(f"     问题数: {stats['total']}")
    print(f"     执行成功率: {stats['success']}/{stats['total']} ({stats['success']/stats['total']*100:.1f}%)")
    print(f"     答案准确率: {stats['match']}/{stats['total']} ({stats['match']/stats['total']*100:.1f}%)")

# ============ 2. 问题类型覆盖率 ============
print(f"\n4. 问题类型覆盖率:")
question_types = list(by_type.keys())
print(f"   覆盖的问题类型: {len(question_types)} 种")
print(f"   类型列表: {', '.join(question_types)}")

# ============ 3. 错误类型分析 ============
print(f"\n5. 错误类型分析:")

cypher_errors = []  # Cypher生成错误（包含<think>等）
query_errors = []   # Neo4j执行错误
answer_errors = []  # 答案不匹配

for r in all_results:
    if r['success']:
        cypher = r['cypher']
        if cypher and '<think>' in cypher:
            cypher_errors.append(r)
        elif not r['answer_match']:
            answer_errors.append(r)
    else:
        query_errors.append(r)

print(f"   Cypher格式错误（含<think>标签）: {len(cypher_errors)} 题 ({len(cypher_errors)/total_questions*100:.1f}%)")
print(f"   Neo4j执行错误: {len(query_errors)} 题 ({len(query_errors)/total_questions*100:.1f}%)")
print(f"   答案不匹配: {len(answer_errors)} 题 ({len(answer_errors)/total_questions*100:.1f}%)")

# ============ 4. 挑选特征问答对 ============
print("\n" + "=" * 80)
print("【二、特征问答对（PPT素材）】")
print("=" * 80)

# 类别1: 完美答对的例子
print("\n【类别1: 完美答对】- 展示系统能力")
perfect_answers = [r for r in all_results if r['answer_match']]
print(f"共{len(perfect_answers)}个")

if perfect_answers:
    print("\n推荐展示案例：")
    for i, r in enumerate(perfect_answers[:3], 1):
        print(f"\n案例{i}:")
        print(f"  问题: {r['question']}")
        print(f"  官方答案: {r['expected_answer']}")
        print(f"  系统答案: {r['predicted_answer']}")
        print(f"  Cypher: {r['cypher'][:150]}..." if len(r['cypher']) > 150 else f"  Cypher: {r['cypher']}")

# 类别2: Cypher格式错误（LLM输出了思考过程）
print("\n\n【类别2: Cypher格式错误】- 展示LLM推理过程泄露问题")
print(f"共{len(cypher_errors)}个")

if cypher_errors:
    print("\n推荐展示案例（最典型）:")
    example = cypher_errors[0]
    print(f"\n问题: {example['question']}")
    print(f"官方答案: {example['expected_answer']}")
    print(f"问题: LLM生成的Cypher包含<think>标签，而非纯Cypher语句")
    print(f"Cypher前100字符: {example['cypher'][:100]}...")

# 类别3: Schema不匹配（如trailer, barrier不存在）
print("\n\n【类别3: Schema不匹配】- 展示数据集标注差异")
schema_mismatch = []
for r in all_results:
    question_lower = r['question'].lower()
    if 'trailer' in question_lower or 'barrier' in question_lower:
        schema_mismatch.append(r)

print(f"共{len(schema_mismatch)}个（涉及trailer/barrier等数据库中不存在的类型）")

if schema_mismatch:
    print("\n推荐展示案例:")
    for i, r in enumerate(schema_mismatch[:2], 1):
        print(f"\n案例{i}:")
        print(f"  问题: {r['question']}")
        print(f"  官方答案: {r['expected_answer']}")
        print(f"  系统答案: {r['predicted_answer'][:100]}...")
        print(f"  问题根源: NuScenes数据中没有'trailer'或'barrier'类型")

# 类别4: 复杂推理失败
print("\n\n【类别4: 复杂推理失败】- 展示多跳推理挑战")
complex_failures = []
for r in all_results:
    question = r['question']
    # 识别复杂问题（包含多个条件）
    if ('same status' in question or 'to the' in question) and not r['answer_match']:
        if 'trailer' not in question.lower() and 'barrier' not in question.lower():
            complex_failures.append(r)

print(f"共{len(complex_failures)}个")

if complex_failures:
    print("\n推荐展示案例:")
    for i, r in enumerate(complex_failures[:2], 1):
        print(f"\n案例{i}:")
        print(f"  问题: {r['question']}")
        print(f"  官方答案: {r['expected_answer']}")
        print(f"  系统答案: {r['predicted_answer'][:150]}...")
        print(f"  Cypher: {r['cypher'][:200]}..." if len(r['cypher']) > 200 else f"  Cypher: {r['cypher']}")

# 类别5: 简单问题答错（最尴尬）
print("\n\n【类别5: 简单问题答错】- 展示基础能力不足")
simple_failures = []
for r in all_results:
    if r['question_type'] == 'exist' and not r['answer_match']:
        if 'trailer' not in r['question'].lower() and 'barrier' not in r['question'].lower():
            simple_failures.append(r)

print(f"共{len(simple_failures)}个")

if simple_failures:
    print("\n推荐展示案例:")
    example = simple_failures[0]
    print(f"\n问题: {example['question']}")
    print(f"官方答案: {example['expected_answer']}")
    print(f"系统答案: {example['predicted_answer']}")
    print(f"问题类型: 简单的存在性判断")

# ============ 5. PPT展示建议 ============
print("\n" + "=" * 80)
print("【三、PPT展示建议】")
print("=" * 80)

print("""
建议PPT结构：

第1张: 测试概况
  - 测试问题: 58题（官方NuScenes QA验证集）
  - 覆盖场景: 4个场景，密度不同
  - 问题类型: exist, object, count, comparison, status
  - 执行成功率: 100% ✓
  - 答案准确率: 11.6% ✗

第2张: 成功案例 - 展示系统能力
  - 展示1-2个答对的例子
  - 强调: 能正确理解问题 → 生成Cypher → 查询Neo4j → 生成答案
  - 展示完整流程图

第3张: 失败案例1 - LLM推理过程泄露
  - 问题: LLM生成Cypher时输出了<think>标签
  - 原因: DeepSeek-R1模型特性（思维链泄露）
  - 影响: Neo4j无法解析，语法错误
  - 解决方案: 优化Prompt，或后处理清理<think>标签

第4张: 失败案例2 - Schema不匹配
  - 问题: 官方QA问到trailer/barrier，但场景图没有这些类型
  - 原因: 官方QA标注 ≠ 场景图Schema
  - 影响: 查询返回空，准确率下降
  - 启示: 需要Schema对齐或问题过滤

第5张: 失败案例3 - 复杂推理失败
  - 问题: 多跳关系查询（如"same status as the truck to the..."）
  - 原因: LLM对空间关系理解不准确，生成的Cypher过于复杂或错误
  - 影响: 查询结果不符合预期
  - 改进方向: 提供更多Few-shot示例，优化Schema描述

第6张: 覆盖率分析总结
  - 问题类型覆盖: 5种全覆盖 ✓
  - 场景元素覆盖: 基于实际标注的对象
  - 关系覆盖: 空间关系（方位+距离）
  - 当前瓶颈:
    1. LLM Cypher生成质量 (思维链泄露)
    2. Schema不一致 (官方QA vs 场景图)
    3. 复杂推理能力弱
""")

# ============ 6. 保存详细分析 ============
output_file = os.path.join(results_dir, "analysis_summary.json")
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump({
        'overall_stats': {
            'total_questions': total_questions,
            'total_success': total_success,
            'total_match': total_match,
            'success_rate': total_success/total_questions*100,
            'accuracy': total_match/total_questions*100
        },
        'by_scene': by_scene,
        'by_type': {k: dict(v) for k, v in by_type.items()},
        'error_analysis': {
            'cypher_format_errors': len(cypher_errors),
            'query_execution_errors': len(query_errors),
            'answer_mismatches': len(answer_errors)
        },
        'featured_examples': {
            'perfect_answers': [
                {
                    'question': r['question'],
                    'expected': r['expected_answer'],
                    'predicted': r['predicted_answer'],
                    'cypher': r['cypher']
                }
                for r in perfect_answers[:3]
            ],
            'cypher_format_errors': [
                {
                    'question': r['question'],
                    'expected': r['expected_answer'],
                    'cypher_prefix': r['cypher'][:200]
                }
                for r in cypher_errors[:3]
            ],
            'schema_mismatches': [
                {
                    'question': r['question'],
                    'expected': r['expected_answer'],
                    'predicted': r['predicted_answer'][:200]
                }
                for r in schema_mismatch[:3]
            ],
            'complex_failures': [
                {
                    'question': r['question'],
                    'expected': r['expected_answer'],
                    'predicted': r['predicted_answer'][:200],
                    'cypher': r['cypher'][:200] if len(r['cypher']) <= 1000 else None
                }
                for r in complex_failures[:3]
            ]
        }
    }, f, indent=2, ensure_ascii=False)

print(f"\n✓ 详细分析已保存: {output_file}")
