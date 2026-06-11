"""
测试新模板生成效果
"""
import json
from pathlib import Path
from generator import UnifiedQAGenerator
from collections import Counter

# 测试场景图
scene_graph_path = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\coverage_analysis\scene_graphs\scene-0103_frame38_scene_graph.json"

print("="*80)
print("测试新模板系统 (57个模板)")
print("="*80)

# 加载场景图
with open(scene_graph_path, 'r', encoding='utf-8') as f:
    scene_data = json.load(f)

# 生成问答对
generator = UnifiedQAGenerator()
qa_pairs = generator.generate(scene_data)

print(f"\n总生成问题数: {len(qa_pairs)}")

# 按难度统计
difficulty_count = Counter([qa.difficulty for qa in qa_pairs])
print(f"\n按难度统计:")
for diff, count in sorted(difficulty_count.items()):
    print(f"  {diff}: {count}")

# 按问题类型统计
qtype_count = Counter([qa.question_type for qa in qa_pairs])
print(f"\n按问题类型统计:")
for qtype, count in sorted(qtype_count.items()):
    print(f"  {qtype}: {count}")

# 按模板统计
template_count = Counter([qa.template_id for qa in qa_pairs])
print(f"\n模板使用频率 (Top 20):")
for template_id, count in template_count.most_common(20):
    print(f"  {template_id}: {count}")

# 时序问题统计
temporal_count = sum(1 for qa in qa_pairs if qa.requires_temporal)
print(f"\n需要时序信息的问题: {temporal_count}/{len(qa_pairs)} ({temporal_count/len(qa_pairs)*100:.1f}%)")

# 展示一些示例问题
print("\n" + "="*80)
print("问题示例 (每个难度各5个)")
print("="*80)

for diff in ["L0", "L1", "L2"]:
    print(f"\n{diff} 问题示例:")
    samples = [qa for qa in qa_pairs if qa.difficulty == diff][:5]
    for qa in samples:
        print(f"  Q: {qa.question}")
        print(f"  A: {qa.answer}")
        print(f"  Template: {qa.template_id}")
        print()

# 保存到文件
output_path = Path(__file__).parent / "test_output_57templates.json"
generator.save_qa_pairs(qa_pairs, str(output_path))
print(f"\n完整输出已保存到: {output_path}")
