"""Quick smoke test to verify V7 pipeline basics."""
import json
from run_gap_pipeline_v7 import run_smoke

records = run_smoke()
r = records[0]
print(f"Family: {r['l2_family']}")
print(f"Question: {r['question']}")
print(f"Answer: {r['answer']}")
print(f"Answer type: {r['answer_type']}")
fp = r["coverage_footprint"]
print(f"Coverage L0={len(fp['l0'])} L1={len(fp['l1'])} L2={len(fp['l2'])}")
print(f"Schema: {r.get('schema_version', 'N/A')}")
print("SMOKE OK")
