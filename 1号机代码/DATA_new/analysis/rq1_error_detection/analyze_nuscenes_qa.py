"""Profile official NuScenes-QA val questions vs. our object-instance suites.

Produces a markdown report comparing answer spaces, template/family types, and
per-sample question counts, to support the GT-mismatch discussion.

Usage:
  python 1号机代码/DATA_new/analysis/rq1_error_detection/analyze_nuscenes_qa.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).absolute().parent
WORKSPACE_ROOT = HERE.parents[3]
NQA_PATH = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "data" / "NuScenes_val_questions.json"
SUITE_DIR = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "analysis" / "fixed_budget_results"
OUT_PATH = HERE / "nuscenes_qa_vs_ours.md"


def load_nqa() -> list[dict]:
    data = json.loads(NQA_PATH.read_text(encoding="utf-8"))
    return data.get("questions", [])


def load_suite(name: str) -> list[dict]:
    path = SUITE_DIR / f"{name}_suite.jsonl"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def top_counter(counter: Counter, k: int = 15) -> str:
    total = sum(counter.values()) or 1
    lines = []
    for key, cnt in counter.most_common(k):
        lines.append(f"| {key} | {cnt} | {cnt / total:.1%} |")
    return "\n".join(lines)


def main() -> int:
    nqa = load_nqa()
    lines: list[str] = []
    lines.append("# NuScenes-QA (val) vs. Our Suites — Answer/Format Comparison\n")

    # --- Official NuScenes-QA profile ---
    lines.append("## Official NuScenes-QA (val)\n")
    lines.append(f"- total questions: {len(nqa)}")
    samples = {q.get("sample_token") for q in nqa}
    lines.append(f"- distinct sample_tokens (key-frames): {len(samples)}")
    if samples:
        per_sample = Counter(q.get("sample_token") for q in nqa)
        avg = len(nqa) / len(samples)
        lines.append(f"- avg questions per sample: {avg:.1f}")
        lines.append(f"- max questions per sample: {max(per_sample.values())}")

    ans_counter = Counter(str(q.get("answer")) for q in nqa)
    lines.append(f"- distinct answers (answer space size): {len(ans_counter)}\n")
    lines.append("### Top answers (official)\n")
    lines.append("| answer | count | share |")
    lines.append("|---|---:|---:|")
    lines.append(top_counter(ans_counter))
    lines.append("")

    tmpl_counter = Counter(str(q.get("template_type")) for q in nqa)
    lines.append("### template_type distribution (official)\n")
    lines.append("| template_type | count | share |")
    lines.append("|---|---:|---:|")
    lines.append(top_counter(tmpl_counter))
    lines.append("")

    hop_counter = Counter(str(q.get("num_hop")) for q in nqa)
    lines.append("### num_hop distribution (official)\n")
    lines.append("| num_hop | count | share |")
    lines.append("|---|---:|---:|")
    lines.append(top_counter(hop_counter))
    lines.append("")

    # --- Our suites profile ---
    lines.append("## Our suites (object-instance)\n")
    for name in ["advtest", "qatest", "qaasker", "random"]:
        rows = load_suite(name)
        if not rows:
            lines.append(f"- {name}: (not found)\n")
            continue
        ans = Counter(str(r.get("answer")) for r in rows)
        fams = Counter(str(r.get("template_id") or r.get("family")) for r in rows)
        frames = {r.get("scene_frame") or f"{r.get('scene_name')}_frame{r.get('frame_idx')}" for r in rows}
        lines.append(f"### {name}_suite")
        lines.append(f"- total questions: {len(rows)}")
        lines.append(f"- distinct frames: {len(frames)}")
        lines.append(f"- distinct answers (answer space): {len(ans)}")
        sample_ans = ", ".join(list(ans)[:10])
        lines.append(f"- example answers: {sample_ans}")
        lines.append(f"- family/template ids: {dict(fams)}")
        lines.append("")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"official_total={len(nqa)} official_answer_space={len(ans_counter)} samples={len(samples)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

