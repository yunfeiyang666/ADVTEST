#!/usr/bin/env python3
"""
ADVTEST VQA Pipeline — 单进程快速批量执行 (替代 run_batch.sh)

优化点:
  - NuScenes 只加载一次 (~20s)，后续帧复用缓存
  - 单进程内串行处理，避免每帧重启 Python 的开销
  - 自动跳过已完成的帧 (断点续传)
  - Phase 1 离线: ~3-5s/帧 (比 shell 版 60s/帧快 12-20 倍)
  - Phase 2 生成: 与 shell 版相当 (~10-90s/帧 取决于节点数)

用法:
  python run_batch_fast.py plans/plan_B_remote1.json
  python run_batch_fast.py plans/plan_B_remote1.json --start 22   # 从第22帧开始(0-indexed)
  python run_batch_fast.py plans/plan_B_remote1.json --phase 2    # 只跑 Phase 2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# ── 加载环境 ──
def _load_env():
    env_file = Path(__file__).resolve().parent.parent / "advtest_runtime.env"  # official_pipeline/advtest_runtime.env
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)

_load_env()

# ── 预热 NuScenes (Phase 1 核心优化) ──
def _warmup_nuscenes():
    """在 Phase 1 开始前预加载 NuScenes 句柄，后续所有帧复用。"""
    here = Path(__file__).resolve().parent         # official_pipeline/code/
    official_root = here.parent                     # official_pipeline/
    for p in [str(official_root / "_archive"), str(official_root.parent)]:
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        from v17_onthefly_sg import _get_generator
        t0 = time.time()
        print(f"[batch] 预加载 NuScenes...", flush=True)
        _get_generator()
        print(f"[batch] NuScenes 加载完成 ({time.time()-t0:.1f}s)", flush=True)
        return True
    except Exception as exc:
        print(f"[batch] WARNING NuScenes 预加载失败 ({exc})，每帧将单独加载", flush=True)
        return False


# ── 导入 pipeline 函数 ──
from run_gap_pipeline_v7 import (
    load_frame_from_plan,
    resolve_scene_graph_path,
    generate_scene_graph_from_legacy,
    resolve_initial_qa_paths,
    plan_prepare_scene_graph,
    plan_prepare_initial_coverage,
    run_neo4j,
    V7ArtifactPaths,
)


def _is_phase1_done(output_root: Path, scene_id: str, frame_id: str) -> bool:
    arts = V7ArtifactPaths(output_root, scene_id=scene_id, frame_id=frame_id)
    return arts.filtered_scene_graph.exists() and arts.initial_coverage_file.exists()


def _is_phase2_done(output_root: Path, scene_id: str, frame_id: str) -> bool:
    gen_dir = output_root / f"{scene_id}_frame{frame_id}" / "generation" / "qa"
    return any(gen_dir.glob(f"*_generated.csv")) if gen_dir.exists() else False


def run_phase1_frame(plan_file: Path, frame_index: int, output_root: Path, concurrency: int) -> dict:
    """单帧离线处理: scene_graph + initial_coverage"""
    frame_meta = load_frame_from_plan(plan_file, frame_index=frame_index)
    scene_id = str(frame_meta["scene_id"])
    frame_id = str(frame_meta["frame_id"])

    # 跳过已完成
    if _is_phase1_done(output_root, scene_id, frame_id):
        return {"status": "skipped", "scene_id": scene_id, "frame_id": frame_id}

    # 解析场景图来源
    scene_graph_source = None
    try:
        scene_graph_source = resolve_scene_graph_path(frame_meta, plan_file)
    except (FileNotFoundError, ValueError):
        scene_graph_source = generate_scene_graph_from_legacy(frame_meta, plan_file)

    # prepare_scene_graph
    plan_prepare_scene_graph(
        output_root, scene_id=scene_id, frame_id=frame_id,
        gap_limit=0, scene_graph_source=scene_graph_source
    )

    # prepare_initial_coverage
    initial_qa = list(resolve_initial_qa_paths(frame_meta, plan_file))
    use_llm = os.environ.get("ADVTEST_INITIAL_COVERAGE_LLM", "false").lower() in ("1", "true", "yes")
    plan_prepare_initial_coverage(
        output_root, scene_id=scene_id, frame_id=frame_id,
        initial_qa=initial_qa, use_llm=use_llm, concurrency=concurrency
    )

    return {"status": "ok", "scene_id": scene_id, "frame_id": frame_id}


def run_phase2_frame(plan_file: Path, frame_index: int, output_root: Path) -> dict:
    """单帧在线生成"""
    frame_meta = load_frame_from_plan(plan_file, frame_index=frame_index)
    scene_id = str(frame_meta["scene_id"])
    frame_id = str(frame_meta["frame_id"])

    # 跳过已完成
    if _is_phase2_done(output_root, scene_id, frame_id):
        return {"status": "skipped", "scene_id": scene_id, "frame_id": frame_id}

    output_dir = output_root / f"{scene_id}_frame{frame_id}" / "generation" / "qa"
    run_neo4j(output_dir, seed=42, artifact_root=output_root, scene_id=scene_id, frame_id=frame_id, use_llm=False)

    return {"status": "ok", "scene_id": scene_id, "frame_id": frame_id}


def main():
    parser = argparse.ArgumentParser(description="ADVTEST VQA fast batch runner")
    parser.add_argument("plan_file", help="Path to plan JSON file")
    parser.add_argument("--start", type=int, default=0, help="Start frame index (0-indexed)")
    parser.add_argument("--end", type=int, default=None, help="End frame index (exclusive)")
    parser.add_argument("--phase", type=int, default=0, help="Only run phase 1 or 2 (0=both)")
    parser.add_argument("--concurrency", type=int, default=4, help="LLM concurrency")
    parser.add_argument("--output-root", default=None, help="Output directory")
    args = parser.parse_args()

    plan_file = Path(args.plan_file)
    plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
    total = plan_data.get("frame_count", len(plan_data.get("frames", [])))
    start = args.start
    end = args.end or total
    output_root = Path(args.output_root) if args.output_root else Path(__file__).resolve().parent.parent.parent / "outputs"
    output_root.mkdir(parents=True, exist_ok=True)

    log_file = output_root / f"batch_fast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    def log(msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    log(f"═══ ADVTEST VQA Fast Batch ═══")
    log(f"Plan: {plan_file} | Frames: {start}-{end}/{total} | Phase: {'both' if args.phase == 0 else args.phase}")

    run_phase1 = args.phase in (0, 1)
    run_phase2 = args.phase in (0, 2)

    # ════════ Phase 1: 离线处理 ════════
    if run_phase1:
        log(f"")
        log(f"╔══════════════════════════════════════════════════╗")
        log(f"║  PHASE 1: OFFLINE (scene_graph + initial_cov)   ║")
        log(f"╚══════════════════════════════════════════════════╝")

        # 预热 NuScenes
        _warmup_nuscenes()

        ok, fail, skip = 0, 0, 0
        t0 = time.time()

        for i in range(start, end):
            frame_t0 = time.time()
            elapsed = time.time() - t0
            done = i - start
            rate = f"{elapsed/done:.1f}s/frame" if done > 0 else "..."
            eta = f"{(end - i) * elapsed / done / 60:.0f}min" if done > 0 else "..."

            try:
                result = run_phase1_frame(plan_file, i, output_root, args.concurrency)
                if result["status"] == "skipped":
                    skip += 1
                    log(f"OFFLINE {i+1}/{total}: {result['scene_id']}_frame{result['frame_id']} SKIPPED (已完成)")
                else:
                    ok += 1
                    dt = time.time() - frame_t0
                    log(f"OFFLINE {i+1}/{total}: {result['scene_id']}_frame{result['frame_id']} OK ({dt:.1f}s) [{rate}, ETA {eta}]")
            except Exception as exc:
                fail += 1
                log(f"OFFLINE {i+1}/{total}: FAILED — {exc}")
                traceback.print_exc()

        phase1_time = time.time() - t0
        log(f"── Phase 1 DONE: OK={ok} SKIP={skip} FAIL={fail} Time={phase1_time:.0f}s ({phase1_time/60:.1f}min) ──")

    # ════════ Phase 2: 在线生成 ════════
    if run_phase2:
        log(f"")
        log(f"╔══════════════════════════════════════════════════╗")
        log(f"║  PHASE 2: GENERATE (gap coverage questions)     ║")
        log(f"╚══════════════════════════════════════════════════╝")

        ok, fail, skip = 0, 0, 0
        t0 = time.time()

        for i in range(start, end):
            frame_t0 = time.time()
            elapsed = time.time() - t0
            done = i - start
            rate = f"{elapsed/done:.1f}s/frame" if done > 0 else "..."
            eta = f"{(end - i) * elapsed / done / 60:.0f}min" if done > 0 else "..."

            try:
                result = run_phase2_frame(plan_file, i, output_root)
                if result["status"] == "skipped":
                    skip += 1
                    log(f"GENERATE {i+1}/{total}: {result['scene_id']}_frame{result['frame_id']} SKIPPED")
                else:
                    ok += 1
                    dt = time.time() - frame_t0
                    log(f"GENERATE {i+1}/{total}: {result['scene_id']}_frame{result['frame_id']} OK ({dt:.1f}s) [{rate}, ETA {eta}]")
            except Exception as exc:
                fail += 1
                log(f"GENERATE {i+1}/{total}: FAILED — {exc}")
                traceback.print_exc()

        phase2_time = time.time() - t0
        log(f"── Phase 2 DONE: OK={ok} SKIP={skip} FAIL={fail} Time={phase2_time:.0f}s ({phase2_time/60:.1f}min) ──")

    log(f"═══ BATCH COMPLETE ═══")


if __name__ == "__main__":
    main()
