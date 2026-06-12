"""Minimal MiniCPM-o smoke test, independent from suite argparse.

Usage:
  .\.venv310\Scripts\python.exe 1号机代码/DATA_new/analysis/rq1_error_detection/run_minicpm_smoke.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("PYTHONNOUSERSITE", "1")
os.environ.setdefault("HF_HOME", "E:/hf_cache")
os.environ.setdefault("HF_MODULES_CACHE", "E:/hf_cache/modules")
os.environ.setdefault("TRANSFORMERS_CACHE", "E:/hf_cache")

HERE = Path(__file__).absolute().parent
WORKSPACE_ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def load_first_question() -> dict:
    suite_path = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "analysis" / "fixed_budget_results" / "advtest_suite.jsonl"
    with suite_path.open("r", encoding="utf-8") as handle:
        return json.loads(handle.readline())


def ensure_mosaic(question: dict) -> Path:
    import evaluator

    scene_frame = question.get("scene_frame", "scene-0013_frame31")
    scene_graph = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "outputs" / scene_frame / "offline" / "scene_graphs" / f"{scene_frame}_filtered_scene_graph.json"
    out_dir = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "analysis" / "suite_eval_results" / "minicpm_smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    mosaic_path = out_dir / f"{scene_frame}_mosaic.jpg"
    if mosaic_path.exists():
        return mosaic_path
    dataroot = WORKSPACE_ROOT / "1号机代码" / "DATA_new" / "data"
    graph = json.loads(scene_graph.read_text(encoding="utf-8"))
    ok = evaluator.render_labeled_mosaic(graph, dataroot, mosaic_path)
    if not ok:
        raise RuntimeError(f"Failed to render mosaic for {scene_frame}")
    return mosaic_path


def main() -> int:
    log(f"python={sys.executable}")
    log("preloading torch")
    import torch
    log(f"torch={torch.__version__} cuda={torch.cuda.is_available()}")

    log("preloading transformers")
    import transformers
    from transformers import Qwen2Config  # noqa: F401
    log(f"transformers={transformers.__version__}; Qwen2Config OK")

    question = load_first_question()
    log(f"question={question.get('question')}")
    mosaic_path = ensure_mosaic(question)
    log(f"mosaic={mosaic_path}")

    import evaluator
    log("constructing MiniCPMOEvaluator")
    vlm = evaluator.MiniCPMOEvaluator()
    log(f"model_loaded={vlm.model is not None}")

    log("running inference")
    pred, ok = vlm.evaluate(question, mosaic_path)
    result = {"predicted": pred, "is_correct": ok, "image_path": str(mosaic_path)}
    out_path = mosaic_path.parent / "minicpm_smoke_result.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

