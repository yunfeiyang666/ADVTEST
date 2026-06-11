#!/usr/bin/env python3
"""V6 final audit."""
import csv, json, statistics, collections, pathlib

rows = list(csv.DictReader(
    open("output/rq1_pilot_v6.csv", encoding="utf-8-sig")))
data = json.loads(pathlib.Path("output/pilot_50paths_v6.json").read_text("utf-8"))

print(f"Total rows: {len(rows)}  |  QA pairs in JSON: {data['n_qa_generated']}")
print(f"wall_ms={data['wall_ms']:.0f}  speedup={data['speedup_x']}×  "
      f"v5_serial_ms={data['v5_equiv_serial_ms']:.0f}")
print()

# Topology
topo = collections.Counter(r["Topology_Level"] for r in rows)
print("Topology dist:")
for t,c in topo.most_common(): print(f"  {t:<20} {c}")

# is_unique
unique_n = sum(1 for r in rows if r.get("is_unique","").lower() == "true")
print(f"\nis_unique: {unique_n}/{len(rows)}  (V5 was 0/{len(rows)})")

# Logic_Verification
lv_ok = sum(1 for r in rows if "✅" in r.get("Logic_Verification",""))
print(f"Logic_Verification n=1: {lv_ok}/{len(rows)}")
lv_dist = collections.Counter(
    "✅" if "✅" in r.get("Logic_Verification","") else "❌"
    for r in rows)
for k,v in lv_dist.items(): print(f"  {k}: {v}")

# Constraint methods
methods = collections.Counter(
    r.get("Template_ID","").split(":")[-1] for r in rows)
print("\nConstraint methods:")
for m,c in methods.most_common(8):
    print(f"  {m:<35} {c}")

# Coverage
print("\nCoverage (from JSON):")
init  = data["coverage_init"]
final = data["coverage_final"]
for lvl in ("L0","L1","L2A","L2B"):
    bi = init[lvl]["rate"]
    af = final[lvl]["rate"]
    cv = final[lvl]["covered"]
    tt = final[lvl]["total"]
    print(f"  {lvl}: {bi:.2f}% → {af:.2f}%  Δ={af-bi:+.3f}%  ({cv}/{tt})")

# Smart sampling verification: how many distinct n2 nodes?
n2s = set()
for r in rows:
    fp = r.get("Footprint_Nodes","")
    parts = fp.split("|")
    if len(parts) == 3: n2s.add(parts[1])
print(f"\nDistinct middle nodes (n2) touched: {len(n2s)}")

# Sample questions showing is_unique=True with non-trivial methods
print("\nSample uniquely-locked questions (is_unique=True):")
samples = [r for r in rows if r.get("is_unique","").lower()=="true"][:4]
for r in samples:
    print(f"  Path:    {r['Path_Structure']}")
    print(f"  Method:  {r['Template_ID']}")
    print(f"  Trace:   {r['Constraint_Trace'][:80]}...")
    print(f"  Q:       {r['question']}")
    print(f"  Verify:  {r['Logic_Verification']}")
    print()
