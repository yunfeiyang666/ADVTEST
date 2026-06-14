import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_output(workspace_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def current_git_state(workspace_root: Path) -> dict:
    commit = _git_output(workspace_root, "rev-parse", "HEAD")
    branch = _git_output(workspace_root, "branch", "--show-current")
    status = _git_output(workspace_root, "status", "--porcelain")
    return {
        "commit": commit or None,
        "branch": branch or None,
        "dirty": bool(status),
    }


def build_manifest(
    *,
    run_id: str,
    purpose: str,
    command: Sequence[str],
    workspace_root: Path,
    input_files: Sequence[Path],
    parameters: Mapping[str, object],
) -> dict:
    inputs = []
    for input_path in input_files:
        resolved = input_path.resolve()
        inputs.append(
            {
                "path": str(resolved),
                "sha256": sha256_file(resolved),
                "size_bytes": resolved.stat().st_size,
            }
        )
    return {
        "schema_version": 1,
        "run_id": run_id,
        "purpose": purpose,
        "status": "prepared",
        "command": list(command),
        "workspace_root": str(workspace_root.resolve()),
        "parameters": dict(parameters),
        "inputs": inputs,
        "git": current_git_state(workspace_root),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_manifest(path: Path, manifest: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_recorded_experiment(
    *,
    run_dir: Path,
    manifest: dict,
    command: Sequence[str],
    cwd: Path,
    overwrite: bool = False,
) -> dict:
    if run_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Run directory already exists: {run_dir}")
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    manifest_path = run_dir / "manifest.json"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    started = time.monotonic()
    manifest.update(
        {
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _write_manifest(manifest_path, manifest)

    exit_code = -1
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, (
            stderr_path.open("w", encoding="utf-8")
        ) as stderr_handle:
            completed = subprocess.run(
                list(command),
                cwd=cwd,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                check=False,
            )
            exit_code = completed.returncode
    finally:
        manifest.update(
            {
                "status": "completed" if exit_code == 0 else "failed",
                "exit_code": exit_code,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": time.monotonic() - started,
                "stdout_path": str(stdout_path.resolve()),
                "stderr_path": str(stderr_path.resolve()),
            }
        )
        _write_manifest(manifest_path, manifest)
    return manifest
