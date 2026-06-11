"""
真实LLM测试 - 覆盖率驱动QA生成
使用DeepSeek API
"""
import json
from pathlib import Path
from coverage_driven_generator import CoverageDrivenGenerator
from llm_client import OpenAIClient

def test_with_real_llm():
    """使用真实LLM进行测试"""
    
    print("=" * 80)
    print("真实LLM测试 - 覆盖率驱动QA生成")
    print("=" * 80)
    
    # 1. 配置LLM客户端 (使用DeepSeek API)
    print("\n步骤1: 配置LLM客户端")
    
    API_KEY = "sk-ecd91655d033446b9ae8ea390e65d923"
    BASE_URL = "https://api.deepseek.com"
    
    llm_client = OpenAIClient(
        api_key=API_KEY,
        model="deepseek-chat",
        base_url=BASE_URL,
        temperature=0.7,
        max_tokens=500
    )
    
    print(f"  ✓ LLM: DeepSeek")
    print(f"  ✓ Model: deepseek-chat")
    
    # 2. 加载场景图
    print("\n步骤2: 加载场景图")
    scene_graph_path = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\coverage_analysis\scene_graphs\scene-0103_frame38_scene_graph.json"
    
    if not Path(scene_graph_path).exists():
        print(f"❌ 场景图文件不存在: {scene_graph_path}")
        return
    
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_data = json.load(f)
    
    scene_name = scene_data.get("scene_name", "unknown")
    frame_idx = scene_data.get("frame_idx", 0)
    nodes_count = len(scene_data.get("nodes", []))
    
    print(f"  ✓ 场景: {scene_name}, 帧: {frame_idx}")
    print(f"  ✓ 对象数: {nodes_count}")
    
    # 3. 创建模拟的覆盖率分析
    print("\n步骤3: 创建覆盖率分析")
    
    coverage_analysis = {
        "scene_name": scene_name,
        "frame_idx": frame_idx,
        "object_coverage": {},
        "relation_coverage": {},
        "pattern_coverage": {},
        "type_coverage": {},
        "direction_coverage": {
            "front": 5,
            "back": 3,
            "left": 1,  # 低覆盖
            "right": 2,
            "front-left": 0,  # 未覆盖
            "front-right": 1,
            "back-left": 0,
            "back-right": 2,
        }
    }
    
    # 初始化对象覆盖率 - 让一些对象有低覆盖
    nodes = scene_data.get("nodes", [])
    for i, node in enumerate(nodes):
        obj_id = node.get("id")
        if obj_id and obj_id != "ego":
            # 前5个对象低覆盖，其他正常
            coverage_analysis["object_coverage"][obj_id] = 0 if i < 5 else 3
    
    low_cov = sum(1 for v in coverage_analysis["object_coverage"].values() if v < 2)
    print(f"  ✓ 低覆盖对象: {low_cov} 个")
    
    # 4. 创建生成器
    print("\n步骤4: 创建覆盖率驱动生成器")
    generator = CoverageDrivenGenerator(llm_client=llm_client)
    print("  ✓ 生成器已创建")
    
    # 5. 生成问题 (少量测试)
    print("\n步骤5: 生成问题 (使用真实LLM)")
    print("  ⏳ 正在调用LLM生成问题...")
    print("  (预计耗时: 10-30秒)")
    
    try:
        qa_pairs = generator.generate_from_coverage_gaps(
            scene_data,
            coverage_analysis,
            target_count=3,  # 先生成3个测试
            focus_areas=["low_object", "rare_patterns"]
        )
        
        print(f"\n  ✅ 成功生成 {len(qa_pairs)} 个问答对")
        
    except Exception as e:
        print(f"\n  ❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 6. 展示结果
    print("\n步骤6: 生成结果展示")
    print("=" * 80)
    
    for i, qa in enumerate(qa_pairs, 1):
        print(f"\n问题 {i}:")
        print(f"  难度: {qa.difficulty}")
        print(f"  类型: {qa.question_type}")
        print(f"  Q: {qa.question}")
        print(f"  A: {qa.answer}")
        print(f"  涉及对象: {', '.join(qa.target_objects) if qa.target_objects else '无'}")
        if qa.reference_objects:
            print(f"  参考对象: {', '.join(qa.reference_objects)}")
        if qa.directions_used:
            print(f"  方向: {', '.join(qa.directions_used)}")
        print(f"  生成原因: {qa.metadata.get('gap_type')}")
        print(f"  需要时序: {'是' if qa.requires_temporal else '否'}")
    
    # 7. 保存结果
    print("\n步骤7: 保存结果")
    output_dir = Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/real_llm_test")
    output_dir.mkdir(exist_ok=True, parents=True)
    
    qa_output = output_dir / "real_llm_qa_pairs.json"
    generator.save_qa_pairs(qa_pairs, str(qa_output))
    
    stats_output = output_dir / "real_llm_stats.json"
    generator.save_coverage_stats(str(stats_output))
    
    print(f"  ✓ 输出目录: {output_dir}")
    
    # 8. 总结
    print("\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)
    
    print("\n✅ 验证结果:")
    print(f"  - 生成问题数: {len(qa_pairs)}")
    print(f"  - LLM调用成功")
    print(f"  - JSON解析成功")
    print(f"  - 覆盖率追踪成功")
    
    print("\n📊 覆盖率提升:")
    for obj_id, count in list(generator.coverage_stats["object_coverage"].items())[:5]:
        print(f"  {obj_id}: +{count}")
    
    print("\n💡 下一步:")
    print("  - 增加生成数量 (target_count=50)")
    print("  - 启用迭代优化 (iterations=3)")
    print("  - 运行完整Pipeline")
    
    return qa_pairs


if __name__ == "__main__":
    try:
        qa_pairs = test_with_real_llm()
        if qa_pairs:
            print("\n🎉 真实LLM测试成功!")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
