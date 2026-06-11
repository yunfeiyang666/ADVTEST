"""
答案验证和格式化模块

功能：
1. 验证答案是否符合问题类型的格式要求
2. 格式化答案为标准格式
3. 提取关键信息
4. LLM最终答案判定（处理语义等价情况）

改进内容：
- 添加类型注解
- 抽取常量
- 改进错误处理
- 添加日志
"""
import re
import logging
from collections import Counter
from typing import Optional, Dict, Any, Tuple, List, Set

# 配置日志
logger = logging.getLogger(__name__)


# ==================== 常量 ====================
# 标准对象类型
OBJECT_TYPES: Set[str] = {
    'car', 'truck', 'bus', 'bicycle', 'pedestrian', 
    'ego', 'barrier', 'motorcycle', 'trailer'
}

# 标准状态值
STATUS_VALUES: Set[str] = {
    'stopped', 'moving', 'parked',
    'with rider', 'without rider', 'standing', 'sitting', 'unknown'
}

# 状态关键词映射
STATUS_KEYWORDS: Dict[str, List[str]] = {
    'stopped': ['stopped', 'stationary', 'not moving', '停止', '静止'],
    'parked': ['parked', '停放'],
    'moving': ['moving', 'driving', 'running', '移动', '行驶'],
    'with rider': ['with rider', 'with_rider', '有骑手', '有人骑'],
    'without rider': ['without rider', 'without_rider', '无骑手', '没人骑'],
    'standing': ['standing', '站立'],
    'sitting': ['sitting', '坐着'],
}

# Yes关键词
YES_KEYWORDS: List[str] = ['yes', '有', '存在', 'visible', 'found', 'true']

# No关键词
NO_KEYWORDS: List[str] = ['no', '没有', '不存在', 'not visible', 'not found', 'false']

# 凗余前缀
REDUNDANT_PREFIXES: List[str] = [
    '根据查询结果，',
    '查询结果显示，',
    '根据数据，',
    'Based on the query result, ',
    'The query shows that ',
    'According to the data, ',
]


class AnswerFormatter:
    """答案格式化器"""
    
    def __init__(self):
        """初始化"""
        pass

    def _strip_think(self, text: str) -> str:
        """移除<think>...</think>内容，杜绝从思考中提取答案。"""
        if not text:
            return ""
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        cleaned = re.sub(r'<think>.*', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'</think>', '', cleaned, flags=re.DOTALL)
        return cleaned.strip()

    def _normalize_status(self, text: str) -> Optional[str]:
        """标准化状态词（严格校验，只返回合法状态）"""
        if not text:
            return None
        s = str(text).strip().lower().replace('_', ' ')
        if s in STATUS_VALUES:
            return s
        return None
    
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
        cleaned_answer = self._strip_think(raw_answer)
        if not cleaned_answer:
            logger.warning("原始答案为空")
            return self._get_default_answer(question_type)
        
        try:
            if question_type == 'exist':
                return self._format_exist_answer(cleaned_answer, query_result)
            elif question_type == 'count':
                return self._format_count_answer(cleaned_answer, query_result)
            elif question_type == 'status':
                return self._format_status_answer(cleaned_answer, query_result)
            elif question_type == 'object':
                return self._format_object_answer(cleaned_answer, query_result)
            elif question_type == 'comparison':
                return self._format_comparison_answer(cleaned_answer, query_result)
            else:
                return self._format_general_answer(cleaned_answer)
        except Exception as e:
            logger.error(f"格式化答案失败: {e}")
            return self._format_general_answer(cleaned_answer)
    
    def _get_default_answer(self, question_type: str) -> str:
        """获取默认答案"""
        defaults = {
            'exist': 'no',
            'count': '0',
            'status': 'unknown',
            'object': 'unknown',
            'comparison': 'no',
        }
        return defaults.get(question_type, 'unknown')
    
    def _format_exist_answer(self, raw_answer: str, query_result: Dict) -> str:
        """
        格式化存在性问题答案为yes/no
        
        Args:
            raw_answer: 原始答案
            query_result: 查询结果
        
        Returns:
            'yes' 或 'no'
        """
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
        raw_lower = raw_answer.lower()
        
        if any(word in raw_lower for word in YES_KEYWORDS):
            return 'yes'
        elif any(word in raw_lower for word in NO_KEYWORDS):
            return 'no'
        
        # 默认返回no（保守策略）
        logger.debug(f"无法从答案提取yes/no，默认返回'no': {raw_answer[:50]}")
        return 'no'
    
    def _format_count_answer(self, raw_answer: str, query_result: Dict) -> str:
        """
        格式化计数问题答案为纯数字
        
        Args:
            raw_answer: 原始答案
            query_result: 查询结果
        
        Returns:
            数字字符串
        """
        # 首先尝试从查询结果提取
        if query_result.get('success') and query_result.get('data'):
            data = query_result['data']
            if data and isinstance(data[0], dict):
                # 查找count相关的键
                for key, value in data[0].items():
                    if 'count' in key.lower() and isinstance(value, (int, float)):
                        return str(int(value))
                # 如果只有一个数值，也认为是count
                for value in data[0].values():
                    if isinstance(value, (int, float)):
                        return str(int(value))
        
        # 从原始答案提取数字
        numbers = re.findall(r'\b\d+\b', raw_answer)
        if numbers:
            return numbers[0]
        
        # 如果没找到，返回0
        logger.debug(f"无法从答案提取数字，默认返回'0': {raw_answer[:50]}")
        return '0'
    
    def _format_status_answer(self, raw_answer: str, query_result: Dict) -> str:
        """
        格式化状态问题答案
        
        Args:
            raw_answer: 原始答案
            query_result: 查询结果
        
        Returns:
            标准化的状态值
        """
        # 优先从查询结果中直接提取status字段
        if query_result.get('success') and query_result.get('data'):
            data = query_result['data']
            if data and isinstance(data[0], dict):
                # 查找status相关的键
                for key, value in data[0].items():
                    if 'status' in key.lower() and isinstance(value, str) and value:
                        status = self._normalize_status(value)
                        if status:
                            return status
        
        raw_lower = raw_answer.lower()
        
        # 检查是否包含状态关键词（使用全局常量）
        for standard_status, keywords in STATUS_KEYWORDS.items():
            if any(kw in raw_lower for kw in keywords):
                normalized = self._normalize_status(standard_status)
                if normalized:
                    return normalized
        
        # 从单词中查找标准状态
        words = raw_answer.split()
        for word in words:
            normalized = self._normalize_status(word)
            if normalized:
                return normalized
        
        # 严格策略：无法识别就返回 unknown
        logger.debug(f"无法标准化状态答案，返回unknown: {raw_answer[:50]}")
        return 'unknown'
    
    def _format_object_answer(self, raw_answer: str, query_result: Dict) -> str:
        """
        格式化对象识别问题答案
        
        Args:
            raw_answer: 原始答案
            query_result: 查询结果
        
        Returns:
            对象类型名称
        """
        # 从查询结果提取：如果有多行，取出现频率最高的类型
        if query_result.get('success') and query_result.get('data'):
            data = query_result['data']
            if data and isinstance(data[0], dict):
                types_from_result = []
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    # 尝试多个字段名
                    t = row.get('type') or row.get('obj.type') or row.get('object_type')
                    if isinstance(t, str):
                        t_lower = t.lower()
                        if t_lower in OBJECT_TYPES:
                            types_from_result.append(t_lower)
                
                if types_from_result:
                    # 返回出现最多的类型
                    counter = Counter(types_from_result)
                    majority_type, _ = counter.most_common(1)[0]
                    return majority_type
        
        # 从答案文本提取（按长度排序，避免短词匹配错误）
        raw_lower = raw_answer.lower()
        sorted_types = sorted(OBJECT_TYPES, key=len, reverse=True)
        for obj_type in sorted_types:
            if obj_type in raw_lower:
                return obj_type
        
        # 如果没找到标准类型，返回清理后的答案
        result = self._extract_key_phrase(raw_answer)
        logger.debug(f"无法提取标准对象类型，返回: {result}")
        return result
    
    def _format_comparison_answer(self, raw_answer: str, query_result: Dict) -> str:
        """格式化比较问题答案为yes/no。

        ⚠️ 重要：如果查询结果实际返回的是count（数字），说明问题可能被误分类，
        应该返回数字而不是强制转换为yes/no。
        
        优先直接依据查询结果中的布尔值字段：
        - 检查所有包含 "same" 的键（如 same, same_status, is_same 等）
        - 如果任何一行的该字段为 True -> "yes"
        - 否则（包括没有数据） -> "no"
        如果查询结果里没有相关字段，再退回到基于原始答案文本的解析逻辑。
        """
        # ⚠️ 检测误分类：如果原始答案是纯数字，且查询结果包含count，说明这是count问题而非comparison
        if query_result.get("success") and query_result.get("data"):
            data = query_result["data"]
            if data and isinstance(data[0], dict):
                # 检查是否包含count字段
                for key, value in data[0].items():
                    if 'count' in key.lower() and isinstance(value, (int, float)):
                        # 这是count问题，返回数字
                        logger.warning(f"问题被误分类为comparison，实际是count。查询返回: {value}")
                        return str(int(value))
        
        # 检查原始答案是否为纯数字
        raw_stripped = raw_answer.strip()
        if raw_stripped.isdigit():
            logger.warning(f"comparison问题返回纯数字答案: {raw_stripped}，可能被误分类")
            return raw_stripped
        
        # 正常comparison逻辑：检查布尔值或字符串yes/true
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
                        # Bug fix: 检查字符串 "yes"/"true"（LLM可能返回字符串而非布尔值）
                        if isinstance(value, str) and value.lower() in ('yes', 'true'):
                            return "yes"
            # 如果有数据但没有 true/yes，则认为整体为 no
            return "no"

        # 回退：如果没有结构化结果，就按exist逻辑从文本里提取
        return self._format_exist_answer(raw_answer, query_result)
    
    def _format_general_answer(self, raw_answer: str) -> str:
        """
        格式化一般问题答案（保持简洁）
        
        Args:
            raw_answer: 原始答案
        
        Returns:
            格式化后的答案
        """
        answer = raw_answer.strip()

        # 移除冗余的解释性文字（使用全局常量）
        for prefix in REDUNDANT_PREFIXES:
            if answer.startswith(prefix):
                answer = answer[len(prefix):]
                break
        
        # 如果答案太长，提取关键短语
        if len(answer) > 50:
            answer = self._extract_key_phrase(answer)
        
        return answer.strip()
    
    def _extract_key_phrase(self, text: str, max_words: int = 3) -> str:
        """
        提取关键短语
        
        Args:
            text: 输入文本
            max_words: 最大单词数
        
        Returns:
            关键短语
        """
        if not text:
            return ''
        
        # 移除解释性句子
        sentences = text.split('。')
        if sentences and len(sentences[0]) < 30:
            return sentences[0].strip()
        
        # 按空格分词
        words = text.split()
        if not words:
            return text.strip()
        
        if len(words) <= max_words:
            return ' '.join(words)
        
        # 返回前N个词
        return ' '.join(words[:max_words])
    
    def validate(self, answer: str, question_type: str) -> bool:
        """
        验证答案是否符合格式要求
        
        Args:
            answer: 答案
            question_type: 问题类型
        
        Returns:
            True if valid, False otherwise
        """
        if not answer:
            return False
        
        answer_lower = answer.lower()
        
        if question_type in ('exist', 'comparison'):
            return answer_lower in ('yes', 'no')
        elif question_type == 'count':
            return answer.isdigit() and int(answer) >= 0
        elif question_type == 'status':
            normalized = self._normalize_status(answer_lower)
            return normalized is not None
        elif question_type == 'object':
            # 使用全局OBJECT_TYPES
            return any(obj_type in answer_lower for obj_type in OBJECT_TYPES)
        else:
            # 一般问题：非空且长度合理
            return 0 < len(answer) < 100


class LLMAnswerJudge:
    """
    LLM最终答案判定器
    用于处理语义等价情况，如parked/stopped
    """
    
    # 语义等价组
    SEMANTIC_EQUIVALENTS: Dict[str, List[Set[str]]] = {
        'status': [
            {'parked', 'stopped'},   # 停车状态语义等价
            {'standing', 'stopped'}, # 站立也认为是停止
            {'sitting', 'stopped'},  # 坐着也是停止
        ]
    }
    
    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLM客户端（可选，用于复杂情况的判定）
        """
        self.llm = llm_client
    
    def judge(self, expected: str, actual: str, question_type: str = '', 
              question: str = '', use_llm: bool = True) -> Tuple[bool, str]:
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
        if not expected or not actual:
            return False, "empty_answer"
        
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
        """
        使用LLM判定答案是否语义等价
        
        Args:
            expected: 预期答案
            actual: 实际答案
            question_type: 问题类型
            question: 原始问题
        
        Returns:
            (是否正确, 原因)
        """
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
            logger.warning(f"LLM判定失败: {e}")
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
