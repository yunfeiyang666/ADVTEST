import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_RUNS_ROOT = (
    Path(__file__).resolve().parents[4] / "scratch" / "rq1_seed_expansion" / "runs"
)


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def summarize_raw(label: str, raw_path: Path, group: str) -> tuple[dict, list[dict]]:
    total = 0
    wrong = 0
    frames = set()
    family_counts = defaultdict(lambda: [0, 0])
    for row in iter_jsonl(raw_path) or []:
        total += 1
        is_wrong = not bool(row.get("is_correct"))
        wrong += int(is_wrong)
        frames.add(str(row.get("scene_frame") or ""))
        family = str(row.get("family") or "unknown")
        family_counts[family][0] += 1
        family_counts[family][1] += int(is_wrong)

    summary = {
        "group": group,
        "method": label,
        "questions": total,
        "wrong": wrong,
        "error_rate": wrong / total if total else 0.0,
        "families": len(family_counts),
        "frames": len({item for item in frames if item}),
        "raw_path": str(raw_path),
    }
    family_rows = []
    for family, (count, family_wrong) in sorted(family_counts.items()):
        family_rows.append(
            {
                "group": group,
                "method": label,
                "family": family,
                "questions": count,
                "wrong": family_wrong,
                "error_rate": family_wrong / count if count else 0.0,
            }
        )
    return summary, family_rows


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def write_markdown(path: Path, total_rows: list[dict], family_rows: list[dict]) -> None:
    lines = [
        "# RQ1 Error Detection Summary",
        "",
        "## Total Error Rate",
        "",
        "| Group | Method | Q | Wrong | Error Rate | Families | Frames |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in total_rows:
        lines.append(
            "| {group} | {method} | {questions} | {wrong} | {rate} | {families} | {frames} |".format(
                group=row["group"],
                method=row["method"],
                questions=row["questions"],
                wrong=row["wrong"],
                rate=pct(row["error_rate"]),
                families=row["families"],
                frames=row["frames"],
            )
        )

    lines.extend(
        [
            "",
            "## By Question Family",
            "",
            "| Group | Method | Family | Q | Wrong | Error Rate |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for row in family_rows:
        lines.append(
            "| {group} | {method} | {family} | {questions} | {wrong} | {rate} |".format(
                group=row["group"],
                method=row["method"],
                family=row["family"],
                questions=row["questions"],
                wrong=row["wrong"],
                rate=pct(row["error_rate"]),
            )
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Official-QA rows use the existing mPLUG seed-filter raw results, not a newly rerun random sample.",
            "- Current automatic scoring is strict for count answers: for example, a model answer like 'there are no cars' is not always normalized to numeric 0.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build RQ1 total and family error tables.")
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument(
        "--l0-l1-results",
        type=Path,
        default=DEFAULT_RUNS_ROOT
        / "mplug-advtest-l0-l1-templatebalanced-v5-q1000-v1"
        / "results",
    )
    parser.add_argument(
        "--l2-results",
        type=Path,
        default=DEFAULT_RUNS_ROOT / "mplug-biglabel-three-method-q1000-v1" / "results",
    )
    parser.add_argument(
        "--official-results",
        type=Path,
        default=DEFAULT_RUNS_ROOT
        / "seed-filter-mplug-f308-q3503-v2"
        / "results"
        / "official_qa_suite_raw_results.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RUNS_ROOT / "rq1-error-summary-tables-v1" / "results",
    )
    args = parser.parse_args()

    sources = [
        (
            "ADVTEST-L0",
            args.l0_l1_results / "advtest_l0_suite_raw_results.jsonl",
            "ours_structural",
        ),
        (
            "ADVTEST-L1",
            args.l0_l1_results / "advtest_l1_suite_raw_results.jsonl",
            "ours_structural",
        ),
        ("ADVTEST-L2", args.l2_results / "advtest_suite_raw_results.jsonl", "ours_l2"),
        ("QAAskeR", args.l2_results / "qaasker_suite_raw_results.jsonl", "baseline"),
        ("QATest", args.l2_results / "qatest_suite_raw_results.jsonl", "baseline"),
        ("Official-QA", args.official_results, "official"),
    ]

    total_rows = []
    family_rows = []
    missing = []
    for label, raw_path, group in sources:
        if not raw_path.exists() or raw_path.stat().st_size == 0:
            missing.append(str(raw_path))
            continue
        total, families = summarize_raw(label, raw_path, group)
        if label != "Official-QA" and total["questions"] < 1000:
            missing.append(f"{raw_path} (incomplete: {total['questions']}/1000)")
            continue
        total_rows.append(total)
        family_rows.extend(families)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "rq1_total_error_rates.csv",
        total_rows,
        ["group", "method", "questions", "wrong", "error_rate", "families", "frames", "raw_path"],
    )
    write_csv(
        args.output_dir / "rq1_error_rates_by_family.csv",
        family_rows,
        ["group", "method", "family", "questions", "wrong", "error_rate"],
    )
    write_markdown(args.output_dir / "rq1_error_tables.md", total_rows, family_rows)
    manifest = {
        "total_rows": len(total_rows),
        "family_rows": len(family_rows),
        "missing_inputs": missing,
        "method_counts": dict(Counter(row["method"] for row in total_rows)),
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
