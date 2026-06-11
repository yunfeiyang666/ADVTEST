"""
生产环境: 使用真实LLM的覆盖率驱动QA生成
"""
import json
from pathlib import Path
from coverage_driven_generator import CoverageDrivenGenerator
from llm_client import OpenAIClient

def run_production_generation(
    scene_graph_path: str,
    output_dir: str,
    api_key: str = "sk-ecd91655d033446b9ae8ea390e65d923",
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-chat",
    num_iterations: int = 5,
    questions_per_iteration: int = 10
):
    """
    运行生产环境的QA生成
    
    Args:
        scene_graph_path: 场景图路径
        output_dir: 输出目录
        api_key: DeepSeek API key
        base_url: API base URL
        model: 模型名称
        num_iterations: 迭代轮数
        questions_per_iteration: 每轮生成问题数
    """
    
    print("=" * 80)
    print("生产环境: 覆盖率驱动QA生成 (真实LLM)")
    print("=" * 80)
    print(f"\nLLM配置:")
    print(f"  API: {base_url}")
    print(f"  模型: {model}")
    print(f"  迭代轮数: {num_iterations}")
    print(f"  每轮问题数: {questions_per_iteration}")
    
    # 1. 加载场景
    print("\n" + "-" * 80)
    print("阶段1: 加载场景图")
    print("-" * 80)
    
    if not Path(scene_graph_path).exists():
        print(f"❌ 场景图不存在: {scene_graph_path}")
        return
    
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_data = json.load(f)
    
    print(f"✓ 场景: {scene_data.get('scene_name')}, 帧: {scene_data.get('frame_idx')}")
    print(f"✓ 对象数: {len(scene_data.get('nodes', []))}")
    print(f"✓ 关系数: {len(scene_data.get('edges', []))}")
    
    # 2. 初始化覆盖率
    print("\n" + "-" * 80)
    print("阶段2: 初始化覆盖率")
    print("-" * 80)
    
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
    
    # 初始化所有对象覆盖率为0
    nodes = scene_data.get("nodes", [])
    for node in nodes:
        obj_id = node.get("unique_id") or node.get("id")
        if obj_id and obj_id != "ego":
            coverage_analysis["object_coverage"][obj_id] = 0
    
    print(f"✓ 总对象: {len(coverage_analysis['object_coverage'])}")
    print(f"✓ 初始覆盖率: 0% (所有对象未覆盖)")
    
    # 3. 初始化LLM
    print("\n" + "-" * 80)
    print("阶段3: 初始化LLM")
    print("-" * 80)
    
    try:
        llm_client = OpenAIClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            verify_ssl=False,  # 与coverage_pipeline一致
            temperature=0.7,
            max_tokens=2048  # 与VQA pipeline保持一致
        )
        print(f"✓ LLM客户端初始化成功")
        
        # 测试连接
        print(f"  测试LLM连接...")
        test_response = llm_client.generate(
            "请用一句话回复: 你好",
            max_tokens=50
        )
        print(f"  ✓ 连接成功! 响应: {test_response[:50]}...")
        
    except Exception as e:
        print(f"❌ LLM初始化失败: {e}")
        return
    
    # 4. 初始化生成器
    generator = CoverageDrivenGenerator(llm_client=llm_client)
    
    # 5. 迭代生成
    print("\n" + "-" * 80)
    print(f"阶段4: 迭代生成 ({num_iterations}轮)")
    print("-" * 80)
    
    all_qa_pairs = []
    
    for iteration in range(1, num_iterations + 1):
        print(f"\n{'='*60}")
        print(f"第 {iteration}/{num_iterations} 轮迭代")
        print(f"{'='*60}")
        
        # 统计当前覆盖率
        total_objects = len(coverage_analysis["object_coverage"])
        covered_objects = sum(1 for v in coverage_analysis["object_coverage"].values() if v > 0)
        low_cov_objects = sum(1 for v in coverage_analysis["object_coverage"].values() if v < 3)
        
        print(f"\n当前覆盖率:")
        print(f"  已覆盖对象: {covered_objects}/{total_objects} ({covered_objects/total_objects*100:.1f}%)")
        print(f"  低覆盖对象: {low_cov_objects}")
        
        # 生成问题
        print(f"\n生成 {questions_per_iteration} 个问题...")
        
        try:
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
            
            # 显示本轮生成的问题样例
            print(f"\n本轮生成样例:")
            for i, qa in enumerate(qa_pairs[:3], 1):
                print(f"  {i}. [{qa.difficulty}] {qa.question_type}")
                print(f"     Q: {qa.question}")
                print(f"     A: {qa.answer}")
            
            if len(qa_pairs) > 3:
                print(f"  ... 还有 {len(qa_pairs) - 3} 个问题")
            
        except Exception as e:
            print(f"❌ 生成失败: {e}")
            import traceback
            traceback.print_exc()
            break
    
    # 6. 保存结果
    print("\n" + "=" * 80)
    print("阶段5: 保存结果")
    print("=" * 80)
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True, parents=True)
    
    # 保存QA对
    qa_output = output_path / "production_qa_pairs.json"
    generator.save_qa_pairs(all_qa_pairs, str(qa_output))
    
    # 保存统计
    stats_output = output_path / "production_stats.json"
    generator.save_coverage_stats(str(stats_output))
    
    # 生成报告
    from collections import Counter
    difficulty_count = Counter(qa.difficulty for qa in all_qa_pairs)
    type_count = Counter(qa.question_type for qa in all_qa_pairs)
    
    final_covered = sum(1 for v in coverage_analysis["object_coverage"].values() if v > 0)
    final_coverage = final_covered / len(coverage_analysis["object_coverage"]) * 100
    
    report = []
    report.append("=" * 80)
    report.append("覆盖率驱动QA生成 - 生产报告")
    report.append("=" * 80)
    report.append("")
    report.append(f"场景: {scene_data.get('scene_name')}, 帧: {scene_data.get('frame_idx')}")
    report.append(f"LLM模型: {model}")
    report.append(f"迭代轮数: {num_iterations}")
    report.append("")
    report.append(f"生成问题总数: {len(all_qa_pairs)}")
    report.append(f"最终覆盖率: {final_coverage:.1f}%")
    report.append(f"已覆盖对象: {final_covered}/{len(coverage_analysis['object_coverage'])}")
    report.append("")
    report.append("难度分布:")
    for diff, count in sorted(difficulty_count.items()):
        report.append(f"  {diff}: {count}")
    report.append("")
    report.append("类型分布:")
    for qtype, count in sorted(type_count.items()):
        report.append(f"  {qtype}: {count}")
    report.append("")
    report.append("=" * 80)
    
    report_path = output_path / "production_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    
    print(f"\n✓ QA对: {qa_output}")
    print(f"✓ 统计: {stats_output}")
    print(f"✓ 报告: {report_path}")
    
    # 7. 总结
    print("\n" + "=" * 80)
    print("生成完成!")
    print("=" * 80)
    
    print(f"\n📊 最终统计:")
    print(f"  总问题数: {len(all_qa_pairs)}")
    print(f"  覆盖率: 0% → {final_coverage:.1f}%")
    print(f"  覆盖对象: {final_covered}/{len(coverage_analysis['object_coverage'])}")
    
    print(f"\n📝 难度分布:")
    for diff, count in sorted(difficulty_count.items()):
        print(f"  {diff}: {count} ({count/len(all_qa_pairs)*100:.1f}%)")
    
    print(f"\n🎯 类型分布:")
    for qtype, count in sorted(type_count.items()):
        print(f"  {qtype}: {count} ({count/len(all_qa_pairs)*100:.1f}%)")
    
    print(f"\n✅ 所有结果已保存到: {output_path}")


if __name__ == "__main__":
    # 默认配置
    scene_graph_path = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\coverage_analysis\scene_graphs\scene-0103_frame38_scene_graph.json"
    output_dir = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\production_qa"
    
    # DeepSeek配置 (与coverage_pipeline一致)
    api_key = "sk-ecd91655d033446b9ae8ea390e65d923"
    base_url = "https://maas-api.ai-yuanjing.com/openapi/compatible-mode/v1"
    model = "deepseek-r1"
    
    # 生成配置
    num_iterations = 5  # 5轮迭代
    questions_per_iteration = 10  # 每轮10个问题
    
    print("\n🚀 启动生产环境QA生成...")
    print(f"   场景: scene-0103 frame 38")
    print(f"   目标: {num_iterations}轮 × {questions_per_iteration}题 = {num_iterations * questions_per_iteration}题")
    print()
    
    try:
        run_production_generation(
            scene_graph_path=scene_graph_path,
            output_dir=output_dir,
            api_key=api_key,
            base_url=base_url,
            model=model,
            num_iterations=num_iterations,
            questions_per_iteration=questions_per_iteration
        )
        print("\n🎉 生产环境运行成功!")
    except Exception as e:
        print(f"\n❌ 生产环境运行失败: {e}")
        import traceback
        traceback.print_exc()
