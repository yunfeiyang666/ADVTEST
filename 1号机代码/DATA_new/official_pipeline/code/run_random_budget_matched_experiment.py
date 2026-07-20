"""Run coverage-blind Random with each frame's ADVTEST question count.

The fixed budget is read from the frozen ADVTEST frame summary.  Random uses
the same frame, initial seed coverage, and validated candidate space, but its
gap/plan draws are independent of coverage accumulated during the run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_frames(stats_path: Path) -> list[str]:
    import csv

    with stats_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    frames = [str(row.get("scene_frame") or "") for row in rows]
    frames = [frame for frame in frames if "_frame" in frame]
    if not frames:
        raise ValueError(f"No scene_frame values in {stats_path}")
    return sorted(dict.fromkeys(frames))


def split_scene_frame(scene_frame: str) -> tuple[str, str]:
    scene, frame = scene_frame.rsplit("_frame", 1)
    return scene, frame


def advtest_budget(outputs_root: Path, scene_frame: str) -> int:
    summary_path = outputs_root / scene_frame / "reports" / f"{scene_frame}_summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"Missing ADVTEST summary: {summary_path}")
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    budget = int(payload.get("generated") or 0)
    if budget < 1:
        raise ValueError(f"Invalid ADVTEST generated count in {summary_path}: {budget}")
    return budget


def random_summary_path(outputs_root: Path, scene_frame: str, run_id: str, seed: int) -> Path:
    return (
        outputs_root
        / scene_frame
        / "random_fixed_budget"
        / run_id
        / f"seed_{seed}"
        / "summary.json"
    )


def is_complete(path: Path, expected_budget: int) -> bool:
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return int(payload.get("draws") or -1) == expected_budget and bool(payload.get("budget_exhausted"))


def run(args: argparse.Namespace) -> int:
    frames = load_frames(args.stats)
    status_path = args.run_root / "status.json"
    completed = skipped = failed = 0
    for seed in args.seeds:
        for scene_frame in frames:
            scene_id, frame_id = split_scene_frame(scene_frame)
            try:
                budget = advtest_budget(args.outputs_root, scene_frame)
                summary_path = random_summary_path(args.outputs_root, scene_frame, args.random_run_id, seed)
                if is_complete(summary_path, budget):
                    skipped += 1
                    continue
                command = [
                    str(args.python), str(args.pipeline), "--plan", "generate",
                    "--artifact-root", str(args.outputs_root),
                    "--scene-id", scene_id, "--frame-id", frame_id,
                    "--seed", str(seed), "--selection-policy", "random_fixed_budget",
                    "--random-run-id", args.random_run_id,
                    "--question-budget", str(budget),
                    "--checkpoint-interval", str(args.checkpoint_interval),
                ]
                atomic_json(status_path, {
                    "state": "running", "current_seed": seed, "current_frame": scene_frame,
                    "current_budget": budget, "completed": completed, "skipped": skipped,
                    "failed": failed, "total": len(frames) * len(args.seeds), "command": command,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                result = subprocess.run(command, cwd=args.pipeline.parent)
                if result.returncode != 0 or not is_complete(summary_path, budget):
                    raise RuntimeError(f"pipeline returncode={result.returncode}")
                completed += 1
            except Exception as exc:  # keep a complete audit of unavailable frames
                failed += 1
                atomic_json(status_path, {
                    "state": "running", "current_seed": seed, "current_frame": scene_frame,
                    "completed": completed, "skipped": skipped, "failed": failed,
                    "total": len(frames) * len(args.seeds), "last_error": str(exc),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                if not args.continue_on_error:
                    raise
    atomic_json(status_path, {
        "state": "complete", "completed": completed, "skipped": skipped,
        "failed": failed, "total": len(frames) * len(args.seeds),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs-root", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--random-run-id", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42])
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--pipeline", type=Path, default=Path(__file__).with_name("run_gap_pipeline_v7.py"))
    parser.add_argument("--checkpoint-interval", type=int, default=50000)
    parser.add_argument("--continue-on-error", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
