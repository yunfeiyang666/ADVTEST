"""
从 advtest_runtime.env 注入环境变量（在 import gap_pipeline / LLM 之前调用）。

文件路径（按优先级）：
  official_pipeline/advtest_runtime.env
  official_pipeline/.advtest_runtime.env

本模块位于 ``official_pipeline/code/``，env 文件在上一级 ``official_pipeline/``。
加入 ``official_pipeline/code`` 和 ``.../code``（含 ``vqa_pipeline``）到 sys.path。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_code_bundle_on_sys_path() -> None:
    """.../code/vqa_pipeline 与 .../code/official_pipeline 并列时，保证可 import vqa_pipeline。"""
    here = Path(__file__).resolve().parent          # official_pipeline/code/
    official_root = here.parent                      # official_pipeline/
    code_root = official_root.parent                 # .../code/ (含 vqa_pipeline)
    for p in (str(code_root), str(here)):
        if p not in sys.path:
            sys.path.insert(0, p)


_ensure_code_bundle_on_sys_path()


def load_advtest_env() -> bool:
    """
    解析 KEY=VALUE 行写入 os.environ（不覆盖已存在变量）。
    Returns: 是否加载了至少一个文件。
    """
    base = Path(__file__).resolve().parent.parent   # official_pipeline/ (env file 在 code/ 的上一级)
    loaded = False
    for name in ("advtest_runtime.env", ".advtest_runtime.env"):
        path = base / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            key = k.strip()
            val = v.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
        loaded = True
        break
    try:
        import advtest_paths as _ap

        _ap.invalidate_site_cache()
        _ap.refresh_module_paths()
    except Exception:
        pass
    return loaded
