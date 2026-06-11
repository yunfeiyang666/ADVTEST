"""
NuScenes官方QA基线测试
使用官方QA数据集中我们6个场景的问题
"""
import os
import sys
import json
from datetime import datetime
from collections import defaultdict

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


def load_official_qa(qa_file_path):
    """加载官方QA数据"""
    print(f"加载官方QA数据: {qa_file_path}")
    with open(qa_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    questions_list = data['questions']
    print(f"  总问题数: {len(questions_list)}")
    
    # 按sample_token索引
    qa_by_sample = defaultdict(list)
    for qa in questions_list:
        sample_token = qa['sample_token']
        qa_by_sample[sample_token].append(qa)
    
    print(f"  覆盖场景数: {len(qa_by_sample)}")
    
    return qa_by_sample


def get_sample_token_for_scene(nusc, scene_name, frame_idx):
    """获取指定场景帧的sample_token"""
    for scene in nusc.scene:
        if scene['name'] == scene_name:
            sample_token = scene['first_sample_token']
            current_frame = 0
            
            while sample_token and current_frame < frame_idx:
                sample = nusc.get('sample', sample_token)
                sample_token = sample['next']
                current_frame += 1
            
            if sample_token:
                return sample_token
            break
    
    return None


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
        print("清空数据...")
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
            
            print(f"✓ 导入完成: {node_count} 个对象, {edge_count} 条关系")
        
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False
    finally:
        importer.close()


def test_official_questions(official_qa_list, scene_name, frame_idx):
    """测试官方QA问题"""
    print("\n" + "#" * 70)
    print(f"#  官方QA基线测试: {scene_name} 帧{frame_idx}")
    print("#" * 70)
    
    pipeline = VQAPipeline()
    if not pipeline.initialize():
        print("❌ Pipeline初始化失败")
        return None
    
    # 测试所有问题
    test_questions = official_qa_list
    
    print(f"\n该场景官方问题数: {len(official_qa_list)}")
    print(f"本次测试问题数: {len(test_questions)}")
    
    # 按类型统计
    type_count = defaultdict(int)
    for qa in test_questions:
        type_count[qa['template_type']] += 1
    
    print(f"\n问题类型分布:")
    for qtype, count in sorted(type_count.items(), key=lambda x: -x[1]):
        print(f"  {qtype}: {count}")
    
    results = []
    for i, qa in enumerate(test_questions, 1):
        question = qa['question']
        expected_answer = qa['answer']
        question_type = qa['template_type']
        
        print(f"\n{'=' * 70}")
        print(f"[{i}/{len(test_questions)}] [{question_type}]")
        print(f"问题: {question}")
        print(f"官方答案: {expected_answer}")
        print("=" * 70)
        
        # 翻译成中文（简单映射）
        # 注意：这里先用英文测试，后续可以考虑翻译
        
        result = pipeline.process_question(question, verbose=True)
        
        # 比较答案
        answer_match = False
        if result.success and result.answer:
            # 简单的答案匹配
            answer_lower = result.answer.lower()
            expected_lower = expected_answer.lower()
            answer_match = expected_lower in answer_lower or answer_lower in expected_lower
        
        results.append({
            'question': question,
            'expected_answer': expected_answer,
            'predicted_answer': result.answer,
            'question_type': question_type,
            'success': result.success,
            'answer_match': answer_match,
            'cypher': result.cypher_query,
            'error': result.error
        })
        
        if result.success:
            if answer_match:
                print(f"\n✅ 成功且答案匹配")
            else:
                print(f"\n⚠️ 成功但答案不匹配")
                print(f"  预期: {expected_answer}")
                print(f"  实际: {result.answer}")
        else:
            print(f"\n❌ 失败: {result.error}")
    
    # 统计
    total = len(results)
    success_count = sum(1 for r in results if r['success'])
    match_count = sum(1 for r in results if r['answer_match'])
    
    print(f"\n{'=' * 70}")
    print(f"  测试总结: {scene_name} 帧{frame_idx}")
    print("=" * 70)
    print(f"  总问题数: {total}")
    print(f"  执行成功: {success_count} ({success_count/total*100:.1f}%)")
    print(f"  答案匹配: {match_count} ({match_count/total*100:.1f}%)")
    
    # 按类型统计
    by_type = defaultdict(lambda: {'total': 0, 'success': 0, 'match': 0})
    for r in results:
        qtype = r['question_type']
        by_type[qtype]['total'] += 1
        if r['success']:
            by_type[qtype]['success'] += 1
        if r['answer_match']:
            by_type[qtype]['match'] += 1
    
    print(f"\n按类型统计:")
    for qtype, stats in sorted(by_type.items()):
        print(f"  {qtype}:")
        print(f"    成功率: {stats['success']}/{stats['total']} ({stats['success']/stats['total']*100:.1f}%)")
        print(f"    准确率: {stats['match']}/{stats['total']} ({stats['match']/stats['total']*100:.1f}%)")
    
    return results


def main():
    output_dir = os.path.join(config.OUTPUT_DIR, "coverage_analysis", "vqa_results")
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"official_qa_baseline_{timestamp}.txt")
    
    logger = Logger(log_file)
    original_stdout = sys.stdout
    sys.stdout = logger
    
    try:
        print("=" * 70)
        print("  NuScenes官方QA基线测试")
        print("=" * 70)
        print(f"\n📝 日志文件: {log_file}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 加载NuScenes
        print("\n加载NuScenes数据集...")
        devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
        if devkit_path not in sys.path:
            sys.path.insert(0, devkit_path)
        from nuscenes.nuscenes import NuScenes
        
        nusc = NuScenes(
            version='v1.0-mini',
            dataroot=config.NUSCENES_DATAROOT,
            verbose=False
        )
        
        # 加载官方QA
        qa_file = "E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json"
        qa_by_sample = load_official_qa(qa_file)
        
        print("\n⚠️  请确保Neo4j数据库已启动！\n")
        
        sys.stdout = original_stdout
        input("按Enter继续...")
        sys.stdout = logger
        
        # 加载我们的6个场景
        manifest_path = os.path.join(
            config.OUTPUT_DIR, "coverage_analysis", "scene_graphs", "manifest.json"
        )
        
        with open(manifest_path, 'r', encoding='utf-8') as f:
            scenes = json.load(f)
        
        all_results = []
        
        for i, scene_info in enumerate(scenes, 1):
            scene_name = scene_info['scene_name']
            frame_idx = scene_info['frame_idx']
            
            print(f"\n{'#' * 70}")
            print(f"#  [{i}/6] 测试场景: {scene_name} 帧{frame_idx}")
            print(f"#  描述: {scene_info['description']}")
            print(f"{'#' * 70}")
            
            # 获取sample_token
            sample_token = get_sample_token_for_scene(nusc, scene_name, frame_idx)
            
            if not sample_token:
                print(f"❌ 无法找到sample_token")
                continue
            
            print(f"\nSample Token: {sample_token}")
            
            # 查找官方问题
            official_qa = qa_by_sample.get(sample_token, [])
            
            if not official_qa:
                print(f"⚠️ 该场景没有官方QA问题")
                continue
            
            print(f"找到 {len(official_qa)} 个官方问题")
            
            # 导入场景图
            scene_graph = load_scene_graph(scene_info['filepath'])
            
            if not import_to_neo4j(scene_graph, scene_name, frame_idx):
                continue
            
            # 测试官方问题（全部）
            results = test_official_questions(official_qa, scene_name, frame_idx)
            
            if results:
                # 保存结果
                result_file = os.path.join(
                    output_dir,
                    f"{scene_name}_frame{frame_idx}_official_qa.json"
                )
                
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'scene_name': scene_name,
                        'frame_idx': frame_idx,
                        'sample_token': sample_token,
                        'total_official_questions': len(official_qa),
                        'tested_questions': len(results),
                        'results': results,
                        'summary': {
                            'success_rate': sum(1 for r in results if r['success']) / len(results) * 100,
                            'accuracy': sum(1 for r in results if r['answer_match']) / len(results) * 100
                        }
                    }, f, indent=2, ensure_ascii=False)
                
                print(f"\n✓ 结果已保存: {result_file}")
                
                all_results.append({
                    'scene': scene_name,
                    'frame': frame_idx,
                    'total_qa': len(official_qa),
                    'tested': len(results),
                    'success_rate': sum(1 for r in results if r['success']) / len(results) * 100,
                    'accuracy': sum(1 for r in results if r['answer_match']) / len(results) * 100
                })
        
        print(f"\n{'=' * 70}")
        print("  最终总结")
        print("=" * 70)
        
        for res in all_results:
            print(f"\n{res['scene']} 帧{res['frame']}")
            print(f"  官方问题: {res['total_qa']} 个")
            print(f"  测试数量: {res['tested']} 个")
            print(f"  执行成功率: {res['success_rate']:.1f}%")
            print(f"  答案准确率: {res['accuracy']:.1f}%")
        
        if all_results:
            avg_success = sum(r['success_rate'] for r in all_results) / len(all_results)
            avg_accuracy = sum(r['accuracy'] for r in all_results) / len(all_results)
            print(f"\n总体平均:")
            print(f"  执行成功率: {avg_success:.1f}%")
            print(f"  答案准确率: {avg_accuracy:.1f}%")
        
        print(f"\n⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    finally:
        sys.stdout = original_stdout
        logger.close()
        print(f"\n✓ 日志已保存: {log_file}")


if __name__ == "__main__":
    main()
