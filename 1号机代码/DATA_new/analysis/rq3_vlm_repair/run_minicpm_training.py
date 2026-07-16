import argparse
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

import yaml


DEFAULT_MODEL = Path("E:/hf_cache/huggingface/openbmb/MiniCPM-o-2_6")
DEFAULT_DATASET = Path(
    "E:/Project/ADVTEST/scratch/rq3_vlm_repair/data/"
    "sft_minicpm_pilot_300_v1/datasets/advtest_minicpm_pilot_300_open.json"
)
DEFAULT_IMAGE_ROOT = Path(
    "E:/Project/ADVTEST/scratch/rq3_vlm_repair/data/sft_minicpm_pilot_300_v1"
)
DEFAULT_RUN_DIR = Path(
    "E:/Project/ADVTEST/scratch/rq3_vlm_repair/runs/minicpm_o_2_6_pilot_smoke_v1"
)
DEFAULT_LLAMAFATORY_CLI = Path(
    "E:/Project/ADVTEST/scratch/rq3_vlm_repair/"
    "venv_minicpm/Scripts/llamafactory-cli.exe"
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def check_model_shards(model_dir: Path) -> dict:
    index_path = model_dir / "model.safetensors.index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Missing model weight index: {index_path}")
    index = read_json(index_path)
    shard_names = sorted(set((index.get("weight_map") or {}).values()))
    if not shard_names:
        raise ValueError(f"No model shards listed in {index_path}")
    missing = [name for name in shard_names if not (model_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"MiniCPM model is incomplete: {len(missing)}/{len(shard_names)} "
            f"weight shards are missing; first={missing[:3]}"
        )
    sizes = {name: (model_dir / name).stat().st_size for name in shard_names}
    if any(size <= 0 for size in sizes.values()):
        raise ValueError("MiniCPM model contains an empty weight shard")
    return {
        "index": str(index_path.resolve()),
        "index_sha256": file_sha256(index_path),
        "shard_count": len(shard_names),
        "total_weight_bytes": sum(sizes.values()),
        "shards": sizes,
    }


def convert_for_llamafactory(
    records: list[dict], image_root: Path, limit: int, seed: int
) -> list[dict]:
    if limit <= 0 or limit > len(records):
        raise ValueError(f"Invalid sample limit {limit} for {len(records)} records")
    indices = list(range(len(records)))
    random.Random(seed).shuffle(indices)
    selected = [records[index] for index in indices[:limit]]
    output = []
    seen_ids = set()
    for record in selected:
        source_id = str((record.get("metadata") or {}).get("source_question_id") or "")
        if not source_id or source_id in seen_ids:
            raise ValueError("MiniCPM training records need unique source_question_id values")
        seen_ids.add(source_id)
        conversations = record.get("conversations") or []
        if len(conversations) != 2:
            raise ValueError(f"Expected one-turn conversation for {source_id}")
        human = dict(conversations[0])
        assistant = dict(conversations[1])
        prompt = str(human.get("value") or "").replace("<|image|>", "<image>")
        if prompt.count("<image>") != 1:
            raise ValueError(f"Expected exactly one image token for {source_id}")
        image_path = (image_root / str(record.get("image") or "")).resolve()
        if not image_path.is_file():
            raise FileNotFoundError(f"Missing training image: {image_path}")
        if human.get("from") != "human" or assistant.get("from") != "gpt":
            raise ValueError(f"Unexpected conversation roles for {source_id}")
        human["value"] = prompt
        output.append(
            {
                "id": str(record.get("id") or source_id),
                "conversations": [human, assistant],
                "images": [str(image_path)],
            }
        )
    return output


def smoke_config(model: Path, run_dir: Path) -> dict:
    return {
        "model_name_or_path": str(model.resolve()),
        "trust_remote_code": True,
        "image_max_pixels": 262144,
        "stage": "sft",
        "do_train": True,
        "finetuning_type": "lora",
        "lora_rank": 8,
        "lora_alpha": 16,
        "lora_dropout": 0.05,
        "lora_target": "all",
        "freeze_vision_tower": True,
        "freeze_multi_modal_projector": True,
        "quantization_bit": 4,
        "quantization_method": "bitsandbytes",
        "dataset": "rq3_minicpm_pilot_smoke",
        "dataset_dir": str((run_dir / "data").resolve()),
        "template": "minicpm_o",
        "cutoff_len": 512,
        "max_samples": 32,
        "overwrite_cache": True,
        "preprocessing_num_workers": 1,
        "dataloader_num_workers": 0,
        "output_dir": str((run_dir / "adapter").resolve()),
        "logging_steps": 1,
        "save_strategy": "steps",
        "save_steps": 20,
        "save_total_limit": 1,
        "plot_loss": True,
        "overwrite_output_dir": True,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 8,
        "learning_rate": 1e-4,
        "num_train_epochs": 1.0,
        "max_steps": 20,
        "lr_scheduler_type": "cosine",
        "warmup_ratio": 0.03,
        "fp16": True,
        "bf16": False,
        "gradient_checkpointing": True,
        "optim": "paged_adamw_8bit",
        "seed": 42,
        "data_seed": 42,
        "report_to": "none",
    }


def prepare_run(args: argparse.Namespace) -> Path:
    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    records = read_json(args.dataset)
    if not isinstance(records, list):
        raise ValueError("SFT dataset must be a JSON list")
    converted = convert_for_llamafactory(records, args.image_root, 32, 42)
    data_dir = run_dir / "data"
    data_path = data_dir / "rq3_minicpm_pilot_smoke.json"
    write_json(data_path, converted)
    write_json(
        data_dir / "dataset_info.json",
        {
            "rq3_minicpm_pilot_smoke": {
                "file_name": data_path.name,
                "formatting": "sharegpt",
                "columns": {"messages": "conversations", "images": "images"},
            }
        },
    )
    config = smoke_config(args.model, run_dir)
    config_path = run_dir / "train_smoke.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "rq3_minicpm_o_2_6_smoke_v1",
        "model": str(args.model.resolve()),
        "model_complete": False,
        "source_dataset": str(args.dataset.resolve()),
        "source_dataset_sha256": file_sha256(args.dataset),
        "converted_dataset": str(data_path.resolve()),
        "converted_dataset_sha256": file_sha256(data_path),
        "rows": len(converted),
        "seed": 42,
        "config": str(config_path.resolve()),
        "llamafactory_cli": str(args.llamafactory_cli.resolve()),
    }
    write_json(run_dir / "run_manifest.json", manifest)
    return config_path


def run_preflight(args: argparse.Namespace) -> dict:
    model = check_model_shards(args.model)
    if not args.llamafactory_cli.is_file():
        raise FileNotFoundError(f"Missing LLaMA-Factory CLI: {args.llamafactory_cli}")
    command = [
        str(args.python_executable),
        "-c",
        (
            "import torch,bitsandbytes,transformers,accelerate,peft; "
            "assert torch.cuda.is_available(); "
            "print(torch.__version__, bitsandbytes.__version__, "
            "transformers.__version__, accelerate.__version__, peft.__version__)"
        ),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    status = {"model": model, "environment": result.stdout.strip()}
    manifest_path = args.run_dir / "run_manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        manifest["model_complete"] = True
        manifest["model_shards"] = model
        manifest["environment"] = result.stdout.strip()
        write_json(manifest_path, manifest)
    return status


def launch(args: argparse.Namespace) -> None:
    config_path = args.run_dir / "train_smoke.yaml"
    if not config_path.is_file():
        config_path = prepare_run(args)
    run_preflight(args)
    log_path = args.run_dir / "train_smoke.log"
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        subprocess.run(
            [str(args.llamafactory_cli), "train", str(config_path)],
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=True,
        )


def verify_adapter(run_dir: Path) -> dict:
    adapter_dir = run_dir / "adapter"
    required = [adapter_dir / "adapter_config.json", adapter_dir / "adapter_model.safetensors"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Smoke adapter is incomplete: {missing}")
    trainer_state = adapter_dir / "trainer_state.json"
    state = read_json(trainer_state) if trainer_state.exists() else {}
    losses = [
        float(row["loss"])
        for row in state.get("log_history") or []
        if row.get("loss") is not None
    ]
    if not losses or any(not (loss == loss and abs(loss) < float("inf")) for loss in losses):
        raise ValueError("Training did not record finite losses")
    result = {
        "adapter_dir": str(adapter_dir.resolve()),
        "adapter_sha256": file_sha256(required[1]),
        "logged_losses": losses,
        "first_loss": losses[0],
        "last_loss": losses[-1],
    }
    write_json(run_dir / "adapter_verification.json", result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the RQ3 MiniCPM-o 2.6 QLoRA pilot.")
    parser.add_argument("command", choices=["prepare", "preflight", "launch", "verify"])
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--image-root", type=Path, default=DEFAULT_IMAGE_ROOT)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--llamafactory-cli", type=Path, default=DEFAULT_LLAMAFATORY_CLI)
    parser.add_argument(
        "--python-executable",
        type=Path,
        default=DEFAULT_LLAMAFATORY_CLI.with_name("python.exe"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "prepare":
        print(prepare_run(args))
    elif args.command == "preflight":
        print(json.dumps(run_preflight(args), ensure_ascii=False))
    elif args.command == "launch":
        launch(args)
    else:
        print(json.dumps(verify_adapter(args.run_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
