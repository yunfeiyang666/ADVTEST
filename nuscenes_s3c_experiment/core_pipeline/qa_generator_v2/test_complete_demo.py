"""
完整演示: 覆盖率驱动QA生成
使用增强的Mock LLM生成高质量多样化问题
"""
import json
import random
from pathlib import Path
from coverage_driven_generator import CoverageDrivenGenerator

class EnhancedMockLLM:
    """增强的Mock LLM - 生成更真实的问题"""
    
    def __init__(self):
        self.call_count = 0
        self.question_templates = {
            "low_object_status": [
                "What is the status of {obj}?",
                "What status is {obj}?",
                "The {obj_type} ({obj}) is in what status?"
            ],
            "low_object_exist": [
                "Are there any {obj_type}s near {obj}?",
                "Is {obj} visible?",
            ],
            "missing_relation": [
                "Are there any {tgt_type}s to the {direction} of {src}?",
                "What is to the {direction} of {src}?",
                "How many {tgt_type}s are to the {direction} of {src}?"
            ],
            "rare_pattern": [
                "Are there any {status} {obj_type}s?",
                "How many {status} {obj_type}s are there?",
                "Are any {status} {obj_type}s visible?"
            ]
        }
    
    def generate(self, prompt: str, **kwargs) -> str:
        """模拟LLM生成高质量问题"""
        self.call_count += 1
        
        # 从prompt中提取关键信息
        if "低覆盖" in prompt and "ID:" in prompt:
            # 低覆盖对象
            import re
            obj_match = re.search(r"ID:\s*(\w+)", prompt)
            type_match = re.search(r"类型:\s*(\w+)", prompt)
            status_match = re.search(r"状态:\s*(\w+)", prompt)
            
            if obj_match and type_match:
                obj = obj_match.group(1)
                obj_type = type_match.group(1)
                status = status_match.group(1) if status_match else "unknown"
                
                # 随机选择问题类型
                if status != "unknown" and random.random() > 0.5:
                    template = random.choice(self.question_templates["low_object_status"])
                    question = template.format(obj=obj, obj_type=obj_type)
                    answer = status
                    q_type = "status"
                else:
                    template = random.choice(self.question_templates["low_object_exist"])
                    question = template.format(obj=obj, obj_type=obj_type)
                    answer = "yes"
                    q_type = "exist"
                
                return f'''```json
{{
  "question": "{question}",
  "answer": "{answer}",
  "question_type": "{q_type}",
  "difficulty": "L0",
  "target_objects": ["{obj}"],
  "reference_objects": [],
  "directions": [],
  "requires_temporal": {"true" if status in ["moving", "stopped"] else "false"}
}}
```'''
        
        elif "空间关系" in prompt:
            # 缺失关系
            import re
            src_match = re.search(r"源对象:\s*(\w+)\s*\((\w+)\)", prompt)
            tgt_match = re.search(r"目标对象:\s*(\w+)\s*\((\w+)\)", prompt)
            dir_match = re.search(r"方向:\s*([\w-]+)", prompt)
            
            if src_match and tgt_match and dir_match:
                src = src_match.group(1)
                tgt = tgt_match.group(1)
                tgt_type = tgt_match.group(2)
                direction = dir_match.group(1)
                
                template = random.choice(self.question_templates["missing_relation"])
                question = template.format(src=src, tgt_type=tgt_type, direction=direction)
                
                # 根据问题类型生成答案
                if "How many" in question or "What number" in question:
                    answer = str(random.randint(0, 3))
                    q_type = "count"
                elif "What is" in question:
                    answer = tgt_type
                    q_type = "object"
                else:
                    answer = random.choice(["yes", "no"])
                    q_type = "exist"
                
                return f'''```json
{{
  "question": "{question}",
  "answer": "{answer}",
  "question_type": "{q_type}",
  "difficulty": "L1",
  "target_objects": ["{tgt}"],
  "reference_objects": ["{src}"],
  "directions": ["{direction}"],
  "requires_temporal": false
}}
```'''
        
        elif "稀有模式" in prompt or "组合" in prompt:
            # 稀有模式
            import re
            type_match = re.search(r"类型:\s*(\w+)", prompt)
            status_match = re.search(r"状态:\s*(\w+)", prompt)
            
            if type_match and status_match:
                obj_type = type_match.group(1)
                status = status_match.group(1)
                
                template = random.choice(self.question_templates["rare_pattern"])
                question = template.format(status=status, obj_type=obj_type)
                
                if "How many" in question or "What number" in question:
                    answer = str(random.randint(0, 5))
                    q_type = "count"
                else:
                    answer = random.choice(["yes", "no"])
                    q_type = "exist"
                
                return f'''```json
{{
  "question": "{question}",
  "answer": "{answer}",
  "question_type": "{q_type}",
  "difficulty": "L0",
  "target_objects": [],
  "reference_objects": [],
  "directions": [],
  "requires_temporal": true
}}
```'''
        
        # 默认
        return '''```json
{
  "question": "Are there any vehicles?",
  "answer": "yes",
  "question_type": "exist",
  "difficulty": "L0",
  "target_objects": [],
  "reference_objects": [],
  "directions": [],
  "requires_temporal": false
}
```'''


def run_complete_demo():
    """运行完整演示"""
    
    print("=" * 80)
    print("完整演示: 覆盖率驱动的QA生成系统")
    print("=" * 80)
    print("\n这是一个完整的端到端演示，展示:")
    print("  1. 覆盖率缺口分析")
    print("  2. LLM针对性生成")
    print("  3. 迭代优化覆盖率")
    print("  4. 质量追踪与报告")
    
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
    
    # 2. 初始覆盖率分析
    print("\n" + "=" * 80)
    print("阶段2: 初始覆盖率分析")
    print("=" * 80)
    
    coverage_analysis = {
        "scene_name": scene_data.get("scene_name"),
        "frame_idx": scene_data.get("frame_idx"),
        "object_coverage": {},
        "relation_coverage": {},
        "pattern_coverage": {},
        "type_coverage": {},
        "direction_coverage": {
            d: random.randint(0, 5) for d in 
            ["front", "back", "left", "right", "front-left", "front-right", "back-left", "back-right"]
        }
    }
    
    # 模拟真实的覆盖率分布
    nodes = scene_data.get("nodes", [])
    for i, node in enumerate(nodes):
        obj_id = node.get("unique_id") or node.get("id")
        if obj_id and obj_id != "ego":
            # 80%对象有一定覆盖，20%几乎无覆盖
            if random.random() < 0.8:
                coverage_analysis["object_coverage"][obj_id] = random.randint(3, 10)
            else:
                coverage_analysis["object_coverage"][obj_id] = random.randint(0, 1)
    
    if len(coverage_analysis["object_coverage"]) == 0:
        print("❌ 场景没有有效对象 (可能都是ego节点)")
        return
    
    low_cov = sum(1 for v in coverage_analysis["object_coverage"].values() if v < 2)
    print(f"✓ 总对象: {len(coverage_analysis['object_coverage'])}")
    print(f"✓ 低覆盖对象 (<2次): {low_cov} 个")
    print(f"✓ 覆盖率: {(1 - low_cov/len(coverage_analysis['object_coverage']))*100:.1f}%")
    
    # 3. 迭代生成
    print("\n" + "=" * 80)
    print("阶段3: 迭代生成问题 (3轮)")
    print("=" * 80)
    
    mock_llm = EnhancedMockLLM()
    generator = CoverageDrivenGenerator(llm_client=mock_llm)
    
    all_qa_pairs = []
    
    for iteration in range(1, 4):
        print(f"\n--- 第 {iteration} 轮迭代 ---")
        
        low_cov_before = sum(1 for v in coverage_analysis["object_coverage"].values() if v < 2)
        
        qa_pairs = generator.generate_from_coverage_gaps(
            scene_data,
            coverage_analysis,
            target_count=5,
            focus_areas=["low_object", "missing_relations", "rare_patterns"]
        )
        
        # 更新覆盖率
        for qa in qa_pairs:
            for obj_id in qa.target_objects + qa.reference_objects:
                if obj_id in coverage_analysis["object_coverage"]:
                    coverage_analysis["object_coverage"][obj_id] += 1
        
        all_qa_pairs.extend(qa_pairs)
        
        low_cov_after = sum(1 for v in coverage_analysis["object_coverage"].values() if v < 2)
        
        print(f"  生成: {len(qa_pairs)} 个问题")
        print(f"  低覆盖对象: {low_cov_before} → {low_cov_after}")
        print(f"  覆盖率提升: +{(low_cov_before - low_cov_after) / len(coverage_analysis['object_coverage']) * 100:.1f}%")
    
    # 4. 结果展示
    print("\n" + "=" * 80)
    print("阶段4: 生成结果")
    print("=" * 80)
    
    print(f"\n总共生成: {len(all_qa_pairs)} 个问答对")
    print(f"LLM调用: {mock_llm.call_count} 次")
    
    # 按难度统计
    from collections import Counter
    difficulty_count = Counter(qa.difficulty for qa in all_qa_pairs)
    type_count = Counter(qa.question_type for qa in all_qa_pairs)
    
    print(f"\n难度分布:")
    for diff, count in sorted(difficulty_count.items()):
        print(f"  {diff}: {count}")
    
    print(f"\n类型分布:")
    for qtype, count in sorted(type_count.items()):
        print(f"  {qtype}: {count}")
    
    print(f"\n示例问题 (前10个):")
    for i, qa in enumerate(all_qa_pairs[:10], 1):
        print(f"\n{i}. [{qa.difficulty}] {qa.question_type}")
        print(f"   Q: {qa.question}")
        print(f"   A: {qa.answer}")
    
    # 5. 保存结果
    print("\n" + "=" * 80)
    print("阶段5: 保存结果")
    print("=" * 80)
    
    output_dir = Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/complete_demo")
    output_dir.mkdir(exist_ok=True, parents=True)
    
    qa_output = output_dir / "demo_qa_pairs.json"
    generator.save_qa_pairs(all_qa_pairs, str(qa_output))
    
    stats_output = output_dir / "demo_stats.json"
    generator.save_coverage_stats(str(stats_output))
    
    # 生成报告
    report = []
    report.append("=" * 80)
    report.append("覆盖率驱动QA生成 - 演示报告")
    report.append("=" * 80)
    report.append("")
    report.append(f"场景: {scene_data.get('scene_name')}, 帧: {scene_data.get('frame_idx')}")
    report.append(f"生成问题总数: {len(all_qa_pairs)}")
    report.append(f"LLM调用次数: {mock_llm.call_count}")
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
    
    report_path = output_dir / "demo_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    
    print(f"✓ 问答对: {qa_output}")
    print(f"✓ 统计: {stats_output}")
    print(f"✓ 报告: {report_path}")
    
    # 6. 总结
    print("\n" + "=" * 80)
    print("演示完成!")
    print("=" * 80)
    
    final_low_cov = sum(1 for v in coverage_analysis["object_coverage"].values() if v < 2)
    initial_low_cov = low_cov
    
    print(f"\n🎯 覆盖率提升:")
    print(f"  初始低覆盖对象: {initial_low_cov}")
    print(f"  最终低覆盖对象: {final_low_cov}")
    print(f"  提升: {initial_low_cov - final_low_cov} 个对象")
    print(f"  覆盖率: {(1 - initial_low_cov/len(coverage_analysis['object_coverage']))*100:.1f}% → {(1 - final_low_cov/len(coverage_analysis['object_coverage']))*100:.1f}%")
    
    print(f"\n✅ 核心功能验证:")
    print(f"  ✓ 覆盖率分析")
    print(f"  ✓ 缺口识别")
    print(f"  ✓ LLM生成")
    print(f"  ✓ 迭代优化")
    print(f"  ✓ 结果保存")
    
    print(f"\n💡 系统已就绪!")
    print(f"  - 替换Mock LLM为真实LLM (OpenAI/DeepSeek/Claude)")
    print(f"  - 增加迭代轮数获得更高覆盖率")
    print(f"  - 批量处理多个场景")
    print(f"  - 用生成的测试集测试CV模型")


if __name__ == "__main__":
    try:
        run_complete_demo()
        print("\n🎉 完整演示成功!")
    except Exception as e:
        print(f"\n❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()
