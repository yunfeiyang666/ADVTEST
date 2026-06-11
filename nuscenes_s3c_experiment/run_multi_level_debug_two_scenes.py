from pathlib import Path
from pprint import pprint

from test_multi_level_coverage import compute_multi_level_coverage

BASE = Path("output/coverage_analysis")

SCENES = [
    ("scene-0916", 8),
    ("scene-0103", 25),
]

for scene_name, frame_idx in SCENES:
    sg_path = BASE / "scene_graphs" / f"{scene_name}_frame{frame_idx}_scene_graph.json"
    vqa_path = BASE / "vqa_results" / f"{scene_name}_frame{frame_idx}_official_qa.json"

    print("=" * 70)
    print(f"Scene: {scene_name}_frame{frame_idx}")
    print(f"  scene_graph: {sg_path}")
    print(f"  vqa_results: {vqa_path}")

    stats = compute_multi_level_coverage(sg_path, vqa_path)

    print("\n[Edge] base_edge_coverage:")
    pprint(stats["base_edge_coverage"])
    print("\n[Multi-level] L0/L1/L2:")
    pprint(stats["multi_level"])
    print()
