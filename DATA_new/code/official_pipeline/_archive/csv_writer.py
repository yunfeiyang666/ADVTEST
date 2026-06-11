#!/usr/bin/env python3
"""
CSV 写入模块 - 替代 Excel 直接写入
稳定、快速、不会损坏
"""
import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

# CSV 文件路径 - 延迟初始化，确保环境变量已加载
import os

_csv_dir_cache = None

def _get_csv_dir() -> Path:
    """延迟获取CSV目录，确保ADVTEST_ROOT已从.env加载"""
    global _csv_dir_cache
    if _csv_dir_cache is None:
        _advtest_root = os.getenv("ADVTEST_ROOT")
        if _advtest_root:
            _csv_dir_cache = Path(_advtest_root) / "csv_output"
        else:
            _csv_dir_cache = Path.home() / "ADVTEST" / "DATA_new" / "csv_output"
    return _csv_dir_cache

def _get_csv_baseline() -> Path:
    return _get_csv_dir() / "raw_coverage.csv"

def _get_csv_generated() -> Path:
    return _get_csv_dir() / "question_answer_our.csv"

def _get_csv_filter() -> Path:
    return _get_csv_dir() / "filter_record.csv"

# 列定义
BASELINE_COLUMNS = [
    "qa_unique_id",
    "scene_id",
    "frame_id",
    "question",
    "answer",
    "q_type",
    "num_hop",
    "l0_nodes",
    "l1_edges",
    "l2_paths",
    "n_l0",
    "n_l1",
    "n_l2",
    "llm_ms",
    "success",
    "timestamp",
]

GENERATED_COLUMNS = [
    "qa_unique_id",
    "scene_id",
    "frame_id",
    "question",
    "answer",
    "q_type",
    "num_hop",
    "timestamp_start",
    "timestamp_llm",
    "timestamp_cypher_return",
    "timestamp_end",
    "iteration_count",
    "complexity",
    "cypher_question",
    "l0_nodes",
    "l1_edges",
    "l2_paths",
    "n_l0",
    "n_l1",
    "n_l2",
    "llm_ms",
    "gap_cell",
    "batch_id",
    "success",
]

FILTER_COLUMNS = [
    "scene_id",
    "frame_id",
    "original_nodes_count",
    "filtered_nodes_count",
    "ratio",
]


def _ensure_csv_exists(csv_path: Path, columns: list):
    """确保 CSV 文件存在，如果不存在则创建并写入表头"""
    if not csv_path.exists():
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
        logger.info(f"Created CSV: {csv_path}")


def _serialize_value(val: Any) -> str:
    """序列化值为字符串"""
    if isinstance(val, (list, dict)):
        return json.dumps(val, ensure_ascii=False)
    elif val is None:
        return ""
    else:
        return str(val)


def write_baseline_row(data: Dict[str, Any]) -> bool:
    """写入一行 baseline 数据"""
    try:
        csv_baseline = _get_csv_baseline()
        _ensure_csv_exists(csv_baseline, BASELINE_COLUMNS)

        with open(csv_baseline, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            row = [_serialize_value(data.get(col, "")) for col in BASELINE_COLUMNS]
            writer.writerow(row)

        return True

    except Exception as exc:
        logger.error(f"CSV write [baseline] failed: {exc}")
        return False


def write_generated_row(data: Dict[str, Any]) -> bool:
    """写入一行生成的问题数据"""
    try:
        csv_generated = _get_csv_generated()
        _ensure_csv_exists(csv_generated, GENERATED_COLUMNS)

        with open(csv_generated, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            row = [_serialize_value(data.get(col, "")) for col in GENERATED_COLUMNS]
            writer.writerow(row)

        return True

    except Exception as exc:
        logger.error(f"CSV write [generated] failed: {exc}")
        return False


def write_filter_record(scene_id: str, frame_id: int, original_num: int,
                       filtered_num: int, ratio: float) -> bool:
    """写入 filter_record"""
    try:
        csv_filter = _get_csv_filter()
        _ensure_csv_exists(csv_filter, FILTER_COLUMNS)

        data = {
            "scene_id": scene_id,
            "frame_id": frame_id,
            "original_nodes_count": original_num,
            "filtered_nodes_count": filtered_num,
            "ratio": round(ratio, 4),
        }

        with open(csv_filter, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            row = [_serialize_value(data.get(col, "")) for col in FILTER_COLUMNS]
            writer.writerow(row)

        return True

    except Exception as exc:
        logger.error(f"CSV write [filter_record] failed: {exc}")
        return False
