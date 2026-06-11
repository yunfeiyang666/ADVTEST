"""\nCompute multi-level (L=0,1,2) coverage for all scenes listed in\noutput/coverage_analysis/scene_graphs/manifest.json, and write\nresults to output/coverage_analysis/vqa_results/all_scenes_multi_level_coverage.json.\n\nThis is a temporary helper script used because test_multi_level_coverage_all_scenes.py\nappears to be corrupted in the current workspace.\n"""
import json
from pathlib import Path
from typing import Any, Dict, List

import config
from test_multi_level_coverage import compute_multi_level_coverage


def _load_manifest(manifest_path: Path) -> List[Dict[str, Any]]:
    with manifest_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _find_vqa_result_file(scene_name: str, frame_idx: int, base_dir: Path) -> Path | None:
    """Prefer *_official_qa_ir.json, fall back to *_official_qa.json."""
    ir_name = f"{scene_name}_frame{frame_idx}_official_qa_ir.json"
    base_name = f"{scene_name}_frame{frame_idx}_official_qa.json"

    ir_path = base_dir / ir_name
    base_path = base_dir / base_name

    if ir_path.exists():
        return ir_path
    if base_path.exists():
        return base_path
    return None


def main() -> None:
    output_root = Path(config.OUTPUT_DIR) / "coverage_analysis"
    scene_graph_dir = output_root / "scene_graphs"
    vqa_result_dir = output_root / "vqa_results"
    vqa_result_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = scene_graph_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found: {manifest_path}")

    scenes = _load_manifest(manifest_path)

    print("=" * 70)
    print("  Global multi-level coverage (L=0,1,2)")
    print("=" * 70)
    print(f"\nTotal scenes in manifest: {len(scenes)}")

    all_stats: List[Dict[str, Any]] = []

    for i, scene_info in enumerate(scenes, 1):
        scene_name = scene_info["scene_name"]
        frame_idx = scene_info["frame_idx"]
        sg_path = Path(scene_info["filepath"])

        print("\n" + "-" * 70)
        print(f"[{i}/{len(scenes)}] Scene: {scene_name} frame {frame_idx}")
        print(f"Scene graph: {sg_path}")

        if not sg_path.exists():
            print("[SKIP] scene graph file does not exist.")
            continue

        vqa_file = _find_vqa_result_file(scene_name, frame_idx, vqa_result_dir)
        if not vqa_file:
            print("[SKIP] no matching official QA result file (*_official_qa_ir.json or *_official_qa.json).")
            continue

        print(f"Using VQA result file: {vqa_file.name}")

        stats = compute_multi_level_coverage(sg_path, vqa_file)
        all_stats.append(
            {
                "scene_name": scene_name,
                "frame_idx": frame_idx,
                "description": scene_info.get("description", ""),
                "total_objects": scene_info.get("total_objects"),
                "multi_level": stats["multi_level"],
                "base_edge_coverage": stats["base_edge_coverage"],
            }
        )

    out_path = vqa_result_dir / "all_scenes_multi_level_coverage.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"scenes": all_stats}, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("  Done computing multi-level coverage for all scenes")
    print("=" * 70)
    print(f"Results written to: {out_path}")


if __name__ == "__main__":
    main()
