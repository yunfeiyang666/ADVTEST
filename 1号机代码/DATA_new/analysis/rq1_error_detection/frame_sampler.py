import os
import json
import random
from pathlib import Path

# Paths
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
OUTPUTS_ROOT = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "outputs"
DATA_CACHE_DIR = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "analysis" / "data_cache"
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def main():
    print("=== Scanning outputs for eligible evaluation frames ===")
    eligible = []
    
    # Iterate through outputs
    for entry in sorted(OUTPUTS_ROOT.iterdir()):
        if not entry.is_dir() or not entry.name.startswith("scene-"):
            continue
        
        sf = entry.name
        summary_path = entry / "reports" / f"{sf}_summary.json"
        generated_jsonl = entry / "generation" / "qa" / f"{sf}_generated.jsonl"
        
        if summary_path.exists() and generated_jsonl.exists():
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary = json.load(f)
                
                n_objects = summary.get("coverage", {}).get("l0", 0)
                generated = summary.get("generated", 0)
                
                # Filter for non-trivial frames
                if n_objects >= 3 and generated >= 50:
                    eligible.append({
                        "scene_frame": sf,
                        "n_objects": n_objects,
                        "generated_count": generated
                    })
            except Exception as e:
                print(f"Error reading summary for {sf}: {e}")
                
    print(f"Total non-trivial frames found: {len(eligible)}")
    
    if len(eligible) < 100:
        print("Warning: Less than 100 eligible frames found. Using all available frames.")
        selected = eligible
    else:
        # Sort by frame name for stable sampling
        eligible.sort(key=lambda x: x["scene_frame"])
        # Deterministic sample of 100 frames
        rng = random.Random(42)
        selected = rng.sample(eligible, 100)
        
    # Sort selected frames by name
    selected.sort(key=lambda x: x["scene_frame"])
    
    # Save cache file
    cache_path = DATA_CACHE_DIR / "rq1_100_eval_frames.json"
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(selected, f, indent=2, ensure_ascii=False)
        
    print(f"Successfully selected {len(selected)} frames.")
    print(f"Saved cache to {cache_path}")
    
    # Print average stats
    avg_objects = sum(x["n_objects"] for x in selected) / len(selected)
    avg_generated = sum(x["generated_count"] for x in selected) / len(selected)
    print(f"Statistics of selected 100 frames:")
    print(f"  - Average objects per frame: {avg_objects:.1f}")
    print(f"  - Average candidate questions per frame: {avg_generated:.1f}")

if __name__ == "__main__":
    main()
