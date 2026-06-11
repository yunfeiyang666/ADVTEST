"""
在所有场景上运行完整测试 - 统计 Source Frame 方法的总体正确率
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from run_official_qa_enhanced import EnhancedQARunner

def main():
    print("="*70)
    print("  全场景测试 - Source Frame 方法")
    print("="*70)
    
    # 定义所有测试场景
    base_dir = Path("output/coverage_analysis")
    scenes = [
        (base_dir / "scene_graphs" / "scene-0103_frame25_scene_graph.json",
         base_dir / "vqa_results" / "scene-0103_frame25_official_qa.json"),
        (base_dir / "scene_graphs" / "scene-0103_frame38_scene_graph.json",
         base_dir / "vqa_results" / "scene-0103_frame38_official_qa.json"),
        (base_dir / "scene_graphs" / "scene-0553_frame8_scene_graph.json",
         base_dir / "vqa_results" / "scene-0553_frame8_official_qa.json"),
        (base_dir / "scene_graphs" / "scene-0916_frame8_scene_graph.json",
         base_dir / "vqa_results" / "scene-0916_frame8_official_qa.json"),
    ]
    
    # 检查文件存在
    valid_scenes = []
    for sg_path, qa_path in scenes:
        if sg_path.exists() and qa_path.exists():
            valid_scenes.append((str(sg_path), str(qa_path)))
            print(f"  ✓ {sg_path.stem}")
        else:
            print(f"  ✗ {sg_path.stem} - 文件不存在")
    
    if not valid_scenes:
        print("没有可用的测试场景!")
        return
    
    print(f"\n共 {len(valid_scenes)} 个有效场景")
    
    # 创建运行器
    runner = EnhancedQARunner(use_llm_judge=True, max_retries=2)
    
    if not runner.initialize():
        print("初始化失败")
        return
    
    # 运行测试
    start_time = time.time()
    results = runner.run_all_scenes(valid_scenes, verbose=True)
    elapsed = time.time() - start_time
    
    # 保存结果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = Path(f'output/coverage_analysis/vqa_results/full_test_source_frame_{timestamp}.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # 详细统计
    print("\n" + "="*70)
    print("  详细统计")
    print("="*70)
    
    # 按问题类型统计
    direction_keywords = ['back', 'front', 'left', 'right']
    dir_total = 0
    dir_correct = 0
    other_total = 0
    other_correct = 0
    
    for scene in results['scenes']:
        for r in scene['results']:
            q = r['question'].lower()
            has_dir = any(kw in q for kw in direction_keywords)
            if has_dir:
                dir_total += 1
                if r['correct']:
                    dir_correct += 1
            else:
                other_total += 1
                if r['correct']:
                    other_correct += 1
    
    print(f"\n方向相关问题: {dir_correct}/{dir_total} = {100*dir_correct/dir_total:.1f}%")
    print(f"非方向问题: {other_correct}/{other_total} = {100*other_correct/other_total:.1f}%")
    print(f"总计: {results['correct_count']}/{results['total_questions']} = {100*results['correct_count']/results['total_questions']:.1f}%")
    
    print(f"\n📊 结果已保存: {output_path}")
    print(f"⏰ 总耗时: {elapsed:.1f}秒")
    
    runner.close()

if __name__ == "__main__":
    main()
