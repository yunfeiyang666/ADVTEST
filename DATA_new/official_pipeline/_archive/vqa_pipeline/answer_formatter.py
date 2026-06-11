"""
答案验证和格式化模块
功能：
1. 验证答案是否符合问题类型的格式要求
2. 格式化答案为标准格式
3. 提取关键信息
4. LLM最终答案判定（处理语义等价情况）
"""
import re
from collections import Counter
from typing import Optional, Dict, Any, Tuple


class AnswerFormatter:
    """答案格式化器"""
    
    def __init__(self):
        pass
    
    def format(self, raw_answer: str, question_type: str, query_result: Dict[str, Any]) -> str:
        """
        格式化答案
        
        Args:
            raw_answer: LLM生成的原始答案
            question_type: 问题类型（exist/count/status/object/comparison）
            query_result: Neo4j查询结果
        
        Returns:
            格式化后的答案
        """
        if question_type == 'exist':
            return self._format_exist_answer(raw_answer, query_result)
        elif question_type == 'count':
            return self._format_count_answer(raw_answer, query_result)
        elif question_type == 'status':
            return self._format_status_answer(raw_answer, query_result)
        elif question_type == 'object':
            return self._format_object_answer(raw_answer, query_result)
        elif question_type == 'comparison':
            return self._format_comparison_answer(raw_answer, query_result)
        else:
            return self._format_general_answer(raw_answer)
    
    def _format_exist_answer(self, raw_answer: str, query_result: Dict) -> str:
        """格式化存在性问题答案为yes/no"""
        raw_lower = raw_answer.lower()
        
        # 首先检查查询结果
        if query_result.get('success'):
            count = query_result.get('count', 0)
            data = query_result.get('data', [])
            
            # 如果有明确的count或data，基于此判断
            if count > 0 or (data and len(data) > 0):
                # 检查是否有false值
                if data and isinstance(data[0], dict):
                    for value in data[0].values():
                        if value is False or value == 'false':
                            return 'no'
                return 'yes'
            else:
                return 'no'
        
        # 如果查询失败，从答案文本提取
        if any(word in raw_lower for word in ['yes', '有', '存在', 'visible', 'found']):
            return 'yes'
        elif any(word in raw_lower for word in ['no', '没有', '不存在', 'not visible', 'not found']):
            return 'no'
        
        # 默认返回no（保守策略）
        return 'no'
    
    def _format_count_answer(self, raw_answer: str, query_result: Dict) -> str:
        """格式化计数问题答案为纯数字"""
        # 首先尝试从查询结果提取
        if query_result.get('success') and query_result.get('data'):
            data = query_result['data']
            if data and isinstance(data[0], dict):
                # 查找count相关的键
                for key, value in data[0].items():
                    if 'count' in key.lower() and isinstance(value, (int, float)):
                        return str(int(value))
                    # 如果只有一个数值，也认为是count
                    if isinstance(value, (int, float)):
                        return str(int(value))
        
        # 从原始答案提取数字
        numbers = re.findall(r'\b\d+\b', raw_answer)
        if numbers:
            return numbers[0]
        
        # 如果没找到，返回0
        return '0'
    
    def _format_status_answer(self, raw_answer: str, query_result: Dict) -> str:
        """格式化状态问题答案"""
        # 优先从查询结果中直接提取status字段
        if query_result.get('success') and query_result.get('data'):
            data = query_result['data']
            if data and isinstance(data[0], dict):
                # 查找status相关的键
                for key, value in data[0].items():
                    if 'status' in key.lower() and isinstance(value, str):
                        # 转换下划线为空格
                        status = value.lower().replace('_', ' ')
                        return status
        
        raw_lower = raw_answer.lower()
        
        # 定义标准状态词
        status_keywords = {
            'stopped': ['stopped', 'stationary', 'not moving', '停止', '静止'],
            'parked': ['parked', '停放'],
            'moving': ['moving', 'driving', 'running', '移动', '行驶'],
            'with rider': ['with rider', 'with_rider', '有骑手', '有人骑'],
            'without rider': ['without rider', 'without_rider', '无骑手', '没人骑'],
            'standing': ['standing', '站立'],
        }
        
        # 检查是否包含状态关键词
        for standard_status, keywords in status_keywords.items():
            if any(kw in raw_lower for kw in keywords):
                return standard_status
        
        # 默认返回原答案的关键词
        words = raw_answer.split()
        for word in words:
            if word.lower() in ['stopped', 'moving', 'parked', 'stationary', 'standing']:
                return word.lower()
        
        return raw_answer.strip()
    
    def _format_object_answer(self, raw_answer: str, query_result: Dict) -> str:
        """格式化对象识别问题答案"""
        raw_lower = raw_answer.lower()
        
        # 标准对象类型（包含 barrier, motorcycle, trailer）
        object_types = ['car', 'truck', 'bus', 'bicycle', 'pedestrian', 'ego', 'barrier', 'motorcycle', 'trailer']
        
        # 从查询结果提取：如果有多行，取出现频率最高的类型
        if query_result.get('success') and query_result.get('data'):
            data = query_result['data']
            if data and isinstance(data[0], dict):
                types_from_result = []
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    t = row.get('type') or row.get('obj.type')
                    if isinstance(t, str):
                        t_lower = t.lower()
                        if t_lower in object_types:
                            types_from_result.append(t_lower)
                if types_from_result:
                    counter = Counter(types_from_result)
                    majority_type, _ = counter.most_common(1)[0]
                    return majority_type
        
        # 从答案文本提取
        for obj_type in object_types:
            if obj_type in raw_lower:
                return obj_type
        
        # 如果没找到标准类型，返回清理后的答案
        return self._extract_key_phrase(raw_answer)
    
    def _format_comparison_answer(self, raw_answer: str, query_result: Dict) -> str:
        """格式化比较问题答案为yes/no。

        优先直接依据查询结果中的布尔值字段：
        - 检查所有包含 "same" 的键（如 same, same_status, is_same 等）
        - 如果任何一行的该字段为 True -> "yes"
        - 否则（包括没有数据） -> "no"
        如果查询结果里没有相关字段，再退回到基于原始答案文本的解析逻辑。
        """
        if query_result.get("success") and query_result.get("data"):
            data = query_result["data"]
            for row in data:
                if isinstance(row, dict):
                    # 检查所有包含 "same" 或布尔类型的键
                    for key, value in row.items():
                        # 匹配 same, same_status, is_same 等键名
                        if 'same' in key.lower() and value is True:
                            return "yes"
                        # 也检查布尔值结果（如 exist, result 等）
                        if isinstance(value, bool) and value is True:
                            return "yes"
            # 如果有数据但没有 true，则认为整体为 no
            return "no"

        # 回退：如果没有结构化结果，就按exist逻辑从文本里提取
        return self._format_exist_answer(raw_answer, query_result)
    
    def _format_general_answer(self, raw_answer: str) -> str:
        """格式化一般问题答案（保持简洁）"""
        # 移除<think>块
        answer = re.sub(r'<think>.*?</think>', '', raw_answer, flags=re.DOTALL).strip()

        # 移除冗余的解释性文字
        prefixes_to_remove = [
            '根据查询结果，',
            '查询结果显示，',
            '根据数据，',
            'Based on the query result, ',
            'The query shows that ',
            'According to the data, ',
        ]

        for prefix in prefixes_to_remove:
            if answer.startswith(prefix):
                answer = answer[len(prefix):]
        
        # 如果答案太长，提取关键短语
        if len(answer) > 50:
            answer = self._extract_key_phrase(answer)
        
        return answer.strip()
    
    def _extract_key_phrase(self, text: str) -> str:
        """提取关键短语"""
        # 移除解释性句子
        sentences = text.split('。')
        if len(sentences[0]) < 30:
            return sentences[0].strip()
        
        # 尝试提取名词短语
        words = text.split()
        if len(words) <= 3:
            return ' '.join(words)
        
        # 返回前3个词
        return ' '.join(words[:3])
    
    def validate(self, answer: str, question_type: str) -> bool:
        """
        验证答案是否符合格式要求
        
        Returns:
            True if valid, False otherwise
        """
        if question_type == 'exist' or question_type == 'comparison':
            return answer.lower() in ['yes', 'no']
        elif question_type == 'count':
            return answer.isdigit()
        elif question_type == 'status':
            valid_statuses = ['stopped', 'moving', 'with rider', 'without rider', 'parked', 'stationary']
            return any(status in answer.lower() for status in valid_statuses)
        elif question_type == 'object':
            # 支持 barrier 作为合法类型，用于0553等多跳问题
            valid_types = ['car', 'truck', 'bus', 'bicycle', 'pedestrian', 'ego', 'barrier']
            return any(obj_type in answer.lower() for obj_type in valid_types)
        else:
            return len(answer) > 0 and len(answer) < 100


class LLMAnswerJudge:
    """
    LLM最终答案判定器
    用于处理语义等价情况，如parked/stopped
    """
    
    # 语义等价组
    SEMANTIC_EQUIVALENTS = {
        'status': [
            {'parked', 'stopped'},  # 停车状态语义等价
        ]
    }
    
    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLM客户端（可选，用于复杂情况的判定）
        """
        self.llm = llm_client
    
    def judge(self, expected: str, actual: str, question_type: str, 
              question: str = "", use_llm: bool = True) -> Tuple[bool, str]:
        """
        判定答案是否正确
        
        Args:
            expected: 预期答案
            actual: 实际答案
            question_type: 问题类型
            question: 原始问题（用于LLM判定）
            use_llm: 是否在不确定时使用LLM判定
            
        Returns:
            (is_correct, reason): 是否正确及原因
        """
        expected_lower = expected.lower().strip()
        actual_lower = actual.lower().strip()
        
        # 1. 完全匹配
        if expected_lower == actual_lower:
            return True, "exact_match"
        
        # 2. 语义等价匹配
        if question_type in self.SEMANTIC_EQUIVALENTS:
            for equiv_group in self.SEMANTIC_EQUIVALENTS[question_type]:
                if expected_lower in equiv_group and actual_lower in equiv_group:
                    return True, f"semantic_equivalent: {expected_lower} ≈ {actual_lower}"
        
        # 3. 特殊情况处理
        # with_rider / without_rider 空格和下划线等价
        if question_type == 'status':
            expected_normalized = expected_lower.replace('_', ' ')
            actual_normalized = actual_lower.replace('_', ' ')
            if expected_normalized == actual_normalized:
                return True, "format_equivalent"
        
        # 4. 如果有LLM且允许使用，进行智能判定
        if use_llm and self.llm and question:
            is_correct, reason = self._llm_judge(expected, actual, question_type, question)
            return is_correct, f"llm_judge: {reason}"
        
        # 5. 默认不匹配
        return False, f"mismatch: expected '{expected}', got '{actual}'"
    
    def _llm_judge(self, expected: str, actual: str, question_type: str, question: str) -> Tuple[bool, str]:
        """使用LLM判定答案是否语义等价"""
        prompt = f"""You are a judge for a VQA (Visual Question Answering) system evaluation.

Question: {question}
Question Type: {question_type}
Expected Answer: {expected}
Actual Answer: {actual}

Determine if the actual answer is semantically correct given the expected answer.

Consider these semantic equivalences:
- For status: "parked" and "stopped" are often used interchangeably for stationary vehicles
- For status: "with_rider" and "with rider" are equivalent (underscore vs space)
- For boolean: "yes"/"true"/"1" are equivalent, "no"/"false"/"0" are equivalent

Respond with ONLY one of these two words:
- "CORRECT" if the actual answer is semantically correct
- "INCORRECT" if the actual answer is wrong

Your judgment:"""
        
        try:
            response = self.llm.call_llm_raw(prompt, max_tokens=50)
            response_upper = response.strip().upper()
            if "CORRECT" in response_upper and "INCORRECT" not in response_upper:
                return True, "llm_approved"
            else:
                return False, "llm_rejected"
        except Exception as e:
            return False, f"llm_error: {e}"


# 测试示例
if __name__ == '__main__':
    formatter = AnswerFormatter()
    
    test_cases = [
        {
            'raw_answer': '根据查询结果，有2辆卡车可见。',
            'question_type': 'exist',
            'query_result': {'success': True, 'count': 2, 'data': [{'count': 2}]},
            'expected': 'yes'
        },
        {
            'raw_answer': '查询结果显示有5个对象。',
            'question_type': 'count',
            'query_result': {'success': True, 'count': 1, 'data': [{'count': 5}]},
            'expected': '5'
        },
        {
            'raw_answer': '这辆车是静止的，速度为[0,0,0]。',
            'question_type': 'status',
            'query_result': {'success': True, 'data': [{'velocity': [0, 0, 0]}]},
            'expected': 'stopped'
        },
        {
            'raw_answer': '根据查询，这是一辆自行车(bicycle)。',
            'question_type': 'object',
            'query_result': {'success': True, 'data': [{'type': 'bicycle'}]},
            'expected': 'bicycle'
        },
    ]
    
    print("答案格式化测试:")
    print("=" * 80)
    for i, test in enumerate(test_cases, 1):
        formatted = formatter.format(
            test['raw_answer'],
            test['question_type'],
            test['query_result']
        )
        is_valid = formatter.validate(formatted, test['question_type'])
        
        print(f"\n测试 {i}:")
        print(f"原始答案: {test['raw_answer']}")
        print(f"问题类型: {test['question_type']}")
        print(f"格式化后: {formatted}")
        print(f"期望答案: {test['expected']}")
        print(f"验证通过: {'✅' if is_valid else '❌'}")
        print(f"匹配正确: {'✅' if formatted == test['expected'] else '❌'}")
        print("-" * 80)
