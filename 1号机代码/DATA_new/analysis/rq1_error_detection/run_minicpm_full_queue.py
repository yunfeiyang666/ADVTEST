"""Serially gate the full frozen RQ1 MiniCPM base/adapter evaluations."""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def write_status(path: Path, **updates: object) -> None:
    existing = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    existing.update(updates)
    existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def first_raw_result(path: Path) -> dict | None:
    if not path.is_file() or not path.read_text(encoding="utf-8").strip():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.loads(next(line for line in handle if line.strip()))


def run_logged(command: list[str], log_path: Path) -> int:
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    return completed.returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--adapter-path", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--outputs-root", type=Path, required=True)
    parser.add_argument("--dataroot", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()

    args.run_root.mkdir(parents=True, exist_ok=True)
    status_path = args.run_root / "queue_status.json"
    base_smoke_raw = args.run_root / "smokes" / "base_l0_limit1" / "advtest_l0_suite_raw_results.jsonl"
    write_status(status_path, state="waiting_for_base_smoke", base_smoke_raw=str(base_smoke_raw))

    while True:
        raw = first_raw_result(base_smoke_raw)
        if raw is not None:
            if raw.get("mode") != "MINICPM":
                write_status(status_path, state="failed", reason="base smoke was not real MINICPM")
                return
            break
        time.sleep(args.poll_seconds)

    adapter_smoke_dir = args.run_root / "smokes" / "adapter_l0_limit1"
    adapter_smoke_dir.mkdir(parents=True, exist_ok=True)
    adapter_smoke = [
        str(args.python), "-u", str(args.runner), "--suite-manifest", str(args.manifest),
        "--methods", "advtest_l0", "--output-dir", str(adapter_smoke_dir),
        "--outputs-root", str(args.outputs_root), "--dataroot", str(args.dataroot),
        "--mode", "MINICPM", "--model-path", str(args.model_path),
        "--adapter-path", str(args.adapter_path), "--limit", "1",
    ]
    write_status(status_path, state="running_adapter_smoke")
    if run_logged(adapter_smoke, args.run_root / "adapter_smoke.log") != 0:
        write_status(status_path, state="failed", reason="adapter smoke command failed")
        return
    adapter_raw = first_raw_result(adapter_smoke_dir / "advtest_l0_suite_raw_results.jsonl")
    if adapter_raw is None or adapter_raw.get("mode") != "MINICPM":
        write_status(status_path, state="failed", reason="adapter smoke produced no real result")
        return

    base_output = args.run_root / "base_full"
    base_command = [
        str(args.python), "-u", str(args.runner), "--suite-manifest", str(args.manifest),
        "--output-dir", str(base_output), "--outputs-root", str(args.outputs_root),
        "--dataroot", str(args.dataroot), "--mode", "MINICPM",
        "--model-path", str(args.model_path), "--resume",
    ]
    write_status(status_path, state="running_base_full", base_output=str(base_output))
    if run_logged(base_command, args.run_root / "base_full.log") != 0:
        write_status(status_path, state="failed", reason="base full command failed")
        return

    adapter_output = args.run_root / "adapter_full"
    adapter_command = [
        str(args.python), "-u", str(args.runner), "--suite-manifest", str(args.manifest),
        "--output-dir", str(adapter_output), "--outputs-root", str(args.outputs_root),
        "--dataroot", str(args.dataroot), "--mode", "MINICPM",
        "--model-path", str(args.model_path), "--adapter-path", str(args.adapter_path), "--resume",
    ]
    write_status(status_path, state="running_adapter_full", adapter_output=str(adapter_output))
    if run_logged(adapter_command, args.run_root / "adapter_full.log") != 0:
        write_status(status_path, state="failed", reason="adapter full command failed")
        return
    write_status(status_path, state="complete")


if __name__ == "__main__":
    main()
