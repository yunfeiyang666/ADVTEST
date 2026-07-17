"""Run and summarize the RQ2 random full-coverage baseline over all frames."""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Sequence


CODE_DIR = Path(__file__).resolve().parent
DATA_NEW_ROOT = CODE_DIR.parents[1]
WORKSPACE_ROOT = CODE_DIR.parents[3]
DEFAULT_OUTPUTS_ROOT = DATA_NEW_ROOT / "outputs"
DEFAULT_STATS = DEFAULT_OUTPUTS_ROOT / "all_frames_stats.csv"
DEFAULT_RUN_ROOT = WORKSPACE_ROOT / "scratch" / "rq2_random_full_coverage"
DEFAULT_RANDOM_RUN_ID = "rq2_formal_v2"
THRESHOLDS = (50, 75, 90, 95, 99, 100)


def _atomic_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def load_frames(stats_path: Path, *, min_nodes: int = 3) -> list[dict]:
    with stats_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    frames = []
    for row in rows:
        nodes = int(row["filtered_nodes"])
        if nodes < min_nodes:
            continue
        frames.append(
            {
                "scene_frame": row["scene_frame"],
                "filtered_nodes": nodes,
                "total_l2_gaps": int(row["total_l2_gaps"]),
            }
        )
    return sorted(frames, key=lambda row: row["scene_frame"])


def split_scene_frame(scene_frame: str) -> tuple[str, str]:
    marker = "_frame"
    if marker not in scene_frame:
        raise ValueError(f"Invalid scene_frame: {scene_frame}")
    return tuple(scene_frame.rsplit(marker, 1))  # type: ignore[return-value]


def random_summary_path(
    outputs_root: Path, scene_frame: str, seed: int, random_run_id: str
) -> Path:
    return (
        outputs_root
        / scene_frame
        / "random_full"
        / random_run_id
        / f"seed_{seed}"
        / "summary.json"
    )


def is_complete(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(payload.get("full_l2")) and float(
        ((payload.get("coverage") or {}).get("l2") or {}).get("rate", 0.0)
    ) == 1.0


def run_frames(args: argparse.Namespace) -> int:
    frames = load_frames(args.stats, min_nodes=args.min_nodes)
    if args.limit is not None:
        frames = frames[: args.limit]
    if not frames:
        raise ValueError("No valid frames selected")

    status_path = args.run_root / "status.json"
    logs_dir = args.run_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    completed = 0
    skipped = 0
    total = len(frames) * len(args.seeds)

    for seed in args.seeds:
        for frame in frames:
            scene_frame = frame["scene_frame"]
            summary_path = random_summary_path(
                args.outputs_root, scene_frame, seed, args.random_run_id
            )
            if is_complete(summary_path):
                skipped += 1
                continue
            scene_id, frame_id = split_scene_frame(scene_frame)
            prepare_command = [
                sys.executable,
                str(CODE_DIR / "run_gap_pipeline_v7.py"),
                "--plan",
                "prepare_initial_coverage",
                "--artifact-root",
                str(args.outputs_root),
                "--scene-id",
                scene_id,
                "--frame-id",
                frame_id,
            ]
            command = [
                sys.executable,
                str(CODE_DIR / "run_gap_pipeline_v7.py"),
                "--plan",
                "generate",
                "--artifact-root",
                str(args.outputs_root),
                "--scene-id",
                scene_id,
                "--frame-id",
                frame_id,
                "--seed",
                str(seed),
                "--selection-policy",
                "random_full",
                "--random-run-id",
                args.random_run_id,
                "--checkpoint-interval",
                str(args.checkpoint_interval),
            ]
            log_path = logs_dir / f"seed_{seed}_{scene_frame}.log"
            _atomic_json(
                status_path,
                {
                    "state": "running",
                    "current_seed": seed,
                    "current_frame": scene_frame,
                    "completed": completed,
                    "skipped": skipped,
                    "failed": len(failures),
                    "total": total,
                    "command": command,
                },
            )
            with log_path.open("a", encoding="utf-8") as log_handle:
                log_handle.write("$ " + " ".join(prepare_command) + "\n")
                prepared = subprocess.run(
                    prepare_command,
                    cwd=CODE_DIR,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                if prepared.returncode != 0:
                    result = prepared
                else:
                    log_handle.write("$ " + " ".join(command) + "\n")
                    result = subprocess.run(
                        command,
                        cwd=CODE_DIR,
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
            if result.returncode == 0 and is_complete(summary_path):
                completed += 1
                continue
            failure = {
                "seed": seed,
                "scene_frame": scene_frame,
                "returncode": result.returncode,
                "log": str(log_path),
            }
            failures.append(failure)
            if not args.continue_on_error:
                _atomic_json(
                    status_path,
                    {
                        "state": "failed",
                        "completed": completed,
                        "skipped": skipped,
                        "total": total,
                        "failures": failures,
                    },
                )
                return 2

    _atomic_json(
        status_path,
        {
            "state": "complete" if not failures else "complete_with_failures",
            "completed": completed,
            "skipped": skipped,
            "total": total,
            "failures": failures,
        },
    )
    return 0 if not failures else 2


def size_group(nodes: int) -> str:
    if nodes <= 15:
        return "S(3-15)"
    if nodes <= 30:
        return "M(16-30)"
    return "L(>=31)"


def _mean(values: Iterable[float]) -> float | None:
    materialized = list(values)
    return statistics.fmean(materialized) if materialized else None


def _seed_group_summary(rows: Sequence[dict]) -> dict:
    result: Dict[str, Any] = {
        "frames": len(rows),
        "draws_mean": _mean(float(row["draws"]) for row in rows),
        "draws_total": sum(int(row["draws"]) for row in rows),
        "gap_duplicate_rate": _mean(float(row["gap_duplicate_rate"]) for row in rows),
        "plan_duplicate_rate": _mean(float(row["plan_duplicate_rate"]) for row in rows),
        "text_duplicate_rate": _mean(float(row["text_duplicate_rate"]) for row in rows),
        "no_gain_rate": _mean(float(row["no_gain_rate"]) for row in rows),
        "l2_tail_questions_95_to_100": _mean(
            float(row["l2_tail_questions_95_to_100"])
            for row in rows
            if row.get("l2_tail_questions_95_to_100") is not None
        ),
    }
    for level in ("l0", "l1", "l2"):
        result[f"{level}_initial_rate"] = _mean(
            float(row[f"{level}_initial_rate"]) for row in rows
        )
        result[f"{level}_final_rate"] = _mean(
            float(row[f"{level}_final_rate"]) for row in rows
        )
        result[f"{level}_auc"] = _mean(float(row[f"{level}_auc"]) for row in rows)
        for threshold in THRESHOLDS:
            key = f"{level}_q{threshold}"
            result[key] = _mean(
                float(row[key]) for row in rows if row.get(key) is not None
            )
    return result


def _ci95(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    return 1.96 * statistics.stdev(values) / math.sqrt(len(values))


def build_report(args: argparse.Namespace) -> int:
    frames = load_frames(args.stats, min_nodes=args.min_nodes)
    frame_rows = []
    missing = []
    for seed in args.seeds:
        for frame in frames:
            scene_frame = frame["scene_frame"]
            path = random_summary_path(
                args.outputs_root, scene_frame, seed, args.random_run_id
            )
            if not is_complete(path):
                missing.append({"seed": seed, "scene_frame": scene_frame})
                continue
            summary = json.loads(path.read_text(encoding="utf-8"))
            row: Dict[str, Any] = {
                "seed": seed,
                "scene_frame": scene_frame,
                "filtered_nodes": frame["filtered_nodes"],
                "group": size_group(frame["filtered_nodes"]),
                "draws": summary["draws"],
                "gap_duplicate_rate": summary["gap_duplicate_rate"],
                "plan_duplicate_rate": summary["plan_duplicate_rate"],
                "text_duplicate_rate": summary["text_duplicate_rate"],
                "no_gain_rate": summary["no_gain_rate"],
                "l2_tail_questions_95_to_100": summary.get(
                    "l2_tail_questions_95_to_100"
                ),
            }
            for level in ("l0", "l1", "l2"):
                row[f"{level}_initial_rate"] = summary["initial_coverage"][level]["rate"]
                row[f"{level}_final_rate"] = summary["coverage"][level]["rate"]
                row[f"{level}_auc"] = summary["coverage"][level]["auc_over_draws"]
                marks = (summary.get("milestones") or {}).get(level, {})
                for threshold in THRESHOLDS:
                    row[f"{level}_q{threshold}"] = marks.get(str(threshold))
            frame_rows.append(row)

    args.report_dir.mkdir(parents=True, exist_ok=True)
    frame_csv = args.report_dir / "random_full_frame_metrics.csv"
    if frame_rows:
        with frame_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(frame_rows[0]))
            writer.writeheader()
            writer.writerows(frame_rows)

    grouped: Dict[tuple[int, str], list[dict]] = defaultdict(list)
    for row in frame_rows:
        grouped[(int(row["seed"]), row["group"])].append(row)
        grouped[(int(row["seed"]), "All")].append(row)
    seed_group_rows = []
    for (seed, group), rows in sorted(grouped.items()):
        seed_group_rows.append(
            {"seed": seed, "group": group, **_seed_group_summary(rows)}
        )

    across: Dict[str, list[dict]] = defaultdict(list)
    for row in seed_group_rows:
        across[row["group"]].append(row)
    aggregate_rows = []
    metric_keys = [
        key
        for key in seed_group_rows[0]
        if key not in {"seed", "group", "frames"}
    ] if seed_group_rows else []
    for group, rows in sorted(across.items()):
        aggregate: Dict[str, Any] = {"group": group, "seeds": len(rows)}
        for key in metric_keys:
            values = [float(row[key]) for row in rows if row.get(key) is not None]
            aggregate[f"{key}_mean"] = _mean(values)
            aggregate[f"{key}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
            aggregate[f"{key}_ci95"] = _ci95(values)
        aggregate_rows.append(aggregate)

    payload = {
        "schema": "rq2_random_full_coverage_report_v1",
        "random_run_id": args.random_run_id,
        "expected_frames": len(frames),
        "seeds": args.seeds,
        "completed_frame_runs": len(frame_rows),
        "missing_frame_runs": missing,
        "seed_group_metrics": seed_group_rows,
        "aggregate_metrics": aggregate_rows,
        "frame_metrics_csv": str(frame_csv),
    }
    _atomic_json(args.report_dir / "random_full_report.json", payload)
    return 0 if not missing else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "report"):
        child = subparsers.add_parser(name)
        child.add_argument("--outputs-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
        child.add_argument("--stats", type=Path, default=DEFAULT_STATS)
        child.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44])
        child.add_argument("--random-run-id", default=DEFAULT_RANDOM_RUN_ID)
        child.add_argument("--min-nodes", type=int, default=3)
        if name == "run":
            child.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
            child.add_argument("--checkpoint-interval", type=int, default=1000)
            child.add_argument("--limit", type=int, default=None)
            child.add_argument("--continue-on-error", action="store_true")
        else:
            child.add_argument(
                "--report-dir", type=Path, default=DEFAULT_RUN_ROOT / "reports"
            )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run_frames(args) if args.command == "run" else build_report(args)


if __name__ == "__main__":
    raise SystemExit(main())
