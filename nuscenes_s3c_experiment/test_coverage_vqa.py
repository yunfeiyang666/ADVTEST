"""
覆盖率测试脚本
分别测试高密度和低密度场景的VQA问题覆盖率
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from import_single_scene_to_neo4j import Neo4jImporter
from vqa_pipeline import VQAPipeline
from vqa_pipeline.sample_questions import SAMPLE_QUESTIONS, get_questions_by_category
import config


def load_scene_graph(filepath):
    """加载场景图"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def import_to_neo4j(scene_graph, neo4j_uri, neo4j_user, neo4j_password):
    """导入场景图到Neo4j"""
    print("\n" + "=" * 70)
    print("  导入场景到Neo4j")
    print("=" * 70)
    
    importer = Neo4jImporter(neo4j_uri, neo4j_user, neo4j_password)
    
    try:
        print("\n连接Neo4j数据库...")
        print(f"  URI: {neo4j_uri}")
        
        print("\n清空现有数据...")
        importer.clear_database()
        
        print("\n创建约束...")
        importer.create_constraints()
        
        # 导入场景
        importer.import_scene(scene_graph)
        
        # 验证
        print("\n验证导入结果...")
        with importer.driver.session() as session:
            result = session.run("MATCH (n:Object) RETURN count(n) as count")
            node_count = result.single()['count']
            
            result = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count")
            edge_count = result.single()['count']
            
            print(f"  对象节点数: {node_count}")
            print(f"  关系数: {edge_count}")
        
        print("\n✓ 导入完成！")
        return True
        
    except Exception as e:
        print(f"\n❌ 导入失败: {e}")
        return False
    finally:
        importer.close()


def test_vqa_questions(scene_name, question_categories=None, max_per_category=3):
    """测试VQA问题"""
    print("\n" + "=" * 70)
    print(f"  测试VQA问题 - {scene_name}")
    print("=" * 70)
    
    # 初始化VQA Pipeline
    pipeline = VQAPipeline()
    if not pipeline.initialize():
        print("❌ Pipeline初始化失败")
        return
    
    # 选择要测试的问题
    if question_categories:
        questions_to_test = []
        for category in question_categories:
            questions = get_questions_by_category(category)
            questions_to_test.extend(questions[:max_per_category])
    else:
        # 每类取几个
        questions_to_test = []
        for category in ['count', 'existence', 'spatial', 'status']:
            questions = get_questions_by_category(category)
            questions_to_test.extend(questions[:max_per_category])
    
    print(f"\n将测试 {len(questions_to_test)} 个问题")
    
    # 测试问题
    results = []
    for i, question in enumerate(questions_to_test, 1):
        print(f"\n{'=' * 70}")
        print(f"问题 {i}/{len(questions_to_test)}: {question}")
        print("=" * 70)
        
        result = pipeline.process_question(question, verbose=True)
        results.append({
            'question': question,
            'success': result.success,
            'cypher': result.cypher_query,
            'answer': result.answer,
            'error': result.error
        })
        
        print(f"\n最终答案: {result.answer}")
    
    # 统计
    success_count = sum(1 for r in results if r['success'])
    print(f"\n{'=' * 70}")
    print("  测试总结")
    print("=" * 70)
    print(f"  总问题数: {len(results)}")
    print(f"  成功: {success_count}")
    print(f"  失败: {len(results) - success_count}")
    print(f"  成功率: {success_count / len(results) * 100:.1f}%")
    
    return results


def main():
    print("=" * 70)
    print("  VQA覆盖率测试")
    print("=" * 70)
    
    # 加载场景清单
    manifest_path = os.path.join(config.OUTPUT_DIR, "coverage_analysis", "scenes_manifest.json")
    with open(manifest_path, 'r', encoding='utf-8') as f:
        scenes = json.load(f)
    
    print(f"\n找到 {len(scenes)} 个场景:")
    for i, scene in enumerate(scenes):
        print(f"  {i+1}. {scene['type']}: {scene['scene_name']} 帧{scene['frame']}")
        print(f"     对象数: {scene['object_count']}")
        print(f"     描述: {scene['description']}")
    
    # Neo4j配置
    neo4j_uri = "bolt://localhost:7600"
    neo4j_user = "neo4j"
    neo4j_password = "87017563"
    
    # 测试每个场景
    for scene_info in scenes:
        print(f"\n{'#' * 70}")
        print(f"#  开始测试: {scene_info['type']}")
        print(f"{'#' * 70}")
        
        # 加载场景图
        print(f"\n加载场景图: {scene_info['filepath']}")
        scene_graph = load_scene_graph(scene_info['filepath'])
        
        # 导入Neo4j
        if not import_to_neo4j(scene_graph, neo4j_uri, neo4j_user, neo4j_password):
            continue
        
        # 根据场景类型选择问题
        if "高密度" in scene_info['type']:
            # 高密度场景：测试计数、空间关系、复合问题
            categories = ['count', 'spatial', 'complex']
            print(f"\n高密度场景，测试问题类型: {categories}")
        else:
            # 低密度场景：测试存在性、状态、比较问题
            categories = ['existence', 'status', 'comparison']
            print(f"\n低密度场景，测试问题类型: {categories}")
        
        # 测试VQA
        results = test_vqa_questions(
            scene_info['scene_name'],
            question_categories=categories,
            max_per_category=3
        )
        
        # 保存结果
        output_dir = os.path.join(config.OUTPUT_DIR, "coverage_analysis", "vqa_results")
        os.makedirs(output_dir, exist_ok=True)
        
        result_file = os.path.join(
            output_dir,
            f"{scene_info['scene_name']}_frame{scene_info['frame']}_results.json"
        )
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                'scene': scene_info,
                'results': results
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 结果已保存: {result_file}")
    
    print(f"\n{'=' * 70}")
    print("  所有场景测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
