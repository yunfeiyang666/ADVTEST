import os
import sys
import subprocess
import time
import re
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# Configuration
PYTHON = sys.executable
WORKSPACE = Path("E:/Project/ADVTEST")
CODE_DIR = WORKSPACE / "1号机代码/DATA_new/official_pipeline/code"
PIPELINE = CODE_DIR / "run_gap_pipeline_v7.py"
OUTPUTS_ROOT = Path("E:/Project/ADVTEST/1号机代码/DATA_new/outputs")
CONCURRENCY = 2
SEED = 42

DIR_PATTERN = re.compile(r"^(scene-\d+)_frame(\d+)$")

def discover_frames():
    frames = []
    for entry in OUTPUTS_ROOT.iterdir():
        if not entry.is_dir():
            continue
        m = DIR_PATTERN.match(entry.name)
        if m:
            scene_id, frame_id = m.group(1), m.group(2)
            frames.append((scene_id, int(frame_id)))
    frames.sort(key=lambda x: (x[0], x[1]))
    return frames

def is_frame_already_processed(scene_id, frame_id):
    import datetime
    cutoff = datetime.datetime(2026, 5, 27, 13, 40, 0).timestamp()
    file_path = OUTPUTS_ROOT / f"{scene_id}_frame{frame_id}" / "generation" / "qa" / f"{scene_id}_frame{frame_id}_generated.jsonl"
    if file_path.exists():
        return file_path.stat().st_mtime >= cutoff
    return False

def run_single_frame(args):
    scene_id, frame_id = args
    env = os.environ.copy()
    env["ADVTEST_IN_MEMORY"] = "true"
    env["ADVTEST_K_THRESHOLD"] = "1.0"
    env["ADVTEST_PLATEAU_WINDOW"] = "10"
    
    cmd = [
        PYTHON, str(PIPELINE),
        "--plan", "generate",
        "--scene-id", scene_id,
        "--frame-id", str(frame_id),
        "--artifact-root", str(OUTPUTS_ROOT),
        "--seed", str(SEED)
    ]
    
    t0 = time.perf_counter()
    try:
        res = subprocess.run(
            cmd,
            cwd=str(CODE_DIR),
            capture_output=True,
            text=True,
            env=env
            # No timeout! Let every single frame run to completion as requested by the user.
        )
        elapsed = time.perf_counter() - t0
        return {
            "scene_id": scene_id,
            "frame_id": frame_id,
            "returncode": res.returncode,
            "elapsed": elapsed,
            "stdout": res.stdout,
            "stderr": res.stderr
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - t0
        return {
            "scene_id": scene_id,
            "frame_id": frame_id,
            "returncode": -9,
            "elapsed": elapsed,
            "stdout": "",
            "stderr": f"TIMEOUT after {exc.timeout} seconds"
        }

def main():
    all_frames = discover_frames()
    frames = [f for f in all_frames if not is_frame_already_processed(f[0], f[1])]
    total = len(all_frames)
    pending = len(frames)
    skipped = total - pending
    
    print(f"[*] Discovered {total} total frames in outputs/...", flush=True)
    print(f"[*] Already completed today (since 13:40): {skipped}", flush=True)
    print(f"[*] Pending processing: {pending}", flush=True)
    print(f"[*] Concurrency limit: {CONCURRENCY}", flush=True)
    print(f"[*] Target executable: {PIPELINE}", flush=True)
    
    t_start = time.time()
    done = 0
    failed = []
    
    with ProcessPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(run_single_frame, f): f for f in frames}
        
        for fut in as_completed(futures):
            res = fut.result()
            done += 1
            
            scene_id = res["scene_id"]
            frame_id = res["frame_id"]
            
            if res["returncode"] != 0:
                failed.append((scene_id, frame_id, res["stderr"]))
                print(f"[{done}/{pending}] FAIL: {scene_id}_frame{frame_id} (code={res['returncode']}, elapsed={res['elapsed']:.1f}s)", flush=True)
                print(f"      Err: {res['stderr'][-200:].strip()}", flush=True)
            else:
                if done % 100 == 0 or res["elapsed"] > 15:
                    avg_time = (time.time() - t_start) / done
                    eta_min = (pending - done) * avg_time / 60
                    print(f"[{done}/{pending}] OK: {scene_id}_frame{frame_id} ({res['elapsed']:.1f}s) | Avg={avg_time:.2f}s, ETA={eta_min:.1f}m", flush=True)
                    
    wall = time.time() - t_start
    print(f"\n[*] FINISHED parallel run in {wall/60:.1f} minutes", flush=True)
    print(f"[*] Total processed: {done} | Failed: {len(failed)}", flush=True)
    
    if failed:
        print("\n[!] The following frames failed execution:")
        for f in failed[:20]:
            print(f"  - {f[0]}_frame{f[1]}: {f[2][:100].strip()}")
        sys.exit(1)
    else:
        print("\n[*] All frames completed successfully!", flush=True)

if __name__ == "__main__":
    main()
