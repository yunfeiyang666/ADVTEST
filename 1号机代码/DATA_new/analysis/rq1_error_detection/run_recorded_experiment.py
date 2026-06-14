import argparse
import json
import sys
from pathlib import Path

from experiment_tracking import build_manifest, run_recorded_experiment


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]


def _parse_parameter(text: str):
    key, separator, value = text.partition("=")
    if not separator or not key:
        raise argparse.ArgumentTypeError("Parameters must use key=value syntax")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value
    return key, parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a command with a reproducible experiment manifest."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--input-file", type=Path, action="append", default=[])
    parser.add_argument(
        "--parameter",
        type=_parse_parameter,
        action="append",
        default=[],
    )
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("A command is required after --")

    parameters = dict(args.parameter)
    manifest = build_manifest(
        run_id=args.run_id,
        purpose=args.purpose,
        command=command,
        workspace_root=WORKSPACE_ROOT,
        input_files=args.input_file,
        parameters=parameters,
    )
    result = run_recorded_experiment(
        run_dir=args.run_root / args.run_id,
        manifest=manifest,
        command=command,
        cwd=args.cwd,
        overwrite=args.overwrite,
    )
    print(
        f"[recorded-run] {result['run_id']} status={result['status']} "
        f"exit={result['exit_code']} duration={result['duration_seconds']:.2f}s"
    )
    if result["exit_code"]:
        raise SystemExit(result["exit_code"])


if __name__ == "__main__":
    main()
