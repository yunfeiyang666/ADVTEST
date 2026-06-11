"""
集成的覆盖率驱动QA生成Pipeline

完整流程:
1. 分析NuScenesQA原题集在场景图上的覆盖率
2. 识别覆盖率缺口（低覆盖对象、缺失关系、稀有模式）
3. LLM根据缺口生成针对性问题和答案
4. 迭代测试覆盖率提升
5. 生成完善的测试集
"""
import json
import sys
from pathlib import Path
from typing import Dict, List
from collections import defaultdict

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from qa_generator_v2.coverage_driven_generator import CoverageDrivenGenerator
from qa_generator_v2.llm_client import OpenAIClient, ClaudeClient, OllamaClient


class IntegratedQAPipeline:
    """
    集成的问答生成Pipeline
    
    组合覆盖率分析和LLM生成的完整流程
    """
    
    def __init__(self, llm_client, config: Dict = None):
        self.llm_client = llm_client
        self.config = config or {}
        self.generator = CoverageDrivenGenerator(llm_client, config)
    
    def run_full_pipeline(self, 
                         scene_graph_path: str,
                         nuscenes_qa_path: str,
                         output_dir: str,
                         iterations: int = 3,
                         questions_per_iter: int = 20):
        """
        运行完整的迭代式生成pipeline
        
        Args:
            scene_graph_path: 场景图文件路径
            nuscenes_qa_path: NuScenesQA原题集路径
            output_dir: 输出目录
            iterations: 迭代次数
            questions_per_iter: 每次迭代生成的问题数
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True, parents=True)
        
        print("=" * 80)
        print("集成的覆盖率驱动QA生成Pipeline")
        print("=" * 80)
        print(f"\n配置:")
        print(f"  - 场景图: {scene_graph_path}")
        print(f"  - NuScenesQA: {nuscenes_qa_path}")
        print(f"  - 输出目录: {output_dir}")
        print(f"  - 迭代次数: {iterations}")
        print(f"  - 每次生成: {questions_per_iter} 个问题")
        
        # 1. 加载场景图
        print(f"\n{'='*80}")
        print("步骤1: 加载场景图")
        print("=" * 80)
        
        with open(scene_graph_path, 'r', encoding='utf-8') as f:
            scene_data = json.load(f)
        
        scene_name = scene_data.get("scene_name", "unknown")
        frame_idx = scene_data.get("frame_idx", 0)
        print(f"  场景: {scene_name}, 帧: {frame_idx}")
        
        # 2. 初始覆盖率分析
        print(f"\n{'='*80}")
        print("步骤2: 分析NuScenesQA的覆盖率")
        print("=" * 80)
        
        initial_coverage = self.analyze_nuscenes_qa_coverage(
            scene_data, 
            nuscenes_qa_path
        )
        
        self.save_coverage_analysis(initial_coverage, output_dir / "coverage_iter0.json")
        self.print_coverage_summary(initial_coverage, "初始")
        
        # 3. 迭代生成
        all_generated_qa = []
        
        for iter_num in range(1, iterations + 1):
            print(f"\n{'='*80}")
            print(f"步骤3.{iter_num}: 迭代 {iter_num}/{iterations} - 生成问题")
            print("=" * 80)
            
            # 生成问题
            qa_pairs = self.generator.generate_from_coverage_gaps(
                scene_data,
                initial_coverage,  # 使用累积的覆盖率
                target_count=questions_per_iter,
                focus_areas=["low_object", "missing_relations", "rare_patterns"]
            )
            
            all_generated_qa.extend(qa_pairs)
            
            # 更新覆盖率
            self.update_coverage_with_generated(initial_coverage, qa_pairs)
            
            # 保存本次迭代结果
            iter_output_path = output_dir / f"qa_iter{iter_num}.json"
            self.generator.save_qa_pairs(qa_pairs, str(iter_output_path))
            
            coverage_output_path = output_dir / f"coverage_iter{iter_num}.json"
            self.save_coverage_analysis(initial_coverage, coverage_output_path)
            
            self.print_coverage_summary(initial_coverage, f"迭代{iter_num}后")
        
        # 4. 保存最终结果
        print(f"\n{'='*80}")
        print("步骤4: 保存最终结果")
        print("=" * 80)
        
        final_output_path = output_dir / "qa_final_all.json"
        self.generator.save_qa_pairs(all_generated_qa, str(final_output_path))
        
        final_coverage_path = output_dir / "coverage_final.json"
        self.save_coverage_analysis(initial_coverage, final_coverage_path)
        
        # 保存生成器的覆盖率统计
        stats_output_path = output_dir / "generation_stats.json"
        self.generator.save_coverage_stats(str(stats_output_path))
        
        # 5. 生成报告
        print(f"\n{'='*80}")
        print("步骤5: 生成报告")
        print("=" * 80)
        
        report = self.generate_report(initial_coverage, all_generated_qa)
        report_path = output_dir / "pipeline_report.txt"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n报告已保存到: {report_path}")
        print("\n" + "=" * 80)
        print("Pipeline完成!")
        print("=" * 80)
        print(f"\n总共生成: {len(all_generated_qa)} 个问答对")
        print(f"输出目录: {output_dir}")
    
    def analyze_nuscenes_qa_coverage(self, scene_data: Dict, 
                                    nuscenes_qa_path: str) -> Dict:
        """
        分析NuScenesQA在该场景图上的覆盖率
        
        注意: 这里简化处理，实际应该加载NuScenesQA的问题并匹配到该场景
        """
        # 简化版本: 初始化为零覆盖率
        # 实际使用时，需要从NuScenesQA中找到匹配该scene的问题并分析
        
        coverage = {
            "scene_name": scene_data.get("scene_name"),
            "frame_idx": scene_data.get("frame_idx"),
            "object_coverage": {},
            "relation_coverage": {},
            "pattern_coverage": {},
            "type_coverage": {},
            "direction_coverage": {},
        }
        
        # 初始化所有对象为0覆盖率
        nodes = scene_data.get("nodes", [])
        for node in nodes:
            obj_id = node.get("id")
            if obj_id and obj_id != "ego":
                coverage["object_coverage"][obj_id] = 0
        
        # 初始化所有关系为0覆盖率
        edges = scene_data.get("edges", [])
        for edge in edges:
            src = edge.get("source")
            tgt = edge.get("target")
            direction = self._extract_direction(edge)
            if direction:
                rel_key = f"{src}-{direction}->{tgt}"
                coverage["relation_coverage"][rel_key] = 0
        
        # 初始化方向覆盖率
        from qa_generator_v2.config import DIRECTIONS_8
        for direction in DIRECTIONS_8:
            coverage["direction_coverage"][direction] = 0
        
        return coverage
    
    def _extract_direction(self, edge: Dict) -> str:
        """从边提取方向"""
        metrics = edge.get("metrics", {})
        direction_source = metrics.get("direction_source", {})
        if isinstance(direction_source, dict):
            return direction_source.get("direction_8", "")
        return ""
    
    def update_coverage_with_generated(self, coverage: Dict, qa_pairs: List):
        """用新生成的问题更新覆盖率统计"""
        for qa in qa_pairs:
            # 更新对象覆盖率
            for obj_id in qa.target_objects + qa.reference_objects:
                if obj_id in coverage["object_coverage"]:
                    coverage["object_coverage"][obj_id] += 1
            
            # 更新关系覆盖率
            if qa.reference_objects and qa.target_objects and qa.directions_used:
                for ref in qa.reference_objects:
                    for direction in qa.directions_used:
                        for tgt in qa.target_objects:
                            rel_key = f"{ref}-{direction}->{tgt}"
                            if rel_key in coverage["relation_coverage"]:
                                coverage["relation_coverage"][rel_key] += 1
            
            # 更新方向覆盖率
            for direction in qa.directions_used:
                if direction in coverage["direction_coverage"]:
                    coverage["direction_coverage"][direction] += 1
    
    def save_coverage_analysis(self, coverage: Dict, output_path: Path):
        """保存覆盖率分析结果"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(coverage, f, indent=2, ensure_ascii=False)
    
    def print_coverage_summary(self, coverage: Dict, stage: str):
        """打印覆盖率摘要"""
        obj_cov = coverage.get("object_coverage", {})
        rel_cov = coverage.get("relation_coverage", {})
        dir_cov = coverage.get("direction_coverage", {})
        
        total_objects = len(obj_cov)
        covered_objects = sum(1 for v in obj_cov.values() if v > 0)
        
        total_relations = len(rel_cov)
        covered_relations = sum(1 for v in rel_cov.values() if v > 0)
        
        total_directions = len(dir_cov)
        covered_directions = sum(1 for v in dir_cov.values() if v > 0)
        
        print(f"\n{stage}覆盖率:")
        print(f"  - 对象覆盖: {covered_objects}/{total_objects} ({covered_objects/total_objects*100:.1f}%)")
        print(f"  - 关系覆盖: {covered_relations}/{total_relations} ({covered_relations/total_relations*100 if total_relations > 0 else 0:.1f}%)")
        print(f"  - 方向覆盖: {covered_directions}/{total_directions} ({covered_directions/total_directions*100:.1f}%)")
    
    def generate_report(self, final_coverage: Dict, generated_qa: List) -> str:
        """生成Pipeline报告"""
        report = []
        report.append("=" * 80)
        report.append("覆盖率驱动QA生成Pipeline - 完成报告")
        report.append("=" * 80)
        report.append("")
        
        # 基本信息
        report.append("## 基本信息")
        report.append(f"场景: {final_coverage.get('scene_name')}")
        report.append(f"帧: {final_coverage.get('frame_idx')}")
        report.append(f"生成问题总数: {len(generated_qa)}")
        report.append("")
        
        # 覆盖率统计
        obj_cov = final_coverage.get("object_coverage", {})
        rel_cov = final_coverage.get("relation_coverage", {})
        dir_cov = final_coverage.get("direction_coverage", {})
        
        report.append("## 最终覆盖率")
        report.append(f"对象覆盖率: {sum(1 for v in obj_cov.values() if v > 0)}/{len(obj_cov)}")
        report.append(f"关系覆盖率: {sum(1 for v in rel_cov.values() if v > 0)}/{len(rel_cov)}")
        report.append(f"方向覆盖率: {sum(1 for v in dir_cov.values() if v > 0)}/{len(dir_cov)}")
        report.append("")
        
        # 按难度统计
        difficulty_count = defaultdict(int)
        type_count = defaultdict(int)
        
        for qa in generated_qa:
            difficulty_count[qa.difficulty] += 1
            type_count[qa.question_type] += 1
        
        report.append("## 生成的问题分布")
        report.append("按难度:")
        for diff, count in sorted(difficulty_count.items()):
            report.append(f"  {diff}: {count}")
        
        report.append("\n按类型:")
        for qtype, count in sorted(type_count.items()):
            report.append(f"  {qtype}: {count}")
        
        report.append("")
        
        # Top覆盖对象
        report.append("## 高覆盖对象 (Top 10)")
        sorted_objs = sorted(obj_cov.items(), key=lambda x: x[1], reverse=True)[:10]
        for obj_id, count in sorted_objs:
            report.append(f"  {obj_id}: {count} 次")
        
        report.append("")
        
        # 低覆盖对象
        report.append("## 低覆盖对象 (覆盖<2次)")
        low_cov_objs = [(k, v) for k, v in obj_cov.items() if v < 2]
        low_cov_objs.sort(key=lambda x: x[1])
        for obj_id, count in low_cov_objs[:20]:
            report.append(f"  {obj_id}: {count} 次")
        
        if len(low_cov_objs) > 20:
            report.append(f"  ... 还有 {len(low_cov_objs) - 20} 个低覆盖对象")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="覆盖率驱动的QA生成Pipeline")
    parser.add_argument("--scene-graph", required=True, help="场景图JSON文件路径")
    parser.add_argument("--nuscenes-qa", required=True, help="NuScenesQA数据文件路径")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--llm-type", default="openai", choices=["openai", "claude", "ollama"], 
                       help="LLM类型")
    parser.add_argument("--api-key", help="API密钥")
    parser.add_argument("--iterations", type=int, default=3, help="迭代次数")
    parser.add_argument("--questions-per-iter", type=int, default=20, help="每次迭代生成的问题数")
    
    args = parser.parse_args()
    
    # 创建LLM客户端
    if args.llm_type == "openai":
        llm_client = OpenAIClient(api_key=args.api_key)
    elif args.llm_type == "claude":
        llm_client = ClaudeClient(api_key=args.api_key)
    elif args.llm_type == "ollama":
        llm_client = OllamaClient()
    
    # 运行pipeline
    pipeline = IntegratedQAPipeline(llm_client)
    pipeline.run_full_pipeline(
        scene_graph_path=args.scene_graph,
        nuscenes_qa_path=args.nuscenes_qa,
        output_dir=args.output_dir,
        iterations=args.iterations,
        questions_per_iter=args.questions_per_iter
    )


if __name__ == "__main__":
    main()
