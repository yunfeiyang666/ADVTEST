"""
Batch runner: execute generate stage for all frames in outputs/.

Usage:
    python run_all_frames.py [--start N] [--end N] [--dry-run]

Features:
  - Auto-skip already-completed frames (resume from checkpoint)
  - Neo4j connectivity check with retry before each frame
  - Consecutive failure detection → pause & retry Neo4j
  - Progress logging with ETA
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# ── Configuration ──
PYTHON = r"E:\Project\ADVTEST\.venv310\Scripts\python.exe"
PIPELINE = Path(__file__).resolve().parent / "run_gap_pipeline_v7.py"
OUTPUTS_ROOT = Path(r"E:\Project\ADVTEST\1号机代码\DATA_new\outputs")
SEED = 42

# Stability settings
MAX_CONSECUTIVE_FAILS = 5       # After this many consecutive fails, pause and check Neo4j
NEO4J_RETRY_WAIT_SECONDS = 30   # Wait time between Neo4j reconnect attempts
NEO4J_MAX_RETRIES = 20          # Max reconnect attempts before giving up (10 min total)

DIR_PATTERN = re.compile(r"^(scene-\d+)_frame(\d+)$")


def check_neo4j() -> bool:
    """Check if Neo4j is reachable."""
    try:
        result = subprocess.run(
            [PYTHON, "-c",
             "from neo4j import GraphDatabase; "
             "d=GraphDatabase.driver('bolt://127.0.0.1:7687',auth=('neo4j','87017563')); "
             "s=d.session(); s.run('RETURN 1').single(); s.close(); d.close(); "
             "print('OK')"],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0 and "OK" in result.stdout
    except Exception:
        return False


def wait_for_neo4j() -> bool:
    """Wait until Neo4j is available, with retries."""
    for attempt in range(1, NEO4J_MAX_RETRIES + 1):
        if check_neo4j():
            print(f"[batch] Neo4j connected (attempt {attempt})", flush=True)
            return True
        print(
            f"[batch] Neo4j unavailable, retry {attempt}/{NEO4J_MAX_RETRIES} "
            f"in {NEO4J_RETRY_WAIT_SECONDS}s...",
            flush=True
        )
        time.sleep(NEO4J_RETRY_WAIT_SECONDS)
    return False


def discover_frames():
    frames = []
    for entry in OUTPUTS_ROOT.iterdir():
        if not entry.is_dir():
            continue
        m = DIR_PATTERN.match(entry.name)
        if m:
            scene_id, frame_id = m.group(1), m.group(2)
            frames.append((scene_id, int(frame_id), entry))
    frames.sort(key=lambda x: (x[0], x[1]))
    return frames


def is_already_done(frame_dir: Path) -> bool:
    gen_dir = frame_dir / "generation" / "qa"
    if not gen_dir.exists():
        return False
    return len(list(gen_dir.glob("*_generated.jsonl"))) > 0


def run_frame(scene_id: str, frame_id: int) -> dict:
    t0 = time.perf_counter()
    cmd = [
        PYTHON, str(PIPELINE),
        "--plan", "generate",
        "--scene-id", scene_id,
        "--frame-id", str(frame_id),
        "--artifact-root", str(OUTPUTS_ROOT),
        "--seed", str(SEED),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(PIPELINE.parent),
        capture_output=True,
        text=True,
        timeout=1800,  # 30 min — large frames (scene-0101) can take 500+ seconds
    )
    elapsed = time.perf_counter() - t0
    return {
        "returncode": result.returncode,
        "elapsed_s": round(elapsed, 2),
        "stdout_tail": result.stdout[-500:] if result.stdout else "",
        "stderr_tail": result.stderr[-500:] if result.stderr else "",
    }


def main():
    parser = argparse.ArgumentParser(description="Batch generate for all frames")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=-1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    frames = discover_frames()
    total = len(frames)
    print(f"[batch] Discovered {total} frame directories", flush=True)

    end = args.end if args.end > 0 else total
    frames = frames[args.start:end]
    print(f"[batch] Processing [{args.start}:{end}] = {len(frames)} frames", flush=True)

    if args.dry_run:
        skipped = sum(1 for _, _, d in frames if is_already_done(d))
        print(f"[batch] DRY RUN: {skipped} done, {len(frames)-skipped} pending")
        return

    # Pre-flight: ensure Neo4j is up
    print("[batch] Pre-flight Neo4j check...", flush=True)
    if not wait_for_neo4j():
        print("[batch] FATAL: Neo4j not available after all retries. Exiting.", flush=True)
        sys.exit(1)

    done_count = 0
    skip_count = 0
    fail_count = 0
    consecutive_fails = 0
    total_elapsed = 0
    start_time = time.time()

    for i, (scene_id, frame_id, frame_dir) in enumerate(frames):
        idx = args.start + i
        tag = f"[{idx+1}/{end}]"

        if not args.force and is_already_done(frame_dir):
            skip_count += 1
            if skip_count <= 3 or skip_count % 200 == 0:
                print(f"{tag} SKIP {scene_id}_frame{frame_id}", flush=True)
            continue

        # If too many consecutive fails, Neo4j might be down → pause & reconnect
        if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
            print(
                f"[batch] {consecutive_fails} consecutive failures detected. "
                f"Waiting for Neo4j recovery...",
                flush=True
            )
            if not wait_for_neo4j():
                print("[batch] FATAL: Neo4j not recoverable. Stopping.", flush=True)
                break
            consecutive_fails = 0
            print("[batch] Neo4j recovered. Resuming.", flush=True)

        try:
            result = run_frame(scene_id, frame_id)
        except subprocess.TimeoutExpired:
            fail_count += 1
            consecutive_fails += 1
            print(f"{tag} TIMEOUT {scene_id}_frame{frame_id}", flush=True)
            continue
        except Exception as exc:
            fail_count += 1
            consecutive_fails += 1
            print(f"{tag} ERROR {scene_id}_frame{frame_id}: {exc}", flush=True)
            continue

        if result["returncode"] == 0:
            done_count += 1
            consecutive_fails = 0
            total_elapsed += result["elapsed_s"]
            avg = total_elapsed / done_count
            remaining = len(frames) - i - 1
            eta_m = (avg * remaining) / 60
            if done_count <= 5 or done_count % 50 == 0 or result["elapsed_s"] > 30:
                print(
                    f"{tag} OK {scene_id}_frame{frame_id} "
                    f"{result['elapsed_s']:.1f}s "
                    f"(done={done_count} skip={skip_count} fail={fail_count} "
                    f"avg={avg:.1f}s ETA={eta_m:.0f}min)",
                    flush=True,
                )
        else:
            fail_count += 1
            consecutive_fails += 1
            # Only print first few fails to avoid log spam
            if consecutive_fails <= 3:
                err = result["stderr_tail"].strip().split("\n")[-1] if result["stderr_tail"] else ""
                print(f"{tag} FAIL {scene_id}_frame{frame_id} {err[:100]}", flush=True)

    wall = time.time() - start_time
    print(
        f"\n[batch] FINISHED in {wall/60:.1f}min: "
        f"done={done_count} skip={skip_count} fail={fail_count}",
        flush=True,
    )


if __name__ == "__main__":
    main()
