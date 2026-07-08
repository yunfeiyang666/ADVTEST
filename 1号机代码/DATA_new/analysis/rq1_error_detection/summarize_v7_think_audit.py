import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(r"E:\Project\ADVTEST")
INPUT_JSONL = (
    ROOT
    / r"scratch\rq1_choice_suites_v7_option_consistency\think_audit_v7_cases_mplug_v3_twocall\think_audit_raw_results.jsonl"
)
ONE_CALL_JSONL = (
    ROOT
    / r"scratch\rq1_choice_suites_v7_option_consistency\think_audit_v7_cases_mplug_v2\think_audit_raw_results.jsonl"
)
OUT_MD = (
    ROOT
    / r"1号机代码\DATA_new\analysis\rq1_error_detection\rq1_v7_think_audit_analysis.md"
)


GROUP_NOTES = {
    "L0-count": "两题都仍然数错，理由也没有真正解释数量，只给出泛化场景描述。这说明计数题的错误更接近视觉计数失败，而不是答案格式问题。",
    "L0-status": "一题在 think 重问后改对，一题仍坚持 moving。理由能明确说出 stopped/moving，适合人工复核图像状态是否可见。",
    "L1-direction": "两题都错，理由只用了 left/back/front 这类粗方向，没有按角度表完成精确方向选择。",
    "L1-count-direction": "两题都错，理由显示模型能抓到局部线索，但计数或方向约束没有同时满足。",
    "L2-converge": "两题都错，理由只覆盖部分约束或复述题干，不能证明它真的完成了唯一目标交汇定位。",
    "L2-direction-chain": "两题在重问后都改对，但理由非常泛化，没有解释关系链本身；这类题的答案可被选择题格式纠正，但 reason 证据弱。",
    "L2-distance-chain": "两题都错，理由没有比较距离，只给出泛化场景描述或重复选项；说明距离比较仍是实际难点。",
    "L2-viewpoint-back": "两题都错，理由明确说目标在 behind/back，说明模型按粗略场景方位判断，没有完成以目标朝向为 0° 的坐标转换。",
    "L2-viewpoint-left-right": "两题都错，理由都说目标在 left，暴露出 left/right 方向选择偏差；这正是 v7 角度精细化后想检出的错误。",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def clean_cell(value: Any) -> str:
    if value is None:
        text = ""
    else:
        text = str(value).strip()
    text = text.replace("\n", "<br>")
    text = text.replace("|", "/")
    text = text.replace("��", "°")
    return text


def label_of(value: Any) -> str:
    text = str(value or "").strip()
    match = re.match(r"^\s*(?:option\s*)?([A-D])(?:[\).:,\-\s]|$)", text, re.I)
    return match.group(1).upper() if match else text[:1].upper()


def build_report() -> None:
    rows = load_jsonl(INPUT_JSONL)
    one_call_rows = load_jsonl(ONE_CALL_JSONL) if ONE_CALL_JSONL.exists() else []

    group_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        group_rows[str(row.get("think_case_group") or "")].append(row)

    corrected = sum(1 for row in rows if row.get("think_is_correct"))
    nonempty_reasons = sum(1 for row in rows if row.get("think"))
    one_call_reasons = sum(1 for row in one_call_rows if row.get("think"))
    same_label = sum(
        1
        for row in rows
        if label_of(row.get("prior_pred")) == label_of(row.get("think_pred"))
    )
    changed_label = len(rows) - same_label
    calls = sum(int(row.get("vlm_calls") or 0) for row in rows)

    lines = [
        "# RQ1 v7 Think Audit 分析",
        "",
        "这份文档只分析典型错题的 think 试点，不进入正式错误率指标。",
        "",
        "## 1. 运行口径",
        "",
        f"- 输入：v7 case 分析中的 9 类 case，每类 2 题，共 {len(rows)} 题。",
        "- 模型：mPLUG-Owl2，本地 ModelScope 权重，`.venv310` 环境。",
        "- v1/v2 单轮格式：要求模型同时输出 `Pred` 和 `Reason/Think`。",
        f"- 单轮结果：`Reason/Think` 非空 {one_call_reasons}/{len(one_call_rows)}，mPLUG 基本只输出选项，不输出理由。",
        "- v3 two-call 格式：第一问选项，第二问固定其选择，让模型补一句视觉依据。",
        f"- v3 结果：非空理由 {nonempty_reasons}/{len(rows)}，总 VLM 调用 {calls} 次。",
        f"- v3 选项正确 {corrected}/{len(rows)}；相对原先错误结果，选项字母变化 {changed_label}/{len(rows)}，保持同一选项 {same_label}/{len(rows)}。",
        "",
        "重要说明：这里的 `Think` 不是模型真实内部推理，只能看作“事后给出的可见线索/解释”。但它仍然有用，因为能暴露模型到底在抓哪个错误线索。",
        "",
        "## 2. 按 case 类别汇总",
        "",
        "| Case | Q | Correct | 主要观察 |",
        "|---|---:|---:|---|",
    ]

    for group, note in GROUP_NOTES.items():
        items = group_rows.get(group, [])
        ok = sum(1 for row in items if row.get("think_is_correct"))
        lines.append(f"| {group} | {len(items)} | {ok} | {note} |")

    lines.extend(
        [
            "",
            "## 3. 逐题结果",
            "",
            "| Case | Sample | Family | Scene | GT | Prior Pred | Think Pred | Correct | Think / Reason |",
            "|---|---:|---|---|---|---|---|---:|---|",
        ]
    )

    for row in rows:
        lines.append(
            "| {case} | {sample} | `{family}` | {scene} | {gt} | {prior} | {pred} | {ok} | {think} |".format(
                case=clean_cell(row.get("think_case_group")),
                sample=clean_cell(row.get("think_case_sample")),
                family=clean_cell(row.get("family")),
                scene=clean_cell(row.get("scene_frame")),
                gt=clean_cell(row.get("gt")),
                prior=clean_cell(row.get("prior_pred")),
                pred=clean_cell(row.get("think_pred")),
                ok=clean_cell(row.get("think_is_correct")),
                think=clean_cell(row.get("think")),
            )
        )

    lines.extend(
        [
            "",
            "## 4. 当前判断",
            "",
            "1. `L0-count`、`L1-count-direction`、`L2-distance-chain` 的理由常常是泛化描述，说明模型没有真正给出可验证的计数/距离依据。",
            "2. `L2-converge` 的理由经常只覆盖局部约束，支持我们对 converge 的判断：它难在多约束同时满足，而不是单个关系看不懂。",
            "3. `L2-viewpoint_transfer` 的理由最有诊断价值：模型明确说 behind/left，但 GT 是 front right，说明它在目标朝向坐标系转换上失败。",
            "4. `L2-direction-chain` 在 two-call 后改对，但理由不解释关系链，说明这个子类不宜作为强 hard-case 主证据。",
            "5. think 机制后续建议只用于典型错题解释和人工复核辅助，不作为正式自动指标。",
            "",
        ]
    )

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    build_report()
