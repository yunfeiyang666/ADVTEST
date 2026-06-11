"""
VQA覆盖率测试 - 测试6个场景（2组低-中-高密度）
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from import_single_scene_to_neo4j import Neo4jImporter
from vqa_pipeline import VQAPipeline
from vqa_pipeline.sample_questions import get_questions_by_category
import config


class Logger:
    """同时输出到屏幕和文件的日志类"""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, 'w', encoding='utf-8')
    
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()  # 立即写入
    
    def flush(self):
        self.terminal.flush()
        self.log.flush()
    
    def close(self):
        self.log.close()


def load_scene_graph(filepath):
    """加载场景图"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def import_to_neo4j(scene_graph, scene_name, frame_idx):
    """导入场景图到Neo4j"""
    print("\n" + "=" * 70)
    print(f"  导入场景到Neo4j: {scene_name} 帧{frame_idx}")
    print("=" * 70)
    
    neo4j_uri = "bolt://localhost:7600"
    neo4j_user = "neo4j"
    neo4j_password = "87017563"
    
    importer = Neo4jImporter(neo4j_uri, neo4j_user, neo4j_password)
    
    try:
        print("\n清空现有数据...")
        importer.clear_database()
        
        print("创建约束...")
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
        import traceback
        traceback.print_exc()
        return False
    finally:
        importer.close()


def test_scene_vqa(scene_name, frame_idx, density_type, questions_config):
    """测试单个场景的VQA"""
    print("\n" + "#" * 70)
    print(f"#  测试场景: {scene_name} 帧{frame_idx} ({density_type})")
    print("#" * 70)
    
    # 初始化VQA Pipeline
    pipeline = VQAPipeline()
    if not pipeline.initialize():
        print("❌ Pipeline初始化失败")
        return None
    
    # 选择问题
    questions_to_test = []
    for category, count in questions_config.items():
        questions = get_questions_by_category(category)
        questions_to_test.extend(questions[:count])
    
    print(f"\n将测试 {len(questions_to_test)} 个问题")
    print(f"问题类型: {list(questions_config.keys())}")
    
    # 测试问题
    results = []
    for i, question in enumerate(questions_to_test, 1):
        print(f"\n{'=' * 70}")
        print(f"问题 [{i}/{len(questions_to_test)}]: {question}")
        print("=" * 70)
        
        result = pipeline.process_question(question, verbose=True)
        results.append({
            'question': question,
            'success': result.success,
            'cypher': result.cypher_query,
            'answer': result.answer,
            'error': result.error
        })
        
        if not result.success:
            print(f"\n❌ 失败: {result.error}")
        else:
            print(f"\n✅ 成功")
    
    # 统计
    success_count = sum(1 for r in results if r['success'])
    print(f"\n{'=' * 70}")
    print(f"  {scene_name} 帧{frame_idx} 测试总结")
    print("=" * 70)
    print(f"  总问题数: {len(results)}")
    print(f"  成功: {success_count}")
    print(f"  失败: {len(results) - success_count}")
    print(f"  成功率: {success_count / len(results) * 100:.1f}%")
    
    return results


def main():
    # 创建日志文件
    output_dir = os.path.join(
        config.OUTPUT_DIR,
        "coverage_analysis",
        "vqa_results"
    )
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"test_log_{timestamp}.txt")
    
    # 启动日志记录
    logger = Logger(log_file)
    original_stdout = sys.stdout
    sys.stdout = logger
    
    try:
        print("=" * 70)
        print("  VQA覆盖率测试 - 6个场景（2组低-中-高密度）")
        print("=" * 70)
        print(f"\n📝 日志文件: {log_file}")
        
        print("\n⚠️  请确保Neo4j数据库已启动！")
        print("   启动命令: E:\\node4j\\neo4j-community-2025.10.1\\bin\\neo4j console\n")
        
        # 恢复标准输入以便接收用户输入
        sys.stdout = original_stdout
        input("按Enter继续...")
        sys.stdout = logger
    
    # 加载场景清单
    manifest_path = os.path.join(
        config.OUTPUT_DIR,
        "coverage_analysis",
        "scene_graphs",
        "manifest.json"
    )
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        scenes = json.load(f)
    
    print(f"\n找到 {len(scenes)} 个场景")
    
    # 定义测试配置
    test_configs = [
        # 组1 - 低密度
        {
            'scene': scenes[0],
            'density': '低密度',
            'questions': {'existence': 2, 'count': 2, 'status': 2}
        },
        # 组2 - 低密度
        {
            'scene': scenes[1],
            'density': '低密度',
            'questions': {'existence': 2, 'count': 2, 'status': 2}
        },
        # 组1 - 中密度
        {
            'scene': scenes[2],
            'density': '中密度',
            'questions': {'count': 2, 'spatial': 2, 'comparison': 2}
        },
        # 组2 - 中密度
        {
            'scene': scenes[3],
            'density': '中密度',
            'questions': {'count': 2, 'spatial': 2, 'comparison': 2}
        },
        # 组1 - 高密度
        {
            'scene': scenes[4],
            'density': '高密度',
            'questions': {'count': 2, 'spatial': 2, 'complex': 2}
        },
        # 组2 - 高密度
        {
            'scene': scenes[5],
            'density': '高密度',
            'questions': {'count': 2, 'spatial': 2, 'complex': 2}
        }
    ]
    
    # 创建输出目录
    output_dir = os.path.join(
        config.OUTPUT_DIR,
        "coverage_analysis",
        "vqa_results"
    )
    os.makedirs(output_dir, exist_ok=True)
    
    # 测试每个场景
    all_results = []
    
    for i, test_config in enumerate(test_configs, 1):
        scene_info = test_config['scene']
        scene_name = scene_info['scene_name']
        frame_idx = scene_info['frame_idx']
        density = test_config['density']
        
        print(f"\n{'#' * 70}")
        print(f"#  [{i}/6] 测试 {density}: {scene_name} 帧{frame_idx}")
        print(f"#  对象数: {scene_info['total_objects']}")
        print(f"#  描述: {scene_info['description']}")
        print(f"{'#' * 70}")
        
        # 加载并导入场景图
        scene_graph = load_scene_graph(scene_info['filepath'])
        
        if not import_to_neo4j(scene_graph, scene_name, frame_idx):
            print(f"\n❌ 跳过场景 {scene_name}")
            continue
        
        # 测试VQA
        results = test_scene_vqa(
            scene_name,
            frame_idx,
            density,
            test_config['questions']
        )
        
        if results:
            # 保存结果
            result_file = os.path.join(
                output_dir,
                f"{scene_name}_frame{frame_idx}_{density}_results.json"
            )
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'scene_name': scene_name,
                    'frame_idx': frame_idx,
                    'density': density,
                    'total_objects': scene_info['total_objects'],
                    'description': scene_info['description'],
                    'type_count': scene_info['type_count'],
                    'test_config': test_config['questions'],
                    'results': results,
                    'summary': {
                        'total': len(results),
                        'success': sum(1 for r in results if r['success']),
                        'failed': sum(1 for r in results if not r['success']),
                        'success_rate': sum(1 for r in results if r['success']) / len(results) * 100
                    }
                }, f, indent=2, ensure_ascii=False)
            
            print(f"\n✓ 结果已保存: {result_file}")
            
            all_results.append({
                'scene': scene_name,
                'frame': frame_idx,
                'density': density,
                'objects': scene_info['total_objects'],
                'summary': {
                    'total': len(results),
                    'success': sum(1 for r in results if r['success']),
                    'success_rate': sum(1 for r in results if r['success']) / len(results) * 100
                }
            })
    
    # 总结报告
    print(f"\n{'=' * 70}")
    print("  整体测试总结")
    print("=" * 70)
    
    print("\n【组1】")
    for result in all_results[:3]:
        print(f"  {result['density']}: {result['scene']} 帧{result['frame']}")
        print(f"    对象数: {result['objects']}")
        print(f"    成功率: {result['summary']['success_rate']:.1f}% "
              f"({result['summary']['success']}/{result['summary']['total']})")
    
    print("\n【组2】")
    for result in all_results[3:]:
        print(f"  {result['density']}: {result['scene']} 帧{result['frame']}")
        print(f"    对象数: {result['objects']}")
        print(f"    成功率: {result['summary']['success_rate']:.1f}% "
              f"({result['summary']['success']}/{result['summary']['total']})")
    
        # 保存总结
        summary_file = os.path.join(output_dir, "overall_summary.json")
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 总结已保存: {summary_file}")
        
        print(f"\n{'=' * 70}")
        print("  所有测试完成！")
        print("=" * 70)
        print(f"\n📝 完整日志已保存至: {log_file}")
        
    finally:
        # 恢复标准输出并关闭日志
        sys.stdout = original_stdout
        logger.close()
        print(f"\n✓ 日志文件已保存: {log_file}")


if __name__ == "__main__":
    main()
