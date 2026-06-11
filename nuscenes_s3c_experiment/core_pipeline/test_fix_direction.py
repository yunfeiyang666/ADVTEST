#!/usr/bin/env python3
"""
测试 _fix_direction_syntax 函数
验证 predicates[0] 自动修复功能
"""
import sys
sys.path.insert(0, '.')

from vqa_pipeline.llm_client import LLMClient

def test_fix_direction_syntax():
    client = LLMClient()
    
    test_cases = [
        {
            'name': '单引号predicates[0]',
            'input': "WHERE r.predicates[0]='back-right'",
            'expected': "WHERE 'back-right' IN r.angle_matches_ego"
        },
        {
            'name': '双引号predicates[0]',
            'input': 'WHERE r.predicates[0]="front-left"',
            'expected': "WHERE 'front-left' IN r.angle_matches_ego"
        },
        {
            'name': '带空格predicates[0]',
            'input': "WHERE r.predicates[0]  =  'back'",
            'expected': "WHERE 'back' IN r.angle_matches_ego"
        },
        {
            'name': '完整查询',
            'input': """MATCH (truck:Object)-[r:RELATES_TO]->(ped:Object)
WHERE ped.type='pedestrian' AND r.predicates[0]='back-right'
RETURN ped.status""",
            'expected': """MATCH (truck:Object)-[r:RELATES_TO]->(ped:Object)
WHERE ped.type='pedestrian' AND 'back-right' IN r.angle_matches_ego
RETURN ped.status"""
        },
        {
            'name': '多个predicates[0]',
            'input': """MATCH (a)-[r1]->(b) WHERE r1.predicates[0]='left'
MATCH (c)-[r2]->(d) WHERE r2.predicates[0]='right'""",
            'expected': """MATCH (a)-[r1]->(b) WHERE 'left' IN r1.angle_matches_ego
MATCH (c)-[r2]->(d) WHERE 'right' IN r2.angle_matches_ego"""
        },
        {
            'name': '已经正确的语法（不应修改）',
            'input': "WHERE 'back-right' IN r.angle_matches_ego",
            'expected': "WHERE 'back-right' IN r.angle_matches_ego"
        }
    ]
    
    print("🧪 测试 _fix_direction_syntax 函数")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for i, case in enumerate(test_cases, 1):
        result = client._fix_direction_syntax(case['input'])
        is_pass = result == case['expected']
        
        if is_pass:
            passed += 1
            print(f"\n✅ Test {i}: {case['name']}")
        else:
            failed += 1
            print(f"\n❌ Test {i}: {case['name']}")
            print(f"  输入:\n    {case['input']}")
            print(f"  期望:\n    {case['expected']}")
            print(f"  实际:\n    {result}")
    
    print("\n" + "=" * 70)
    print(f"📊 结果: {passed} passed, {failed} failed")
    
    return failed == 0

if __name__ == '__main__':
    success = test_fix_direction_syntax()
    sys.exit(0 if success else 1)
