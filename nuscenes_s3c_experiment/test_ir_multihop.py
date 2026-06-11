"""Run IR -> Cypher pipeline on several multi-hop NuScenes QA questions.

For each case:
- Import the corresponding scene_*_scene_graph.json into Neo4j (clears DB).
- Initialize VQAPipeline(use_ir=True).
- Run the given English questions (already normalized schema-wise by QuestionNormalizer).
- Log full structured results to output/coverage_analysis/vqa_results/.
"""
import os
import json
from datetime import datetime
from pathlib import Path

from vqa_pipeline import VQAPipeline
from import_single_scene_to_neo4j import Neo4jImporter


CASES = [
    {
        "scene_graph": "scene-0553_frame8_scene_graph.json",
        "description": "scene-0553_frame8 L2 object (barrier)",
        "questions": [
            "What is the thing that is both to the back right of the stopped trailer and the back of the stopped truck?",
            "There is a thing that is to the back right of the stopped trailer and the back of the stopped truck; what is it?",
        ],
    },
    {
        "scene_graph": "scene-0103_frame38_scene_graph.json",
        "description": "scene-0103_frame38 L2 object (truck)",
        "questions": [
            "There is a thing that is to the back right of the without rider motorcycle and the front left of me; what is it?",
            "There is a parked thing that is to the back right of the without rider motorcycle and the front left of me; what is it?",
        ],
    },
    {
        "scene_graph": "scene-0916_frame8_scene_graph.json",
        "description": "scene-0916_frame8 moving thing behind ego & bus",
        "questions": [
            "What is the moving thing that is to the back right of me and the back right of the bus?",
        ],
    },
]


def run_case(case, log_f):
    scene_file = case["scene_graph"]
    desc = case["description"]
    questions = case["questions"]

    print("\n" + "=" * 80)
    print(f"[Case] {desc}  ({scene_file})")
    print("=" * 80)

    # 1) 导入场景到 Neo4j（清空数据库）
    print("\n[Import] 清空数据库并导入场景图 -> Neo4j ...")
    importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
    importer.clear_database()
    importer.create_constraints()
    sg_path = Path("output/coverage_analysis/scene_graphs") / scene_file
    with sg_path.open("r", encoding="utf-8") as f:
        scene_graph = json.load(f)
    importer.import_scene(scene_graph)
    importer.close()

    # 2) 初始化 VQAPipeline（IR 模式）
    pipeline = VQAPipeline(use_ir=True)
    if not pipeline.initialize():
        print("初始化失败，跳过该场景。")
        return

    for idx, q in enumerate(questions, 1):
        print(f"\n----- 问题 {idx}/{len(questions)} -----")
        print(f"Q: {q}")
        log_f.write("\n" + "-" * 60 + "\n")
        log_f.write(f"[Case] {desc} ({scene_file})\n")
        log_f.write(f"Question {idx}/{len(questions)}: {q}\n")

        result = pipeline.process_question(q, verbose=True)

        log_f.write("\n[Structured Result]\n")
        log_f.write(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        log_f.write("\n")

    pipeline.close()


def main():
    print("=" * 80)
    print(" IR -> Cypher Multi-hop VQA Debug Run ")
    print("=" * 80)

    out_dir = os.path.join("output", "coverage_analysis", "vqa_results")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(out_dir, f"ir_multihop_debug_{ts}.txt")

    with open(log_path, "w", encoding="utf-8") as log_f:
        for case in CASES:
            run_case(case, log_f)

    print(f"\n✓ 多跳调试日志已保存到: {log_path}")


if __name__ == "__main__":
    main()
