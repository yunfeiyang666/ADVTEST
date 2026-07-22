#!/usr/bin/env python3
"""
RQ2 Random Budget-Matched — Self-contained launcher.

Place this file ANYWHERE inside the experiment directory.
It finds its own location and resolves all paths relative to itself.
No env vars needed, no CWD games, no Neo4j dependency.

Usage:
    python3 rq2_run.py                     # 3 workers (default)
    WORKERS=4 python3 rq2_run.py           # 4 workers

Run in tmux/screen/nohup so workers survive disconnection:
    nohup python3 rq2_run.py > rq2_run.log 2>&1 &
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess  # noqa: S404
import sys
from pathlib import Path


# ── Root: wherever this file sits ────────────────────────────
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FILTERED_SG = ROOT / "filtered_scene_graphs"
OUTPUTS = ROOT / "outputs"
CODE = ROOT / "code"
RUNNER = CODE / "run_random_budget_matched_experiment.py"
PIPELINE = CODE / "run_gap_pipeline_v7.py"
STATS = OUTPUTS / "all_frames_stats.csv"

RUN_ID = "rq2-random-budget-matched-s42-v1"
SEED = 42
WORKERS = int(os.environ.get("WORKERS", "3"))
TOTAL_FRAMES = 5767


def main() -> int:
    os.chdir(ROOT)
    print(f"[rq2] Dir:      {ROOT}")
    print(f"[rq2] Workers:  {WORKERS}")

    # ── Step 1: Ensure scene graphs are in artifacts dir ──────
    print(f"[rq2] Pre-copy scene graphs...")
    copied = 0
    for sg_file in sorted(FILTERED_SG.glob("*.json")):
        stem = sg_file.stem                       # scene-0796_frame0_scene_graph
        fkey = stem.replace("_scene_graph", "")   # scene-0796_frame0
        scene, frame = fkey.split("_frame", 1)
        dst = (
            OUTPUTS / f"{scene}_frame{frame}"
            / "offline" / "scene_graphs"
            / f"{scene}_frame{frame}_filtered_scene_graph.json"
        )
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sg_file, dst)
            copied += 1
    print(f"[rq2]   Copied {copied} scene graphs to artifacts")

    # ── Step 2: Count remaining frames ────────────────────────
    remaining = []
    with open(STATS, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sf = row["scene_frame"]
            budget = int(row["generated_questions"])
            summary = (
                OUTPUTS / sf / "random_fixed_budget" / RUN_ID
                / f"seed_{SEED}" / "summary.json"
            )
            done = False
            if summary.is_file():
                try:
                    p = json.loads(summary.read_text(encoding="utf-8"))
                    done = (
                        int(p.get("draws", 0)) == budget
                        and p.get("budget_exhausted")
                    )
                except Exception:
                    pass
            if not done:
                remaining.append(sf)

    done_count = TOTAL_FRAMES - len(remaining)
    print(f"[rq2] Total:    {TOTAL_FRAMES}")
    print(f"[rq2] Done:     {done_count}")
    print(f"[rq2] To do:    {len(remaining)}")

    if not remaining:
        print("[rq2] All frames complete!")
        return 0

    # ── Step 3: Split remaining frames across workers ────────
    chunks = [remaining[i::WORKERS] for i in range(WORKERS)]
    run_root = ROOT / "scratch" / "rq2_random_budget_matched" / "formal-s42-v1"
    workers_dir = run_root / "workers"
    run_root.mkdir(parents=True, exist_ok=True)
    workers_dir.mkdir(exist_ok=True)

    for i, chunk in enumerate(chunks):
        if not chunk:
            continue
        csv_path = workers_dir / f"chunk_{i:02d}_{len(chunk)}_frames.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["scene_frame"])
            for sf in chunk:
                w.writerow([sf])

    # ── Step 4: Launch detached workers ───────────────────────
    python = sys.executable
    workers_launched = 0
    for i, chunk in enumerate(chunks):
        if not chunk:
            continue
        chunk_csv = workers_dir / f"chunk_{i:02d}_{len(chunk)}_frames.csv"
        wr = run_root / f"worker_{i:02d}"
        wr.mkdir(exist_ok=True)
        log = wr / "worker.log"

        cmd = [
            str(python), "-u", str(RUNNER),
            "--outputs-root", str(OUTPUTS),
            "--stats", str(chunk_csv),
            "--run-root", str(wr),
            "--random-run-id", RUN_ID,
            "--seeds", str(SEED),
            "--python", str(python),
            "--pipeline", str(PIPELINE),
            "--checkpoint-interval", "50000",
            "--continue-on-error",
        ]

        env = os.environ.copy()
        env["ADVTEST_USE_NEO4J"] = "false"
        env["NEO4J_URI"] = ""

        proc = subprocess.Popen(
            cmd,
            stdout=open(log, "w"),
            stderr=subprocess.STDOUT,
            cwd=str(ROOT),
            env=env,
            start_new_session=True,  # survive terminal disconnect
        )
        print(f"[rq2]   Worker {i}: {len(chunk)} frames → PID {proc.pid}")
        workers_launched += 1

    print(f"[rq2] Launched {workers_launched} workers")
    print(f"[rq2]   Logs: {run_root}/worker_0*/worker.log")
    print(f"[rq2]   GPU:  nvidia-smi --query-gpu=name,memory.used --format=csv -l 5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
