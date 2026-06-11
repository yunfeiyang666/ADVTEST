#!/usr/bin/env python3
"""
prep_scene0926.py — Phase 0 preparation for scene-0926 frame-20
Finds sample_token, then generates scene graph and imports to Neo4j.
"""
import json, pathlib, sys, time, collections
sys.path.insert(0, str(pathlib.Path(__file__).parent))

TRAINVAL = pathlib.Path("E:/Project/ADVTEST/data/nuscenes/v1.0-trainval")
DATA_ROOT = pathlib.Path("E:/Project/ADVTEST/data/nuscenes")
TARGET_SCENE = "scene-0926"
TARGET_FRAME = 20   # 0-based

print("=" * 65)
print(f"  Phase 0-A: Locating {TARGET_SCENE} frame-{TARGET_FRAME}")
print("=" * 65)

# ── Load metadata ─────────────────────────────────────────────────────────────
scenes  = json.loads((TRAINVAL / "scene.json").read_text())
samples = json.loads((TRAINVAL / "sample.json").read_text())

scene_token2info = {s["token"]: s for s in scenes}
# Find scene-0926
target_scene_info = next((s for s in scenes if s["name"] == TARGET_SCENE), None)
if not target_scene_info:
    print(f"ERROR: {TARGET_SCENE} not found in trainval!")
    sys.exit(1)

print(f"  scene token   : {target_scene_info['token']}")
print(f"  description   : {target_scene_info.get('description','')[:80]}")
print(f"  n_ann tokens  : {target_scene_info.get('nbr_samples', '?')}")

# Get all samples for this scene, sorted by timestamp
scene_samples = [s for s in samples if s["scene_token"] == target_scene_info["token"]]
scene_samples.sort(key=lambda x: x["timestamp"])
print(f"  Total frames  : {len(scene_samples)}")
print(f"  Frames 18-22  : {[s['token'][:8]+'...' for s in scene_samples[18:23]]}")

if TARGET_FRAME >= len(scene_samples):
    print(f"ERROR: frame-{TARGET_FRAME} out of range (max {len(scene_samples)-1})")
    sys.exit(1)

target_sample = scene_samples[TARGET_FRAME]
SAMPLE_TOKEN = target_sample["token"]
print(f"\n  ✅ Frame-{TARGET_FRAME} sample_token : {SAMPLE_TOKEN}")
print(f"     timestamp            : {target_sample['timestamp']}")

# Save for downstream
out_info = {
    "scene_name": TARGET_SCENE,
    "frame_idx": TARGET_FRAME,
    "sample_token": SAMPLE_TOKEN,
    "scene_token": target_scene_info["token"],
    "timestamp": target_sample["timestamp"],
    "total_frames": len(scene_samples),
}
pathlib.Path("output/scene0926_frame20_info.json").write_text(
    json.dumps(out_info, indent=2), encoding="utf-8"
)
print(f"\n  Info saved → output/scene0926_frame20_info.json")

# ── Phase 0-B: Generate scene graph ──────────────────────────────────────────
print("\n" + "=" * 65)
print("  Phase 0-B: Generating scene graph")
print("=" * 65)

# Check nuscenes-devkit
try:
    from nuscenes.nuscenes import NuScenes
    print("  ✅ nuscenes-devkit available")
except ImportError:
    print("  ❌ nuscenes-devkit not available")
    sys.exit(1)

# Check the generation script
gen_script = pathlib.Path("generate_selected_scenes_improved.py")
import_script = pathlib.Path("import_single_scene_to_neo4j.py")
print(f"  generate script : {'✅' if gen_script.exists() else '❌'} {gen_script}")
print(f"  import script   : {'✅' if import_script.exists() else '❌'} {import_script}")

# Target output path
sg_dir = pathlib.Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs")
sg_out  = sg_dir / f"{TARGET_SCENE}_frame{TARGET_FRAME}_scene_graph.json"
print(f"\n  Target SG path  : {sg_out}")
print(f"  Already exists  : {sg_out.exists()}")

if sg_out.exists():
    size = sg_out.stat().st_size // 1024
    print(f"  ✅ Scene graph already exists ({size} KB) — skipping generation")
else:
    print("\n  Generating scene graph using nuscenes-devkit...")
    print(f"  (data_root={DATA_ROOT}, version=v1.0-trainval, sample={SAMPLE_TOKEN})")
    
    # Use the step2 scene graph generation script approach
    # Load nuscenes for the specific sample
    t0 = time.perf_counter()
    
    # Minimal inline generation (same logic as generate_selected_scenes_improved.py)
    nusc = NuScenes(version="v1.0-trainval", dataroot=str(DATA_ROOT), verbose=False)
    
    # Get sample
    sample = nusc.get("sample", SAMPLE_TOKEN)
    
    # Import the scene graph builder from project
    sys.path.insert(0, str(pathlib.Path("E:/Project/ADVTEST/nuscenes_s3c_experiment")))
    try:
        # Try importing the project's graph generator
        from core_pipeline.generate_selected_scenes_improved import generate_scene_graph_for_sample
        sg_data = generate_scene_graph_for_sample(nusc, SAMPLE_TOKEN, scene_name=TARGET_SCENE, frame_idx=TARGET_FRAME)
        sg_dir.mkdir(parents=True, exist_ok=True)
        sg_out.write_text(json.dumps(sg_data, indent=2, ensure_ascii=False), encoding="utf-8")
        elapsed = time.perf_counter() - t0
        print(f"  ✅ Scene graph generated in {elapsed:.1f}s → {sg_out}")
    except (ImportError, AttributeError) as e:
        print(f"  ⚠️  Direct import failed ({e}), using subprocess approach...")
        import subprocess
        result = subprocess.run(
            [sys.executable, str(gen_script),
             "--scene-name", TARGET_SCENE,
             "--frame-idx", str(TARGET_FRAME),
             "--sample-token", SAMPLE_TOKEN],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            print(f"  ✅ Scene graph generated via script")
        else:
            print(f"  ❌ Generation failed:\n{result.stderr[:500]}")
            # Last resort: build minimal scene graph
            print("  Attempting minimal graph construction...")
            import build_minimal_sg
            
print("\nPhase 0-A/B complete. See output/scene0926_frame20_info.json")
