"""
覆盖率驱动的LLM问答生成器

核心思路:
1. 分析现有问题集(如NuScenesQA)的覆盖率
2. 识别未覆盖或低覆盖的场景区域/模式
3. 动态生成prompt引导LLM生成针对性问题
4. 迭代验证覆盖率提升
"""
import json
import random
from typing import Dict, List, Optional, Tuple, Set
from pathlib import Path
from dataclasses import asdict
from collections import defaultdict

try:
    from .templates import TemplateManager
    from .generator import SceneGraphWithEdges, QAPair
    from .camera_mapper import CameraMapper
    from .config import TYPE_NAMES, STATUS_DISPLAY_NAMES, DIRECTIONS_8, OBJECT_TYPES
except ImportError:
    from templates import TemplateManager
    from generator import SceneGraphWithEdges, QAPair
    from camera_mapper import CameraMapper
    from config import TYPE_NAMES, STATUS_DISPLAY_NAMES, DIRECTIONS_8, OBJECT_TYPES


class CoverageDrivenGenerator:
    """
    覆盖率驱动的问答生成器
    
    工作流程:
    1. 加载场景图和覆盖率分析结果
    2. 识别低覆盖区域（对象、关系、模式等）
    3. 为LLM生成针对性prompt
    4. LLM生成问题和答案
    5. 更新覆盖率统计
    """
    
    def __init__(self, llm_client, config: Dict = None):
        """
        Args:
            llm_client: LLM客户端
            config: 配置参数
        """
        self.llm_client = llm_client
        self.config = config or {}
        self.template_manager = TemplateManager()
        self._question_counter = 0
        
        # 覆盖率统计
        self.coverage_stats = {
            "object_coverage": defaultdict(int),      # 每个对象被问到的次数
            "relation_coverage": defaultdict(int),    # 每个关系被问到的次数
            "pattern_coverage": defaultdict(int),     # 每个模式被覆盖的次数
            "difficulty_coverage": defaultdict(int),  # 每个难度级别的问题数
            "type_coverage": defaultdict(int),        # 每个问题类型的数量
        }
    
    def generate_from_coverage_gaps(self, 
                                    scene_data: Dict,
                                    coverage_analysis: Dict,
                                    target_count: int = 50,
                                    focus_areas: List[str] = None) -> List[QAPair]:
        """
        根据覆盖率缺口生成问题
        
        Args:
            scene_data: 场景图数据
            coverage_analysis: 覆盖率分析结果
            target_count: 目标生成问题数
            focus_areas: 重点关注的区域 ["low_object", "missing_relations", "rare_patterns"]
        
        Returns:
            生成的QA对列表
        """
        focus_areas = focus_areas or ["low_object", "missing_relations", "rare_patterns"]
        
        # 解析场景
        parser = SceneGraphWithEdges(scene_data)
        camera_mapper = CameraMapper(scene_data)
        
        print(f"基于覆盖率分析生成 {target_count} 个问题...")
        print(f"关注领域: {', '.join(focus_areas)}")
        
        qa_pairs = []
        
        # 识别覆盖率缺口
        gaps = self._identify_coverage_gaps(parser, coverage_analysis)
        
        print(f"\n发现覆盖率缺口:")
        print(f"  - 低覆盖对象: {len(gaps['low_coverage_objects'])}")
        print(f"  - 缺失关系: {len(gaps['missing_relations'])}")
        print(f"  - 稀有模式: {len(gaps['rare_patterns'])}")
        
        # 根据缺口生成问题
        generated = 0
        max_attempts = target_count * 3  # 防止死循环
        attempts = 0
        
        while generated < target_count and attempts < max_attempts:
            attempts += 1
            
            # 选择一个缺口类型
            gap_type = self._select_gap_type(gaps, focus_areas)
            if not gap_type:
                print(f"警告: 没有更多缺口可以填充")
                break
            
            # 为该缺口生成问题
            qa = self._generate_for_gap(parser, camera_mapper, gap_type, gaps[gap_type])
            
            if qa:
                qa_pairs.append(qa)
                generated += 1
                
                # 更新覆盖率统计
                self._update_coverage_stats(qa)
                
                if generated % 10 == 0:
                    print(f"  已生成: {generated}/{target_count}")
        
        print(f"\n总共生成 {len(qa_pairs)} 个问答对")
        return qa_pairs
    
    def _identify_coverage_gaps(self, parser: SceneGraphWithEdges, 
                                coverage_analysis: Dict) -> Dict[str, List]:
        """
        识别覆盖率缺口
        
        Returns:
            {
                "low_coverage_objects": [(obj_id, coverage_score), ...],
                "missing_relations": [(src, tgt, direction), ...],
                "rare_patterns": [pattern_description, ...],
                "underrepresented_types": [obj_type, ...],
            }
        """
        gaps = {
            "low_coverage_objects": [],
            "missing_relations": [],
            "rare_patterns": [],
            "underrepresented_types": [],
        }
        
        # 1. 识别低覆盖对象
        # 假设coverage_analysis中有object_coverage信息
        object_coverage = coverage_analysis.get("object_coverage", {})
        all_objects = set(parser.nodes.keys()) - {"ego"}
        
        for obj_id in all_objects:
            coverage = object_coverage.get(obj_id, 0)
            if coverage < 3:  # 被问到少于3次认为是低覆盖
                gaps["low_coverage_objects"].append((obj_id, coverage))
        
        # 按覆盖率排序
        gaps["low_coverage_objects"].sort(key=lambda x: x[1])
        
        # 2. 识别缺失的关系
        # 场景图中存在但未被问到的关系
        relation_coverage = coverage_analysis.get("relation_coverage", {})
        for edge in parser.edges:
            src = edge["source"]
            tgt = edge["target"]
            direction = self._get_direction_from_edge(edge)
            if not direction:
                continue
            
            rel_key = f"{src}-{direction}->{tgt}"
            if relation_coverage.get(rel_key, 0) == 0:
                gaps["missing_relations"].append((src, tgt, direction))
        
        # 3. 识别稀有模式
        # 例如: 特定类型+状态的组合、特定方向的查询等
        pattern_coverage = coverage_analysis.get("pattern_coverage", {})
        
        # 检查类型-状态组合覆盖
        for obj_id, node in parser.nodes.items():
            if obj_id == "ego":
                continue
            obj_type = node.get("type")
            status = node.get("status")
            if status and status != "unknown":
                pattern = f"{status}_{obj_type}"
                if pattern_coverage.get(pattern, 0) < 2:
                    gaps["rare_patterns"].append({
                        "type": "status_type_combo",
                        "obj_type": obj_type,
                        "status": status,
                        "example_obj": obj_id
                    })
        
        # 检查方向覆盖
        direction_coverage = coverage_analysis.get("direction_coverage", {})
        for direction in DIRECTIONS_8:
            if direction_coverage.get(direction, 0) < 5:
                gaps["rare_patterns"].append({
                    "type": "direction",
                    "direction": direction
                })
        
        # 4. 识别代表性不足的类型
        type_coverage = coverage_analysis.get("type_coverage", {})
        for obj_type in parser.object_types_present:
            if type_coverage.get(obj_type, 0) < 5:
                gaps["underrepresented_types"].append(obj_type)
        
        return gaps
    
    def _select_gap_type(self, gaps: Dict, focus_areas: List[str]) -> Optional[str]:
        """
        智能选择缺口类型 (加权策略)
        
        策略:
        - rare_patterns: 50% 权重 (稀有模式更有测试价值)
        - missing_relations: 30% 权重 (空间关系重要)
        - low_coverage_objects: 20% 权重 (单对象补充)
        """
        # 1. 过滤非空列表
        available = []
        weights = []
        
        weight_config = {
            "rare_patterns": 0.5,
            "missing_relations": 0.3,
            "low_coverage_objects": 0.2
        }
        
        if "low_object" in focus_areas and gaps.get("low_coverage_objects"):
            available.append("low_coverage_objects")
            weights.append(weight_config["low_coverage_objects"])
        
        if "missing_relations" in focus_areas and gaps.get("missing_relations"):
            available.append("missing_relations")
            weights.append(weight_config["missing_relations"])
        
        if "rare_patterns" in focus_areas and gaps.get("rare_patterns"):
            available.append("rare_patterns")
            weights.append(weight_config["rare_patterns"])
        
        if not available:
            return None  # 没有缺口，覆盖率100%!
        
        # 2. 加权随机选择
        return random.choices(available, weights=weights, k=1)[0]
    
    def _generate_for_gap(self, parser: SceneGraphWithEdges,
                         camera_mapper: CameraMapper,
                         gap_type: str,
                         gap_data: List) -> Optional[QAPair]:
        """
        为特定的覆盖率缺口生成问题
        
        Args:
            gap_type: 缺口类型
            gap_data: 该类型的缺口数据
        """
        if not gap_data:
            return None
        
        # 智能选择缺口: 优先选择coverage=0的对象
        gap_item = self._select_gap_item_intelligently(gap_type, gap_data)
        
        # 构建针对性的prompt
        prompt = self._build_gap_filling_prompt(parser, gap_type, gap_item)
        
        # LLM生成问答对
        qa_json = self._llm_generate_qa_pair(prompt)
        
        if not qa_json:
            return None
        
        # 解析并创建QAPair
        qa = self._parse_qa_from_llm(parser, camera_mapper, qa_json, gap_type, gap_item)
        
        # 从缺口列表中移除已处理的项
        gap_data.remove(gap_item)
        
        return qa
    
    def _select_gap_item_intelligently(self, gap_type: str, gap_data: List):
        """
        智能选择缺口项 (优先消零策略)
        
        策略:
        1. 对于low_coverage_objects: 优先选择coverage=0的对象
        2. 在相同coverage的对象中随机选择 (避免总是选同一个)
        """
        if gap_type == "low_coverage_objects":
            # gap_data 格式: [(obj_id, coverage), ...]
            # 按coverage排序
            sorted_gaps = sorted(gap_data, key=lambda x: x[1])  # coverage从小到大
            
            # 找到最小coverage值
            min_coverage = sorted_gaps[0][1]
            
            # 提取所有coverage=min_coverage的对象
            zero_shot_candidates = [item for item in sorted_gaps if item[1] == min_coverage]
            
            # 从这些候选中随机选一个
            return random.choice(zero_shot_candidates)
        
        else:
            # 其他类型: 直接随机
            return random.choice(gap_data)
    
    def _build_gap_filling_prompt(self, parser: SceneGraphWithEdges,
                                  gap_type: str, gap_item) -> str:
        """
        构建针对覆盖率缺口的prompt
        """
        # 场景基本信息
        scene_desc = self._get_scene_description(parser)
        
        if gap_type == "low_coverage_objects":
            obj_id, coverage = gap_item
            node = parser.nodes[obj_id]
            obj_type = node.get("type")
            status = node.get("status", "unknown")
            
            # 获取L0模板示例（直接展示模板原文）
            l0_templates = self._get_template_examples('L0')
            
            prompt = f"""你是NuScenes自动驾驶场景问答系统。

{scene_desc}

任务: 生成一个关于对象 {obj_id} 的问题和答案。

对象信息:
- ID: {obj_id}
- 类型: {obj_type}
- 状态: {status}
- 当前覆盖率: {coverage} (需要提升)

**参考问题模板（请选择一个模板并填充具体信息）**:
{l0_templates}

要求:
1. 必须参考上述模板格式生成问题
2. 将模板中的占位符替换为具体的对象信息
3. 问题必须涉及对象 {obj_id}
4. 答案要准确，基于对象的实际属性

请以JSON格式输出:
{{
  "question": "问题文本",
  "answer": "答案文本",
  "question_type": "exist/count/status/object/comparison",
  "difficulty": "L0",
  "target_objects": ["{obj_id}"],
  "reference_objects": [],
  "directions": [],
  "requires_temporal": false
}}

**重要**: 在<think>标签内完成思考后，必须在标签外输出JSON。
"""
        
        elif gap_type == "missing_relations":
            src, tgt, direction = gap_item
            src_node = parser.nodes[src]
            tgt_node = parser.nodes[tgt]
            tgt_type = tgt_node.get('type', 'object')
            
            # 获取L1模板示例（直接展示模板原文）
            l1_templates = self._get_template_examples('L1')
            
            prompt = f"""你是NuScenes自动驾驶场景问答系统。

{scene_desc}

任务: 生成一个关于空间关系的问题和答案。

关系信息:
- 源对象: {src} ({src_node.get('type')})
- 目标对象: {tgt} ({tgt_type})
- 方向: {direction} (从{src}看向{tgt})
- 当前覆盖率: 0 (该关系未被问到)

**参考问题模板（请选择一个模板并填充具体信息）**:
{l1_templates}

要求:
1. 必须参考上述模板格式生成问题
2. 问题必须涉及 {src} 和 {direction} 方向的空间关系
3. 使用Source Frame（以{src}的朝向为基准）
4. 答案要准确

请以JSON格式输出:
{{
  "question": "问题文本",
  "answer": "答案文本",
  "question_type": "exist/count/status/object/comparison",
  "difficulty": "L1",
  "target_objects": ["{tgt}"],
  "reference_objects": ["{src}"],
  "directions": ["{direction}"],
  "requires_temporal": false
}}

**重要**: 在<think>标签内完成思考后，必须在标签外输出JSON。
"""
        
        elif gap_type == "rare_patterns":
            if isinstance(gap_item, dict):
                if gap_item.get("type") == "status_type_combo":
                    obj_type = gap_item["obj_type"]
                    status = gap_item["status"]
                    example = gap_item["example_obj"]
                    
                    prompt = f"""你是NuScenes自动驾驶场景问答系统。

{scene_desc}

任务: 生成一个关于"{status} {obj_type}"组合的问题。

模式信息:
- 类型: {obj_type}
- 状态: {status}
- 示例对象: {example}
- 当前覆盖率: 低 (该组合很少被问到)

要求:
1. 问题要突出这个状态-类型组合
2. 可以询问"有多少个{status}的{obj_type}?"
3. 或"是否存在{status}的{obj_type}?"
4. 问题自然流畅

请以JSON格式输出:
{{
  "question": "问题文本",
  "answer": "答案文本",
  "question_type": "exist/count/status",
  "difficulty": "L0/L1",
  "target_objects": ["{example}"],
  "reference_objects": [],
  "directions": [],
  "requires_temporal": true
}}

**重要**: 在<think>标签内完成思考后，必须在标签外输出JSON。
"""
                elif gap_item.get("type") == "direction":
                    direction = gap_item["direction"]
                    prompt = f"""你是NuScenes自动驾驶场景问答系统。

{scene_desc}

任务: 生成一个关于"{direction}"方向的问题。

方向信息:
- 方向: {direction}
- 当前覆盖率: 低 (该方向很少被问到)

要求:
1. 问题必须涉及{direction}方向
2. 可以询问该方向有什么对象、有多少对象等
3. 使用Source Frame
4. 问题自然流畅

请以JSON格式输出:
{{
  "question": "问题文本",
  "answer": "答案文本",
  "question_type": "exist/count",
  "difficulty": "L1",
  "target_objects": [],
  "reference_objects": [],
  "directions": ["{direction}"],
  "requires_temporal": false
}}

**重要**: 在<think>标签内完成思考后，必须在标签外输出JSON。
"""
        else:
            return None
        
        return prompt
    
    def _get_template_examples(self, level: str) -> str:
        """
        从模板库导出指定级别的模板文档
        
        Args:
            level: L0, L1, L2
        
        Returns:
            模板文档字符串（直接展示模板原文）
        """
        return TemplateManager.export_templates_for_llm(level)
    
    def _llm_generate_qa_pair(self, prompt: str, max_retries: int = 2) -> Optional[Dict]:
        """
        让LLM生成问答对（JSON格式）
        
        Args:
            prompt: 生成prompt
            max_retries: 最大重试次数
        """
        for attempt in range(max_retries + 1):
            try:
                response = self.llm_client.generate(prompt, temperature=0.7 if attempt == 0 else 0.5)
                
                # DEBUG: 打印原始响应
                if attempt == 0:
                    print(f"DEBUG 原始响应 (前300字符): {response[:300] if len(response) > 300 else response}")
                
                # 清理DeepSeek-R1的<think>标签 (使用简单字符串操作)
                # 循环移除所有<think>...</think>块
                while '<think>' in response.lower():
                    start_idx = response.lower().find('<think>')
                    end_idx = response.lower().find('</think>', start_idx)
                    if start_idx != -1 and end_idx != -1:
                        # 移除该块
                        response = response[:start_idx] + response[end_idx + 8:]
                    else:
                        # 如果只有<think>没有</think>，直接截断
                        response = response[:start_idx] if start_idx != -1 else response
                        break
                
                # 尝试解析JSON
                # 移除可能的markdown代码块标记
                response = response.strip()
                if response.startswith("```json"):
                    response = response[7:]
                if response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                response = response.strip()
                
                # 如果还是以{}之外的字符开头，尝试找到第一个{
                if not response.startswith('{'):
                    json_start = response.find('{')
                    if json_start != -1:
                        response = response[json_start:]
                
                qa_json = json.loads(response)
                return qa_json
                
            except json.JSONDecodeError as e:
                if attempt < max_retries:
                    continue  # 重试
                else:
                    print(f"警告: JSON解析失败 (已重试{max_retries}次): {e}")
                    print(f"清理后的响应 (前500字符): {response[:500] if len(response) > 500 else response}")
                    return None
            except Exception as e:
                print(f"警告: LLM生成失败: {e}")
                return None
        
        return None
    
    def _parse_qa_from_llm(self, parser: SceneGraphWithEdges,
                          camera_mapper: CameraMapper,
                          qa_json: Dict,
                          gap_type: str,
                          gap_item) -> Optional[QAPair]:
        """从LLM的JSON响应创建QAPair对象"""
        self._question_counter += 1
        
        # 提取信息
        question = qa_json.get("question", "")
        answer = qa_json.get("answer", "")
        question_type = qa_json.get("question_type", "exist")
        difficulty = qa_json.get("difficulty", "L0")
        target_objects = qa_json.get("target_objects", [])
        reference_objects = qa_json.get("reference_objects", [])
        directions = qa_json.get("directions", [])
        requires_temporal = qa_json.get("requires_temporal", False)
        
        # 重新判断难度 (覆盖LLM的判断)
        difficulty = self._determine_difficulty(question_type, target_objects, reference_objects, directions)
        
        # 计算相机
        cameras = set()
        for obj_id in target_objects + reference_objects:
            if obj_id in parser.nodes:
                cameras.update(camera_mapper.get_object_cameras(obj_id))
        
        # 推断answer_type
        answer_type = self._infer_answer_type(question_type, answer)
        
        qa_pair = QAPair(
            question_id=f"{parser.scene_name}_frame{parser.frame_idx}_cov_q{self._question_counter:04d}",
            scene_name=parser.scene_name,
            frame_idx=parser.frame_idx,
            sample_token=parser.sample_token,
            question_type=question_type,
            template_id=f"coverage_{gap_type}",
            difficulty=difficulty,
            target_objects=target_objects,
            reference_objects=reference_objects,
            directions_used=directions,
            question=question,
            answer=answer,
            answer_type=answer_type,
            requires_temporal=requires_temporal,
            cameras_for_analysis=list(cameras),
            metadata={
                "generation_method": "coverage_driven",
                "gap_type": gap_type,
                "gap_item": str(gap_item)
            }
        )
        
        return qa_pair
    
    def _determine_difficulty(self, question_type: str, target_objects: List, 
                             reference_objects: List, directions: List) -> str:
        """
        判断问题难度
        
        规则:
        - L0: 纯节点存在性 (exist且无具体对象)
        - L1: 单边查询 (status/空间关系/单对象查询)
        - L2: 多边/复杂推理 (comparison/多步骤)
        """
        # L2: 比较类问题
        if question_type == "comparison":
            return "L2"
        
        # L2: 同时有目标对象+参照对象+方向 (多边查询)
        if target_objects and reference_objects and directions:
            return "L2"
        
        # L1: 有具体对象或空间关系
        if target_objects or reference_objects or directions:
            return "L1"
        
        # L1: status/object类型 (属性边查询)
        if question_type in ["status", "object"]:
            return "L1"
        
        # L0: 纯存在性/计数 (无具体对象)
        return "L0"
    
    def _infer_answer_type(self, question_type: str, answer: str) -> str:
        """推断答案类型"""
        answer_lower = answer.lower().strip()
        
        if answer_lower in ["yes", "no", "是", "否"]:
            return "bool"
        elif answer_lower.isdigit():
            return "number"
        elif question_type == "status":
            return "status"
        elif question_type == "object":
            return "type"
        else:
            return "bool"  # 默认
    
    def _get_scene_description(self, parser: SceneGraphWithEdges) -> str:
        """获取场景描述"""
        obj_stats = defaultdict(list)
        for node_id, node in parser.nodes.items():
            if node_id == "ego":
                continue
            obj_type = node.get("type")
            obj_stats[obj_type].append(node_id)
        
        desc = f"场景: {parser.scene_name}, 帧: {parser.frame_idx}\n\n"
        desc += "场景中的对象:\n"
        for obj_type, ids in sorted(obj_stats.items()):
            desc += f"  - {obj_type}: {', '.join(ids[:5])}"
            if len(ids) > 5:
                desc += f" (共{len(ids)}个)"
            desc += "\n"
        
        return desc
    
    def _get_direction_from_edge(self, edge: Dict) -> Optional[str]:
        """从边获取方向（兼容多种格式）"""
        # 尝试多种字段
        if 'predicates' in edge and isinstance(edge['predicates'], list):
            return edge['predicates'][0] if edge['predicates'] else None
        if 'direction_8' in edge:
            return edge['direction_8']
        if 'direction_4' in edge:
            return edge['direction_4']
        
        metrics = edge.get('metrics', {})
        if isinstance(metrics, dict):
            ds = metrics.get('direction_source', {})
            if isinstance(ds, dict):
                return ds.get('direction_8', ds.get('direction_4'))
        
        return None
    
    def _update_coverage_stats(self, qa: QAPair):
        """更新覆盖率统计"""
        # 更新对象覆盖率
        for obj_id in qa.target_objects + qa.reference_objects:
            self.coverage_stats["object_coverage"][obj_id] += 1
        
        # 更新关系覆盖率
        if qa.reference_objects and qa.target_objects and qa.directions_used:
            for ref in qa.reference_objects:
                for direction in qa.directions_used:
                    for tgt in qa.target_objects:
                        rel_key = f"{ref}-{direction}->{tgt}"
                        self.coverage_stats["relation_coverage"][rel_key] += 1
        
        # 更新模式覆盖率
        self.coverage_stats["difficulty_coverage"][qa.difficulty] += 1
        self.coverage_stats["type_coverage"][qa.question_type] += 1
    
    def save_qa_pairs(self, qa_pairs: List[QAPair], output_path: str):
        """保存问答对"""
        output_data = [asdict(qa) for qa in qa_pairs]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n已保存 {len(qa_pairs)} 个问答对到: {output_path}")
    
    def save_coverage_stats(self, output_path: str):
        """保存覆盖率统计"""
        stats = {
            "object_coverage": dict(self.coverage_stats["object_coverage"]),
            "relation_coverage": dict(self.coverage_stats["relation_coverage"]),
            "difficulty_coverage": dict(self.coverage_stats["difficulty_coverage"]),
            "type_coverage": dict(self.coverage_stats["type_coverage"]),
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        print(f"已保存覆盖率统计到: {output_path}")


# 使用示例
if __name__ == "__main__":
    print("覆盖率驱动的问答生成器")
    print("=" * 60)
    print()
    print("使用方法:")
    print("""
from coverage_driven_generator import CoverageDrivenGenerator
from llm_client import OpenAIClient

# 1. 创建LLM客户端
llm_client = OpenAIClient(api_key="sk-...")

# 2. 创建覆盖率驱动生成器
generator = CoverageDrivenGenerator(llm_client=llm_client)

# 3. 加载场景图和覆盖率分析
with open("scene_graph.json", 'r') as f:
    scene_data = json.load(f)

with open("coverage_analysis.json", 'r') as f:
    coverage_analysis = json.load(f)

# 4. 基于覆盖率缺口生成问题
qa_pairs = generator.generate_from_coverage_gaps(
    scene_data,
    coverage_analysis,
    target_count=50,
    focus_areas=["low_object", "missing_relations", "rare_patterns"]
)

# 5. 保存结果
generator.save_qa_pairs(qa_pairs, "qa_coverage_driven.json")
generator.save_coverage_stats("coverage_stats.json")
""")
