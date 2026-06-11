"""OpenAI-compatible LLM client for v7 verbalization and small utilities."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List
from urllib.parse import urlparse


_FALSE = {"0", "false", "no", "off"}


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: Dict[str, Any] | None = None


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def _clean_llm_text(text: Any) -> str:
    out = str(text or "").strip()
    out = re.sub(r"^```(?:json|text)?\s*", "", out, flags=re.I).strip()
    out = re.sub(r"\s*```$", "", out).strip()
    if (out.startswith('"') and out.endswith('"')) or (out.startswith("'") and out.endswith("'")):
        out = out[1:-1].strip()
    return " ".join(out.split())


class LLMClient:
    def __init__(self, *, api_key: str, api_base: str, model: str) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model

    @classmethod
    def from_env(cls) -> "LLMClient":
        key = _env_first("LLM_API_KEY", "OPENAI_API_KEY", "VQA_API_KEY")
        if not key:
            raise RuntimeError("Missing LLM_API_KEY/OPENAI_API_KEY/VQA_API_KEY")
        base = _env_first("LLM_API_BASE", "OPENAI_BASE_URL", "VQA_API_BASE_URL", default="https://api.openai.com/v1")
        model = _env_first("LLM_MODEL", "VQA_MODEL", "VQA_MODEL_NAME", default="gpt-4o-mini")
        return cls(api_key=key, api_base=base, model=model)

    def chat(self, messages: List[Dict[str, str]], *, max_tokens: int = 256, temperature: float | None = None, **extra: Any) -> LLMResult:
        payload: Dict[str, Any] = {
            "model": extra.pop("model", self.model),
            "messages": messages,
            "temperature": float(_env_first("LLM_TEMPERATURE", default="0") if temperature is None else temperature),
            "max_tokens": max_tokens,
        }
        payload.update(extra)
        data = self._post_json("/chat/completions", payload)
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        text = msg.get("content") or msg.get("reasoning_content") or choice.get("text") or ""
        usage = data.get("usage") or {}
        return LLMResult(
            text=_clean_llm_text(text),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            raw=data,
        )

    def verbalize(self, question: str) -> LLMResult:
        prompt = (
            "Rewrite this autonomous-driving scene question in clear natural English. "
            "Preserve every object id, spatial relation, answer semantics, and constraint exactly. "
            "Return one question only, with no explanation.\n\n"
            f"Question: {question}"
        )
        result = self.chat(
            [
                {"role": "system", "content": "You improve wording while preserving logic exactly."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=int(_env_first("LLM_VERBALIZE_MAX_TOKENS", "VQA_VERBALIZE_MAX_TOKENS", default="128")),
            temperature=0,
        )
        if not result.text or result.text.lower() == "null":
            result.text = question
        return result

    def _post_json(self, suffix: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(payload)
        timeout = int(payload.pop("_timeout_seconds", None) or _env_first("LLM_TIMEOUT_SECONDS", "VQA_TIMEOUT_SECONDS", default="300"))
        retries = int(payload.pop("_retries", None) if payload.get("_retries") is not None else _env_first("LLM_RETRIES", "VQA_RETRIES", default="2"))
        enable_thinking = _env_first("LLM_ENABLE_THINKING", "VQA_ENABLE_THINKING")
        if enable_thinking and enable_thinking.strip().lower() in _FALSE:
            payload.setdefault("chat_template_kwargs", {})["enable_thinking"] = False
        url = self._url(suffix)
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw)
            except urllib.error.HTTPError as exc:
                err = exc.read().decode("utf-8", errors="replace")[:1000]
                last_error = RuntimeError(f"LLM HTTP {exc.code}: {err}")
            except json.JSONDecodeError as exc:
                last_error = RuntimeError(f"LLM returned non-JSON response: {exc}")
            except Exception as exc:
                last_error = exc
            if attempt >= retries:
                raise RuntimeError(f"LLM request failed after {attempt + 1} attempt(s): {last_error}")
            time.sleep(min(10, 2 ** attempt))
        raise RuntimeError(f"LLM request failed: {last_error}")

    def _url(self, suffix: str) -> str:
        parsed = urlparse(self.api_base + suffix)
        path = parsed.path or suffix
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return f"{parsed.scheme}://{parsed.netloc}{path}"
