"""Reproducible strict open-QA interface for the seeded RQ1 method suite."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
RQ1_DIR = SCRIPT_DIR.parent
WORKSPACE_ROOT = RQ1_DIR.parents[3]
DEFAULT_PYTHON = WORKSPACE_ROOT / ".venv310" / "Scripts" / "python.exe"


def iter_jsonl(path: Path) -> Iterable[dict]:
    # PowerShell-created JSONL may include a UTF-8 BOM; experiment exports do not.
    # Accept both so the assembler is portable without changing source data.
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(python: Path, script: str, args: list[str]) -> None:
    command = [str(python), str(RQ1_DIR / script), *args]
    print("[seeded-strict]", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=RQ1_DIR, check=True)


def write_bundle_manifest(output_dir: Path, budget: int) -> None:
    sources = {
        "advtest": output_dir / "advtest_suite.jsonl",
        "qatest": output_dir / "qatest_suite.jsonl",
        "qaasker": output_dir / "qaasker_suite.jsonl",
    }
    manifest = {"format": "strict_open_qa", "budget": budget, "suites": {}}
    for method, path in sources.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing strict suite for {method}: {path}")
        rows = sum(1 for _ in iter_jsonl(path))
        if rows != budget:
            raise ValueError(f"{method} has {rows} rows; expected {budget}")
        manifest["suites"][method] = {
            "path": str(path), "rows": rows, "sha256": sha256(path)
        }
    (output_dir / "strict_bundle_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed-bank", help="Build VLM-correct official seed bank.")
    add_common(seed)
    seed.add_argument("--candidate-suite", type=Path, required=True)
    seed.add_argument("--eval-raw-results", type=Path, required=True)
    seed.add_argument("--output-jsonl", type=Path, required=True)
    seed.add_argument("--summary-json", type=Path, required=True)

    adv = sub.add_parser("advtest", help="Generate the strict ADVTEST suite.")
    add_common(adv)
    adv.add_argument("--frame-cache", type=Path, required=True)
    adv.add_argument("--frame-pool-size", type=int, required=True)
    adv.add_argument("--output-dir", type=Path, required=True)
    adv.add_argument("--budget", type=int, default=6000)

    base = sub.add_parser("baselines", help="Generate strict QATest and QAAskeR suites.")
    add_common(base)
    base.add_argument("--seed-bank", type=Path, required=True)
    base.add_argument("--output-dir", type=Path, required=True)
    base.add_argument("--budget", type=int, default=6000)
    base.add_argument("--seed", type=int, default=42)
    base.add_argument("--methods", nargs="+", choices=["qatest", "qaasker"], default=["qatest", "qaasker"])
    base.add_argument("--qatest-dir", type=Path, default=WORKSPACE_ROOT / "QATest-main")
    base.add_argument("--qatest-iter-n", type=int, default=None)
    base.add_argument("--qaasker-python", type=Path, default=DEFAULT_PYTHON)
    base.add_argument("--qaasker-max-attempts", type=int, default=None)
    base.add_argument("--qaasker-use-gold-answer", action="store_true")

    bundle = sub.add_parser("assemble", help="Freeze three strict suites in one bundle.")
    bundle.add_argument("--advtest-suite", type=Path, required=True)
    bundle.add_argument("--qatest-suite", type=Path, required=True)
    bundle.add_argument("--qaasker-suite", type=Path, required=True)
    bundle.add_argument("--output-dir", type=Path, required=True)
    bundle.add_argument("--budget", type=int, default=6000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "seed-bank":
        run(args.python, "build_seed_bank_from_eval.py", [
            "--candidate-suite", str(args.candidate_suite), "--eval-raw-results", str(args.eval_raw_results),
            "--output-jsonl", str(args.output_jsonl), "--summary-json", str(args.summary_json),
        ])
    elif args.command == "advtest":
        run(args.python, "fixed_budget_experiment.py", [
            "--methods", "advtest", "--execution-mode", "presampled_frames",
            "--generation-budget", str(args.budget), "--frame-cache", str(args.frame_cache),
            "--frame-pool-size", str(args.frame_pool_size), "--output-dir", str(args.output_dir),
        ])
    elif args.command == "baselines":
        command = ["--seed-bank", str(args.seed_bank), "--output-dir", str(args.output_dir),
                   "--budget", str(args.budget), "--seed", str(args.seed), "--methods", *args.methods,
                   "--qatest-dir", str(args.qatest_dir), "--qaasker-python", str(args.qaasker_python)]
        if args.qatest_iter_n is not None:
            command += ["--qatest-iter-n", str(args.qatest_iter_n)]
        if args.qaasker_max_attempts is not None:
            command += ["--qaasker-max-attempts", str(args.qaasker_max_attempts)]
        if args.qaasker_use_gold_answer:
            command.append("--qaasker-use-gold-answer")
        run(args.python, "build_seeded_baseline_suites.py", command)
    else:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for method, source in {
            "advtest": args.advtest_suite, "qatest": args.qatest_suite, "qaasker": args.qaasker_suite
        }.items():
            target = args.output_dir / f"{method}_suite.jsonl"
            shutil.copy2(source, target)
        write_bundle_manifest(args.output_dir, args.budget)
        print(f"[seeded-strict] frozen bundle: {args.output_dir}")


if __name__ == "__main__":
    main()
