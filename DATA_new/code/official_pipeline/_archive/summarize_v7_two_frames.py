from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any, Dict, List


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def frame_paths(root: Path, frame: str) -> Dict[str, Path]:
    return {
        "qa": root / frame / "generation" / "qa" / f"{frame}_generated.jsonl",
        "summary": root / frame / "generation" / "summary" / f"{frame}_summary.json",
        "coverage": root / frame / "coverage" / f"{frame}_coverage_state.json",
        "status": root / frame / "plan_status.json",
    }


def summarize_frame(root: Path, frame: str) -> Dict[str, Any]:
    paths = frame_paths(root, frame)
    rows = read_jsonl(paths["qa"])
    fam = collections.Counter(r.get("template_id") for r in rows)
    verify = collections.Counter(r.get("logic_verification") for r in rows)
    backend = collections.Counter(r.get("generation_backend") for r in rows)
    answer_types = collections.Counter(r.get("answer_type") for r in rows)
    coverage_l0 = set()
    coverage_l1 = set()
    coverage_l2 = set()
    examples = []
    for r in rows:
        coverage_l0.update(r.get("coverage_l0") or (r.get("coverage_footprint") or {}).get("l0") or [])
        coverage_l1.update(r.get("coverage_l1") or (r.get("coverage_footprint") or {}).get("l1") or [])
        coverage_l2.update(r.get("coverage_l2") or (r.get("coverage_footprint") or {}).get("l2") or [])
        if len(examples) < 5:
            examples.append({
                "template_id": r.get("template_id"),
                "question": r.get("question"),
                "answer": r.get("answer"),
                "logic_verification": r.get("logic_verification"),
            })
    return {
        "frame": frame,
        "generated": len(rows),
        "families": dict(fam),
        "verification": dict(verify),
        "backend": dict(backend),
        "answer_types": dict(answer_types),
        "coverage": {"l0": len(coverage_l0), "l1": len(coverage_l1), "l2": len(coverage_l2)},
        "qa_path": str(paths["qa"]),
        "examples": examples,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-root", default="outputs/v7_formal_test")
    ap.add_argument("--frames", nargs="+", default=["scene-0103_frame0", "scene-0103_frame3"])
    ap.add_argument("--out", default="outputs/v7_formal_test/two_frame_report.json")
    args = ap.parse_args()
    root = Path(args.artifact_root)
    frames = [summarize_frame(root, f) for f in args.frames]
    total_families = collections.Counter()
    total_verify = collections.Counter()
    total_backend = collections.Counter()
    for item in frames:
        total_families.update(item["families"])
        total_verify.update(item["verification"])
        total_backend.update(item["backend"])
    report = {
        "artifact_root": str(root),
        "frames": frames,
        "total": {
            "generated": sum(f["generated"] for f in frames),
            "families": dict(total_families),
            "verification": dict(total_verify),
            "backend": dict(total_backend),
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

