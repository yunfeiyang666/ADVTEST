#!/usr/bin/env python3
"""Syntax check + smoke test for RQ files."""
import ast, pathlib, sys, json, csv
base = pathlib.Path(__file__).parent
sys.path.insert(0, str(base))

# ── Syntax check ────────────────────────────────────────────────────────────
files = ['rq_tables.py','run_mut_evaluation.py','run_rq_experiment.py','bench_models.py']
ok = True
for f in files:
    try:
        ast.parse((base/f).read_text(encoding='utf-8'))
        print(f"OK  {f}")
    except SyntaxError as e:
        print(f"ERR {f}: {e}")
        ok = False

if not ok:
    sys.exit(1)

# ── Smoke test: Table A + B from V6 data ─────────────────────────────────────
from rq_tables import write_all_tables, CoverageSnapshotter
from gap_pipeline.coverage_tracker import CoverageTracker

data = json.loads((base / "output/pilot_50paths_v6.json").read_text("utf-8"))
out  = base / "output/rq_experiment"

write_all_tables(
    qa_pairs=data["qa_pairs"][:10],
    timings=data["cell_timings"][:10],
    scene_id="scene-0553",
    frame_id=8,
    out_dir=out,
    llm_model="qwen-plus",
)

rows = list(csv.DictReader(open(str(out / "question-answer-our.csv"), encoding="utf-8-sig")))
print(f"\nTable B rows: {len(rows)}")
for r in rows[:3]:
    qid   = r["question_id"]
    qtype = r["question_type"]
    cpx   = r["complexity"]
    it    = r["iteration_count"]
    uniq  = r["is_unique"]
    q     = r["natural_language_question"][:55]
    print(f"  [{qid}] {qtype} {cpx} it={it} unique={uniq}")
    print(f"    Q: {q}")

rows_a = list(csv.DictReader(open(str(out / "raw_coverage.csv"), encoding="utf-8-sig")))
print(f"\nTable A rows: {len(rows_a)}")
print("  Sample (L2_paths):")
for r in rows_a[:3]:
    print(f"    {r['nuscenes_qa_id']}  L0={r['L0_nodes'][:40]}  L2={r['L2_paths'][:40]}")

print("\nALL OK")
