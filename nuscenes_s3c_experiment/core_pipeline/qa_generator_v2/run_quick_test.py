"""
快速测试: 真实LLM生成 (2轮 x 5题 = 10题)
"""
import json
from pathlib import Path
from coverage_driven_generator import CoverageDrivenGenerator
from llm_client import OpenAIClient

def main():
    print("=" * 80)
    print("快速测试: 真实LLM生成 (10题)")
    print("=" * 80)
    
    # 加载场景
    scene_graph_path = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\coverage_analysis\scene_graphs\scene-0103_frame38_scene_graph.json"
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_data = json.load(f)
    
    print(f"✓ 场景: {scene_data.get('scene_name')}, 帧: {scene_data.get('frame_idx')}")
    
    # 初始化覆盖率
    coverage_analysis = {
        "scene_name": scene_data.get("scene_name"),
        "frame_idx": scene_data.get("frame_idx"),
        "object_coverage": {},
        "relation_coverage": {},
        "pattern_coverage": {},
        "type_coverage": {},
        "direction_coverage": {}
    }
    
    for node in scene_data.get("nodes", []):
        obj_id = node.get("unique_id") or node.get("id")
        if obj_id and obj_id != "ego":
            coverage_analysis["object_coverage"][obj_id] = 0
    
    print(f"✓ 总对象: {len(coverage_analysis['object_coverage'])}")
    
    # 初始化LLM
    print("\n初始化LLM...")
    llm_client = OpenAIClient(
        api_key="sk-ecd91655d033446b9ae8ea390e65d923",
        base_url="https://maas-api.ai-yuanjing.com/openapi/compatible-mode/v1",
        model="deepseek-r1",
        verify_ssl=False,
        temperature=0.1,  # 与VQA pipeline一致，低温度减少推理
        max_tokens=4096  # 与VQA pipeline一致，给足空间
    )
    print("✓ LLM就绪")
    
    # 初始化生成器
    generator = CoverageDrivenGenerator(llm_client=llm_client)
    
    # 生成 (2轮 x 5题)
    all_qa_pairs = []
    
    for iteration in range(1, 3):
        print(f"\n{'='*60}")
        print(f"第 {iteration}/2 轮")
        print(f"{'='*60}")
        
        covered = sum(1 for v in coverage_analysis["object_coverage"].values() if v > 0)
        print(f"当前覆盖: {covered}/{len(coverage_analysis['object_coverage'])}")
        
        print("\n生成5个问题...")
        qa_pairs = generator.generate_from_coverage_gaps(
            scene_data,
            coverage_analysis,
            target_count=5,
            focus_areas=["low_object", "rare_patterns"]
        )
        
        print(f"✓ 成功生成 {len(qa_pairs)} 个")
        
        # 更新覆盖率
        for qa in qa_pairs:
            for obj_id in qa.target_objects + qa.reference_objects:
                if obj_id in coverage_analysis["object_coverage"]:
                    coverage_analysis["object_coverage"][obj_id] += 1
        
        all_qa_pairs.extend(qa_pairs)
        
        # 显示样例
        for i, qa in enumerate(qa_pairs[:2], 1):
            print(f"  {i}. Q: {qa.question}")
            print(f"     A: {qa.answer}")
    
    # 保存
    print(f"\n{'='*60}")
    print("保存结果")
    print(f"{'='*60}")
    
    output_dir = Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/quick_test")
    output_dir.mkdir(exist_ok=True, parents=True)
    
    qa_output = output_dir / "quick_10_qa_pairs.json"
    generator.save_qa_pairs(all_qa_pairs, str(qa_output))
    
    final_covered = sum(1 for v in coverage_analysis["object_coverage"].values() if v > 0)
    
    print(f"\n✓ 生成完成!")
    print(f"  总问题: {len(all_qa_pairs)}")
    print(f"  覆盖率: 0% → {final_covered/len(coverage_analysis['object_coverage'])*100:.1f}%")
    print(f"  保存到: {qa_output}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
