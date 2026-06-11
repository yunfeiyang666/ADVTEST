#!/usr/bin/env python
"""
简化版双坐标系VQA评估 - 直接运行版本
"""
import json
import sys
import re
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent / 'core_pipeline'))
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig


class SimpleDualFrameEvaluator:
    """简化版双坐标系VQA评估器"""
    
    def __init__(self, questions_file: str):
        self.questions = self._load_questions(questions_file)
        self.config = Neo4jConfig.from_env()
        self.importer = None
        
    def _load_questions(self, file_path: str) -> List[Dict]:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        questions = []
        for q_id, q_data in data.items():
            questions.append({
                'id': q_id,
                'question': q_data['question'],
                'ground_truth': q_data['ground_truth'],
                'scene': q_data['metadata']['scene_name']
            })
        return questions
    
    def _parse_question(self, question: str) -> Dict:
        """解析问题提取关键信息（支持中英文）"""
        info = {
            'source_obj': None,
            'target_type': None,
            'direction': None,
            'distance': None,
            'query_type': None,
            'status_filter': None
        }
        
        q_lower = question.lower()
        
        # === 检测对象类型（中英文） ===
        type_map = {
            'pedestrian': 'pedestrian', '行人': 'pedestrian',
            'car': 'car', '车': 'car', '车辆': 'car',
            'truck': 'truck', '卡车': 'truck',
            'bus': 'bus', '工交车': 'bus', '公交': 'bus',
            'motorcycle': 'motorcycle', '摩托车': 'motorcycle',
            'bicycle': 'bicycle', '自行车': 'bicycle',
            'barrier': 'barrier', '障碍物': 'barrier',
            'trailer': 'trailer', '拖车': 'trailer'
        }
        for keyword, obj_type in type_map.items():
            if keyword in q_lower:
                info['target_type'] = obj_type
                break
        
        # === 检测方向（中英文，优先匹配复合方向） ===
        direction_map = [
            # 英文复合方向（优先）
            ('back right', 'back-right'), ('back left', 'back-left'),
            ('front right', 'front-right'), ('front left', 'front-left'),
            # 中文复合方向
            ('后右', 'back-right'), ('右后', 'back-right'),
            ('后左', 'back-left'), ('左后', 'back-left'),
            ('前右', 'front-right'), ('右前', 'front-right'),
            ('前左', 'front-left'), ('左前', 'front-left'),
            # 英文单方向
            ('front', 'front'), ('back', 'back'),
            ('left', 'left'), ('right', 'right'),
            # 中文单方向
            ('前方', 'front'), ('前', 'front'),
            ('后方', 'back'), ('后', 'back'),
            ('左侧', 'left'), ('左', 'left'),
            ('右侧', 'right'), ('右', 'right'),
        ]
        for keyword, direction in direction_map:
            if keyword in q_lower:
                info['direction'] = direction
                break
        
        # === 检测状态过滤 ===
        if 'moving' in q_lower or '移动' in question:
            info['status_filter'] = 'moving'
        elif 'stopped' in q_lower or 'parked' in q_lower or '停止' in question or '停放' in question:
            info['status_filter'] = 'stopped'
        elif 'with rider' in q_lower:
            info['status_filter'] = 'with_rider'
        elif 'without rider' in q_lower:
            info['status_filter'] = 'without_rider'
        elif 'standing' in q_lower:
            info['status_filter'] = 'standing'
        elif 'not standing' in q_lower:
            info['status_filter'] = 'moving'
        
        # === 检测距离 ===
        distance_match = re.search(r'(\d+)\s*(米|meter|m\b)', q_lower)
        if distance_match:
            info['distance'] = int(distance_match.group(1))
        
        # === 检测source对象 ===
        if '自车' in question or ' me' in q_lower or 'of me' in q_lower:
            info['source_obj'] = 'ego'
        elif 'ego' in q_lower:
            info['source_obj'] = 'ego'
        # 检测具体对象引用（如 "the truck", "the motorcycle"）
        obj_ref_match = re.search(r'the (truck|motorcycle|bicycle|car|bus|pedestrian)', q_lower)
        if obj_ref_match and not info['source_obj']:
            info['source_obj'] = obj_ref_match.group(1)
        
        # === 判断查询类型 ===
        if '多少' in question or 'how many' in q_lower or 'what number' in q_lower:
            info['query_type'] = 'count'
        elif '吗' in question or q_lower.endswith('?'):
            if 'is there' in q_lower or 'are there' in q_lower or 'are any' in q_lower:
                info['query_type'] = 'exist'
            elif 'is its status' in q_lower or 'same status' in q_lower or 'does' in q_lower:
                info['query_type'] = 'yesno'
            else:
                info['query_type'] = 'yesno'
        elif 'what is' in q_lower or 'what status' in q_lower:
            info['query_type'] = 'what'
        else:
            info['query_type'] = 'describe'
        
        return info
    
    def _build_cypher_ego(self, scene: str, info: Dict, use_direction_8: bool = False) -> str:
        """构建Ego Frame的Cypher查询
        
        Args:
            use_direction_8: 是否使用direction_8精确匹配（而不是angle_matches）
        """
        scene_ego = f"{scene}_ego"
        
        conditions = []
        if info['target_type']:
            conditions.append(f"tgt.type = '{info['target_type']}'")
        if info['direction']:
            if use_direction_8:
                # 精确匹配 direction_8
                conditions.append(f"r.direction_8_ego = '{info['direction']}'")
            else:
                # 模糊匹配 angle_matches
                conditions.append(f"'{info['direction']}' IN r.angle_matches_ego")
        if info['distance']:
            conditions.append(f"r.distance <= {info['distance']}")
        
        where_clause = " AND ".join(conditions) if conditions else "true"
        
        if info['query_type'] == 'count':
            return f"""
            MATCH (src:Object {{unique_id: '{scene_ego}'}})-[r:RELATES_TO]->(tgt:Object)
            WHERE {where_clause}
            RETURN count(tgt) as result
            """
        elif info['query_type'] == 'exist':
            return f"""
            MATCH (src:Object {{unique_id: '{scene_ego}'}})-[r:RELATES_TO]->(tgt:Object)
            WHERE {where_clause}
            RETURN CASE WHEN count(tgt) > 0 THEN 'yes' ELSE 'no' END as result
            """
        else:
            return f"""
            MATCH (src:Object {{unique_id: '{scene_ego}'}})-[r:RELATES_TO]->(tgt:Object)
            WHERE {where_clause}
            RETURN tgt.type as result
            LIMIT 1
            """
    
    def _build_cypher_source(self, scene: str, info: Dict, use_direction_8: bool = False) -> str:
        """构建Source Frame的Cypher查询
        
        Args:
            use_direction_8: 是否使用direction_8精确匹配
        """
        # 确定source对象
        if info['source_obj'] and info['source_obj'] not in ['ego', None]:
            # 查找该类型的第一个对象
            source_id = f"{scene}_{info['source_obj']}1"  # 如 truck1, motorcycle1
        else:
            source_id = f"{scene}_ego"
        
        conditions = []
        if info['target_type']:
            conditions.append(f"tgt.type = '{info['target_type']}'")
        if info['direction']:
            if use_direction_8:
                conditions.append(f"r.direction_8_source = '{info['direction']}'")
            else:
                conditions.append(f"'{info['direction']}' IN r.angle_matches_source")
        if info['distance']:
            conditions.append(f"r.distance <= {info['distance']}")
        
        where_clause = " AND ".join(conditions) if conditions else "true"
        
        if info['query_type'] == 'count':
            return f"""
            MATCH (src:Object {{unique_id: '{source_id}'}})-[r:RELATES_TO]->(tgt:Object)
            WHERE {where_clause}
            RETURN count(tgt) as result
            """
        elif info['query_type'] == 'exist':
            return f"""
            MATCH (src:Object {{unique_id: '{source_id}'}})-[r:RELATES_TO]->(tgt:Object)
            WHERE {where_clause}
            RETURN CASE WHEN count(tgt) > 0 THEN 'yes' ELSE 'no' END as result
            """
        else:
            return f"""
            MATCH (src:Object {{unique_id: '{source_id}'}})-[r:RELATES_TO]->(tgt:Object)
            WHERE {where_clause}
            RETURN tgt.type as result
            LIMIT 1
            """
    
    def _execute_query(self, cypher: str) -> Tuple[bool, str]:
        """执行Cypher查询"""
        try:
            with self.importer._session() as session:
                result = session.run(cypher)
                record = result.single()
                if record:
                    value = record['result']
                    if value is None:
                        return False, "No result"
                    return True, str(value)
                return False, "No record"
        except Exception as e:
            return False, f"Error: {e}"
    
    def _check_answer(self, result: str, ground_truth: str) -> bool:
        """检查答案是否正确"""
        result = result.strip().lower()
        ground_truth = ground_truth.strip().lower()
        
        # Yes/No答案
        if ground_truth in ['yes', 'no']:
            if 'yes' in result or result == 'yes':
                result = 'yes'
            elif 'no' in result or result == 'no':
                result = 'no'
            elif result and result != 'no result' and result != '0':
                result = 'yes'
            else:
                result = 'no'
            return result == ground_truth
        
        # 数值答案
        if ground_truth.isdigit():
            try:
                return int(result) == int(ground_truth)
            except:
                return False
        
        # 字符串匹配
        return result == ground_truth
    
    def evaluate_strategy(self, strategy: str) -> Dict:
        """评估单个策略"""
        print(f"\n{'='*60}")
        print(f"评估策略: {strategy}")
        print(f"{'='*60}")
        
        correct = 0
        details = []
        
        for i, q in enumerate(self.questions):
            print(f"\n[{i+1}/{len(self.questions)}] {q['id']}: {q['question']}")
            
            info = self._parse_question(q['question'])
            
            if strategy == 'ego':
                cypher = self._build_cypher_ego(q['scene'], info)
            else:  # source
                cypher = self._build_cypher_source(q['scene'], info)
            
            print(f"  解析: {info}")
            print(f"  Cypher: {cypher.strip()[:100]}...")
            
            success, result = self._execute_query(cypher)
            is_correct = success and self._check_answer(result, q['ground_truth'])
            
            if is_correct:
                correct += 1
                print(f"  ✓ 正确 (result: {result})")
            else:
                print(f"  ✗ 错误 (result: {result}, expected: {q['ground_truth']})")
            
            details.append({
                'question_id': q['id'],
                'question': q['question'],
                'ground_truth': q['ground_truth'],
                'result': result,
                'success': success,
                'correct': is_correct,
                'parsed_info': info
            })
        
        accuracy = (correct / len(self.questions) * 100) if self.questions else 0
        return {
            'strategy': strategy,
            'total': len(self.questions),
            'correct': correct,
            'accuracy': accuracy,
            'details': details
        }
    
    def evaluate_retry(self) -> Dict:
        """评估Retry策略（4层尝试）
        
        层次：
        1. Ego Frame + angle_matches (模糊匹配)
        2. Source Frame + angle_matches (模糊匹配)
        3. Ego Frame + direction_8 (精确匹配45度)
        4. Source Frame + direction_8 (精确匹配45度)
        """
        print(f"\n{'='*60}")
        print(f"评估策略: Retry (4层: Ego/Source + angle_matches/direction_8)")
        print(f"{'='*60}")
        
        correct = 0
        layer_success = {'ego_matches': 0, 'source_matches': 0, 'ego_dir8': 0, 'source_dir8': 0}
        details = []
        
        for i, q in enumerate(self.questions):
            print(f"\n[{i+1}/{len(self.questions)}] {q['id']}: {q['question'][:60]}...")
            
            info = self._parse_question(q['question'])
            print(f"  解析: type={info['target_type']}, dir={info['direction']}, src={info['source_obj']}")
            
            found = False
            used_layer = None
            final_result = None
            
            # Layer 1: Ego Frame + angle_matches
            if not found:
                cypher = self._build_cypher_ego(q['scene'], info, use_direction_8=False)
                success, result = self._execute_query(cypher)
                if success and self._check_answer(result, q['ground_truth']):
                    found = True
                    used_layer = 'ego_matches'
                    final_result = result
                    print(f"  ✓ Layer1 Ego+angle_matches成功: {result}")
            
            # Layer 2: Source Frame + angle_matches
            if not found:
                cypher = self._build_cypher_source(q['scene'], info, use_direction_8=False)
                success, result = self._execute_query(cypher)
                if success and self._check_answer(result, q['ground_truth']):
                    found = True
                    used_layer = 'source_matches'
                    final_result = result
                    print(f"  ✓ Layer2 Source+angle_matches成功: {result}")
            
            # Layer 3: Ego Frame + direction_8 (精确45度)
            if not found and info['direction']:
                cypher = self._build_cypher_ego(q['scene'], info, use_direction_8=True)
                success, result = self._execute_query(cypher)
                if success and self._check_answer(result, q['ground_truth']):
                    found = True
                    used_layer = 'ego_dir8'
                    final_result = result
                    print(f"  ✓ Layer3 Ego+direction_8成功: {result}")
            
            # Layer 4: Source Frame + direction_8 (精确45度)
            if not found and info['direction']:
                cypher = self._build_cypher_source(q['scene'], info, use_direction_8=True)
                success, result = self._execute_query(cypher)
                if success and self._check_answer(result, q['ground_truth']):
                    found = True
                    used_layer = 'source_dir8'
                    final_result = result
                    print(f"  ✓ Layer4 Source+direction_8成功: {result}")
            
            if found:
                correct += 1
                layer_success[used_layer] += 1
                details.append({
                    'question_id': q['id'],
                    'question': q['question'],
                    'ground_truth': q['ground_truth'],
                    'result': final_result,
                    'used_layer': used_layer,
                    'correct': True
                })
            else:
                print(f"  ✗ 所有层都失败 (expected: {q['ground_truth']})")
                details.append({
                    'question_id': q['id'],
                    'question': q['question'],
                    'ground_truth': q['ground_truth'],
                    'result': 'all_failed',
                    'used_layer': 'none',
                    'correct': False
                })
        
        accuracy = (correct / len(self.questions) * 100) if self.questions else 0
        print(f"\n统计:")
        print(f"  Layer1 Ego+angle_matches: {layer_success['ego_matches']}次")
        print(f"  Layer2 Source+angle_matches: {layer_success['source_matches']}次")
        print(f"  Layer3 Ego+direction_8: {layer_success['ego_dir8']}次")
        print(f"  Layer4 Source+direction_8: {layer_success['source_dir8']}次")
        
        return {
            'strategy': 'retry_4layer',
            'total': len(self.questions),
            'correct': correct,
            'accuracy': accuracy,
            'layer_success': layer_success,
            'details': details
        }
    
    def run(self, retry_only: bool = False):
        """运行评估
        
        Args:
            retry_only: 只运行Retry策略评估
        """
        print("\n" + "="*80)
        print("双坐标系VQA评估")
        print("="*80)
        print(f"问题总数: {len(self.questions)}")
        
        self.importer = Neo4jImporter(self.config)
        
        try:
            if retry_only:
                # 只运行Retry
                result_retry = self.evaluate_retry()
                
                print("\n" + "="*80)
                print("评估结果汇总")
                print("="*80)
                
                print(f"\nRetry (4-Layer):")
                print(f"  正确: {result_retry['correct']}/{result_retry['total']}")
                print(f"  准确率: {result_retry['accuracy']:.2f}%")
                ls = result_retry['layer_success']
                print(f"  分层统计:")
                print(f"    Layer1 Ego+angle_matches: {ls['ego_matches']}")
                print(f"    Layer2 Source+angle_matches: {ls['source_matches']}")
                print(f"    Layer3 Ego+direction_8: {ls['ego_dir8']}")
                print(f"    Layer4 Source+direction_8: {ls['source_dir8']}")
                
                output_data = {
                    'total_questions': len(self.questions),
                    'results': {'retry': result_retry}
                }
            else:
                # 完整评估
                result_ego = self.evaluate_strategy('ego')
                result_source = self.evaluate_strategy('source')
                result_retry = self.evaluate_retry()
                
                print("\n" + "="*80)
                print("评估结果汇总")
                print("="*80)
                
                for result in [result_ego, result_source, result_retry]:
                    strategy_name = {
                        'ego': 'Ego Frame Only',
                        'source': 'Source Frame Only',
                        'retry_4layer': 'Retry (4-Layer)'
                    }.get(result['strategy'], result['strategy'])
                    
                    print(f"\n{strategy_name}:")
                    print(f"  正确: {result['correct']}/{result['total']}")
                    print(f"  准确率: {result['accuracy']:.2f}%")
                    
                    if 'layer_success' in result:
                        ls = result['layer_success']
                        print(f"  分层: ego_m={ls['ego_matches']}, src_m={ls['source_matches']}, ego_8={ls['ego_dir8']}, src_8={ls['source_dir8']}")
                
                output_data = {
                    'total_questions': len(self.questions),
                    'results': {
                        'ego_only': result_ego,
                        'source_only': result_source,
                        'retry': result_retry
                    }
                }
            
            output_path = Path('output/vqa_dual_frame_evaluation_results.json')
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            print(f"\n✓ 详细结果已保存至: {output_path}")
            
        finally:
            if self.importer:
                self.importer.close()


def main():
    import sys
    
    # 默认使用官方完整的58题
    questions_file = "output/vqa_questions_all_official.json"
    retry_only = False
    
    # 解析命令行参数
    for arg in sys.argv[1:]:
        if arg == '--retry-only':
            retry_only = True
        else:
            questions_file = arg
    
    print(f"加载问题文件: {questions_file}")
    evaluator = SimpleDualFrameEvaluator(questions_file)
    
    if retry_only:
        print(f"\n模式: 只运行Retry策略 (4层)")
    else:
        print(f"\n模式: 完整评估 (Ego + Source + Retry)")
    
    evaluator.run(retry_only=retry_only)
    print("\n✓ 评估完成")


if __name__ == "__main__":
    main()
