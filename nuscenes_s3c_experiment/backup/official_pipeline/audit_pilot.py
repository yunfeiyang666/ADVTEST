#!/usr/bin/env python3
"""4-point audit script for pilot run CSV and JSON."""
import csv, json, statistics, pathlib
from collections import Counter

CSV_PATH  = pathlib.Path("output/rq1_pilot_v2.csv")
JSON_PATH = pathlib.Path("output/pilot_50cells_v2.json")

rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
data = json.loads(JSON_PATH.read_text("utf-8"))
qa_pairs = data["qa_pairs"]

print("=" * 60)
print("  4-POINT AUDIT REPORT — rq1_pilot_v2.csv")
print("=" * 60)

# ── AUDIT 1: Token authenticity ──────────────────────────────────────────────
print("\n[1] LLM Token Authenticity")
tokens = []
for r in rows:
    v = r.get("llm_token_total", "0").strip()
    if v.isdigit():
        tokens.append(int(v))
llm_used = [t for t in tokens if t > 0]
print(f"  Total cells     : {len(rows)}")
print(f"  LLM called      : {len(llm_used)}")
if llm_used:
    stdev = statistics.stdev(llm_used) if len(llm_used) > 1 else 0.0
    print(f"  max             : {max(llm_used)}")
    print(f"  min             : {min(llm_used)}")
    print(f"  mean            : {statistics.mean(llm_used):.1f}")
    print(f"  stdev           : {stdev:.1f}  {'✅ real values (stdev>>0)' if stdev > 5 else '⚠️  suspiciously low'}")
    # Distribution histogram (rough)
    buckets = Counter((t // 100) * 100 for t in llm_used)
    print("  Distribution (token bucket → count):")
    for b in sorted(buckets):
        bar = "#" * buckets[b]
        print(f"    [{b:5d}-{b+99}]  {bar}  ({buckets[b]})")
else:
    print("  WARNING: no LLM calls recorded!")

# ── AUDIT 2: Level distribution ───────────────────────────────────────────────
print("\n[2] Level Distribution")
cell_levels = Counter(r.get("level", "") for r in rows)
print(f"  Cell-timing level  L0:{cell_levels['L0']}  L1:{cell_levels['L1']}  L2:{cell_levels['L2']}")

qt_counts  = Counter(qa.get("question_type", "") for qa in qa_pairs)
src_counts = Counter(qa.get("source", "")        for qa in qa_pairs)
tmpl_counts = Counter(qa.get("template_id", "")  for qa in qa_pairs
                      if qa.get("source") == "L0_node")
print(f"\n  QA pair total: {len(qa_pairs)}")
print("  By question_type:")
for qt, n in sorted(qt_counts.items(), key=lambda x: -x[1]):
    bar = "#" * min(n, 40)
    print(f"    {qt:<30} {n:>4}  {bar}")
print("  By source:")
for s, n in sorted(src_counts.items(), key=lambda x: -x[1]):
    print(f"    {s:<30} {n:>4}")
if tmpl_counts:
    print("  L0 template_ids:")
    for t, n in tmpl_counts.items():
        print(f"    {t:<30} {n:>4}")

# ── AUDIT 3: n_referents for two_hop / dual_hop ───────────────────────────────
print("\n[3] n_referents Verification (two_hop / dual_hop cells)")
hop_rows = [r for r in rows if "hop" in r.get("final_method", "")]
print(f"  Hop-method cells: {len(hop_rows)}")
ok = all_ok = True
for r in hop_rows:
    n_ref = int(r.get("n_referents", 0))
    ids   = r.get("referent_ids", "")
    ok = (n_ref >= 1 and ids.strip() != "")
    tag = "✅" if ok else "❌"
    print(f"  {tag} [{r['final_method']:30s}] n_referents={n_ref}  ids={ids!r}")
    if not ok:
        all_ok = False
print(f"  → {'ALL hop cells have n_referents>=1 ✅' if all_ok else 'SOME hop cells missing referent IDs ❌'}")

# ── AUDIT 4: Negation distractor style ───────────────────────────────────────
print("\n[4] Negation Question Sample — distractor style check")
neg_qas = [qa for qa in qa_pairs if qa.get("question_type") == "negation"]
print(f"  Total negation QA pairs: {len(neg_qas)}")
tmpl_dist = Counter(qa.get("template_id", "?") for qa in neg_qas)
print("  Template distribution:")
for t, n in tmpl_dist.items():
    print(f"    {t:<40} {n:>3}")
print("\n  Sample (first 5):")
for i, qa in enumerate(neg_qas[:5], 1):
    print(f"  [{i}] template={qa.get('template_id','?')}")
    print(f"       Q: {qa['question']}")
    print(f"       A: {qa['answer']}")
is_distractor = any("confusable" in qa.get("template_id","") or "wrong_status" in qa.get("template_id","")
                    for qa in neg_qas)
print(f"\n  → Distractor-style used: {'YES ✅' if is_distractor else 'NO (absent_type only) ⚠️'}")

# ── LLM-Judge summary by level ────────────────────────────────────────────────
print("\n[5] LLM-as-Judge Scores by Level")
for lvl in ("L0", "L1", "L2"):
    lvl_rows = [r for r in rows if r.get("level") == lvl]
    ls_vals = []
    lf_vals = []
    for r in lvl_rows:
        ls = r.get("logical_soundness","").strip()
        lf = r.get("linguistic_fluency","").strip()
        if ls.isdigit():
            ls_vals.append(int(ls))
        if lf.isdigit():
            lf_vals.append(int(lf))
    if ls_vals:
        print(f"  {lvl}  logical_soundness: mean={statistics.mean(ls_vals):.2f} n={len(ls_vals)}  "
              f"linguistic_fluency: mean={statistics.mean(lf_vals):.2f}")
    else:
        print(f"  {lvl}  no judge scores (level not represented in cell timings)")

# Also check L0 node type questions judge scores if they were judged
l0_qas = [qa for qa in qa_pairs if qa.get("source") == "L0_node"]
print(f"\n  L0 node questions generated: {len(l0_qas)} (not in cell CSV, judged via constraint row)")

# ── CSV first 5 rows ──────────────────────────────────────────────────────────
print("\n[CSV] First 5 rows (key columns):")
key_cols = ["gap_cell_id","level","q_type1","q_type2","difficulty_mapped",
            "final_method","is_unique","n_referents","referent_ids",
            "llm_token_total","question"]
print("  " + "  ".join(f"{c[:18]}" for c in key_cols))
print("  " + "─"*130)
for r in rows[:5]:
    vals = [str(r.get(c,""))[:18] for c in key_cols]
    print("  " + "  ".join(f"{v:<18}" for v in vals))
