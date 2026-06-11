#!/usr/bin/env python3
"""
analysis_utils.py — RQ1 分析工具
将 gap_result.json 转换为符合 RQ1 标准的精细 CSV 表格。

用法：
    python analysis_utils.py <gap_result.json>
    python analysis_utils.py <gap_result.json> --out rq1_table.csv
    python analysis_utils.py --merge output/run_*/gap_result.json  # 合并多次运行
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# ─── 错误分类规则 ────────────────────────────────────────────────────────────

def classify_error(ct: Dict, qa: Optional[Dict]) -> tuple[str, str]:
    """返回 (error_type, error_detail)"""
    # Timeout
    if ct.get("ctx_llm_ms", 0) >= 29000 and not ct.get("ctx_llm_used_llm"):
        return "Timeout", f"LLM timeout {ct.get('ctx_llm_ms',0):.0f}ms"
    # Cypher error（LLM调用了但深度=0可能有问题）
    if ct.get("ctx_llm_used_llm") and ct.get("llm_cypher_depth", 0) == 0:
        return "CypherError", "LLM cypher has no MATCH clause"
    # Lock failed（无法唯一）
    if not ct.get("is_unique") and ct.get("method_used") == "yesno_fallback":
        return "LockFailed", f"All methods failed, fallback to yesno after {ct.get('n_failed_attempts',0)} attempts"
    # Verify failed（验证返回n>1）
    # (需要将来加入verify_n字段后使用)
    # Semantic redundant（已通过代码修复，历史数据中可检测）
    if qa and re.search(r"\b(\w+) \1\b", qa.get("question", ""), re.IGNORECASE):
        return "SemanticRedundant", "repeated type+id in question"
    # OK
    return "OK", ""


def cypher_logic_depth(ct: Dict) -> int:
    """从已存字段读 llm_cypher_depth，或估算"""
    return ct.get("llm_cypher_depth", 0)


def _count_referents(ct: Dict) -> int:
    """从 referent_ids_str 字段计算实际参照节点数。
    two_hop: 'car9'          → 1
    dual_hop: 'car9|car15'   → 2
    attr+two_hop: 'car9'     → 1
    其他/空: ''              → 0
    """
    s = ct.get("referent_ids_str", "")
    if not s:
        return 0
    return len([x for x in s.split("|") if x.strip()])


def build_rq1_row(
    run_id: str,
    scene_id: str,
    frame_idx: int,
    ct: Dict[str, Any],
    qa_constraint: Optional[Dict],
    qa_negation: Optional[Dict],
    qa_multihop: Optional[Dict],
    all_qa: List[Dict],
) -> Dict[str, Any]:
    """构建单个 gap cell 的 RQ1 行。"""
    cell_id = ct.get("cell_id", "")
    src_id, tgt_id = (cell_id.split("→") + ["", ""])[:2]

    # 约束链完整路径：从 constraint_trace_str 分解
    trace_str = ct.get("constraint_trace_str", "")
    # 提取成功方法
    success_method = ct.get("method_used", "")

    # 主问题（constraint_chain 类型）
    q_main  = qa_constraint.get("question", "") if qa_constraint else ""
    a_main  = qa_constraint.get("answer",   "") if qa_constraint else ""
    diff    = qa_constraint.get("difficulty","") if qa_constraint else ""
    q_neg   = qa_negation.get("question",  "") if qa_negation  else ""
    q_hop   = qa_multihop.get("question",  "") if qa_multihop  else ""
    a_hop   = qa_multihop.get("answer",    "") if qa_multihop  else ""

    error_type, error_detail = classify_error(ct, qa_constraint)

    row = {
        # ── 基础信息 ───────────────────────────────────
        "run_id":          run_id,
        "scene_id":        scene_id,
        "frame_idx":       frame_idx,
        "gap_cell_id":     cell_id,
        "src_id":          src_id,
        "tgt_id":          tgt_id,

        # ── 等级分类（来自 level_taxonomy）───────────────────
        "level":           ct.get("level", ""),
        "q_type1":         ct.get("q_type1", ""),
        "q_type2":         ct.get("q_type2", ""),
        "difficulty_mapped": ct.get("difficulty_mapped", ""),

        # ── 生成链条 ───────────────────────────────────
        "llm_cypher_ok":       int(ct.get("ctx_llm_used_llm", False)),
        "cypher_logic_depth":  cypher_logic_depth(ct),
        "initial_candidate_n": ct.get("n_candidates", 0),
        "n_referents":         _count_referents(ct),
        "referent_ids":        ct.get("referent_ids_str", ""),
        "constraint_trace":    trace_str,
        "final_method":        success_method,
        "is_unique":           int(ct.get("is_unique", False)),
        "n_failed_attempts":   ct.get("n_failed_attempts", 0),

        # ── 效能指标 ───────────────────────────────────
        "total_latency_ms":    round(ct.get("total_ms",         0), 1),
        "llm_time_ms":         round(ct.get("ctx_llm_ms",       0), 1),
        "neo4j_ctx_ms":        round(ct.get("ctx_neo4j_ms",     0), 1),
        "neo4j_cand_ms":       round(ct.get("cand_neo4j_ms",    0), 1),
        "tighten_ms":          round(ct.get("constraint_ms",    0), 3),
        "template_fill_ms":    round(ct.get("template_fill_ms", 0), 3),
        "llm_token_prompt":    ct.get("llm_token_prompt",    0),
        "llm_token_completion":ct.get("llm_token_completion",0),
        "llm_token_total":     ct.get("llm_token_prompt",0) + ct.get("llm_token_completion",0),

        # ── 主 QA（constraint_chain / yesno）──────────────────
        "question":       q_main,
        "answer":         a_main,
        "difficulty":     diff,
        "question_type":  qa_constraint.get("question_type","") if qa_constraint else "",

        # ── 否定题 ───────────────────────────────────
        "negation_question": q_neg,
        "negation_answer":   "No" if q_neg else "",

        # ── 多跳题 ───────────────────────────────────
        "multihop_question": q_hop,
        "multihop_answer":   a_hop,

        # ── 质量评分（预留人工打分）─────────────────────
        "logical_soundness":     "",   # 1-5，人工/LLM打分
        "linguistic_fluency":    "",   # 1-5
        "visual_answerability":  "",   # 1-5
        "uniqueness_human":      "",   # True/False

        # ── 错误分类 ───────────────────────────────────
        "error_type":   error_type,
        "error_detail": error_detail,
    }
    return row


# ─── V3 拓扑路径 CSV 生成 ──────────────────────────────────────────────────────

def process_v3_result_file(path: Path, run_id: str = "") -> List[Dict]:
    """Convert a V3 pipeline result JSON to a flat CSV row list.

    Each row corresponds to one QA pair and includes:
    - Topology_Level, Path_Pattern, Footprint_L0/L1/L2
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not run_id:
        run_id = path.parent.name

    scene_id  = data.get("scene_name", "")
    frame_idx = data.get("frame_idx", 0)
    rows = []

    for qa in data.get("qa_pairs", []):
        topo  = qa.get("topology_level", "")
        path_p = qa.get("path_pattern", "")
        nodes = qa.get("footprint_nodes", [])

        # Footprint derivation
        fp_l0 = "|".join(nodes)
        fp_l1 = ""
        fp_l2 = ""
        if topo == "L2A" and "→" in path_p:
            parts = path_p.split("→")
            if len(parts) == 3:
                fp_l1 = f"{parts[0]}→{parts[1]}|{parts[1]}→{parts[2]}"
                fp_l2 = path_p
        elif topo == "L2B" and "←" in path_p and "→" in path_p:
            x = path_p.split("←")[0]
            rest = path_p.split("←")[1]
            eg, y = rest.split("→")[0], rest.split("→")[1]
            fp_l1 = f"{eg}→{x}|{eg}→{y}"
            fp_l2 = path_p

        rows.append({
            "run_id":         run_id,
            "scene_id":       scene_id,
            "frame_idx":      frame_idx,
            "question_id":    qa.get("question_id", ""),
            "Topology_Level": topo,
            "Path_Pattern":   path_p,
            "template_id":    qa.get("template_id", ""),
            "difficulty":     qa.get("difficulty", ""),
            "question":       qa.get("question", ""),
            "answer":         qa.get("answer", ""),
            "answer_type":    qa.get("answer_type", ""),
            "Footprint_L0":   fp_l0,
            "Footprint_L1":   fp_l1,
            "Footprint_L2":   fp_l2,
        })

    return rows


def print_v3_coverage_summary(data: Dict) -> None:
    """Print V3 topology coverage curves split by L2A/L2B."""
    init   = data.get("coverage_init",  {})
    final  = data.get("coverage_final", {})
    n_l2a  = data.get("n_l2a_cells", 0)
    n_l2b  = data.get("n_l2b_cells", 0)
    n_qa   = data.get("n_qa_generated", 0)

    SEP = "─" * 65
    print(f"\n{SEP}")
    print("  V3 拓扑覆盖摘要")
    print(SEP)
    print(f"  Gap cells processed:  L2A={n_l2a}  L2B={n_l2b}  total={n_l2a+n_l2b}")
    print(f"  QA pairs generated:   {n_qa}")
    print(f"\n  {'Level':5}  {'Before':>10}  {'After':>10}  {'Delta':>8}")
    print(f"  {'─'*40}")
    for lvl in ("L0", "L1", "L2A", "L2B"):
        bi = init.get(lvl, {}).get("rate", 0)
        af = final.get(lvl, {}).get("rate", 0)
        t  = final.get(lvl, {}).get("total", 0)
        c  = final.get(lvl, {}).get("covered", 0)
        print(f"  {lvl:5}  {bi:>8.1f}%  {af:>8.1f}%  {af-bi:>+7.1f}%"
              f"  ({c}/{t})")
    print(SEP)


# ─── 主逻辑 ──────────────────────────────────────────────────────────────────

def process_result_file(path: Path, run_id: str = "") -> List[Dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not run_id:
        run_id = path.parent.name  # 用目录名作 run_id

    scene_id   = ""
    frame_idx  = 0
    # 从 params 取场景信息
    for entry in data.get("cell_timings", []):
        # cell_id 格式 "ego→truck1"，不含场景名，从 qa_pairs 里取
        break

    # 建立 cell_id → QA 映射
    qa_by_cell: Dict[str, Dict[str, Dict]] = {}
    for qa in data.get("qa_pairs", []):
        ci = qa.get("cell_info", {})
        key = f"{ci.get('src_id','')}→{ci.get('tgt_id','')}"
        sn  = qa.get("scene_name", "")
        fi  = qa.get("frame_idx", 0)
        if not scene_id and sn:
            scene_id  = sn
            frame_idx = fi
        qt = qa.get("question_type", "")
        if key not in qa_by_cell:
            qa_by_cell[key] = {}
        # 按 question_type 归类，每类取第一条
        if qt not in qa_by_cell[key]:
            qa_by_cell[key][qt] = qa

    rows = []
    for ct in data.get("cell_timings", []):
        cell_id = ct.get("cell_id", "")
        qmap    = qa_by_cell.get(cell_id, {})
        # 取各类型的代表 QA
        qa_cc  = qmap.get("constraint_chain") or qmap.get("existence")
        qa_neg = qmap.get("negation")
        qa_hop = qmap.get("multihop")
        all_qa = list(qmap.values())

        row = build_rq1_row(
            run_id=run_id,
            scene_id=scene_id,
            frame_idx=frame_idx,
            ct=ct,
            qa_constraint=qa_cc,
            qa_negation=qa_neg,
            qa_multihop=qa_hop,
            all_qa=all_qa,
        )
        rows.append(row)

    return rows


def write_csv(rows: List[Dict], out_path: Path) -> None:
    if not rows:
        print("No data to write.")
        return
    fieldnames = list(rows[0].keys())
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"✓ 已写入 {len(rows)} 行 → {out_path}")


def compute_coverage_curves(rows: List[Dict]) -> Dict[str, List[int]]:
    """按 L0/L1/L2 分别计算累积覆盖曲线。

    返回 dict：
        {
            "L0": [unique_so_far after cell 1, after cell 2, ...],
            "L1": [...],
            "L2": [...],
            "all": [...],
        }
    """
    from collections import defaultdict
    curves: Dict[str, List[int]] = {"L0": [], "L1": [], "L2": [], "all": []}
    seen: Dict[str, set] = {"L0": set(), "L1": set(), "L2": set(), "all": set()}

    for row in rows:
        lvl = row.get("level", "L1") or "L1"  # fallback to L1 if blank
        cell_id = row.get("gap_cell_id", "")
        # only count unique-locked cells toward coverage
        if row.get("is_unique") and cell_id:
            seen["all"].add(cell_id)
            if lvl in seen:
                seen[lvl].add(cell_id)
        curves["all"].append(len(seen["all"]))
        for lv in ("L0", "L1", "L2"):
            curves[lv].append(len(seen[lv]))
    return curves


def print_coverage_curves(rows: List[Dict]) -> None:
    """打印 L0/L1/L2 覆盖曲线摘要（每 10 行采样一次）."""
    curves = compute_coverage_curves(rows)
    n = len(rows)
    step = max(1, n // 10)
    print(f"\n{'─'*55}")
    print(f"  覆盖曲线 (N={n} cells，unique locked)")
    print(f"  {'idx':>6}  {'L0':>5}  {'L1':>5}  {'L2':>5}  {'all':>5}")
    print(f"  {'─'*40}")
    for i in range(0, n, step):
        print(f"  {i+1:>6}  "
              f"{curves['L0'][i]:>5}  "
              f"{curves['L1'][i]:>5}  "
              f"{curves['L2'][i]:>5}  "
              f"{curves['all'][i]:>5}")
    # last row
    print(f"  {n:>6}  "
          f"{curves['L0'][-1]:>5}  "
          f"{curves['L1'][-1]:>5}  "
          f"{curves['L2'][-1]:>5}  "
          f"{curves['all'][-1]:>5}")
    print(f"{'─'*55}\n")


def print_summary(rows: List[Dict]) -> None:
    total   = len(rows)
    unique  = sum(1 for r in rows if r["is_unique"])
    timeout = sum(1 for r in rows if r["error_type"] == "Timeout")
    lock_f  = sum(1 for r in rows if r["error_type"] == "LockFailed")

    from collections import Counter
    method_dist = Counter(r["final_method"] for r in rows if r["final_method"])
    avg_llm  = sum(r["llm_time_ms"] for r in rows) / total if total else 0
    avg_fail = sum(r["n_failed_attempts"] for r in rows) / total if total else 0
    token_avg = sum(r["llm_token_total"] for r in rows) / max(1, sum(1 for r in rows if r["llm_token_total"]>0))

    print(f"\n{'─'*55}")
    print(f"  RQ1 摘要  |  共 {total} 行")
    print(f"{'─'*55}")
    print(f"  唯一锁定率   : {unique}/{total} = {unique*100//total if total else 0}%")
    print(f"  LLM Timeout  : {timeout}  |  LockFailed: {lock_f}")
    print(f"  平均 LLM耗时 : {avg_llm:.0f}ms")
    print(f"  平均失败尝试 : {avg_fail:.1f} 次/cell")
    print(f"  平均 Token   : {token_avg:.0f} (仅LLM调用时)")
    print(f"  约束方法 Top5:")
    for m, c in method_dist.most_common(5):
        print(f"    {m:<35} {c:>4}次  {c*100//total if total else 0}%")
    print(f"{'─'*55}\n")


# ─── LLM-as-Judge ───────────────────────────────────────────────────

_JUDGE_PROMPT = """\
You are a judge evaluating a Visual Question Answering (VQA) question
generated for autonomous driving scenes.

Given the question and its ground-truth answer, rate on two dimensions:

1. logical_soundness (1-5):
   5 = Logically tight, the answer uniquely satisfies the question constraints.
   3 = Some ambiguity but mostly sound.
   1 = Logical error or the answer does not satisfy the question.

2. linguistic_fluency (1-5):
   5 = Natural, grammatically correct English.
   3 = Understandable but awkward.
   1 = Grammatically broken or incomprehensible.

Question: {question}
Answer: {answer}

Respond with ONLY a JSON object like this (no explanation):
{{"logical_soundness": <1-5>, "linguistic_fluency": <1-5>}}
"""


def llm_judge(
    rows: List[Dict],
    sample_n: int = 50,
    api_key: str = "",
    api_base: str = "",
    model: str = "deepseek-v3",
) -> List[Dict]:
    """对 sample_n 个样本做 LLM-as-Judge 评分。
    直接修改传入的 rows 列表，填充 logical_soundness / linguistic_fluency 字段。
    """
    import json
    import random
    try:
        import openai
        import httpx
    except ImportError:
        print("[WARN] openai/httpx not installed, skip LLM judge.")
        return rows

    # 优先从 config.py 读取 API 配置
    if not api_key:
        try:
            import sys, os
            sys.path.insert(0, str(Path(__file__).parent))
            from gap_pipeline.config import LLM_CONFIG
            api_key  = LLM_CONFIG["api_key"]
            api_base = LLM_CONFIG["api_base"]
            model    = LLM_CONFIG["model"]
        except Exception:
            print("[WARN] Cannot load LLM config, skip judge.")
            return rows

    timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)
    client  = openai.OpenAI(
        api_key=api_key, base_url=api_base,
        http_client=httpx.Client(verify=False, timeout=timeout),
        max_retries=0,
    )

    # 随机抽样（优先抽取有问题的行）
    candidates = [r for r in rows if r.get("question") and r.get("answer")]
    sample = random.sample(candidates, min(sample_n, len(candidates)))
    sample_ids = {id(r) for r in sample}

    print(f"LLM Judge: 对 {len(sample)} 个样本评分（model={model}）...")
    for idx, row in enumerate(sample, 1):
        prompt = _JUDGE_PROMPT.format(
            question=row["question"],
            answer=row["answer"],
        )
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0.0,
            )
            raw  = resp.choices[0].message.content.strip()
            # 解析 JSON
            raw  = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`")
            data = json.loads(raw)
            row["logical_soundness"]    = int(data.get("logical_soundness", ""))
            row["linguistic_fluency"]   = int(data.get("linguistic_fluency", ""))
            row["visual_answerability"] = ""  # 无图评估
        except Exception as e:
            row["logical_soundness"]  = ""
            row["linguistic_fluency"] = ""
            print(f"  [{idx}] judge error: {e}")
            continue
        if idx % 10 == 0:
            print(f"  完成 {idx}/{len(sample)}")
    print("LLM Judge 完成")
    return rows


# ─── CLI ─────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RQ1 Analysis: gap_result.json → RQ1 CSV"
    )
    parser.add_argument("inputs", nargs="+", help="gap_result.json 路径（支持多个合并）")
    parser.add_argument("--out", default=None, help="输出 CSV 路径（默认: rq1_<run_id>.csv）")
    parser.add_argument("--no-summary", action="store_true")
    parser.add_argument("--judge", action="store_true",
                        help="LLM-as-Judge: 对 50 个样本评分 logical_soundness/linguistic_fluency")
    parser.add_argument("--judge-n", type=int, default=50,
                        help="Judge 样本数（默认 50）")
    args = parser.parse_args()

    all_rows: List[Dict] = []
    for inp in args.inputs:
        p = Path(inp)
        if not p.exists():
            print(f"[WARN] 文件不存在: {p}", file=sys.stderr)
            continue
        rows = process_result_file(p)
        all_rows.extend(rows)
        print(f"  {p.name}: {len(rows)} 行")

    if not all_rows:
        print("未找到有效数据。")
        return

    if args.out:
        out = Path(args.out)
    else:
        # 默认放在第一个输入文件旁边
        out = Path(args.inputs[0]).parent / "rq1_table.csv"

    if args.judge:
        all_rows = llm_judge(all_rows, sample_n=args.judge_n)

    write_csv(all_rows, out)
    if not args.no_summary:
        print_summary(all_rows)
        print_coverage_curves(all_rows)


if __name__ == "__main__":
    main()
