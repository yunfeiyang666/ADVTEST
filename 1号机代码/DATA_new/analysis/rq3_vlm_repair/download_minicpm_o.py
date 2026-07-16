"""Resumable core-weight download for the local MiniCPM-o 2.6 smoke run."""

import argparse
import subprocess
from pathlib import Path
from urllib.parse import quote_plus


MODEL_ID = "OpenBMB/MiniCPM-o-2_6"
REVISION = "master"
API_TEMPLATE = "https://www.modelscope.cn/api/v1/models/{model}/repo?Revision={revision}&FilePath={path}"

CORE_FILES = (
    ".gitattributes",
    "added_tokens.json",
    "config.json",
    "configuration.json",
    "configuration_minicpm.py",
    "image_processing_minicpmv.py",
    "merges.txt",
    "model.safetensors.index.json",
    "modeling_minicpmo.py",
    "modeling_navit_siglip.py",
    "preprocessor_config.json",
    "processing_minicpmo.py",
    "resampler.py",
    "special_tokens_map.json",
    "tokenization_minicpmo_fast.py",
    "tokenizer.json",
    "tokenizer_config.json",
    "utils.py",
    "vocab.json",
)
WEIGHT_FILES = tuple(f"model-{index:05d}-of-00004.safetensors" for index in range(1, 5))


def file_url(path: str) -> str:
    return API_TEMPLATE.format(
        model=MODEL_ID,
        revision=REVISION,
        path=quote_plus(path),
    )


def download(curl: str, destination: Path, filename: str, resume: bool) -> None:
    output = destination / filename
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        curl,
        "--noproxy",
        "*",
        "--fail",
        "--location",
        "--retry",
        "10",
        "--retry-all-errors",
        "--retry-delay",
        "5",
        "--connect-timeout",
        "30",
    ]
    if resume:
        command.extend(["--continue-at", "-"])
    command.extend(["--output", str(output), file_url(filename)])
    print(f"Downloading {filename} -> {output}", flush=True)
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("E:/hf_cache/modelscope_minicpm_core/openbmb/MiniCPM-o-2_6"),
    )
    parser.add_argument("--curl", default="curl.exe")
    parser.add_argument("--weights-only", action="store_true")
    args = parser.parse_args()

    args.model_dir.mkdir(parents=True, exist_ok=True)
    if not args.weights_only:
        for filename in CORE_FILES:
            download(args.curl, args.model_dir, filename, resume=False)
    for filename in WEIGHT_FILES:
        download(args.curl, args.model_dir, filename, resume=True)


if __name__ == "__main__":
    main()
