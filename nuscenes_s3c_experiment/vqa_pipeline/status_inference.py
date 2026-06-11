"""
状态推断模块
从NuScenes的attributes和velocity推断对象状态
"""
import numpy as np
from typing import List, Dict, Any, Optional


class StatusInferenceEngine:
    """状态推断引擎"""
    
    def __init__(self):
        # 状态关键词映射（基于NuScenes的attribute定义）
        self.status_keywords = {
            # 自行车状态
            'with_rider': ['cycle.with_rider'],
            'without_rider': ['cycle.without_rider'],
            
            # 车辆状态
            'stopped': ['vehicle.stopped', 'vehicle.parked'],
            'moving': ['vehicle.moving'],
            'parked': ['vehicle.parked'],
            
            # 行人状态
            'standing': ['pedestrian.standing'],
            'sitting': ['pedestrian.sitting_lying_down'],
            'moving_pedestrian': ['pedestrian.moving']
        }
    
    def infer_status(self, obj_data: Dict[str, Any]) -> Optional[str]:
        """
        从对象数据推断状态
        
        Args:
            obj_data: 对象数据，包含：
                - type: 对象类型
                - attributes: NuScenes attributes列表
                - velocity: 速度向量
                
        Returns:
            推断出的状态字符串，如 'with rider', 'stopped', 'moving'
        """
        obj_type = obj_data.get('type')
        attributes = obj_data.get('attributes', [])
        velocity = obj_data.get('velocity')
        
        # 优先使用attributes推断
        inferred_status = self._infer_from_attributes(attributes, obj_type)
        if inferred_status:
            return inferred_status
        
        # 其次使用velocity推断
        if velocity is not None:
            return self._infer_from_velocity(velocity, obj_type)
        
        # 默认返回unknown
        return 'unknown'
    
    def _infer_from_attributes(self, attributes: List[str], obj_type: str) -> Optional[str]:
        """从attributes推断状态"""
        if not attributes:
            return None
        
        # 检查每个状态关键词
        for status, keywords in self.status_keywords.items():
            for attr in attributes:
                if any(keyword in attr for keyword in keywords):
                    # 格式化为自然语言
                    if status == 'with_rider':
                        return 'with rider'
                    elif status == 'without_rider':
                        return 'without rider'
                    elif status == 'moving_pedestrian':
                        return 'moving'
                    else:
                        return status
        
        # 如果有attributes但不匹配任何状态，尝试从第一个attribute推断
        if attributes:
            first_attr = attributes[0].lower()
            if 'moving' in first_attr:
                return 'moving'
            elif 'stopped' in first_attr or 'parked' in first_attr:
                return 'stopped'
            elif 'standing' in first_attr:
                return 'standing'
        
        return None
    
    def _infer_from_velocity(self, velocity: List[float], obj_type: str) -> str:
        """从速度推断状态"""
        if velocity is None or all(v == 0 or v is None for v in velocity):
            return 'stopped'
        
        # 计算速度大小
        try:
            speed = np.linalg.norm([v for v in velocity[:2] if v is not None])
        except:
            return 'stopped'
        
        # 速度阈值判断
        if speed < 0.5:
            return 'stopped'
        else:
            return 'moving'
    
    def format_for_neo4j(self, status: Optional[str]) -> str:
        """格式化为Neo4j存储格式"""
        if status is None or status == 'unknown':
            return 'unknown'
        return status.lower().replace(' ', '_')
    
    def format_for_answer(self, status: str) -> str:
        """格式化为答案格式（用于LLM回答）"""
        if status == 'unknown':
            return 'unknown'
        # 将下划线格式转换为自然语言格式
        return status.replace('_', ' ')


# 测试
if __name__ == '__main__':
    engine = StatusInferenceEngine()
    
    print("=" * 60)
    print("状态推断引擎测试")
    print("=" * 60)
    
    # 测试用例1: with rider
    test1 = {
        'type': 'bicycle',
        'attributes': ['cycle.with_rider'],
        'velocity': [1.5, 0.3, 0]
    }
    result1 = engine.infer_status(test1)
    print(f"\n测试1: with rider")
    print(f"  输入: {test1}")
    print(f"  推断结果: {result1}")
    print(f"  Neo4j格式: {engine.format_for_neo4j(result1)}")
    print(f"  答案格式: {engine.format_for_answer(result1)}")
    assert result1 == 'with rider', f"期望 'with rider'，得到 '{result1}'"
    
    # 测试用例2: without rider
    test2 = {
        'type': 'bicycle',
        'attributes': ['cycle.without_rider'],
        'velocity': [0, 0, 0]
    }
    result2 = engine.infer_status(test2)
    print(f"\n测试2: without rider")
    print(f"  输入: {test2}")
    print(f"  推断结果: {result2}")
    assert result2 == 'without rider', f"期望 'without rider'，得到 '{result2}'"
    
    # 测试用例3: stopped (从attributes)
    test3 = {
        'type': 'car',
        'attributes': ['vehicle.parked'],
        'velocity': [0, 0, 0]
    }
    result3 = engine.infer_status(test3)
    print(f"\n测试3: stopped from attributes")
    print(f"  输入: {test3}")
    print(f"  推断结果: {result3}")
    assert result3 in ['stopped', 'parked'], f"期望 'stopped' 或 'parked'，得到 '{result3}'"
    
    # 测试用例4: moving (从velocity推断，无attributes)
    test4 = {
        'type': 'pedestrian',
        'attributes': [],
        'velocity': [2.0, 0.5, 0]
    }
    result4 = engine.infer_status(test4)
    print(f"\n测试4: moving from velocity")
    print(f"  输入: {test4}")
    print(f"  推断结果: {result4}")
    assert result4 == 'moving', f"期望 'moving'，得到 '{result4}'"
    
    # 测试用例5: stopped (从velocity推断，velocity为None)
    test5 = {
        'type': 'car',
        'attributes': [],
        'velocity': None
    }
    result5 = engine.infer_status(test5)
    print(f"\n测试5: stopped from None velocity")
    print(f"  输入: {test5}")
    print(f"  推断结果: {result5}")
    assert result5 == 'stopped', f"期望 'stopped'，得到 '{result5}'"
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
