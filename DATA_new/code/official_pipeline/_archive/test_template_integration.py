#!/usr/bin/env python3
"""测试模板库集成 - 验证问题生成速度和质量"""
import sys
import pathlib
import time
import collections

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from gap_pipeline.template_library import get_template_library
import random

# 初始化模板库
_template_lib = get_template_library()
_template_usage_count = collections.defaultdict(int)

def _noun_plural(noun: str) -> str:
    n = str(noun or "object").strip() or "object"
    return n if n.endswith("s") else f"{n}s"

def _extract_template_params(_cell: dict, required: list) -> dict:
    """从 cell 提取模板所需参数"""
    params = {}
    n1_id = str(_cell.get("n1_id", "ego") or "ego")
    n1_type = str(_cell.get("n1_type", "") or "")
    n2_id = str(_cell.get("n2_id", "") or "")
    n2_type = str(_cell.get("n2_type", "object") or "object")
    n3_id = str(_cell.get("n3_id", "") or "")
    n3_type = str(_cell.get("n3_type", "object") or "object")
    n3_status = str(_cell.get("n3_status", "") or "")
    r1_dir = str(_cell.get("r1_dir8") or _cell.get("r1_dir4") or "front")
    r2_dir = str(_cell.get("r2_dir8") or _cell.get("r2_dir4") or "front")

    # L0/L1 风格参数
    if "obj_id" in required:
        params["obj_id"] = n3_id if n3_id else f"{n3_type}1"
    if "ref_id" in required:
        params["ref_id"] = n2_id if n2_id else f"{n2_type}1"
    if "obj_type" in required:
        params["obj_type"] = n3_type
    if "type_plural" in required:
        params["type_plural"] = _noun_plural(n3_type)
    if "ref_type" in required:
        params["ref_type"] = n2_type
    if "status" in required:
        params["status"] = n3_status if n3_status else "moving"
    if "direction" in required:
        params["direction"] = r2_dir
    if "direction1" in required:
        params["direction1"] = r1_dir
    if "direction2" in required:
        params["direction2"] = r2_dir

    # L2 风格参数
    if "ref1_id" in required:
        params["ref1_id"] = n1_id if n1_id != "ego" else "ego"
    if "ref2_id" in required:
        params["ref2_id"] = n2_id if n2_id else f"{n2_type}1"
    if "mid_id" in required:
        params["mid_id"] = n2_id if n2_id else f"{n2_type}1"
    if "target_id" in required:
        params["target_id"] = n3_id if n3_id else f"{n3_type}1"
    if "mid_type" in required:
        params["mid_type"] = n2_type
    if "target_type" in required:
        params["target_type"] = n3_type
    if "target_status" in required:
        params["target_status"] = n3_status if n3_status else "moving"

    return params

def _template_question(_topology: str, _cell: dict, _qtype: str) -> str:
    """基于模板库生成问题"""
    # 映射 topology 到 coverage_level
    if _topology in ("L2A", "L2B"):
        coverage_level = "L2"
    elif _topology == "L1":
        coverage_level = "L1"
    else:
        coverage_level = "L0"

    # 获取候选模板
    candidates = _template_lib.get_by_level_type(coverage_level, _qtype)

    if not candidates:
        return f"[No template for {coverage_level}/{_qtype}]"

    # 频率反馈均衡选择
    import math
    T = 2.0
    usage_counts = [_template_usage_count[t.template_id] for t in candidates]
    min_usage = min(usage_counts) if usage_counts else 0
    weights = [math.exp(-(cnt - min_usage) / T) for cnt in usage_counts]
    total_weight = sum(weights)

    r = random.random() * total_weight
    cumsum = 0
    selected_template = candidates[0]
    for i, w in enumerate(weights):
        cumsum += w
        if r <= cumsum:
            selected_template = candidates[i]
            break

    _template_usage_count[selected_template.template_id] += 1

    # 填充参数
    params = _extract_template_params(_cell, selected_template.required_params)

    try:
        question = selected_template.template.format(**params)
        return question
    except KeyError as e:
        return f"[Missing param {e}]"

# 测试用例
test_cells = [
    # L2A exist
    {
        "topology": "L2A",
        "qtype": "exist",
        "cell": {
            "n1_id": "ego", "n2_id": "car5", "n2_type": "car",
            "n3_id": "ped3", "n3_type": "pedestrian",
            "r1_dir8": "front", "r2_dir8": "left"
        }
    },
    # L2B count
    {
        "topology": "L2B",
        "qtype": "count",
        "cell": {
            "n1_id": "car1", "n1_type": "car", "n2_id": "truck2", "n2_type": "truck",
            "n3_id": "ped5", "n3_type": "pedestrian",
            "r1_dir8": "right", "r2_dir8": "front"
        }
    },
    # L2A status
    {
        "topology": "L2A",
        "qtype": "status",
        "cell": {
            "n1_id": "ego", "n2_id": "bus3", "n2_type": "bus",
            "n3_id": "car7", "n3_type": "car", "n3_status": "stopped",
            "r1_dir8": "front-left", "r2_dir8": "right"
        }
    },
]

print("=" * 80)
print("模板库集成测试")
print("=" * 80)

# 统计信息
_template_lib.print_hierarchy()

print("\n" + "=" * 80)
print("问题生成测试")
print("=" * 80)

total_time = 0
for i, test in enumerate(test_cells, 1):
    print(f"\n测试 {i}: {test['topology']} / {test['qtype']}")
    print(f"  Cell: n1={test['cell'].get('n1_id')} n2={test['cell'].get('n2_id')} n3={test['cell'].get('n3_id')}")

    start = time.time()
    question = _template_question(test["topology"], test["cell"], test["qtype"])
    elapsed = (time.time() - start) * 1000
    total_time += elapsed

    print(f"  Question: {question}")
    print(f"  Time: {elapsed:.2f}ms")

print(f"\n平均生成时间: {total_time / len(test_cells):.2f}ms")

# 批量测试（模拟94题）
print("\n" + "=" * 80)
print("批量生成测试（模拟94题）")
print("=" * 80)

batch_cells = []
for _ in range(94):
    batch_cells.append({
        "topology": random.choice(["L2A", "L2B"]),
        "qtype": random.choice(["exist", "count", "status", "object"]),
        "cell": {
            "n1_id": "ego",
            "n2_id": f"car{random.randint(1,10)}",
            "n2_type": random.choice(["car", "truck", "bus"]),
            "n3_id": f"ped{random.randint(1,10)}",
            "n3_type": random.choice(["pedestrian", "bicycle", "motorcycle"]),
            "r1_dir8": random.choice(["front", "back", "left", "right"]),
            "r2_dir8": random.choice(["front", "back", "left", "right"]),
        }
    })

start = time.time()
questions = []
for test in batch_cells:
    q = _template_question(test["topology"], test["cell"], test["qtype"])
    questions.append(q)
elapsed = (time.time() - start) * 1000

print(f"生成 {len(questions)} 个问题")
print(f"总时间: {elapsed:.0f}ms")
print(f"平均: {elapsed / len(questions):.2f}ms/题")
print(f"预计速度提升: {6000 / (elapsed / len(questions)):.1f}x")

# 模板使用分布
print("\n" + "=" * 80)
print("模板使用分布（前10）")
print("=" * 80)
top_templates = sorted(_template_usage_count.items(), key=lambda x: x[1], reverse=True)[:10]
for tid, count in top_templates:
    print(f"  {tid}: {count} 次")

print("\n✓ 测试完成")
