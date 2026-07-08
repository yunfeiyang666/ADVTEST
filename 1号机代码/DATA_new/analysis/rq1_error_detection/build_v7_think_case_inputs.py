import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parents[3]
sys.path.insert(0, str(SCRIPT_DIR))

import generate_v7_vs_strict_case_analysis as case_analysis


OUTPUT_DIR = (
    WORKSPACE_ROOT
    / "scratch"
    / "rq1_choice_suites_v7_option_consistency"
    / "think_audit_v7_case_inputs"
)
OUTPUT_JSONL = OUTPUT_DIR / "v7_case_think_inputs.jsonl"
OUTPUT_MANIFEST = OUTPUT_DIR / "v7_case_think_inputs_manifest.md"


CASE_DEFINITIONS = [
    (
        "L0-count",
        "数量题仍然容易错",
        "advtest_l0",
        lambda row: case_analysis.family_name("advtest_l0", row) == "l0:count_type",
    ),
    (
        "L0-status",
        "状态/属性题的视觉判断错误",
        "advtest_l0",
        lambda row: case_analysis.family_name("advtest_l0", row)
        in {"l0:status", "l0:status_yes"},
    ),
    (
        "L1-direction",
        "方向关系选错",
        "advtest_l1",
        lambda row: case_analysis.family_name("advtest_l1", row)
        in {"l1:direction", "l1:direction_reverse"},
    ),
    (
        "L1-count-direction",
        "带方向约束的计数题",
        "advtest_l1",
        lambda row: case_analysis.family_name("advtest_l1", row)
        in {"l1:count_direction_type", "l1:count_status_direction_type"},
    ),
    (
        "L2-converge",
        "converge 多约束定位误选同类目标",
        "advtest_l2_converge",
        lambda row: True,
    ),
    (
        "L2-direction-chain",
        "direction_chain 二值选择仍有少量错",
        "advtest_l2_direction_chain",
        lambda row: True,
    ),
    (
        "L2-distance-chain",
        "distance_chain 距离比较错误",
        "advtest_l2_distance_chain",
        lambda row: True,
    ),
    (
        "L2-viewpoint-back",
        "viewpoint_transfer 过度选择 back",
        "advtest_l2_viewpoint_transfer",
        lambda row: "back" in case_analysis.predicted_choice_text(row).lower()
        and "back" not in case_analysis.answer_text(row).lower(),
    ),
    (
        "L2-viewpoint-left-right",
        "viewpoint_transfer 前后/左右混淆",
        "advtest_l2_viewpoint_transfer",
        lambda row: case_analysis.direction_error_type(row) == "left_right_flip",
    ),
]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows_by_method = {
        method: case_analysis.iter_jsonl(path)
        for method, path in case_analysis.V7_RAW.items()
    }

    selected = []
    manifest_lines = [
        "# V7 Think Case Inputs",
        "",
        "These rows match the case groups in `rq1_v7_vs_strict_case_analysis.md`.",
        "",
        "| Case | Sample | Method | Family | Scene | Source Question ID | GT | Prior Pred |",
        "|---|---:|---|---|---|---|---|---|",
    ]
    for case_group, case_title, method, predicate in CASE_DEFINITIONS:
        rows = case_analysis.find_cases(rows_by_method[method], predicate, limit=2)
        if len(rows) != 2:
            raise RuntimeError(f"Expected 2 rows for {case_group}, got {len(rows)}")
        for sample_index, row in enumerate(rows, start=1):
            item = dict(row)
            item["family"] = case_analysis.family_name(method, row)
            item["think_case_group"] = case_group
            item["think_case_title"] = case_title
            item["think_case_sample"] = sample_index
            selected.append(item)
            manifest_lines.append(
                "| {case} | {sample} | {method_name} | `{family}` | {scene} | `{qid}` | {gt} | {pred} |".format(
                    case=case_group,
                    sample=sample_index,
                    method_name=item.get("method", ""),
                    family=item.get("family", ""),
                    scene=item.get("scene_frame", ""),
                    qid=item.get("source_question_id") or item.get("question_id") or "",
                    gt=case_analysis.answer_text(item).replace("|", "/"),
                    pred=case_analysis.prediction_text(item).replace("|", "/"),
                )
            )

    with OUTPUT_JSONL.open("w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    OUTPUT_MANIFEST.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(selected)} rows to {OUTPUT_JSONL}")


if __name__ == "__main__":
    main()
