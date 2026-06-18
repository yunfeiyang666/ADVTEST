"""Start the formal three-method VLM run once expanded suites are assembled."""

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


WORKSPACE_ROOT = Path(__file__).absolute().parents[4]
SCRIPT_DIR = Path(__file__).absolute().parent
DEFAULT_PYTHON = WORKSPACE_ROOT / ".venv310" / "Scripts" / "python.exe"
DEFAULT_RUN_ROOT = WORKSPACE_ROOT / "scratch" / "rq1_seed_expansion" / "runs"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def jsonl_line_count(path: Path) -> int:
    return sum(1 for _ in iter_jsonl(path))


def update_status(path: Path, **fields) -> None:
    status = read_json(path)
    status.update(fields)
    status["updated_at"] = now_iso()
    write_json(path, status)


def suite_paths(suite_dir: Path) -> dict[str, Path]:
    return {
        "advtest": suite_dir / "advtest_suite.jsonl",
        "qatest": suite_dir / "qatest_suite.jsonl",
        "qaasker": suite_dir / "qaasker_suite.jsonl",
    }


def validate_suites(suite_dir: Path, expected_rows: int) -> dict:
    details = {}
    for method, path in suite_paths(suite_dir).items():
        if not path.exists():
            raise FileNotFoundError(f"missing {method} suite: {path}")
        rows = jsonl_line_count(path)
        if rows != expected_rows:
            raise ValueError(f"{method} suite has {rows} rows, expected {expected_rows}")
        details[method] = {"path": str(path), "rows": rows}
    return details


def correct_count(raw_results: Path) -> int:
    if not raw_results.exists():
        return 0
    return sum(1 for row in iter_jsonl(raw_results) if row.get("is_correct") is True)


def stop_seed_filter(seed_filter_run_id: str) -> list[dict]:
    """Stop the seed-filter command line once the required seed threshold is met."""

    escaped = seed_filter_run_id.replace("'", "''")
    command = f"""
$procs = Get-CimInstance Win32_Process |
  Where-Object {{ $_.CommandLine -like '*{escaped}*' }}
$stopped = @()
foreach ($proc in $procs) {{
  try {{
    Stop-Process -Id $proc.ProcessId -Force
    $stopped += [pscustomobject]@{{
      process_id = $proc.ProcessId
      command_line = $proc.CommandLine
      stopped = $true
    }}
  }} catch {{
    $stopped += [pscustomobject]@{{
      process_id = $proc.ProcessId
      command_line = $proc.CommandLine
      stopped = $false
      error = $_.Exception.Message
    }}
  }}
}}
$stopped | ConvertTo-Json -Depth 3
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        return []
    payload = json.loads(result.stdout)
    if isinstance(payload, dict):
        return [payload]
    return list(payload)


def run_recorded_formal_eval(args: argparse.Namespace, suite_details: dict) -> None:
    suite_dir = args.assembly_dir
    output_dir = args.run_root / args.formal_run_id / "results"
    command = [
        str(args.python),
        str(SCRIPT_DIR / "run_suite_evaluation.py"),
        "--mode",
        "MPLUG",
        "--suite-dir",
        str(suite_dir),
        "--output-dir",
        str(output_dir),
        "--methods",
        "advtest",
        "qatest",
        "qaasker",
        "--vlm-call-budget",
        str(args.vlm_call_budget),
    ]
    recorded = [
        str(args.python),
        str(SCRIPT_DIR / "run_recorded_experiment.py"),
        "--run-id",
        args.formal_run_id,
        "--purpose",
        "RQ1_formal_mPLUG_evaluation_three_expanded_seeded_suites",
        "--run-root",
        str(args.run_root),
        "--cwd",
        str(SCRIPT_DIR),
        "--overwrite",
        "--parameter",
        f"vlm_call_budget={args.vlm_call_budget}",
        "--parameter",
        f"suite_rows={json.dumps({k: v['rows'] for k, v in suite_details.items()})}",
    ]
    for path in suite_paths(suite_dir).values():
        recorded.extend(["--input-file", str(path)])
    recorded.append("--")
    recorded.extend(command)
    subprocess.run(recorded, cwd=SCRIPT_DIR, check=True)


def wait_for_assembly(args: argparse.Namespace, status_path: Path) -> dict:
    started = time.time()
    while True:
        monitor = read_json(args.seed_monitor_status)
        assembly_manifest = args.assembly_dir / "assembly_manifest.json"
        update_status(
            status_path,
            state="waiting_for_assembly",
            seed_monitor_state=monitor.get("state"),
            seed_monitor_updated_at=monitor.get("updated_at"),
            assembly_manifest=str(assembly_manifest),
        )
        if assembly_manifest.exists():
            return read_json(assembly_manifest)
        if args.max_wait_seconds and time.time() - started > args.max_wait_seconds:
            raise TimeoutError("timed out waiting for assembled suites")
        time.sleep(args.poll_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wait for expanded suites, then start formal mPLUG evaluation."
    )
    parser.add_argument("--assembly-dir", required=True, type=Path)
    parser.add_argument("--seed-monitor-status", required=True, type=Path)
    parser.add_argument("--seed-filter-run-id", required=True)
    parser.add_argument("--seed-filter-raw-results", required=True, type=Path)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--formal-run-id", default="mplug-expanded-three-method-q1000-v1")
    parser.add_argument("--status-json", required=True, type=Path)
    parser.add_argument("--seed-threshold", type=int, default=1000)
    parser.add_argument("--expected-suite-rows", type=int, default=1000)
    parser.add_argument("--vlm-call-budget", type=int, default=1000)
    parser.add_argument("--poll-seconds", type=int, default=120)
    parser.add_argument("--max-wait-seconds", type=int, default=0)
    parser.add_argument(
        "--stop-seed-filter",
        action="store_true",
        help="Stop the seed-filter process after the threshold is satisfied.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    update_status(args.status_json, state="started", started_at=now_iso())
    try:
        assembly = wait_for_assembly(args, args.status_json)
        update_status(args.status_json, state="validating_suites", assembly=assembly)
        suite_details = validate_suites(args.assembly_dir, args.expected_suite_rows)
        stopped = []
        if args.stop_seed_filter:
            seeds = correct_count(args.seed_filter_raw_results)
            if seeds >= args.seed_threshold:
                update_status(
                    args.status_json,
                    state="stopping_seed_filter",
                    correct_seed_count=seeds,
                )
                stopped = stop_seed_filter(args.seed_filter_run_id)
            else:
                raise RuntimeError(
                    f"cannot stop seed filter before threshold: {seeds} < {args.seed_threshold}"
                )
        update_status(
            args.status_json,
            state="running_formal_eval",
            suite_details=suite_details,
            stopped_seed_filter_processes=stopped,
        )
        run_recorded_formal_eval(args, suite_details)
        formal_manifest = read_json(args.run_root / args.formal_run_id / "manifest.json")
        update_status(
            args.status_json,
            state="completed",
            formal_manifest=formal_manifest,
        )
        print(f"[formal-eval-monitor] completed run={args.formal_run_id}")
    except Exception as exc:
        update_status(args.status_json, state="failed", error=f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
