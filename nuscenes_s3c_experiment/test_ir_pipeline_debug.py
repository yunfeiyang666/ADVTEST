"""Run a few NuScenes official QA questions through the new IR -> Cypher pipeline.

This script:
- uses VQAPipeline(use_ir=True)
- runs several hand-picked English questions (taken from official QA JSON)
- prints all intermediate steps (normalization, IR JSON, Cypher, Neo4j result, answers)
- writes a detailed text log to output/coverage_analysis/vqa_results/
"""
import os
import json
from datetime import datetime

from vqa_pipeline import VQAPipeline
from import_single_scene_to_neo4j import Neo4jImporter


# 这里专注于 scene-0916_frame8 的第三类多参照问题
# 问题取自 scene-0916_frame8_official_qa.json
TEST_QUESTIONS = [
    "What is the moving thing that is to the back right of me and the back right of the bus?",
]


def main():
    print("=" * 70)
    print("  IR -> Cypher VQA Pipeline Debug Run (scene-0916_frame8)")
    print("=" * 70)

    # 先导入 scene-0916_frame8 场景图到 Neo4j（会清空当前数据库）
    print("\n[Import] 导入 scene-0916_frame8_scene_graph.json 到 Neo4j（会清空数据库）...")
    importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
    importer.clear_database()
    importer.create_constraints()
    import json, pathlib
    sg_path = pathlib.Path("output/coverage_analysis/scene_graphs/scene-0916_frame8_scene_graph.json")
    with open(sg_path, "r", encoding="utf-8") as f:
        scene_graph = json.load(f)
    importer.import_scene(scene_graph)
    importer.close()

    # 然后初始化 VQAPipeline，仅负责查询和LLM推理
    pipeline = VQAPipeline(use_ir=True)
    if not pipeline.initialize():
        print("初始化失败，退出。")
        return

    # 准备日志文件
    out_dir = os.path.join("output", "coverage_analysis", "vqa_results")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(out_dir, f"ir_pipeline_debug_{ts}.txt")

    with open(log_path, "w", encoding="utf-8") as log_f:
        for idx, q in enumerate(TEST_QUESTIONS, 1):
            print(f"\n===== 问题 {idx}/{len(TEST_QUESTIONS)} =====")
            log_f.write(f"\n===== 问题 {idx}/{len(TEST_QUESTIONS)} =====\n")
            log_f.write(f"原始问题: {q}\n")

            result = pipeline.process_question(q, verbose=True)

            # 记录结构化结果
            log_f.write("\n[Structured Result]\n")
            log_f.write(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            log_f.write("\n")

    pipeline.close()
    print(f"\n✓ 调试日志已保存到: {log_path}")


if __name__ == "__main__":
    main()
