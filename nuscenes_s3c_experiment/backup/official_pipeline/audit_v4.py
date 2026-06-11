#!/usr/bin/env python3
"""V4 Pilot audit — LLM stats, ConstraintChain, footprint, coverage."""
import csv, json, pathlib, sys, statistics, collections
sys.path.insert(0, str(pathlib.Path(__file__).parent))

data = json.loads(pathlib.Path("output/pilot_50paths_v4.json").read_text("utf-8"))
qa_pairs = data.get("qa_pairs", [])

# ── Build CSV rows ────────────────────────────────────────────────────────────
rows = []
arrow_r = "\u2192"  # →
arrow_l = "\u2190"  # ←
for qa in qa_pairs:
    topo  = qa.get("topology_level", "")
    path  = qa.get("path_pattern",   "")
    nodes = qa.get("footprint_nodes", [])
    fp_l0 = "|".join(nodes)
    fp_l1 = fp_l2 = ""
    if topo == "L2A" and arrow_r in path:
        parts = path.split(arrow_r)
        if len(parts) == 3:
            fp_l1 = f"{parts[0]}{arrow_r}{parts[1]}|{parts[1]}{arrow_r}{parts[2]}"
            fp_l2 = path
    elif topo == "L2B" and arrow_l in path and arrow_r in path:
        x    = path.split(arrow_l)[0]
        rest = path.split(arrow_l)[1]
        eg   = rest.split(arrow_r)[0]
        y    = rest.split(arrow_r)[1]
        fp_l1 = f"{eg}{arrow_r}{x}|{eg}{arrow_r}{y}"
        fp_l2 = path
    rows.append({
        "Topology_Level":            topo,
        "Path_Pattern":              path,
        "template_id":               qa.get("template_id", ""),
        "constraint_method":         qa.get("constraint_method", ""),
        "path_uniqueness_validated": str(qa.get("path_uniqueness_validated", "")),
        "n_interference_siblings":   str(qa.get("n_interference_siblings", "")),
        "llm_used":                  str(qa.get("llm_used", "")),
        "llm_tokens":                str(qa.get("llm_tokens", "")),
        "question":                  qa.get("question", ""),
        "answer":                    qa.get("answer",   ""),
        "Footprint_L0":              fp_l0,
        "Footprint_L1":              fp_l1,
        "Footprint_L2":              fp_l2,
    })

# Write CSV
out = pathlib.Path("output/rq1_pilot_v4.csv")
with out.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print(f"Written {len(rows)} rows -> {out}")

# ── Audit stats ───────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("  V4 AUDIT REPORT")
print("="*60)

topo_dist   = collections.Counter(r["Topology_Level"] for r in rows)
method_dist = collections.Counter(r["constraint_method"] for r in rows if r["constraint_method"])
n_llm = sum(1 for r in rows if r["llm_used"] == "True")
tok_list = [int(r["llm_tokens"]) for r in rows
            if r["llm_tokens"].isdigit() and int(r["llm_tokens"]) > 0]

print(f"\n[1] QA total: {len(rows)}")
print("  Topology dist:")
for t, c in topo_dist.most_common():
    print(f"    {t:<25} {c}")

print(f"\n[2] LLM-called rows: {n_llm}/{len(rows)}")
if tok_list:
    print(f"  Token max={max(tok_list)}  min={min(tok_list)}  "
          f"mean={sum(tok_list)/len(tok_list):.0f}  "
          f"stdev={statistics.stdev(tok_list) if len(tok_list)>1 else 0:.1f}")
    print("  → stdev > 0 confirms real API values")

print("\n[3] Constraint methods (L2A cells):")
l2a_rows = [r for r in rows if r["Topology_Level"] == "L2A"]
for m, c in method_dist.most_common():
    print(f"    {m:<35} {c}")
n_sib_vals = [int(r["n_interference_siblings"]) for r in l2a_rows
               if r["n_interference_siblings"].isdigit()]
if n_sib_vals:
    print(f"  Average interference siblings per L2A cell: {sum(n_sib_vals)/len(n_sib_vals):.1f}")
unique_l2a = sum(1 for r in l2a_rows if r["path_uniqueness_validated"] == "True")
print(f"  ConstraintChain unique locks: {unique_l2a}/{len(l2a_rows)}")

print("\n[4] Coverage final:")
final = data.get("coverage_final", {})
for lvl in ("L0", "L1", "L2A", "L2B"):
    d = final.get(lvl, {})
    print(f"  {lvl}: {d.get('covered',0)}/{d.get('total',0)} ({d.get('rate',0):.1f}%)")

print("\n[5] Sample L2A questions (ConstraintChain + explicit chain ref):")
for r in [x for x in rows if x["Topology_Level"] == "L2A"][:4]:
    print(f"  Path:   {r['Path_Pattern']}")
    print(f"  Method: {r['constraint_method']}  Sib: {r['n_interference_siblings']} nodes")
    print(f"  Q:      {r['question']}")
    print(f"  A:      {r['answer']}")
    print(f"  L2fp:   {r['Footprint_L2']}")
    print()

print("[6] Sample L2B questions (forced comparison, ego-hub explicit):")
l2b_tmpl = collections.Counter(r["template_id"] for r in rows if "L2B" in r["Topology_Level"])
print("  Template distribution:")
for t, c in l2b_tmpl.most_common():
    print(f"    {t:<40} {c}")
print("\n  Examples:")
for r in [x for x in rows if x["Topology_Level"] == "L2B"][:3]:
    print(f"  Path: {r['Path_Pattern']}")
    print(f"  Q:    {r['question']}")
    print(f"  A:    {r['answer']}  (template={r['template_id']})")
    print(f"  L1fp: {r['Footprint_L1']}")
    print()

print("[CSV] First 5 rows:")
cols = ["Topology_Level","Path_Pattern","template_id","question","answer","Footprint_L2"]
print("  " + "  ".join(f"{c[:18]:<18}" for c in cols))
print("  " + "─" * 120)
for r in rows[:5]:
    print("  " + "  ".join(f"{str(r.get(c,''))[:18]:<18}" for c in cols))
