import argparse
import sys
from collections import Counter
from pathlib import Path

import torch
from PIL import Image
from peft import PeftModel
from transformers import BitsAndBytesConfig
from transformers.models.clip.image_processing_clip import CLIPImageProcessor

from data_ops import read_json, write_json


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
MPLUG_ROOT = WORKSPACE_ROOT / "baselines" / "mPLUG-Owl" / "mPLUG-Owl2"
sys.path.insert(0, str(MPLUG_ROOT))

from mplug_owl2.constants import DEFAULT_IMAGE_TOKEN, IMAGE_TOKEN_INDEX  # noqa: E402
from mplug_owl2.conversation import conv_templates  # noqa: E402
from mplug_owl2.mm_utils import tokenizer_image_token  # noqa: E402
from mplug_owl2.model import MPLUGOwl2LlamaForCausalLM  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402


def load_adapter(config: dict):
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )
    base = MPLUGOwl2LlamaForCausalLM.from_pretrained(
        config["model_path"],
        low_cpu_mem_usage=True,
        device_map={"": 0},
        quantization_config=quantization,
    )
    base.get_model().vision_model.to(dtype=torch.float16, device="cuda")
    base.get_model().visual_abstractor.to(dtype=torch.float16, device="cuda")
    adapter_dir = Path(config["adapter_output"])
    non_lora_path = adapter_dir / "non_lora_trainables.bin"
    if non_lora_path.exists():
        weights = torch.load(non_lora_path, map_location="cpu")
        weights = {
            (key[11:] if key.startswith("base_model.") else key): value
            for key, value in weights.items()
        }
        if any(key.startswith("model.model.") for key in weights):
            weights = {
                (key[6:] if key.startswith("model.") else key): value
                for key, value in weights.items()
            }
        base.load_state_dict(weights, strict=False)
    model = PeftModel.from_pretrained(base, adapter_dir)
    devices = Counter(str(parameter.device) for parameter in model.parameters())
    print(f"[rq3-smoke] adapter parameter devices: {dict(devices)}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(config["model_path"], use_fast=False)
    processor = CLIPImageProcessor.from_pretrained(config["model_path"])
    return tokenizer, model, processor


def verify(config_path: Path, output_path: Path) -> None:
    config = read_json(config_path)
    rows = read_json(Path(config["training_data"]))
    record = rows[0]
    human = str(record["conversations"][0]["value"])
    question = human.replace(DEFAULT_IMAGE_TOKEN, "", 1).strip()
    conversation = conv_templates["mplug_owl2"].copy()
    conversation.append_message(conversation.roles[0], DEFAULT_IMAGE_TOKEN + "\n" + question)
    conversation.append_message(conversation.roles[1], None)
    prompt = conversation.get_prompt()

    tokenizer, model, processor = load_adapter(config)
    image_path = Path(config["image_root"]) / record["image"]
    image = Image.open(image_path).convert("RGB")
    image_tensor = (
        processor.preprocess(image, return_tensors="pt")["pixel_values"]
        .half()
        .to("cuda")
    )
    input_ids = tokenizer_image_token(
        prompt, tokenizer, IMAGE_TOKEN_INDEX, return_tensors="pt"
    ).unsqueeze(0).to("cuda")
    model.eval()
    with torch.inference_mode():
        outputs = model(
            input_ids=input_ids,
            images=image_tensor,
            use_cache=False,
            return_dict=True,
        )
    top_tokens = outputs.logits[0, -1].topk(20).indices.tolist()
    answer = next(
        (
            tokenizer.decode([token], skip_special_tokens=True).strip()
            for token in top_tokens
            if tokenizer.decode([token], skip_special_tokens=True).strip()
        ),
        "",
    )
    if not answer:
        raise RuntimeError("Reloaded adapter produced an empty answer")
    write_json(
        output_path,
        {
            "schema_version": "rq3_adapter_reload_verification_v1",
            "record_id": record["id"],
            "image": str(image_path),
            "generated_answer": answer,
            "verification_mode": "single_visual_forward_greedy_next_token",
            "adapter_output": config["adapter_output"],
            "model_checkpoint_sha256": config["model_checkpoint_sha256"],
        },
    )
    print(answer)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(args.config, args.output)


if __name__ == "__main__":
    main()
