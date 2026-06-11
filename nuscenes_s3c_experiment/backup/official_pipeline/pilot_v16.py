#!/usr/bin/env python3
"""
pilot_v16.py — V16 性能革命首测 (10 条记录)
==============================================
对比指标：
  V15  : 每条问题独立 LLM 调用 (串行, N 次 RTT)
  V16  : 所有问题一次批量 LLM 调用 (1 次 RTT)
  并行1: Phase 1 ThreadPoolExecutor 并行约束链耗时

执行前确认：
  ✅ Neo4j bolt://localhost:7800 已导入 scene-0926 frame-20 数据
"""

import sys, pathlib, time, random, json
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent))

NEO4J_URI   = "bolt://localhost:7800"
NEO4J_USER  = "neo4j"
NEO4J_PWD   = "87017563"
SCENE_ID    = "scene-0926"
FRAME_ID    = 20
N_PILOT     = 10   # 测试条数（5 L2B + 5 L2A）
N_WORKERS   = 3    # Phase 1 并行线程数

def _abs_ts() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


def main():
    print("=" * 65)
    print("  pilot_v16.py — V16 性能首测 (10 条)")
    print("=" * 65)

    from neo4j import GraphDatabase
    from gap_pipeline.llm_client import LLMClient
    from gap_pipeline.coverage_tracker import CoverageTracker
    from gap_pipeline.constraint_methods import CumulativeConstraintChain
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from run_gap_pipeline_v6 import _process_single_cell
    from run_method_a import _gen_semantic_question, _Q_TYPE_WEIGHTS

    llm    = LLMClient()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))

    try:
        # ── Step 1: 获取 gap cells ────────────────────────────────────
        tracker = CoverageTracker()
        with driver.session() as sess:
            tracker.init_from_session(sess)

        l2b_pool = tracker.get_gap_cells("L2B")
        l2a_pool = tracker.get_gap_cells("L2A")
        print(f"\n  Gap pool: L2B={len(l2b_pool)}  L2A={len(l2a_pool)}")

        random.shuffle(l2b_pool); random.shuffle(l2a_pool)
        n_b = min(5, len(l2b_pool))
        n_a = min(5, len(l2a_pool))
        pilot_cells = (
            [("L2B", c) for c in l2b_pool[:n_b]] +
            [("L2A", c) for c in l2a_pool[:n_a]]
        )[:N_PILOT]
        print(f"  Pilot sample: {len(pilot_cells)} cells "
              f"(L2B={sum(1 for t,_ in pilot_cells if t=='L2B')}, "
              f"L2A={sum(1 for t,_ in pilot_cells if t=='L2A')})")

        # ── Step 2: 生成 context cyphers ─────────────────────────────
        print("\n  [Step 2] Generating context cyphers...")
        l2a_cells_p  = [c for t, c in pilot_cells if t == "L2A"]
        l2b_cells_p  = [c for t, c in pilot_cells if t == "L2B"]

        t_ctx = time.perf_counter()
        l2a_cyphers = llm.generate_context_cypher_batch(l2a_cells_p, "L2A") if l2a_cells_p else []
        t_ctx_ms = _ms(t_ctx)
        l2b_cyphers = [LLMClient.build_l2b_obj_fallback_cypher(c) for c in l2b_cells_p]

        cypher_map: dict = {}
        ai = bi = 0
        for topo, cell in pilot_cells:
            if topo == "L2A":
                cypher_map[cell["_key"]] = l2a_cyphers[ai] if ai < len(l2a_cyphers) else ""
                ai += 1
            else:
                cypher_map[cell["_key"]] = l2b_cyphers[bi] if bi < len(l2b_cyphers) else ""
                bi += 1
        print(f"  Context cyphers ready  (L2A batch RTT: {t_ctx_ms:.0f}ms)")

        # ── Step 3: Phase 1 — 并行约束链 ─────────────────────────────
        print(f"\n  [Step 3] Parallel constraint chains (workers={N_WORKERS})...")

        def _worker(args):
            _topo, _cell = args
            _cypher = cypher_map.get(_cell["_key"], "")
            _chain  = CumulativeConstraintChain()
            try:
                _qa, _tmg = _process_single_cell(
                    cell=_cell, topology=_topo, cypher=_cypher,
                    driver=driver, chain=_chain,
                    scene_name=SCENE_ID, frame_idx=FRAME_ID,
                    llm_timing={"total_ms": 0, "tok_per_sec": 0, "est_rtt_overhead_ms": 0},
                )
            except Exception as exc:
                return (_topo, _cell, None, None, str(exc))
            return (_topo, _cell, _qa, _tmg, None)

        t_p1 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
            futs = [ex.submit(_worker, item) for item in pilot_cells]
            phase1_raw = [f.result() for f in as_completed(futs)]
        t_p1_ms = _ms(t_p1)

        valid = [(topo, cell, qa, tmg)
                 for topo, cell, qa, tmg, exc in phase1_raw
                 if qa is not None and exc is None]
        n_fail = len(pilot_cells) - len(valid)
        print(f"  Phase 1 parallel done: {len(valid)}/{len(pilot_cells)} valid  "
              f"({n_fail} failed)  elapsed={t_p1_ms:.0f}ms")

        if not valid:
            print("  ❌ 无有效 cell，终止测试")
            return

        # ── Step 4: 构建公共问题生成参数 ──────────────────────────────
        q_type_pool: list = []
        for qt, wt in _Q_TYPE_WEIGHTS.items():
            q_type_pool.extend([qt] * wt)
        random.shuffle(q_type_pool)

        common_inputs = []
        for i, (topo, cell, qa, tmg) in enumerate(valid):
            qt = q_type_pool[i % len(q_type_pool)]
            ctx_tmpl = {k: cell.get(k, "") for k in
                        ("n1_id","n1_type","n2_type","n3_id",
                         "n3_type","n3_status",
                         "r1_dir4","r1_dir8","r2_dir4","r2_dir8")}
            fb_q, answer = _gen_semantic_question(qt, ctx_tmpl, topo)
            common_inputs.append({
                "topo": topo, "cell": cell, "qa": qa, "tmg": tmg,
                "q_type": qt, "answer": answer, "fallback": fb_q,
            })

        # ── Step 5: V15 基线 — 串行 LLM 问题生成 ─────────────────────
        print(f"\n  [V15] Serial question generation ({len(valid)} calls)...")
        v15_qs = []
        v15_per_call_ms = []
        t_v15 = time.perf_counter()
        for inp in common_inputs:
            cell = inp["cell"]
            t0 = time.perf_counter()
            q = llm.generate_question_nlp(
                path=cell.get("path_pattern", "?"),
                q_type=inp["q_type"],
                n1_id=cell.get("n1_id",""),   n1_type=cell.get("n1_type",""),
                n2_id=cell.get("n2_id",""),   n2_type=cell.get("n2_type",""),
                n3_id=cell.get("n3_id",""),   n3_type=cell.get("n3_type",""),
                n3_status=cell.get("n3_status",""),
                r1_dir=cell.get("r1_dir8") or cell.get("r1_dir4","front"),
                r2_dir=cell.get("r2_dir8") or cell.get("r2_dir4","front"),
                constraint_desc="path uniqueness",
                answer=str(inp["answer"]),
                fallback=inp["fallback"],
            )
            t1 = time.perf_counter()
            call_ms = (t1 - t0) * 1000
            v15_per_call_ms.append(call_ms)
            v15_qs.append(q)
            print(f"    [{len(v15_qs):2d}] {call_ms:6.0f}ms  {q[:60]}")
        t_v15_total = _ms(t_v15)

        # ── Step 6: V16 批量 — 一次 LLM 调用 ────────────────────────
        print(f"\n  [V16] Batch question generation (1 call, {len(valid)} questions)...")
        batch_inputs = []
        for inp in common_inputs:
            cell = inp["cell"]
            batch_inputs.append({
                "q_type":    inp["q_type"],
                "n1_id":     cell.get("n1_id",""),
                "n1_type":   cell.get("n1_type",""),
                "n2_id":     cell.get("n2_id",""),
                "n2_type":   cell.get("n2_type",""),
                "n3_id":     cell.get("n3_id",""),
                "n3_type":   cell.get("n3_type",""),
                "n3_status": cell.get("n3_status",""),
                "r1_dir":    cell.get("r1_dir8") or cell.get("r1_dir4","front"),
                "r2_dir":    cell.get("r2_dir8") or cell.get("r2_dir4","front"),
                "answer":    str(inp["answer"]),
                "fallback":  inp["fallback"],
            })

        t_v16 = time.perf_counter()
        v16_qs = llm.generate_questions_batch(batch_inputs)
        t_v16_total = _ms(t_v16)

        rtt_ms      = llm.last_call_timing.get("est_rtt_overhead_ms", 0)
        rtt_pct     = llm.last_call_timing.get("est_rtt_pct", 0)
        tok_per_sec = llm.last_call_timing.get("tok_per_sec", 0)

        for i, q in enumerate(v16_qs):
            print(f"    [{i+1:2d}] {q[:65]}")

        # ── Step 7: 对比摘要 ──────────────────────────────────────────
        n = len(valid)
        speedup      = t_v15_total / max(t_v16_total, 1.0)
        rtt_saved    = rtt_ms * max(n - 1, 0)
        avg_v15_call = sum(v15_per_call_ms) / max(n, 1)

        print(f"\n{'='*65}")
        print(f"  V16 性能对比摘要 (N={n} 条问题)")
        print(f"{'='*65}")
        print(f"  Phase 1 并行约束链耗时  : {t_p1_ms:>8.0f} ms  "
              f"(vs 串行估算 ≈ {t_p1_ms * N_WORKERS:.0f} ms)")
        print(f"  V15 串行 LLM 总耗时     : {t_v15_total:>8.0f} ms  "
              f"(均值 {avg_v15_call:.0f} ms/call)")
        print(f"  V16 批量 LLM 总耗时     : {t_v16_total:>8.0f} ms  "
              f"(单次批量)")
        print(f"  问题生成加速比          : {speedup:>8.2f} x")
        print(f"  RTT 占批量时间          : {rtt_pct:>7.0f} %  ({rtt_ms:.0f} ms)")
        print(f"  已压缩 RTT 开销         : {rtt_saved:>8.0f} ms  ({n-1} 个 RTT)")
        print(f"  LLM 生成速度            : {tok_per_sec:>7.0f} tok/s")
        print(f"{'='*65}")
        print(f"\n  V16 问题生成 vs V15: {speedup:.1f}x 加速")
        print(f"  (Phase 1 并行约束链可节约 Neo4j 串行等待)")
        print(f"{'='*65}")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
