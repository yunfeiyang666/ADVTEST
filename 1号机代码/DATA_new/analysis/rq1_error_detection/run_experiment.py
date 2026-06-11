import os
import sys
import json
import random
import time
from pathlib import Path
from collections import defaultdict
from typing import List

# Insert path of official_pipeline/code and local directory so we can import modules correctly
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "official_pipeline" / "code"))
sys.path.insert(0, str(Path(__file__).parent))

import rq1_selectors as selectors
import evaluator

# Paths
OUTPUTS_ROOT = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "outputs"
DATA_CACHE_DIR = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "analysis" / "data_cache"
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Budgets to evaluate
BUDGETS = [5, 10, 15, 20, 30, 40, 50]
SELECTORS = {
    "Ours (Complete)": selectors.select_ours_complete,
    "Ours-Random": selectors.select_ours_random,
    "Qatest": selectors.select_qatest,
    "Recursive Asking": selectors.select_recursive_asking
}

def get_scene_graph(frame_dir: Path, sf: str) -> dict:
    """Load the filtered scene graph for a frame."""
    sg_path = frame_dir / "offline" / "scene_graphs" / f"{sf}_filtered_scene_graph.json"
    if sg_path.exists():
        with open(sg_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def scan_valid_frames(limit: int = 50, seed: int = 42) -> List[dict]:
    """Scan or load cached representative frames."""
    cache_path = DATA_CACHE_DIR / "rq1_100_eval_frames.json"
    if cache_path.exists():
        print(f"Loading evaluation frames from cache: {cache_path}")
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            
            # Limit to the requested number of frames
            if len(cached_data) > limit:
                cached_data = cached_data[:limit]
                
            valid_frames = []
            for item in cached_data:
                sf = item["scene_frame"]
                valid_frames.append({
                    "sf": sf,
                    "frame_dir": OUTPUTS_ROOT / sf,
                    "n_objects": item["n_objects"],
                    "generated_count": item["generated_count"]
                })
            print(f"Loaded {len(valid_frames)} evaluation frames successfully.")
            return valid_frames
        except Exception as e:
            print(f"Error loading cached frames: {e}. Falling back to active scan.")

    # Fallback to scanning if cache is missing
    print("Warning: rq1_100_eval_frames.json cache not found. Scanning outputs directory...")
    valid_frames = []
    
    for frame_dir in sorted(OUTPUTS_ROOT.iterdir()):
        if not frame_dir.is_dir() or not frame_dir.name.startswith("scene-"):
            continue
        
        sf = frame_dir.name
        summary_path = frame_dir / "reports" / f"{sf}_summary.json"
        generated_jsonl = frame_dir / "generation" / "qa" / f"{sf}_generated.jsonl"
        
        if summary_path.exists() and generated_jsonl.exists():
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary = json.load(f)
                
                n_objects = summary.get("coverage", {}).get("l0", 0)
                generated = summary.get("generated", 0)
                
                if n_objects >= 3 and generated >= 50:
                    valid_frames.append({
                        "sf": sf,
                        "frame_dir": frame_dir,
                        "n_objects": n_objects,
                        "generated_count": generated
                    })
            except Exception:
                pass
                
    print(f"Found {len(valid_frames)} total eligible non-trivial frames.")
    
    # Sample frames randomly for evaluation
    if len(valid_frames) > limit:
        rng = random.Random(seed)
        valid_frames = rng.sample(valid_frames, limit)
        
    print(f"Selected {len(valid_frames)} representative frames for evaluation.")
    return valid_frames

def main():
    import argparse
    parser = argparse.ArgumentParser(description="RQ1 Error Detection Experiment Runner")
    parser.add_argument("--mode", choices=["MOCK", "LOCAL_GPU", "API", "MPLUG", "MINICPM"], default="MOCK",
                        help="Evaluation mode (default: MOCK)")
    parser.add_argument("--frames", type=int, default=50,
                        help="Number of evaluation frames (default: 50)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for selection (default: 42)")
    args = parser.parse_args()

    print(f"\n=== Starting RQ1 Error Detection Experiment (Mode: {args.mode}) ===")
    
    # Initialize VLM Evaluator
    if args.mode == "MOCK":
        vlm = evaluator.MockVLMEvaluator()
    elif args.mode == "LOCAL_GPU":
        vlm = evaluator.LocalGPUEvaluator()
    elif args.mode == "MPLUG":
        vlm = evaluator.MPLUGEvaluator()
    elif args.mode == "MINICPM":
        vlm = evaluator.MiniCPMOEvaluator()
    else:  # API
        vlm = evaluator.APIEvaluator()

    # Load frames
    eval_frames = scan_valid_frames(limit=args.frames, seed=args.seed)
    
    # Global cache to prevent duplicate VLM evaluations on the same question
    vlm_result_cache = {}  # (frame_name, question_text) -> (predicted_answer, is_correct)
    
    # Structured results log
    # format: selector -> budget -> list of results per frame
    results = {
        sel_name: {
            b: {"wrong_count": 0, "obj_involvement_sum": 0.0} for b in BUDGETS
        } for sel_name in SELECTORS
    }
    
    # Detailed log for check
    detailed_frame_records = []
    
    t0 = time.time()
    
    for idx, f_meta in enumerate(eval_frames):
        sf = f_meta["sf"]
        frame_dir = f_meta["frame_dir"]
        
        # Load generated questions
        generated_jsonl = frame_dir / "generation" / "qa" / f"{sf}_generated.jsonl"
        all_qs = []
        with open(generated_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    all_qs.append(json.loads(line))
        
        # Load scene graph to get total objects
        sg = get_scene_graph(frame_dir, sf)
        nodes = sg.get("nodes") or sg.get("objects") or []
        scene_objects = set(str(n.get("id") or n.get("unique_id")) for n in nodes if n.get("id") != "ego" and n.get("unique_id") != "ego")
        n_total_objects = len(scene_objects) if scene_objects else f_meta["n_objects"]
        
        print(f"[{idx+1}/{len(eval_frames)}] {sf} ({len(all_qs)} questions, {n_total_objects} objects)")
        
        # Optional: render mosaic image if in visual mode
        mosaic_path = None
        if args.mode in ("LOCAL_GPU", "API", "MPLUG", "MINICPM"):
            mosaic_path = WORKSPACE_ROOT / "output" / "rq1_temp_mosaics" / f"{sf}_labeled_mosaic.jpg"
            dataroot = WORKSPACE_ROOT / "DATA_new" / "data"
            if not dataroot.exists():
                dataroot = WORKSPACE_ROOT / "data" / "nuscenes"
            if not dataroot.exists():
                dataroot = WORKSPACE_ROOT / "data"  # fallback
            
            # Draw labeled mosaic
            success = evaluator.render_labeled_mosaic(sg, dataroot, mosaic_path)
            if not success:
                print(f"  Warning: Failed to render mosaic for {sf}. Falling back to MOCK mode for this frame.")
                frame_vlm = evaluator.MockVLMEvaluator()
            else:
                frame_vlm = vlm
        else:
            frame_vlm = vlm

        frame_record = {
            "scene_frame": sf,
            "total_objects": n_total_objects,
            "budgets": {}
        }

        # For each budget and selector
        for b in BUDGETS:
            frame_record["budgets"][b] = {}
            for sel_name, sel_fn in SELECTORS.items():
                # Select B questions
                selected_qs = sel_fn(all_qs, b, seed=args.seed)
                
                wrong_qs = []
                correct_count = 0
                
                # Evaluate each selected question
                for q in selected_qs:
                    q_text = q["question"]
                    
                    # Cache lookup
                    cache_key = (sf, q_text)
                    if cache_key in vlm_result_cache:
                        pred, is_correct = vlm_result_cache[cache_key]
                    else:
                        if args.mode in ("LOCAL_GPU", "API", "MPLUG", "MINICPM") and mosaic_path and mosaic_path.exists():
                            pred, is_correct = frame_vlm.evaluate(q, mosaic_path)
                        else:
                            pred, is_correct = frame_vlm.evaluate(q)
                        vlm_result_cache[cache_key] = (pred, is_correct)
                    
                    if is_correct:
                        correct_count += 1
                    else:
                        wrong_qs.append(q)
                
                # Calculate object involvement coverage
                # Set of objects in wrong questions
                involved_objects = set()
                for wq in wrong_qs:
                    fnodes = wq.get("footprint_nodes") or []
                    for node in fnodes:
                        if node != "ego" and node in scene_objects:
                            involved_objects.add(node)
                
                involvement_ratio = len(involved_objects) / n_total_objects if n_total_objects > 0 else 0.0
                
                results[sel_name][b]["wrong_count"] += len(wrong_qs)
                results[sel_name][b]["obj_involvement_sum"] += involvement_ratio
                
                frame_record["budgets"][b][sel_name] = {
                    "selected_count": len(selected_qs),
                    "wrong_count": len(wrong_qs),
                    "involvement_ratio": involvement_ratio
                }
                
        detailed_frame_records.append(frame_record)

    # Compile aggregated metrics
    aggregated = {
        "mode": args.mode,
        "num_frames": len(eval_frames),
        "results": {}
    }
    
    for sel_name in SELECTORS:
        aggregated["results"][sel_name] = []
        for b in BUDGETS:
            avg_wrong = results[sel_name][b]["wrong_count"] / len(eval_frames)
            avg_involvement = results[sel_name][b]["obj_involvement_sum"] / len(eval_frames)
            aggregated["results"][sel_name].append({
                "budget": b,
                "avg_wrong": round(avg_wrong, 2),
                "avg_involvement": round(avg_involvement, 4)
            })

    # Save results cache
    cache_file = DATA_CACHE_DIR / "rq1_results.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({
            "summary": aggregated,
            "detailed": detailed_frame_records
        }, f, indent=2, ensure_ascii=False)
        
    print(f"\n=== Experiment completed in {time.time() - t0:.1f}s ===")
    print(f"Results saved to {cache_file}")
    
    # Print summary table
    print("\nSummary of Failures Detected (Avg. Wrong Questions / Avg. Object Involvement Rate):")
    print(f"{'Selector':<20} | " + " | ".join(f"B={b:<8}" for b in BUDGETS))
    print("-" * 110)
    for sel_name in SELECTORS:
        row_strs = []
        for b in BUDGETS:
            stat = next(item for item in aggregated["results"][sel_name] if item["budget"] == b)
            row_strs.append(f"{stat['avg_wrong']:.1f} ({stat['avg_involvement'] * 100:.1f}%)")
        print(f"{sel_name:<20} | " + " | ".join(row_strs))
    print()

if __name__ == "__main__":
    main()
