#!/usr/bin/env python3
"""
run_gap_pipeline_v3.py — V3 拓扑路径缺口驱动的 QA 生成管线

与 V2 的根本区别
─────────────────
  V2: Step 4 从 Neo4j 枚举所有有向边，把"边"作为 gap 基本单元，
      然后用 constraint chain 求解，再按求解方法标注 L1/L2。
      → 错误：`ego→car35` 被标为 L2，仅因求解时借了 car9 作参照。

  V3: Step 4 直接从图谱中枚举两类真实路径：
        L2A: ego→A→B 两连跳锚点链
        L2B: X←ego→Y 双臂交互链
      → 正确：Gap 的等级由图谱拓扑决定，与求解策略无关。
      → 每条 QA 携带 path_pattern + topology_level，
        CoverageTracker 级联更新 L2→L1→L0。

运行示例
─────────
  python run_gap_pipeline_v3.py --l2a-cells 25 --l2b-cells 25 \\
      --scene-name scene-0553 --frame-idx 8 \\
      --output output/pilot_50paths_v3.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_gap_pipeline_v3")


# =============================================================================
# Helpers
# =============================================================================

def _fmt_stats(stats: Dict) -> str:
    parts = []
    for lvl, d in stats.items():
        parts.append(f"{lvl}: {d['covered']}/{d['total']} ({d['rate']:.1f}%)")
    return "  |  ".join(parts)


# =============================================================================
# Main pipeline
# =============================================================================

def run_v3_pipeline(
    neo4j_uri:      str,
    neo4j_user:     str,
    neo4j_password: str,
    l2a_cells:      int = 25,
    l2b_cells:      int = 25,
    scene_name:     str = "",
    frame_idx:      int = 0,
    output_path:    Optional[str] = None,
) -> Dict[str, Any]:
    """
    V3 pipeline: enumerate topological path gaps, generate chain QA.

    Returns a result dict with qa_pairs, coverage stats, and per-cell timing.
    """
    from neo4j import GraphDatabase  # type: ignore[import]
    from gap_pipeline.coverage_tracker import CoverageTracker
    from gap_pipeline.l2_chain_generator import L2ChainGenerator

    t_start = time.perf_counter()

    # ── Step 0: Connect ──────────────────────────────────────────────────────
    logger.info("Step 0  connecting to Neo4j: %s", neo4j_uri)
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        # ── Step 1: Init CoverageTracker (L0+L1+L2A+L2B) ────────────────────
        logger.info("Step 1  initialising topological CoverageTracker …")
        tracker = CoverageTracker()
        with driver.session() as sess:
            tracker.init_from_session(sess)

        init_stats = tracker.stats()
        logger.info("  CoverageTracker: %s", _fmt_stats(init_stats))

        # ── Step 2: Extract path gaps ────────────────────────────────────────
        logger.info("Step 2  extracting L2A gaps (limit=%d) …", l2a_cells)
        l2a_gaps = tracker.get_gap_cells("L2A", limit=l2a_cells)
        logger.info("  L2A gaps available: %d", len(l2a_gaps))

        logger.info("Step 2  extracting L2B gaps (limit=%d) …", l2b_cells)
        l2b_gaps = tracker.get_gap_cells("L2B", limit=l2b_cells)
        logger.info("  L2B gaps available: %d", len(l2b_gaps))

        all_gaps = l2a_gaps + l2b_gaps
        logger.info("  Total path gaps to process: %d (L2A=%d  L2B=%d)",
                    len(all_gaps), len(l2a_gaps), len(l2b_gaps))

        if not all_gaps:
            logger.warning("No path gaps found — scene may already be fully covered.")
            return {"qa_pairs": [], "coverage": tracker.stats()}

        # ── Step 3: Generate chain QA ────────────────────────────────────────
        logger.info("Step 3  generating chain QA pairs …")
        gen = L2ChainGenerator(scene_name=scene_name, frame_idx=frame_idx)

        all_qa:     List[Dict[str, Any]] = []
        cell_logs:  List[Dict[str, Any]] = []

        for i, cell in enumerate(all_gaps, 1):
            level = cell.get("_level", "?")
            path  = cell.get("path_pattern", "?")
            logger.info("  cell %d/%d  [%s]  %s", i, len(all_gaps), level, path)

            t_cell = time.perf_counter()
            if level == "L2A":
                qa_list = gen.generate_l2a(cell)
            else:
                qa_list = gen.generate_l2b(cell)
            elapsed_ms = (time.perf_counter() - t_cell) * 1_000

            # Record coverage via cascaded update
            for qa in qa_list:
                tracker.record_from_qa(qa)
            all_qa.extend(qa_list)

            cell_logs.append({
                "cell_idx":      i,
                "topology_level": level,
                "path_pattern":  path,
                "n_qa_generated": len(qa_list),
                "gen_ms":        round(elapsed_ms, 2),
            })
            logger.info("    → %d QA pairs generated (%.1f ms)", len(qa_list), elapsed_ms)

        # ── Step 4: Final stats ──────────────────────────────────────────────
        final_stats = tracker.stats()
        total_ms = (time.perf_counter() - t_start) * 1_000

        logger.info("=" * 60)
        logger.info("  V3 Pipeline Complete")
        logger.info("  Total QA pairs  : %d", len(all_qa))
        logger.info("  Total time      : %.1f ms", total_ms)
        logger.info("  Coverage after  : %s", _fmt_stats(final_stats))

        _print_summary(all_qa, final_stats, cell_logs)

        result: Dict[str, Any] = {
            "pipeline_version": "v3",
            "scene_name":       scene_name,
            "frame_idx":        frame_idx,
            "n_l2a_cells":      len(l2a_gaps),
            "n_l2b_cells":      len(l2b_gaps),
            "n_qa_generated":   len(all_qa),
            "total_ms":         round(total_ms, 1),
            "coverage_init":    init_stats,
            "coverage_final":   final_stats,
            "cell_logs":        cell_logs,
            "qa_pairs":         all_qa,
        }

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            logger.info("Result written to: %s", out)

        return result

    finally:
        driver.close()


# =============================================================================
# Console summary
# =============================================================================

def _print_summary(
    all_qa: List[Dict],
    stats:  Dict,
    cell_logs: List[Dict],
) -> None:
    from collections import Counter

    SEP = "─" * 65
    print(f"\n{SEP}")
    print("  Gap Pipeline V3 — 拓扑路径覆盖报告")
    print(SEP)

    # QA breakdown
    topo_cnt = Counter(qa.get("topology_level", "?") for qa in all_qa)
    tmpl_cnt = Counter(qa.get("template_id", "?") for qa in all_qa)
    print(f"\n  总 QA 对数: {len(all_qa)}")
    print(f"  by topology:  L2A={topo_cnt['L2A']}  L2B={topo_cnt['L2B']}")
    print("  by template:")
    for tid, n in tmpl_cnt.most_common():
        print(f"    {tid:<40} {n:>4}")

    # Coverage summary
    print(f"\n  最终覆盖率:")
    for lvl, d in stats.items():
        bar = "#" * int(d["rate"] / 5)
        print(f"    {lvl:5s} {d['covered']:>4}/{d['total']:<6} "
              f"({d['rate']:>5.1f}%)  {bar}")

    # Per-cell table (first 10)
    print(f"\n  前 10 个 gap cell 的生成结果:")
    print(f"  {'idx':>4}  {'level':6}  {'path_pattern':<30}  {'n_qa':>5}  {'ms':>7}")
    print("  " + "─" * 58)
    for cl in cell_logs[:10]:
        print(f"  {cl['cell_idx']:>4}  {cl['topology_level']:6}  "
              f"{cl['path_pattern']:<30}  {cl['n_qa_generated']:>5}  "
              f"{cl['gen_ms']:>7.1f}")
    if len(cell_logs) > 10:
        print(f"  ... ({len(cell_logs)-10} more)")
    print(f"\n{SEP}\n")


# =============================================================================
# CLI
# =============================================================================

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Gap Pipeline V3 — 拓扑路径缺口驱动 QA 生成"
    )
    p.add_argument("--neo4j-uri",      default="bolt://localhost:7800")
    p.add_argument("--neo4j-user",     default="neo4j")
    p.add_argument("--neo4j-password", default="87017563")
    p.add_argument("--l2a-cells", type=int, default=25,
                   help="L2A (ego→A→B) gap cells to process")
    p.add_argument("--l2b-cells", type=int, default=25,
                   help="L2B (X←ego→Y) gap cells to process")
    p.add_argument("--scene-name", default="scene-0553")
    p.add_argument("--frame-idx",  type=int, default=8)
    p.add_argument("--output", default="output/pilot_50paths_v3.json")
    p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING"],
                   default="INFO")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.getLogger().setLevel(args.log_level)
    for noisy in ("neo4j", "neo4j.io", "neo4j.pool", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger.info(
        "Gap Pipeline V3 | L2A=%d  L2B=%d | scene=%s frame=%d",
        args.l2a_cells, args.l2b_cells, args.scene_name, args.frame_idx,
    )
    run_v3_pipeline(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        l2a_cells=args.l2a_cells,
        l2b_cells=args.l2b_cells,
        scene_name=args.scene_name,
        frame_idx=args.frame_idx,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
