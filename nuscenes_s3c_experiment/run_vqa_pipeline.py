"""
NuScenes VQA Pipeline 主运行脚本
完整流程：问题 -> Cypher查询 -> Neo4j执行 -> 自然语言答案

使用前请先配置 vqa_pipeline/config.py 中的 API_KEY
"""
import os
import sys
import json
import argparse
from datetime import datetime

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vqa_pipeline import VQAPipeline, LLMClient, Neo4jClient
from vqa_pipeline.sample_questions import (
    NUSCENES_QA_QUESTIONS, 
    DRIVELM_QUESTIONS,
    get_all_questions,
    print_question_stats
)
from vqa_pipeline import config


def check_config():
    """检查配置是否完整"""
    print("=" * 60)
    print("  检查配置")
    print("=" * 60)
    
    issues = []
    
    # 检查API Key
    if config.API_KEY == "YOUR_API_KEY_HERE" or not config.API_KEY:
        issues.append("API_KEY 未配置，请在 vqa_pipeline/config.py 中设置")
    else:
        print(f"✓ API_KEY 已配置: {config.API_KEY[:10]}...")
    
    # 检查Neo4j配置
    print(f"✓ Neo4j URI: {config.NEO4J_URI}")
    print(f"✓ Neo4j User: {config.NEO4J_USER}")
    
    if issues:
        print("\n⚠️ 发现配置问题:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    
    return True


def test_connections():
    """测试所有连接"""
    print("\n" + "=" * 60)
    print("  测试连接")
    print("=" * 60)
    
    # 测试Neo4j
    print("\n1. 测试Neo4j连接...")
    neo4j = Neo4jClient()
    if not neo4j.connect():
        print("  ✗ Neo4j连接失败，请确保数据库已启动")
        return False
    
    result = neo4j.execute_query("MATCH (n:Object) RETURN count(n) as count")
    if result['success']:
        print(f"  ✓ Neo4j连接成功，对象数量: {result['data'][0]['count']}")
    neo4j.close()
    
    # 测试LLM API
    print("\n2. 测试LLM API连接...")
    if config.API_KEY == "YOUR_API_KEY_HERE":
        print("  ⚠️ API_KEY未配置，跳过LLM测试")
        return True  # 可以继续，但LLM功能不可用
    
    try:
        llm = LLMClient()
        response = llm.chat([{"role": "user", "content": "请用一句话回复：你好"}])
        print(f"  ✓ LLM API连接成功")
        print(f"    回复: {response[:50]}...")
    except Exception as e:
        print(f"  ✗ LLM API连接失败: {e}")
        return False
    
    return True


def run_single_question(question: str):
    """运行单个问题"""
    pipeline = VQAPipeline()
    
    if not pipeline.initialize():
        print("Pipeline初始化失败")
        return None
    
    result = pipeline.process_question(question, verbose=True)
    pipeline.close()
    
    return result


def run_batch_questions(questions: list, output_file: str = None):
    """批量运行问题"""
    pipeline = VQAPipeline()
    
    if not pipeline.initialize():
        print("Pipeline初始化失败")
        return None
    
    results = pipeline.process_batch(questions, verbose=True)
    
    # 保存结果
    if output_file:
        pipeline.save_results(results, output_file)
    
    pipeline.close()
    return results


def run_category_test(category: str):
    """按类别运行测试"""
    questions = NUSCENES_QA_QUESTIONS.get(category, [])
    questions.extend(DRIVELM_QUESTIONS.get(category, []))
    
    if not questions:
        print(f"未找到类别 '{category}' 的问题")
        return None
    
    print(f"\n运行类别 '{category}' 的 {len(questions)} 个问题...")
    
    # 输出文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.path.dirname(__file__), "output", "vqa_results")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"vqa_{category}_{timestamp}.json")
    
    return run_batch_questions(questions, output_file)


def run_all_tests():
    """运行所有测试"""
    all_questions = get_all_questions()
    questions = [q["question"] for q in all_questions]
    
    print(f"\n运行所有 {len(questions)} 个问题...")
    
    # 输出文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.path.dirname(__file__), "output", "vqa_results")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"vqa_all_{timestamp}.json")
    
    return run_batch_questions(questions, output_file)


def interactive_mode():
    """交互式模式"""
    print("\n" + "=" * 60)
    print("  VQA Pipeline 交互模式")
    print("  输入问题，输入 'quit' 退出")
    print("=" * 60)
    
    pipeline = VQAPipeline()
    
    if not pipeline.initialize():
        print("Pipeline初始化失败")
        return
    
    while True:
        print("\n" + "-" * 40)
        question = input("请输入问题: ").strip()
        
        if question.lower() in ['quit', 'exit', 'q']:
            break
        
        if not question:
            continue
        
        result = pipeline.process_question(question, verbose=True)
        
        print("\n" + "-" * 40)
        print(f"最终答案: {result.answer}")
    
    pipeline.close()
    print("\n再见！")


def main():
    parser = argparse.ArgumentParser(description="NuScenes VQA Pipeline")
    parser.add_argument("--check", action="store_true", help="检查配置")
    parser.add_argument("--test", action="store_true", help="测试连接")
    parser.add_argument("--question", "-q", type=str, help="运行单个问题")
    parser.add_argument("--category", "-c", type=str, help="运行指定类别的问题")
    parser.add_argument("--all", action="store_true", help="运行所有问题")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--stats", action="store_true", help="显示问题统计")
    
    args = parser.parse_args()
    
    # 显示问题统计
    if args.stats:
        print_question_stats()
        return
    
    # 检查配置
    if args.check or not any([args.test, args.question, args.category, args.all, args.interactive]):
        if not check_config():
            print("\n请先完成配置后再运行")
            return
    
    # 测试连接
    if args.test:
        test_connections()
        return
    
    # 运行单个问题
    if args.question:
        run_single_question(args.question)
        return
    
    # 运行类别
    if args.category:
        run_category_test(args.category)
        return
    
    # 运行所有
    if args.all:
        run_all_tests()
        return
    
    # 交互模式
    if args.interactive:
        interactive_mode()
        return
    
    # 默认：显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
