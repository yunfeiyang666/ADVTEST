#!/usr/bin/env python3
"""V3 Pilot audit: generate CSV + verify topological correctness."""
import csv, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from analysis_utils import process_v3_result_file, print_v3_coverage_summary, write_csv

JSON_PATH = pathlib.Path("output/pilot_50paths_v3.json")
CSV_PATH  = pathlib.Path("output/rq1_pilot_v3.csv")

# ── Generate CSV ──────────────────────────────────────────────────────────────
rows = process_v3_result_file(JSON_PATH)
write_csv(rows, CSV_PATH)

data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
print_v3_coverage_summary(data)

# ── V3-specific validation ────────────────────────────────────────────────────
print("\n" + "="*60)
print("  V3 CORRECTNESS AUDIT")
print("="*60)

from collections import Counter

# 1. All L2 rows must have path_pattern with exactly 3 nodes
topo_counts = Counter(r["Topology_Level"] for r in rows)
print(f"\n[1] Topology distribution:")
for t, n in topo_counts.most_common():
    print(f"  {t:<6} {n:>4} rows")

# 2. Every L2A row must have path_pattern = "X→Y→Z" (3 nodes, 2 arrows)
l2a_bad = [r for r in rows if r["Topology_Level"]=="L2A"
           and r["Path_Pattern"].count("→") != 2]
l2b_bad = [r for r in rows if r["Topology_Level"]=="L2B"
           and ("←" not in r["Path_Pattern"] or "→" not in r["Path_Pattern"])]
print(f"\n[2] Path_Pattern validity:")
print(f"  L2A malformed: {len(l2a_bad)} (should be 0)")
print(f"  L2B malformed: {len(l2b_bad)} (should be 0)")

# 3. Footprint completeness: L2A must have L1 footprint with 2 edges
l2a_rows = [r for r in rows if r["Topology_Level"]=="L2A"]
fp_l1_ok = sum(1 for r in l2a_rows if r["Footprint_L1"].count("|") >= 1)
print(f"\n[3] L2A Footprint_L1 populated: {fp_l1_ok}/{len(l2a_rows)} (should be {len(l2a_rows)})")

# 4. Sample 5 L2A and 5 L2B questions
print("\n[4] Sample L2A questions (chain structure visible):")
for r in [x for x in rows if x["Topology_Level"]=="L2A"][:5]:
    print(f"  Path: {r['Path_Pattern']}")
    print(f"  Tmpl: {r['template_id']}")
    print(f"  Q:    {r['question']}")
    print(f"  A:    {r['answer']}")
    print(f"  L1fp: {r['Footprint_L1']}")
    print()

print("[5] Sample L2B questions (ego-hub interaction visible):")
for r in [x for x in rows if x["Topology_Level"]=="L2B"][:5]:
    print(f"  Path: {r['Path_Pattern']}")
    print(f"  Tmpl: {r['template_id']}")
    print(f"  Q:    {r['question']}")
    print(f"  A:    {r['answer']}")
    print(f"  L1fp: {r['Footprint_L1']}")
    print()

# 5. CSV first 5 rows
print("[CSV] First 5 rows (key columns):")
cols = ["Topology_Level","Path_Pattern","template_id","question","answer","Footprint_L1"]
hdr = "  ".join(f"{c[:20]:<20}" for c in cols)
print("  " + hdr)
print("  " + "─"*120)
for r in rows[:5]:
    vals = "  ".join(f"{str(r.get(c,''))[:20]:<20}" for c in cols)
    print("  " + vals)
