#!/usr/bin/env python3
"""
验证路径配置是否正确
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "official_pipeline"))

from advtest_env import load_advtest_env
load_advtest_env()

from advtest_paths import get_site

site = get_site(force_reload=True)

print("=" * 80)
print("Path Configuration Verification")
print("=" * 80)
print()

for line in site.summary_lines():
    print(line)

print()
print("=" * 80)
print("File Existence Check")
print("=" * 80)

checks = [
    ("ADVTEST_ROOT", site.advtest_root),
    ("NUSCENES_DATAROOT", site.nuscenes_dataroot),
    ("TRAINVAL_META", site.trainval_meta),
    ("VQA_QA_JSON", site.vqa_qa_json),
    ("EXCEL_PATH", site.excel_path),
    ("GEN_QA_DIR", site.gen_qa_dir),
    ("FILTERED_SG_DIR", site.filtered_sg_dir),
]

all_ok = True
for name, path in checks:
    exists = path.exists()
    status = "[OK]" if exists else "[MISSING]"
    print(f"{status} {name}: {path}")
    if not exists and name not in ["EXCEL_PATH", "GEN_QA_DIR"]:
        all_ok = False

print()
if all_ok:
    print("[OK] All critical paths exist")
else:
    print("[FAIL] Some critical paths are missing")
