import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import shlex
import subprocess
import sys
from pathlib import Path

from config import SCRATCH_ROOT
from data_ops import file_sha256, read_json, write_json


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
MPLUG_ROOT = WORKSPACE_ROOT / "baselines" / "mPLUG-Owl" / "mPLUG-Owl2"
DEFAULT_MODEL = Path("E:/hf_cache/modelscope/iic/mPLUG-Owl2")
MODEL_FINGERPRINT_CACHE = SCRATCH_ROOT / "cache" / "model_fingerprints.json"

PROFILES = {
    "smoke": {
        "base_init_seed": 20260715,
        "learning_rate": 1e-4,
        "bits": 4,
        "lora_r": 8,
        "lora_alpha": 16,
        "lora_dropout": 0.05,
        "tune_visual_abstractor": False,
        "visual_abstractor_lr": None,
        "batch_size": 1,
        "gradient_accumulation_steps": 8,
        "max_steps": 20,
        "num_train_epochs": 1,
        "save_strategy": "steps",
        "save_steps": 20,
        "dataloader_num_workers": 0,
    },
    "formal": {
        "base_init_seed": 20260715,
        "learning_rate": 1e-4,
        "bits": 4,
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "tune_visual_abstractor": True,
        "visual_abstractor_lr": 2e-5,
        "batch_size": 1,
        "gradient_accumulation_steps": 16,
        "max_steps": -1,
        "num_train_epochs": 3,
        "save_strategy": "epoch",
        "save_steps": 0,
        "dataloader_num_workers": 4,
    },
}


def _json_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def fingerprint_model(model_path: Path) -> dict:
    model_path = model_path.resolve()
    files = sorted(path for path in model_path.rglob("*") if path.is_file())
    state = [
        {
            "path": path.relative_to(model_path).as_posix(),
            "size": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
        }
        for path in files
    ]
    cache = read_json(MODEL_FINGERPRINT_CACHE) if MODEL_FINGERPRINT_CACHE.exists() else {}
    cache_key = str(model_path)
    cached = cache.get(cache_key)
    if cached and cached.get("file_state") == state:
        return cached["fingerprint"]
    hashed_files = []
    for index, path in enumerate(files, start=1):
        hashed_files.append(
            {
                "path": path.relative_to(model_path).as_posix(),
                "size": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
        if index % 5 == 0:
            print(f"[rq3-train] hashed model files {index}/{len(files)}", flush=True)
    fingerprint = {
        "model_path": str(model_path),
        "file_count": len(hashed_files),
        "total_bytes": sum(item["size"] for item in hashed_files),
        "files": hashed_files,
        "checkpoint_sha256": _json_sha256(hashed_files),
    }
    cache[cache_key] = {"file_state": state, "fingerprint": fingerprint}
    write_json(MODEL_FINGERPRINT_CACHE, cache)
    return fingerprint


def environment_snapshot() -> dict:
    packages = {}
    for name in (
        "torch",
        "torchvision",
        "transformers",
        "tokenizers",
        "accelerate",
        "peft",
        "bitsandbytes",
        "Pillow",
    ):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    try:
        gpu = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        gpu = "unavailable"
    try:
        git_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        git_commit = "unavailable"
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "gpu": gpu,
        "packages": packages,
        "git_commit": git_commit,
    }


def prepare_training_data(
    dataset_path: Path, profile: str, seed: int, run_dir: Path
) -> Path:
    rows = read_json(dataset_path)
    if not isinstance(rows, list) or not rows:
        raise ValueError("Training dataset must be a non-empty JSON list")
    if profile == "formal":
        return dataset_path.resolve()
    if len(rows) < 32:
        raise ValueError(f"Smoke training requires 32 unique rows, found {len(rows)}")
    rng = random.Random(seed)
    indices = list(range(len(rows)))
    rng.shuffle(indices)
    selected = [rows[index] for index in indices[:32]]
    source_ids = [row["metadata"]["source_question_id"] for row in selected]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Smoke sample contains duplicate source questions")
    output = run_dir / "smoke_train_32.json"
    write_json(output, selected)
    return output


def build_training_command(config: dict) -> list[str]:
    profile = config["training"]
    command = [
        config["python_executable"],
        "-m",
        "mplug_owl2.train.train",
        "--model_name_or_path",
        config["model_path"],
        "--version",
        "v1",
        "--data_path",
        config["training_data"],
        "--image_folder",
        config["image_root"],
        "--image_aspect_ratio",
        "pad",
        "--output_dir",
        config["adapter_output"],
        "--seed",
        str(config["seed"]),
        "--rq3_base_init_seed",
        str(profile["base_init_seed"]),
        "--data_seed",
        str(config["seed"]),
        "--lora_enable",
        "True",
        "--lora_r",
        str(profile["lora_r"]),
        "--lora_alpha",
        str(profile["lora_alpha"]),
        "--lora_dropout",
        str(profile["lora_dropout"]),
        "--bits",
        str(profile["bits"]),
        "--double_quant",
        "True",
        "--quant_type",
        "nf4",
        "--freeze_vision_model",
        "True",
        "--tune_visual_abstractor",
        str(profile["tune_visual_abstractor"]),
        "--per_device_train_batch_size",
        str(profile["batch_size"]),
        "--gradient_accumulation_steps",
        str(profile["gradient_accumulation_steps"]),
        "--num_train_epochs",
        str(profile["num_train_epochs"]),
        "--save_strategy",
        profile["save_strategy"],
        "--save_total_limit",
        "3",
        "--learning_rate",
        str(profile["learning_rate"]),
        "--weight_decay",
        "0",
        "--warmup_ratio",
        "0.03",
        "--lr_scheduler_type",
        "cosine",
        "--logging_steps",
        "1",
        "--fp16",
        "True",
        "--bf16",
        "False",
        "--tf32",
        "True",
        "--model_max_length",
        "512",
        "--gradient_checkpointing",
        "True",
        "--optim",
        "paged_adamw_8bit",
        "--group_by_modality_length",
        "True",
        "--lazy_preprocess",
        "True",
        "--dataloader_num_workers",
        str(profile["dataloader_num_workers"]),
        "--report_to",
        "none",
        "--evaluation_strategy",
        "no",
    ]
    if profile["visual_abstractor_lr"] is not None:
        command.extend(
            ["--visual_abstractor_lr", str(profile["visual_abstractor_lr"])]
        )
    if profile["max_steps"] > 0:
        command.extend(["--max_steps", str(profile["max_steps"])])
    if profile["save_steps"] > 0:
        command.extend(["--save_steps", str(profile["save_steps"])])
    return command


def _write_launchers(run_dir: Path, command: list[str]) -> None:
    ps_command = " ".join("'" + value.replace("'", "''") + "'" for value in command)
    (run_dir / "launch.ps1").write_text(ps_command + "\n", encoding="utf-8")
    (run_dir / "launch.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n" + shlex.join(command) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def prepare_run(args: argparse.Namespace) -> Path:
    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.model.resolve()
    dataset_path = args.dataset.resolve()
    image_root = args.image_root.resolve()
    if not model_path.exists() or not dataset_path.exists() or not image_root.exists():
        raise FileNotFoundError("Model, dataset, and image root must all exist")
    training_data = prepare_training_data(
        dataset_path, args.profile, args.seed, run_dir
    )
    model_fingerprint = fingerprint_model(model_path)
    profile = dict(PROFILES[args.profile])
    if args.profile == "formal":
        profile["learning_rate"] = float(
            getattr(args, "learning_rate", profile["learning_rate"])
        )
        profile["lora_r"] = int(getattr(args, "lora_r", profile["lora_r"]))
        profile["lora_alpha"] = int(
            getattr(args, "lora_alpha", profile["lora_alpha"])
        )
        if getattr(args, "disable_visual_abstractor", False):
            profile["tune_visual_abstractor"] = False
            profile["visual_abstractor_lr"] = None
    config = {
        "schema_version": "rq3_mplug_qlora_run_v1",
        "profile": args.profile,
        "seed": args.seed,
        "python_executable": str(args.python_executable),
        "model_path": str(model_path),
        "model_checkpoint_sha256": model_fingerprint["checkpoint_sha256"],
        "base_missing_weight_init_seed": profile["base_init_seed"],
        "source_dataset": str(dataset_path),
        "source_dataset_sha256": file_sha256(dataset_path),
        "training_data": str(training_data),
        "training_data_sha256": file_sha256(training_data),
        "image_root": str(image_root),
        "adapter_output": str((run_dir / "adapter").resolve()),
        "training": profile,
    }
    command = build_training_command(config)
    config["command"] = command
    write_json(run_dir / "run_config.json", config)
    write_json(run_dir / "model_fingerprint.json", model_fingerprint)
    write_json(run_dir / "environment.json", environment_snapshot())
    _write_launchers(run_dir, command)
    print(run_dir / "run_config.json")
    return run_dir / "run_config.json"


def inspect_training_artifacts(
    config: dict, require_loss_decrease: bool = True
) -> dict:
    adapter_dir = Path(config["adapter_output"])
    adapter_files = [
        adapter_dir / "adapter_config.json",
        adapter_dir / "adapter_model.bin",
    ]
    if not adapter_files[1].exists():
        adapter_files[1] = adapter_dir / "adapter_model.safetensors"
    missing = [str(path) for path in adapter_files if not path.exists()]
    state_path = adapter_dir / "trainer_state.json"
    if not state_path.exists():
        missing.append(str(state_path))
    losses = []
    if state_path.exists():
        state = read_json(state_path)
        losses = [
            float(row["loss"])
            for row in state.get("log_history", [])
            if row.get("loss") is not None
        ]
    finite = bool(losses) and all(math.isfinite(value) for value in losses)
    decreased = len(losses) >= 2 and losses[-1] < losses[0]
    return {
        "adapter_files_missing": missing,
        "loss_count": len(losses),
        "first_loss": losses[0] if losses else None,
        "last_loss": losses[-1] if losses else None,
        "loss_finite": finite,
        "loss_decreased": decreased,
        "loss_decrease_required": require_loss_decrease,
        "passed": not missing and finite and (
            decreased or not require_loss_decrease
        ),
    }


def execute_run(args: argparse.Namespace) -> None:
    config = read_json(args.config)
    run_dir = args.config.resolve().parent
    log_path = run_dir / "training.log"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(MPLUG_ROOT), environment.get("PYTHONPATH", "")]
    )
    environment["PYTHONUNBUFFERED"] = "1"
    environment.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128")
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        process = subprocess.Popen(
            config["command"],
            cwd=MPLUG_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log.write(line)
        return_code = process.wait()
    artifacts = inspect_training_artifacts(
        config, require_loss_decrease=config["profile"] == "smoke"
    )
    verification = None
    if return_code == 0 and artifacts["passed"] and config["profile"] == "smoke":
        verify_output = run_dir / "adapter_reload_verification.json"
        verify_log = run_dir / "adapter_reload.log"
        verify_command = [
            config["python_executable"],
            str(Path(__file__).resolve().parent / "verify_adapter.py"),
            "--config",
            str(args.config.resolve()),
            "--output",
            str(verify_output),
        ]
        with verify_log.open("w", encoding="utf-8", newline="\n") as log:
            verify_process = subprocess.run(
                verify_command,
                cwd=WORKSPACE_ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        verification = {
            "return_code": verify_process.returncode,
            "output": str(verify_output),
            "log": str(verify_log),
            "answer_produced": (
                verify_output.exists()
                and bool(read_json(verify_output).get("generated_answer"))
            ),
        }
    result = {
        "return_code": return_code,
        "training_log": str(log_path),
        "artifacts": artifacts,
        "adapter_reload_verification": verification,
    }
    write_json(run_dir / "training_result.json", result)
    verification_failed = verification is not None and (
        verification["return_code"] != 0 or not verification["answer_produced"]
    )
    if return_code != 0 or not artifacts["passed"] or verification_failed:
        raise RuntimeError(f"Training run failed validation: {result}")


def finalize_existing_smoke(args: argparse.Namespace) -> None:
    config = read_json(args.config)
    run_dir = args.config.resolve().parent
    artifacts = inspect_training_artifacts(config)
    verification_path = run_dir / "adapter_reload_verification.json"
    answer = ""
    if verification_path.exists():
        answer = str(read_json(verification_path).get("generated_answer") or "").strip()
    passed = artifacts["passed"] and bool(answer)
    result = {
        "return_code": 0 if passed else 1,
        "training_log": str(run_dir / "training.log"),
        "artifacts": artifacts,
        "adapter_reload_verification": {
            "return_code": 0 if answer else 1,
            "output": str(verification_path),
            "answer_produced": bool(answer),
        },
        "passed": passed,
    }
    write_json(run_dir / "training_result.json", result)
    if not passed:
        raise RuntimeError(f"Existing smoke artifacts did not pass: {result}")
    print(run_dir / "training_result.json")


def parse_named_path(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Expected NAME=PATH")
    name, raw_path = value.split("=", 1)
    if not name or not raw_path:
        raise argparse.ArgumentTypeError("Expected non-empty NAME=PATH")
    return name, Path(raw_path)


def matrix_run_specs(
    datasets: dict[str, Path],
    hard_dataset: Path | None = None,
    choice_dataset: Path | None = None,
) -> list[tuple[str, Path, int]]:
    required = ("advtest_10k", "random_10k", "official_qa_10k")
    missing = [name for name in required if name not in datasets]
    if missing:
        raise ValueError(f"Training matrix is missing datasets: {missing}")
    specs = [
        (f"{name}_open_s{seed}", datasets[name], seed)
        for name in required
        for seed in (42, 43, 44)
    ]
    if hard_dataset is not None:
        specs.append(("advtest_hard_10k_open_s42", hard_dataset, 42))
    if choice_dataset is not None:
        specs.append(("advtest_10k_choice_s42", choice_dataset, 42))
    return specs


def matrix_image_root(
    run_name: str, main_image_root: Path, hard_image_root: Path | None
) -> Path:
    if run_name == "advtest_hard_10k_open_s42":
        if hard_image_root is None:
            raise ValueError(
                "--hard-image-root is required when --hard-dataset is provided"
            )
        return hard_image_root
    return main_image_root


def prepare_matrix(args: argparse.Namespace) -> None:
    specs = matrix_run_specs(
        dict(args.dataset), args.hard_dataset, args.choice_dataset
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for run_name, dataset, seed in specs:
        image_root = matrix_image_root(
            run_name, args.image_root, args.hard_image_root
        )
        config_path = prepare_run(
            argparse.Namespace(
                run_dir=output_dir / "runs" / run_name,
                model=args.model,
                dataset=dataset,
                image_root=image_root,
                profile="formal",
                seed=seed,
                python_executable=args.python_executable,
                learning_rate=args.learning_rate,
                lora_r=args.lora_r,
                lora_alpha=args.lora_alpha,
                disable_visual_abstractor=args.disable_visual_abstractor,
            )
        )
        config = read_json(config_path)
        entries.append(
            {
                "run_name": run_name,
                "seed": seed,
                "question_format": "choice" if "_choice_" in run_name else "open",
                "dataset": str(dataset.resolve()),
                "dataset_sha256": config["source_dataset_sha256"],
                "image_root": str(image_root.resolve()),
                "config": str(config_path.resolve()),
                "adapter_output": config["adapter_output"],
                "training": config["training"],
            }
        )
    script_path = Path(__file__).resolve()
    ps_lines = [
        "& '" + str(args.python_executable).replace("'", "''") + "' '"
        + str(script_path).replace("'", "''") + "' execute --config '"
        + entry["config"].replace("'", "''") + "'"
        for entry in entries
    ]
    sh_lines = [
        shlex.join(
            [
                str(args.python_executable),
                str(script_path),
                "execute",
                "--config",
                entry["config"],
            ]
        )
        for entry in entries
    ]
    (output_dir / "execute_matrix.ps1").write_text(
        "$ErrorActionPreference = 'Stop'\n" + "\n".join(ps_lines) + "\n",
        encoding="utf-8",
    )
    (output_dir / "execute_matrix.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n" + "\n".join(sh_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    pilot_names = {
        "advtest_10k_open_s42",
        "random_10k_open_s42",
        "official_qa_10k_open_s42",
    }
    pilot_entries = [entry for entry in entries if entry["run_name"] in pilot_names]
    remaining_entries = [entry for entry in entries if entry["run_name"] not in pilot_names]
    for stem, selected in (
        ("execute_pilots", pilot_entries),
        ("execute_after_pilots", remaining_entries),
    ):
        selected_ps = [ps_lines[entries.index(entry)] for entry in selected]
        selected_sh = [sh_lines[entries.index(entry)] for entry in selected]
        (output_dir / f"{stem}.ps1").write_text(
            "$ErrorActionPreference = 'Stop'\n" + "\n".join(selected_ps) + "\n",
            encoding="utf-8",
        )
        (output_dir / f"{stem}.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            + "\n".join(selected_sh)
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    write_json(
        output_dir / "training_matrix_manifest.json",
        {
            "schema_version": "rq3_training_matrix_v1",
            "base_model": str(args.model.resolve()),
            "main_image_root": str(args.image_root.resolve()),
            "hard_image_root": (
                str(args.hard_image_root.resolve()) if args.hard_image_root else None
            ),
            "required_server_gpu_memory_gb": 24,
            "main_runs": 9,
            "ablation_runs": len(entries) - 9,
            "runs": entries,
        },
    )
    print(output_dir / "training_matrix_manifest.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run reproducible mPLUG RQ3 QLoRA.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--profile", choices=sorted(PROFILES), required=True)
    prepare.add_argument("--dataset", type=Path, required=True)
    prepare.add_argument("--image-root", type=Path, required=True)
    prepare.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    prepare.add_argument("--run-dir", type=Path, required=True)
    prepare.add_argument("--seed", type=int, default=42)
    prepare.add_argument("--python-executable", default=sys.executable)
    prepare.set_defaults(func=prepare_run)

    execute = subparsers.add_parser("execute")
    execute.add_argument("--config", type=Path, required=True)
    execute.set_defaults(func=execute_run)

    finalize = subparsers.add_parser(
        "finalize-smoke", help="Finalize a trained smoke after a separate reload check."
    )
    finalize.add_argument("--config", type=Path, required=True)
    finalize.set_defaults(func=finalize_existing_smoke)

    matrix = subparsers.add_parser(
        "matrix", help="Prepare the fixed 3-method x 3-seed formal matrix."
    )
    matrix.add_argument(
        "--dataset", action="append", type=parse_named_path, required=True
    )
    matrix.add_argument("--hard-dataset", type=Path)
    matrix.add_argument("--choice-dataset", type=Path)
    matrix.add_argument("--image-root", type=Path, required=True)
    matrix.add_argument("--hard-image-root", type=Path)
    matrix.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    matrix.add_argument("--output-dir", type=Path, required=True)
    matrix.add_argument("--python-executable", default=sys.executable)
    matrix.add_argument("--learning-rate", type=float, default=1e-4)
    matrix.add_argument("--lora-r", type=int, default=16)
    matrix.add_argument("--lora-alpha", type=int, default=32)
    matrix.add_argument("--disable-visual-abstractor", action="store_true")
    matrix.set_defaults(func=prepare_matrix)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
