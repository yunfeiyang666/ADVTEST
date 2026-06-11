"""
LLM-based QA Generator
让大模型根据NuScenesQA的问题类型和模板，生成自然的问题，然后自己回答
"""
import json
import random
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import asdict

try:
    from .templates import TemplateManager, QATemplate
    from .generator import SceneGraphWithEdges, QAPair
    from .camera_mapper import CameraMapper
    from .config import TYPE_NAMES, STATUS_DISPLAY_NAMES, DIRECTIONS_8
except ImportError:
    from templates import TemplateManager, QATemplate
    from generator import SceneGraphWithEdges, QAPair
    from camera_mapper import CameraMapper
    from config import TYPE_NAMES, STATUS_DISPLAY_NAMES, DIRECTIONS_8


class LLMQAGenerator:
    """
    基于LLM的问答生成器
    
    流程:
    1. 根据场景图和模板类型，让LLM生成问题
    2. 让LLM根据场景图回答问题
    3. 验证答案的正确性（可选）
    """
    
    def __init__(self, llm_client=None, config: Dict = None):
        """
        Args:
            llm_client: LLM客户端（OpenAI, Claude等）
            config: 配置参数
        """
        self.llm_client = llm_client
        self.config = config or {}
        self.template_manager = TemplateManager()
        self._question_counter = 0
    
    def generate(self, scene_data: Dict, 
                 difficulties: List[str] = None,
                 num_questions_per_template: int = 2) -> List[QAPair]:
        """
        生成LLM驱动的问答对
        
        Args:
            scene_data: 场景图JSON数据
            difficulties: 难度级别 (["L0", "L1", "L2"])
            num_questions_per_template: 每个模板生成几个问题
        
        Returns:
            QAPair列表
        """
        difficulties = difficulties or ["L0", "L1", "L2"]
        
        # 解析场景图
        parser = SceneGraphWithEdges(scene_data)
        camera_mapper = CameraMapper()
        
        # 获取所有需要的模板
        templates = []
        for diff in difficulties:
            templates.extend(self.template_manager.get_templates(difficulty=diff))
        
        print(f"将为 {len(templates)} 个模板生成问题...")
        
        qa_pairs = []
        for template in templates:
            print(f"  处理模板: {template.template_id} ({template.difficulty}, {template.question_type})")
            
            # 为每个模板生成多个问题
            for i in range(num_questions_per_template):
                qa = self._generate_single_qa(parser, camera_mapper, template, i)
                if qa:
                    qa_pairs.append(qa)
        
        print(f"\n总共生成 {len(qa_pairs)} 个问答对")
        return qa_pairs
    
    def _generate_single_qa(self, parser: SceneGraphWithEdges,
                           camera_mapper: CameraMapper,
                           template: QATemplate,
                           variant_idx: int) -> Optional[QAPair]:
        """
        为单个模板生成一个问答对
        
        Args:
            parser: 场景图解析器
            camera_mapper: 相机映射器
            template: 问题模板
            variant_idx: 变体索引（用于生成不同的问题）
        """
        # 1. 准备场景上下文
        scene_context = self._prepare_scene_context(parser)
        
        # 2. 根据模板类型采样相关对象
        sampled_objects = self._sample_objects_for_template(parser, template, variant_idx)
        if not sampled_objects:
            return None
        
        # 3. 让LLM生成问题
        question = self._llm_generate_question(template, scene_context, sampled_objects)
        if not question:
            return None
        
        # 4. 让LLM回答问题
        answer = self._llm_answer_question(question, scene_context, sampled_objects)
        if not answer:
            return None
        
        # 5. 创建QAPair对象
        self._question_counter += 1
        
        # 提取相关对象和相机
        target_objects = sampled_objects.get("target_objects", [])
        reference_objects = sampled_objects.get("reference_objects", [])
        directions = sampled_objects.get("directions", [])
        
        cameras = set()
        for obj_id in target_objects + reference_objects:
            cameras.update(camera_mapper.get_object_cameras(obj_id))
        
        qa_pair = QAPair(
            question_id=f"{parser.scene_name}_frame{parser.frame_idx}_llm_q{self._question_counter:04d}",
            scene_name=parser.scene_name,
            frame_idx=parser.frame_idx,
            sample_token=parser.sample_token,
            question_type=template.question_type,
            template_id=template.template_id,
            difficulty=template.difficulty,
            target_objects=target_objects,
            reference_objects=reference_objects,
            directions_used=directions,
            question=question,
            answer=answer,
            answer_type=template.answer_type,
            requires_temporal=template.requires_temporal,
            cameras_for_analysis=list(cameras),
            metadata={
                "generation_method": "llm",
                "template_used": template.template,
                **sampled_objects.get("metadata", {})
            }
        )
        
        return qa_pair
    
    def _prepare_scene_context(self, parser: SceneGraphWithEdges) -> str:
        """准备场景上下文（给LLM看的场景描述）"""
        # 统计场景中的对象
        obj_stats = {}
        for node_id, node in parser.nodes.items():
            if node_id == "ego":
                continue
            obj_type = node["type"]
            status = node.get("status", "unknown")
            
            key = f"{status} {obj_type}" if status != "unknown" else obj_type
            if key not in obj_stats:
                obj_stats[key] = []
            obj_stats[key].append(node_id)
        
        # 构建场景描述
        scene_desc = f"场景: {parser.scene_name}, 帧: {parser.frame_idx}\n\n"
        scene_desc += "场景中的对象:\n"
        for key, ids in sorted(obj_stats.items()):
            scene_desc += f"  - {key}: {', '.join(ids[:5])}"
            if len(ids) > 5:
                scene_desc += f" (共{len(ids)}个)"
            scene_desc += "\n"
        
        return scene_desc
    
    def _sample_objects_for_template(self, parser: SceneGraphWithEdges,
                                    template: QATemplate,
                                    variant_idx: int) -> Optional[Dict]:
        """
        根据模板类型采样相关对象
        
        Returns:
            包含target_objects, reference_objects, directions, metadata的字典
        """
        result = {
            "target_objects": [],
            "reference_objects": [],
            "directions": [],
            "metadata": {}
        }
        
        # 根据难度级别采样
        if template.difficulty == "L0":
            return self._sample_for_L0(parser, template, variant_idx, result)
        elif template.difficulty == "L1":
            return self._sample_for_L1(parser, template, variant_idx, result)
        elif template.difficulty == "L2":
            return self._sample_for_L2(parser, template, variant_idx, result)
        
        return None
    
    def _sample_for_L0(self, parser: SceneGraphWithEdges, template: QATemplate,
                       variant_idx: int, result: Dict) -> Optional[Dict]:
        """为L0模板采样对象"""
        if template.question_type == "exist":
            # 随机选择一个对象类型
            obj_type = random.choice(list(parser.object_types_present))
            result["metadata"]["obj_type"] = obj_type
            result["target_objects"] = [uid for uid, node in parser.nodes.items()
                                       if node.get("type") == obj_type and uid != "ego"][:5]
            
        elif template.question_type == "count":
            # 随机选择一个对象类型
            obj_type = random.choice(list(parser.object_types_present))
            result["metadata"]["obj_type"] = obj_type
            result["target_objects"] = [uid for uid, node in parser.nodes.items()
                                       if node.get("type") == obj_type and uid != "ego"]
            
        elif template.question_type == "status":
            # 随机选择一个有状态的对象
            candidates = [uid for uid, node in parser.nodes.items()
                         if uid != "ego" and node.get("status") and node.get("status") != "unknown"]
            if not candidates:
                return None
            obj_id = random.choice(candidates)
            result["target_objects"] = [obj_id]
            result["metadata"]["obj_type"] = parser.nodes[obj_id]["type"]
            
        elif template.question_type == "object":
            # 随机选择一个有状态的对象
            candidates = [uid for uid, node in parser.nodes.items()
                         if uid != "ego" and node.get("status") and node.get("status") != "unknown"]
            if not candidates:
                return None
            obj_id = random.choice(candidates)
            result["target_objects"] = [obj_id]
            result["metadata"]["status"] = parser.nodes[obj_id]["status"]
            
        elif template.question_type == "comparison":
            # 随机选择两个有状态的对象
            candidates = [uid for uid, node in parser.nodes.items()
                         if uid != "ego" and node.get("status") and node.get("status") != "unknown"]
            if len(candidates) < 2:
                return None
            objs = random.sample(candidates, 2)
            result["target_objects"] = objs
        
        return result if result["target_objects"] else None
    
    def _sample_for_L1(self, parser: SceneGraphWithEdges, template: QATemplate,
                       variant_idx: int, result: Dict) -> Optional[Dict]:
        """为L1模板采样对象（涉及方向）"""
        # 随机选择一个参考对象
        ref_candidates = [uid for uid in parser.nodes if uid != "ego"]
        if not ref_candidates:
            return None
        ref_id = random.choice(ref_candidates)
        result["reference_objects"] = [ref_id]
        
        # 随机选择一个方向
        direction = random.choice(DIRECTIONS_8)
        result["directions"] = [direction]
        
        # 查找该方向的对象
        targets = parser.get_objects_in_direction(ref_id, direction)
        if not targets:
            return None
        
        result["target_objects"] = targets[:5]
        result["metadata"]["direction"] = direction
        result["metadata"]["ref_type"] = parser.nodes[ref_id]["type"]
        
        return result
    
    def _sample_for_L2(self, parser: SceneGraphWithEdges, template: QATemplate,
                       variant_idx: int, result: Dict) -> Optional[Dict]:
        """为L2模板采样对象（链式或复合查询）"""
        # L2比较复杂，这里简化处理
        # 可以根据具体模板ID做更精细的采样
        
        if "same_status" in template.template_id:
            # 同状态查询
            candidates = [uid for uid, node in parser.nodes.items()
                         if uid != "ego" and node.get("status") and node.get("status") != "unknown"]
            if not candidates:
                return None
            ref_id = random.choice(candidates)
            result["reference_objects"] = [ref_id]
            
            # 找同状态的其他对象
            ref_status = parser.nodes[ref_id]["status"]
            same_status = [uid for uid, node in parser.nodes.items()
                          if uid != "ego" and uid != ref_id and node.get("status") == ref_status]
            result["target_objects"] = same_status[:10]
            
        elif "chain" in template.template_id:
            # 链式查询
            # 简化处理：随机选两个有关系的对象
            if not parser.edges:
                return None
            edge = random.choice(parser.edges)
            result["reference_objects"] = [edge["source"]]
            result["target_objects"] = [edge["target"]]
            
        return result if result["target_objects"] or result["reference_objects"] else None
    
    def _llm_generate_question(self, template: QATemplate,
                               scene_context: str,
                               sampled_objects: Dict) -> Optional[str]:
        """
        让LLM生成问题
        
        这里需要调用实际的LLM API (OpenAI, Claude等)
        """
        if not self.llm_client:
            # 如果没有LLM客户端，回退到模板生成
            return self._fallback_template_question(template, sampled_objects)
        
        # 构建prompt
        prompt = self._build_question_prompt(template, scene_context, sampled_objects)
        
        # 调用LLM
        try:
            response = self.llm_client.generate(prompt)
            question = self._extract_question_from_response(response)
            return question
        except Exception as e:
            print(f"LLM生成问题失败: {e}")
            return None
    
    def _llm_answer_question(self, question: str,
                            scene_context: str,
                            sampled_objects: Dict) -> Optional[str]:
        """
        让LLM回答问题
        """
        if not self.llm_client:
            # 如果没有LLM客户端，回退到规则生成
            return self._fallback_answer(question, sampled_objects)
        
        # 构建prompt
        prompt = self._build_answer_prompt(question, scene_context, sampled_objects)
        
        # 调用LLM
        try:
            response = self.llm_client.generate(prompt)
            answer = self._extract_answer_from_response(response)
            return answer
        except Exception as e:
            print(f"LLM回答问题失败: {e}")
            return None
    
    def _build_question_prompt(self, template: QATemplate,
                              scene_context: str,
                              sampled_objects: Dict) -> str:
        """构建问题生成prompt"""
        prompt = f"""你是一个自动驾驶场景问答系统。

{scene_context}

现在需要你根据以下模板类型生成一个自然的问题：
- 模板类型: {template.question_type}
- 难度: {template.difficulty}
- 模板示例: {template.template}
- 描述: {template.description}

涉及的对象:
- 目标对象: {', '.join(sampled_objects.get('target_objects', [])[:5])}
- 参考对象: {', '.join(sampled_objects.get('reference_objects', []))}
- 方向: {', '.join(sampled_objects.get('directions', []))}

要求:
1. 问题要自然、流畅，符合NuScenesQA的风格
2. 问题中要使用精确的对象ID（如car1, pedestrian2）
3. 方向使用Source Frame（以参考对象的朝向为准）
4. 问题应该可以根据场景图回答

只输出问题本身，不要有其他解释。
"""
        return prompt
    
    def _build_answer_prompt(self, question: str,
                            scene_context: str,
                            sampled_objects: Dict) -> str:
        """构建回答生成prompt"""
        prompt = f"""你是一个自动驾驶场景问答系统。

{scene_context}

问题: {question}

涉及的对象信息:
{json.dumps(sampled_objects, indent=2, ensure_ascii=False)}

请根据场景信息回答这个问题。

要求:
1. 答案要简洁、准确
2. 对于yes/no问题，只回答"yes"或"no"
3. 对于计数问题，只回答数字
4. 对于类型/状态问题，只回答对应的类型/状态名称

只输出答案本身，不要有其他解释。
"""
        return prompt
    
    def _extract_question_from_response(self, response: str) -> str:
        """从LLM响应中提取问题"""
        # 简单清理
        question = response.strip()
        # 移除可能的引号
        if question.startswith('"') and question.endswith('"'):
            question = question[1:-1]
        return question
    
    def _extract_answer_from_response(self, response: str) -> str:
        """从LLM响应中提取答案"""
        answer = response.strip()
        # 移除可能的引号
        if answer.startswith('"') and answer.endswith('"'):
            answer = answer[1:-1]
        return answer
    
    def _fallback_template_question(self, template: QATemplate,
                                   sampled_objects: Dict) -> str:
        """回退到模板生成（当没有LLM时）"""
        # 这里使用原有的模板填充逻辑
        # 简化示例
        return f"[Template] {template.template}"
    
    def _fallback_answer(self, question: str, sampled_objects: Dict) -> str:
        """回退到规则生成（当没有LLM时）"""
        # 简化示例
        return "[Answer based on rules]"
    
    def save_qa_pairs(self, qa_pairs: List[QAPair], output_path: str):
        """保存问答对到JSON文件"""
        output_data = [asdict(qa) for qa in qa_pairs]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"已保存 {len(qa_pairs)} 个问答对到: {output_path}")


# 示例：如何使用
if __name__ == "__main__":
    # TODO: 需要实现LLM客户端
    # 可以使用OpenAI API, Claude API, 或本地模型
    
    print("LLM QA Generator")
    print("=" * 60)
    print("这个生成器需要配置LLM客户端才能工作")
    print("支持的LLM:")
    print("  - OpenAI GPT-4")
    print("  - Anthropic Claude")
    print("  - 本地大模型 (通过API)")
    print()
    print("请先实现LLM客户端，然后:")
    print("  generator = LLMQAGenerator(llm_client=your_llm_client)")
    print("  qa_pairs = generator.generate(scene_data)")
