"""Choice-suite conversion and evaluation interface for frozen seeded RQ1 rows."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RQ1_DIR = SCRIPT_DIR.parent
WORKSPACE_ROOT = RQ1_DIR.parents[3]
DEFAULT_PYTHON = WORKSPACE_ROOT / ".venv310" / "Scripts" / "python.exe"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(python: Path, script: str, args: list[str]) -> None:
    command = [str(python), str(RQ1_DIR / script), *args]
    print("[seeded-choice]", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=RQ1_DIR, check=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    convert = sub.add_parser("convert", help="Convert frozen strict suites; never regenerate source questions.")
    convert.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    convert.add_argument("--strict-dir", type=Path, required=True)
    convert.add_argument("--output-dir", type=Path, required=True)
    convert.add_argument("--outputs-root", type=Path, default=WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "outputs")
    convert.add_argument("--seed", type=int, default=20260707)
    convert.add_argument("--methods", nargs="+", choices=["advtest", "qatest", "qaasker"], default=["advtest", "qatest", "qaasker"])

    direct = sub.add_parser("evaluate-advtest", help="Direct choice evaluation for ADVTEST only.")
    direct.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    direct.add_argument("--suite-dir", type=Path, required=True)
    direct.add_argument("--output-dir", type=Path, required=True)
    direct.add_argument("--mode", required=True, choices=["MOCK", "LOCAL_GPU", "API", "MPLUG", "MINICPM"])
    direct.add_argument("--limit", type=int, default=0)

    two = sub.add_parser("evaluate-baselines", help="Free answer then option mapping for QATest/QAAskeR.")
    two.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    two.add_argument("--suite-dir", type=Path, required=True)
    two.add_argument("--output-dir", type=Path, required=True)
    two.add_argument("--mode", required=True, choices=["MOCK", "LOCAL_GPU", "API", "MPLUG", "MINICPM"])
    two.add_argument("--limit", type=int, default=0)
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "convert":
        args.output_dir.mkdir(parents=True, exist_ok=True)
        command = ["--output-dir", str(args.output_dir), "--outputs-root", str(args.outputs_root), "--seed", str(args.seed)]
        manifest = {"format": "choice_from_frozen_strict", "sources": {}}
        for method in args.methods:
            source = args.strict_dir / f"{method}_suite.jsonl"
            if not source.exists():
                raise FileNotFoundError(f"Missing strict source: {source}")
            command += ["--source", f"{method}={source}"]
            manifest["sources"][method] = {"path": str(source), "sha256": sha256(source)}
        run(args.python, "build_choice_suites.py", command)
        (args.output_dir / "choice_source_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    elif args.command == "evaluate-advtest":
        command = ["--suite-dir", str(args.suite_dir), "--output-dir", str(args.output_dir),
                   "--mode", args.mode, "--methods", "advtest_choice"]
        if args.limit:
            command += ["--limit", str(args.limit)]
        run(args.python, "run_suite_evaluation.py", command)
    else:
        command = ["--suite-dir", str(args.suite_dir), "--output-dir", str(args.output_dir),
                   "--mode", args.mode, "--methods", "qatest_choice", "qaasker_choice"]
        if args.limit:
            command += ["--limit", str(args.limit)]
        run(args.python, "run_two_step_choice_evaluation.py", command)


if __name__ == "__main__":
    main()
