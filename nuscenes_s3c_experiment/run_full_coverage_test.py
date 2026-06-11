"""
完整版覆盖率测试脚本
对所有6个场景帧运行VQA测试并计算多级覆盖率

场景列表(manifest.json):
- scene-0757_frame26: 18对象
- scene-1077_frame19: 19对象  
- scene-0553_frame8: 50对象 (有官方QA)
- scene-0103_frame38: 49对象 (有官方QA)
- scene-0916_frame8: 72对象 (有官方QA)
- scene-0103_frame25: 65对象 (有官方QA)

流程:
1. 加载每个场景的场景图
2. 导入Neo4j（含direction_4/direction_8字段）
3. 为每个场景生成VQA问题（或使用官方QA）
4. 运行VQA测试
5. 计算多级覆盖率(L0/L1/L2)
"""
import os
import sys
import json
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from import_single_scene_to_neo4j import Neo4jImporter
from vqa_pipeline import VQAPipeline
from vqa_pipeline.scene_coverage import calculate_scene_coverage
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


def load_manifest(manifest_path: Path) -> List[Dict[str, Any]]:
    """加载场景清单"""
    with open(manifest_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_scene_graph(filepath: str) -> Dict[str, Any]:
    """加载场景图"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_official_qa(qa_path: Path) -> List[Dict[str, Any]]:
    """加载官方QA数据（如果存在）"""
    if not qa_path.exists():
        return None
    with open(qa_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    qa_pairs = []
    for result in data.get('results', []):
        qa_pairs.append({
            'question': result['question'],
            'expected_answer': result['expected_answer'],
            'question_type': result.get('question_type', 'unknown')
        })
    return qa_pairs


def import_to_neo4j(scene_graph: Dict[str, Any], scene_name: str, frame_idx: int) -> bool:
    """导入场景图到Neo4j"""
    print(f"\n导入场景到Neo4j: {scene_name} 帧{frame_idx}")
    
    importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
    
    try:
        importer.clear_database()
        importer.create_constraints()
        importer.import_scene(scene_graph)
        
        with importer.driver.session() as session:
            result = session.run("MATCH (n:Object) RETURN count(n) as count")
            node_count = result.single()['count']
            result = session.run("MATCH ()-[r:RELATES_TO]->() WHERE r.direction_4 IS NOT NULL RETURN count(r) as count")
            dir4_count = result.single()['count']
            print(f"✓ 导入 {node_count} 节点, {dir4_count} 条关系有direction_4")
        
        return True
    except Exception as e:
        print(f"✗ 导入失败: {e}")
        return False
    finally:
        importer.close()


def run_vqa_test(qa_pairs: List[Dict[str, Any]], pipeline: VQAPipeline, scene_name: str, frame_idx: int) -> List[Dict[str, Any]]:
    """运行VQA测试"""
    print(f"\n{'='*70}")
    print(f"  VQA测试: {scene_name} 帧{frame_idx}")
    print(f"  问题数量: {len(qa_pairs)}")
    print("="*70)
    
    results = []
    
    for i, qa in enumerate(qa_pairs, 1):
        question = qa['question']
        expected_answer = qa.get('expected_answer', '')
        question_type = qa.get('question_type', 'unknown')
        
        print(f"\n[{i}/{len(qa_pairs)}] Q: {question[:60]}...")
        
        # 开启verbose=True，完整打印规范化、中间推理、生成的Cypher和查询结果
        result = pipeline.process_question(question, verbose=True)
        
        # 比较答案（如果有预期答案）
        answer_match = False
        if expected_answer and result.success and result.answer:
            answer_lower = result.answer.lower().strip()
            expected_lower = expected_answer.lower().strip()
            answer_match = (
                expected_lower in answer_lower or 
                answer_lower in expected_lower or
                answer_lower == expected_lower
            )
        
        results.append({
            'question': question,
            'expected_answer': expected_answer,
            'predicted_answer': result.answer,
            'question_type': question_type,
            'success': result.success,
            'answer_match': answer_match,
            'cypher_query': result.cypher_query,
            'query_result': result.raw_result if hasattr(result, 'raw_result') else {},
            'error': result.error
        })
        
        status = "✅" if result.success else "❌"
        print(f"  {status} {result.answer if result.answer else result.error}")
    
    return results


def compute_coverage(scene_graph: Dict[str, Any], vqa_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """计算多级覆盖率"""
    print("\n计算覆盖率...")
    
    # 提取问题格式用于覆盖率计算
    questions = []
    for r in vqa_results:
        questions.append({
            'question': r['question'],
            'cypher_query': r.get('cypher_query', ''),
            'query_result': r.get('query_result', {})
        })
    
    # 计算边级覆盖
    coverage_stats = calculate_scene_coverage(questions, scene_graph)
    edge_details = coverage_stats.get('edge_details', [])
    
    # 构建边集合
    all_edges = set()
    covered_edges = set()
    for e in edge_details:
        source = e.get('source')
        target = e.get('target')
        if source and target:
            edge = (source, target)
            all_edges.add(edge)
            if e.get('is_covered'):
                covered_edges.add(edge)
    
    # L0: 节点覆盖
    nodes = scene_graph.get('nodes', [])
    all_node_ids = {n.get('id') or n.get('unique_id') for n in nodes}
    all_node_ids = {nid for nid in all_node_ids if nid}
    
    covered_node_ids = set()
    for s, t in covered_edges:
        covered_node_ids.add(s)
        covered_node_ids.add(t)
    
    l0_total = len(all_node_ids)
    l0_covered = len(covered_node_ids & all_node_ids)
    l0_rate = (l0_covered / l0_total * 100) if l0_total > 0 else 0
    
    # L1: ego一跳边覆盖
    ego_edges = {e for e in all_edges if e[0] == 'ego'}
    covered_ego_edges = ego_edges & covered_edges
    l1_total = len(ego_edges)
    l1_covered = len(covered_ego_edges)
    l1_rate = (l1_covered / l1_total * 100) if l1_total > 0 else 0
    
    # L2: ego两跳路径覆盖
    outgoing = {}
    for s, t in all_edges:
        outgoing.setdefault(s, set()).add(t)
    
    l2_total = 0
    l2_covered = 0
    for mid in outgoing.get('ego', set()):
        e1 = ('ego', mid)
        for dst in outgoing.get(mid, set()):
            e2 = (mid, dst)
            l2_total += 1
            if e1 in covered_edges and e2 in covered_edges:
                l2_covered += 1
    
    l2_rate = (l2_covered / l2_total * 100) if l2_total > 0 else 0
    
    return {
        'base_edge_coverage': coverage_stats,
        'multi_level': {
            'L0': {'total': l0_total, 'covered': l0_covered, 'rate': round(l0_rate, 2)},
            'L1': {'total': l1_total, 'covered': l1_covered, 'rate': round(l1_rate, 2)},
            'L2': {'total': l2_total, 'covered': l2_covered, 'rate': round(l2_rate, 2)}
        }
    }


def main():
    output_root = Path(config.OUTPUT_DIR) / "coverage_analysis"
    scene_graph_dir = output_root / "scene_graphs"
    vqa_result_dir = output_root / "vqa_results"
    vqa_result_dir.mkdir(parents=True, exist_ok=True)
    
    manifest_path = scene_graph_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"错误: manifest.json不存在: {manifest_path}")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = vqa_result_dir / f"full_coverage_test_{timestamp}.txt"
    
    logger = Logger(str(log_file))
    original_stdout = sys.stdout
    sys.stdout = logger
    
    try:
        print("="*70)
        print("  完整版覆盖率测试")
        print("="*70)
        print(f"\n📝 日志文件: {log_file}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 加载场景清单
        scenes = load_manifest(manifest_path)
        print(f"\n共 {len(scenes)} 个场景待测试")
        
        # 初始化VQA Pipeline
        print("\n初始化VQA Pipeline...")
        pipeline = VQAPipeline(use_ir=False)
        if not pipeline.initialize():
            print("✗ Pipeline初始化失败")
            return
        
        # 处理每个场景
        all_stats = []
        
        for i, scene_info in enumerate(scenes, 1):
            scene_name = scene_info['scene_name']
            frame_idx = scene_info['frame_idx']
            sg_path = Path(scene_info['filepath'])
            
            print(f"\n{'='*70}")
            print(f"[{i}/{len(scenes)}] 场景: {scene_name} 帧{frame_idx}")
            print(f"描述: {scene_info.get('description', '')}")
            print("="*70)
            
            if not sg_path.exists():
                print(f"❌ 场景图文件不存在: {sg_path}")
                continue
            
            # 加载场景图
            scene_graph = load_scene_graph(str(sg_path))
            
            # 导入到Neo4j
            if not import_to_neo4j(scene_graph, scene_name, frame_idx):
                print(f"跳过场景 {scene_name}")
                continue
            
            # 查找官方QA或生成问题
            qa_filename = f"{scene_name}_frame{frame_idx}_official_qa.json"
            qa_path = vqa_result_dir / qa_filename
            
            qa_pairs = load_official_qa(qa_path)
            if qa_pairs:
                print(f"使用官方QA: {len(qa_pairs)} 题")
            else:
                print(f"⚠️ 无官方QA，跳过此场景（需要手动生成问题）")
                continue
            
            # 运行VQA测试
            vqa_results = run_vqa_test(qa_pairs, pipeline, scene_name, frame_idx)
            
            # 计算覆盖率
            coverage = compute_coverage(scene_graph, vqa_results)
            
            # 统计
            total_qa = len(vqa_results)
            success_qa = sum(1 for r in vqa_results if r['success'])
            correct_qa = sum(1 for r in vqa_results if r['answer_match'])
            
            scene_stat = {
                'scene_name': scene_name,
                'frame_idx': frame_idx,
                'description': scene_info.get('description', ''),
                'total_objects': scene_info.get('total_objects'),
                'vqa_stats': {
                    'total': total_qa,
                    'success': success_qa,
                    'correct': correct_qa,
                    'accuracy': round(correct_qa/total_qa*100, 2) if total_qa > 0 else 0
                },
                'coverage': coverage['multi_level'],
                'vqa_results': vqa_results
            }
            all_stats.append(scene_stat)
            
            # 打印场景统计
            ml = coverage['multi_level']
            print(f"\n场景统计:")
            print(f"  VQA准确率: {correct_qa}/{total_qa} ({correct_qa/total_qa*100:.1f}%)")
            print(f"  L0节点覆盖: {ml['L0']['covered']}/{ml['L0']['total']} ({ml['L0']['rate']}%)")
            print(f"  L1边覆盖: {ml['L1']['covered']}/{ml['L1']['total']} ({ml['L1']['rate']}%)")
            print(f"  L2路径覆盖: {ml['L2']['covered']}/{ml['L2']['total']} ({ml['L2']['rate']}%)")
        
        # 全局统计
        print("\n" + "="*70)
        print("  全局测试总结")
        print("="*70)
        
        total_scenes = len(all_stats)
        total_questions = sum(s['vqa_stats']['total'] for s in all_stats)
        total_correct = sum(s['vqa_stats']['correct'] for s in all_stats)
        
        print(f"  测试场景: {total_scenes}")
        print(f"  总问题数: {total_questions}")
        print(f"  总正确数: {total_correct}")
        print(f"  总准确率: {total_correct/total_questions*100:.1f}%" if total_questions > 0 else "  总准确率: N/A")
        
        # 平均覆盖率
        if all_stats:
            avg_l0 = sum(s['coverage']['L0']['rate'] for s in all_stats) / len(all_stats)
            avg_l1 = sum(s['coverage']['L1']['rate'] for s in all_stats) / len(all_stats)
            avg_l2 = sum(s['coverage']['L2']['rate'] for s in all_stats) / len(all_stats)
            print(f"\n平均覆盖率:")
            print(f"  L0: {avg_l0:.2f}%")
            print(f"  L1: {avg_l1:.2f}%")
            print(f"  L2: {avg_l2:.2f}%")
        
        # 保存结果
        result_file = vqa_result_dir / f"full_coverage_test_{timestamp}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': timestamp,
                'total_scenes': total_scenes,
                'total_questions': total_questions,
                'total_correct': total_correct,
                'overall_accuracy': round(total_correct/total_questions*100, 2) if total_questions > 0 else 0,
                'scenes': all_stats
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n📊 结果已保存: {result_file}")
        print(f"⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.stdout = original_stdout
        logger.close()
        print(f"\n✓ 日志已保存: {log_file}")


if __name__ == '__main__':
    main()
