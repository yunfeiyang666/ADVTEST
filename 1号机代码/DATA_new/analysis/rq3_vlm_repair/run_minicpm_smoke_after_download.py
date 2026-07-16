"""Wait for the MiniCPM download, then run the guarded local smoke pipeline."""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_RUN_DIR = Path(
    "E:/Project/ADVTEST/scratch/rq3_vlm_repair/runs/minicpm_o_2_6_pilot_smoke_v1"
)
DEFAULT_TRAINER = Path(
    "E:/Project/ADVTEST/1号机代码/DATA_new/analysis/rq3_vlm_repair/"
    "run_minicpm_training.py"
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_step(command: list[str], log) -> None:
    log.write("$ " + subprocess.list2cmdline(command) + "\n")
    log.flush()
    subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, text=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-pid", type=int, required=True)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--trainer", type=Path, default=DEFAULT_TRAINER)
    args = parser.parse_args()

    args.run_dir.mkdir(parents=True, exist_ok=True)
    status_path = args.run_dir / "pipeline_status.json"
    status = {
        "schema_version": "rq3_minicpm_smoke_pipeline_v1",
        "download_pid": args.download_pid,
        "started_at": now(),
        "state": "waiting_for_download",
    }
    status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    log_path = args.run_dir / "pipeline.log"
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        try:
            run_step(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    f"Wait-Process -Id {args.download_pid}",
                ],
                log,
            )
            status["state"] = "preflight"
            status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
            run_step([sys.executable, str(args.trainer), "preflight"], log)
            status["state"] = "training"
            status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
            run_step([sys.executable, str(args.trainer), "launch"], log)
            status["state"] = "verifying"
            status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
            run_step([sys.executable, str(args.trainer), "verify"], log)
            status["state"] = "complete"
        except subprocess.CalledProcessError as error:
            status["state"] = "failed"
            status["failed_command"] = error.cmd
            status["exit_code"] = error.returncode
            raise
        finally:
            status["finished_at"] = now()
            status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
