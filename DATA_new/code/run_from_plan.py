#!/usr/bin/env python3
import sys
import json
import subprocess
import re
from pathlib import Path

OFFICIAL_PIPELINE_DIR = Path(__file__).parent / "official_pipeline"
RUN_METHOD_A = OFFICIAL_PIPELINE_DIR / "run_method_a.py"

def load_plan(plan_file: Path):
    with open(plan_file, 'r', encoding='utf-8') as f:
        plan = json.load(f)
    return plan['frames']

def modify_run_method_a(scene_id: str, frame_id: int, sg_filename: str):
    print(f"\nModifying config: {scene_id} frame {frame_id}")
    content = RUN_METHOD_A.read_text(encoding='utf-8')
    content = re.sub(r'TARGET_SG\s*=\s*"[^"]+"', f'TARGET_SG   = "{sg_filename}"', content)
    content = re.sub(r'SCENE_ID\s*=\s*"[^"]+"', f'SCENE_ID    = "{scene_id}"', content)
    content = re.sub(r'FRAME_ID\s*=\s*\d+', f'FRAME_ID    = {frame_id}', content)
    RUN_METHOD_A.write_text(content, encoding='utf-8')
    print(f"  [OK] Config updated")

def run_frame(frame_info: dict):
    scene_id = frame_info['scene_id']
    frame_id = frame_info['frame_id']
    sg_filename = frame_info['sg_filename']
    print("\n" + "="*80)
    print(f"Running: {scene_id} frame {frame_id}")
    print("="*80)
    try:
        modify_run_method_a(scene_id, frame_id, sg_filename)
    except Exception as e:
        print(f"[FAIL] Config modification failed: {e}")
        return False
    try:
        result = subprocess.run([sys.executable, str(RUN_METHOD_A)], cwd=str(OFFICIAL_PIPELINE_DIR), timeout=3600)
        if result.returncode == 0:
            print(f"[OK] {scene_id} frame {frame_id} completed")
            return True
        else:
            print(f"[FAIL] {scene_id} frame {frame_id} failed")
            return False
    except Exception as e:
        print(f"[FAIL] Exception: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_from_plan.py <plan_file.json>")
        return 1
    plan_file = Path(sys.argv[1])
    if not plan_file.exists():
        print(f"[FAIL] Plan file not found: {plan_file}")
        return 1
    print("="*80)
    print(f"Running from plan file: {plan_file}")
    print("="*80)
    frames = load_plan(plan_file)
    print(f"\nTotal {len(frames)} frames")
    results = []
    for i, frame_info in enumerate(frames, 1):
        print(f"\n[{i}/{len(frames)}]")
        success = run_frame(frame_info)
        results.append((frame_info, success))
    print("\n" + "="*80)
    print("Results:")
    for frame_info, success in results:
        status = "[OK]" if success else "[FAIL]"
        print(f"  {status} {frame_info['scene_id']} frame {frame_info['frame_id']}")
    print("="*80)
    all_success = all(success for _, success in results)
    return 0 if all_success else 1

if __name__ == "__main__":
    sys.exit(main())
