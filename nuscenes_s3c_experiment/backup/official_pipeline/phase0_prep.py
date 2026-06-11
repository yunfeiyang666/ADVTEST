#!/usr/bin/env python3
"""Phase 0: find scene-0926 frame-20 token + generate scene graph + import Neo4j."""
import json, pathlib, sys, time, subprocess
sys.path.insert(0, str(pathlib.Path(__file__).parent))

TRAINVAL  = pathlib.Path("E:/Project/ADVTEST/data/nuscenes/v1.0-trainval")
DATA_ROOT = pathlib.Path("E:/Project/ADVTEST/data/nuscenes")
SG_DIR    = pathlib.Path("E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs")
OFFICIAL  = pathlib.Path(__file__).parent
TARGET_SCENE = "scene-0926"
TARGET_FRAME = 20

# ── A: Find sample token ──────────────────────────────────────────────────────
print("=" * 60)
print("  Phase 0-A: Locating sample token")
print("=" * 60)

scenes  = json.loads((TRAINVAL / "scene.json").read_text())
samples = json.loads((TRAINVAL / "sample.json").read_text())

scene_info = next(s for s in scenes if s["name"] == TARGET_SCENE)
print(f"  scene_token : {scene_info['token']}")
print(f"  description : {scene_info.get('description','')[:90]}")

scene_samps = sorted(
    [s for s in samples if s["scene_token"] == scene_info["token"]],
    key=lambda x: x["timestamp"]
)
print(f"  total frames: {len(scene_samps)}")

frame = scene_samps[TARGET_FRAME]
SAMPLE_TOKEN = frame["token"]
print(f"\n  ✅ frame-{TARGET_FRAME} sample_token : {SAMPLE_TOKEN}")

info = {
    "scene_name":   TARGET_SCENE,
    "frame_idx":    TARGET_FRAME,
    "sample_token": SAMPLE_TOKEN,
    "scene_token":  scene_info["token"],
    "total_frames": len(scene_samps),
}
pathlib.Path("output/scene0926_info.json").parent.mkdir(exist_ok=True)
pathlib.Path("output/scene0926_info.json").write_text(json.dumps(info, indent=2))
print("  Info saved → output/scene0926_info.json")

# ── B: Generate scene graph ───────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Phase 0-B: Scene graph generation")
print("=" * 60)

sg_out = SG_DIR / f"{TARGET_SCENE}_frame{TARGET_FRAME}_scene_graph.json"
print(f"  Target path : {sg_out}")
print(f"  Exists      : {sg_out.exists()}")

if sg_out.exists():
    size_kb = sg_out.stat().st_size // 1024
    print(f"  ✅ Already exists ({size_kb} KB) — skipping generation")
else:
    # Check available generation scripts
    gen_script    = OFFICIAL / "generate_selected_scenes_improved.py"
    import_script = OFFICIAL / "import_single_scene_to_neo4j.py"
    print(f"  gen_script    : {'✅' if gen_script.exists() else '❌'} {gen_script.name}")
    print(f"  import_script : {'✅' if import_script.exists() else '❌'} {import_script.name}")

    # Read generation script to understand its args
    if gen_script.exists():
        src = gen_script.read_text(encoding="utf-8", errors="ignore")
        # Find argparse lines
        import re
        args_found = re.findall(r"add_argument\(['\"](-[-\w]+)['\"].*?\)", src)
        print(f"  gen_script args found: {args_found[:10]}")
    
    print("\n  Starting generation with nuscenes-devkit...")
    t0 = time.perf_counter()
    
    # Try running the project's generation script
    try:
        result = subprocess.run(
            [sys.executable, str(gen_script),
             "--scene-names", TARGET_SCENE,
             "--frame-indices", str(TARGET_FRAME),
             "--data-root", str(DATA_ROOT),
             "--version", "v1.0-trainval",
             "--output-dir", str(SG_DIR)],
            capture_output=True, text=True, timeout=300, cwd=str(OFFICIAL)
        )
        print(f"  returncode: {result.returncode}")
        if result.stdout:
            print(f"  stdout:\n{result.stdout[:800]}")
        if result.stderr:
            print(f"  stderr (last 400):\n{result.stderr[-400:]}")
    except Exception as e:
        print(f"  Subprocess error: {e}")

    if sg_out.exists():
        size_kb = sg_out.stat().st_size // 1024
        elapsed = time.perf_counter() - t0
        print(f"\n  ✅ Scene graph generated in {elapsed:.1f}s ({size_kb} KB)")
    else:
        print(f"\n  ❌ Scene graph not found at expected path, checking outputs...")
        # Search for any newly created files
        for f in SG_DIR.glob(f"*0926*"):
            print(f"    Found: {f.name} ({f.stat().st_size//1024} KB)")

# ── C: Check import script args ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Phase 0-C: Neo4j import script check")
print("=" * 60)
import_script = OFFICIAL / "import_single_scene_to_neo4j.py"
if import_script.exists():
    src = import_script.read_text(encoding="utf-8", errors="ignore")
    import re
    args_found = re.findall(r"add_argument\(['\"](-[-\w]+)['\"].*?\)", src)
    print(f"  import_script args: {args_found[:15]}")
    # Show first 50 lines
    lines = src.splitlines()[:50]
    for ln in lines:
        if "add_argument" in ln or "argparse" in ln or "scene" in ln.lower():
            print(f"    {ln.strip()}")
else:
    print("  ❌ import_single_scene_to_neo4j.py not found")
    # Search alternative
    for f in OFFICIAL.glob("import*.py"):
        print(f"  Found: {f.name}")

print("\n✅ Phase 0-A/B/C prep complete")
