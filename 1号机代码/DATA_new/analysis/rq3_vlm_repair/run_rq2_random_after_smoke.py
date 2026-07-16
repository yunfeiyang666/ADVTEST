"""Start the RQ2 random full-coverage run only after the MiniCPM smoke exits."""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE = Path("E:/Project/ADVTEST")
DEFAULT_RUNNER = WORKSPACE / (
    "1号机代码/DATA_new/official_pipeline/code/"
    "run_random_full_coverage_experiment.py"
)
DEFAULT_RUN_ROOT = WORKSPACE / "scratch/rq2_random_full_coverage"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_status(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_step(command: list[str], log) -> int:
    log.write("$ " + subprocess.list2cmdline(command) + "\n")
    log.flush()
    return subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, text=True).returncode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-pid", required=True, type=int)
    parser.add_argument("--runner", type=Path, default=DEFAULT_RUNNER)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    args = parser.parse_args()

    status_path = args.run_root / "after_smoke_status.json"
    status = {
        "schema_version": "rq2_random_after_minicpm_smoke_v1",
        "smoke_pid": args.smoke_pid,
        "started_at": timestamp(),
        "state": "waiting_for_smoke",
    }
    write_status(status_path, status)
    log_path = args.run_root / "after_smoke.log"
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"Wait-Process -Id {args.smoke_pid}",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        status["state"] = "running_random_full_coverage"
        write_status(status_path, status)
        run_code = run_step(
            [
                sys.executable,
                str(args.runner),
                "run",
                "--seeds",
                "42",
                "43",
                "44",
                "--continue-on-error",
            ],
            log,
        )
        status["random_run_exit_code"] = run_code
        status["state"] = "building_report"
        write_status(status_path, status)
        report_code = run_step(
            [
                sys.executable,
                str(args.runner),
                "report",
                "--seeds",
                "42",
                "43",
                "44",
            ],
            log,
        )
        status["random_report_exit_code"] = report_code
        status["state"] = "complete" if run_code == 0 and report_code == 0 else "complete_with_issues"
        status["finished_at"] = timestamp()
        write_status(status_path, status)


if __name__ == "__main__":
    main()
