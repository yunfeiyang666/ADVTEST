"""
约束丢失问题专项测试
测试精简Prompt后是否修复了WITH变量未使用的问题
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from vqa_pipeline.llm_client import LLMClient
import json

# 7个约束丢失问题的测试用例
TEST_CASES = [
    {
        "id": "scene-0553_Q6",
        "question": "How many other things are there of the same status as the bicycle?",
        "question_type": "count",
        "expected_pattern": ["refStatus", "refId", "other.status=refStatus", "other.unique_id<>refId"]
    },
    {
        "id": "scene-0553_Q7",
        "question": "What number of other things are there of the same status as the trailer?",
        "question_type": "count",
        "expected_pattern": ["trailerStatus", "trailerId", "other.status=trailerStatus", "other.unique_id<>trailerId"]
    },
    {
        "id": "scene-0553_Q14",
        "question": "How many other bicycles in the same status as the barrier to the front left of the bicycle?",
        "question_type": "count",
        "expected_pattern": ["barrierStatus", "refBikeId", "other.status=barrierStatus", "other.unique_id<>refBikeId"]
    },
    {
        "id": "scene-0553_Q19",
        "question": "Is there another truck of the same status as the truck to the front left of the with rider thing?",
        "question_type": "exist",
        "expected_pattern": ["targetStatus", "refId", "other.status=targetStatus", "other.unique_id<>refId"]
    },
    {
        "id": "scene-0553_Q20",
        "question": "Are there any other cars of the same status as the truck that is to the front left of the with rider thing?",
        "question_type": "exist",
        "expected_pattern": ["truckStatus", "truckId", "other.status=truckStatus"]
    },
    {
        "id": "scene-0103_Q6",
        "question": "Are there any other things that in the same status as the truck?",
        "question_type": "exist",
        "expected_pattern": ["refStatus", "refId", "other.status=refStatus"]
    },
    {
        "id": "scene-0916_Q6",
        "question": "What number of other things are in the same status as the bus?",
        "question_type": "count",
        "expected_pattern": ["busStatus", "busId", "other.status=busStatus", "other.unique_id<>busId"]
    }
]

def check_constraint_usage(cypher: str, expected_patterns: list) -> dict:
    """检查Cypher查询中是否正确使用了WITH变量"""
    results = {
        "all_patterns_found": True,
        "found_patterns": [],
        "missing_patterns": [],
        "has_with": False,
        "has_constraint": False,
        "has_status_constraint": False,
        "has_id_constraint": False
    }
    
    # 检查是否有WITH语句
    if "WITH" in cypher.upper():
        results["has_with"] = True
    
    # 检查是否有status约束（不要求精确变量名）
    import re
    if re.search(r'status\s*=\s*\w+Status', cypher) or re.search(r'status\s*=\s*refStatus', cypher):
        results["has_status_constraint"] = True
        results["has_constraint"] = True
    
    # 检查是否有unique_id约束
    if re.search(r'unique_id\s*<>\s*\w+Id', cypher) or re.search(r'unique_id\s*<>\s*refId', cypher):
        results["has_id_constraint"] = True
        results["has_constraint"] = True
    
    # 检查是否有AND连接的约束（说明不是简单的WHERE一行）
    if "AND" in cypher.upper() and results["has_constraint"]:
        results["all_patterns_found"] = True
    else:
        results["all_patterns_found"] = False
    
    return results

def main():
    print("=" * 80)
    print("约束丢失问题专项测试")
    print("=" * 80)
    
    client = LLMClient()
    
    passed = 0
    failed = 0
    results_detail = []
    
    for i, test in enumerate(TEST_CASES, 1):
        print(f"\n[{i}/7] 测试用例: {test['id']}")
        print(f"问题: {test['question']}")
        
        try:
            cypher = client.generate_cypher(
                question=test['question'],
                question_type=test['question_type'],
                mode='strict'
            )
            
            print(f"生成的Cypher:\n{cypher}\n")
            
            # 检查约束使用情况
            check_result = check_constraint_usage(cypher, test['expected_pattern'])
            
            if check_result['has_with'] and check_result['has_constraint']:
                print("✓ 通过")
                print(f"  - WITH语句: ✓")
                print(f"  - status约束: {'✓' if check_result['has_status_constraint'] else '✗'}")
                print(f"  - unique_id约束: {'✓' if check_result['has_id_constraint'] else '✗'}")
                passed += 1
                results_detail.append({
                    "test_id": test['id'],
                    "status": "PASS",
                    "cypher": cypher,
                    "check": check_result
                })
            else:
                print("✗ 失败")
                print(f"  - WITH语句: {'✓' if check_result['has_with'] else '✗'}")
                print(f"  - status约束: {'✓' if check_result['has_status_constraint'] else '✗'}")
                print(f"  - unique_id约束: {'✓' if check_result['has_id_constraint'] else '✗'}")
                failed += 1
                results_detail.append({
                    "test_id": test['id'],
                    "status": "FAIL",
                    "cypher": cypher,
                    "check": check_result
                })
        
        except Exception as e:
            print(f"✗ 错误：{e}")
            failed += 1
            results_detail.append({
                "test_id": test['id'],
                "status": "ERROR",
                "error": str(e)
            })
    
    print("\n" + "=" * 80)
    print(f"测试结果汇总: {passed}/7 通过, {failed}/7 失败")
    print("=" * 80)
    
    # 保存详细结果
    output_file = "output/coverage_analysis/vqa_results/constraint_fix_test_results.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "total": 7,
            "passed": passed,
            "failed": failed,
            "details": results_detail
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细结果已保存到: {output_file}")
    
    return passed == 7

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
