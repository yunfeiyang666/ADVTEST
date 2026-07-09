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
    / r"scratch\rq1_choice_suites_v7_option_consistency\think_audit_v7_cases_mplug_v10_think3_q27\think_audit_raw_results.jsonl"
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


def first_think_fields(think_row: dict[str, Any] | None) -> tuple[str, str, str]:
    """Return only the first think-prompt output, ignoring optional second-call reason."""
    if not think_row:
        return "", "", ""
    raw = clean_text(think_row.get("raw_think_output"))
    pred = clean_text(think_row.get("think_pred"))
    think = clean_text(think_row.get("think"))
    if not think:
        matches = re.findall(r"(?im)^\s*(?:Think|Reason|Because|Evidence)\s*:\s*(.+?)\s*$", raw)
        think = "\n".join(clean_text(match) for match in matches if clean_text(match))
    think_lines = [line.strip() for line in think.splitlines() if line.strip()]
    think = "\n".join(think_lines[:3])
    return pred, think, raw


def choice_label_from_text(text: str) -> str:
    match = re.match(r"^\s*(?:option\s*)?([A-D])(?:[\).:,\-\s]|$)", clean_text(text), re.I)
    return match.group(1).upper() if match else ""


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


def full_prediction_text(row: dict[str, Any]) -> str:
    pred = prediction_text(row)
    label = predicted_label(row)
    text = predicted_choice_text(row)
    if label and text and pred.strip().upper() == label:
        return f"{label}. {text}"
    return pred


def full_choice_text_from_answer(row: dict[str, Any], answer: str) -> str:
    value = clean_text(answer)
    label = choice_label_from_text(value)
    if not label:
        return value
    for choice in row.get("choices") or []:
        if str(choice.get("label") or "").upper() == label:
            text = clean_text(choice.get("canonical_text") or choice.get("text"))
            return f"{label}. {text}" if text else label
    return value


def display_think_text(raw_think: str) -> str:
    lines = []
    for line in clean_text(raw_think).splitlines():
        if re.match(r"(?i)^\s*(?:Pred|Answer|Final answer|Final)\s*:", line):
            continue
        line = re.sub(r"(?i)^\s*(?:Think|Reason|Because|Evidence)\s*:\s*", "", line).strip()
        lines.append(line)
    visible_lines = [line for line in lines if line.strip()]
    return "\n".join(visible_lines[:3]).strip()


def diagnose_from_think(
    family: str,
    gt: str,
    pred: str,
    reason: str,
    think_status: str,
) -> str:
    reason_l = reason.lower()
    is_correct_this_run = "选对" in think_status
    if pred == "(not provided)":
        return f"它给了理由但没有按要求给选项，所以这条主要是输出格式失败；理由是 `{reason}`。"

    if is_correct_this_run:
        if family == "direction_chain":
            if "same direction" in reason_l or "opposite direction" in reason_l:
                return f"Think 明确在判断关系链 `{reason}`，说明给出理由后它能抓住这条关系。"
            return f"但 Think 只是普通位置描述 `{reason}`，不能证明它真的完成了关系链推理。"
        if family == "viewpoint_transfer":
            if any(token in reason_l for token in ("image", "middle", "left side", "right side")):
                return f"但 Think 仍是图像画面位置描述 `{reason}`，不能证明它真的完成了目标朝向坐标转换。"
            return f"Think 给出的依据是 `{reason}`。"
        return f"Think 给出的依据是 `{reason}`。"

    if family == "l0:count_type":
        if not any(ch.isdigit() for ch in reason):
            return f"Think 没有真正数目标，只是在泛泛描述场景，所以答案偏成 `{pred}`。"
        return f"Think 里给出的数量线索和标准答案 `{gt}` 不一致，说明它确实数错了。"

    if family in {"l0:status", "l0:status_yes"}:
        if any(token in reason_l for token in ("moving", "stopped", "parked")):
            return f"Think 直接把目标状态判断成 `{reason}`，所以错因是状态看错。"
        return f"Think 没有说清目标状态，说明它没有抓住题目真正问的属性。"

    if family in {"l1:direction", "l1:direction_reverse"}:
        return f"Think 只给了粗方向关系 `{reason}`，没有按六类角度区间判断，所以选到了 `{pred}`。"

    if family in {"l1:count_direction_type", "l1:count_status_direction_type"}:
        return f"Think 只抓到一个局部线索 `{reason}`，没有完成“方向筛选后再计数”，所以数量选错。"

    if family == "converge":
        return f"Think 只验证了部分关系 `{reason}`，没有把题干里的多条约束同时交汇到唯一目标。"

    if family == "direction_chain":
        if "same direction" in reason_l or "opposite direction" in reason_l:
            return f"Think 已经在判断关系链 `{reason}`；本题错时主要是关系链方向判断不稳定。"
        return f"Think 退化成普通位置描述 `{reason}`，没有真正完成关系链判断。"

    if family == "distance_chain":
        if "closer" in reason_l or "nearer" in reason_l:
            return f"Think 明确认为 `{reason}`，说明错误来自距离比较本身。"
        return f"Think 没有比较两个候选距离，只描述了局部对象 `{reason}`，所以答案缺少有效依据。"

    if family == "viewpoint_transfer":
        if any(token in reason_l for token in ("image", "middle", "left side", "right side")):
            return f"Think 使用的是图像画面里的左右/中间 `{reason}`，没有切换到目标朝向为 0° 的坐标系。"
        return f"Think 给的是普通空间描述 `{reason}`，没有体现题目要求的视角转换。"

    return f"Think 给出的理由是 `{reason}`，需要结合图像继续复核。"


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
    think_row = (think_rows or {}).get(think_key(row))
    think_pred, _think_reason, raw_think = first_think_fields(think_row)
    pred_for_case = full_choice_text_from_answer(row, think_pred) if think_pred else "(not provided)"
    block = [
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
            f"Answer: {pred_for_case}",
            f"Think: {display_think_text(raw_think) or '(not available)'}",
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
    think_pred, think_reason, raw_think = first_think_fields(think_row)
    pred = full_choice_text_from_answer(row, think_pred) if think_pred else "(not provided)"

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

    if pred:
        think_ok = think_row.get("think_is_correct") if think_row else None
        if think_ok is True:
            think_status = "这次选对了"
        elif think_ok is False:
            think_status = "这次选错了"
        else:
            think_status = "这次无法自动判断正误"
    else:
        think_status = "没有拿到可解析答案"

    if think_reason:
        cause = diagnose_from_think(family, gt, pred, think_reason, think_status)
    elif raw_think:
        cause = "Think 没有给出可用理由，只能根据答案本身判断。"
    else:
        cause = "没有拿到 Think 输出，需要结合图像复核。"

    analysis = f"标准答案是 `{gt}`，模型答 `{pred}`，{think_status}。{cause}"

    return [
        "人工分析：",
        analysis,
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


def choose_case(
    rows: list[dict[str, Any]],
    method: str,
    think_rows: dict[tuple[str, str, str], dict[str, Any]],
    predicate: Callable[[dict[str, Any], dict[str, Any], str], bool],
) -> list[dict[str, Any]]:
    fallback: dict[str, Any] | None = None
    for row in rows:
        if is_correct(row):
            continue
        think_row = think_rows.get(think_key(row))
        if not think_row:
            continue
        think_pred, think_reason, _raw_think = first_think_fields(think_row)
        if not think_pred or not think_reason:
            continue
        if think_row.get("think_is_correct") is True:
            continue
        if fallback is None:
            fallback = row
        if predicate(row, think_row, family_name(method, row)):
            return [row]
    return [fallback] if fallback is not None else []


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
    "l0:status": "直接问具体对象运动状态，需要在 moving/stopped/parked 中选。",
    "l0:status_no": "状态否定式 yes/no；低错主要因为模型在状态判断里强烈倾向答 no。",
    "l0:status_yes": "状态肯定式 yes/no；高错主要因为模型在具体 ID 状态确认题里强烈倾向答 no。",
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
    "l1:relation_no": "关系否定式 yes/no；低错同样受模型 no 倾向影响。",
    "l1:relation_yes": "关系肯定式 yes/no；当前 108/108 都被答成 no，主要反映模型对具体空间陈述的默认否定。",
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
        "这里不讨论 v1/v3/v6；QATest、QAAskeR 只补回严格问答版结果，v7 列留空，方便横向对比。",
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

    for method, label in (
        ("qatest_l2_mixed", "QATest"),
        ("qaasker_l2_mixed", "QAAskeR"),
    ):
        source = strict_sources[method]
        lines.append(f"| {label} | {pct(source['error_rate'])} |  |  |")

    lines.extend(
        [
            "",
            "补充：严格版各项均为 1000 题；v7 中 `mixed` 为 955 题、`converge` 为 973 题，因为选择题转换时强制要求同类候选、唯一正确项、无重复选项，转换不出的题没有纳入正式判分。QATest、QAAskeR 没有做 v7 选择题重跑，所以对应列留空。",
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
            "注意：`status_yes/status_no` 和 `relation_yes/relation_no` 的差异不是 yes/no 题本身难度差异，而是模型在这批具体陈述确认题里明显偏向回答 `no`：`status_yes` 有 103/111 被答成 no，`status_no` 有 96/96 被答成 no；`relation_yes` 有 108/108 被答成 no，`relation_no` 有 83/104 被答成 no。",
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
            "下面只放 v7 错题。每个 case 只展示题目、标准答案、模型答案、Think 原文和图像路径。",
            "",
            "说明：`Think` 是让模型带理由作答时的第一次原始输出；如果它只写理由、没写答案，报告也按原样保留。",
            "",
        ]
    )

    cases: list[tuple[str, list[dict[str, Any]], str]] = []
    l0_rows = v7_rows["advtest_l0"]
    cases.append(
        (
            "Case L0-1：数量题，数目判断错",
            choose_case(
                l0_rows,
                "advtest_l0",
                think_rows,
                lambda r, t, f: f == "l0:count_type",
            ),
            "代表错误：题目要求数目标，Think 给出了计数过程，但最终数目判断与 GT 不一致。",
        )
    )
    cases.append(
        (
            "Case L0-2：状态题，目标状态看错",
            choose_case(
                l0_rows,
                "advtest_l0",
                think_rows,
                lambda r, t, f: f in {"l0:status", "l0:status_yes"}
                and any(token in clean_text(t.get("think")).lower() for token in ("moving", "stopped", "parked", "driving")),
            ),
            "代表错误：Think 明确给出一个状态判断，但该状态和标准答案不一致。",
        )
    )

    l1_rows = v7_rows["advtest_l1"]
    cases.append(
        (
            "Case L1-1：方向题，只做粗方向判断",
            choose_case(
                l1_rows,
                "advtest_l1",
                think_rows,
                lambda r, t, f: f in {"l1:direction", "l1:direction_reverse"},
            ),
            "代表错误：Think 没有按六类角度区间精确判断，只给了粗略空间描述。",
        )
    )
    cases.append(
        (
            "Case L1-2：方向约束计数，只抓局部线索",
            choose_case(
                l1_rows,
                "advtest_l1",
                think_rows,
                lambda r, t, f: f in {"l1:count_direction_type", "l1:count_status_direction_type"},
            ),
            "代表错误：题目要求方向筛选后计数，但 Think 只抓到单个方向/状态线索。",
        )
    )

    cases.append(
        (
            "Case L2-1：converge，只验证部分约束",
            choose_case(
                v7_rows["advtest_l2_converge"],
                "advtest_l2_converge",
                think_rows,
                lambda r, t, f: True,
            ),
            "代表错误：多条关系共同确定答案，但 Think 只覆盖其中一部分关系。",
        )
    )
    cases.append(
        (
            "Case L2-2：direction_chain，退化成普通场景描述",
            choose_case(
                v7_rows["advtest_l2_direction_chain"],
                "advtest_l2_direction_chain",
                think_rows,
                lambda r, t, f: "same direction" not in clean_text(t.get("think")).lower()
                and "opposite direction" not in clean_text(t.get("think")).lower(),
            ),
            "代表错误：题目问关系链，但 Think 没有真正解释链式方向关系。",
        )
    )
    cases.append(
        (
            "Case L2-3：distance_chain，没有完成距离比较",
            choose_case(
                v7_rows["advtest_l2_distance_chain"],
                "advtest_l2_distance_chain",
                think_rows,
                lambda r, t, f: "closer" not in clean_text(t.get("think")).lower()
                and "nearer" not in clean_text(t.get("think")).lower(),
            ),
            "代表错误：题目要求比较两个候选距离，但 Think 只是描述对象，没有给出比较依据。",
        )
    )
    cases.append(
        (
            "Case L2-4：viewpoint_transfer，使用图像坐标而非目标朝向坐标",
            choose_case(
                v7_rows["advtest_l2_viewpoint_transfer"],
                "advtest_l2_viewpoint_transfer",
                think_rows,
                lambda r, t, f: any(
                    token in clean_text(t.get("think")).lower()
                    for token in ("image", "middle", "left side", "right side")
                ),
            ),
            "代表错误：Think 依据图像中的左右/中间位置，而不是题目指定的目标朝向坐标系。",
        )
    )
    cases.append(
        (
            "Case L2-5：viewpoint_transfer，朝向对象被看见但方向转换仍错",
            choose_case(
                v7_rows["advtest_l2_viewpoint_transfer"],
                "advtest_l2_viewpoint_transfer",
                think_rows,
                lambda r, t, f: any(
                    token in clean_text(t.get("think")).lower()
                    for token in ("theta", "reference direction", "relative to the reference")
                ),
            ),
            "代表错误：模型注意到了 facing 关系，但没有把它转成正确的六类方向答案。",
        )
    )

    for title, rows, note in cases:
        if not rows:
            continue
        row = rows[0]
        lines.extend(format_case(title, row, note, think_rows))

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
