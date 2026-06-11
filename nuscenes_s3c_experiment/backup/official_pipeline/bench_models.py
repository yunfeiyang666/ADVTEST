#!/usr/bin/env python3
"""
bench_models.py — 学校 OpenAI 兼容接口模型基准测试

目标：
  1) 对比模型可用性（是否支持 chat.completions）
  2) 对比生成速度（RTT / tok/s）
  3) 对比生成质量（Cypher 语法通过率）

默认模型列表：
  - Qwen3.5-35B-A3B
  - Qwen3.5-27B
  - Qwen3.5-122B-A10B
  - BGE-M3
  - Whisper-large-v3

说明：
  - BGE-M3（Embedding）和 Whisper-large-v3（ASR）通常不支持 chat.completions。
  - 若它们返回接口不支持错误，脚本会记录为 unsupported，不会中断整体测试。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import statistics
import time
from typing import Dict, List, Any

import httpx
import openai
def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")

DEFAULT_MODELS = [
    "Qwen3.5-35B-A3B",
    "Qwen3.5-27B",
    "Qwen3.5-122B-A10B",
    "BGE-M3",
    "Whisper-large-v3",
]

SYSTEM_PROMPT = (
    "You are a Neo4j Cypher expert. "
    "Return only executable Cypher without markdown fences."
)

TEST_PROMPT = """\
Generate ONE Cypher query for this spatial chain in an autonomous driving scene graph:
Path: ego -> truck1 -> car35
Constraints:
- Match exact IDs for ego, truck1, car35
- Return n1_id, n2_id, n3_id, r1_dir8, r2_dir8, sibling_ids
- Include sibling candidates from truck1's outgoing neighbors excluding ego and car35
- LIMIT 1
Return ONLY Cypher.
"""


def _looks_like_cypher(text: str) -> bool:
    if not text:
        return False
    s = text.strip()
    if "```" in s:
        return False
    if not re.match(r"(?is)^(MATCH|OPTIONAL|WITH|UNWIND|CALL|CREATE|MERGE)\b", s):
        return False
    return "RETURN" in s.upper()


def _build_client(
    api_base: str,
    api_key: str,
    timeout_connect: float,
    timeout_read: float,
    trust_env_proxy: bool,
) -> openai.OpenAI:
    timeout = httpx.Timeout(connect=timeout_connect, read=timeout_read, write=10.0, pool=5.0)
    return openai.OpenAI(
        api_key=api_key,
        base_url=api_base.rstrip("/"),
        http_client=httpx.Client(timeout=timeout, trust_env=trust_env_proxy),
        timeout=timeout_read,
        max_retries=0,
    )


def _one_call(client: openai.OpenAI, model: str, max_tokens: int, temperature: float) -> Dict[str, Any]:
    disable_thinking = _env_bool("VQA_DISABLE_THINKING", True)
    extra_kwargs = (
        {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
        if disable_thinking
        else {}
    )
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": TEST_PROMPT},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        stream=False,
        **extra_kwargs,
    )
    t1 = time.perf_counter()
    ms = (t1 - t0) * 1000
    msg = (resp.choices[0].message.content or "").strip()
    usage = resp.usage
    prompt_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tok = int(getattr(usage, "completion_tokens", 0) or 0)
    tok_per_sec = (completion_tok / (ms / 1000)) if ms > 0 else 0.0
    return {
        "ms": ms,
        "prompt_tokens": prompt_tok,
        "completion_tokens": completion_tok,
        "tok_per_sec": tok_per_sec,
        "is_cypher": _looks_like_cypher(msg),
        "preview": msg[:180],
    }


def benchmark_model(
    *,
    client: openai.OpenAI,
    model: str,
    n_calls: int,
    max_tokens: int,
    temperature: float,
) -> Dict[str, Any]:
    print(f"\n  Testing {model} ...")
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    syntax_ok = 0

    for i in range(1, n_calls + 1):
        try:
            row = _one_call(client, model=model, max_tokens=max_tokens, temperature=temperature)
            rows.append(row)
            if row["is_cypher"]:
                syntax_ok += 1
            tag = "✅" if row["is_cypher"] else "❌"
            print(
                f"    call {i}: {row['ms']:.0f}ms  "
                f"{row['completion_tokens']}tok  {row['tok_per_sec']:.0f}tok/s  {tag}"
            )
        except Exception as exc:
            err = str(exc)
            errors.append(err)
            print(f"    call {i}: ERROR — {err[:180]}")

    if not rows:
        unsupported = any(
            k in " ".join(errors).lower()
            for k in ("unsupported", "not support", "invalid model", "model not found")
        )
        return {
            "model": model,
            "n_calls": n_calls,
            "n_success": 0,
            "n_errors": len(errors),
            "unsupported_for_chat_completions": unsupported,
            "errors": errors[:3],
        }

    ms_list = [r["ms"] for r in rows]
    tps_list = [r["tok_per_sec"] for r in rows]
    completion_tok = [r["completion_tokens"] for r in rows]
    prompt_tok = [r["prompt_tokens"] for r in rows]
    syntax_rate = syntax_ok / len(rows)

    return {
        "model": model,
        "n_calls": n_calls,
        "n_success": len(rows),
        "n_errors": len(errors),
        "unsupported_for_chat_completions": False,
        "syntax_ok": syntax_ok,
        "syntax_ok_rate": round(syntax_rate, 3),
        "avg_ms": round(statistics.mean(ms_list), 1),
        "min_ms": round(min(ms_list), 1),
        "max_ms": round(max(ms_list), 1),
        "stdev_ms": round(statistics.stdev(ms_list), 1) if len(ms_list) > 1 else 0.0,
        "avg_tok_per_s": round(statistics.mean(tps_list), 1),
        "avg_prompt_tokens": round(statistics.mean(prompt_tok), 1),
        "avg_completion_tokens": round(statistics.mean(completion_tok), 1),
        "preview_example": rows[0]["preview"],
        "errors": errors[:3],
    }


def _parse_models(raw: str) -> List[str]:
    return [m.strip() for m in raw.split(",") if m.strip()]


def parse_args() -> argparse.Namespace:
    default_trust_env = os.getenv("VQA_TRUST_ENV_PROXY", "false").lower() in ("1", "true", "yes")
    p = argparse.ArgumentParser(description="Benchmark school OpenAI-compatible models for Cypher generation.")
    p.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="Comma-separated model list.",
    )
    p.add_argument(
        "--api-base",
        default=os.getenv("VQA_API_BASE_URL", "http://218.197.140.7:3001/v1"),
        help="OpenAI-compatible base URL.",
    )
    p.add_argument(
        "--api-key-env",
        default="VQA_API_KEY",
        help="Environment variable name that stores API key.",
    )
    p.add_argument("--n-calls", type=int, default=3, help="Calls per model.")
    p.add_argument("--max-tokens", type=int, default=220, help="max_tokens for each chat completion.")
    p.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature.")
    p.add_argument("--timeout-connect", type=float, default=10.0, help="HTTP connect timeout (s).")
    p.add_argument("--timeout-read", type=float, default=60.0, help="HTTP read timeout (s).")
    p.add_argument(
        "--trust-env-proxy",
        action="store_true",
        default=default_trust_env,
        help="Respect HTTP_PROXY/HTTPS_PROXY from environment (default from VQA_TRUST_ENV_PROXY, normally false).",
    )
    p.add_argument(
        "--out",
        default="output/bench_models_school.json",
        help="Output JSON path.",
    )
    return p.parse_args()


def main():
    args = parse_args()
    models = _parse_models(args.models)
    api_key = os.getenv(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit(
            f"Missing API key env: {args.api_key_env}. "
            f"Please export it first, then rerun."
        )

    client = _build_client(
        api_base=args.api_base,
        api_key=api_key,
        timeout_connect=args.timeout_connect,
        timeout_read=args.timeout_read,
        trust_env_proxy=args.trust_env_proxy,
    )

    print("=" * 72)
    print("  School API Model Benchmark — Cypher Generation")
    print("=" * 72)
    print(f"  base_url : {args.api_base}")
    print(f"  models   : {models}")
    print(f"  n_calls  : {args.n_calls}")
    print(f"  trust_env_proxy : {args.trust_env_proxy}")

    all_results: List[Dict[str, Any]] = []
    for model in models:
        result = benchmark_model(
            client=client,
            model=model,
            n_calls=args.n_calls,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        all_results.append(result)

    valid = [
        r for r in all_results
        if r.get("n_success", 0) > 0 and not r.get("unsupported_for_chat_completions", False)
    ]
    fastest_ms = min((r["avg_ms"] for r in valid), default=None)
    best_quality = max((r["syntax_ok_rate"] for r in valid), default=None)

    print("\n" + "=" * 72)
    print("  Summary")
    print("=" * 72)
    print(f"\n  {'Model':<22} {'avg_ms':>10} {'tok/s':>10} {'syntax':>10} {'errors':>8}")
    print("  " + "-" * 72)
    for r in all_results:
        if r.get("n_success", 0) == 0:
            flag = "unsupported" if r.get("unsupported_for_chat_completions") else "failed"
            print(f"  {r['model']:<22} {'-':>10} {'-':>10} {'-':>10} {r['n_errors']:>8}  ({flag})")
            continue
        ms_tag = " ◄ fastest" if fastest_ms is not None and r["avg_ms"] == fastest_ms else ""
        q_tag = " ◄ best syntax" if best_quality is not None and r["syntax_ok_rate"] == best_quality else ""
        print(
            f"  {r['model']:<22} {r['avg_ms']:>9.1f} {r['avg_tok_per_s']:>9.1f} "
            f"{r['syntax_ok_rate']*100:>8.1f}% {r['n_errors']:>8}{ms_tag}{q_tag}"
        )

    if valid:
        fastest = min(valid, key=lambda x: x["avg_ms"])
        stable = max(valid, key=lambda x: (x["syntax_ok_rate"], -x["avg_ms"]))
        print(
            f"\n  推荐（速度优先）: {fastest['model']} "
            f"(avg {fastest['avg_ms']:.1f}ms, {fastest['avg_tok_per_s']:.1f} tok/s)"
        )
        print(
            f"  推荐（稳定优先）: {stable['model']} "
            f"(syntax {stable['syntax_ok_rate']*100:.1f}%, avg {stable['avg_ms']:.1f}ms)"
        )

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_payload = {
        "api_base": args.api_base,
        "models": models,
        "n_calls": args.n_calls,
        "trust_env_proxy": args.trust_env_proxy,
        "results": all_results,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    out_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Results saved -> {out_path}")


if __name__ == "__main__":
    main()
