import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_DIR = Path(__file__).resolve().parent
RUN_ROOT = WORKSPACE_ROOT / "scratch" / "rq1_group_minimal" / "runs"

DEFAULT_SEED_RUN_ID = "seed-filter-mplug-f30-q454-v5"
DEFAULT_EXPECTED_SEED_ROWS = 454

OFFICIAL_CANDIDATE_SUITE = (
    RUN_ROOT / "group-seed-candidates-f30" / "results" / "official_qa_suite.jsonl"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_command(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / f"{name}.stdout.log"
    stderr_path = output_dir / f"{name}.stderr.log"
    started = time.time()
    result: dict[str, Any] = {
        "name": name,
        "command": command,
        "cwd": str(cwd),
        "timeout_seconds": timeout_seconds,
        "started_at": utc_now(),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        result.update(
            {
                "status": "completed" if completed.returncode == 0 else "failed",
                "returncode": completed.returncode,
            }
        )
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        result.update({"status": "timeout", "returncode": None})
    result["finished_at"] = utc_now()
    result["duration_seconds"] = round(time.time() - started, 3)
    return result


def seed_paths(seed_run_id: str) -> dict[str, Path]:
    seed_result_dir = RUN_ROOT / seed_run_id / "results"
    return {
        "seed_result_dir": seed_result_dir,
        "raw_results": seed_result_dir / "official_qa_suite_raw_results.jsonl",
        "seed_bank": seed_result_dir / "correct_seed_bank.jsonl",
        "seed_summary": seed_result_dir / "correct_seed_bank_summary.json",
    }


def ensure_seed_bank(
    *,
    seed_run_id: str,
    expected_seed_rows: int,
    status: dict[str, Any],
    timeout_seconds: int,
) -> bool:
    paths = seed_paths(seed_run_id)
    raw_count = count_jsonl(paths["raw_results"])
    status["seed_filter"] = {
        "run_id": seed_run_id,
        "raw_results": str(paths["raw_results"]),
        "raw_rows": raw_count,
        "expected_rows": expected_seed_rows,
    }
    if raw_count < expected_seed_rows:
        status["state"] = "waiting_seed_filter"
        status["message"] = (
            f"Seed filter has {raw_count}/{expected_seed_rows} raw rows."
        )
        return False

    if paths["seed_bank"].exists() and paths["seed_summary"].exists():
        status["seed_bank"] = read_json(paths["seed_summary"])
        return True

    command = [
        sys.executable,
        str(SCRIPT_DIR / "build_seed_bank_from_eval.py"),
        "--candidate-suite",
        str(OFFICIAL_CANDIDATE_SUITE),
        "--eval-raw-results",
        str(paths["raw_results"]),
        "--output-jsonl",
        str(paths["seed_bank"]),
        "--summary-json",
        str(paths["seed_summary"]),
    ]
    result = run_command(
        name="build_seed_bank",
        command=command,
        cwd=SCRIPT_DIR,
        output_dir=RUN_ROOT / "overnight_orchestrator" / "logs",
        timeout_seconds=timeout_seconds,
    )
    status.setdefault("commands", []).append(result)
    if result["status"] != "completed":
        status["state"] = "blocked_seed_bank"
        status["message"] = "Seed bank extraction failed or timed out."
        return False
    status["seed_bank"] = read_json(paths["seed_summary"])
    return True


def run_start_checks(
    *,
    smoke_budget: int,
    status: dict[str, Any],
    timeout_seconds: int,
) -> None:
    checks = status.setdefault("start_checks", {})
    logs_dir = RUN_ROOT / "overnight_orchestrator" / "logs"

    if "advtest_smoke" not in checks:
        checks["advtest_smoke"] = run_command(
            name="advtest_smoke",
            command=[
                sys.executable,
                str(SCRIPT_DIR / "fixed_budget_experiment.py"),
                "--generation-budget",
                str(smoke_budget),
                "--frame-pool-size",
                "3",
                "--question-load-limit",
                "50",
                "--output-dir",
                str(RUN_ROOT / "overnight_advtest_smoke" / "results"),
            ],
            cwd=SCRIPT_DIR,
            output_dir=logs_dir,
            timeout_seconds=timeout_seconds,
        )

    if "qatest_original_smoke" not in checks:
        checks["qatest_original_smoke"] = run_command(
            name="qatest_original_smoke",
            command=[sys.executable, str(WORKSPACE_ROOT / "scratch" / "test_original_qatest.py")],
            cwd=WORKSPACE_ROOT,
            output_dir=logs_dir,
            timeout_seconds=timeout_seconds,
        )

    if "qaasker_original_smoke" not in checks:
        checks["qaasker_original_smoke"] = run_command(
            name="qaasker_original_smoke",
            command=[sys.executable, str(WORKSPACE_ROOT / "scratch" / "test_original_qaasker.py")],
            cwd=WORKSPACE_ROOT,
            output_dir=logs_dir,
            timeout_seconds=timeout_seconds,
        )

    failed = {
        name: result["status"]
        for name, result in checks.items()
        if result["status"] != "completed"
    }
    if failed:
        status["state"] = "start_checks_blocked"
        status["message"] = f"Some method start checks failed: {failed}"
    else:
        status["state"] = "start_checks_completed"
        status["message"] = "Seed bank is ready and all method start checks completed."


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    status_path = args.status_json
    status = read_json(status_path)
    status.update(
        {
            "schema_version": 1,
            "updated_at": utc_now(),
            "workspace_root": str(WORKSPACE_ROOT),
            "python": sys.executable,
        }
    )
    seed_ready = ensure_seed_bank(
        seed_run_id=args.seed_run_id,
        expected_seed_rows=args.expected_seed_rows,
        status=status,
        timeout_seconds=args.command_timeout_seconds,
    )
    if seed_ready:
        run_start_checks(
            smoke_budget=args.smoke_budget,
            status=status,
            timeout_seconds=args.command_timeout_seconds,
        )
    write_json(status_path, status)
    return status


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Idempotent overnight continuation for the RQ1 seeded pipeline."
    )
    parser.add_argument("--seed-run-id", default=DEFAULT_SEED_RUN_ID)
    parser.add_argument("--expected-seed-rows", type=int, default=DEFAULT_EXPECTED_SEED_ROWS)
    parser.add_argument("--smoke-budget", type=int, default=5)
    parser.add_argument("--command-timeout-seconds", type=int, default=120)
    parser.add_argument(
        "--status-json",
        type=Path,
        default=RUN_ROOT / "overnight_orchestrator" / "status.json",
    )
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--sleep-seconds", type=int, default=900)
    parser.add_argument("--max-hours", type=float, default=12.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    stop_at = time.time() + args.max_hours * 3600
    while True:
        status = run_once(args)
        print(
            f"[overnight] {status['updated_at']} state={status.get('state')} "
            f"message={status.get('message')}",
            flush=True,
        )
        if not args.loop:
            break
        if status.get("state") in {"start_checks_completed", "start_checks_blocked"}:
            break
        if time.time() >= stop_at:
            break
        time.sleep(args.sleep_seconds)


if __name__ == "__main__":
    main()
