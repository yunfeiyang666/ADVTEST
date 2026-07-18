"""Wait for the RQ2 Random formal run, then execute safe follow-up gates.

The queue never treats a partial Random run as finished.  It first produces the
coverage report and then checks that MiniCPM can perform one real RQ1 inference;
the full MiniCPM/Qwen matrices remain separate explicit experiment launches.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path("E:/Project/ADVTEST")
CODE_DIR = ROOT / "1号机代码/DATA_new/official_pipeline/code"
RQ1_DIR = ROOT / "1号机代码/DATA_new/analysis/rq1_error_detection"
DEFAULT_OUTPUTS = ROOT / "1号机代码/DATA_new/outputs"
DEFAULT_RUN_ROOT = ROOT / "scratch/rq2_random_full_coverage/formal-cache-v1"
DEFAULT_MINICPM_PYTHON = ROOT / ".venv310/Scripts/python.exe"


def write_status(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def read_status(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def wait_for_random(status_path: Path, queue_status: Path, interval_seconds: int) -> dict:
    while True:
        if status_path.exists():
            payload = read_status(status_path)
            state = str(payload.get("state") or "")
            write_status(queue_status, {"state": "waiting_random", "random": payload})
            if state in {"complete", "complete_with_failures", "failed"}:
                return payload
        else:
            write_status(queue_status, {"state": "waiting_for_random_status"})
        time.sleep(interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--outputs-root", type=Path, default=DEFAULT_OUTPUTS)
    parser.add_argument("--random-run-id", default="rq2-random-full-cache-v1")
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--minicpm-python", type=Path, default=DEFAULT_MINICPM_PYTHON)
    args = parser.parse_args()
    if args.interval_seconds < 10:
        raise ValueError("--interval-seconds must be at least 10")

    queue_status = args.run_root / "post_random_queue_status.json"
    random = wait_for_random(args.run_root / "status.json", queue_status, args.interval_seconds)
    if random.get("state") != "complete":
        write_status(
            queue_status,
            {
                "state": "blocked_random_incomplete",
                "random": random,
                "reason": "Random has failures or missing frame-runs; no downstream evaluation started.",
            },
        )
        return 2

    report_dir = args.run_root / "reports"
    report_command = [
        sys.executable,
        str(CODE_DIR / "run_random_full_coverage_experiment.py"),
        "report",
        "--outputs-root",
        str(args.outputs_root),
        "--stats",
        str(args.outputs_root / "all_frames_stats.csv"),
        "--random-run-id",
        args.random_run_id,
        "--report-dir",
        str(report_dir),
    ]
    write_status(queue_status, {"state": "building_random_report", "command": report_command})
    report = subprocess.run(report_command, cwd=CODE_DIR, capture_output=True, text=True)
    if report.returncode != 0:
        write_status(
            queue_status,
            {"state": "failed_random_report", "stdout": report.stdout[-8000:], "stderr": report.stderr[-8000:]},
        )
        return report.returncode

    smoke_command = [str(args.minicpm_python), str(RQ1_DIR / "run_minicpm_smoke.py")]
    write_status(queue_status, {"state": "running_minicpm_smoke", "command": smoke_command})
    smoke = subprocess.run(smoke_command, cwd=ROOT, capture_output=True, text=True)
    final_state = "ready_for_rq1_minicpm_matrix" if smoke.returncode == 0 else "failed_minicpm_smoke"
    write_status(
        queue_status,
        {
            "state": final_state,
            "random_report": str(report_dir / "random_full_report.json"),
            "minicpm_smoke_returncode": smoke.returncode,
            "minicpm_smoke_stdout": smoke.stdout[-8000:],
            "minicpm_smoke_stderr": smoke.stderr[-8000:],
        },
    )
    return smoke.returncode


if __name__ == "__main__":
    raise SystemExit(main())
