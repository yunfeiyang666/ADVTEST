"""
多场景多级路径覆盖率统计脚本 (L=0,1,2)

- 依赖 test_multi_level_coverage.compute_multi_level_coverage
- 对 manifest.json 中列出的所有场景：
    * 读取 scene_graph.json
    * 尝试使用 *_official_qa_ir.json 作为 VQA 结果文件
      (若不存在则回退到 *_official_qa.json)
    * 计算边级 + L0/L1/L2 覆盖率
- 支持预实验模式（只跑 1 个场景）和正式模式（全部场景）

输出：
  - 文本日志：output/coverage_analysis/vqa_results/multi_level_coverage_*.txt
  - 汇总 JSON：output/coverage_analysis/vqa_results/all_scenes_multi_level_coverage.json
"""
import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from test_multi_level_coverage import compute_multi_level_coverage


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


def _load_manifest(manifest_path: Path) -> List[Dict[str, Any]]:
    with manifest_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _find_vqa_result_file(
    scene_name: str, frame_idx: int, base_dir: Path
) -> Optional[Path]:
    """优先使用 IR 版本官方 QA 结果 *_official_qa_ir.json，若不存在则回退到 baseline *_official_qa.json"""
    ir_name = f"{scene_name}_frame{frame_idx}_official_qa_ir.json"
    base_name = f"{scene_name}_frame{frame_idx}_official_qa.json"

    ir_path = base_dir / ir_name
    base_path = base_dir / base_name

    if ir_path.exists():
        return ir_path
    if base_path.exists():
        return base_path
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Compute multi-level (L0/L1/L2) coverage for all scenes."
    )
    parser.add_argument(
        "--mode",
        choices=["pre", "full"],
        default="full",
        help="pre: 预实验（仅首个场景），full: 正式实验（全部场景）",
    )
    args = parser.parse_args()

    output_root = Path(config.OUTPUT_DIR) / "coverage_analysis"
    scene_graph_dir = output_root / "scene_graphs"
    vqa_result_dir = output_root / "vqa_results"
    vqa_result_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = scene_graph_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json 不存在: {manifest_path}")

    scenes = _load_manifest(manifest_path)

    # 准备日志
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = vqa_result_dir / f"multi_level_coverage_{ts}.txt"
    logger = Logger(str(log_path))
    original_stdout = sys.stdout
    sys.stdout = logger

    try:
        print("=" * 70)
        print("  多级路径覆盖率统计 (L=0,1,2)")
        print("=" * 70)
        print(f"\n📝 日志文件: {log_path}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🔧 运行模式: {args.mode}")

        if args.mode == "pre":
            scenes_to_run = scenes[:1]
            print(
                f"\n[预实验] 仅统计第 1 个场景，用于验证流程与日志输出格式。"
            )
        else:
            scenes_to_run = scenes

        print(f"\n共需处理场景: {len(scenes_to_run)} 个")

        all_stats: List[Dict[str, Any]] = []

        for i, scene_info in enumerate(scenes_to_run, 1):
            scene_name = scene_info["scene_name"]
            frame_idx = scene_info["frame_idx"]
            sg_path = Path(scene_info["filepath"])

            print("\n" + "-" * 70)
            print(f"[{i}/{len(scenes_to_run)}] 场景: {scene_name} 帧{frame_idx}")
            print(f"场景图路径: {sg_path}")

            if not sg_path.exists():
                print("❌ 场景图文件不存在，跳过该场景。")
                continue

            vqa_file = _find_vqa_result_file(scene_name, frame_idx, vqa_result_dir)
            if not vqa_file:
                print(
                    "⚠️ 未找到对应的官方 QA 结果文件 "
                    f"({scene_name}_frame{frame_idx}_official_qa_ir.json / .json)，跳过。"
                )
                continue

            print(f"使用 VQA 结果文件: {vqa_file.name}")

            # 调用已有的 compute_multi_level_coverage
            stats = compute_multi_level_coverage(sg_path, vqa_file)

            base_edge = stats["base_edge_coverage"]
            ml = stats["multi_level"]
            all_stats.append(
                {
                    "scene_name": scene_name,
                    "frame_idx": frame_idx,
                    "description": scene_info.get("description", ""),
                    "total_objects": scene_info.get("total_objects"),
                    "base_edge_coverage": base_edge,
                    "multi_level": ml,
                }
            )

        # 保存汇总 JSON
        out_json_path = vqa_result_dir / "all_scenes_multi_level_coverage.json"
        with out_json_path.open("w", encoding="utf-8") as f:
            json.dump({"scenes": all_stats}, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 70)
        print("  所有场景多级覆盖率统计完成")
        print("=" * 70)
        print(f"结果已保存到: {out_json_path}")
        print(f"\n⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\n✓ 多级覆盖率实验结束，日志已保存到: {log_path}")

    finally:
        sys.stdout = original_stdout
        logger.close()
        print(f"\n[INFO] 多级覆盖率实验日志文件: {log_path}")


if __name__ == "__main__":
    main()
