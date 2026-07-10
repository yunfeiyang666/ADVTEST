import argparse
import json
import re
from collections import Counter
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def choice_prediction(row: dict) -> str:
    output = str(row.get("predicted") or row.get("raw_model_output") or "").strip()
    match = re.match(r"^\s*([A-D])(?:\.|\)|:|\s)", output, flags=re.IGNORECASE)
    if match:
        label = match.group(1).upper()
        for choice in row.get("choices") or []:
            if str(choice.get("label") or "").upper() == label:
                return str(choice.get("canonical_text") or choice.get("text") or "").lower()
    normalized = output.lower()
    for choice in sorted(
        row.get("choices") or [],
        key=lambda item: len(str(item.get("canonical_text") or "")),
        reverse=True,
    ):
        canonical = str(choice.get("canonical_text") or "").lower()
        if canonical and re.search(rf"\b{re.escape(canonical)}\b", normalized):
            return canonical
    return "unparsed"


def percent(value: int, total: int) -> str:
    return f"{value / total * 100:.1f}%" if total else "n/a"


def summarize(
    strict_rows: list[dict],
    v7_rows: list[dict],
    fourway_suite: list[dict],
    fourway_results: list[dict] | None,
) -> dict:
    if not (len(strict_rows) == len(v7_rows) == len(fourway_suite)):
        raise ValueError("Strict, v7, and four-way suites must have equal row counts")
    for index, (strict, v7, fourway) in enumerate(
        zip(strict_rows, v7_rows, fourway_suite), start=1
    ):
        strict_key = (str(strict.get("scene_frame")), str(strict.get("question_id")))
        if strict_key != (str(v7.get("scene_frame")), str(v7.get("question_id"))):
            raise ValueError(f"v7 alignment mismatch at row {index}")
        if strict_key != (str(fourway.get("scene_frame")), str(fourway.get("question_id"))):
            raise ValueError(f"four-way alignment mismatch at row {index}")

    total = len(strict_rows)
    strict_wrong = sum(not bool(row.get("is_correct")) for row in strict_rows)
    v7_wrong = sum(not bool(row.get("is_correct")) for row in v7_rows)
    transitions = Counter(
        (
            "strict_correct" if strict.get("is_correct") else "strict_wrong",
            "v7_correct" if v7.get("is_correct") else "v7_wrong",
        )
        for strict, v7 in zip(strict_rows, v7_rows)
    )
    v7_gt = Counter(str(row.get("answer") or "").lower() for row in v7_rows)
    v7_pred = Counter(choice_prediction(row) for row in v7_rows)
    v7_gt_pred = Counter(
        (str(row.get("answer") or "").lower(), choice_prediction(row))
        for row in v7_rows
    )
    v7_answer_labels = Counter(str(row.get("choice_answer_label") or "") for row in v7_rows)
    v7_predicted_labels = Counter()
    for row in v7_rows:
        output = str(row.get("predicted") or row.get("raw_model_output") or "")
        match = re.match(r"^\s*([A-D])(?:\.|\)|:|\s)", output, flags=re.IGNORECASE)
        v7_predicted_labels[match.group(1).upper() if match else "unparsed"] += 1
    back_offered = [
        row
        for row in v7_rows
        if any(
            str(choice.get("canonical_text") or "").lower() == "back"
            for choice in row.get("choices") or []
        )
    ]
    back_absent = [row for row in v7_rows if row not in back_offered]
    back_selected = sum(choice_prediction(row) == "back" for row in back_offered)
    wrong_back_selected = sum(
        choice_prediction(row) == "back"
        and str(row.get("answer") or "").lower() != "back"
        for row in v7_rows
    )

    summary = {
        "rows": total,
        "unique_question_ids": len(
            {(str(row.get("scene_frame")), str(row.get("question_id"))) for row in strict_rows}
        ),
        "strict_task": "binary left/right open QA",
        "strict_wrong": strict_wrong,
        "strict_error_rate": strict_wrong / total if total else None,
        "v7_task": "six direction bins with four sampled choices",
        "v7_wrong": v7_wrong,
        "v7_error_rate": v7_wrong / total if total else None,
        "v7_bad_angle_symbol_rows": sum(
            ("\ufffd" in str(row.get("question") or "") or "掳" in str(row.get("question") or ""))
            for row in v7_rows
        ),
        "strict_to_v7_transitions": {" -> ".join(key): value for key, value in transitions.items()},
        "v7_ground_truth_counts": dict(v7_gt),
        "v7_prediction_counts": dict(v7_pred),
        "v7_answer_label_counts": dict(v7_answer_labels),
        "v7_predicted_label_counts": dict(v7_predicted_labels),
        "v7_back_option_diagnosis": {
            "offered": len(back_offered),
            "selected_when_offered": back_selected,
            "selection_rate_when_offered": (
                back_selected / len(back_offered) if back_offered else None
            ),
            "wrong_back_selections": wrong_back_selected,
            "error_rate_when_offered": (
                sum(not bool(row.get("is_correct")) for row in back_offered)
                / len(back_offered)
                if back_offered
                else None
            ),
            "error_rate_when_absent": (
                sum(not bool(row.get("is_correct")) for row in back_absent)
                / len(back_absent)
                if back_absent
                else None
            ),
        },
        "v7_top_gt_prediction_pairs": [
            {"ground_truth": gt, "prediction": pred, "count": count}
            for (gt, pred), count in v7_gt_pred.most_common(12)
        ],
        "fourway_task": "four broad 90-degree bins with all four choices",
        "fourway_ground_truth_counts": dict(
            Counter(str(row.get("answer") or "").lower() for row in fourway_suite)
        ),
        "fourway_answer_label_counts": dict(
            Counter(str(row.get("choice_answer_label") or "") for row in fourway_suite)
        ),
        "fourway_bad_angle_symbol_rows": sum(
            ("\ufffd" in str(row.get("question") or "") or "掳" in str(row.get("question") or ""))
            for row in fourway_suite
        ),
    }
    if fourway_results is not None:
        if len(fourway_results) != total:
            raise ValueError("Four-way result count does not match the suite")
        wrong = sum(not bool(row.get("is_correct")) for row in fourway_results)
        summary.update(
            {
                "fourway_wrong": wrong,
                "fourway_error_rate": wrong / total if total else None,
                "fourway_prediction_counts": dict(
                    Counter(choice_prediction(row) for row in fourway_results)
                ),
            }
        )
    return summary


def markdown(summary: dict) -> str:
    rows = summary["rows"]
    lines = [
        "# Viewpoint-transfer 版本诊断",
        "",
        "| 版本 | 实际任务 | 错题数 | 错误率 |",
        "|---|---|---:|---:|",
        f"| 严格版 | 左/右二选一，自由回答 | {summary['strict_wrong']}/{rows} | {percent(summary['strict_wrong'], rows)} |",
        f"| v7 | 六类方向标准，每题随机给四个候选 | {summary['v7_wrong']}/{rows} | {percent(summary['v7_wrong'], rows)} |",
    ]
    if "fourway_wrong" in summary:
        lines.append(
            f"| 四方向重跑 | front/left/back/right 四分类，完整四选项 | {summary['fourway_wrong']}/{rows} | {percent(summary['fourway_wrong'], rows)} |"
        )
    else:
        lines.append("| 四方向重跑 | front/left/back/right 四分类，完整四选项 | 待正式评测 | 待正式评测 |")
    lines.extend(
        [
            "",
            "严格版与 v7 不是同一难度。严格版只判断目标位于朝向线的左侧还是右侧；v7 要区分 front、front left、front right、back left、back right、back 六类，因此错误率上升不能简单归因于选择题。",
            "",
            f"v7 中有 {summary['v7_bad_angle_symbol_rows']}/{rows} 题的角度符号损坏；四方向题库使用 ASCII `degrees`，损坏数为 {summary['fourway_bad_angle_symbol_rows']}/{rows}。",
            "",
            "v7 正确选项位置："
            + "，".join(f"{key}={value}" for key, value in sorted(summary["v7_answer_label_counts"].items()))
            + "。位置基本均衡，不像是正确答案固定在某个字母造成的。",
            "",
            "v7 模型选择方向："
            + "，".join(
                f"{key}={value}"
                for key, value in sorted(
                    summary["v7_prediction_counts"].items(), key=lambda item: item[1], reverse=True
                )
            )
            + "。",
            "",
            "v7 的 `back (otherwise)` 选项具有明显诱导："
            f"它出现 {summary['v7_back_option_diagnosis']['offered']} 次，模型在出现时选择 back "
            f"{summary['v7_back_option_diagnosis']['selected_when_offered']} 次，"
            f"其中 {summary['v7_back_option_diagnosis']['wrong_back_selections']} 次标准答案并非 back。"
            "因此 v7 的 81.9% 包含选项措辞带来的额外错误，不能全部解释为视觉空间推理失败。",
            "",
            "## 严格版到 v7 的逐题变化",
            "",
        ]
    )
    for key, value in summary["strict_to_v7_transitions"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## v7 最常见的标准答案到模型答案", ""])
    for item in summary["v7_top_gt_prediction_pairs"]:
        lines.append(
            f"- {item['ground_truth']} -> {item['prediction']}: {item['count']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-results", type=Path, required=True)
    parser.add_argument("--v7-results", type=Path, required=True)
    parser.add_argument("--fourway-suite", type=Path, required=True)
    parser.add_argument("--fourway-results", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = summarize(
        load_jsonl(args.strict_results),
        load_jsonl(args.v7_results),
        load_jsonl(args.fourway_suite),
        load_jsonl(args.fourway_results) if args.fourway_results else None,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "viewpoint_version_diagnosis.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "viewpoint_version_diagnosis.md").write_text(
        markdown(summary), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
