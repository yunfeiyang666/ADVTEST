"""
NuScenes 官方 QA + IR Pipeline 测试脚本

- 使用 VQAPipeline(use_ir=True)
- 针对 manifest.json 中列出的场景逐帧跑官方 QA
- 支持预实验模式（只跑 1 帧、每帧少量题），以及正式模式（全量）
- 运行时同时在命令行打印详细进度，并写入日志文件

用法示例：
  # 预实验：只对第一帧跑 1 题
  python test_official_qa_ir.py --mode pre --max-questions 1

  # 正式实验：对 manifest 中所有帧，跑该帧的全部官方题
  python test_official_qa_ir.py --mode full
"""
import os
import sys
import json
import argparse
from datetime import datetime
from collections import defaultdict
from typing import Optional

import config
from import_single_scene_to_neo4j import Neo4jImporter
from vqa_pipeline import VQAPipeline


class Logger:
    """简单 tee logger：同时写终端和文件"""

    def __init__(self, filepath: str):
        self.terminal = sys.stdout
        self.log = open(filepath, "w", encoding="utf-8")

    def write(self, message: str):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()


def load_official_qa(qa_file_path: str):
    """加载官方 QA 数据，并按 sample_token 分组"""
    print(f"加载官方 QA 数据: {qa_file_path}")
    with open(qa_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions_list = data["questions"]
    print(f"  总问题数: {len(questions_list)}")

    qa_by_sample = defaultdict(list)
    for qa in questions_list:
        sample_token = qa["sample_token"]
        qa_by_sample[sample_token].append(qa)

    print(f"  覆盖 sample_token 数: {len(qa_by_sample)}")
    return qa_by_sample


def get_sample_token_for_scene(nusc, scene_name: str, frame_idx: int) -> Optional[str]:
    """用 NuScenes devkit 根据 scene_name + frame_idx 找到 sample_token"""
    for scene in nusc.scene:
        if scene["name"] == scene_name:
            sample_token = scene["first_sample_token"]
            current_frame = 0

            while sample_token and current_frame < frame_idx:
                sample = nusc.get("sample", sample_token)
                sample_token = sample["next"]
                current_frame += 1

            return sample_token
    return None


def load_scene_graph(filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def import_to_neo4j(scene_graph, scene_name: str, frame_idx: int) -> bool:
    """导入场景图到 Neo4j（会清空现有数据）"""
    print("\n" + "=" * 70)
    print(f"  导入场景到 Neo4j: {scene_name} 帧{frame_idx}")
    print("=" * 70)

    importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")

    try:
        print("清空数据库 ...")
        importer.clear_database()
        print("创建约束 ...")
        importer.create_constraints()
        print("导入场景图 ...")
        importer.import_scene(scene_graph)

        with importer.driver.session() as session:
            node_count = session.run(
                "MATCH (n:Object) RETURN count(n) AS count"
            ).single()["count"]
            edge_count = session.run(
                "MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS count"
            ).single()["count"]
        print(f"✓ 导入完成: {node_count} 个对象, {edge_count} 条关系")
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False
    finally:
        importer.close()


def test_official_questions_ir(
    official_qa_list,
    scene_name: str,
    frame_idx: int,
    max_questions: Optional[int] = None,
):
    """用 IR pipeline 测试指定场景的一组官方 QA 题目"""
    print("\n" + "#" * 70)
    print(f"#  官方 QA + IR 测试: {scene_name} 帧{frame_idx}")
    print("#" * 70)

    pipeline = VQAPipeline(use_ir=True)
    if not pipeline.initialize():
        print("❌ VQAPipeline 初始化失败")
        return None

    # 截断为预跑子集
    test_questions = official_qa_list
    if max_questions is not None:
        test_questions = test_questions[:max_questions]

    print(f"\n该场景官方问题数: {len(official_qa_list)}")
    print(f"本次测试问题数: {len(test_questions)}")

    type_count = defaultdict(int)
    for qa in test_questions:
        type_count[qa["template_type"]] += 1

    print("\n问题类型分布（本次测试子集）：")
    for qtype, count in sorted(type_count.items(), key=lambda x: -x[1]):
        print(f"  {qtype}: {count}")

    results = []
    total = len(test_questions)
    for i, qa in enumerate(test_questions, 1):
        question = qa["question"]
        expected_answer = qa["answer"]
        question_type = qa["template_type"]

        print("\n" + "=" * 70)
        print(f"[{i}/{total}] [{question_type}]")
        print(f"问题: {question}")
        print(f"官方答案: {expected_answer}")
        print("=" * 70)

        # 直接用英文原题（不翻译），让 QuestionNormalizer 自己处理
        result = pipeline.process_question(question, verbose=True)

        # 简单答案匹配（可后续细化）
        answer_match = False
        if result.success and result.answer:
            answer_lower = str(result.answer).strip().lower()
            expected_lower = str(expected_answer).strip().lower()
            answer_match = (
                expected_lower in answer_lower or answer_lower in expected_lower
            )

        results.append(
            {
                "question": question,
                "expected_answer": expected_answer,
                "predicted_answer": result.answer,
                "question_type": question_type,
                "success": result.success,
                "answer_match": answer_match,
                "cypher": result.cypher_query,
                "error": result.error,
                "normalized_question": result.normalized_question,
                "ir_query_plan": result.query_plan_json,
            }
        )

        if result.success:
            if answer_match:
                print("\n✅ 成功且答案匹配")
            else:
                print("\n⚠️ 成功但答案不匹配")
                print(f"  预期: {expected_answer}")
                print(f"  实际: {result.answer}")
        else:
            print(f"\n❌ 失败: {result.error}")

    pipeline.close()

    # 汇总统计
    total = len(results)
    success_count = sum(1 for r in results if r["success"])
    match_count = sum(1 for r in results if r["answer_match"])

    print("\n" + "=" * 70)
    print(f"  测试总结: {scene_name} 帧{frame_idx}")
    print("=" * 70)
    print(f"  总问题数: {total}")
    print(f"  执行成功: {success_count} ({success_count/total*100:.1f}%)")
    print(f"  答案匹配: {match_count} ({match_count/total*100:.1f}%)")

    by_type = defaultdict(lambda: {"total": 0, "success": 0, "match": 0})
    for r in results:
        qt = r["question_type"]
        by_type[qt]["total"] += 1
        if r["success"]:
            by_type[qt]["success"] += 1
        if r["answer_match"]:
            by_type[qt]["match"] += 1

    print("\n按类型统计:")
    for qt, stats in sorted(by_type.items()):
        t = stats["total"] or 1
        print(f"  {qt}:")
        print(f"    成功率: {stats['success']}/{stats['total']} ({stats['success']/t*100:.1f}%)")
        print(f"    准确率: {stats['match']}/{stats['total']} ({stats['match']/t*100:.1f}%)")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Run NuScenes official QA with IR pipeline on selected scenes."
    )
    parser.add_argument(
        "--mode",
        choices=["pre", "full"],
        default="full",
        help="pre: 预实验（少量题），full: 正式实验（全部题）",
    )
    parser.add_argument(
        "--max-questions",
        type=int,
        default=None,
        help="每帧最多测试多少道题；预实验建议设为 1，full 模式默认 None=全部",
    )
    args = parser.parse_args()

    output_dir = os.path.join(config.OUTPUT_DIR, "coverage_analysis", "vqa_results")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"official_qa_ir_{timestamp}.txt")

    logger = Logger(log_file)
    original_stdout = sys.stdout
    sys.stdout = logger

    try:
        print("=" * 70)
        print("  NuScenes 官方 QA + IR Pipeline 测试")
        print("=" * 70)
        print(f"\n📝 日志文件: {log_file}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🔧 运行模式: {args.mode}")

        # 加载 NuScenes devkit
        print("\n加载 NuScenes 数据集 ...")
        devkit_path = r"E:\\Project\\ADVTEST\\nuscenes-devkit\\nuscenes-devkit-master\\python-sdk"
        if devkit_path not in sys.path:
            sys.path.insert(0, devkit_path)
        from nuscenes.nuscenes import NuScenes  # type: ignore

        nusc = NuScenes(
            version="v1.0-mini", dataroot=config.NUSCENES_DATAROOT, verbose=False
        )

        # 加载官方 QA
        qa_file = r"E:\\Project\\ADVTEST\\data\\nuscenes\\qa\\NuScenes_val_questions.json"
        qa_by_sample = load_official_qa(qa_file)

        print("\n⚠️  请确保 Neo4j 数据库已启动！\n")

        # 读取 manifest 中的场景列表
        manifest_path = os.path.join(
            config.OUTPUT_DIR, "coverage_analysis", "scene_graphs", "manifest.json"
        )
        with open(manifest_path, "r", encoding="utf-8") as f:
            scenes = json.load(f)

        all_results_summary = []

        # 预实验模式：只跑第一帧，题目数量由 --max-questions 控制（默认 1）
        if args.mode == "pre":
            scenes_to_run = scenes[:1]
            max_questions = args.max_questions or 1
            print(
                f"\n[预实验] 仅测试第 1 个场景，每帧最多 {max_questions} 题，用于验证流程与日志输出。"
            )
        else:
            scenes_to_run = scenes
            max_questions = args.max_questions  # None => 全部题

        for i, scene_info in enumerate(scenes_to_run, 1):
            scene_name = scene_info["scene_name"]
            frame_idx = scene_info["frame_idx"]

            print("\n" + "#" * 70)
            print(f"#  [{i}/{len(scenes_to_run)}] 测试场景: {scene_name} 帧{frame_idx}")
            print(f"#  描述: {scene_info.get('description', '')}")
            print("#" * 70)

            # 找 sample_token
            sample_token = get_sample_token_for_scene(nusc, scene_name, frame_idx)
            if not sample_token:
                print("❌ 无法找到 sample_token，跳过该场景。")
                continue

            print(f"\nSample Token: {sample_token}")

            official_qa = qa_by_sample.get(sample_token, [])
            if not official_qa:
                print("⚠️ 该场景没有官方 QA 问题，跳过。")
                continue

            print(f"找到 {len(official_qa)} 个官方问题。")

            # 导入场景图
            scene_graph = load_scene_graph(scene_info["filepath"])
            if not import_to_neo4j(scene_graph, scene_name, frame_idx):
                continue

            # 跑 IR pipeline
            results = test_official_questions_ir(
                official_qa,
                scene_name,
                frame_idx,
                max_questions=max_questions,
            )

            if results:
                # 写 per-scene 结果（区分于 baseline 的 *_official_qa.json）
                result_file = os.path.join(
                    output_dir, f"{scene_name}_frame{frame_idx}_official_qa_ir.json"
                )
                with open(result_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "scene_name": scene_name,
                            "frame_idx": frame_idx,
                            "sample_token": sample_token,
                            "total_official_questions": len(official_qa),
                            "tested_questions": len(results),
                            "results": results,
                            "summary": {
                                "success_rate": (
                                    sum(1 for r in results if r["success"])
                                    / len(results)
                                    * 100
                                ),
                                "accuracy": (
                                    sum(1 for r in results if r["answer_match"])
                                    / len(results)
                                    * 100
                                ),
                            },
                        },
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )

                print(f"\n✓ 场景结果已保存: {result_file}")

                all_results_summary.append(
                    {
                        "scene": scene_name,
                        "frame": frame_idx,
                        "total_qa": len(official_qa),
                        "tested": len(results),
                        "success_rate": (
                            sum(1 for r in results if r["success"])
                            / len(results)
                            * 100
                        ),
                        "accuracy": (
                            sum(1 for r in results if r["answer_match"])
                            / len(results)
                            * 100
                        ),
                    }
                )

        # 最终总结
        print("\n" + "=" * 70)
        print("  官方 QA + IR Pipeline 实验总结")
        print("=" * 70)

        for res in all_results_summary:
            print(f"\n{res['scene']} 帧{res['frame']}")
            print(f"  官方问题: {res['total_qa']} 个")
            print(f"  测试数量: {res['tested']} 个")
            print(f"  执行成功率: {res['success_rate']:.1f}%")
            print(f"  答案准确率: {res['accuracy']:.1f}%")

        if all_results_summary:
            avg_success = (
                sum(r["success_rate"] for r in all_results_summary)
                / len(all_results_summary)
            )
            avg_accuracy = (
                sum(r["accuracy"] for r in all_results_summary)
                / len(all_results_summary)
            )
            print("\n总体平均:")
            print(f"  执行成功率: {avg_success:.1f}%")
            print(f"  答案准确率: {avg_accuracy:.1f}%")

        print(f"\n⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\n✓ 官方 QA + IR 实验结束，日志已保存到: {log_file}")

    finally:
        sys.stdout = original_stdout
        logger.close()
        print(f"\n[INFO] 官方 QA + IR 实验日志文件: {log_file}")


if __name__ == "__main__":
    main()
