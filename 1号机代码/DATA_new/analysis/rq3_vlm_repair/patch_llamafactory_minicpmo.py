"""Apply the image-only MiniCPM-o compatibility patch to LLaMA-Factory."""

import argparse
from pathlib import Path


DEFAULT_COLLATOR = Path(
    "E:/Project/ADVTEST/scratch/rq3_vlm_repair/vendor/LLaMA-Factory-v0.9.2/"
    "src/llamafactory/data/collator.py"
)
MARKER = "MiniCPM-o image-only batches do not need a synthetic audio sample."
BATCH_ENCODING_MARKER = "Unwrap MiniCPM-o BatchEncoding values before Accelerate moves the batch."
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
IMPORT_ORIGINAL = "from transformers import DataCollatorForSeq2Seq\n"
IMPORT_PATCHED = '''from transformers import DataCollatorForSeq2Seq
from transformers.tokenization_utils_base import BatchEncoding
'''
HELPER_ANCHOR = "\n\ndef prepare_4d_attention_mask"
HELPER = '''


def _unwrap_minicpmo_batch_encoding(value):
    """{}"""
    if isinstance(value, BatchEncoding):
        return {{key: _unwrap_minicpmo_batch_encoding(item) for key, item in value.items()}}
    if isinstance(value, dict):
        return {{key: _unwrap_minicpmo_batch_encoding(item) for key, item in value.items()}}
    if isinstance(value, list):
        return [_unwrap_minicpmo_batch_encoding(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_unwrap_minicpmo_batch_encoding(item) for item in value)
    return value
'''.format(BATCH_ENCODING_MARKER)
MM_INPUTS_ORIGINAL = '''        )
        if "token_type_ids" in mm_inputs:
'''
MM_INPUTS_PATCHED = '''        )
        if getattr(getattr(self.model, "config", None), "model_type", None) == "minicpmo":
            mm_inputs = _unwrap_minicpmo_batch_encoding(mm_inputs)
        if "token_type_ids" in mm_inputs:
'''


def apply_patch(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    changed = False
    if MARKER not in content:
        if ORIGINAL not in content:
            raise ValueError(f"Unsupported audio patch layout: {path}")
        content = content.replace(ORIGINAL, PATCHED, 1)
        changed = True

    if BATCH_ENCODING_MARKER not in content:
        if IMPORT_ORIGINAL not in content or HELPER_ANCHOR not in content or MM_INPUTS_ORIGINAL not in content:
            raise ValueError(f"Unsupported BatchEncoding patch layout: {path}")
        content = content.replace(IMPORT_ORIGINAL, IMPORT_PATCHED, 1)
        content = content.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)
        content = content.replace(MM_INPUTS_ORIGINAL, MM_INPUTS_PATCHED, 1)
        changed = True

    if changed:
        path.write_text(content, encoding="utf-8")
        return "patched"
    return "already_patched"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collator", type=Path, default=DEFAULT_COLLATOR)
    args = parser.parse_args()
    print(apply_patch(args.collator))


if __name__ == "__main__":
    main()
