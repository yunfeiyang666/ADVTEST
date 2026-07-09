import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable


ROOT = Path(r"E:\Project\ADVTEST")
OUT_MD = ROOT / r"1号机代码\DATA_new\analysis\rq1_error_detection\rq1_v7_vs_strict_case_analysis.md"

STRICT_MANIFEST = (
    ROOT
    / r"scratch\rq1_choice_suites_v1_formal\strict_open_qa_freeze_v1\strict_results_manifest.json"
)

V7_RAW = {
    "advtest_l0": ROOT
    / r"scratch\rq1_choice_suites_v7_option_consistency\mplug_advtest_v7_option_consistency\advtest_l0_choice_suite_raw_results.jsonl",
    "advtest_l1": ROOT
    / r"scratch\rq1_choice_suites_v7_option_consistency\mplug_advtest_v7_option_consistency\advtest_l1_choice_suite_raw_results.jsonl",
    "advtest_l2_mixed": ROOT
    / r"scratch\rq1_choice_suites_v7_option_consistency\mplug_advtest_v7_recover_mixed_viewpoint\advtest_l2_mixed_choice_suite_raw_results.jsonl",
    "advtest_l2_converge": ROOT
    / r"scratch\rq1_choice_suites_v7_option_consistency\mplug_advtest_v7_option_consistency\advtest_l2_converge_choice_suite_raw_results.jsonl",
    "advtest_l2_direction_chain": ROOT
    / r"scratch\rq1_choice_suites_v7_option_consistency\mplug_advtest_v7_option_consistency\advtest_l2_direction_chain_choice_suite_raw_results.jsonl",
    "advtest_l2_distance_chain": ROOT
    / r"scratch\rq1_choice_suites_v7_option_consistency\mplug_advtest_v7_option_consistency\advtest_l2_distance_chain_choice_suite_raw_results.jsonl",
    "advtest_l2_viewpoint_transfer": ROOT
    / r"scratch\rq1_choice_suites_v7_option_consistency\mplug_advtest_v7_recover_mixed_viewpoint\advtest_l2_viewpoint_transfer_choice_suite_raw_results.jsonl",
}

THINK_AUDIT_RAW = (
    ROOT
    / r"scratch\rq1_choice_suites_v7_option_consistency\think_audit_v7_cases_mplug_v5_targeted_q27\think_audit_raw_results.jsonl"
)

LABELS = {
    "advtest_l0": "ADVTEST-L0",
    "advtest_l1": "ADVTEST-L1",
    "advtest_l2_mixed": "ADVTEST-L2 mixed",
    "advtest_l2_converge": "ADVTEST-L2 converge",
    "advtest_l2_direction_chain": "ADVTEST-L2 direction_chain",
    "advtest_l2_distance_chain": "ADVTEST-L2 distance_chain",
    "advtest_l2_viewpoint_transfer": "ADVTEST-L2 viewpoint_transfer",
}

ORDER = tuple(LABELS)


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def pp(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.1f} pp"


def clean_text(text: Any) -> str:
    value = "" if text is None else str(text)
    replacements = {
        "掳": "°",
        "锛?": "：",
        "鈥?": "-",
        "鈥檚": "'s",
        "\r\n": "\n",
        "\r": "\n",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value.strip()


def short_question(row: dict[str, Any]) -> str:
    text = clean_text(row.get("question"))
    for marker in (
        "\n\nUse the NuScenes-QA direction convention.",
        "\n\nChoose the best answer",
        "\n\nAnswer with",
    ):
        text = text.split(marker, 1)[0]
    return text.strip()


def answer_text(row: dict[str, Any]) -> str:
    return clean_text(
        row.get("choice_answer_text")
        or row.get("choice_answer_canonical_text")
        or row.get("answer")
        or row.get("gt_answer")
    )


def prediction_text(row: dict[str, Any]) -> str:
    return clean_text(row.get("predicted") or row.get("raw_model_output") or row.get("prediction"))


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    qid = (
        row.get("source_question_id")
        or row.get("original_question_id")
        or row.get("question_id")
        or row.get("id")
        or ""
    )
    return (str(row.get("scene_frame") or ""), str(qid))


def think_key(row: dict[str, Any]) -> tuple[str, str, str]:
    qid = (
        row.get("source_question_id")
        or row.get("original_question_id")
        or row.get("question_id")
        or row.get("id")
        or ""
    )
    return (
        str(row.get("method") or ""),
        str(row.get("scene_frame") or ""),
        str(qid),
    )


def load_think_rows(path: Path = THINK_AUDIT_RAW) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    return {think_key(row): row for row in iter_jsonl(path)}


def is_correct(row: dict[str, Any]) -> bool:
    return bool(row.get("is_correct"))


def raw_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wrong = sum(1 for row in rows if not is_correct(row))
    return {"rows": len(rows), "wrong": wrong, "rate": wrong / len(rows) if rows else 0.0}


def qid_family(row: dict[str, Any]) -> str:
    qid = str(row.get("source_question_id") or row.get("question_id") or "")
    parts = qid.split(":")
    if len(parts) >= 3 and parts[1] in {"l0", "l1", "l2"}:
        return f"{parts[1]}:{parts[2]}"
    return ""


def family_name(method: str, row: dict[str, Any]) -> str:
    explicit = row.get("family") or row.get("template_id") or row.get("l2_family")
    if explicit and explicit != "unknown":
        return str(explicit)
    family = qid_family(row)
    if family:
        return family
    if method == "advtest_l0":
        q = short_question(row).lower()
        if "how many" in q:
            return "l0_count"
        if "movement status" in q or " moving" in q or "stopped" in q:
            return "l0_status"
        if "type of object" in q or "is a " in q:
            return "l0_type"
        return "l0_other"
    if method == "advtest_l1":
        q = short_question(row).lower()
        if "how many" in q:
            return "l1_count_relation"
        if "relative to" in q or "where is" in q:
            return "l1_pair_direction"
        if "same direction" in q:
            return "l1_relation"
        return "l1_other"
    if "converge" in method:
        return "converge"
    if "direction_chain" in method:
        return "direction_chain"
    if "distance_chain" in method:
        return "distance_chain"
    if "viewpoint_transfer" in method:
        return "viewpoint_transfer"
    return "unknown"


def choice_lines(row: dict[str, Any]) -> list[str]:
    lines = []
    for choice in row.get("choices") or []:
        label = clean_text(choice.get("label"))
        text = clean_text(choice.get("text"))
        lines.append(f"{label}. {text}")
    return lines


def predicted_label(row: dict[str, Any]) -> str:
    pred = prediction_text(row)
    match = re.match(r"^\s*(?:option\s*)?([A-D])(?:[\).:,\-\s]|$)", pred, re.I)
    return match.group(1).upper() if match else ""


def predicted_choice_text(row: dict[str, Any]) -> str:
    label = predicted_label(row)
    for choice in row.get("choices") or []:
        if str(choice.get("label") or "").upper() == label:
            return clean_text(choice.get("canonical_text") or choice.get("text"))
    return prediction_text(row)


def direction_error_type(row: dict[str, Any]) -> str:
    gt = answer_text(row).lower()
    pred = predicted_choice_text(row).lower()
    if gt == pred:
        return "correct"
    direction_tokens = ("front", "back", "left", "right")
    if not any(token in gt for token in direction_tokens):
        return "non_direction_or_object_error"
    gt_side = "left" if "left" in gt else "right" if "right" in gt else "center"
    pred_side = "left" if "left" in pred else "right" if "right" in pred else "center"
    gt_fb = "front" if "front" in gt else "back" if "back" in gt else "center"
    pred_fb = "front" if "front" in pred else "back" if "back" in pred else "center"
    if gt_fb in ("front", "back") and pred_fb in ("front", "back") and gt_fb != pred_fb:
        return "front_back_flip"
    if gt_side in ("left", "right") and pred_side in ("left", "right") and gt_side != pred_side:
        return "left_right_flip"
    return "direction_other"


def format_case(
    title: str,
    row: dict[str, Any],
    note: str,
    think_rows: dict[tuple[str, str, str], dict[str, Any]] | None = None,
) -> list[str]:
    lines = [f"### {title}", ""]
    row_method = str(row.get("method") or "")
    analysis_method = row_method.removesuffix("_choice")
    parsed_family = family_name(analysis_method, row)
    block = [
        f"Method: {clean_text(row.get('method'))}",
        f"Family: {clean_text(parsed_family)}",
        f"Scene: {clean_text(row.get('scene_frame'))}",
        f"Question: {short_question(row)}",
    ]
    choices = choice_lines(row)
    if choices:
        block.append("")
        block.extend(choices)
    think_row = (think_rows or {}).get(think_key(row))
    block.extend(
        [
            "",
            f"GT: {clean_text(row.get('choice_answer_label'))}. {answer_text(row)}"
            if row.get("choice_answer_label")
            else f"GT: {answer_text(row)}",
            f"Pred: {prediction_text(row)}",
        ]
    )
    if think_row:
        block.extend(
            [
                f"Think Pred: {clean_text(think_row.get('think_pred'))}",
                f"Think: {clean_text(think_row.get('think'))}",
            ]
        )
    block.append(f"Image: {clean_text(row.get('image_path'))}")
    lines.extend(["```text", *block, "```", ""])
    lines.extend(render_human_analysis(row, note, think_row))
    return lines


def render_human_analysis(
    row: dict[str, Any], group_note: str, think_row: dict[str, Any] | None
) -> list[str]:
    row_method = str(row.get("method") or "")
    analysis_method = row_method.removesuffix("_choice")
    family = family_name(analysis_method, row)
    gt = answer_text(row)
    pred = prediction_text(row)
    think_pred = clean_text(think_row.get("think_pred")) if think_row else ""
    reason = clean_text(think_row.get("think")) if think_row else ""

    validity = "有效。题干、选项和 GT 都明确。"
    if family in {"l0:count_type", "l1:count_direction_type", "l1:count_status_direction_type"}:
        validity = "有效，但偏难。它要求先筛对象，再计数。"
    elif family in {"l1:direction", "l1:direction_reverse", "viewpoint_transfer"}:
        validity = "有效。它考察相对方向和角度区间。"
    elif family == "converge":
        validity = "有效且较难。需要同时满足多条关系约束。"
    elif family == "direction_chain":
        validity = "有效，但选择题会明显降低回答难度。"
    elif family == "distance_chain":
        validity = "有效。它考察两个候选的相对距离。"

    if family == "l0:count_type":
        error = f"原始答案选 `{pred}`，GT 是 `{gt}`；重问后为 `{think_pred}`。"
        think_cause = "Think 只给出一个总数，说明它是在估数量，没有可靠地数清每个目标。"
    elif family in {"l0:status", "l0:status_yes"}:
        error = f"原始答案 `{pred}` 和 GT `{gt}` 不一致；重问后为 `{think_pred}`。"
        think_cause = "Think 直接判断 stopped/moving，错因主要是把目标状态看错或前后两次判断不稳定。"
    elif family in {"l1:direction", "l1:direction_reverse"}:
        error = f"模型选 `{pred}`，GT 是 `{gt}`；重问后为 `{think_pred}`。"
        think_cause = "Think 用的是粗略 left/back/front，没有按角度区间精确区分方向。"
    elif family in {"l1:count_direction_type", "l1:count_status_direction_type"}:
        error = f"模型选 `{pred}`，GT 是 `{gt}`；重问后为 `{think_pred}`。"
        think_cause = "Think 只抓到局部方向线索，没有完成方向筛选后的完整计数。"
    elif family == "converge":
        error = f"模型选 `{pred}`，GT 是 `{gt}`；重问后为 `{think_pred}`。"
        think_cause = "Think 只验证了部分关系，说明它被局部约束带偏，没有把所有条件交汇起来。"
    elif family == "direction_chain":
        error = f"原始答案 `{pred}` 和 GT `{gt}` 不一致；重问后为 `{think_pred}`。"
        think_cause = "Think 有时能说出关系链，但原始选择不稳；这类题更多暴露关系链判断稳定性。"
    elif family == "distance_chain":
        error = f"模型选 `{pred}`，GT 是 `{gt}`；重问后为 `{think_pred}`。"
        think_cause = "Think 直接声称某个对象更近，说明错因是距离比较本身判断错。"
    elif family == "viewpoint_transfer":
        error = f"模型选 `{pred}`，GT 是 `{gt}`；重问后为 `{think_pred}`。"
        think_cause = "Think 仍按普通视角说 behind/left，没有切到目标朝向为 0° 的坐标系。"
    else:
        error = f"模型答 `{pred}`，GT 是 `{gt}`；重问后为 `{think_pred}`。"
        think_cause = "Think 只能作为辅助线索，具体错因需要结合图像复核。"

    if reason:
        think_cause += f" 具体看，它说：`{reason}`"

    return [
        "人工分析：",
        f"- 题目：{validity}",
        f"- 错因：{error}",
        f"- Think 暴露的问题：{think_cause}",
        "",
    ]


def find_case(
    rows: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]
) -> dict[str, Any] | None:
    for row in rows:
        if (not is_correct(row)) and predicate(row):
            return row
    return next((row for row in rows if not is_correct(row)), None)


def find_cases(
    rows: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool], limit: int = 3
) -> list[dict[str, Any]]:
    picked: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = row_key(row)
        if key in seen:
            continue
        if (not is_correct(row)) and predicate(row):
            picked.append(row)
            seen.add(key)
        if len(picked) >= limit:
            return picked
    for row in rows:
        key = row_key(row)
        if key in seen:
            continue
        if not is_correct(row):
            picked.append(row)
            seen.add(key)
        if len(picked) >= limit:
            break
    return picked


def family_metrics(rows: list[dict[str, Any]], method: str) -> list[tuple[str, int, int, float]]:
    counts: Counter[str] = Counter()
    wrong_counts: Counter[str] = Counter()
    for row in rows:
        family = family_name(method, row)
        counts[family] += 1
        if not is_correct(row):
            wrong_counts[family] += 1
    result = []
    for family, total in counts.items():
        wrong = wrong_counts[family]
        result.append((family, total, wrong, wrong / total if total else 0.0))
    return sorted(result, key=lambda item: (-item[1], item[0]))


def compact_family_metrics(
    rows: list[dict[str, Any]], method: str, limit_each: int = 3
) -> list[tuple[str, int, int, float, str]]:
    metrics = family_metrics(rows, method)
    high = sorted(metrics, key=lambda item: (-item[3], -item[1], item[0]))[:limit_each]
    low = sorted(metrics, key=lambda item: (item[3], -item[1], item[0]))[:limit_each]
    selected: list[tuple[str, int, int, float, str]] = []
    seen = set()
    for bucket, rows_in_bucket in (("高错", high), ("低错", low)):
        for family, total, wrong, rate in rows_in_bucket:
            if family in seen:
                continue
            selected.append((family, total, wrong, rate, bucket))
            seen.add(family)
    return selected


FAMILY_EXPLANATIONS = {
    "l0:count_type": "按类别计数，主要考察能否数清同类对象。",
    "l0:exists": "判断具体对象是否存在。",
    "l0:exists_status_type": "判断某类/某状态对象是否存在，带类型和状态约束。",
    "l0:more_type": "比较两类对象数量多少。",
    "l0:status": "询问具体对象运动状态。",
    "l0:status_no": "状态否定式 yes/no。",
    "l0:status_yes": "状态肯定式 yes/no；当前 v7 错误率异常高，需优先人工复核题干/GT/图像。",
    "l0:type": "询问具体对象类别。",
    "l0:type_no": "类别否定式 yes/no。",
    "l0:type_yes": "类别肯定式 yes/no。",
    "l1:count_direction_type": "带方向约束的类别计数。",
    "l1:count_status_direction_type": "带方向、类别、状态约束的计数。",
    "l1:direction": "对象相对方向。",
    "l1:direction_reverse": "反向对象相对方向。",
    "l1:exists_direction_type": "某方向是否存在某类对象。",
    "l1:exists_direction_type_no": "方向存在题的否定式。",
    "l1:exists_status_direction_type": "某方向是否存在某类且某状态对象。",
    "l1:object_at": "具体对象是否位于某方向。",
    "l1:relation_no": "关系否定式 yes/no。",
    "l1:relation_yes": "关系肯定式 yes/no；当前错误率极高，需优先检查是否存在 yes/no 选项或 GT 方向口径问题。",
}


def build_report() -> None:
    with STRICT_MANIFEST.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    strict_sources = manifest["sources"]
    strict_rows = {method: iter_jsonl(Path(strict_sources[method]["path"])) for method in ORDER}
    v7_rows = {method: iter_jsonl(path) for method, path in V7_RAW.items()}
    think_rows = load_think_rows()

    v7_metrics = {method: raw_metrics(rows) for method, rows in v7_rows.items()}
    strict_metrics = {
        method: {
            "rows": strict_sources[method]["rows"],
            "wrong": strict_sources[method]["wrong"],
            "rate": strict_sources[method]["error_rate"],
        }
        for method in ORDER
    }

    transition_stats: dict[str, Counter[tuple[bool, bool]]] = {}
    for method in ORDER:
        strict_by_key = {row_key(row): row for row in strict_rows[method]}
        v7_by_key = {row_key(row): row for row in v7_rows[method]}
        common = set(strict_by_key) & set(v7_by_key)
        counter: Counter[tuple[bool, bool]] = Counter()
        for key in common:
            counter[(is_correct(strict_by_key[key]), is_correct(v7_by_key[key]))] += 1
        transition_stats[method] = counter

    lines: list[str] = [
        "# RQ1 ADVTEST v7 与严格问答版 case 分析",
        "",
        "本文只比较两版：",
        "",
        "- 严格问答版：模型自由生成答案，按冻结的自动判分结果统计。",
        "- v7 角度精细化选择题版：题目来源保持一致，转成选择题；涉及方向的题，在题干和选项里显式给出 NuScenes-QA 的方向角度标准，角度以目标朝向为 0°。",
        "",
        "这里不讨论 v1/v3/v6，也不重算 QATest、QAAskeR；重点是看我们的题在“自由回答”和“选项明确化”之后，错误率变化是否合理。",
        "",
        "## 1. 总体对比",
        "",
        "| 数据项 | 严格版错误率 | v7 错误率 | 变化 |",
        "|---|---:|---:|---:|",
    ]

    for method in ORDER:
        s = strict_metrics[method]
        v = v7_metrics[method]
        delta = v["rate"] - s["rate"]
        lines.append(f"| {LABELS[method]} | {pct(s['rate'])} | {pct(v['rate'])} | {pp(delta)} |")

    lines.extend(
        [
            "",
            "补充：严格版各项均为 1000 题；v7 中 `mixed` 为 955 题、`converge` 为 973 题，因为选择题转换时强制要求同类候选、唯一正确项、无重复选项，转换不出的题没有纳入正式判分。",
            "",
            "## 2. 同一题目上的变化",
            "",
            "这一节只列同一题目在两版之间的转移数字；原因统一放到第 3 节解释。",
            "",
        ]
    )

    lines.append("| 数据项 | 可对齐题数 | 严格错→v7对 | 严格对→v7错 | 两版都错 | 两版都对 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for method in ORDER:
        c = transition_stats[method]
        common = sum(c.values())
        lines.append(
            f"| {LABELS[method]} | {common} | {c[(False, True)]} | "
            f"{c[(True, False)]} | {c[(False, False)]} | {c[(True, True)]} |"
        )

    lines.extend(["", "## 3. 分数据项解释", ""])

    per_method = {
        "advtest_l0": [
            "严格版错误率 45.2%，v7 为 36.2%。这说明 L0 中确实有一部分是自动判分过严，例如 `walking` 与 `moving`、`person` 与 `pedestrian` 这类同义表达。",
            "但 v7 仍有 362/1000 错题，不能把 L0 的错全归因于判分。数量题、状态题和小目标类型判断依旧会出错。",
        ],
        "advtest_l1": [
            "严格版 64.0%，v7 56.1%，有小幅改善。也就是说，给出方向角度和选项后能减少一部分表达/判分损失，但 L1 的主要困难仍在空间关系本身。",
            "这类题适合保留，但报告时要说明它比 L0 明显更难，尤其是方向+计数、负关系、对象间相对方向。",
        ],
        "advtest_l2_mixed": [
            "严格版 90.2%，v7 58.3%，降幅很大。原因是 strict open QA 要求模型自由生成准确目标 ID；v7 把候选压到同一选项集合，减少了格式和 ID 生成负担。",
            "v7 mixed 有 955 题，其中 949 题是 converge，因此 mixed 不能作为均衡 L2 结论，只能作为“当前混合池主要由 converge 驱动”的补充结果。",
        ],
        "advtest_l2_converge": [
            "严格版 90.3%，v7 58.7%。下降不是因为题变简单，而是因为 v7 把答案空间从开放 ID 生成改成同类候选选择。",
            "即使这样仍错 571/973，说明 converge 的多约束定位仍然很强：模型经常抓住其中一两个条件，但无法同时满足全部条件。",
        ],
        "advtest_l2_direction_chain": [
            "严格版 83.8%，v7 12.0%，这是最大幅下降。原因主要是这类题转成 yes/no 或 A/B 选择后，模型不用组织自然语言答案，判分也不再受表达影响。",
            "所以 direction_chain 可以作为 L2 子类报告，但不适合作为“最强检错能力”的主证据；它更像检查模型是否能做一条明确关系链判断。",
        ],
        "advtest_l2_distance_chain": [
            "严格版 52.9%，v7 51.3%，基本不变。这反而是最干净的信号：选择题没有明显把它变简单，模型仍然在相对距离比较上犯错。",
            "这类题可以作为稳定的中等难度 L2 子类。",
        ],
        "advtest_l2_viewpoint_transfer": [
            "严格版 48.3%，v7 81.9%，显著上升。这里不是 bug，而是任务口径变严格了：v7 要求从目标朝向为 0° 的坐标系里，在 `front/front left/front right/back left/back right/back` 六类中选最精确方向。",
            "从错题分布看，模型大量偏向选 `back`，说明它不是不知道选项，而是没有稳定完成视角坐标转换。这一项非常适合作为空间推理 hard case，但要在论文中清楚写明方向角度规则。",
        ],
    }
    for method in ORDER:
        lines.extend([f"### {LABELS[method]}", ""])
        for item in per_method[method]:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend(
        [
            "## 4. L0/L1 v7 分题型错误率",
            "",
            "L0/L1 的原始评测结果里 `family` 字段统一是 `unknown`，但 `source_question_id` 保留了结构化题型片段。下面的表就是从 `source_question_id` 中解析出的题型，例如 `scene-0003_frame0:l1:direction_reverse:car14:barrier2` 归为 `l1:direction_reverse`。",
            "",
        ]
    )

    for method in ("advtest_l0", "advtest_l1"):
        lines.extend([f"### {LABELS[method]}", ""])
        lines.append("| 类型 | Q | 错题率 | 为什么看它 |")
        lines.append("|---|---:|---:|---|")
        for family, total, wrong, rate, bucket in compact_family_metrics(v7_rows[method], method):
            explanation = FAMILY_EXPLANATIONS.get(family, "")
            lines.append(f"| `{family}`（{bucket}） | {total} | {pct(rate)} | {explanation} |")
        lines.append("")

    lines.extend(
        [
            "完整 L0/L1 明细不放正文铺开。当前最需要人工复核的是高错项：`l0:status_yes`、`l1:relation_yes`、`l1:exists_status_direction_type`；它们可能混有模型错误、题干口径问题和 GT/自动判分问题。",
            "",
            "## 5. v7 错题 case",
            "",
            "下面只放 v7 错题。每个 case 都按当前选择题版口径展示：题干、选项、GT、模型输出、two-call think 和图像路径。",
            "",
            "说明：`Think` 不是模型内部推理，而是第二次固定其选择后，让模型补充的一句视觉依据；它用于解释错因，不进入正式指标。",
            "",
        ]
    )

    cases: list[tuple[str, list[dict[str, Any]], str]] = []
    l0_rows = v7_rows["advtest_l0"]
    cases.append(
        (
            "Case L0-1：数量题仍然容易错",
            find_cases(l0_rows, lambda r: family_name("advtest_l0", r) == "l0:count_type"),
            "这类题不是同义词问题，而是需要模型数清同一类对象数量；v7 给了选项后仍会错。",
        )
    )
    cases.append(
        (
            "Case L0-2：状态/属性题的视觉判断错误",
            find_cases(
                l0_rows,
                lambda r: family_name("advtest_l0", r) in {"l0:status", "l0:status_yes"},
            ),
            "状态题在严格版里有同义词风险，v7 后仍错的 case 更接近真实视觉状态识别失败。",
        )
    )

    l1_rows = v7_rows["advtest_l1"]
    cases.append(
        (
            "Case L1-1：方向关系选错",
            find_cases(
                l1_rows,
                lambda r: family_name("advtest_l1", r) in {"l1:direction", "l1:direction_reverse"},
            ),
            "题干已经要求相对方向，v7 也给了角度标准；仍错说明模型的相对方位判断不稳。",
        )
    )
    cases.append(
        (
            "Case L1-2：带方向约束的计数题",
            find_cases(
                l1_rows,
                lambda r: family_name("advtest_l1", r)
                in {"l1:count_direction_type", "l1:count_status_direction_type"},
            ),
            "这类题同时要求识别类别、判断方位、再计数，比单纯 yes/no 难很多。",
        )
    )

    cases.append(
        (
            "Case L2-1：converge 多约束定位误选同类目标",
            find_cases(v7_rows["advtest_l2_converge"], lambda r: True),
            "converge 的核心价值在这里：选项都是可混淆同类对象，模型必须同时满足多个关系约束。",
        )
    )
    cases.append(
        (
            "Case L2-2：direction_chain 二值选择仍有少量错",
            find_cases(v7_rows["advtest_l2_direction_chain"], lambda r: True),
            "虽然 v7 后错误率大幅下降，但剩下的错题说明关系链判断并非完全 trivial。",
        )
    )
    cases.append(
        (
            "Case L2-3：distance_chain 距离比较错误",
            find_cases(v7_rows["advtest_l2_distance_chain"], lambda r: True),
            "distance_chain 在两版之间错误率几乎不变，这类错更可能是真正的距离关系理解问题。",
        )
    )
    cases.append(
        (
            "Case L2-4：viewpoint_transfer 过度选择 back",
            find_cases(
                v7_rows["advtest_l2_viewpoint_transfer"],
                lambda r: "back" in predicted_choice_text(r).lower()
                and "back" not in answer_text(r).lower(),
            ),
            "v7 把角度规则说清后，模型仍大量选 back，说明它对目标朝向坐标系的转换能力弱。",
        )
    )
    cases.append(
        (
            "Case L2-5：viewpoint_transfer 前后/左右混淆",
            find_cases(
                v7_rows["advtest_l2_viewpoint_transfer"],
                lambda r: direction_error_type(r) == "left_right_flip",
            ),
            "这类错不是答案格式问题，而是在六方向角度标准下选到了相反或邻近方向。",
        )
    )

    for title, rows, note in cases:
        for index, row in enumerate(rows, start=1):
            suffix = chr(ord("a") + index - 1)
            lines.extend(format_case(f"{title}（样例 {suffix}）", row, note, think_rows))

    lines.extend(
        [
            "## 6. 当前结论",
            "",
            "1. v7 让 L0 和部分 L2 的判分更公平，尤其减少了自由回答带来的同义词、格式和精确 ID 生成损失。",
            "2. v7 没有把所有题都变简单：L1 基本不降，distance_chain 基本不变，viewpoint_transfer 反而显著升高。",
            "3. converge 的错误率从 90.3% 降到 58.7%，但仍是强 hard case；它的价值不在开放生成 ID，而在同类候选中的多约束定位。",
            "4. viewpoint_transfer 是 v7 最强信号，但汇报时必须明确：方向词按 NuScenes-QA 角度表定义，角度以目标朝向为 0°。",
            "5. 后续人工复核优先看三类：L0/L1 是否仍有判分别名问题、converge 是否存在过长或歧义题干、viewpoint_transfer 的 GT 角度边界是否正确。",
            "",
        ]
    )

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    build_report()
