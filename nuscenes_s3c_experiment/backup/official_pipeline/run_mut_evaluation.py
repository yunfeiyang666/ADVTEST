#!/usr/bin/env python3
"""
run_mut_evaluation.py — RQ3 MUT (Model Under Test) 评测框架

对生成的 QA 集，并行调用 3-5 个视觉语言模型（VLM/LLM），
记录每个模型对每道题的回答，输出 Table C (model_performance_raw_our.csv)。

MUT 列表（可按需配置）：
  - text_llm     : 仅文本模式（用于消融：去掉图像看是否能答对）
  - qwen-plus    : 通义千问 VL  (yunwu.ai)
  - gpt-4o       : OpenAI GPT-4o  (需单独 key)
  - glm-4v-plus  : 智谱 GLM-4V  (yunwu.ai)

注意：
  - 对于视觉模型，需要场景图像路径；本框架提供 image_path 接口
  - 如无图像，自动降级为纯文本模式（不传图）
  - 所有 MUT 调用是并发的（ThreadPoolExecutor）
"""
from __future__ import annotations

import argparse, json, logging, pathlib, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent))
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("run_mut_eval")


# ─────────────────────────────────────────────────────────────────────────────
# MUT 配置表
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MUT_CONFIGS = [
    {
        "name":     "text_llm_qwen-plus",
        "model":    "qwen-plus",
        "mode":     "text",          # "text" | "vision"
        "api_base": None,            # None = use LLM_CONFIG default
        "api_key":  None,
        "max_tokens": 60,
        "enabled":  True,
    },
    {
        "name":     "text_llm_glm-4-air",
        "model":    "glm-4-air",
        "mode":     "text",
        "api_base": None,
        "api_key":  None,
        "max_tokens": 60,
        "enabled":  True,
    },
    # ── 以下需要对应模型的图像输入能力 ──────────────────────────────────
    {
        "name":     "vision_qwen-vl-plus",
        "model":    "qwen-vl-plus",
        "mode":     "vision",
        "api_base": None,
        "api_key":  None,
        "max_tokens": 80,
        "enabled":  False,   # 需要场景图像时开启
    },
    {
        "name":     "vision_gpt-4o",
        "model":    "gpt-4o",
        "mode":     "vision",
        "api_base": "https://api.openai.com/v1",  # 需填写独立 key
        "api_key":  "",
        "max_tokens": 80,
        "enabled":  False,
    },
]

# 评测 Prompt 模板（纯文本模式）
_TEXT_EVAL_PROMPT = """\
You are evaluating an autonomous driving scene (scene={scene_id}, frame={frame_id}).
The scene graph contains vehicles, pedestrians, and other objects with directed spatial relations.

Question: {question}

Instructions:
- Answer with ONLY the object ID (e.g., "car35") or a direction/status word.
- Do NOT explain. Do NOT say "I don't know". Give your best single answer.

Answer:"""

# 评测 Prompt 模板（视觉模式，附 image）
_VISION_EVAL_PROMPT = """\
Look at the autonomous driving scene image.
Question: {question}
Answer with ONLY the object ID or a single word. No explanation."""


# ─────────────────────────────────────────────────────────────────────────────
# Single MUT call
# ─────────────────────────────────────────────────────────────────────────────

def call_mut(
    qa:          Dict,
    mut_cfg:     Dict,
    scene_id:    str,
    frame_id:    int,
    image_path:  Optional[pathlib.Path] = None,
) -> Dict:
    """Call one MUT for one QA. Returns a Table C row dict."""
    import openai, httpx, base64
    from gap_pipeline.config import LLM_CONFIG

    api_base = mut_cfg.get("api_base") or LLM_CONFIG["api_base"]
    api_key  = mut_cfg.get("api_key")  or LLM_CONFIG["api_key"]
    model    = mut_cfg["model"]
    mode     = mut_cfg.get("mode", "text")

    timeout = httpx.Timeout(connect=10, read=30, write=10, pool=5)
    client  = openai.OpenAI(
        api_key=api_key, base_url=api_base,
        http_client=httpx.Client(verify=False, timeout=timeout),
        max_retries=0,
    )

    question = qa.get("question", "")
    try:
        if mode == "vision" and image_path and image_path.exists():
            # Encode image to base64
            img_b64 = base64.b64encode(image_path.read_bytes()).decode()
            ext     = image_path.suffix.lstrip(".").lower()
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": _VISION_EVAL_PROMPT.format(question=question)},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/{ext};base64,{img_b64}"}},
                ],
            }]
        else:
            # Text-only mode
            prompt = _TEXT_EVAL_PROMPT.format(
                scene_id=scene_id, frame_id=frame_id, question=question
            )
            messages = [{"role": "user", "content": prompt}]

        t0   = time.perf_counter()
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=mut_cfg.get("max_tokens", 60),
            temperature=0.0,
            stream=False,
        )
        t1 = time.perf_counter()
        model_answer = resp.choices[0].message.content.strip()
        # Extract only the first token/word as answer (models sometimes add explanation)
        import re
        # Take first word-like token
        m = re.match(r"([\w\-]+)", model_answer)
        model_answer = m.group(1) if m else model_answer[:40]
        latency_ms = round((t1 - t0) * 1000, 1)

    except Exception as exc:
        model_answer = ""
        latency_ms   = 0.0
        logger.warning("MUT %s / %s failed: %s", mut_cfg["name"], qa.get("question_id"), exc)

    from rq_tables import build_table_c_row
    row = build_table_c_row(qa, mut_cfg["name"], model_answer, scene_id, frame_id)
    row["latency_ms"] = latency_ms
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Main evaluation runner
# ─────────────────────────────────────────────────────────────────────────────

def run_mut_evaluation(
    qa_json_path:  str,
    out_csv:       str = "output/model_performance_raw_our.csv",
    scene_id:      str = "scene-0553",
    frame_id:      int = 8,
    image_dir:     Optional[str] = None,
    n_workers:     int = 4,
    mut_configs:   Optional[List[Dict]] = None,
    sample_n:      int = 0,   # 0 = all
) -> None:
    from rq_tables import write_table_c

    qa_pairs = json.loads(pathlib.Path(qa_json_path).read_text("utf-8"))
    if isinstance(qa_pairs, dict):
        qa_pairs = qa_pairs.get("qa_pairs", [])
    if sample_n > 0:
        import random; qa_pairs = random.sample(qa_pairs, min(sample_n, len(qa_pairs)))

    muts = [c for c in (mut_configs or DEFAULT_MUT_CONFIGS) if c.get("enabled", True)]
    logger.info("MUT evaluation: %d QAs × %d models = %d calls",
                len(qa_pairs), len(muts), len(qa_pairs) * len(muts))

    out_path = pathlib.Path(out_csv)
    first_write = True

    # Submit all (qa, mut) pairs in parallel
    tasks = [(qa, mut) for qa in qa_pairs for mut in muts]
    n_done = 0

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {
            executor.submit(
                call_mut, qa, mut, scene_id, frame_id,
                pathlib.Path(image_dir) / f"{scene_id}_frame{frame_id}.png"
                if image_dir else None,
            ): (qa, mut)
            for qa, mut in tasks
        }
        for future in as_completed(futures):
            try:
                row = future.result()
            except Exception as exc:
                qa, mut = futures[future]
                logger.error("Future failed qa=%s mut=%s: %s",
                             qa.get("question_id","?"), mut["name"], exc)
                continue
            mode = "w" if first_write else "a"
            write_table_c(row, out_path, mode=mode)
            first_write = False
            n_done += 1
            if n_done % 20 == 0:
                logger.info("  %d/%d calls done", n_done, len(tasks))

    logger.info("Done. Table C → %s  (%d rows)", out_path, n_done)
    _print_table_c_summary(out_path)


def _print_table_c_summary(csv_path: pathlib.Path) -> None:
    import csv as _csv
    from collections import Counter, defaultdict

    rows = list(_csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    if not rows:
        return

    SEP = "─" * 65
    print(f"\n{SEP}")
    print("  Table C — MUT Evaluation Summary")
    print(SEP)

    # Per-model pass rate
    by_model: Dict[str, list] = defaultdict(list)
    for r in rows:
        by_model[r["model_name"]].append(r["pass_fail"] == "pass")

    print(f"\n  {'Model':<30} {'Pass':>6} {'Total':>6} {'Rate':>8}")
    print(f"  {'─'*55}")
    for model, passes in sorted(by_model.items()):
        n_pass = sum(passes)
        n_total = len(passes)
        print(f"  {model:<30} {n_pass:>6} {n_total:>6} {n_pass/n_total*100:>7.1f}%")

    # Per-complexity breakdown
    print(f"\n  Pass rate by complexity:")
    by_cmplx: Dict[str, list] = defaultdict(list)
    for r in rows:
        by_cmplx[r.get("question_complexity","?")].append(r["pass_fail"]=="pass")
    for cmpl, passes in sorted(by_cmplx.items()):
        n_p = sum(passes); n_t = len(passes)
        print(f"    {cmpl:<12} {n_p}/{n_t} = {n_p/n_t*100:.1f}%")

    # Error type dist
    err_dist = Counter(r["error_type"] for r in rows if r["error_type"])
    if err_dist:
        print(f"\n  Error type distribution:")
        for et, c in err_dist.most_common():
            print(f"    {et:<25} {c}")
    print(f"\n{SEP}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="MUT Evaluation — Table C")
    p.add_argument("qa_json", help="gap_result JSON (contains qa_pairs)")
    p.add_argument("--out",   default="output/model_performance_raw_our.csv")
    p.add_argument("--scene-id",   default="scene-0553")
    p.add_argument("--frame-id",   type=int, default=8)
    p.add_argument("--image-dir",  default=None, help="dir with scene images")
    p.add_argument("--workers",    type=int, default=4)
    p.add_argument("--sample-n",   type=int, default=0,
                   help="Evaluate only N random QAs (0=all)")
    args = p.parse_args()
    run_mut_evaluation(
        args.qa_json, out_csv=args.out,
        scene_id=args.scene_id, frame_id=args.frame_id,
        image_dir=args.image_dir, n_workers=args.workers,
        sample_n=args.sample_n,
    )
