import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize(path: Path) -> dict:
    rows = 0
    wrong = 0
    frames = set()
    families = defaultdict(lambda: [0, 0])
    for row in iter_jsonl(path):
        rows += 1
        is_wrong = not bool(row.get("is_correct"))
        wrong += int(is_wrong)
        scene_frame = str(row.get("scene_frame") or "")
        if scene_frame:
            frames.add(scene_frame)
        family = str(row.get("family") or "unknown")
        families[family][0] += 1
        families[family][1] += int(is_wrong)

    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "rows": rows,
        "wrong": wrong,
        "error_rate": wrong / rows if rows else 0.0,
        "frames": len(frames),
        "families": {
            family: {
                "rows": values[0],
                "wrong": values[1],
                "error_rate": values[1] / values[0] if values[0] else 0.0,
            }
            for family, values in sorted(families.items())
        },
    }


def parse_source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Source must be NAME=PATH")
    name, path = value.split("=", 1)
    return name, Path(path)


def write_report(path: Path, manifest: dict) -> None:
    lines = [
        "# RQ1 Strict Open-QA Results Freeze",
        "",
        "This freezes the current strict open-ended QA scoring results before the multiple-choice variant.",
        "",
        "| Name | Rows | Wrong | Error Rate | Frames | SHA256 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name, item in manifest["sources"].items():
        lines.append(
            "| {name} | {rows} | {wrong} | {rate:.2%} | {frames} | `{sha}` |".format(
                name=name,
                rows=item["rows"],
                wrong=item["wrong"],
                rate=item["error_rate"],
                frames=item["frames"],
                sha=item["sha256"][:12],
            )
        )
    lines.extend(
        [
            "",
            "## Scoring Scope",
            "",
            "- These results use the strict open-ended QA prompts and the raw `is_correct` values already recorded in each raw result file.",
            "- This artifact is only a freeze/manifest; it does not relax synonym matching or rerun VLM inference.",
            "- The multiple-choice suites should be treated as a separate display/evaluation format built from the same questions.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze strict RQ1 raw result files.")
    parser.add_argument("--source", action="append", type=parse_source, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = {
        "format": "strict_open_qa",
        "scoring": "frozen_recorded_is_correct",
        "sources": {},
    }
    for name, path in args.source:
        if not path.exists():
            raise FileNotFoundError(path)
        manifest["sources"][name] = summarize(path)

    manifest["total_rows"] = sum(item["rows"] for item in manifest["sources"].values())
    manifest["source_count"] = len(manifest["sources"])
    manifest["row_count_distribution"] = dict(
        Counter(item["rows"] for item in manifest["sources"].values())
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "strict_results_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_report(args.output_dir / "strict_results_freeze.md", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
