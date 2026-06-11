"""
测试场景覆盖率计算功能
"""
import json
import os
from vqa_pipeline.scene_coverage import calculate_scene_coverage


def test_coverage_with_real_data():
    """使用真实的VQA测试数据测试覆盖率计算"""
    
    print("=" * 70)
    print("  场景覆盖率计算测试")
    print("=" * 70)
    
    # 加载场景图
    scene_graph_path = "output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json"
    print(f"\n加载场景图: {scene_graph_path}")
    
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    
    print(f"  节点数: {len(scene_graph.get('nodes', []))}")
    print(f"  边数: {len(scene_graph.get('edges', []))}")
    
    # 加载VQA测试结果
    vqa_result_path = "output/coverage_analysis/vqa_results/scene-0553_frame8_official_qa.json"
    print(f"\n加载VQA测试结果: {vqa_result_path}")
    
    with open(vqa_result_path, 'r', encoding='utf-8') as f:
        vqa_results = json.load(f)
    
    # 提取问题和Cypher查询
    questions = []
    for result in vqa_results.get('results', []):
        questions.append({
            'question': result.get('question', ''),
            'cypher_query': result.get('cypher_query', ''),
            'query_result': result.get('query_result', {})
        })
    
    print(f"  问题数: {len(questions)}")
    
    # 计算覆盖率
    print(f"\n正在计算场景覆盖率...")
    coverage_stats = calculate_scene_coverage(questions, scene_graph)
    
    # 输出结果
    print("\n" + "=" * 70)
    print("  覆盖率统计结果")
    print("=" * 70)
    
    print(f"\n📊 总体统计:")
    print(f"  总边数: {coverage_stats['total_edges']}")
    print(f"  覆盖边数: {coverage_stats['covered_edges']}")
    print(f"  未覆盖边数: {coverage_stats['uncovered_edges']}")
    print(f"  覆盖率: {coverage_stats['coverage_rate']}%")
    
    print(f"\n📝 问题统计:")
    summary = coverage_stats['summary']
    print(f"  总问题数: {summary['total_questions']}")
    print(f"  有覆盖的问题数: {summary['questions_with_coverage']}")
    print(f"  平均每个问题覆盖边数: {summary['avg_edges_per_question']}")
    
    # 显示每个问题的覆盖情况
    print(f"\n📋 问题覆盖详情 (前10个):")
    for q_coverage in coverage_stats['question_coverage'][:10]:
        print(f"\n  问题 {q_coverage['question_id']}: {q_coverage['question'][:60]}...")
        print(f"    覆盖边数: {q_coverage['covered_edges_count']}")
        if q_coverage['covered_edge_ids']:
            print(f"    覆盖边: {', '.join(map(str, q_coverage['covered_edge_ids'][:5]))}")
    
    # 边覆盖率分析
    covered_count = sum(1 for e in coverage_stats['edge_details'] if e['is_covered'])
    uncovered_count = sum(1 for e in coverage_stats['edge_details'] if not e['is_covered'])
    
    print(f"\n🔗 边覆盖分析:")
    print(f"  已覆盖: {covered_count} 条")
    print(f"  未覆盖: {uncovered_count} 条")
    
    # 显示部分未覆盖的边
    uncovered_edges = [e for e in coverage_stats['edge_details'] if not e['is_covered']]
    if uncovered_edges:
        print(f"\n  未覆盖边示例 (前5条):")
        for edge in uncovered_edges[:5]:
            print(f"    Edge {edge['edge_id']}: {edge['source']} -> {edge['target']}")
    
    # 保存结果
    output_path = "output/coverage_analysis/vqa_results/scene-0553_frame8_coverage_stats.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(coverage_stats, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ 覆盖率统计已保存: {output_path}")
    
    print("\n" + "=" * 70)
    print("  测试完成")
    print("=" * 70)
    
    return coverage_stats


def test_coverage_simple():
    """简单测试用例"""
    print("\n" + "=" * 70)
    print("  简单测试用例")
    print("=" * 70)
    
    # 简单场景图
    scene_graph = {
        'edges': [
            {'source': 'ego', 'target': 'car1'},
            {'source': 'ego', 'target': 'car2'},
            {'source': 'ego', 'target': 'truck1'},
            {'source': 'ego', 'target': 'bicycle1'},
            {'source': 'ego', 'target': 'pedestrian1'}
        ]
    }
    
    # 简单问题集
    questions = [
        {
            'question': 'Are there any cars?',
            'cypher_query': "MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(car:Object {type:'car'}) RETURN count(car)"
        },
        {
            'question': 'How many trucks?',
            'cypher_query': "MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(truck:Object {type:'truck'}) RETURN count(truck)"
        },
        {
            'question': 'What is the status of bicycle1?',
            'cypher_query': "MATCH (n:Object {unique_id:'bicycle1'}) RETURN n.status"
        }
    ]
    
    print(f"\n场景图: {len(scene_graph['edges'])} 条边")
    print(f"问题数: {len(questions)}")
    
    coverage_stats = calculate_scene_coverage(questions, scene_graph)
    
    print(f"\n覆盖率: {coverage_stats['coverage_rate']}%")
    print(f"覆盖边数: {coverage_stats['covered_edges']} / {coverage_stats['total_edges']}")
    
    print("\n边覆盖详情:")
    for edge in coverage_stats['edge_details']:
        status = "✓" if edge['is_covered'] else "✗"
        print(f"  {status} {edge['source']} -> {edge['target']}")


if __name__ == '__main__':
    # 测试1: 简单用例
    test_coverage_simple()
    
    # 测试2: 真实数据
    print("\n\n")
    test_coverage_with_real_data()
