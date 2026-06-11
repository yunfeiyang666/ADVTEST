"""
Retry 机制演示脚本 — 对一帧执行 5 层 retry 做题，展示完整过程
"""
import sys, os, json, time

_core = os.path.dirname(os.path.abspath(__file__))
_experiment = os.path.dirname(_core)
# 只加 core_pipeline 的父目录，让 vqa_pipeline 通过正确包路径解析
# 不加 _core 本身，避免 backup 目录下的旧 vqa_pipeline 干扰
if _core not in sys.path:
    sys.path.insert(0, _core)

from neo4j import GraphDatabase
from vqa_pipeline.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def check_neo4j():
    """检查 Neo4j 连接和数据"""
    d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    s = d.session()
    
    r = s.run("MATCH (n:Object) RETURN DISTINCT n.type AS t, count(n) AS c ORDER BY c DESC")
    types = r.data()
    print("Neo4j 中的节点类型分布:")
    for row in types:
        print(f"  {row['t']}: {row['c']}")
    
    r2 = s.run("MATCH (n:Object {unique_id:'ego'}) RETURN n.unique_id AS uid")
    ego = r2.data()
    print(f"\nEgo 节点: {ego}")
    
    r3 = s.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS cnt")
    print(f"关系边数: {r3.single()['cnt']}")
    
    s.close()
    d.close()
    return True


def run_retry_demo(max_questions=3):
    """运行 retry 演示，取几道题展示 5 层 retry 过程"""
    from vqa_pipeline.pipeline import VQAPipeline
    
    # 检查方法是否存在
    print(f"\n  Pipeline 模块路径: {VQAPipeline.__module__}")
    print(f"  process_question_with_retry 存在: {hasattr(VQAPipeline, 'process_question_with_retry')}")
    
    test_questions = [
        {
            "question": "Are there any stopped cars?",
            "expected_answer": "yes",
            "question_type": "exist"
        },
        {
            "question": "How many pedestrians are there?",
            "expected_answer": "25",
            "question_type": "count"
        },
        {
            "question": "What is the status of car1?",
            "expected_answer": "stopped",
            "question_type": "status"
        },
    ]
    
    print("\n" + "=" * 70)
    print("  Retry 机制演示 — 5 层策略逐级尝试")
    print("=" * 70)
    
    results = []
    with VQAPipeline() as pipeline:
        for i, tq in enumerate(test_questions[:max_questions]):
            print(f"\n{'─' * 60}")
            print(f"  题目 {i+1}: {tq['question']}")
            print(f"  预期答案: {tq['expected_answer']}")
            print(f"  类型: {tq['question_type']}")
            print(f"{'─' * 60}")
            
            start = time.time()
            result = pipeline.process_question_with_retry(
                question=tq["question"],
                expected_answer=tq["expected_answer"],
                max_retries=5,
                verbose=True
            )
            elapsed = time.time() - start
            
            print(f"\n  最终答案: {result.answer}")
            print(f"  成功: {result.success}")
            print(f"  耗时: {elapsed:.1f}s")
            if result.cypher_query:
                print(f"  最终 Cypher:")
                for line in result.cypher_query.split('\n'):
                    print(f"    {line}")
            if result.error:
                print(f"  错误: {result.error}")
            
            # 展示 retry 历史
            if hasattr(result, 'retry_history') and result.retry_history:
                print(f"\n  --- Retry 历史 ({len(result.retry_history)} 次) ---")
                for rh in result.retry_history:
                    if isinstance(rh, dict):
                        print(f"    策略: {rh.get('strategy', '?')}, 答案: {rh.get('answer', '?')}")
            
            results.append({
                "question": tq["question"],
                "expected": tq["expected_answer"],
                "answer": result.answer,
                "success": result.success,
                "question_type": result.question_type,
                "elapsed": round(elapsed, 1)
            })
    
    return results


if __name__ == "__main__":
    print("\n" + "#" * 70)
    print("#  5 层 Retry 机制实跑演示")
    print("#" * 70)
    
    print("\n--- Step 1: 检查 Neo4j 连接 ---")
    try:
        check_neo4j()
    except Exception as e:
        print(f"Neo4j 连接失败: {e}")
        print("请确保 Neo4j 已启动")
        sys.exit(1)
    
    print("\n--- Step 2: 运行 Retry 演示 ---")
    try:
        results = run_retry_demo(max_questions=3)
    except Exception as e:
        import traceback
        print(f"Retry 演示出错: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    print("\n" + "=" * 70)
    print("  演示结果汇总")
    print("=" * 70)
    for r in results:
        status = "✓" if r["success"] else "✗"
        print(f"  {status} Q: {r['question']}")
        print(f"    预期: {r['expected']} → 实际: {r['answer']} (类型: {r['question_type']}, 耗时: {r['elapsed']}s)")
