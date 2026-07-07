import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


METHOD_ORDER = (
    "advtest_l0_choice",
    "advtest_l1_choice",
    "advtest_l2_mixed_choice",
    "advtest_l2_converge_choice",
    "advtest_l2_direction_chain_choice",
    "advtest_l2_distance_chain_choice",
    "advtest_l2_viewpoint_transfer_choice",
)


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def read_summary(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["method"]: row for row in csv.DictReader(handle)}


def method_from_raw_path(path: Path) -> str:
    name = path.name
    return name.removesuffix("_suite_raw_results.jsonl")


def short_question(row: dict) -> str:
    question = str(row.get("question") or "")
    return question.split("\n\nUse the NuScenes-QA direction convention.", 1)[0].strip()


def format_choices(row: dict) -> str:
    lines = []
    for choice in row.get("choices") or []:
        lines.append(f"{choice.get('label')}. {choice.get('text')}")
    return "\n".join(lines)


def format_case(row: dict) -> str:
    return (
        "```text\n"
        f"Method: {row.get('method', '')}\n"
        f"Family: {row.get('family') or row.get('template_id') or ''}\n"
        f"Scene: {row.get('scene_frame', '')}\n"
        f"Question: {short_question(row)}\n\n"
        f"{format_choices(row)}\n\n"
        f"GT: {row.get('choice_answer_label', '')}. {row.get('choice_answer_text') or row.get('answer')}\n"
        f"Prediction: {row.get('predicted') or row.get('raw_model_output')}\n"
        f"Image: {row.get('image_path', '')}\n"
        "```"
    )


def has_angle_annotation(row: dict) -> bool:
    text = str(row.get("question") or "")
    return "theta" in text or "°" in text


def predicted_label(row: dict) -> str:
    pred = str(row.get("predicted") or row.get("raw_model_output") or "")
    match = re.match(r"^\s*(?:option\s*)?([A-D])(?:[\).:,\-\s]|$)", pred, re.I)
    return match.group(1).upper() if match else ""


def predicted_choice_text(row: dict) -> str:
    label = predicted_label(row)
    for choice in row.get("choices") or []:
        if str(choice.get("label") or "").upper() == label:
            return str(choice.get("canonical_text") or choice.get("text") or "")
    return str(row.get("predicted") or row.get("raw_model_output") or "")


def direction_error_type(row: dict) -> str:
    gt = str(row.get("choice_answer_canonical_text") or row.get("answer") or "").lower()
    pred = predicted_choice_text(row).lower()
    if gt == pred:
        return "correct"
    if not pred:
        return "unparsed"
    if any(token in gt for token in ("front", "back", "left", "right")):
        gt_side = "left" if "left" in gt else "right" if "right" in gt else "center"
        pred_side = "left" if "left" in pred else "right" if "right" in pred else "center"
        gt_fb = "front" if "front" in gt else "back" if "back" in gt else "center"
        pred_fb = "front" if "front" in pred else "back" if "back" in pred else "center"
        if gt_side in ("left", "right") and pred_side in ("left", "right") and gt_side != pred_side:
            return "left_right_flip"
        if gt_fb in ("front", "back") and pred_fb in ("front", "back") and gt_fb != pred_fb:
            return "front_back_flip"
        return "direction_other"
    return "non_direction_or_object_error"


def pick_cases(rows_by_method: dict[str, list[dict]]) -> list[tuple[str, dict]]:
    picked = []
    for method in METHOD_ORDER:
        rows = rows_by_method.get(method, [])
        wrong = [row for row in rows if not row.get("is_correct")]
        correct = [row for row in rows if row.get("is_correct")]
        if correct:
            picked.append((f"{method}: 正确样例", correct[0]))
        if wrong:
            picked.append((f"{method}: 典型错例", wrong[0]))
        if method.endswith("viewpoint_transfer_choice"):
            for tag in ("front_back_flip", "left_right_flip", "direction_other"):
                row = next((item for item in wrong if direction_error_type(item) == tag), None)
                if row:
                    picked.append((f"{method}: {tag}", row))
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate case analysis for the ADVTEST angle-annotated choice run."
    )
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--expected-total", type=int, default=6928)
    args = parser.parse_args()

    raw_paths = sorted(args.result_dir.glob("*_suite_raw_results.jsonl"))
    rows_by_method: dict[str, list[dict]] = {}
    total_rows = 0
    for path in raw_paths:
        method = method_from_raw_path(path)
        rows = list(iter_jsonl(path))
        rows_by_method[method] = rows
        total_rows += len(rows)

    if total_rows < args.expected_total:
        raise SystemExit(
            f"Raw results incomplete: {total_rows}/{args.expected_total} rows in {args.result_dir}"
        )

    summary = read_summary(args.result_dir / "suite_eval_summary.csv")
    family_counts = defaultdict(Counter)
    error_type_counts = defaultdict(Counter)
    angle_coverage = {}
    for method, rows in rows_by_method.items():
        family_counts[method].update(str(row.get("family") or row.get("template_id") or "unknown") for row in rows)
        error_type_counts[method].update(direction_error_type(row) for row in rows if not row.get("is_correct"))
        angle_coverage[method] = sum(1 for row in rows if has_angle_annotation(row))

    lines = [
        "# Case Analysis: ADVTEST Angle-Annotated Choice Run",
        "",
        "## 目的",
        "",
        "这份文档整理 ADVTEST 全题库角度标注选择题版的结果。QATest 和 QAAskeR 本轮不重跑。",
        "本轮改动不是改题目答案，而是在所有含方向词的题干中补充角度说明，并在方向选项中显示角度范围。",
        "",
        "核心检查点：",
        "",
        "1. 方向词是否已经在题干和选项中说清楚。",
        "2. 模型答错是否仍然集中在空间定位、方向判断、视角转换，而不是不知道方向词含义。",
        "3. 哪些 case 适合进入汇报/论文，哪些需要人工复核。",
        "",
        "## 总体结果",
        "",
        "| Method | Q | Calls | Wrong | Error Rate | Unique Failures | Angle-Annotated Rows |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for method in METHOD_ORDER:
        row = summary.get(method, {})
        rows = rows_by_method.get(method, [])
        q = int(row.get("questions") or len(rows))
        calls = int(row.get("vlm_calls") or q)
        wrong = int(row.get("wrong") or sum(1 for item in rows if not item.get("is_correct")))
        rate = float(row.get("failure_rate") or (wrong / q if q else 0))
        unique = int(row.get("unique_failures") or wrong)
        lines.append(
            f"| {method} | {q} | {calls} | {wrong} | {rate:.2%} | {unique} | {angle_coverage.get(method, 0)} |"
        )

    lines.extend(["", "## 题型分布", ""])
    for method in METHOD_ORDER:
        if method not in rows_by_method:
            continue
        lines.append(f"### {method}")
        lines.append("")
        lines.append("| Family | Count |")
        lines.append("|---|---:|")
        for family, count in family_counts[method].most_common():
            lines.append(f"| `{family}` | {count} |")
        lines.append("")

    lines.extend(["## 错误类型概览", ""])
    for method in METHOD_ORDER:
        counts = error_type_counts.get(method)
        if not counts:
            continue
        lines.append(f"### {method}")
        lines.append("")
        lines.append("| Error Type | Count |")
        lines.append("|---|---:|")
        for key, count in counts.most_common():
            lines.append(f"| `{key}` | {count} |")
        lines.append("")

    lines.extend(["## 典型 case", ""])
    for title, row in pick_cases(rows_by_method):
        lines.extend(
            [
                f"### {title}",
                "",
                format_case(row),
                "",
                f"人工判断：该题是否含角度标注：`{has_angle_annotation(row)}`；预测归类为 `{direction_error_type(row)}`。",
                "",
            ]
        )
        if row.get("is_correct"):
            lines.extend(["结论：新题面可被模型正常读取和作答。", ""])
        else:
            lines.extend(
                [
                    "结论：这类错例需要结合图像复核，但在角度边界已显式给出的情况下，仍可作为空间理解失败候选。",
                    "",
                ]
            )

    lines.extend(
        [
            "## 初步结论",
            "",
            "1. 本轮把方向口径从隐含规则改成显式规则，降低了审稿人质疑“方向词不明确”的风险。",
            "2. 如果错误率仍然高，说明问题更接近视觉空间理解和坐标系转换，而不是回答格式。",
            "3. QATest、QAAskeR 没有在本轮重跑，避免把 baseline 也改成我们的提示风格。",
            "4. Think 仍然不进入正式流程，只后续用于典型错题解释。",
            "",
        ]
    )

    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.output_md}")


if __name__ == "__main__":
    main()
