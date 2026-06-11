"""
coverage_persistence.py - 覆盖状态持久化扩展 (V6 Unified L2)
"""
import json
from pathlib import Path


def save_coverage_state(tracker, output_path: str) -> None:
    """保存覆盖状态到JSON文件"""
    state = {
        "L0": {k: v.to_dict() for k, v in tracker._L0.items()},
        "L1": {k: v.to_dict() for k, v in tracker._L1.items()},
        "L2": {k: v.to_dict() for k, v in tracker._L2.items()},
        "meta": {
            "L0": tracker._L0_meta,
            "L1": tracker._L1_meta,
            "L2": tracker._L2_meta,
        }
    }

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    print(f"[Coverage] Saved to {output_path}")


def load_coverage_state(tracker, input_path: str) -> int:
    """从JSON文件恢复覆盖状态"""
    from gap_pipeline.coverage_tracker import CoverageRecord

    input_file = Path(input_path)
    if not input_file.exists():
        return 0

    with open(input_file, 'r', encoding='utf-8') as f:
        state = json.load(f)

    count = 0

    for k, v in state.get("L0", {}).items():
        rec = CoverageRecord()
        rec.hit_count = v["hit_count"]
        rec.template_ids = v.get("template_ids", [])
        rec.question_ids = v.get("question_ids", [])
        tracker._L0[k] = rec
        count += 1

    for k, v in state.get("L1", {}).items():
        rec = CoverageRecord()
        rec.hit_count = v["hit_count"]
        rec.template_ids = v.get("template_ids", [])
        rec.question_ids = v.get("question_ids", [])
        tracker._L1[k] = rec
        count += 1

    for k, v in state.get("L2", {}).items():
        rec = CoverageRecord()
        rec.hit_count = v["hit_count"]
        rec.template_ids = v.get("template_ids", [])
        rec.question_ids = v.get("question_ids", [])
        tracker._L2[k] = rec
        count += 1

    if "meta" in state:
        tracker._L0_meta = state["meta"].get("L0", {})
        tracker._L1_meta = state["meta"].get("L1", {})
        tracker._L2_meta = state["meta"].get("L2", {})

    print(f"[Coverage] Restored {count} records from {input_path}")

    return count
