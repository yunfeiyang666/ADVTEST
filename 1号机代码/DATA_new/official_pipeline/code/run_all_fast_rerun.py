import subprocess
import sys
import time
from pathlib import Path

# Use the active Python interpreter
PYTHON = sys.executable
RUN_BATCH = Path(__file__).resolve().parent / "run_batch_fast.py"
PLANS_DIR = Path(__file__).resolve().parent.parent / "plans"

shards = [
    # Plan A Remaining:
    {"name": "plan_A_shard1a", "file": "plan_A_local.json", "start": 855, "end": 859},
    {"name": "plan_A_shard1_scene0106a", "file": "plan_A_local.json", "start": 1030, "end": 1050},
    
    # Split the remaining 26 frames of other2 (1004 to 1030) into 5 parallel micro-shards
    {"name": "plan_A_shard1_other2_1", "file": "plan_A_local.json", "start": 1004, "end": 1010},
    {"name": "plan_A_shard1_other2_2", "file": "plan_A_local.json", "start": 1010, "end": 1015},
    {"name": "plan_A_shard1_other2_3", "file": "plan_A_local.json", "start": 1015, "end": 1020},
    {"name": "plan_A_shard1_other2_4", "file": "plan_A_local.json", "start": 1020, "end": 1025},
    {"name": "plan_A_shard1_other2_5", "file": "plan_A_local.json", "start": 1025, "end": 1030},
]

print("Starting sharded full batch rerun of Phase 2 generation in PARALLEL...")
processes = []

for shard in shards:
    plan_path = PLANS_DIR / shard["file"]
    shard_name = shard["name"]
    start = shard["start"]
    end = shard["end"]
    
    print(f"Launching shard {shard_name}: {shard['file']} [frames {start} to {end}]", flush=True)
    log_file = PLANS_DIR.parent / "outputs" / f"run_{shard_name}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    f = log_file.open("w", encoding="utf-8")
    
    cmd = [
        PYTHON, str(RUN_BATCH), str(plan_path),
        "--start", str(start),
        "--end", str(end),
        "--phase", "2"
    ]
    proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
    processes.append((shard_name, proc, f))

# Wait for all processes to complete
print("\nAll plans launched. Waiting for completion...", flush=True)
while True:
    running = [p for p in processes if p[1].poll() is None]
    if not running:
        break
    print(f"[{time.strftime('%H:%M:%S')}] Running plans: {', '.join([r[0] for r in running])}", flush=True)
    time.sleep(60)

# Check return codes
failed = False
for name, proc, f in processes:
    f.close()
    code = proc.returncode
    print(f"Plan {name} finished with exit code {code}", flush=True)
    if code != 0:
        failed = True

if failed:
    print("\nSome plans failed execution.", flush=True)
    sys.exit(1)
else:
    print("\nAll plans completed successfully in parallel!", flush=True)
