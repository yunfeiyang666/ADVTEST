"""Continue RQ1 seed expansion once enough VLM-correct seeds are available."""

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


WORKSPACE_ROOT = Path(__file__).absolute().parents[4]
SCRIPT_DIR = Path(__file__).absolute().parent
DEFAULT_PYTHON = WORKSPACE_ROOT / ".venv310" / "Scripts" / "python.exe"
DEFAULT_RUN_ROOT = WORKSPACE_ROOT / "scratch" / "rq1_seed_expansion" / "runs"


def iter_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def count_eval_rows(path: Path) -> dict:
    total = 0
    correct = 0
    last_question_index = None
    for row in iter_jsonl(path):
        total += 1
        if row.get("is_correct") is True:
            correct += 1
        last_question_index = row.get("question_index")
    return {
        "eval_rows": total,
        "correct_rows": correct,
        "last_question_index": last_question_index,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_recorded(
    *,
    python: Path,
    run_root: Path,
    run_id: str,
    purpose: str,
    input_files: list[Path],
    parameters: dict,
    command: list[str],
) -> None:
    args = [
        str(python),
        str(SCRIPT_DIR / "run_recorded_experiment.py"),
        "--run-id",
        run_id,
        "--purpose",
        purpose,
        "--run-root",
        str(run_root),
        "--cwd",
        str(SCRIPT_DIR),
        "--overwrite",
    ]
    for input_file in input_files:
        args.extend(["--input-file", str(input_file)])
    for key, value in parameters.items():
        args.extend(["--parameter", f"{key}={json.dumps(value)}"])
    args.append("--")
    args.extend(command)
    subprocess.run(args, cwd=SCRIPT_DIR, check=True)


def build_seed_bank(args: argparse.Namespace) -> Path:
    output_dir = args.run_root / args.seedbank_run_id / "results"
    output_jsonl = output_dir / "correct_seed_bank.jsonl"
    summary_json = output_dir / "correct_seed_bank_summary.json"
    command = [
        str(args.python),
        str(SCRIPT_DIR / "build_seed_bank_from_eval.py"),
        "--candidate-suite",
        str(args.candidate_suite),
        "--eval-raw-results",
        str(args.eval_raw_results),
        "--output-jsonl",
        str(output_jsonl),
        "--summary-json",
        str(summary_json),
    ]
    run_recorded(
        python=args.python,
        run_root=args.run_root,
        run_id=args.seedbank_run_id,
        purpose="RQ1_build_expanded_correct_seed_bank_from_live_mPLUG_results",
        input_files=[args.candidate_suite, args.eval_raw_results],
        parameters={"seed_threshold": args.seed_threshold},
        command=command,
    )
    return output_jsonl


def run_advtest(args: argparse.Namespace) -> None:
    output_dir = args.run_root / args.advtest_run_id / "results"
    command = [
        str(args.python),
        str(SCRIPT_DIR / "fixed_budget_experiment.py"),
        "--methods",
        "advtest",
        "--execution-mode",
        "presampled_frames",
        "--generation-budget",
        str(args.budget),
        "--frame-cache",
        str(args.frame_cache),
        "--frame-pool-size",
        str(args.frame_pool_size),
        "--output-dir",
        str(output_dir),
    ]
    run_recorded(
        python=args.python,
        run_root=args.run_root,
        run_id=args.advtest_run_id,
        purpose="RQ1_ADVTEST_expanded_frame_pool_1000_question_suite",
        input_files=[args.frame_cache],
        parameters={
            "budget": args.budget,
            "frame_pool_size": args.frame_pool_size,
            "execution_mode": "presampled_frames",
        },
        command=command,
    )


def run_seeded_baselines(args: argparse.Namespace, seed_bank: Path) -> None:
    output_dir = args.run_root / args.baselines_run_id / "results"
    command = [
        str(args.python),
        str(SCRIPT_DIR / "build_seeded_baseline_suites.py"),
        "--seed-bank",
        str(seed_bank),
        "--output-dir",
        str(output_dir),
        "--budget",
        str(args.budget),
        "--methods",
        "qatest",
        "qaasker",
        "--qaasker-max-attempts",
        str(args.qaasker_max_attempts),
    ]
    run_recorded(
        python=args.python,
        run_root=args.run_root,
        run_id=args.baselines_run_id,
        purpose="RQ1_seeded_QATest_QAAskeR_expanded_seed_bank_1000_suites",
        input_files=[seed_bank],
        parameters={
            "budget": args.budget,
            "qaasker_max_attempts": args.qaasker_max_attempts,
        },
        command=command,
    )


def assemble_three_method_suites(args: argparse.Namespace) -> dict:
    output_dir = args.run_root / args.assembly_run_id / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "advtest": args.run_root / args.advtest_run_id / "results" / "advtest_suite.jsonl",
        "qatest": args.run_root / args.baselines_run_id / "results" / "qatest_suite.jsonl",
        "qaasker": args.run_root / args.baselines_run_id / "results" / "qaasker_suite.jsonl",
    }
    manifest = {
        "schema_version": 1,
        "assembled_at": now_iso(),
        "budget": args.budget,
        "suites": {},
    }
    for method, source in sources.items():
        target = output_dir / f"{method}_suite.jsonl"
        shutil.copy2(source, target)
        manifest["suites"][method] = {
            "source": str(source),
            "target": str(target),
            "source_sha256": sha256_file(source),
            "target_sha256": sha256_file(target),
            "bytes": target.stat().st_size,
        }
    write_json(output_dir / "assembly_manifest.json", manifest)
    return manifest


def update_status(path: Path, **fields) -> None:
    status = read_json(path)
    status.update(fields)
    status["updated_at"] = now_iso()
    write_json(path, status)


def wait_for_threshold(args: argparse.Namespace, status_path: Path) -> dict:
    started = time.time()
    while True:
        counts = count_eval_rows(args.eval_raw_results)
        manifest = read_json(args.seed_filter_manifest)
        seed_filter_status = manifest.get("status")
        enough = counts["correct_rows"] >= args.seed_threshold
        completed = seed_filter_status in {"completed", "failed"}
        update_status(
            status_path,
            state="waiting_for_seed_threshold",
            seed_filter_status=seed_filter_status,
            **counts,
            seed_threshold=args.seed_threshold,
        )
        if enough:
            return counts
        if completed:
            if counts["correct_rows"] < args.seed_threshold:
                raise RuntimeError(
                    "seed filter finished before reaching threshold: "
                    f"{counts['correct_rows']} < {args.seed_threshold}"
                )
            return counts
        if args.max_wait_seconds and time.time() - started > args.max_wait_seconds:
            raise TimeoutError("timed out waiting for seed threshold")
        time.sleep(args.poll_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wait for expanded seed threshold, then build three RQ1 suites."
    )
    parser.add_argument("--candidate-suite", required=True, type=Path)
    parser.add_argument("--eval-raw-results", required=True, type=Path)
    parser.add_argument("--seed-filter-manifest", required=True, type=Path)
    parser.add_argument("--frame-cache", required=True, type=Path)
    parser.add_argument("--frame-pool-size", required=True, type=int)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--seed-threshold", type=int, default=1000)
    parser.add_argument("--budget", type=int, default=1000)
    parser.add_argument("--qaasker-max-attempts", type=int, default=6000)
    parser.add_argument("--poll-seconds", type=int, default=120)
    parser.add_argument("--max-wait-seconds", type=int, default=0)
    parser.add_argument(
        "--status-json",
        type=Path,
        default=DEFAULT_RUN_ROOT / "seed-expansion-threshold-monitor" / "status.json",
    )
    parser.add_argument(
        "--seedbank-run-id",
        default="expanded-seedbank-threshold1000-v1",
    )
    parser.add_argument(
        "--advtest-run-id",
        default="advtest-expanded-f308-q1000-v1",
    )
    parser.add_argument(
        "--baselines-run-id",
        default="seeded-baselines-expanded-threshold1000-q1000-v1",
    )
    parser.add_argument(
        "--assembly-run-id",
        default="seeded-three-method-suites-expanded-q1000-v1",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.run_root.mkdir(parents=True, exist_ok=True)
    update_status(args.status_json, state="started", started_at=now_iso())
    try:
        counts = wait_for_threshold(args, args.status_json)
        update_status(args.status_json, state="building_seed_bank", **counts)
        seed_bank = build_seed_bank(args)
        seed_summary = read_json(
            args.run_root
            / args.seedbank_run_id
            / "results"
            / "correct_seed_bank_summary.json"
        )
        update_status(
            args.status_json,
            state="running_advtest",
            seed_bank=str(seed_bank),
            seed_summary=seed_summary,
        )
        run_advtest(args)
        update_status(args.status_json, state="running_seeded_baselines")
        run_seeded_baselines(args, seed_bank)
        update_status(args.status_json, state="assembling_three_method_suites")
        assembly = assemble_three_method_suites(args)
        update_status(args.status_json, state="completed", assembly=assembly)
        print(f"[seed-expansion-monitor] completed suites={args.assembly_run_id}")
    except Exception as exc:
        update_status(args.status_json, state="failed", error=f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
