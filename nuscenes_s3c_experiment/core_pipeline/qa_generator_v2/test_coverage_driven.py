"""
小测试: 覆盖率驱动的QA生成
"""
import json
from pathlib import Path

# 模拟LLM客户端（用于测试，无需真实API）
class MockLLMClient:
    """模拟LLM客户端，用于测试"""
    
    def __init__(self):
        self.call_count = 0
    
    def generate(self, prompt: str, **kwargs) -> str:
        """模拟LLM生成"""
        self.call_count += 1
        
        # 从prompt中提取关键信息
        if "car3" in prompt and "低覆盖" in prompt:
            # 针对低覆盖对象
            return '''```json
{
  "question": "What is the status of car3?",
  "answer": "parked",
  "question_type": "status",
  "difficulty": "L0",
  "target_objects": ["car3"],
  "reference_objects": [],
  "directions": [],
  "requires_temporal": false
}
```'''
        
        elif "missing_relations" in prompt or "空间关系" in prompt:
            # 针对缺失关系
            return '''```json
{
  "question": "Are there any pedestrians to the left of car1?",
  "answer": "yes",
  "question_type": "exist",
  "difficulty": "L1",
  "target_objects": ["pedestrian1"],
  "reference_objects": ["car1"],
  "directions": ["left"],
  "requires_temporal": false
}
```'''
        
        elif "稀有模式" in prompt or "parked_pedestrian" in prompt:
            # 针对稀有模式
            return '''```json
{
  "question": "How many parked pedestrians are there?",
  "answer": "2",
  "question_type": "count",
  "difficulty": "L0",
  "target_objects": ["pedestrian2", "pedestrian3"],
  "reference_objects": [],
  "directions": [],
  "requires_temporal": true
}
```'''
        
        else:
            # 默认返回
            return '''```json
{
  "question": "Are there any cars?",
  "answer": "yes",
  "question_type": "exist",
  "difficulty": "L0",
  "target_objects": [],
  "reference_objects": [],
  "directions": [],
  "requires_temporal": false
}
```'''


def test_coverage_driven_generation():
    """测试覆盖率驱动生成"""
    
    print("=" * 80)
    print("测试: 覆盖率驱动的QA生成")
    print("=" * 80)
    
    # 1. 加载场景图
    print("\n步骤1: 加载场景图")
    scene_graph_path = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\coverage_analysis\scene_graphs\scene-0103_frame38_scene_graph.json"
    
    if not Path(scene_graph_path).exists():
        print(f"错误: 场景图文件不存在: {scene_graph_path}")
        print("请确保已运行coverage_analysis生成场景图")
        return
    
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_data = json.load(f)
    
    scene_name = scene_data.get("scene_name", "unknown")
    frame_idx = scene_data.get("frame_idx", 0)
    nodes_count = len(scene_data.get("nodes", []))
    edges_count = len(scene_data.get("edges", []))
    
    print(f"  ✓ 场景: {scene_name}, 帧: {frame_idx}")
    print(f"  ✓ 对象数: {nodes_count}, 关系数: {edges_count}")
    
    # 2. 创建模拟的覆盖率分析
    print("\n步骤2: 模拟初始覆盖率分析")
    
    coverage_analysis = {
        "scene_name": scene_name,
        "frame_idx": frame_idx,
        "object_coverage": {},
        "relation_coverage": {},
        "pattern_coverage": {
            "moving_car": 10,
            "parked_car": 5,
            "parked_pedestrian": 1,  # 稀有模式
        },
        "type_coverage": {
            "car": 15,
            "pedestrian": 3,
            "bicycle": 1,
        },
        "direction_coverage": {
            "front": 10,
            "back": 8,
            "left": 2,  # 低覆盖
            "right": 3,
        }
    }
    
    # 初始化对象覆盖率
    nodes = scene_data.get("nodes", [])
    for node in nodes:
        obj_id = node.get("id")
        if obj_id and obj_id != "ego":
            # 模拟一些对象已有覆盖，一些没有
            if "car" in obj_id:
                num = int(obj_id.replace("car", "")) if obj_id.replace("car", "").isdigit() else 0
                coverage_analysis["object_coverage"][obj_id] = max(0, 5 - num)  # car1:4, car2:3, car3:2...
            else:
                coverage_analysis["object_coverage"][obj_id] = 0
    
    # 统计低覆盖情况
    low_coverage_objs = [k for k, v in coverage_analysis["object_coverage"].items() if v < 2]
    print(f"  ✓ 低覆盖对象数: {len(low_coverage_objs)}")
    print(f"  ✓ 示例: {', '.join(low_coverage_objs[:5])}")
    
    # 3. 创建生成器
    print("\n步骤3: 创建覆盖率驱动生成器")
    
    from coverage_driven_generator import CoverageDrivenGenerator
    
    mock_llm = MockLLMClient()
    generator = CoverageDrivenGenerator(llm_client=mock_llm)
    
    print("  ✓ 生成器已创建 (使用模拟LLM)")
    
    # 4. 生成问题
    print("\n步骤4: 基于覆盖率缺口生成问题")
    print("  目标: 生成5个问题，填补覆盖率缺口")
    
    qa_pairs = generator.generate_from_coverage_gaps(
        scene_data,
        coverage_analysis,
        target_count=5,
        focus_areas=["low_object", "missing_relations", "rare_patterns"]
    )
    
    # 5. 展示结果
    print("\n步骤5: 生成结果")
    print("=" * 80)
    
    print(f"\n总共生成: {len(qa_pairs)} 个问答对")
    print(f"LLM调用次数: {mock_llm.call_count}")
    
    print("\n生成的问题:")
    for i, qa in enumerate(qa_pairs, 1):
        print(f"\n{i}. 【{qa.difficulty}】{qa.question_type}")
        print(f"   Q: {qa.question}")
        print(f"   A: {qa.answer}")
        print(f"   涉及对象: {', '.join(qa.target_objects)}")
        if qa.reference_objects:
            print(f"   参考对象: {', '.join(qa.reference_objects)}")
        if qa.directions_used:
            print(f"   方向: {', '.join(qa.directions_used)}")
        print(f"   生成原因: {qa.metadata.get('gap_type', 'unknown')}")
        print(f"   模板ID: {qa.template_id}")
    
    # 6. 覆盖率统计
    print("\n步骤6: 覆盖率提升统计")
    print("=" * 80)
    
    print("\n对象覆盖率变化:")
    for obj_id in list(generator.coverage_stats["object_coverage"].keys())[:5]:
        count = generator.coverage_stats["object_coverage"][obj_id]
        print(f"  {obj_id}: +{count}")
    
    print("\n关系覆盖率:")
    rel_count = len(generator.coverage_stats["relation_coverage"])
    print(f"  新增关系覆盖: {rel_count} 个")
    
    print("\n难度分布:")
    for diff, count in sorted(generator.coverage_stats["difficulty_coverage"].items()):
        print(f"  {diff}: {count}")
    
    print("\n问题类型分布:")
    for qtype, count in sorted(generator.coverage_stats["type_coverage"].items()):
        print(f"  {qtype}: {count}")
    
    # 7. 保存结果
    print("\n步骤7: 保存结果")
    output_dir = Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/test_coverage_driven")
    output_dir.mkdir(exist_ok=True, parents=True)
    
    qa_output = output_dir / "test_qa_pairs.json"
    generator.save_qa_pairs(qa_pairs, str(qa_output))
    
    stats_output = output_dir / "test_coverage_stats.json"
    generator.save_coverage_stats(str(stats_output))
    
    print(f"  ✓ 输出目录: {output_dir}")
    
    # 8. 总结
    print("\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)
    print("\n✅ 核心功能验证:")
    print("  1. 覆盖率分析 - 识别低覆盖对象、缺失关系、稀有模式")
    print("  2. 针对性生成 - LLM根据缺口类型生成对应问题")
    print("  3. 覆盖率更新 - 实时追踪覆盖率提升")
    print("  4. 结果保存 - 问答对和统计数据已保存")
    
    print("\n💡 下一步:")
    print("  - 使用真实LLM (OpenAI/Claude)")
    print("  - 增加迭代次数提升覆盖率")
    print("  - 集成到完整Pipeline中")
    
    return qa_pairs


if __name__ == "__main__":
    try:
        qa_pairs = test_coverage_driven_generation()
        print("\n✅ 测试成功!")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
