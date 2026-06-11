#!/usr/bin/env python3
"""
pilot_v15_2.py — 10条样板诊断（5基线 + 5生成）

三大病灶修复验证：
  1. 时间戳物理死锁：L2B的ts_llm也独立捕捉（在hardcoded Cypher构建后）
  2. cypher question 字段：raw_coverage增加LLM调用时刻记录
  3. L0/L1/L2真实ID：审计时空间题直接从Neo4j提取物理边

运行：python pilot_v15_2.py
结束后打印10条完整字段，等待用户核验。
"""
import sys, json, uuid, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from datetime import datetime

def _ts() -> str:
    """物理壁钟时间戳，毫秒精度"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

def _dt_ms(a: str, b: str) -> int:
    """两个时间戳的毫秒差"""
    fmt = '%Y-%m-%d %H:%M:%S.%f'
    try:
        return int((datetime.strptime(b, fmt) -
                    datetime.strptime(a, fmt)).total_seconds() * 1000)
    except Exception:
        return -1

SCENE_ID  = "scene-0926"
FRAME_ID  = 20
NEO4J_URI = "bolt://localhost:7800"
NEO4J_USER = "neo4j"
NEO4J_PWD  = "87017563"

TRAINVAL = pathlib.Path("E:/Project/ADVTEST/data/nuscenes/v1.0-trainval")
QA_PATH  = pathlib.Path("E:/Project/ADVTEST/data/nuscenes/qa/NuScenes_val_questions.json")

SEP = "=" * 70

# ─────────────────────────────────────────────────────────────────────────────
# Neo4j helpers
# ─────────────────────────────────────────────────────────────────────────────

def _neo4j_driver():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))


def _fetch_spatial_edges(driver, anchor_id: str) -> list:
    """从Neo4j直接取anchor节点的全部出向边（ID+方向+距离）"""
    with driver.session() as sess:
        rows = sess.run(
            "MATCH (src:Object {unique_id:$a})-[r:RELATES_TO]->(tgt:Object) "
            "RETURN tgt.unique_id AS tgt_id, tgt.type AS tgt_type, "
            "r.direction_8 AS dir8, coalesce(r.predicates[1],'') AS dist",
            a=anchor_id
        )
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# 修复后的 raw_coverage 审计（V15.2）
# ─────────────────────────────────────────────────────────────────────────────

def audit_one_baseline(q: dict, global_idx: int, driver, llm_client,
                       scene_ctx: str) -> dict:
    """
    三病灶修复版审计：
      - 4段时间戳：ts_start / ts_llm / ts_neo4j / ts_end 全部独立捕捉
      - L1 从Neo4j直接查询物理边（不依赖LLM猜ID）
      - cypher_question 写入审计Cypher（JSON子图）
    """
    question = q.get("question", "")
    answer   = q.get("answer", "")
    qtype    = q.get("template_type", "")

    # ── Phase 1 intent extraction: ts_start ─────────────────────────────────
    ts_start = _ts()

    from semantic_auditor import (
        INTENT_EXTRACTION_PROMPT, _parse_subgraph_json,
        AUDIT_PROMPT_TEMPLATE, derive_l2_from_l1,
    )

    # Step A: LLM提取意图（不猜ID）
    intent_prompt = INTENT_EXTRACTION_PROMPT.format(question=question)
    raw_intent = llm_client._call(intent_prompt)
    import re
    intent = {}
    m = re.search(r"\{.*\}", raw_intent, re.DOTALL)
    if m:
        try: intent = json.loads(m.group(0))
        except: pass

    ts_llm = _ts()  # ← 物理断点：LLM意图提取完毕

    # Step B: Neo4j软匹配（±15°）直接拿物理边
    anchor_type = (intent.get("anchor_type") or "ego").lower()
    relation_dir = intent.get("relation_dir") or ""
    target_type  = intent.get("target_type") or "any"

    anchor_id = "ego" if anchor_type == "ego" else ""
    if not anchor_id:
        # 找第一个匹配类型的节点
        with driver.session() as sess:
            row = sess.run(
                "MATCH (n:Object) WHERE n.type=$t RETURN n.unique_id AS id LIMIT 1",
                t=anchor_type
            ).single()
            if row: anchor_id = row["id"]

    # 从Neo4j取真实物理边
    l0_nodes = []
    l1_edges = []
    if anchor_id:
        edges = _fetch_spatial_edges(driver, anchor_id)
        # 方向容差过滤（±22.5° = 相邻扇区）
        _DIR_ADJACENT = {
            "front":      {"front", "front-left", "front-right"},
            "front-left": {"front-left", "front", "left"},
            "left":       {"left", "front-left", "back-left"},
            "back-left":  {"back-left", "left", "back"},
            "back":       {"back", "back-left", "back-right"},
            "back-right": {"back-right", "back", "right"},
            "right":      {"right", "back-right", "front-right"},
            "front-right":{"front-right", "right", "front"},
        }
        allowed_dirs = _DIR_ADJACENT.get(relation_dir, {relation_dir})
        matched = [e for e in edges
                   if e["dir8"] in allowed_dirs
                   and (target_type in ("any", "") or e["tgt_type"] == target_type)]
        if matched:
            l0_nodes = [anchor_id] + [e["tgt_id"] for e in matched]
            l1_edges = [{"source": anchor_id, "target": e["tgt_id"],
                         "relation": e["dir8"]} for e in matched]

    ts_neo4j = _ts()  # ← 物理断点：Neo4j查询完毕

    # Step C: LLM全局子图提取（补充非空间型问题的节点）
    prompt = AUDIT_PROMPT_TEMPLATE.format(
        scene_context=scene_ctx, question=question, q_type=qtype)
    try:
        raw_sg = llm_client._call(prompt)
        sg = _parse_subgraph_json(raw_sg)
        if sg:
            # 合并：Neo4j的物理边 + LLM的子图
            for nid in sg["nodes"]:
                if nid not in l0_nodes:
                    l0_nodes.append(nid)
            for e in sg["edges"]:
                e_key = (e["source"], e["target"])
                if not any((x["source"], x["target"]) == e_key for x in l1_edges):
                    l1_edges.append(e)
    except Exception:
        pass  # LLM失败不影响已有物理结果

    l2_paths = derive_l2_from_l1(l1_edges)

    ts_end = _ts()  # ← 物理断点：全部处理完毕

    audit_json = json.dumps(
        {"nodes": l0_nodes, "edges": l1_edges, "intent": intent},
        ensure_ascii=False
    )

    return {
        "nuscenes_qa_id":  f"val_{global_idx}_{qtype}",
        "question":        question,
        "answer":          answer,
        "question_type":   qtype,
        "l0_nodes":        l0_nodes,
        "l1_edges":        l1_edges,
        "l2_paths":        l2_paths,
        "ts_start":        ts_start,
        "ts_llm":          ts_llm,
        "ts_neo4j":        ts_neo4j,  # 额外断点
        "ts_end":          ts_end,
        "audit_cypher":    audit_json,
        "intent":          intent,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 修复后的 question-answer-our 生成（V15.2）
# ─────────────────────────────────────────────────────────────────────────────

def generate_one_question(cell: dict, topology: str, driver,
                          llm_client, chain, q_type: str) -> dict:
    """
    四段时间戳全部独立物理捕捉（含L2B的ts_llm区分）：
      ts_start   → 处理开始
      ts_llm     → 上下文Cypher就绪（L2A: LLM返回；L2B: hardcoded构建后）
      ts_cypher  → Neo4j+ConstraintChain完毕
      ts_end     → LLM问题生成完毕
    """
    from gap_pipeline.llm_client import LLMClient
    from run_gap_pipeline_v6 import _process_single_cell

    path = cell.get("path_pattern", "?")

    ts_start = _ts()  # ← 物理断点①：处理开始

    # 上下文Cypher获取
    if topology == "L2A":
        cyphers = llm_client.generate_context_cypher_batch([cell], "L2A")
        cypher  = cyphers[0] if cyphers else LLMClient.build_l2a_fallback_cypher(cell)
    else:
        cypher = LLMClient.build_l2b_obj_fallback_cypher(cell)

    ts_llm = _ts()  # ← 物理断点②：上下文Cypher就绪（L2A: LLM完毕；L2B: hardcoded完毕，独立捕捉）

    # Neo4j + ConstraintChain
    llm_timing = {"total_ms": 0, "tok_per_sec": 0, "est_rtt_overhead_ms": 0}
    try:
        qa, timing = _process_single_cell(
            cell=cell, topology=topology, cypher=cypher,
            driver=driver, chain=chain,
            scene_name=SCENE_ID, frame_idx=FRAME_ID,
            llm_timing=llm_timing,
        )
    except Exception as exc:
        print(f"    ❌ {path}: {exc}")
        return {}

    ts_cypher = _ts()  # ← 物理断点③：Neo4j+ConstraintChain完毕

    if qa is None:
        return {}

    # iteration_count 从 trace 真实计算
    trace = timing.get("constraint_trace", "")
    trace_methods = [p for p in trace.split("→") if p and p != "Path"]
    iteration_count = max(1, len(trace_methods))

    # 选q_type fallback问题
    from run_method_a import _gen_semantic_question
    ctx_tmpl = {k: cell.get(k, "") for k in
                ("n1_id","n1_type","n2_type","n3_id","n3_type","n3_status",
                 "r1_dir4","r1_dir8","r2_dir4","r2_dir8")}
    fallback_q, answer = _gen_semantic_question(q_type, ctx_tmpl, topology)

    # LLM 真实问题生成
    method = timing.get("method_used", "") or "path"
    _CDM = {
        "type_filter": "target type unique in this direction",
        "status_anchor": "target status unique in this direction",
        "type_status_anchor": "type+status combo unique",
        "dir8_refine": "exact 8-direction narrows to 1",
        "dual_reference": "two reference objects jointly identify target",
        "dist_ord": "closest/farthest in this direction",
        "two_hop_referent": "a third node uniquely points to target",
        "dual_hop_referent": "two third nodes jointly identify target",
        "anchor_intro": "source object uniquely described as anchor",
        "type+dir8": "type+direction unique",
        "type+dir8+dist_ord": "type+direction+distance rank unique",
        "dir8+dist_ord": "direction+distance rank unique",
        "yesno_fallback": "path itself uniquely identifies target",
    }
    constraint_desc = _CDM.get(method, f"constraint chain method={method}")
    question = llm_client.generate_question_nlp(
        path=path, q_type=q_type,
        n1_id=cell.get("n1_id",""), n1_type=cell.get("n1_type",""),
        n2_id=cell.get("n2_id",""), n2_type=cell.get("n2_type",""),
        n3_id=cell.get("n3_id",""), n3_type=cell.get("n3_type",""),
        n3_status=cell.get("n3_status",""),
        r1_dir=cell.get("r1_dir8") or cell.get("r1_dir4","front"),
        r2_dir=cell.get("r2_dir8") or cell.get("r2_dir4","front"),
        constraint_desc=constraint_desc,
        answer=str(answer), fallback=fallback_q,
    )

    ts_end = _ts()  # ← 物理断点④：LLM问题生成完毕

    n1 = cell.get("n1_id",""); n2 = cell.get("n2_id",""); n3 = cell.get("n3_id","")
    l0 = [x for x in [n1,n2,n3] if x]
    l1 = ([{"source":n1,"target":n2}] if n1 and n2 else []) + \
         ([{"source":n2,"target":n3}] if n2 and n3 else [])
    l2 = [{"o1":n1,"o2":n2,"o3":n3}] if all([n1,n2,n3]) else []

    return {
        "question_id":  f"pilot_{str(uuid.uuid4())[:8]}",
        "gap_cell":     path,
        "topology":     topology,
        "question":     question,
        "answer":       str(answer),
        "question_type": q_type,
        "iteration_count": iteration_count,
        "constraint_trace": trace,
        "ts_start":     ts_start,
        "ts_llm":       ts_llm,
        "ts_cypher":    ts_cypher,
        "ts_end":       ts_end,
        "verify_cypher": timing.get("verify_cypher",""),
        "l0": l0, "l1": l1, "l2": l2,
        "method_used":  method,
        "is_unique":    timing.get("is_unique", False),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 打印诊断报告
# ─────────────────────────────────────────────────────────────────────────────

def _print_baseline(i: int, r: dict):
    ts_s = r["ts_start"]; ts_l = r["ts_llm"]; ts_n = r["ts_neo4j"]; ts_e = r["ts_end"]
    print(f"\n{'─'*65}")
    print(f"[Baseline #{i}] {r['nuscenes_qa_id']}  type={r['question_type']}")
    print(f"  Q : {r['question'][:80]}")
    print(f"  A : {r['answer']}")
    print(f"  ① ts_start          = {ts_s}")
    print(f"  ② ts_llm            = {ts_l}   Δ={_dt_ms(ts_s,ts_l):+d}ms")
    print(f"  ③ ts_neo4j          = {ts_n}   Δ={_dt_ms(ts_s,ts_n):+d}ms from start")
    print(f"  ④ ts_end            = {ts_e}   Δ={_dt_ms(ts_s,ts_e):+d}ms  ← 总耗时")
    print(f"  L0 ({len(r['l0_nodes'])}): {r['l0_nodes']}")
    l1_preview = [f"{e.get('source',e.get('src','?'))}→{e.get('target',e.get('tgt','?'))}" for e in r['l1_edges'][:4]]
    print(f"  L1 ({len(r['l1_edges'])}): {l1_preview}")
    print(f"  L2 ({len(r['l2_paths'])}): {r['l2_paths'][:2]}")
    print(f"  Intent: {r.get('intent',{})}")
    print(f"  cypher_question len={len(r['audit_cypher'])} chars")


def _print_generated(i: int, r: dict):
    ts_s = r["ts_start"]; ts_l = r["ts_llm"]; ts_c = r["ts_cypher"]; ts_e = r["ts_end"]
    print(f"\n{'─'*65}")
    print(f"[Generated #{i}] {r['gap_cell']}  [{r['topology']}]  type={r['question_type']}")
    print(f"  Q : {r['question'][:80]}")
    print(f"  A : {r['answer']}")
    print(f"  ① ts_start          = {ts_s}")
    print(f"  ② ts_llm            = {ts_l}   Δ={_dt_ms(ts_s,ts_l):+d}ms  ← context LLM/hardcoded")
    print(f"  ③ ts_cypher_return  = {ts_c}   Δ={_dt_ms(ts_s,ts_c):+d}ms from start")
    print(f"  ④ ts_end            = {ts_e}   Δ={_dt_ms(ts_s,ts_e):+d}ms  ← 总耗时")
    print(f"  iteration_count = {r['iteration_count']}   is_unique={r['is_unique']}  method={r['method_used']}")
    print(f"  trace: {r['constraint_trace'][:90]}")
    print(f"  L0={r['l0']}  L1={r['l1']}  L2={r['l2']}")
    print(f"  cypher_question: {r['verify_cypher'][:100].strip()}")


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(SEP)
    print("  V15.2 Pilot Diagnostic — 5 Baseline + 5 Generated")
    print("  目的：验证三病灶修复，不删旧数据，仅追加10行")
    print(SEP)

    import collections as _col
    from neo4j import GraphDatabase
    from gap_pipeline.llm_client import LLMClient
    from gap_pipeline.constraint_methods import CumulativeConstraintChain
    from gap_pipeline.coverage_tracker import CoverageTracker
    from rq_tables import write_baseline_to_coverage, write_generated_question
    from semantic_auditor import build_scene_context

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))
    llm    = LLMClient()
    chain  = CumulativeConstraintChain()

    # 构建场景上下文
    print("\n[准备] 构建场景上下文 + 载入NuScenes-QA原题...")
    scene_ctx = build_scene_context(driver)
    print(f"  scene_ctx: {len(scene_ctx)} chars")

    # 载入场景-帧-sample映射
    scenes  = json.loads((TRAINVAL/"scene.json").read_text())
    samples = json.loads((TRAINVAL/"sample.json").read_text())
    st2name = {s["token"]: s["name"] for s in scenes}
    tok2info = {}
    s2tok = _col.defaultdict(list)
    for samp in samples:
        sname = st2name.get(samp["scene_token"], "?")
        tok2info[samp["token"]] = {"scene_name": sname, "timestamp": samp["timestamp"]}
        s2tok[sname].append(samp["token"])
    for sname, toks in s2tok.items():
        for idx, tok in enumerate(sorted(toks, key=lambda t: tok2info[t]["timestamp"])):
            tok2info[tok]["frame_idx"] = idx

    all_qs = json.loads(QA_PATH.read_text())["questions"]
    target_qs = [
        (gi, q) for gi, q in enumerate(all_qs)
        if tok2info.get(q.get("sample_token",""), {}).get("scene_name") == SCENE_ID
        and tok2info.get(q.get("sample_token",""), {}).get("frame_idx") == FRAME_ID
    ]
    print(f"  Found {len(target_qs)} questions for {SCENE_ID} frame-{FRAME_ID}")

    # ─────────────────────────────────────────────────────────────────────────
    # Part A: 5条 Baseline 审计
    # ─────────────────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  Part A: 5条 Baseline 审计 → raw_coverage")
    print(SEP)

    baseline_results = []
    for i, (gi, q) in enumerate(target_qs[:5], 1):
        print(f"\n  Auditing #{i}/5: {q.get('template_type')} | {q.get('question','')[:60]}...")
        res = audit_one_baseline(q, gi, driver, llm, scene_ctx)
        baseline_results.append(res)
        _print_baseline(i, res)

        # 写入Excel
        ok = write_baseline_to_coverage(
            scene_id=SCENE_ID, frame_id=FRAME_ID,
            nuscenes_qa_id=res["nuscenes_qa_id"],
            question=res["question"], answer=res["answer"],
            l0_nodes=res["l0_nodes"], l1_edges=res["l1_edges"], l2_paths=res["l2_paths"],
            question_type=res["question_type"],
            timestamp_start=res["ts_start"],
            timestamp_end=res["ts_end"],
            audit_cypher=res["audit_cypher"],
        )
        print(f"  Excel write: {'OK' if ok else 'FAIL'}")

    # ─────────────────────────────────────────────────────────────────────────
    # Part B: 5条 L2 生成
    # ─────────────────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  Part B: 5条 L2 生成 → question-answer-our")
    print(SEP)

    tracker = CoverageTracker()
    with driver.session() as sess:
        tracker.init_from_session(sess)

    l2b_cells = tracker.priority_sort_gaps(tracker.get_gap_cells("L2B"))[:3]
    l2a_cells = tracker.priority_sort_gaps(tracker.get_gap_cells("L2A"))[:2]
    cells_to_run = [("L2B", c) for c in l2b_cells] + [("L2A", c) for c in l2a_cells]

    import random
    q_types = ["object", "status", "exist", "count", "comparison"]

    generated_results = []
    for i, (topo, cell) in enumerate(cells_to_run, 1):
        qt = q_types[i-1]
        print(f"\n  Generating #{i}/5: [{topo}] {cell.get('path_pattern','?')} q={qt}")
        res = generate_one_question(cell, topo, driver, llm, chain, qt)
        if not res:
            print("  SKIP (failed)")
            continue
        generated_results.append(res)
        _print_generated(i, res)

        ok = write_generated_question(
            scene_id=SCENE_ID, frame_id=FRAME_ID,
            question_id=res["question_id"],
            timestamp_start=res["ts_start"],
            timestamp_llm=res["ts_llm"],
            timestamp_cypher_return=res["ts_cypher"],
            timestamp_end=res["ts_end"],
            iteration_count=res["iteration_count"],
            question_type=res["question_type"],
            complexity="L2",
            natural_language_question=res["question"],
            cypher_question=res["verify_cypher"],
            answer=res["answer"],
            l0_nodes=res["l0"], l1_edges=res["l1"], l2_paths=res["l2"],
            target_gap_cell=res["gap_cell"],
        )
        print(f"  Excel write: {'OK' if ok else 'FAIL'}")

    # ─────────────────────────────────────────────────────────────────────────
    # 最终合格性摘要
    # ─────────────────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  合格性检查")
    print(SEP)
    print("\n[Baseline 5条]")
    for i, r in enumerate(baseline_results, 1):
        dt = _dt_ms(r["ts_start"], r["ts_end"])
        l0_ok = len(r["l0_nodes"]) > 0
        print(f"  #{i} Δt={dt:>6}ms  L0={len(r['l0_nodes'])}ids  L1={len(r['l1_edges'])}edges  "
              f"L0_ok={'YES' if l0_ok else 'NO'}  type={r['question_type']}")

    print("\n[Generated 5条]")
    for i, r in enumerate(generated_results, 1):
        dt = _dt_ms(r["ts_start"], r["ts_end"])
        ts_same = r["ts_start"] == r["ts_llm"]
        iter_ok = r["iteration_count"] > 1
        print(f"  #{i} [{r['topology']}] Δt={dt:>6}ms  "
              f"ts_start==ts_llm={ts_same}  "
              f"iter={r['iteration_count']}({'OK>1' if iter_ok else 'iter=1'})  "
              f"cypher={'有' if r['verify_cypher'] else '空'}")

    print(f"\n{SEP}")
    print("  STOP — 请检查以上10条数据后再决定是否全量运行")
    print(SEP)

    driver.close()


if __name__ == "__main__":
    main()
