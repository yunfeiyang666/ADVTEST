"""
测试规范化功能
验证问题规范化和答案格式化的效果
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vqa_pipeline.question_normalizer import QuestionNormalizer
from vqa_pipeline.answer_formatter import AnswerFormatter


def test_question_normalization():
    """测试问题规范化"""
    print("=" * 80)
    print("  测试1: 问题规范化")
    print("=" * 80)
    
    normalizer = QuestionNormalizer()
    
    test_cases = [
        "Are there any trailers?",
        "What is the status of the parked barrier?",
        "How many motorcycles are in front of me?",
        "Is the construction vehicle behind me moving?",
        "What is in the back of the stationary trailer?",
    ]
    
    for i, question in enumerate(test_cases, 1):
        normalized, qtype = normalizer.normalize(question)
        format_spec = normalizer.get_expected_format(qtype)
        
        print(f"\n测试 {i}:")
        print(f"  原始问题: {question}")
        if normalized != question:
            print(f"  规范化后: {normalized}")
            print(f"  ✅ 问题已规范化")
        else:
            print(f"  ℹ️  问题无需规范化")
        print(f"  问题类型: {qtype}")
        print(f"  答案格式: {format_spec}")
        print("-" * 80)


def test_answer_formatting():
    """测试答案格式化"""
    print("\n" + "=" * 80)
    print("  测试2: 答案格式化")
    print("=" * 80)
    
    formatter = AnswerFormatter()
    
    test_cases = [
        {
            'name': 'exist问题 - 详细答案',
            'raw_answer': '根据查询结果，场景中有2辆卡车可见。',
            'question_type': 'exist',
            'query_result': {'success': True, 'count': 2, 'data': [{'count': 2}]},
            'expected': 'yes'
        },
        {
            'name': 'exist问题 - 空结果',
            'raw_answer': '未找到相关对象。',
            'question_type': 'exist',
            'query_result': {'success': True, 'count': 0, 'data': []},
            'expected': 'no'
        },
        {
            'name': 'count问题 - 包含解释',
            'raw_answer': '查询结果显示有5个对象，其中3个在前方。',
            'question_type': 'count',
            'query_result': {'success': True, 'count': 1, 'data': [{'count': 5}]},
            'expected': '5'
        },
        {
            'name': 'status问题 - 静止状态',
            'raw_answer': '这辆车是静止的，速度为[0,0,0]，位于后方。',
            'question_type': 'status',
            'query_result': {'success': True, 'data': [{'velocity': [0, 0, 0]}]},
            'expected': 'stopped'
        },
        {
            'name': 'status问题 - 移动状态',
            'raw_answer': '根据数据，该对象正在移动中。',
            'question_type': 'status',
            'query_result': {'success': True, 'data': [{'velocity': [1.5, 0.3, 0]}]},
            'expected': 'moving'
        },
        {
            'name': 'object问题 - 包含解释',
            'raw_answer': '根据查询，这是一辆自行车(bicycle)，位于ego前方。',
            'question_type': 'object',
            'query_result': {'success': True, 'data': [{'type': 'bicycle'}]},
            'expected': 'bicycle'
        },
        {
            'name': 'comparison问题',
            'raw_answer': '两个对象的状态相同。',
            'question_type': 'comparison',
            'query_result': {'success': True, 'count': 2, 'data': [{'same': True}]},
            'expected': 'yes'
        },
    ]
    
    success_count = 0
    for i, test in enumerate(test_cases, 1):
        formatted = formatter.format(
            test['raw_answer'],
            test['question_type'],
            test['query_result']
        )
        is_valid = formatter.validate(formatted, test['question_type'])
        is_correct = (formatted.lower() == test['expected'].lower())
        
        if is_correct:
            success_count += 1
        
        print(f"\n测试 {i}: {test['name']}")
        print(f"  原始答案: {test['raw_answer']}")
        print(f"  格式化后: {formatted}")
        print(f"  期望答案: {test['expected']}")
        print(f"  验证通过: {'✅' if is_valid else '❌'}")
        print(f"  匹配正确: {'✅' if is_correct else '❌'}")
        print("-" * 80)
    
    print(f"\n总体成功率: {success_count}/{len(test_cases)} ({success_count/len(test_cases)*100:.1f}%)")


def test_synonyms():
    """测试同义词映射"""
    print("\n" + "=" * 80)
    print("  测试3: 同义词映射")
    print("=" * 80)
    
    normalizer = QuestionNormalizer()
    
    synonym_tests = [
        ('trailer', 'truck'),
        ('barrier', 'car'),
        ('motorcycle', 'bicycle'),
        ('parked', 'stopped'),
        ('stationary', 'stopped'),
        ('in front of', 'to the front of'),
        ('behind', 'to the back of'),
    ]
    
    for original, expected in synonym_tests:
        question = f"Is there a {original}?"
        normalized, _ = normalizer.normalize(question)
        
        if expected in normalized.lower():
            print(f"  ✅ '{original}' → '{expected}' (成功)")
        else:
            print(f"  ❌ '{original}' → '{expected}' (失败)")
            print(f"     实际结果: {normalized}")


if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("  VQA规范化功能测试")
    print("=" * 80)
    
    test_question_normalization()
    test_answer_formatting()
    test_synonyms()
    
    print("\n" + "=" * 80)
    print("  测试完成！")
    print("=" * 80)
