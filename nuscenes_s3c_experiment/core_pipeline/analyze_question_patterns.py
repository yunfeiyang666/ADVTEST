"""
问题数据集特征分析工具

分析维度：
1. 问题类型分布（计数、存在性、属性查询等）
2. 涉及的对象类型
3. 空间关系类型（方向词）
4. 查询复杂度（单跳/多跳）
5. 答案类型分布
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


@dataclass
class QuestionFeatures:
    """问题特征"""
    question: str
    answer: str
    
    # 问题类型
    question_type: str = ""  # count, existence, attribute, identification
    
    # 涉及的元素
    mentioned_objects: Set[str] = field(default_factory=set)  # 提到的对象类型
    specific_ids: Set[str] = field(default_factory=set)       # 特定对象ID (如 car1)
    involves_ego: bool = False
    
    # 空间关系
    directions: List[str] = field(default_factory=list)        # 方向词
    hop_count: int = 0                                         # 跳数（单跳/多跳）
    
    # 属性查询
    queried_attributes: Set[str] = field(default_factory=set)  # status, type等
    
    # 答案类型
    answer_type: str = ""  # number, yes/no, object_id, status, other


class QuestionAnalyzer:
    """问题分析器"""
    
    # 对象类型关键词
    OBJECT_TYPES = {
        'car', 'truck', 'bus', 'pedestrian', 'bicycle', 
        'motorcycle', 'trailer', 'barrier', 'vehicle', 'object'
    }
    
    # 方向关键词
    DIRECTIONS = {
        'front', 'back', 'left', 'right', 
        'front-left', 'front-right', 'back-left', 'back-right',
        'ahead', 'behind', 'forward', 'rear'
    }
    
    # 属性关键词
    ATTRIBUTES = {
        'status', 'moving', 'stopped', 'parked', 'standing',
        'with_rider', 'without_rider', 'rider'
    }
    
    # 问题类型模式
    COUNT_PATTERNS = [
        r'how many', r'count', r'number of'
    ]
    
    EXISTENCE_PATTERNS = [
        r'is there', r'are there', r'any', r'exist'
    ]
    
    ATTRIBUTE_PATTERNS = [
        r'what.+status', r'status of', r'is.+moving', r'is.+stopped', r'is.+parked'
    ]
    
    IDENTIFICATION_PATTERNS = [
        r'what is', r'which', r'what\s+\w+\s+is', r'closest', r'nearest', r'farthest'
    ]
    
    def analyze(self, question: str, answer: str) -> QuestionFeatures:
        """分析单个问题"""
        features = QuestionFeatures(question=question, answer=answer)
        
        q_lower = question.lower()
        
        # 1. 分析问题类型
        features.question_type = self._classify_question_type(q_lower)
        
        # 2. 提取对象类型
        features.mentioned_objects = self._extract_object_types(q_lower)
        
        # 3. 提取特定对象ID
        features.specific_ids = self._extract_specific_ids(q_lower)
        
        # 4. 检查是否涉及ego
        features.involves_ego = self._involves_ego(q_lower)
        
        # 5. 提取方向词
        features.directions = self._extract_directions(q_lower)
        
        # 6. 计算跳数
        features.hop_count = self._estimate_hop_count(q_lower, features.directions)
        
        # 7. 提取属性查询
        features.queried_attributes = self._extract_attributes(q_lower)
        
        # 8. 分析答案类型
        features.answer_type = self._classify_answer_type(answer)
        
        return features
    
    def _classify_question_type(self, q_lower: str) -> str:
        """分类问题类型"""
        for pattern in self.COUNT_PATTERNS:
            if re.search(pattern, q_lower):
                return 'count'
        
        for pattern in self.EXISTENCE_PATTERNS:
            if re.search(pattern, q_lower):
                return 'existence'
        
        for pattern in self.ATTRIBUTE_PATTERNS:
            if re.search(pattern, q_lower):
                return 'attribute'
        
        for pattern in self.IDENTIFICATION_PATTERNS:
            if re.search(pattern, q_lower):
                return 'identification'
        
        return 'other'
    
    def _extract_object_types(self, q_lower: str) -> Set[str]:
        """提取对象类型（优化版 - 使用边界匹配）"""
        found = set()
        for obj_type in self.OBJECT_TYPES:
            # 使用边界匹配，避免 "scarf" 匹配到 "car"
            if re.search(r'\b' + re.escape(obj_type) + r'\b', q_lower):
                found.add(obj_type)
        return found
    
    def _extract_specific_ids(self, q_lower: str) -> Set[str]:
        """提取特定对象ID"""
        # 匹配 car1, pedestrian2 等
        pattern = r'\b(car|truck|pedestrian|bicycle|motorcycle|bus|trailer|barrier)(\d+)\b'
        matches = re.findall(pattern, q_lower)
        return {f"{obj_type}{num}" for obj_type, num in matches}
    
    def _involves_ego(self, q_lower: str) -> bool:
        """检查是否涉及ego"""
        ego_patterns = ['ego', ' me ', ' my ', ' i ', 'myself']
        return any(p in q_lower or q_lower.startswith(p.strip()) or q_lower.endswith(p.strip()) 
                   for p in ego_patterns)
    
    def _extract_directions(self, q_lower: str) -> List[str]:
        """提取方向词（修正版）"""
        found = []
        temp_q = q_lower  # 使用临时变量，避免重复匹配
        
        # 1. 先匹配复合方向（长词优先）
        compound_directions = ['front-left', 'front-right', 'back-left', 'back-right',
                               'front left', 'front right', 'back left', 'back right']
        
        for direction in compound_directions:
            if direction in temp_q:
                # 记录归一化后的方向
                norm_dir = direction.replace(' ', '-')
                count = temp_q.count(direction)
                found.extend([norm_dir] * count)
                # 从文本中移除已匹配的词，防止 "front-left" 后续又匹配到 "front"
                temp_q = temp_q.replace(direction, " ")
        
        # 2. 再匹配基本方向（匹配剩余文本）
        for direction in self.DIRECTIONS:
            # 忽略复合词部分，只看基础词
            if '-' in direction:
                continue
            
            # 使用正则在剩余文本中查找
            matches = re.findall(r'\b' + re.escape(direction) + r'\b', temp_q)
            found.extend(matches)
        
        return found
    
    def _estimate_hop_count(self, q_lower: str, directions: List[str]) -> int:
        """估算跳数"""
        # 两跳的标志
        two_hop_indicators = [
            'that is', 'which is', 'that are', 'which are',
            'of the', 'to the .* of the'
        ]
        
        # 多个方向词暗示多跳
        if len(directions) >= 2:
            return 2
        
        # 语法结构暗示多跳
        for indicator in two_hop_indicators:
            if re.search(indicator, q_lower):
                return 2
        
        # 单跳
        if len(directions) == 1 or any(obj in q_lower for obj in self.OBJECT_TYPES):
            return 1
        
        # 无空间关系
        return 0
    
    def _extract_attributes(self, q_lower: str) -> Set[str]:
        """提取属性查询"""
        found = set()
        for attr in self.ATTRIBUTES:
            if attr in q_lower:
                found.add(attr)
        return found
    
    def _classify_answer_type(self, answer: str) -> str:
        """分类答案类型"""
        answer_lower = answer.lower().strip()
        
        # yes/no
        if answer_lower in ['yes', 'no']:
            return 'yes/no'
        
        # 数字
        if answer_lower.isdigit():
            return 'number'
        
        # 对象ID (car1, pedestrian2等)
        if re.match(r'^(car|truck|pedestrian|bicycle|motorcycle|bus|trailer|barrier)\d+$', answer_lower):
            return 'object_id'
        
        # 状态
        status_values = ['moving', 'stopped', 'parked', 'standing', 'with_rider', 'without_rider']
        if answer_lower in status_values:
            return 'status'
        
        return 'other'


class DatasetStatistics:
    """数据集统计"""
    
    def __init__(self):
        self.total_questions = 0
        
        # 问题类型统计
        self.question_types = Counter()
        
        # 对象类型统计
        self.object_mentions = Counter()
        self.specific_id_mentions = Counter()
        self.ego_involvement = 0
        
        # 空间关系统计
        self.direction_usage = Counter()
        self.hop_distribution = Counter()
        
        # 属性统计
        self.attribute_queries = Counter()
        
        # 答案类型统计
        self.answer_types = Counter()
        
        # 复杂度统计
        self.complexity_distribution = defaultdict(int)
    
    def update(self, features: QuestionFeatures):
        """更新统计"""
        self.total_questions += 1
        
        # 问题类型
        self.question_types[features.question_type] += 1
        
        # 对象
        for obj in features.mentioned_objects:
            self.object_mentions[obj] += 1
        for obj_id in features.specific_ids:
            self.specific_id_mentions[obj_id] += 1
        if features.involves_ego:
            self.ego_involvement += 1
        
        # 方向
        for direction in features.directions:
            self.direction_usage[direction] += 1
        self.hop_distribution[features.hop_count] += 1
        
        # 属性
        for attr in features.queried_attributes:
            self.attribute_queries[attr] += 1
        
        # 答案类型
        self.answer_types[features.answer_type] += 1
        
        # 复杂度（启发式）
        complexity = 'simple'
        if features.hop_count >= 2:
            complexity = 'complex'
        elif features.hop_count == 1 and len(features.queried_attributes) > 0:
            complexity = 'medium'
        elif features.hop_count == 1:
            complexity = 'medium'
        
        self.complexity_distribution[complexity] += 1
    
    def print_report(self):
        """打印统计报告"""
        logger.info("\n" + "="*70)
        logger.info("  问题数据集特征分析报告")
        logger.info("="*70)
        
        logger.info(f"\n总问题数: {self.total_questions}")
        
        # 问题类型分布
        logger.info("\n【问题类型分布】")
        for qtype, count in self.question_types.most_common():
            pct = 100 * count / self.total_questions
            logger.info(f"  {qtype:15s}: {count:3d} ({pct:5.1f}%)")
        
        # 对象类型分布
        logger.info("\n【涉及的对象类型 (Top 10)】")
        for obj_type, count in self.object_mentions.most_common(10):
            pct = 100 * count / self.total_questions
            logger.info(f"  {obj_type:15s}: {count:3d} ({pct:5.1f}%)")
        
        logger.info(f"\n  涉及 ego 的问题: {self.ego_involvement} ({100*self.ego_involvement/self.total_questions:.1f}%)")
        
        if self.specific_id_mentions:
            logger.info("\n【特定对象ID提及 (Top 10)】")
            for obj_id, count in self.specific_id_mentions.most_common(10):
                logger.info(f"  {obj_id:15s}: {count:3d}")
        
        # 空间关系分布
        logger.info("\n【方向词使用频率】")
        for direction, count in self.direction_usage.most_common():
            pct = 100 * count / self.total_questions
            logger.info(f"  {direction:15s}: {count:3d} ({pct:5.1f}%)")
        
        # 跳数分布
        logger.info("\n【查询跳数分布】")
        for hop_count in sorted(self.hop_distribution.keys()):
            count = self.hop_distribution[hop_count]
            pct = 100 * count / self.total_questions
            hop_label = f"{hop_count}-hop" if hop_count > 0 else "0-hop (no spatial relation)"
            logger.info(f"  {hop_label:30s}: {count:3d} ({pct:5.1f}%)")
        
        # 属性查询
        if self.attribute_queries:
            logger.info("\n【属性查询频率】")
            for attr, count in self.attribute_queries.most_common():
                pct = 100 * count / self.total_questions
                logger.info(f"  {attr:15s}: {count:3d} ({pct:5.1f}%)")
        
        # 答案类型分布
        logger.info("\n【答案类型分布】")
        for atype, count in self.answer_types.most_common():
            pct = 100 * count / self.total_questions
            logger.info(f"  {atype:15s}: {count:3d} ({pct:5.1f}%)")
        
        # 复杂度分布
        logger.info("\n【问题复杂度分布】")
        for complexity in ['simple', 'medium', 'complex']:
            count = self.complexity_distribution[complexity]
            pct = 100 * count / self.total_questions if self.total_questions > 0 else 0
            logger.info(f"  {complexity:15s}: {count:3d} ({pct:5.1f}%)")
        
        # L-Level 映射报告
        logger.info("\n" + "="*70)
        logger.info("  L-Level 覆盖率评估 (基于问题意图)")
        logger.info("="*70)
        
        total = self.total_questions
        
        # L0: 涉及显式节点的问题
        l0_questions = self.ego_involvement + len([q for q in self.specific_id_mentions if self.specific_id_mentions[q] > 0])
        l0_pct = 100 * l0_questions / total if total > 0 else 0
        logger.info(f"\nL0 (显式节点引用): {l0_questions} 题 ({l0_pct:.1f}%)")
        logger.info(f"  - 涉及 ego: {self.ego_involvement} 题")
        logger.info(f"  - 涉及特定ID: {len(self.specific_id_mentions)} 个不同ID")
        
        # L1: 空间关系查询（至少1跳）
        l1_questions = sum(cnt for hop, cnt in self.hop_distribution.items() if hop >= 1)
        l1_pct = 100 * l1_questions / total if total > 0 else 0
        logger.info(f"\nL1 (空间关系查询): {l1_questions} 题 ({l1_pct:.1f}%)")
        logger.info(f"  - 1-hop: {self.hop_distribution[1]} 题")
        logger.info(f"  - 2-hop及以上: {sum(cnt for hop, cnt in self.hop_distribution.items() if hop >= 2)} 题")
        
        # L2: 多跳复杂推理（2跳及以上）
        l2_questions = sum(cnt for hop, cnt in self.hop_distribution.items() if hop >= 2)
        l2_pct = 100 * l2_questions / total if total > 0 else 0
        logger.info(f"\nL2 (多跳复杂推理): {l2_questions} 题 ({l2_pct:.1f}%)")
        if l2_questions > 0:
            logger.info(f"  ⚠️ 高复杂度问题占比: {l2_pct:.1f}%")
        
        logger.info("\n" + "="*70)


def analyze_questions(questions: List[Dict]) -> DatasetStatistics:
    """分析问题集"""
    analyzer = QuestionAnalyzer()
    stats = DatasetStatistics()
    
    for q in questions:
        question = q.get('question', '')
        answer = q.get('answer', q.get('expected_answer', ''))
        
        features = analyzer.analyze(question, answer)
        stats.update(features)
    
    return stats


def main():
    """主函数"""
    import sys
    
    print("="*70)
    print("  问题数据集特征分析工具")
    print("="*70)
    
    # 默认路径
    default_path = "output/coverage_analysis/qa_data/scene-0103_frame38_qa.json"
    
    # 命令行参数
    if len(sys.argv) >= 2:
        qa_path = sys.argv[1]
    else:
        qa_path = default_path
    
    qa_path = Path(qa_path)
    
    # 检查文件
    if not qa_path.exists():
        logger.error(f"找不到问题文件: {qa_path}")
        logger.info("\n用法: python analyze_question_patterns.py <questions.json>")
        logger.info(f"默认路径: {default_path}")
        return
    
    # 加载问题
    with open(qa_path, 'r', encoding='utf-8') as f:
        qa_data = json.load(f)
    
    questions = qa_data.get('questions', [])
    if not questions:
        # 尝试从 results 格式提取
        questions = [{'question': r['question'], 'answer': r.get('expected_answer', '')} 
                    for r in qa_data.get('results', [])]
    
    if not questions:
        logger.error("未找到问题数据")
        return
    
    logger.info(f"\n已加载 {len(questions)} 个问题")
    logger.info(f"来源: {qa_path}\n")
    
    # 分析
    stats = analyze_questions(questions)
    
    # 打印报告
    stats.print_report()
    
    # 保存结果
    output_path = qa_path.parent / f"{qa_path.stem}_analysis.json"
    output_data = {
        'source': str(qa_path),
        'total_questions': stats.total_questions,
        'question_types': dict(stats.question_types),
        'object_mentions': dict(stats.object_mentions),
        'ego_involvement': stats.ego_involvement,
        'direction_usage': dict(stats.direction_usage),
        'hop_distribution': dict(stats.hop_distribution),
        'attribute_queries': dict(stats.attribute_queries),
        'answer_types': dict(stats.answer_types),
        'complexity_distribution': dict(stats.complexity_distribution),
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n分析结果已保存: {output_path}")


if __name__ == "__main__":
    main()
