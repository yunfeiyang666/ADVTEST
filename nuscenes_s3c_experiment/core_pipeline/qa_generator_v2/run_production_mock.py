"""
生产规模演示: 使用增强Mock LLM生成50题
模拟真实LLM的生产环境表现
"""
import json
import random
from pathlib import Path
from coverage_driven_generator import CoverageDrivenGenerator
from test_complete_demo import EnhancedMockLLM

def run_production_scale():
    """运行生产规模的QA生成 (5轮 x 10题 = 50题)"""
    
    print("=" * 80)
    print("生产规模演示: 覆盖率驱动QA生成 (50题)")
    print("=" * 80)
    print("\n使用增强Mock LLM模拟真实生产环境")
    print("配置: 5轮迭代 × 10题/轮 = 50题")
    
    # 1. 加载场景
    print("\n" + "=" * 80)
    print("阶段1: 加载场景图")
    print("=" * 80)
    
    scene_graph_path = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\coverage_analysis\scene_graphs\scene-0103_frame38_scene_graph.json"
    
    if not Path(scene_graph_path).exists():
        print(f"❌ 场景图不存在: {scene_graph_path}")
        return
    
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_data = json.load(f)
    
    print(f"✓ 场景: {scene_data.get('scene_name')}, 帧: {scene_data.get('frame_idx')}")
    print(f"✓ 对象数: {len(scene_data.get('nodes', []))}")
    print(f"✓ 关系数: {len(scene_data.get('edges', []))}")
    
    # 2. 初始化覆盖率 (所有对象从0开始)
    print("\n" + "=" * 80)
    print("阶段2: 初始化覆盖率")
    print("=" * 80)
    
    coverage_analysis = {
        "scene_name": scene_data.get("scene_name"),
        "frame_idx": scene_data.get("frame_idx"),
        "object_coverage": {},
        "relation_coverage": {},
        "pattern_coverage": {},
        "type_coverage": {},
        "direction_coverage": {
            d: 0 for d in 
            ["front", "back", "left", "right", "front-left", "front-right", "back-left", "back-right"]
        }
    }
    
    # 所有对象初始覆盖率为0
    nodes = scene_data.get("nodes", [])
    for node in nodes:
        obj_id = node.get("unique_id") or node.get("id")
        if obj_id and obj_id != "ego":
            coverage_analysis["object_coverage"][obj_id] = 0
    
    print(f"✓ 总对象: {len(coverage_analysis['object_coverage'])}")
    print(f"✓ 初始覆盖率: 0% (所有对象未覆盖)")
    
    # 3. 初始化LLM和生成器
    print("\n" + "=" * 80)
    print("阶段3: 初始化生成器")
    print("=" * 80)
    
    mock_llm = EnhancedMockLLM()
    generator = CoverageDrivenGenerator(llm_client=mock_llm)
    
    print(f"✓ 使用增强Mock LLM")
    print(f"✓ 生成器初始化完成")
    
    # 4. 迭代生成 (5轮 x 10题)
    print("\n" + "=" * 80)
    print("阶段4: 迭代生成 (5轮)")
    print("=" * 80)
    
    all_qa_pairs = []
    num_iterations = 5
    questions_per_iteration = 10
    
    for iteration in range(1, num_iterations + 1):
        print(f"\n{'='*70}")
        print(f"第 {iteration}/{num_iterations} 轮迭代")
        print(f"{'='*70}")
        
        # 统计当前覆盖率
        total_objects = len(coverage_analysis["object_coverage"])
        covered_objects = sum(1 for v in coverage_analysis["object_coverage"].values() if v > 0)
        low_cov_objects = sum(1 for v in coverage_analysis["object_coverage"].values() if v < 3)
        uncovered_objects = sum(1 for v in coverage_analysis["object_coverage"].values() if v == 0)
        
        print(f"\n📊 当前覆盖率:")
        print(f"  总对象: {total_objects}")
        print(f"  已覆盖: {covered_objects} ({covered_objects/total_objects*100:.1f}%)")
        print(f"  未覆盖: {uncovered_objects}")
        print(f"  低覆盖(<3): {low_cov_objects}")
        
        # 生成问题
        print(f"\n🔄 生成 {questions_per_iteration} 个问题...")
        
        qa_pairs = generator.generate_from_coverage_gaps(
            scene_data,
            coverage_analysis,
            target_count=questions_per_iteration,
            focus_areas=["low_object", "missing_relations", "rare_patterns"]
        )
        
        print(f"✓ 成功生成 {len(qa_pairs)} 个问题")
        
        # 更新覆盖率
        for qa in qa_pairs:
            for obj_id in qa.target_objects + qa.reference_objects:
                if obj_id in coverage_analysis["object_coverage"]:
                    coverage_analysis["object_coverage"][obj_id] += 1
        
        all_qa_pairs.extend(qa_pairs)
        
        # 显示样例
        print(f"\n📝 本轮生成样例:")
        for i, qa in enumerate(qa_pairs[:3], 1):
            print(f"  {i}. [{qa.difficulty}] {qa.question_type}")
            print(f"     Q: {qa.question}")
            print(f"     A: {qa.answer}")
        
        if len(qa_pairs) > 3:
            print(f"  ... 还有 {len(qa_pairs) - 3} 个")
        
        # 统计改进
        new_covered = sum(1 for v in coverage_analysis["object_coverage"].values() if v > 0)
        new_uncovered = sum(1 for v in coverage_analysis["object_coverage"].values() if v == 0)
        
        print(f"\n📈 覆盖率变化:")
        print(f"  已覆盖: {covered_objects} → {new_covered} (+{new_covered - covered_objects})")
        print(f"  未覆盖: {uncovered_objects} → {new_uncovered} ({new_uncovered - uncovered_objects})")
        print(f"  覆盖率: {covered_objects/total_objects*100:.1f}% → {new_covered/total_objects*100:.1f}%")
    
    # 5. 保存结果
    print("\n" + "=" * 80)
    print("阶段5: 保存结果")
    print("=" * 80)
    
    output_dir = Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/production_mock")
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # 保存QA对
    qa_output = output_dir / "production_50_qa_pairs.json"
    generator.save_qa_pairs(all_qa_pairs, str(qa_output))
    
    # 保存统计
    stats_output = output_dir / "production_50_stats.json"
    generator.save_coverage_stats(str(stats_output))
    
    # 生成详细报告
    from collections import Counter
    difficulty_count = Counter(qa.difficulty for qa in all_qa_pairs)
    type_count = Counter(qa.question_type for qa in all_qa_pairs)
    
    final_covered = sum(1 for v in coverage_analysis["object_coverage"].values() if v > 0)
    final_coverage = final_covered / len(coverage_analysis["object_coverage"]) * 100
    
    # 覆盖率分布
    coverage_dist = Counter()
    for obj_id, count in coverage_analysis["object_coverage"].items():
        if count == 0:
            coverage_dist["未覆盖 (0次)"] += 1
        elif count < 3:
            coverage_dist["低覆盖 (1-2次)"] += 1
        elif count < 5:
            coverage_dist["中等覆盖 (3-4次)"] += 1
        else:
            coverage_dist["高覆盖 (5+次)"] += 1
    
    report = []
    report.append("=" * 80)
    report.append("覆盖率驱动QA生成 - 生产规模报告")
    report.append("=" * 80)
    report.append("")
    report.append(f"场景: {scene_data.get('scene_name')}, 帧: {scene_data.get('frame_idx')}")
    report.append(f"生成配置: {num_iterations}轮 × {questions_per_iteration}题 = {len(all_qa_pairs)}题")
    report.append(f"LLM调用: {mock_llm.call_count} 次")
    report.append("")
    report.append("=" * 80)
    report.append("覆盖率统计")
    report.append("=" * 80)
    report.append(f"总对象: {len(coverage_analysis['object_coverage'])}")
    report.append(f"最终覆盖率: {final_coverage:.1f}%")
    report.append(f"已覆盖对象: {final_covered}/{len(coverage_analysis['object_coverage'])}")
    report.append("")
    report.append("覆盖率分布:")
    for level, count in sorted(coverage_dist.items()):
        pct = count / len(coverage_analysis['object_coverage']) * 100
        report.append(f"  {level}: {count} ({pct:.1f}%)")
    report.append("")
    report.append("=" * 80)
    report.append("问题质量统计")
    report.append("=" * 80)
    report.append(f"总问题数: {len(all_qa_pairs)}")
    report.append("")
    report.append("难度分布:")
    for diff, count in sorted(difficulty_count.items()):
        pct = count / len(all_qa_pairs) * 100
        report.append(f"  {diff}: {count} ({pct:.1f}%)")
    report.append("")
    report.append("类型分布:")
    for qtype, count in sorted(type_count.items()):
        pct = count / len(all_qa_pairs) * 100
        report.append(f"  {qtype}: {count} ({pct:.1f}%)")
    report.append("")
    report.append("=" * 80)
    
    report_path = output_dir / "production_50_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    
    print(f"\n✓ QA对 (50题): {qa_output}")
    print(f"✓ 统计数据: {stats_output}")
    print(f"✓ 详细报告: {report_path}")
    
    # 6. 最终总结
    print("\n" + "=" * 80)
    print("🎉 生产规模生成完成!")
    print("=" * 80)
    
    print(f"\n📊 最终统计:")
    print(f"  ✓ 生成问题: {len(all_qa_pairs)} 题")
    print(f"  ✓ LLM调用: {mock_llm.call_count} 次")
    print(f"  ✓ 覆盖率: 0% → {final_coverage:.1f}%")
    print(f"  ✓ 已覆盖对象: {final_covered}/{len(coverage_analysis['object_coverage'])}")
    
    print(f"\n📝 难度分布:")
    for diff, count in sorted(difficulty_count.items()):
        pct = count / len(all_qa_pairs) * 100
        print(f"  {diff}: {count} ({pct:.1f}%)")
    
    print(f"\n🎯 类型分布:")
    for qtype, count in sorted(type_count.items()):
        pct = count / len(all_qa_pairs) * 100
        print(f"  {qtype}: {count} ({pct:.1f}%)")
    
    print(f"\n📈 覆盖率分布:")
    for level, count in sorted(coverage_dist.items()):
        pct = count / len(coverage_analysis['object_coverage']) * 100
        print(f"  {level}: {count} ({pct:.1f}%)")
    
    print(f"\n✅ 所有结果已保存到: {output_dir}")
    
    print(f"\n" + "=" * 80)
    print("💡 下一步建议")
    print("=" * 80)
    print("  1. 查看生成的50个问答对: production_50_qa_pairs.json")
    print("  2. 分析覆盖率改进: production_50_report.txt")
    print("  3. 替换真实LLM (需解决网络问题)")
    print("  4. 批量处理多个场景")
    print("  5. 用生成的题集测试CV模型")


if __name__ == "__main__":
    try:
        run_production_scale()
        print("\n🎉 生产规模演示成功!")
    except Exception as e:
        print(f"\n❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()
