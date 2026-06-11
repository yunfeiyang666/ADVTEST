"""
VQA覆盖率分析 - 完整版
1. 根据场景密度匹配VQA问题
2. 区分原始标注对象和计算关系
3. 分析覆盖率
4. 记录完整日志
"""
import os
import sys
import json
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from import_single_scene_to_neo4j import Neo4jImporter
from vqa_pipeline import VQAPipeline
from vqa_pipeline.sample_questions import NUSCENES_QA_QUESTIONS
import config


class Logger:
    """日志记录器"""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, 'w', encoding='utf-8')
    
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()
    
    def flush(self):
        self.terminal.flush()
        self.log.flush()
    
    def close(self):
        self.log.close()


def select_questions_by_scene_density(density, object_count):
    """根据场景密度选择合适的VQA问题"""
    selected = []
    
    if density == '低密度':
        # 低密度场景：基础问题
        selected.extend([
            ("existence", "场景中有行人吗？"),
            ("existence", "ego车前方有车辆吗？"),
            ("count", "场景中有多少辆车？"),
            ("count", "场景中有多少个行人？"),
            ("status", "离ego最近的车辆是哪个？"),
            ("spatial", "ego车前方有哪些对象？"),
        ])
    
    elif density == '中密度':
        # 中密度场景：空间关系和比较
        selected.extend([
            ("count", "场景中有多少辆车？"),
            ("count", "ego车前方有多少个对象？"),
            ("spatial", "ego车前方有哪些对象？"),
            ("spatial", "哪些对象在ego的后方？"),
            ("comparison", "场景中车辆多还是行人多？"),
            ("comparison", "ego前方和后方哪边的对象更多？"),
        ])
    
    else:  # 高密度
        # 高密度场景：复合问题
        selected.extend([
            ("count", "场景中有多少辆车？"),
            ("count", "距离ego车10米内有多少个对象？"),
            ("spatial", "ego车前方有哪些对象？"),
            ("spatial", "ego右侧最近的对象是什么？"),
            ("complex", "ego车前方最近的车辆是哪个？它距离ego多远？"),
            ("complex", "有多少个行人在ego的前方且距离小于20米？"),
        ])
    
    return selected


def analyze_scene_graph_coverage(scene_graph):
    """分析场景图的全集内容"""
    analysis = {
        'total_objects': len(scene_graph['nodes']),
        'total_relationships': len(scene_graph['edges']),
        'object_types': defaultdict(int),
        'relationship_patterns': defaultdict(int),
        'spatial_predicates': defaultdict(int),
        'distance_predicates': defaultdict(int),
    }
    
    # 统计对象类型
    for node in scene_graph['nodes']:
        obj_type = node['type']
        analysis['object_types'][obj_type] += 1
    
    # 统计关系模式
    for edge in scene_graph['edges']:
        source_type = edge['source_type']
        target_type = edge['target_type']
        pattern = f"{source_type}->{target_type}"
        analysis['relationship_patterns'][pattern] += 1
        
        # 统计谓词
        if 'predicates' in edge:
            for pred in edge['predicates']:
                if pred in ['front', 'left', 'right', 'rear']:
                    analysis['spatial_predicates'][pred] += 1
                elif pred in ['near', 'mid', 'far']:
                    analysis['distance_predicates'][pred] += 1
    
    return analysis


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
        
        print("\n导入场景图...")
        importer.import_scene(scene_graph)
        
        print("\n✓ 导入完成！")
        
        # 验证
        with importer.driver.session() as session:
            result = session.run("MATCH (n:Object) RETURN count(n) as count")
            node_count = result.single()['count']
            
            result = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count")
            edge_count = result.single()['count']
            
            print(f"\n【数据库验证】")
            print(f"  对象节点: {node_count}")
            print(f"  关系边: {edge_count}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        importer.close()


def test_vqa_questions(questions, scene_name, frame_idx):
    """测试VQA问题"""
    print("\n" + "#" * 70)
    print(f"#  开始VQA测试: {scene_name} 帧{frame_idx}")
    print("#" * 70)
    
    pipeline = VQAPipeline()
    if not pipeline.initialize():
        print("❌ Pipeline初始化失败")
        return None
    
    print(f"\n共 {len(questions)} 个问题")
    
    results = []
    for i, (category, question) in enumerate(questions, 1):
        print(f"\n{'=' * 70}")
        print(f"[{i}/{len(questions)}] 类别: {category}")
        print(f"问题: {question}")
        print("=" * 70)
        
        result = pipeline.process_question(question, verbose=True)
        
        results.append({
            'category': category,
            'question': question,
            'success': result.success,
            'cypher': result.cypher_query,
            'answer': result.answer,
            'error': result.error,
            'query_result_count': len(result.query_results) if result.query_results else 0
        })
        
        if result.success:
            print(f"\n✅ 成功")
        else:
            print(f"\n❌ 失败: {result.error}")
    
    return results


def analyze_coverage(scene_analysis, vqa_results):
    """分析覆盖率"""
    print("\n" + "=" * 70)
    print("  覆盖率分析")
    print("=" * 70)
    
    # 统计成功的问题
    success_by_category = defaultdict(lambda: {'total': 0, 'success': 0})
    
    for result in vqa_results:
        category = result['category']
        success_by_category[category]['total'] += 1
        if result['success']:
            success_by_category[category]['success'] += 1
    
    print("\n【按类别的成功率】")
    for category, stats in sorted(success_by_category.items()):
        rate = stats['success'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"  {category}: {stats['success']}/{stats['total']} ({rate:.1f}%)")
    
    # 分析查询到的对象类型
    queried_objects = set()
    for result in vqa_results:
        if result['success'] and result.get('query_result_count', 0) > 0:
            queried_objects.add(result['question'])
    
    print(f"\n【场景图全集】")
    print(f"  总对象数: {scene_analysis['total_objects']}")
    print(f"  总关系数: {scene_analysis['total_relationships']}")
    print(f"\n  对象类型分布:")
    for obj_type, count in sorted(scene_analysis['object_types'].items(), key=lambda x: -x[1]):
        print(f"    {obj_type}: {count}")
    
    print(f"\n  空间关系分布:")
    for pred, count in sorted(scene_analysis['spatial_predicates'].items(), key=lambda x: -x[1]):
        print(f"    {pred}: {count}")
    
    print(f"\n  距离关系分布:")
    for pred, count in sorted(scene_analysis['distance_predicates'].items(), key=lambda x: -x[1]):
        print(f"    {pred}: {count}")
    
    # 总体覆盖率
    total_questions = len(vqa_results)
    successful_questions = sum(1 for r in vqa_results if r['success'])
    overall_rate = successful_questions / total_questions * 100 if total_questions > 0 else 0
    
    print(f"\n【总体覆盖率】")
    print(f"  成功问题: {successful_questions}/{total_questions} ({overall_rate:.1f}%)")
    
    return {
        'success_by_category': dict(success_by_category),
        'overall_success_rate': overall_rate,
        'scene_analysis': scene_analysis
    }


def main():
    # 创建日志
    output_dir = os.path.join(config.OUTPUT_DIR, "coverage_analysis", "vqa_results")
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"coverage_test_{timestamp}.txt")
    
    logger = Logger(log_file)
    original_stdout = sys.stdout
    sys.stdout = logger
    
    try:
        print("=" * 70)
        print("  VQA覆盖率分析 - 完整版")
        print("=" * 70)
        print(f"\n📝 日志文件: {log_file}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        print("\n⚠️  请确保Neo4j数据库已启动！")
        print("   启动命令: E:\\node4j\\neo4j-community-2025.10.1\\bin\\neo4j console\n")
        
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
        
        # 配置测试
        test_configs = [
            {'scene_idx': 0, 'density': '低密度'},
            {'scene_idx': 1, 'density': '低密度'},
            {'scene_idx': 2, 'density': '中密度'},
            {'scene_idx': 3, 'density': '中密度'},
            {'scene_idx': 4, 'density': '高密度'},
            {'scene_idx': 5, 'density': '高密度'},
        ]
        
        all_results = []
        
        for i, config_item in enumerate(test_configs, 1):
            scene_info = scenes[config_item['scene_idx']]
            scene_name = scene_info['scene_name']
            frame_idx = scene_info['frame_idx']
            density = config_item['density']
            
            print(f"\n{'#' * 70}")
            print(f"#  [{i}/6] 测试场景: {scene_name} 帧{frame_idx}")
            print(f"#  密度: {density}")
            print(f"#  对象数: {scene_info['total_objects']}")
            print(f"#  描述: {scene_info['description']}")
            print(f"{'#' * 70}")
            
            # 加载场景图
            scene_graph = load_scene_graph(scene_info['filepath'])
            
            # 分析场景图全集
            print("\n【分析场景图全集】")
            scene_analysis = analyze_scene_graph_coverage(scene_graph)
            print(f"  对象: {scene_analysis['total_objects']}")
            print(f"  关系: {scene_analysis['total_relationships']}")
            print(f"  对象类型: {len(scene_analysis['object_types'])}")
            print(f"  关系模式: {len(scene_analysis['relationship_patterns'])}")
            
            # 导入Neo4j
            if not import_to_neo4j(scene_graph, scene_name, frame_idx):
                print(f"\n❌ 跳过场景 {scene_name}")
                continue
            
            # 选择匹配的VQA问题
            questions = select_questions_by_scene_density(density, scene_info['total_objects'])
            print(f"\n【选择VQA问题】")
            print(f"  根据{density}选择 {len(questions)} 个问题")
            for cat, q in questions:
                print(f"    [{cat}] {q}")
            
            # 测试VQA
            vqa_results = test_vqa_questions(questions, scene_name, frame_idx)
            
            if not vqa_results:
                continue
            
            # 分析覆盖率
            coverage = analyze_coverage(scene_analysis, vqa_results)
            
            # 保存结果
            result_file = os.path.join(
                output_dir,
                f"{scene_name}_frame{frame_idx}_{density}_coverage.json"
            )
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'scene_name': scene_name,
                    'frame_idx': frame_idx,
                    'density': density,
                    'scene_info': scene_info,
                    'scene_analysis': scene_analysis,
                    'vqa_results': vqa_results,
                    'coverage_analysis': coverage
                }, f, indent=2, ensure_ascii=False)
            
            print(f"\n✓ 结果已保存: {result_file}")
            
            all_results.append({
                'scene': scene_name,
                'frame': frame_idx,
                'density': density,
                'coverage_rate': coverage['overall_success_rate']
            })
        
        # 总结
        print(f"\n{'=' * 70}")
        print("  最终总结")
        print("=" * 70)
        
        for result in all_results:
            print(f"\n{result['density']}: {result['scene']} 帧{result['frame']}")
            print(f"  覆盖率: {result['coverage_rate']:.1f}%")
        
        print(f"\n⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\n📝 完整日志: {log_file}")
        
    finally:
        sys.stdout = original_stdout
        logger.close()
        print(f"\n✓ 日志已保存: {log_file}")


if __name__ == "__main__":
    main()
