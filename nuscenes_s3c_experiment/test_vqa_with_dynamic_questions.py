"""
VQA覆盖率测试 - 使用动态生成的场景特定问题
"""
import os
import sys
import json
from datetime import datetime
from collections import defaultdict
import random

from vqa_pipeline.object_utils import build_indexed_objects, pretty_options_from_indexed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from import_single_scene_to_neo4j import Neo4jImporter
from vqa_pipeline import VQAPipeline
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


def get_chinese_name(obj_type):
    """获取对象类型的中文名"""
    mapping = {
        'car': '车辆', 'pedestrian': '行人', 'truck': '卡车',
        'bus': '公交车', 'bicycle': '自行车', 'motorcycle': '摩托车',
    }
    return mapping.get(obj_type, obj_type)


def generate_high_coverage_questions(scene_graph, density, max_distance: float = 40.0):
    """生成高覆盖率的场景特定问题。

    说明：
    - 只考虑距离ego在 max_distance 米以内的对象，过滤掉远端小目标；
    - 其余逻辑与原实现一致。
    """
    objects_by_type = defaultdict(list)

    # 距离过滤：只保留近处对象
    from vqa_pipeline.object_utils import filter_nodes_by_distance  # 局部导入避免循环
    nearby_nodes = filter_nodes_by_distance(scene_graph, max_distance=max_distance, include_ego=False)

    for node in nearby_nodes:
        unique_id = node['unique_id']
        obj_type = node['type']
        objects_by_type[obj_type].append(unique_id)
    
    questions = []
    covered_objects = set()
    
    print(f"\n【场景对象统计】")
    for obj_type, ids in sorted(objects_by_type.items(), key=lambda x: -len(x[1])):
        print(f"  {obj_type}: {len(ids)} 个")
    
    # 1. 存在性 - 覆盖所有类型
    print(f"\n【生成存在性问题】")
    for obj_type in ['car', 'pedestrian', 'truck', 'bus', 'bicycle', 'motorcycle']:
        if obj_type in objects_by_type:
            questions.append(("existence", f"场景中有{get_chinese_name(obj_type)}吗？"))
        else:
            questions.append(("existence", f"场景中有{get_chinese_name(obj_type)}吗？"))
    
    # 2. 计数 - 每种类型都问
    print(f"【生成计数问题】")
    for obj_type, ids in objects_by_type.items():
        questions.append(("count", f"场景中有多少个{get_chinese_name(obj_type)}？"))
    
    questions.append(("count", "ego车前方有多少个对象？"))
    questions.append(("count", "距离ego车10米内有多少个对象？"))
    
    # 3. 状态 - 尽量覆盖多个对象
    print(f"【生成状态问题】")
    
    # 对每种类型的前几个对象提问
    for obj_type, ids in objects_by_type.items():
        sample_size = min(3, len(ids))  # 每种类型采样3个
        for obj_id in ids[:sample_size]:
            questions.append(("status", f"{obj_id}距离ego多远？"))
            questions.append(("status", f"{obj_id}在ego的什么方向？"))
            covered_objects.add(obj_id)
    
    # 最近/最远
    if 'car' in objects_by_type:
        questions.append(("status", "离ego最近的车辆是哪个？"))
    if 'pedestrian' in objects_by_type:
        questions.append(("status", "离ego最远的行人是哪个？"))
    
    # 4. 空间关系 - 对象对组合
    print(f"【生成空间关系问题】")
    questions.append(("spatial", "ego车前方有哪些对象？"))
    questions.append(("spatial", "哪些对象在ego的后方？"))
    questions.append(("spatial", "ego右侧最近的对象是什么？"))
    
    # 对象间关系 - 采样多个对象对
    all_ids = [obj_id for ids in objects_by_type.values() for obj_id in ids]
    if len(all_ids) >= 2:
        # 随机选择几对
        for _ in range(min(5, len(all_ids) // 2)):
            if len(all_ids) >= 2:
                obj1 = random.choice(all_ids)
                obj2 = random.choice([o for o in all_ids if o != obj1])
                questions.append(("spatial", f"{obj1}和{obj2}之间的空间关系是什么？"))
                covered_objects.update([obj1, obj2])
    
    # 5. 比较
    print(f"【生成比较问题】")
    types = list(objects_by_type.keys())
    if len(types) >= 2:
        type1, type2 = types[0], types[1]
        questions.append(("comparison", f"场景中{get_chinese_name(type1)}多还是{get_chinese_name(type2)}多？"))
    
    questions.append(("comparison", "哪种类型的对象数量最多？"))
    questions.append(("comparison", "ego前方和后方哪边的对象更多？"))
    
    # 如果有多个同类对象，比较距离
    for obj_type, ids in objects_by_type.items():
        if len(ids) >= 2:
            obj1, obj2 = ids[0], ids[1]
            questions.append(("comparison", f"{obj1}和{obj2}哪个离ego更近？"))
            covered_objects.update([obj1, obj2])
    
    # 6. 复合问题
    print(f"【生成复合问题】")
    questions.append(("complex", "列出所有在ego车10米范围内的对象及其类型"))
    questions.append(("complex", "ego车周围最密集的方向是哪个？有多少对象？"))
    
    if 'car' in objects_by_type:
        questions.append(("complex", "ego车前方最近的车辆是哪个？它距离ego多远？"))
    
    if 'pedestrian' in objects_by_type:
        questions.append(("complex", "有多少个行人在ego的前方且距离小于20米？"))
        
        if 'car' in objects_by_type and len(objects_by_type['car']) > 0:
            car_id = objects_by_type['car'][0]
            questions.append(("complex", f"{car_id}前方有哪些行人？分别距离多远？"))
            covered_objects.add(car_id)
    
    # 统计覆盖率
    total_objects = sum(len(ids) for ids in objects_by_type.values())
    coverage_rate = len(covered_objects) / total_objects * 100 if total_objects > 0 else 0
    
    print(f"\n【问题生成总结】")
    print(f"  总问题数: {len(questions)}")
    print(f"  场景对象数: {total_objects}")
    print(f"  明确提及的对象: {len(covered_objects)}")
    print(f"  对象覆盖率: {coverage_rate:.1f}%")
    
    # 根据密度筛选问题
    if density == '低密度':
        selected = [q for q in questions if q[0] in ['existence', 'count', 'status']]
        selected = selected[:15]
    elif density == '中密度':
        selected = [q for q in questions if q[0] in ['count', 'spatial', 'comparison', 'status']]
        selected = selected[:20]
    else:  # 高密度
        selected = questions[:25]
    
    print(f"  根据{density}筛选: {len(selected)} 个问题")
    
    return selected, covered_objects


def load_scene_graph(filepath):
    """加载场景图"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def import_to_neo4j(scene_graph, scene_name, frame_idx):
    """导入场景图到Neo4j"""
    print("\n" + "=" * 70)
    print(f"  导入场景到Neo4j: {scene_name} 帧{frame_idx}")
    print("=" * 70)
    
    importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
    
    try:
        print("\n清空数据...")
        importer.clear_database()
        print("创建约束...")
        importer.create_constraints()
        print("导入场景图...")
        importer.import_scene(scene_graph)
        
        with importer.driver.session() as session:
            result = session.run("MATCH (n:Object) RETURN count(n) as count")
            node_count = result.single()['count']
            result = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count")
            edge_count = result.single()['count']
            
            print(f"\n✓ 导入完成: {node_count} 个对象, {edge_count} 条关系")
        
        return True
    except Exception as e:
        print(f"\n❌ 导入失败: {e}")
        return False
    finally:
        importer.close()


def test_questions(questions, scene_name, frame_idx):
    """测试VQA问题"""
    print("\n" + "#" * 70)
    print(f"#  VQA测试: {scene_name} 帧{frame_idx}")
    print("#" * 70)
    
    pipeline = VQAPipeline()
    if not pipeline.initialize():
        print("❌ Pipeline初始化失败")
        return None
    
    results = []
    for i, (category, question) in enumerate(questions, 1):
        print(f"\n{'=' * 70}")
        print(f"[{i}/{len(questions)}] [{category}] {question}")
        print("=" * 70)
        
        result = pipeline.process_question(question, verbose=True)
        
        results.append({
            'category': category,
            'question': question,
            'success': result.success,
            'cypher': result.cypher_query,
            'answer': result.answer,
            'error': result.error
        })
        
        print(f"\n{'✅' if result.success else '❌'} {'成功' if result.success else '失败'}")
    
    return results


def main():
    output_dir = os.path.join(config.OUTPUT_DIR, "coverage_analysis", "vqa_results")
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"dynamic_questions_{timestamp}.txt")
    
    logger = Logger(log_file)
    original_stdout = sys.stdout
    sys.stdout = logger
    
    try:
        print("=" * 70)
        print("  VQA覆盖率测试 - 动态生成场景特定问题")
        print("=" * 70)
        print(f"\n📝 日志文件: {log_file}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        print("\n⚠️  请确保Neo4j数据库已启动！\n")
        
        sys.stdout = original_stdout
        input("按Enter继续...")
        sys.stdout = logger
        
        manifest_path = os.path.join(
            config.OUTPUT_DIR, "coverage_analysis", "scene_graphs", "manifest.json"
        )
        
        with open(manifest_path, 'r', encoding='utf-8') as f:
            scenes = json.load(f)
        
        test_configs = [
            {'idx': 0, 'density': '低密度'},
            {'idx': 1, 'density': '低密度'},
            {'idx': 2, 'density': '中密度'},
            {'idx': 3, 'density': '中密度'},
            {'idx': 4, 'density': '高密度'},
            {'idx': 5, 'density': '高密度'},
        ]
        
        all_results = []
        
        for i, cfg in enumerate(test_configs, 1):
            scene_info = scenes[cfg['idx']]
            scene_name = scene_info['scene_name']
            frame_idx = scene_info['frame_idx']
            density = cfg['density']
            
            print(f"\n{'#' * 70}")
            print(f"#  [{i}/6] {density}: {scene_name} 帧{frame_idx}")
            print(f"#  描述: {scene_info['description']}")
            print(f"{'#' * 70}")
            
            scene_graph = load_scene_graph(scene_info['filepath'])

            # 为该场景构建基于距离的对象索引（用于选项、可视化）
            indexed_objs, id_to_index = build_indexed_objects(scene_graph, max_distance=40.0)
            options_lines = pretty_options_from_indexed(indexed_objs)

            print("\n[对象索引与选项] (仅展示前20个)")
            for line in options_lines[:20]:
                print("  " + line)

            # 动态生成问题（同样基于距离过滤后的对象）
            questions, covered_objects = generate_high_coverage_questions(scene_graph, density, max_distance=40.0)
            
            if not import_to_neo4j(scene_graph, scene_name, frame_idx):
                continue
            
            results = test_questions(questions, scene_name, frame_idx)
            
            if results:
                success_count = sum(1 for r in results if r['success'])
                success_rate = success_count / len(results) * 100
                
                print(f"\n{'=' * 70}")
                print(f"  测试总结")
                print("=" * 70)
                print(f"  问题数: {len(results)}")
                print(f"  成功: {success_count}/{len(results)} ({success_rate:.1f}%)")
                print(f"  对象覆盖: {len(covered_objects)} 个")
                
                result_file = os.path.join(
                    output_dir,
                    f"{scene_name}_frame{frame_idx}_dynamic.json"
                )
                
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'scene_name': scene_name,
                        'frame_idx': frame_idx,
                        'density': density,
                        'questions': questions,
                        'results': results,
'covered_objects': sorted(covered_objects),
                        'object_options': {
                            'objects': [
                                {
                                    'index': idx,
                                    'unique_id': obj.unique_id,
                                    'type': obj.obj_type,
                                    'distance_from_ego': round(obj.distance_from_ego, 2),
                                    'status': obj.status,
                                }
                                for idx, obj in enumerate(indexed_objs, start=1)
                            ],
                        },
                        'summary': {
                            'total_questions': len(results),
                            'success': success_count,
                            'success_rate': success_rate,
                            'object_coverage': len(covered_objects)
                        }
                    }, f, indent=2, ensure_ascii=False)
                
                print(f"\n✓ 结果已保存: {result_file}")
                
                all_results.append({
                    'scene': scene_name,
                    'frame': frame_idx,
                    'density': density,
                    'success_rate': success_rate,
                    'object_coverage': len(covered_objects)
                })
        
        print(f"\n{'=' * 70}")
        print("  最终总结")
        print("=" * 70)
        
        for res in all_results:
            print(f"\n{res['density']}: {res['scene']} 帧{res['frame']}")
            print(f"  成功率: {res['success_rate']:.1f}%")
            print(f"  对象覆盖: {res['object_coverage']} 个")
        
        print(f"\n⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    finally:
        sys.stdout = original_stdout
        logger.close()
        print(f"\n✓ 日志已保存: {log_file}")


if __name__ == "__main__":
    main()
