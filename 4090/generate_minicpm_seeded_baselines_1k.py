"""Generate three 1k RQ1 baselines from the MiniCPM-correct official seed bank.

QATest and QAAskeR use the original baseline adapters. Random uses the same
299 seed-derived frames as ADVTEST, with a fixed near-uniform six-family quota
and no coverage feedback. The script only generates suites; it never evaluates
the VLM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RQ1 = ROOT / "1号机代码" / "DATA_new" / "analysis" / "rq1_error_detection"
RQ3 = ROOT / "1号机代码" / "DATA_new" / "analysis" / "rq3_vlm_repair"
SEED_BANK = ROOT / "4090" / "seed_bank" / "minicpm_base_correct_seed_bank.jsonl"
OUTPUT = ROOT / "4090" / "seeded_baselines_1k_v1"
PYTHON = ROOT / ".venv310" / "Scripts" / "python.exe"

# 1000 questions, spread as evenly as possible across the six ADVTEST families.
RANDOM_QUOTAS = {
    "l0": 167,
    "l1": 167,
    "converge": 167,
    "direction_chain": 167,
    "distance_chain": 166,
    "viewpoint_transfer": 166,
}


def rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def trusted_frames() -> list[str]:
    frames = sorted({str(row.get("scene_frame") or "") for row in rows(SEED_BANK)})
    frames = [frame for frame in frames if frame]
    if len(frames) != 299:
        raise ValueError(f"Expected 299 MiniCPM seed frames, found {len(frames)}")
    return frames


def generate_original_baselines(args: argparse.Namespace) -> None:
    command = [
        str(args.python), str(RQ1 / "build_seeded_baseline_suites.py"),
        "--seed-bank", str(SEED_BANK), "--output-dir", str(OUTPUT / "strict"),
        "--budget", str(args.budget), "--seed", str(args.seed), "--methods", "qatest", "qaasker",
        "--qatest-dir", str(ROOT / "baselines" / "QATest"),
        "--qaasker-python", str(args.python),
        "--qaasker-max-attempts", str(args.qaasker_max_attempts),
    ]
    print("[seeded-1k]", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=RQ1, check=True)


def generate_random(args: argparse.Namespace) -> None:
    sys.path.insert(0, str(RQ3))
    from data_ops import build_structural_pair, file_sha256, row_scene_frame
    from config import DATAROOT, OUTPUTS_ROOT

    frame_rows = [{"scene_frame": frame} for frame in trusted_frames()]
    datasets, assignments = build_structural_pair(
        frame_rows=frame_rows,
        quotas=RANDOM_QUOTAS if args.budget == 1000 else {"l0": args.budget},
        outputs_root=OUTPUTS_ROOT,
        dataroot=DATAROOT,
        seed=args.seed,
        per_frame_candidate_limit=300,
        dataset_names=("random",),
    )
    suite = datasets["random"]
    if len(suite) != args.budget:
        raise ValueError(f"Random generated {len(suite)} rows, expected {args.budget}")
    allowed_frames = set(trusted_frames())
    if any(row_scene_frame(row) not in allowed_frames for row in suite):
        raise ValueError("Random emitted a row outside MiniCPM seed-derived frames")

    output_dir = OUTPUT / "strict"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "random_suite.jsonl"
    with output.open("w", encoding="utf-8") as handle:
        for row in suite:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    family_counts = Counter(str(row.get("family") or "") for row in suite)
    (output_dir / "random_summary.json").write_text(
        json.dumps(
            {
                "method": "random",
                "requested_budget": args.budget,
                "accepted_for_eval": len(suite),
                "seed": args.seed,
                "seed_bank": str(SEED_BANK),
                "seed_bank_sha256": sha256(SEED_BANK),
                "trusted_frame_count": len(allowed_frames),
                "family_quotas": RANDOM_QUOTAS if args.budget == 1000 else {"l0": args.budget},
                "family_counts": dict(family_counts),
                "selection": "uniform random legal candidate selection; no coverage feedback",
                "assignment_manifest": assignments,
                "suite_sha256": sha256(output),
            },
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def validate(args: argparse.Namespace) -> None:
    output_dir = OUTPUT / "strict"
    manifest = {"seed_bank": str(SEED_BANK), "seed_bank_sha256": sha256(SEED_BANK), "suites": {}}
    for method in ("qatest", "qaasker", "random"):
        path = output_dir / f"{method}_suite.jsonl"
        count = sum(1 for _ in rows(path))
        if count != args.budget:
            raise ValueError(f"{method} has {count} rows, expected {args.budget}")
        manifest["suites"][method] = {"path": str(path), "rows": count, "sha256": sha256(path)}
    (output_dir / "frozen_seeded_baseline_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, default=PYTHON)
    parser.add_argument("--budget", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--qaasker-max-attempts", type=int, default=6000)
    parser.add_argument("--skip-baselines", action="store_true")
    parser.add_argument("--skip-random", action="store_true")
    args = parser.parse_args()
    if args.budget != 1000:
        raise ValueError("This frozen RQ1 baseline launcher is intentionally fixed at 1000 questions.")
    if not args.skip_baselines:
        generate_original_baselines(args)
    if not args.skip_random:
        generate_random(args)
    validate(args)
    print(f"[seeded-1k] complete: {OUTPUT / 'strict'}", flush=True)


if __name__ == "__main__":
    main()
