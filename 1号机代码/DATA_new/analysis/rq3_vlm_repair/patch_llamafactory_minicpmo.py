"""Apply the image-only MiniCPM-o compatibility patch to LLaMA-Factory."""

import argparse
from pathlib import Path


DEFAULT_COLLATOR = Path(
    "E:/Project/ADVTEST/scratch/rq3_vlm_repair/vendor/LLaMA-Factory-v0.9.2/"
    "src/llamafactory/data/collator.py"
)
MARKER = "MiniCPM-o image-only batches do not need a synthetic audio sample."
ORIGINAL = '''        if (
            self.template.mm_plugin.audio_token is not None and sum(batch_audlens) == 0
        ):  # avoid process hanging in zero3/fsdp case
'''
PATCHED = '''        if (
            self.template.mm_plugin.audio_token is not None
            and sum(batch_audlens) == 0
            # MiniCPM-o image-only batches do not need a synthetic audio sample.
            and getattr(getattr(self.model, "config", None), "model_type", None) != "minicpmo"
        ):  # avoid process hanging in zero3/fsdp case
'''


def apply_patch(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    if MARKER in content:
        return "already_patched"
    if ORIGINAL not in content:
        raise ValueError(f"Unsupported LLaMA-Factory collator layout: {path}")
    path.write_text(content.replace(ORIGINAL, PATCHED, 1), encoding="utf-8")
    return "patched"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collator", type=Path, default=DEFAULT_COLLATOR)
    args = parser.parse_args()
    print(apply_patch(args.collator))


if __name__ == "__main__":
    main()
