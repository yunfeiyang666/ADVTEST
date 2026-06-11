"""
Rebuild coverage_state.json for scene-0105_frame33 from its initial_coverage.jsonl,
then invoke the generate step of the pipeline.
"""
import json
import sys
from pathlib import Path

FRAME = "scene-0105_frame33"
FRAME_DIR = Path(r"E:\Project\ADVTEST\1号机代码\DATA_new\outputs") / FRAME

# ── Step 1: rebuild coverage_state.json ──────────────────────────────
init_file = FRAME_DIR / "offline" / "initial_coverage" / f"{FRAME}_initial_coverage.jsonl"
state_dir = FRAME_DIR / "generation" / "coverage_state"
state_file = state_dir / f"{FRAME}_coverage_state.json"

l0 = set()
l1 = set()
l2 = set()
init_count = 0

if init_file.exists():
    with open(init_file, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            fp = data.get("coverage_footprint") or {}
            for x in (fp.get("l0") or []):
                l0.add(str(x))
            for x in (fp.get("l1") or []):
                l1.add(str(x))
            for x in (fp.get("l2") or []):
                l2.add(str(x))
            init_count += 1
    print(f"[rebuild] Loaded {init_count} initial QA records")
    print(f"[rebuild] Initial coverage: L0={len(l0)}, L1={len(l1)}, L2={len(l2)}")
else:
    print(f"[rebuild] No initial_coverage.jsonl found at {init_file}")

state_dir.mkdir(parents=True, exist_ok=True)
state = {
    "schema": "v7_l2_coverage_state",
    "L0": sorted(l0),
    "L1": sorted(l1),
    "L2": sorted(l2),
}
with open(state_file, "w", encoding="utf-8") as f:
    json.dump(state, f)
print(f"[rebuild] Wrote coverage_state.json ({state_file.stat().st_size:,} bytes)")

# Also clear the old empty generated.jsonl and existing reports
gen_jsonl = FRAME_DIR / "generation" / "qa" / f"{FRAME}_generated.jsonl"
if gen_jsonl.exists():
    gen_jsonl.unlink()
    print(f"[rebuild] Cleared old {gen_jsonl.name}")

inc_csv = FRAME_DIR / "reports" / f"{FRAME}_incremental_coverage.csv"
if inc_csv.exists():
    inc_csv.unlink()
    print(f"[rebuild] Cleared old {inc_csv.name}")

# Reset plan_status
plan_status_file = FRAME_DIR / "plan_status.json"
plan_status = {
    "schema": "v7_plan_status",
    "scene_id": "scene-0105",
    "frame_id": "33",
    "plans": {
        "prepare_scene_graph": "DONE",
        "prepare_initial_coverage": "DONE",
        "generate": "PENDING"
    }
}
with open(plan_status_file, "w", encoding="utf-8") as f:
    json.dump(plan_status, f, indent=2)
print(f"[rebuild] Reset plan_status to PENDING for generate")

print("\n[rebuild] Ready to run generate step.")
print(f"Scene graph: {FRAME_DIR / 'offline' / 'scene_graphs' / f'{FRAME}_filtered_scene_graph.json'}")
print(f"Coverage state: {state_file}")
