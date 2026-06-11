#!/usr/bin/env python3
"""
run_rq_experiment.py — RQ2/3 正式实验全流程入口

=== 实验流程 ===

  Phase 1 — Baseline 注入
    读取 NuScenes-QA 原题，写入 Table A（raw_coverage.csv）的初始状态
    将其拓扑指纹标记进 CoverageTracker，使增量生成只针对真正缺口

  Phase 2 — 增量 QA 生成 (V6 pipeline)
    使用 qwen-plus + batch(6) + workers(3) 生成 L2A/L2B 路径缺口题
    每 10 题打一次覆盖率快照 → coverage_snapshots.csv
    写入 Table B (question-answer-our.csv)
    写入 Table A 增量行（我们生成的题）

  Phase 3 — MUT 评测 (RQ3)
    并行调用 qwen-plus / glm-4-air（纯文本消融）
    写入 Table C (model_performance_raw_our.csv)

  输出目录结构（--out-dir 指定，默认 output/rq_experiment/）：
    raw_coverage.csv           ← Table A (含 baseline + our_gen)
    question-answer-our.csv   ← Table B
    model_performance_raw_our.csv ← Table C
    coverage_snapshots.csv     ← 每 10 题的 L0/L1/L2A/L2B 覆盖率曲线

=== 典型调用 ===

  # 完整流程（无 baseline 文件时跳过 Phase 1）
  python run_rq_experiment.py \\
    --scene-name scene-0553 --frame-idx 8 \\
    --l2a-cells 25 --l2b-cells 25 \\
    --out-dir output/rq_experiment

  # 附 baseline 文件
  python run_rq_experiment.py \\
    --baseline output/qa_generated/scene-0553_frame8_qa_full.json \\
    --l2a-cells 50 --l2b-cells 50

  # 仅评测已有结果（跳过生成阶段）
  python run_rq_experiment.py --skip-gen \\
    --qa-json output/rq_experiment/pilot_50paths.json
"""
from __future__ import annotations

import argparse, json, logging, pathlib, sys, time
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent))
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("run_rq_experiment")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Baseline injection
# ─────────────────────────────────────────────────────────────────────────────

def phase1_baseline(
    tracker,
    baseline_file: Optional[str],
    scene_name:    str,
    frame_id:      int,
    out_dir:       pathlib.Path,
) -> int:
    """Load NuScenes-QA baseline, mark coverage, write Table A baseline rows."""
    from rq_tables import build_table_a_row, write_table_a

    if not baseline_file:
        logger.info("Phase 1: No baseline file — skipping.")
        return 0

    bl_path = pathlib.Path(baseline_file)
    if not bl_path.exists():
        logger.warning("Baseline file not found: %s", bl_path)
        return 0

    logger.info("Phase 1: Loading baseline from %s ...", bl_path.name)
    stats = tracker.load_nuscenes_qa_baseline(str(bl_path), scene_name)
    logger.info("  Baseline coverage: %s", tracker.stats())

    # Write Table A rows for baseline questions
    data = json.loads(bl_path.read_text(encoding="utf-8"))
    questions = data.get("questions") or data.get("qa_pairs", [])
    table_a = out_dir / "raw_coverage.csv"
    n = 0
    for i, q in enumerate(questions):
        if scene_name and q.get("scene_name","") != scene_name:
            continue
        # Build a pseudo-QA dict
        qa_stub = {
            "question_id":    q.get("question_id", q.get("id", f"bl_{i}")),
            "topology_level": q.get("topology_level", "L1"),
            "path_pattern":   q.get("path_pattern", ""),
            "footprint_nodes": list(set(
                [q.get("cell_info",{}).get("src_id",""),
                 q.get("cell_info",{}).get("tgt_id","")]
            )),
        }
        row = build_table_a_row(qa_stub, scene_name, frame_id, source="nuscenes_qa")
        row["nuscenes_qa_id"] = qa_stub["question_id"]
        mode = "w" if (i == 0 and n == 0) else "a"
        write_table_a(row, table_a, mode=mode)
        n += 1

    logger.info("Phase 1 done: %d baseline questions written to Table A.", n)
    return n


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: Incremental generation
# ─────────────────────────────────────────────────────────────────────────────

def phase2_generate(
    tracker,
    neo4j_uri:   str,
    neo4j_user:  str,
    neo4j_pwd:   str,
    scene_name:  str,
    frame_id:    int,
    l2a_cells:   int,
    l2b_cells:   int,
    out_dir:     pathlib.Path,
    batch_size:  int = 6,
    n_workers:   int = 3,
) -> tuple:
    """Run V6 incremental generation, write Table A/B + coverage snapshots."""
    from run_gap_pipeline_v6 import run_v6_pipeline
    from rq_tables import (write_all_tables, CoverageSnapshotter,
                            build_table_a_row, write_table_a)
    from gap_pipeline.config import LLM_CONFIG

    logger.info("Phase 2: Incremental generation (%d L2A + %d L2B)...", l2a_cells, l2b_cells)

    # Snapshot file
    snap_path = out_dir / "coverage_snapshots.csv"
    snapper   = CoverageSnapshotter(tracker, snap_path, step_size=10)

    result = run_v6_pipeline(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_pwd,
        l2a_cells=l2a_cells,
        l2b_cells=l2b_cells,
        scene_name=scene_name,
        frame_idx=frame_id,
        output_path=str(out_dir / "pilot_paths.json"),
        csv_path=str(out_dir / "rq1_pilot.csv"),
        debug_log=str(out_dir / "pipeline_debug.log"),
        batch_size=batch_size,
        n_workers=n_workers,
    )

    qa_pairs = result.get("qa_pairs", [])
    timings  = result.get("cell_timings", [])

    # Step through snapshots
    for qa in qa_pairs:
        tracker.record_from_qa(qa)
        snapper.step(qa)
    snapper.flush()

    # Write Table A + B
    write_all_tables(
        qa_pairs=qa_pairs,
        timings=timings,
        scene_id=scene_name,
        frame_id=frame_id,
        out_dir=out_dir,
        llm_model=LLM_CONFIG.get("model", "qwen-plus"),
    )

    logger.info("Phase 2 done: %d QAs generated.", len(qa_pairs))
    return qa_pairs, timings, result


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3: MUT evaluation
# ─────────────────────────────────────────────────────────────────────────────

def phase3_mut_eval(
    qa_pairs:   list,
    scene_name: str,
    frame_id:   int,
    out_dir:    pathlib.Path,
    sample_n:   int = 50,
    n_workers:  int = 4,
) -> None:
    """Run MUT evaluation on a sample of generated QA pairs."""
    from run_mut_evaluation import run_mut_evaluation

    qa_path = out_dir / "_mut_eval_input.json"
    qa_path.write_text(json.dumps({"qa_pairs": qa_pairs}, ensure_ascii=False),
                       encoding="utf-8")

    logger.info("Phase 3: MUT evaluation on %d QA (sample=%d)...",
                len(qa_pairs), min(sample_n, len(qa_pairs)))
    run_mut_evaluation(
        qa_json_path=str(qa_path),
        out_csv=str(out_dir / "model_performance_raw_our.csv"),
        scene_id=scene_name,
        frame_id=frame_id,
        n_workers=n_workers,
        sample_n=sample_n,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

def print_experiment_summary(
    out_dir:     pathlib.Path,
    n_baseline:  int,
    n_generated: int,
    t_total:     float,
) -> None:
    SEP = "═" * 65
    print(f"\n{SEP}")
    print("  RQ2/3 Experiment Summary")
    print(SEP)
    print(f"\n  Baseline questions:  {n_baseline}")
    print(f"  Generated QA pairs: {n_generated}")
    print(f"  Total experiment time: {t_total:.0f}s")
    print(f"\n  Output files:")
    for fname in ["raw_coverage.csv", "question-answer-our.csv",
                  "model_performance_raw_our.csv", "coverage_snapshots.csv",
                  "pilot_paths.json", "rq1_pilot.csv"]:
        p = out_dir / fname
        if p.exists():
            size = p.stat().st_size // 1024
            print(f"    {fname:<42} {size:>5} KB")
        else:
            print(f"    {fname:<42}  (not generated)")
    print(f"\n{SEP}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="RQ2/3 Experiment — full pipeline")
    p.add_argument("--neo4j-uri",      default="bolt://localhost:7800")
    p.add_argument("--neo4j-user",     default="neo4j")
    p.add_argument("--neo4j-password", default="87017563")
    p.add_argument("--scene-name",     default="scene-0553")
    p.add_argument("--frame-idx",      type=int, default=8)
    p.add_argument("--baseline",       default=None,
                   help="NuScenes-QA JSON for Phase 1 baseline")
    p.add_argument("--l2a-cells",      type=int, default=25)
    p.add_argument("--l2b-cells",      type=int, default=25)
    p.add_argument("--batch-size",     type=int, default=6)
    p.add_argument("--workers",        type=int, default=3)
    p.add_argument("--mut-workers",    type=int, default=4)
    p.add_argument("--mut-sample",     type=int, default=50,
                   help="How many QAs to evaluate with MUT (0=all)")
    p.add_argument("--out-dir",        default="output/rq_experiment")
    p.add_argument("--skip-gen",       action="store_true",
                   help="Skip Phase 2 (use existing pilot_paths.json)")
    p.add_argument("--skip-mut",       action="store_true",
                   help="Skip Phase 3 MUT evaluation")
    p.add_argument("--qa-json",        default=None,
                   help="Existing QA JSON for --skip-gen mode")
    p.add_argument("--log-level", choices=["DEBUG","INFO","WARNING"], default="INFO")
    args = p.parse_args()

    logging.getLogger().setLevel(args.log_level)
    for noisy in ("neo4j","neo4j.io","neo4j.pool","httpx","urllib3","openai","httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t_exp_start = time.perf_counter()

    logger.info("=== RQ Experiment Start ===  out=%s", out_dir)

    # Init CoverageTracker
    from neo4j import GraphDatabase  # type: ignore[import]
    from gap_pipeline.coverage_tracker import CoverageTracker
    driver  = GraphDatabase.driver(args.neo4j_uri,
                                   auth=(args.neo4j_user, args.neo4j_password))
    tracker = CoverageTracker()
    with driver.session() as sess:
        tracker.init_from_session(sess)
    driver.close()
    logger.info("Tracker: %s", tracker.stats())

    # Phase 1: Baseline
    n_baseline = phase1_baseline(
        tracker, args.baseline, args.scene_name, args.frame_idx, out_dir
    )

    # Phase 2: Generation
    if not args.skip_gen:
        qa_pairs, timings, result = phase2_generate(
            tracker=tracker,
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_pwd=args.neo4j_password,
            scene_name=args.scene_name,
            frame_id=args.frame_idx,
            l2a_cells=args.l2a_cells,
            l2b_cells=args.l2b_cells,
            out_dir=out_dir,
            batch_size=args.batch_size,
            n_workers=args.workers,
        )
    else:
        qa_json = args.qa_json or str(out_dir / "pilot_paths.json")
        data = json.loads(pathlib.Path(qa_json).read_text(encoding="utf-8"))
        qa_pairs = data.get("qa_pairs", []) if isinstance(data, dict) else data
        timings  = data.get("cell_timings", []) if isinstance(data, dict) else []
        logger.info("Phase 2 skipped. Loaded %d QAs from %s", len(qa_pairs), qa_json)

    # Phase 3: MUT evaluation
    if not args.skip_mut and qa_pairs:
        phase3_mut_eval(
            qa_pairs=qa_pairs,
            scene_name=args.scene_name,
            frame_id=args.frame_idx,
            out_dir=out_dir,
            sample_n=args.mut_sample,
            n_workers=args.mut_workers,
        )

    t_total = time.perf_counter() - t_exp_start
    print_experiment_summary(out_dir, n_baseline, len(qa_pairs), t_total)


if __name__ == "__main__":
    main()
