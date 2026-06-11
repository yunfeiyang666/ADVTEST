"""一次性清空 RQ Excel 数据行（保留表头）。"""
from __future__ import annotations

from pathlib import Path

import openpyxl


def clear_excel_data_rows(excel_path: Path) -> int:
    """
    删除所有工作表第 2 行及以后。返回删除的总行数估算。
    """
    path = Path(excel_path)
    if not path.is_file():
        return 0
    wb = openpyxl.load_workbook(str(path))
    removed = 0
    for ws in wb.worksheets:
        n = ws.max_row or 0
        if n > 1:
            removed += n - 1
            ws.delete_rows(2, n - 1)
    wb.save(str(path))
    wb.close()
    return removed
