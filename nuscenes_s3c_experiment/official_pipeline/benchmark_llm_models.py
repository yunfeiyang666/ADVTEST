#!/usr/bin/env python3
"""
在相同并行度下对比学校网关多模型的速度与「管线可用性」代理指标。

质量代理（非人工 VLM）：Neo4j 上下文 Cypher 能执行且 _process_single_cell 返回非 None，
且 verify_n==1（链上声明唯一时）。

用法（在 official_pipeline 目录，需已配置 VQA_API_KEY、Neo4j 且图内已有 Object）:
  python benchmark_llm_models.py
  python benchmark_llm_models.py --workers 8 --per-model 12

环境变量可与 run_method_a 相同；本脚本会临时改写 gap_pipeline.config.LLM_CONFIG 中的模型名。
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# 默认与运维提供的可用名一致（须与网关 /v1/models 一致）
DEFAULT_MODELS = [
    "Qwen3.5-122B-A10B",
    "Qwen3.5-35B-A3B",
    "Qwen3.5-27B",
]


def _apply_model(model: str) -> None:
    os.environ["VQA_MODEL_NAME"] = model
    os.environ["VQA_MODEL_AUDIT"] = model
    os.environ["VQA_MODEL_RENDER"] = model
    import gap_pipeline.config as gcfg

    gcfg.LLM_CONFIG["model"] = model
    gcfg.LLM_CONFIG["model_audit"] = model
    gcfg.LLM_CONFIG["model_render"] = model


def _meta_to_cell(meta: Dict[str, Any], topology: str) -> Dict[str, Any]:
    d = dict(meta)
    n1, n2, n3 = d["n1_id"], d["n2_id"], d["n3_id"]
    d["path_pattern"] = f"{n1}→{n2}→{n3}"
    d["_key"] = f"{n1}|{n2}|{n3}"
    d["_level"] = topology
    return d


def _pick_cells(tracker, per_model: int) -> List[Tuple[str, Dict[str, Any]]]:
    """从 tracker 取混合 L2A/L2B 样本（优先有代表性的前若干条 meta）。"""
    out: List[Tuple[str, Dict[str, Any]]] = []
    l2a = list(tracker._L2A_meta.values())
    l2b = list(tracker._L2B_meta.values())
    half = max(1, per_model // 2)
    for m in l2a[:half]:
        out.append(("L2A", _meta_to_cell(m, "L2A")))
    for m in l2b[: per_model - len(out)]:
        out.append(("L2B", _meta_to_cell(m, "L2B")))
    while len(out) < per_model and l2b:
        i = len(out) % len(l2b)
        out.append(("L2B", _meta_to_cell(l2b[i], "L2B")))
    return out[:per_model]


def _parse_verify_n(text: str) -> int:
    import re

    m = re.search(r"n=(\d+)", str(text or ""))
    return int(m.group(1)) if m else -1


def main() -> None:
    from advtest_env import load_advtest_env

    load_advtest_env()

    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8, help="并发 worker 数（与 run_method_a 批次接近）")
    ap.add_argument("--per-model", type=int, default=12, help="每个模型跑的 cell 数")
    ap.add_argument(
        "--models",
        type=str,
        default=",".join(DEFAULT_MODELS),
        help="逗号分隔模型名",
    )
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    from neo4j import GraphDatabase
    from gap_pipeline.coverage_tracker import CoverageTracker
    from gap_pipeline.llm_client import LLMClient
    from run_method_a import NEO4J_PWD, NEO4J_URI, NEO4J_USER
    from run_gap_pipeline_v6 import _process_single_cell
    from gap_pipeline.constraint_methods import CumulativeConstraintChain

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))
    tracker = CoverageTracker()
    with driver.session() as sess:
        tracker.init_from_session(sess)
        n_nodes = sess.run("MATCH (n:Object) RETURN count(n) AS c").single()["c"]
    if int(n_nodes or 0) < 2:
        print("[FAIL] Neo4j 中 Object 过少，请先导入场景图（如 run_method_a Step 3）。")
        driver.close()
        sys.exit(1)

    cells = _pick_cells(tracker, args.per_model)
    if len(cells) < 2:
        print("[FAIL] 无法从 CoverageTracker 抽取 L2 样本。")
        driver.close()
        sys.exit(1)

    print(
        f"Benchmark: {len(cells)} cells × {len(models)} models, workers={args.workers}\n"
        f"L2A_total={tracker.stats()['L2A']['total']} L2B_total={tracker.stats()['L2B']['total']}\n"
    )

    results: List[Dict[str, Any]] = []

    for model in models:
        _apply_model(model)
        t0 = time.perf_counter()
        neo_ok = 0
        verify_ok = 0
        chain_unique = 0
        llm_ms_sum = 0.0

        lock = threading.Lock()

        def _job(item: Tuple[str, Dict[str, Any]]) -> None:
            nonlocal neo_ok, verify_ok, chain_unique, llm_ms_sum
            topo, cell = item
            local = LLMClient()
            if topo == "L2A":
                cypher = local.generate_l2a_context_cypher(cell)
            else:
                cypher = local.generate_l2b_obj_context_cypher(cell)
            llm_ms = float(local.last_call_timing.get("total_ms", 0.0))
            chain = CumulativeConstraintChain()
            qa, timing = _process_single_cell(
                cell=cell,
                topology=topo,
                cypher=cypher,
                driver=driver,
                chain=chain,
                scene_name="bench",
                frame_idx=0,
                llm_timing=dict(local.last_call_timing),
                render_local_question=False,
            )
            vn = _parse_verify_n(str(timing.get("logic_verification", "")))
            cu = bool(timing.get("is_unique", False))
            with lock:
                llm_ms_sum += llm_ms
                if qa is not None:
                    neo_ok += 1
                if cu and vn == 1:
                    verify_ok += 1
                if cu:
                    chain_unique += 1

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(_job, c) for c in cells]
            for _ in as_completed(futs):
                pass

        elapsed = time.perf_counter() - t0
        results.append(
            {
                "model": model,
                "wall_s": round(elapsed, 2),
                "neo4j_ok": neo_ok,
                "chain_unique": chain_unique,
                "strict_ok": verify_ok,
                "avg_llm_ms": round(llm_ms_sum / max(len(cells), 1), 1),
            }
        )
        print(
            f"  {model}\n"
            f"    wall={elapsed:.1f}s  neo4j_ok={neo_ok}/{len(cells)}  "
            f"chain_unique={chain_unique}/{len(cells)}  verify_n1={verify_ok}/{len(cells)}  "
            f"avg_llm_ms/cell≈{llm_ms_sum/max(len(cells),1):.0f}\n"
        )

    driver.close()

    # 排序：优先 strict_ok，其次 wall 短
    ranked = sorted(
        results,
        key=lambda r: (-r["strict_ok"], -r["neo4j_ok"], r["wall_s"]),
    )
    print("── 推荐（同并行下：verify 命中优先，其次总耗时短）──")
    for i, r in enumerate(ranked, 1):
        print(
            f"  {i}. {r['model']}  verify_n1={r['strict_ok']}/{len(cells)}  "
            f"neo_ok={r['neo4j_ok']}/{len(cells)}  {r['wall_s']}s"
        )


if __name__ == "__main__":
    main()
