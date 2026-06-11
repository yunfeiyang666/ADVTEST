#!/usr/bin/env python3
"""
package_for_server.py — 打包 official_pipeline 服务器部署包

默认行为：
  - 打包 official_pipeline 全目录代码与脚本
  - 自动排除 output/__pycache__/缓存日志等非部署文件
  - 额外包含 requirements_server.txt（以及上级 requirements.txt 若存在）
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import time
import zipfile
from typing import List

EXCLUDE_DIRS = {"output", "__pycache__", ".git", ".idea", ".vscode", ".pytest_cache", ".mypy_cache"}
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".log", ".tmp"}
EXCLUDE_FILE_PREFIX = ("~$",)


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def should_include(root: pathlib.Path, file_path: pathlib.Path) -> bool:
    if not file_path.is_file():
        return False
    rel = file_path.relative_to(root)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return False
    if file_path.suffix.lower() in EXCLUDE_SUFFIX:
        return False
    if file_path.name.startswith(EXCLUDE_FILE_PREFIX):
        return False
    return True


def collect_files(root: pathlib.Path) -> List[pathlib.Path]:
    return sorted([p for p in root.rglob("*") if should_include(root, p)])


def parse_args() -> argparse.Namespace:
    here = pathlib.Path(__file__).resolve().parent
    default_out_dir = here.parent / "deploy_packages"
    p = argparse.ArgumentParser(description="Build deployment zip for official_pipeline.")
    p.add_argument(
        "--out-dir",
        default=str(default_out_dir),
        help="Output directory for zip package.",
    )
    p.add_argument(
        "--name-prefix",
        default="official_pipeline_server_bundle",
        help="Zip filename prefix.",
    )
    return p.parse_args()


def main():
    args = parse_args()
    root = pathlib.Path(__file__).resolve().parent
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    zip_path = out_dir / f"{args.name_prefix}_{ts}.zip"

    files = collect_files(root)
    extra_root_req = root.parent / "requirements.txt"

    manifest_lines = []
    manifest_lines.append(f"package_time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    manifest_lines.append(f"root: {root}")
    manifest_lines.append(f"files_count: {len(files)}")
    manifest_lines.append("")
    manifest_lines.append("files:")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fp in files:
            rel = fp.relative_to(root)
            zf.write(fp, arcname=str(rel).replace("\\", "/"))
            manifest_lines.append(f"- {rel.as_posix()} | sha256={sha256_file(fp)}")

        if extra_root_req.exists():
            zf.write(extra_root_req, arcname="requirements_root.txt")
            manifest_lines.append(f"- requirements_root.txt | sha256={sha256_file(extra_root_req)}")

        manifest_text = "\n".join(manifest_lines) + "\n"
        zf.writestr("DEPLOY_MANIFEST.txt", manifest_text.encode("utf-8"))

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print("=" * 72)
    print("Deployment package created")
    print("=" * 72)
    print(f"zip_path  : {zip_path}")
    print(f"file_count: {len(files)} (+manifest)")
    print(f"size_mb   : {size_mb:.2f}")
    print("\nNext:")
    print("  1) 上传 zip 到服务器并解压")
    print("  2) pip install -r requirements_server.txt")
    print("  3) 设置 VQA_API_KEY / VQA_API_BASE_URL / VQA_MODEL_NAME 环境变量")


if __name__ == "__main__":
    main()
