#!/usr/bin/env python3
"""
为scene-0916的frame 8和frame 10生成场景图
这是完整流程的第一步：场景图生成 + 官方过滤
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "official_pipeline"))

def generate_scene_graph(scene_name: str, frame_idx: int, output_dir: Path):
    print(f"\n{'='*80}")
    print(f"Generating scene graph: {scene_name} frame {frame_idx}")
    print(f"{'='*80}")

    from generate_selected_scenes_improved import SceneGraphConfig, SceneGraphGenerator, setup_environment
    import config as core_config
    from nuscenes.nuscenes import NuScenes
    from core_universe_filter import filter_scene_graph

    cfg = SceneGraphConfig.from_config(core_config)
    setup_environment(cfg.devkit_path)

    print(f"\nLoading NuScenes dataset...")
    nusc = NuScenes(version=cfg.nuscenes_version, dataroot=cfg.nuscenes_dataroot, verbose=False)
    print(f"[OK] Loaded {len(nusc.scene)} scenes")

    generator = SceneGraphGenerator(nusc, cfg)
    scene_graph = generator.generate(scene_name, frame_idx)

    if not scene_graph:
        print(f"[FAIL] Scene graph generation failed")
        return False

    # Apply official filtering
    print(f"\nApplying official filtering (30/40/50m by object type)...")
    raw_nodes = len(scene_graph.get('nodes', []))
    raw_edges = len(scene_graph.get('edges', []))
    print(f"  Raw: {raw_nodes} nodes, {raw_edges} edges")

    filtered_graph = filter_scene_graph(
        scene_graph,
        pixel_mode="lenient",
        min_visibility=0.4
    )

    filtered_nodes = len(filtered_graph.get('nodes', []))
    filtered_edges = len(filtered_graph.get('edges', []))
    print(f"  Filtered: {filtered_nodes} nodes, {filtered_edges} edges")
    print(f"  Reduction: {raw_nodes - filtered_nodes} nodes removed, {raw_edges - filtered_edges} edges removed")

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{scene_name}_frame{frame_idx}_scene_graph.json"
    filepath = output_dir / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(filtered_graph, f, indent=2, ensure_ascii=False)

    print(f"[OK] Filtered scene graph saved: {filepath}")

    # Print filtering statistics
    filter_info = filtered_graph.get('core_universe_filter', {})
    removal = filter_info.get('removal', {})
    print(f"  Removal breakdown:")
    print(f"    Distance: {removal.get('distance', 0)}")
    print(f"    Visibility: {removal.get('visibility', 0)}")
    print(f"    Pixel height: {removal.get('pixel_height', 0)}")
    print(f"    Non-core type: {removal.get('non_core_type', 0)}")

    return True

def main():
    print("="*80)
    print("Generate scene graphs for two frames - scene-0916 frames 8 and 10")
    print("="*80)

    output_dir = Path(__file__).parent.parent.parent / "filtered_scene_graphs"
    print(f"\nOutput directory: {output_dir}\n")

    success1 = generate_scene_graph("scene-0916", 8, output_dir)
    success2 = generate_scene_graph("scene-0916", 10, output_dir)

    print("\n" + "="*80)
    print(f"Result: Frame 8 {'[OK]' if success1 else '[FAIL]'}, Frame 10 {'[OK]' if success2 else '[FAIL]'}")
    print("="*80)
    print("\nNext step: python run_from_plan.py two_frames_plan.json\n")

    return 0 if (success1 and success2) else 1

if __name__ == "__main__":
    sys.exit(main())
