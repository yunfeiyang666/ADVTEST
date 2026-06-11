"""
快速测试脚本 - 用LLM直接判定答案是否语义等价
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vqa_pipeline.pipeline import VQAPipeline
from import_single_scene_to_neo4j import Neo4jImporter


# 硬编码的等价词组
EQUIVALENT_SETS = [
    {'parked', 'stopped'},
    {'with_rider', 'with rider'},
    {'without_rider', 'without rider'},
    {'moving', 'in motion'},
]


def normalize_answer(answer: str) -> str:
    """标准化答案格式"""
    return answer.lower().strip().replace('_', ' ')


def check_equivalent(expected: str, actual: str) -> bool:
    """检查两个答案是否在等价词组中"""
    exp_norm = normalize_answer(expected)
    act_norm = normalize_answer(actual)
    
    # 精确匹配
    if exp_norm == act_norm:
        return True
    
    # 检查等价词组
    for equiv_set in EQUIVALENT_SETS:
        norm_set = {normalize_answer(w) for w in equiv_set}
        if exp_norm in norm_set and act_norm in norm_set:
            return True
    
    return False


def llm_judge_answers(llm_client, question: str, expected: str, actual: str) -> tuple:
    """判断两个答案是否等价，返回(是否等价, 原因)"""
    # 1. 先用硬编码规则检查
    if check_equivalent(expected, actual):
        return True, "等价词组匹配"
    
    # 2. 规则检查不通过，才调用LLM
    prompt = f"""判断以下两个答案是否表达相同意思。

问题: {question}
标准答案: {expected}
实际答案: {actual}

只回答YES或NO。"""
    
    try:
        response = llm_client.call_llm_raw(prompt, max_tokens=10, temperature=0)
        is_same = "YES" in response.upper()
        return is_same, "LLM判定" if is_same else "LLM判定不等价"
    except Exception as e:
        return False, f"LLM调用失败: {e}"


def main():
    print("="*70)
    print("  快速测试 - LLM答案判定")
    print("="*70)
    
    pipeline = VQAPipeline()
    if not pipeline.initialize():
        print("初始化失败")
        return
    
    # 加载场景
    scene_graph_path = 'output/coverage_analysis/scene_graphs/scene-0103_frame25_scene_graph.json'
    qa_path = 'output/coverage_analysis/vqa_results/scene-0103_frame25_official_qa.json'
    
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    with open(qa_path, 'r', encoding='utf-8') as f:
        qa_data = json.load(f)
    
    # 导入Neo4j
    importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
    try:
        importer.clear_database()
        importer.create_constraints()
        importer.import_scene(scene_graph)
    finally:
        importer.close()
    
    # 提取问题
    questions = qa_data.get('questions', [])
    if not questions:
        questions = [{'question': r['question'], 'answer': r['expected_answer']} 
                    for r in qa_data.get('results', [])]
    
    print(f"\n测试 {len(questions)} 道题...")
    
    correct = 0
    llm_judged = 0
    
    for i, q in enumerate(questions, 1):
        question = q['question']
        expected = q['answer']
        
        print(f"\n[{i}/{len(questions)}] Q: {question}")
        print(f"  预期: {expected}")
        
        result = pipeline.process_question(question, verbose=False)
        actual = result.answer if result.success else "FAILED"
        print(f"  实际: {actual}")
        
        # 精确匹配
        if expected.lower().strip() == actual.lower().strip():
            correct += 1
            print(f"  ✅ 正确")
        else:
            # 等价判定（硬编码规则 + LLM兜底）
            is_same, reason = llm_judge_answers(pipeline.llm, question, expected, actual)
            if is_same:
                correct += 1
                llm_judged += 1
                print(f"  ✅ 正确 ({reason})")
            else:
                print(f"  ❌ 错误 ({reason})")
    
    print(f"\n{'='*70}")
    print(f"  结果: {correct}/{len(questions)} ({100*correct/len(questions):.1f}%)")
    print(f"  其中LLM判定等价: {llm_judged}")
    print("="*70)
    
    pipeline.close()


if __name__ == "__main__":
    main()
