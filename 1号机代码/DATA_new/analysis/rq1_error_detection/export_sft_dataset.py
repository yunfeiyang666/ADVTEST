import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict

# Insert paths to import evaluator
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).parent))

import evaluator

# NuScenes-mini scene list
MINI_SCENES = {
    "scene-0061", "scene-0103", "scene-0553", "scene-0655", "scene-0757", 
    "scene-0796", "scene-0916", "scene-1077", "scene-1094", "scene-1100"
}

def main():
    parser = argparse.ArgumentParser(description="Export LLaVA-style VLM SFT Dataset")
    parser.add_argument("--out_dir", type=str, default=None,
                        help="Output directory (default: DATA_new/sft_dataset)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Maximum number of QA pairs to export")
    parser.add_argument("--mini_only", action="store_true",
                        help="Only export frames belonging to NuScenes-mini scenes")
    args = parser.parse_args()

    # Resolve paths
    out_dir = Path(args.out_dir) if args.out_dir else WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "sft_dataset"
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    outputs_root = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "outputs"
    dataroot = WORKSPACE_ROOT / "data" / "nuscenes"
    if not dataroot.exists():
        dataroot = WORKSPACE_ROOT / "data"  # fallback

    print("=== Starting VLM SFT Dataset Export ===")
    print(f"Target Output Directory: {out_dir}")
    print(f"Data root: {dataroot}")
    if args.mini_only:
        print("Filter active: exporting NuScenes-mini scenes only.")
    if args.limit:
        print(f"Limit active: exporting maximum of {args.limit} QA pairs.")

    sft_data = []
    total_rendered_images = 0
    t0 = time.time()

    # Iterate through each processed output frame folder
    frame_dirs = sorted(list(outputs_root.iterdir()))
    
    for frame_dir in frame_dirs:
        if not frame_dir.is_dir() or not frame_dir.name.startswith("scene-"):
            continue

        sf = frame_dir.name
        scene_name = sf.split("_")[0]

        # Apply mini filter
        if args.mini_only and scene_name not in MINI_SCENES:
            continue

        generated_jsonl = frame_dir / "generation" / "qa" / f"{sf}_generated.jsonl"
        sg_path = frame_dir / "offline" / "scene_graphs" / f"{sf}_filtered_scene_graph.json"

        if not (generated_jsonl.exists() and sg_path.exists()):
            continue

        # Load questions
        all_qs = []
        try:
            with open(generated_jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        all_qs.append(json.loads(line))
        except Exception as e:
            print(f"Error reading questions for {sf}: {e}")
            continue

        if not all_qs:
            continue

        # Load scene graph
        try:
            with open(sg_path, "r", encoding="utf-8") as f:
                sg = json.load(f)
        except Exception as e:
            print(f"Error reading scene graph for {sf}: {e}")
            continue

        # Target image path inside the exported SFT folder
        target_image_rel = f"images/{sf}_labeled_mosaic.jpg"
        target_image_abs = out_dir / target_image_rel

        # Render stitched 2x3 labeled cameras mosaic
        image_exists = target_image_abs.exists()
        if not image_exists:
            success = evaluator.render_labeled_mosaic(sg, dataroot, target_image_abs)
            if not success:
                print(f"  Warning: Failed to render mosaic for {sf}. Proceeding with VQA questions export (placeholders).")
            else:
                total_rendered_images += 1
        
        # Add questions to SFT list
        frame_qa_count = 0
        for q in all_qs:
            if args.limit and len(sft_data) >= args.limit:
                break

            q_id = q.get("question_id") or str(len(sft_data))
            question_text = q["question"]
            answer_text = str(q["answer"])

            sft_data.append({
                "id": f"{sf}_q{q_id}",
                "image": target_image_rel,
                "conversations": [
                    {
                        "from": "human",
                        "value": f"<image>\n{question_text}"
                    },
                    {
                        "from": "gpt",
                        "value": answer_text
                    }
                ]
            })
            frame_qa_count += 1

        if frame_qa_count > 0:
            print(f"Exported {frame_qa_count} QA pairs from {sf} (Image rendered: {not image_exists})")

        if args.limit and len(sft_data) >= args.limit:
            print("Limit reached. Stopping export.")
            break

    # Save SFT JSON file
    dataset_json_path = out_dir / "dataset.json"
    with open(dataset_json_path, "w", encoding="utf-8") as f:
        json.dump(sft_data, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - t0
    print("\n=== SFT Dataset Export Completed ===")
    print(f"Saved dataset JSON: {dataset_json_path}")
    print(f"Total exported SFT instances: {len(sft_data)}")
    print(f"Total rendered images: {total_rendered_images}")
    print(f"Time elapsed: {elapsed:.1f}s")

if __name__ == "__main__":
    main()
