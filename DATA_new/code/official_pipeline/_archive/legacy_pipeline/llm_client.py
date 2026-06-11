"""
Gap Pipeline — LLM Client
Thin wrapper around an OpenAI-compatible chat completion API.
Only used for Cypher generation — all QA answers come from Neo4j context.
"""
import logging
import os
import re
from typing import Dict
from datetime import datetime

import json as _json
import time as _time
from typing import List
from .config import (
    LLM_CONFIG, SCENE_ANALYSIS_PROMPT, GAP_CONTEXT_PROMPT,
    L2_CONTEXT_PROMPT, L2_INTERACTION_CONTEXT_PROMPT, L2B_OBJ_CONTEXT_PROMPT,
    L2_BATCH_PROMPT, L2_BATCH_HINT_PROMPT, QUESTION_GEN_PROMPT, QUESTION_GEN_BATCH_PROMPT_V16,
)

# Backward compatibility
L2A_CONTEXT_PROMPT = L2_CONTEXT_PROMPT
L2B_CONTEXT_PROMPT = L2_INTERACTION_CONTEXT_PROMPT

_logger = logging.getLogger(__name__)

# LLM HTTP 超时配置（connect 10s，read 30s）
# 超时后 run_gap_pipeline 自动退回硬编码 Cypher，保证流程不卡住
_LLM_TIMEOUT_CONNECT = float(
    LLM_CONFIG.get("timeout_connect", 10.0)  # type: ignore[arg-type]
)
_LLM_TIMEOUT_READ = float(
    LLM_CONFIG.get("timeout_read", 30.0)  # type: ignore[arg-type]
)
_LLM_TRUST_ENV_PROXY = bool(
    LLM_CONFIG.get("trust_env_proxy", False)  # type: ignore[arg-type]
)
_LLM_DISABLE_THINKING = bool(
    LLM_CONFIG.get("disable_thinking", True)  # type: ignore[arg-type]
)
_LLM_CHAT_EXTRA_KWARGS = (
    {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    if _LLM_DISABLE_THINKING
    else {}
)


class LLMClient:
    """Wraps an OpenAI-compatible API for Cypher generation."""

    def __init__(self):
        try:
            import openai
            import httpx
        except ImportError as exc:
            raise ImportError(
                "Install required packages: pip install openai httpx"
            ) from exc
        if not str(LLM_CONFIG.get("api_key", "")).strip():
            raise ValueError(
                "VQA_API_KEY is empty. Set environment variable first "
                "(for example: run set_school_api_env.ps1)."
            )

        # 设置连接超时，防止 DeepSeek-R1 思考过长把流程挂起
        _timeout = httpx.Timeout(
            connect=_LLM_TIMEOUT_CONNECT,
            read=_LLM_TIMEOUT_READ,
            write=10.0,
            pool=5.0,
        )
        http_client = (
            httpx.Client(timeout=_timeout, trust_env=_LLM_TRUST_ENV_PROXY)  # verify_ssl=True 时不禁用 SSL
            if LLM_CONFIG["verify_ssl"]
            else httpx.Client(verify=False, timeout=_timeout, trust_env=_LLM_TRUST_ENV_PROXY)  # noqa: S501
        )
        self._client = openai.OpenAI(
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["api_base"],
            http_client=http_client,
            timeout=_LLM_TIMEOUT_READ,   # openai 客户端级超时保险
            max_retries=0,               # 禁止重试，超时直接退回硬编码 Cypher
        )
        self._model_audit = str(LLM_CONFIG.get("model_audit") or LLM_CONFIG.get("model") or "")
        self._model_render = str(LLM_CONFIG.get("model_render") or self._model_audit)
        # 向后兼容：历史代码读取 self._model 时默认走审计模型
        self._model = self._model_audit
        self._temperature = LLM_CONFIG["temperature"]
        self._max_tokens = LLM_CONFIG["max_tokens"]
        # 最近一次调用的 token 用量（用于 RQ1 成本分析）
        self.last_token_usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        # V6 埋点：每次 _call() 的精细耐时分段
        self.last_call_timing: dict = {"total_ms": 0.0, "prompt_tokens_per_ms": 0.0}
        # V18 物理时刻死锁（必须由真实 datetime.now() 捕获）
        self.last_physical_ts_start: str = ""
        self.last_physical_ts_llm: str = ""
        self.last_call_meta: dict = {}
        _logger.info(
            "LLMClient 初始化  model_audit=%s  model_render=%s  timeout(connect/read)=%.0f/%.0fs",
            self._model_audit, self._model_render, _LLM_TIMEOUT_CONNECT, _LLM_TIMEOUT_READ,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ts_now() -> str:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

    def _choose_model(self, call_tag: str) -> str:
        """V23: route model by call purpose."""
        render_tags = {"question_nlp", "question_nlp_strict", "question_batch"}
        return self._model_render if call_tag in render_tags else self._model_audit

    def _call(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        call_tag: str = "generic",
    ) -> str:
        """Send a single-turn prompt and return the response text.
        V6: Records wall-clock time in self.last_call_timing for RTT diagnosis.
        """
        _sys = system_prompt or (
            "You are a Neo4j Cypher expert for autonomous driving scene graphs. "
            "Return only valid Cypher queries."
        )
        _temp = self._temperature if temperature is None else temperature
        # max_tokens <= 0: do not send max_tokens (uncapped by client-side hard limit)
        if max_tokens is not None and max_tokens <= 0:
            _max_tok = None
        else:
            _max_tok = self._max_tokens if max_tokens is None else max_tokens
        _model_used = self._choose_model(call_tag)
        # V18 [物理采样点-LLM start]
        self.last_physical_ts_start = self._ts_now()
        _t0 = _time.perf_counter()
        _req = {
            "model": _model_used,
            "messages": [
                {
                    "role": "system",
                    "content": _sys,
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": _temp,
            "stream": False,
            **_LLM_CHAT_EXTRA_KWARGS,
        }
        if _max_tok is not None:
            _req["max_tokens"] = _max_tok
        resp = self._client.chat.completions.create(**_req)
        # V18 [物理采样点-timestamp_llm]：必须紧贴 API 返回之后
        self.last_physical_ts_llm = self._ts_now()
        # 记录 token 用量（部分接口可能无 usage 字段，安全取得）
        try:
            u = resp.usage
            if u:
                self.last_token_usage = {
                    "prompt_tokens":     getattr(u, "prompt_tokens",     0) or 0,
                    "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                    "total_tokens":      getattr(u, "total_tokens",      0) or 0,
                }
                # INFO 级别输出，方便用户验证它们是真实 API 返回的（非硬编码）
                _logger.info(
                    "LLM token usage — prompt: %d  completion: %d  total: %d  (model=%s)",
                    self.last_token_usage["prompt_tokens"],
                    self.last_token_usage["completion_tokens"],
                    self.last_token_usage["total_tokens"],
                    _model_used,
                )
        except Exception:
            pass
        _t1 = _time.perf_counter()
        _total_ms = (_t1 - _t0) * 1000
        _comp = self.last_token_usage.get("completion_tokens", 1) or 1
        self.last_call_timing = {
            "total_ms": round(_total_ms, 1),
            # 生成速度： completion tokens / 秒
            "tok_per_sec": round(_comp / (_total_ms / 1000), 1),
            # 估算：络络下行 = prompt 对应 TTFT， 剩余 = 生成时间
            "est_rtt_overhead_ms": round(max(0.0, _total_ms - _comp * 20), 1),
        }
        _logger.debug(
            "LLM call timing: total=%.0fms  tok/s=%.0f  est_rtt=%.0fms",
            self.last_call_timing["total_ms"],
            self.last_call_timing["tok_per_sec"],
            self.last_call_timing["est_rtt_overhead_ms"],
        )
        self.last_call_meta = {
            "call_tag": call_tag,
            "model_used": _model_used,
            "timestamp_start": self.last_physical_ts_start,
            "timestamp_llm": self.last_physical_ts_llm,
            "timing": dict(self.last_call_timing),
            "usage": dict(self.last_token_usage),
        }
        return resp.choices[0].message.content.strip()

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove markdown code fences and deepseek-r1 <think> tags."""
        # Remove markdown fences first
        m = re.search(
            r"```(?:cypher|sql)?\s*\n(.*?)```",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if m:
            text = m.group(1).strip()

        # Remove closed <think> blocks first
        text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL | re.IGNORECASE)

        # If there is still an unclosed <think>, cut from first Cypher keyword
        if "<think>" in text:
            k = re.search(r"(?is)\b(MATCH|OPTIONAL|WITH|UNWIND|CALL|CREATE|MERGE)\b", text)
            if k:
                text = text[k.start():]

        # Generic: cut from first Cypher keyword if prose precedes it
        k = re.search(r"(?is)\b(MATCH|OPTIONAL|WITH|UNWIND|CALL|CREATE|MERGE)\b", text)
        if k:
            text = text[k.start():]

        # Trim trailing prose by stopping at LIMIT n / first semicolon when possible
        m_limit = re.search(r"(?is)(.*?\bLIMIT\s+\d+\b\s*;?)", text)
        if m_limit:
            text = m_limit.group(1)
        else:
            m_semi = re.search(r"(?is)(.*?;)", text)
            if m_semi:
                text = m_semi.group(1)

        return text.strip()

    @staticmethod
    def _looks_like_cypher(text: str) -> bool:
        """Sanity check for generated Cypher, including truncation guards."""
        if not text:
            return False
        s = text.strip()
        if "<think>" in s.lower():
            return False
        if not re.match(r"(?is)^(MATCH|OPTIONAL|WITH|UNWIND|CALL|CREATE|MERGE)\b", s):
            return False
        if "RETURN" not in s.upper():
            return False
        # Truncation guards: bracket/brace/paren balance
        if s.count("(") != s.count(")"):
            return False
        if s.count("[") != s.count("]"):
            return False
        if s.count("{") != s.count("}"):
            return False
        # Truncation guards: string quote balance
        if s.count("'") % 2 != 0:
            return False
        # RETURN must have non-trivial body
        m = re.search(r"(?is)\bRETURN\b\s+(.+)", s)
        if not m or len(m.group(1).strip()) < 5:
            return False
        # Tail token should not look like a cut-off fragment
        tail = s.rstrip().rstrip(";").rstrip()
        last_word = re.split(r"[\s,(){}\[\]]+", tail)[-1] if tail else ""
        lw = (last_word or "").strip().lower()
        if lw and "." in lw:
            return False
        if lw in {"co", "coales", "coalesc", "toflo", "tofloa"}:
            return False
        return True

    @staticmethod
    def _extract_return_aliases(cypher: str) -> set[str]:
        """Best-effort extraction of RETURN aliases from Cypher text."""
        aliases = set()
        for m in re.finditer(r"(?is)\bAS\s+([A-Za-z_][A-Za-z0-9_]*)", cypher):
            aliases.add(m.group(1).strip().lower())
        return aliases

    @classmethod
    def _looks_like_l2_context_schema(cls, cypher: str) -> bool:
        """Require key aliases used by downstream L2 pipeline logic."""
        need = {
            "n2_id", "n3_id", "n2_type", "n3_type",
            "r2_dir8", "r2_dist", "r2_actual_dist",
            "sibling_ids", "sibling_types", "sibling_statuses",
            "sibling_dir8s", "sibling_dists",
        }
        got = cls._extract_return_aliases(cypher)
        if not need.issubset(got):
            return False
        return cls._passes_with_scope_guard(cypher)

    @staticmethod
    def _passes_with_scope_guard(cypher: str) -> bool:
        """
        Guard common invalid Cypher from LLM:
        RETURN references r1/r2/... but last WITH clause forgot to carry variables.
        """
        m_ret = re.search(r"(?is)\bRETURN\b", cypher)
        if not m_ret:
            return True
        ret_body = cypher[m_ret.end():]
        refs = {
            v.strip()
            for v in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.", ret_body)
            if v and v.strip()
        }
        if not refs:
            return True
        # list comprehension variable, e.g. [s IN siblings | s.id]
        for v in list(refs):
            if re.search(rf"\[\s*{re.escape(v)}\s+IN\b", ret_body, re.IGNORECASE):
                refs.discard(v)
        if not refs:
            return True
        prefix = cypher[:m_ret.start()]
        with_hits = list(re.finditer(r"(?is)\bWITH\b", prefix))
        if not with_hits:
            return True
        last_with = prefix[with_hits[-1].start():]
        for v in refs:
            if not re.search(rf"(?<![A-Za-z0-9_]){re.escape(v)}(?![A-Za-z0-9_])", last_with):
                return False
        return True

    @staticmethod
    def _inject_keep_vars_into_last_with(cypher: str, vars_needed: List[str]) -> str:
        if not cypher or not vars_needed:
            return cypher
        m_ret = re.search(r"(?is)\bRETURN\b", cypher)
        if not m_ret:
            return cypher
        prefix = cypher[:m_ret.start()]
        with_hits = list(re.finditer(r"(?is)\bWITH\b", prefix))
        if not with_hits:
            return cypher
        _with_start = with_hits[-1].start()
        after_with = cypher[_with_start + 4 :]
        m_next_clause = re.search(
            r"(?is)\n\s*(MATCH|OPTIONAL MATCH|RETURN|UNWIND|CALL|WITH)\b",
            after_with,
        )
        if m_next_clause:
            _list_end = _with_start + 4 + m_next_clause.start()
        else:
            _list_end = m_ret.start()
        with_list = cypher[_with_start + 4 : _list_end]
        with_list_new = with_list
        for v in vars_needed:
            if not re.search(rf"(?<![A-Za-z0-9_]){re.escape(v)}(?![A-Za-z0-9_])", with_list_new):
                with_list_new = with_list_new.rstrip() + f", {v}"
        if with_list_new == with_list:
            return cypher
        return cypher[: _with_start + 4] + with_list_new + cypher[_list_end :]

    @classmethod
    def _repair_l2_scope(cls, cypher: str) -> str:
        if not cypher:
            return cypher
        fixed = cypher
        # 常见错误：最后一个 WITH 丢了 r1/r2，导致 RETURN 作用域报错
        fixed = cls._inject_keep_vars_into_last_with(fixed, ["r1", "r2"])
        return fixed

    @staticmethod
    def _cypher_quote(v: object) -> str:
        return str(v or "").replace("\\", "\\\\").replace("'", "\\'")

    @staticmethod
    def _default_ctx_hint() -> Dict:
        return {
            "sibling_dir8": "any",
            "sibling_type": "any",
            "sibling_status": "any",
            "sibling_dist": "any",
            "focus": "conservative",
            "require_status_nonempty": False,
        }

    @classmethod
    def _sanitize_ctx_hint(cls, raw: object) -> Dict:
        out = cls._default_ctx_hint()
        if not isinstance(raw, dict):
            return out
        _dirs = {
            "any",
            "front",
            "front-left",
            "front-right",
            "back-left",
            "back-right",
            "back",
        }
        _statuses = {
            "any",
            "moving",
            "stopped",
            "parked",
            "standing",
            "with_rider",
            "without_rider",
        }
        _dists = {"any", "near", "mid", "far"}
        _focus = {"conservative", "balanced", "aggressive"}
        d8 = str(raw.get("sibling_dir8") or "").strip().lower()
        if d8 in _dirs:
            out["sibling_dir8"] = d8
        st = str(raw.get("sibling_type") or "").strip().lower()
        if st in ("any", "n3_type"):
            out["sibling_type"] = st
        st_status = str(raw.get("sibling_status") or "").strip().lower()
        if st_status in _statuses:
            out["sibling_status"] = st_status
        st_dist = str(raw.get("sibling_dist") or "").strip().lower()
        if st_dist in _dists:
            out["sibling_dist"] = st_dist
        st_focus = str(raw.get("focus") or "").strip().lower()
        if st_focus in _focus:
            out["focus"] = st_focus
        rs = raw.get("require_status_nonempty")
        if isinstance(rs, bool):
            out["require_status_nonempty"] = rs
        else:
            rs_s = str(rs or "").strip().lower()
            if rs_s in ("1", "true", "yes", "on"):
                out["require_status_nonempty"] = True
            elif rs_s in ("0", "false", "no", "off"):
                out["require_status_nonempty"] = False
        return out

    @classmethod
    def _parse_hint_batch_response(cls, raw: str, n: int) -> List[Dict]:
        text = str(raw or "").strip()
        text = re.sub(r"```[a-zA-Z]*\n?", "", text).rstrip("`").strip()
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            text = m.group(0)
        try:
            arr = _json.loads(text)
            if not isinstance(arr, list):
                raise ValueError("not-list")
            out = []
            for i in range(n):
                item = arr[i] if i < len(arr) else {}
                out.append(cls._sanitize_ctx_hint(item))
            return out
        except Exception:
            return [cls._default_ctx_hint() for _ in range(n)]

    def _generate_context_hints_batch(self, cells: List[Dict], topology: str) -> List[Dict]:
        n = len(cells)
        if n == 0:
            return []
        payload = [
            [
                topology,
                c.get("n1_id", ""),
                c.get("n2_id", ""),
                c.get("n3_id", ""),
                c.get("r1_dir8", ""),
                c.get("r2_dir8", ""),
                c.get("n2_type", ""),
                c.get("n3_type", ""),
            ]
            for c in cells
        ]
        prompt = L2_BATCH_HINT_PROMPT.format(
            n=n,
            gaps_json=_json.dumps(payload, ensure_ascii=False),
        )
        try:
            _hint_tok_env = int(str(os.getenv("VQA_CTX_HINT_MAX_TOKENS", "") or "0").strip() or "0")
        except Exception:
            _hint_tok_env = 0
        _hint_max_tokens = _hint_tok_env if _hint_tok_env > 0 else min(640, max(128, 36 * n))
        try:
            raw = self._call(
                prompt,
                temperature=0.0,
                max_tokens=_hint_max_tokens,
                call_tag="l2_batch_hint",
            )
        except Exception as exc:
            _logger.info("context hint batch failed (%s), using conservative defaults", exc)
            return [self._default_ctx_hint() for _ in range(n)]
        hints = self._parse_hint_batch_response(raw, n)
        _n_dir8 = sum(1 for h in hints if str(h.get("sibling_dir8", "any")) != "any")
        _n_type = sum(1 for h in hints if str(h.get("sibling_type", "any")) != "any")
        _n_status = sum(1 for h in hints if str(h.get("sibling_status", "any")) != "any")
        _n_dist = sum(1 for h in hints if str(h.get("sibling_dist", "any")) != "any")
        _n_aggr = sum(1 for h in hints if str(h.get("focus", "")) == "aggressive")
        _n_bal = sum(1 for h in hints if str(h.get("focus", "")) == "balanced")
        _logger.info(
            "context hints topo=%s n=%d tighten(dir8=%d type=%d status=%d dist=%d) focus(aggr=%d balanced=%d)",
            topology,
            n,
            _n_dir8,
            _n_type,
            _n_status,
            _n_dist,
            _n_aggr,
            _n_bal,
        )
        return hints

    def _build_l2_hybrid_cypher(self, cell: Dict, hint: Dict) -> str:
        """Unified L2 hybrid cypher (alias for _build_l2a_hybrid_cypher)."""
        return self._build_l2a_hybrid_cypher(cell, hint)

    def _build_l2a_hybrid_cypher(self, cell: Dict, hint: Dict) -> str:
        h = self._sanitize_ctx_hint(hint)
        n1 = self._cypher_quote(cell.get("n1_id", "ego"))
        n2 = self._cypher_quote(cell.get("n2_id", ""))
        n3 = self._cypher_quote(cell.get("n3_id", ""))
        n3_type = self._cypher_quote(cell.get("n3_type", ""))
        where_parts = [
            f"sibling.unique_id <> '{n1}'",
            f"sibling.unique_id <> '{n3}'",
        ]
        if h.get("sibling_dir8") and h["sibling_dir8"] != "any":
            where_parts.append(
                f"coalesce(r3.direction_8,'') = '{self._cypher_quote(h['sibling_dir8'])}'"
            )
        if h.get("sibling_type") == "n3_type" and n3_type:
            where_parts.append(f"coalesce(sibling.type,'') = '{n3_type}'")
        if h.get("sibling_status") and h["sibling_status"] != "any":
            where_parts.append(
                f"coalesce(sibling.status,'') = '{self._cypher_quote(h['sibling_status'])}'"
            )
        if h.get("sibling_dist") and h["sibling_dist"] != "any":
            where_parts.append(
                f"coalesce(r3.predicates[1],'') = '{self._cypher_quote(h['sibling_dist'])}'"
            )
        if h.get("focus") == "aggressive" and (
            h.get("sibling_dir8") in ("", "any")
        ):
            where_parts.append("coalesce(r3.direction_8,'') = coalesce(r2.direction_8,'')")
        if h.get("require_status_nonempty"):
            where_parts.append("coalesce(sibling.status,'') <> ''")
        where_clause = " AND ".join(where_parts)
        return f"""
MATCH (ego:Object {{unique_id: '{n1}'}})-[r1:RELATES_TO]-(a:Object {{unique_id: '{n2}'}})
      -[r2:RELATES_TO]-(b:Object {{unique_id: '{n3}'}})
OPTIONAL MATCH (a)-[r3:RELATES_TO]-(sibling:Object)
  WHERE {where_clause}
WITH a, b, r1, r2,
     collect({{id:sibling.unique_id, type:sibling.type,
               status:coalesce(sibling.status,''),
               dir8:r3.direction_8, dist:r3.distance}}) AS siblings
RETURN
  '{n1}'                               AS n1_id,
  a.unique_id                          AS n2_id,
  a.type                               AS n2_type,
  coalesce(a.status,'')                AS n2_status,
  b.unique_id                          AS n3_id,
  b.type                               AS n3_type,
  coalesce(b.status,'')                AS n3_status,
  r1.direction_4                       AS r1_dir4,
  r1.direction_8                       AS r1_dir8,
  coalesce(r1.predicates[1],'')        AS r1_dist,
  r1.distance                          AS r1_actual_dist,
  r2.direction_4                       AS r2_dir4,
  r2.direction_8                       AS r2_dir8,
  coalesce(r2.predicates[1],'')        AS r2_dist,
  r2.distance                          AS r2_actual_dist,
  [s IN siblings | s.id]               AS sibling_ids,
  [s IN siblings | s.type]             AS sibling_types,
  [s IN siblings | s.status]           AS sibling_statuses,
  [s IN siblings | s.dir8]             AS sibling_dir8s,
  [s IN siblings | s.dist]             AS sibling_dists
LIMIT 1
""".strip()

    def _build_l2b_hybrid_cypher(self, cell: Dict, hint: Dict) -> str:
        h = self._sanitize_ctx_hint(hint)
        n1 = self._cypher_quote(cell.get("n1_id", ""))
        n2 = self._cypher_quote(cell.get("n2_id", ""))
        n3 = self._cypher_quote(cell.get("n3_id", ""))
        n3_type = self._cypher_quote(cell.get("n3_type", ""))
        where_parts = [
            f"sibling.unique_id <> '{n1}'",
            f"sibling.unique_id <> '{n3}'",
        ]
        if h.get("sibling_dir8") and h["sibling_dir8"] != "any":
            where_parts.append(
                f"coalesce(r3.direction_8,'') = '{self._cypher_quote(h['sibling_dir8'])}'"
            )
        if h.get("sibling_type") == "n3_type" and n3_type:
            where_parts.append(f"coalesce(sibling.type,'') = '{n3_type}'")
        if h.get("sibling_status") and h["sibling_status"] != "any":
            where_parts.append(
                f"coalesce(sibling.status,'') = '{self._cypher_quote(h['sibling_status'])}'"
            )
        if h.get("sibling_dist") and h["sibling_dist"] != "any":
            where_parts.append(
                f"coalesce(r3.predicates[1],'') = '{self._cypher_quote(h['sibling_dist'])}'"
            )
        if h.get("focus") == "aggressive" and (
            h.get("sibling_dir8") in ("", "any")
        ):
            where_parts.append("coalesce(r3.direction_8,'') = coalesce(r2.direction_8,'')")
        if h.get("require_status_nonempty"):
            where_parts.append("coalesce(sibling.status,'') <> ''")
        where_clause = " AND ".join(where_parts)
        return f"""
MATCH (a:Object {{unique_id: '{n1}'}})-[r1:RELATES_TO]-(b:Object {{unique_id: '{n2}'}})
      -[r2:RELATES_TO]-(c:Object {{unique_id: '{n3}'}})
OPTIONAL MATCH (b)-[r3:RELATES_TO]-(sibling:Object)
  WHERE {where_clause}
WITH a, b, c, r1, r2,
     collect({{id:sibling.unique_id, type:sibling.type,
               status:coalesce(sibling.status,''),
               dir8:r3.direction_8, dist:r3.distance}}) AS siblings
RETURN
  a.unique_id                          AS n1_id,
  a.type                               AS n1_type,
  coalesce(a.status,'')                AS n1_status,
  b.unique_id                          AS n2_id,
  b.type                               AS n2_type,
  coalesce(b.status,'')                AS n2_status,
  c.unique_id                          AS n3_id,
  c.type                               AS n3_type,
  coalesce(c.status,'')                AS n3_status,
  r1.direction_4                       AS r1_dir4,
  r1.direction_8                       AS r1_dir8,
  coalesce(r1.predicates[1],'')        AS r1_dist,
  r1.distance                          AS r1_actual_dist,
  r2.direction_4                       AS r2_dir4,
  r2.direction_8                       AS r2_dir8,
  coalesce(r2.predicates[1],'')        AS r2_dist,
  r2.distance                          AS r2_actual_dist,
  [s IN siblings | s.id]               AS sibling_ids,
  [s IN siblings | s.type]             AS sibling_types,
  [s IN siblings | s.status]           AS sibling_statuses,
  [s IN siblings | s.dir8]             AS sibling_dir8s,
  [s IN siblings | s.dist]             AS sibling_dists
LIMIT 1
""".strip()

    @staticmethod
    def _scene_fallback_cypher() -> str:
        """Deterministic scene-edge query fallback."""
        return (
            "MATCH (src)-[r]->(tgt)\n"
            "RETURN\n"
            "  src.unique_id AS src_id,\n"
            "  src.type AS src_type,\n"
            "  src.status AS src_status,\n"
            "  tgt.unique_id AS tgt_id,\n"
            "  tgt.type AS tgt_type,\n"
            "  tgt.status AS tgt_status,\n"
            "  r.dir4 AS dir4,\n"
            "  r.dir8 AS dir8,\n"
            "  r.dist_level AS dist_level"
        )

    @staticmethod
    def _gap_context_fallback_cypher(src_id: str, tgt_id: str) -> str:
        """Deterministic per-gap context query fallback."""
        return (
            f"MATCH (src {{unique_id: '{src_id}'}})-[e]->(tgt {{unique_id: '{tgt_id}'}})\n"
            "OPTIONAL MATCH (anc)-[]->(src)\n"
            "WHERE anc.unique_id <> tgt.unique_id\n"
            "OPTIONAL MATCH (tgt)-[]->(beyond)\n"
            "WHERE beyond.unique_id <> src.unique_id\n"
            "RETURN\n"
            "  src.unique_id AS src_id,\n"
            "  src.type AS src_type,\n"
            "  src.status AS src_status,\n"
            "  tgt.unique_id AS tgt_id,\n"
            "  tgt.type AS tgt_type,\n"
            "  tgt.status AS tgt_status,\n"
            "  e.dir4 AS dir4,\n"
            "  e.dir8 AS dir8,\n"
            "  e.dist_level AS dist_level,\n"
            "  anc.unique_id AS anc_id,\n"
            "  anc.type AS anc_type,\n"
            "  beyond.unique_id AS beyond_id,\n"
            "  beyond.type AS beyond_type\n"
            "LIMIT 1"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Hardcoded Cypher templates (no LLM, reliable)
    # ------------------------------------------------------------------

    @staticmethod
    def build_scene_analysis_cypher() -> str:
        """Hardcoded scene analysis Cypher using the real DB property names."""
        return """
MATCH (src:Object)-[r:RELATES_TO]->(tgt:Object)
RETURN
  src.unique_id                    AS src_id,
  src.type                         AS src_type,
  coalesce(src.status, '')         AS src_status,
  tgt.unique_id                    AS tgt_id,
  tgt.type                         AS tgt_type,
  coalesce(tgt.status, '')         AS tgt_status,
  r.direction_4                    AS dir4,
  r.direction_8                    AS dir8,
  coalesce(r.predicates[1], '')    AS dist_level
""".strip()

    @staticmethod
    def build_gap_context_cypher(src_id: str, tgt_id: str) -> str:
        """Hardcoded gap context Cypher for a specific edge.

        beyond 只取与 src→tgt 同方向（direction_8）的邻居，避免随机选取；
        同时返回 actual_dist（实际米数）用于距离序约束。
        """
        return f"""
MATCH (src:Object {{unique_id: '{src_id}'}})-[e:RELATES_TO]->(tgt:Object {{unique_id: '{tgt_id}'}})
OPTIONAL MATCH (anc:Object)-[:RELATES_TO]->(src)
  WHERE anc.unique_id <> tgt.unique_id
WITH src, tgt, e, collect(anc)[0] AS anc
OPTIONAL MATCH (tgt)-[r2:RELATES_TO]->(beyond:Object)
  WHERE beyond.unique_id <> src.unique_id
    AND r2.direction_8 = e.direction_8
WITH src, tgt, e, anc, collect(beyond)[0] AS beyond
OPTIONAL MATCH (:Object {{unique_id: 'ego'}})-[ego_r:RELATES_TO]->(tgt)
RETURN
  src.unique_id                    AS src_id,
  src.type                         AS src_type,
  coalesce(src.status, '')         AS src_status,
  tgt.unique_id                    AS tgt_id,
  tgt.type                         AS tgt_type,
  coalesce(tgt.status, '')         AS tgt_status,
  e.direction_4                    AS dir4,
  e.direction_8                    AS dir8,
  coalesce(e.predicates[1], '')    AS dist_level,
  e.distance                       AS actual_dist,
  coalesce(ego_r.direction_8, '')  AS ego_dir8,
  anc.unique_id                    AS anc_id,
  anc.type                         AS anc_type,
  beyond.unique_id                 AS beyond_id,
  beyond.type                      AS beyond_type
LIMIT 1
""".strip()

    # ------------------------------------------------------------------
    # LLM-based generation (kept for reference / future use)
    # ------------------------------------------------------------------

    def generate_scene_analysis_cypher(self) -> str:
        """
        Ask the LLM to write a Cypher that enumerates all edges in the scene
        graph and returns one row per edge with these columns:
            src_id, src_type, src_status,
            tgt_id, tgt_type, tgt_status,
            dir4, dir8, dist_level
        """
        raw = self._call(
            SCENE_ANALYSIS_PROMPT,
            temperature=0.0,
            max_tokens=800,
            call_tag="scene_analysis_cypher",
        )
        return self._strip_fences(raw)
        if not self._looks_like_cypher(cypher):
            return self._scene_fallback_cypher()
        return cypher

    def generate_gap_context_cypher(self, gap_cell: Dict) -> str:
        """
        Ask the LLM to write a Cypher that pulls full context for one gap edge.

        Args:
            gap_cell: dict containing at least:
                src_id  — unique_id of the source node
                tgt_id  — unique_id of the target node
                dir8    — 8-direction label of the edge

        Returns:
            Cypher string (LIMIT 1, includes OPTIONAL MATCH for anc/beyond).
        """
        import logging
        logger = logging.getLogger(__name__)
        
        src_id = gap_cell.get("src_id", "")
        tgt_id = gap_cell.get("tgt_id", "")
        dir8 = gap_cell.get("dir8", "")

        prompt = GAP_CONTEXT_PROMPT.format(
            src_id=src_id,
            tgt_id=tgt_id,
            dir8=dir8,
        )
        raw = self._call(
            prompt,
            temperature=0.0,
            max_tokens=800,
            call_tag="gap_context_cypher",
        )
        logger.debug("LLM raw output (first 200 chars): %s", raw[:200])
        cleaned = self._strip_fences(raw)
        logger.debug("After _strip_fences (first 200 chars): %s", cleaned[:200])
        if not self._looks_like_cypher(cleaned):
            return self._gap_context_fallback_cypher(src_id, tgt_id)
        return cleaned

    # ------------------------------------------------------------------
    # V4: L2 路径缺口上下文 Cypher (统一L2，不再区分L2A/L2B)
    # ------------------------------------------------------------------

    def generate_l2_context_cypher(self, cell: Dict) -> str:
        """生成 L2 路径缺口的上下文 Cypher（A→B→C，含干扰项兄弟节点）。"""
        try:
            prompt = L2_CONTEXT_PROMPT.format(**cell)
        except KeyError:
            return self.build_l2_fallback_cypher(cell)
        raw     = self._call(
            prompt,
            temperature=0.0,
            max_tokens=800,
            call_tag="l2_context",
        )
        cleaned = self._strip_fences(raw)
        _logger.debug("L2 LLM raw (200): %s", raw[:200])
        if not self._looks_like_cypher(cleaned):
            _logger.info("「L2 LLM Cypher 不合规」，退回硬编码")
            return self.build_l2_fallback_cypher(cell)
        return cleaned

    # Backward compatibility aliases
    def generate_l2a_context_cypher(self, cell: Dict) -> str:
        """生成 L2A 路径缺口的上下文 Cypher（向后兼容，实际调用统一的L2方法）。"""
        return self.generate_l2_context_cypher(cell)

    def generate_l2b_context_cypher(self, cell: Dict) -> str:
        """生成 L2B 路径缺口的上下文 Cypher（X←ego→Y，含对比信息）。"""
        try:
            prompt = L2_INTERACTION_CONTEXT_PROMPT.format(**cell)
        except KeyError:
            return self.build_l2b_fallback_cypher(cell)
        raw     = self._call(
            prompt,
            temperature=0.0,
            max_tokens=800,
            call_tag="l2b_context",
        )
        cleaned = self._strip_fences(raw)
        _logger.debug("L2B LLM raw (200): %s", raw[:200])
        if not self._looks_like_cypher(cleaned):
            _logger.info("「L2B LLM Cypher 不合规」，退回硬编码")
            return self.build_l2b_fallback_cypher(cell)
        return cleaned

    # ------------------------------------------------------------------
    # V16: 批量问题生成 + RTT诊断
    # ------------------------------------------------------------------

    def generate_questions_batch(
        self,
        inputs: List[Dict],   # 每项包含: q_type,n1_label,n2_id,n2_type,n3_id,n3_type,n3_status,r1_dir,r2_dir,answer,fallback
        n_workers: int = 1,   # 并行工作线程数（默认不并行）
    ) -> List[str]:
        """
        V16: 一次 LLM 调用生成 N 个问题，压缩 N-1 个 RTT。
        返回问题字符串列表（与 inputs 等长）。
        单项解析失败就地降级到 fallback。

        V17 改进：自动分块防止超时（每批最多 MAX_SAFE_BATCH_SIZE 条）
        """
        if not inputs:
            return []

        # V17: 二级分块保护，防止单次请求过大导致超时
        MAX_SAFE_BATCH_SIZE = int(os.getenv("VQA_Q_MAX_SAFE_BATCH_SIZE", "16"))

        if len(inputs) <= MAX_SAFE_BATCH_SIZE:
            # 单批处理（原逻辑）
            return self._generate_questions_batch_single(inputs)

        # 多批处理：自动分块
        _logger.info(
            "V17 auto-chunking: %d questions -> %d chunks (max_size=%d)",
            len(inputs),
            (len(inputs) + MAX_SAFE_BATCH_SIZE - 1) // MAX_SAFE_BATCH_SIZE,
            MAX_SAFE_BATCH_SIZE
        )
        results = []
        for i in range(0, len(inputs), MAX_SAFE_BATCH_SIZE):
            chunk = inputs[i:i+MAX_SAFE_BATCH_SIZE]
            chunk_results = self._generate_questions_batch_single(chunk)
            results.extend(chunk_results)
        return results

    def _generate_questions_batch_single(self, inputs: List[Dict]) -> List[str]:
        """V16 单批次问题生成（内部方法）"""
        if not inputs:
            return []
        n = len(inputs)

        # 构建精简输入数组 [q_type, n1_label, n2_type, r1_dir, n3_type, r2_dir, answer]
        arr = []
        for inp in inputs:
            n1 = inp.get("n1_id","ego")
            n1_type = inp.get("n1_type","ego")
            n1_label = "ego" if n1 == "ego" else (
                n1 if n1.lower().startswith(n1_type.lower()) else f"{n1_type} {n1}"
            )
            arr.append([
                inp.get("q_type", "object"),
                n1_label,
                inp.get("n2_type", ""),
                inp.get("r1_dir", "front"),
                inp.get("n3_type", ""),
                inp.get("r2_dir", "front"),
                str(inp.get("answer", "")),
            ])

        prompt = QUESTION_GEN_BATCH_PROMPT_V16.format(
            n=n,
            inputs_json=_json.dumps(arr, ensure_ascii=False),
        )

        # 记录调用前时间以测量 RTT
        _t0 = _time.perf_counter()
        try:
            _model_used = self._choose_model("question_batch")
            resp = self._client.chat.completions.create(
                model=_model_used,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You write VQA questions for autonomous driving. "
                            "Return ONLY a JSON array of question strings."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                stream=False,
                **_LLM_CHAT_EXTRA_KWARGS,
            )
            _t1 = _time.perf_counter()
            total_ms = (_t1 - _t0) * 1000

            # RTT诊断计算
            try:
                u = resp.usage
                comp_tok = getattr(u, "completion_tokens", 0) or n * 15
                self.last_token_usage = {
                    "prompt_tokens":     getattr(u, "prompt_tokens", 0) or 0,
                    "completion_tokens": comp_tok,
                    "total_tokens":      getattr(u, "total_tokens", 0) or 0,
                }
                tok_per_sec = comp_tok / max(total_ms / 1000, 0.001)
                est_gen_ms  = comp_tok * 1000 / max(tok_per_sec, 1)
                est_rtt_ms  = max(0.0, total_ms - est_gen_ms)
                rtt_pct     = est_rtt_ms / max(total_ms, 1) * 100
                _logger.info(
                    "V16 batch(%d) total=%.0fms  tok/s=%.0f  "
                    "est_gen=%.0fms  est_RTT=%.0fms (%.0f%%)  prompt=%d comp=%d",
                    n, total_ms, tok_per_sec, est_gen_ms, est_rtt_ms, rtt_pct,
                    self.last_token_usage["prompt_tokens"],
                    self.last_token_usage["completion_tokens"],
                )
                self.last_call_timing = {
                    "total_ms": round(total_ms, 1),
                    "tok_per_sec": round(tok_per_sec, 1),
                    "est_rtt_overhead_ms": round(est_rtt_ms, 1),
                    "est_rtt_pct": round(rtt_pct, 1),
                }
            except Exception:
                pass

            # 解析 JSON 数组
            raw = resp.choices[0].message.content.strip()
            text = re.sub(r"```[a-zA-Z]*\n?", "", raw).rstrip("`").strip()
            m = re.search(r"\[.*\]", text, re.DOTALL)
            if m:
                text = m.group(0)
            try:
                parsed = _json.loads(text)
                if isinstance(parsed, list) and len(parsed) == n:
                    # 清洁每个项
                    cleaned = []
                    for i, s in enumerate(parsed):
                        s = str(s).strip().strip('"').strip("'").split("\n")[0].strip()
                        cleaned.append(s if len(s) > 5 else inputs[i].get("fallback", ""))
                    return cleaned
                elif isinstance(parsed, list):
                    # 长度不匹配，将已有的补全、多余的截断
                    result = []
                    for i in range(n):
                        if i < len(parsed):
                            s = str(parsed[i]).strip().strip('"').strip("'")
                            result.append(s if len(s) > 5 else inputs[i].get("fallback", ""))
                        else:
                            result.append(inputs[i].get("fallback", ""))
                    return result
            except Exception as parse_err:
                _logger.warning("V16 batch parse failed (%s), using fallbacks", parse_err)
        except Exception as call_err:
            _logger.warning("V16 batch call failed (%s), using fallbacks", call_err)

        # 全部降级到 fallback
        return [inp.get("fallback", "") for inp in inputs]

    # ------------------------------------------------------------------
    # V15: 自然语言问题生成（真实 LLM 调用，不走模板）
    # ------------------------------------------------------------------

    def generate_question_nlp(
        self,
        path:            str,
        q_type:          str,
        n1_id:           str,
        n1_type:         str,
        n2_id:           str,
        n2_type:         str,
        n3_id:           str,
        n3_type:         str,
        n3_status:       str,
        r1_dir:          str,
        r2_dir:          str,
        constraint_desc: str,
        answer:          str,
        fallback:        str = "",
    ) -> str:
        """
        V15: 调用 LLM 生成一条自然语言问题。
        使用独立的 VQA 小向导 prompt（非 Cypher专家）。
        失败时返回 fallback。
        """
        # A 的标签
        n1_label = "ego" if n1_id == "ego" else (
            n1_id if n1_id.lower().startswith(n1_type.lower()) else f"{n1_type} {n1_id}"
        )
        n2_label = n2_id if n2_id.lower().startswith(n2_type.lower()) else f"{n2_type} {n2_id}"

        qtype_rule = {
            "exist": "Yes/No question; MUST start with 'Is' or 'Are'.",
            "count": "Counting question; MUST start with 'How many'.",
            "object": "Object identification question; MUST start with 'What' or 'Which'.",
            "status": "Status question; ask state/status or moving/stopped/parked attribute.",
            "comparison": "Comparison question; include closer/farther/closest/farthest relation.",
        }.get(q_type, "Follow qt strictly.")

        prompt = QUESTION_GEN_PROMPT.format(
            n1_label=n1_label, n1_type=n1_type,
            n2_label=n2_label, n2_type=n2_type,
            n3_id=n3_id, n3_type=n3_type, n3_status=n3_status or "unknown",
            r1_dir=r1_dir, r2_dir=r2_dir,
            constraint_desc=constraint_desc or "path-level uniqueness",
            q_type=q_type, answer=answer,
        )
        try:
            _model_used = self._choose_model("question_nlp")
            resp = self._client.chat.completions.create(
                model=_model_used,
                messages=[
                    {
                        "role":    "system",
                        "content": (
                            "You are a VQA question writer for autonomous driving benchmarks. "
                            "Write concise, grammatically correct questions. Return ONLY the "
                            "question text, no explanation."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,   # 少量随机性 = 多样但不失控
                max_tokens=80,     # 一条问题不超过 80 tokens
                stream=False,
                **_LLM_CHAT_EXTRA_KWARGS,
            )
            text = resp.choices[0].message.content.strip()
            # 去除加 引号、多行等杂质
            text = text.strip('"').strip("'").split("\n")[0].strip()
            if len(text) > 10:   # 最短合理问题
                return text
        except Exception as exc:
            _logger.warning("generate_question_nlp failed (%s), using fallback", exc)
        return fallback

    def generate_question_nlp_strict(
        self,
        *,
        path: str,
        q_type: str,
        n1_id: str,
        n1_type: str,
        n2_id: str,
        n2_type: str,
        n3_id: str,
        n3_type: str,
        n3_status: str,
        r1_dir: str,
        r2_dir: str,
        constraint_desc: str,
        answer: str,
        scene_distribution: Dict[str, int] | None = None,
    ) -> str:
        """
        V18 严格模式：
        - 自然语言问题必须由 LLM 生成
        - 禁止模板 fallback
        - 失败时抛异常，由调用方重试/丢弃
        """
        scene_distribution = scene_distribution or {}
        # 只保留前6类，压缩token
        dist_items = list(scene_distribution.items())[:6]
        dist_text = ",".join(f"{k}:{v}" for k, v in dist_items) or "na"

        n1_label = "ego" if n1_id == "ego" else (
            n1_id if n1_id.lower().startswith(n1_type.lower()) else f"{n1_type} {n1_id}"
        )
        n2_label = n2_id if n2_id.lower().startswith(n2_type.lower()) else f"{n2_type} {n2_id}"
        qtype_rule = {
            "exist": "Yes/No question; MUST start with 'Is' or 'Are'.",
            "count": "Counting question; MUST start with 'How many'.",
            "object": "Object identification question; MUST start with 'What' or 'Which'.",
            "status": "Status question; ask state/status or moving/stopped/parked attribute.",
            "comparison": "Comparison question; include closer/farther/closest/farthest relation.",
        }.get(q_type, "Follow qt strictly.")

        prompt = (
            f"qt={q_type};"
            f"p1={n1_label}->{n2_label}@{r1_dir};"
            f"p2={n2_label}->{n3_id}({n3_type},{n3_status or 'unknown'})@{r2_dir};"
            f"c={constraint_desc or 'path-unique'};"
            f"a={answer};"
            f"d={dist_text};"
            f"rule={qtype_rule}\n"
            "Write ONE grounded driving question that follows the rule EXACTLY. "
            "Use only dirs {front,front-left,front-right,back-left,back-right,back}. "
            "Max 18 words. Output question only."
        )

        raw = self._call(
            prompt,
            system_prompt=(
                "You are a NuScenes-QA style question writer for autonomous driving VQA. "
                "Return EXACTLY ONE question sentence, no quotes, no explanation. "
                "Obey qt and rule strictly."
            ),
            temperature=0.15,
            max_tokens=56,
            call_tag="question_nlp_strict",
        )
        text = raw.strip().strip('"').strip("'").split("\n")[0].strip()
        if len(text) < 12:
            raise RuntimeError(f"LLM returned too-short question: {text!r}")
        return text

    # ------------------------------------------------------------------
    # V6: 批处理：generate_context_cypher_batch()
    # ------------------------------------------------------------------

    def generate_context_cypher_batch(
        self,
        cells: List[Dict],
        topology: str = "L2",  # "L2" (统一), "L2A"/"L2B" (向后兼容)
    ) -> List[str]:
        """一次 LLM 调用处理 N 个路径缺口，返回长度相同的 Cypher 列表。

        单条解析失败时降级到小写弋 fallback。
        """
        n = len(cells)
        if n == 0:
            return []
        _strategy = str(os.getenv("VQA_CTX_BATCH_STRATEGY", "hybrid") or "hybrid").strip().lower()
        if _strategy in ("hybrid", "template_hybrid", "template_only", "template"):
            if _strategy in ("hybrid", "template_hybrid"):
                _hints = self._generate_context_hints_batch(cells, topology=topology)
            else:
                _hints = [self._default_ctx_hint() for _ in range(n)]
            _out = []
            for i, c in enumerate(cells):
                _hint = _hints[i] if i < len(_hints) else self._default_ctx_hint()
                # 统一使用L2方法，向后兼容L2A/L2B
                if topology in ("L2", "L2A"):
                    _out.append(self._build_l2_hybrid_cypher(c, _hint))
                else:  # L2B
                    _out.append(self._build_l2b_hybrid_cypher(c, _hint))
            return _out

        gaps_payload = [
            [
                topology,
                c.get("n1_id", ""), c.get("n2_id", ""), c.get("n3_id", ""),
                c.get("r1_dir8", ""), c.get("r2_dir8", ""),
                c.get("n2_type", ""), c.get("n3_type", ""),
            ]
            for c in cells
        ]
        prompt = L2_BATCH_PROMPT.format(
            n=n,
            gaps_json=_json.dumps(gaps_payload, ensure_ascii=False),
        )
        try:
            _tok_env = int(str(os.getenv("VQA_CTX_BATCH_MAX_TOKENS", "") or "0").strip() or "0")
        except Exception:
            _tok_env = 0
        if _tok_env > 0:
            _ctx_max_tokens = _tok_env
        else:
            try:
                _per_cell = int(
                    str(os.getenv("VQA_CTX_BATCH_TOKENS_PER_CELL", "180") or "180").strip() or "180"
                )
            except Exception:
                _per_cell = 180
            try:
                _auto_cap = int(
                    str(os.getenv("VQA_CTX_BATCH_MAX_TOKENS_AUTO_CAP", "1400") or "1400").strip() or "1400"
                )
            except Exception:
                _auto_cap = 1400
            _per_cell = max(80, _per_cell)
            _auto_cap = max(256, _auto_cap)
            _ctx_max_tokens = min(_auto_cap, max(256, _per_cell * max(1, n)))

        try:
            raw = self._call(
                prompt,
                temperature=0.0,
                max_tokens=_ctx_max_tokens,
                call_tag="l2_batch_context",
            )
        except Exception as exc:
            _logger.info("批处理 LLM 失败 (%s)，全部降级到 fallback", exc)
            return [self._get_fallback(c, topology) for c in cells]

        # 解析 JSON 数组
        cyphers = self._parse_batch_response(raw, n)

        # 按项验证 / 降级
        result = []
        for i, cypher in enumerate(cyphers):
            cypher = self._repair_l2_scope(cypher)
            if (
                cypher
                and self._looks_like_cypher(cypher)
                and self._looks_like_l2_context_schema(cypher)
            ):
                result.append(cypher)
            else:
                _logger.debug("批处理项 %d Cypher 不合规，降级 fallback", i)
                result.append(self._get_fallback(cells[i], topology))
        return result

    @staticmethod
    def _parse_batch_response(raw: str, n: int) -> List[str]:
        """Try to extract a JSON array of N Cypher strings from LLM output."""
        # 尝试直接解析 JSON 数组
        text = raw.strip()
        # 安全去掉 markdown
        text = re.sub(r"```[a-zA-Z]*\n?", "", text).rstrip("`").strip()
        # 尝试救 ```json ... ``` 包裹
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            text = m.group(0)
        try:
            parsed = _json.loads(text)
            if isinstance(parsed, list) and len(parsed) == n:
                out: List[str] = []
                for item in parsed:
                    if isinstance(item, str):
                        out.append(item.strip())
                        continue
                    if isinstance(item, dict):
                        cand = (
                            item.get("cypher")
                            or item.get("query")
                            or item.get("c")
                            or ""
                        )
                        out.append(str(cand).strip())
                        continue
                    out.append("")
                return out
        except Exception:
            pass
        # 如果解析失败，返回空列表触发全部降级
        _logger.info("批处理响应无法解析为 JSON 数组 (n=%d)", n)
        return ["" for _ in range(n)]

    def _get_fallback(self, cell: Dict, topology: str) -> str:
        """Dispatch to the appropriate fallback Cypher builder."""
        if topology in ("L2", "L2A"):
            return self.build_l2_fallback_cypher(cell)
        return self.build_l2b_obj_fallback_cypher(cell)

    @staticmethod
    def build_l2_fallback_cypher(cell: Dict) -> str:
        """Hardcoded L2 context Cypher (A→B→C + B的干扰项兄弟节点，含空间属性).
        统一L2方法，不再区分L2A/L2B。
        V6 Fix: 用 collect({{...}}) 收集 sibling 的 dir8/dist，让 ConstraintChain 能用方向收束。
        V7 Enhancement: sibling 额外带 actual_dist / translation / degree，
                        供 DistRank / SpatialRegion / DegreeConstraint 使用。
        """
        n1 = cell.get("n1_id", "")
        n2 = cell.get("n2_id", "")
        n3 = cell.get("n3_id", "")
        return f"""
MATCH (a:Object {{unique_id: '{n1}'}})-[r1:RELATES_TO]->(b:Object {{unique_id: '{n2}'}})
      -[r2:RELATES_TO]->(c:Object {{unique_id: '{n3}'}})
OPTIONAL MATCH (b)-[r3:RELATES_TO]->(sibling:Object)
  WHERE sibling.unique_id <> '{n1}' AND sibling.unique_id <> '{n3}'
OPTIONAL MATCH (sibling)-[:RELATES_TO]-(sib_neighbor:Object)
WITH a, b, c, r1, r2,
     sibling, r3, count(DISTINCT sib_neighbor) AS sib_degree
WITH a, b, c, r1, r2,
     collect({{id:sibling.unique_id, type:sibling.type,
               status:coalesce(sibling.status,''),
               dir8:r3.direction_8, dist:r3.distance,
               actual_dist:r3.distance,
               tx:sibling.translation_x, ty:sibling.translation_y,
               degree:sib_degree}}) AS siblings
OPTIONAL MATCH (c)-[:RELATES_TO]-(c_neighbor:Object)
WITH a, b, c, r1, r2, siblings, count(DISTINCT c_neighbor) AS c_degree
RETURN
  a.unique_id                          AS n1_id,
  a.type                               AS n1_type,
  coalesce(a.status,'')                AS n1_status,
  b.unique_id                          AS n2_id,
  b.type                               AS n2_type,
  coalesce(b.status,'')                AS n2_status,
  b.translation_x                      AS n2_tx,
  b.translation_y                      AS n2_ty,
  c.unique_id                          AS n3_id,
  c.type                               AS n3_type,
  coalesce(c.status,'')                AS n3_status,
  c.translation_x                      AS n3_tx,
  c.translation_y                      AS n3_ty,
  c_degree                             AS n3_degree,
  r1.direction_4                       AS r1_dir4,
  r1.direction_8                       AS r1_dir8,
  coalesce(r1.predicates[1],'')        AS r1_dist,
  r1.distance                          AS r1_actual_dist,
  r2.direction_4                       AS r2_dir4,
  r2.direction_8                       AS r2_dir8,
  coalesce(r2.predicates[1],'')        AS r2_dist,
  r2.distance                          AS r2_actual_dist,
  [s IN siblings | s.id]               AS sibling_ids,
  [s IN siblings | s.type]             AS sibling_types,
  [s IN siblings | s.status]           AS sibling_statuses,
  [s IN siblings | s.dir8]             AS sibling_dir8s,
  [s IN siblings | s.dist]             AS sibling_dists,
  [s IN siblings | s.actual_dist]      AS sibling_actual_dists,
  [s IN siblings | s.tx]               AS sibling_txs,
  [s IN siblings | s.ty]               AS sibling_tys,
  [s IN siblings | s.degree]           AS sibling_degrees
LIMIT 1
""".strip()

    # Backward compatibility alias
    @staticmethod
    def build_l2a_fallback_cypher(cell: Dict) -> str:
        """向后兼容：调用统一的L2方法"""
        return LLMClient.build_l2_fallback_cypher(cell)

    def generate_l2b_obj_context_cypher(self, cell: Dict) -> str:
        """生成 L2B 物体链上下文 Cypher（A→B→C；A 非 ego，B/C 可为 ego）。"""
        try:
            prompt = L2B_OBJ_CONTEXT_PROMPT.format(**cell)
        except KeyError:
            return self.build_l2b_obj_fallback_cypher(cell)
        raw     = self._call(
            prompt,
            temperature=0.0,
            max_tokens=800,
            call_tag="l2b_obj_context",
        )
        cleaned = self._strip_fences(raw)
        if not self._looks_like_cypher(cleaned):
            _logger.info("「L2B-OBJ LLM Cypher 不合规」，退回硬编码")
            return self.build_l2b_obj_fallback_cypher(cell)
        return cleaned

    @staticmethod
    def build_l2b_obj_fallback_cypher(cell: Dict) -> str:
        """Hardcoded L2B fallback（A→B→C；A 非 ego；B/C 可为 ego；含 sibling dir8/dist）。"""
        n1 = cell.get("n1_id", "")
        n2 = cell.get("n2_id", "")
        n3 = cell.get("n3_id", "")
        return f"""
MATCH (a:Object {{unique_id: '{n1}'}})-[r1:RELATES_TO]-(b:Object {{unique_id: '{n2}'}})
      -[r2:RELATES_TO]-(c:Object {{unique_id: '{n3}'}})
OPTIONAL MATCH (b)-[r3:RELATES_TO]-(sibling:Object)
  WHERE sibling.unique_id <> '{n1}' AND sibling.unique_id <> '{n3}'
WITH a, b, c, r1, r2,
     collect({{id:sibling.unique_id, type:sibling.type,
               status:coalesce(sibling.status,''),
               dir8:r3.direction_8, dist:r3.distance}}) AS siblings
RETURN
  a.unique_id                          AS n1_id,
  a.type                               AS n1_type,
  coalesce(a.status,'')                AS n1_status,
  b.unique_id                          AS n2_id,
  b.type                               AS n2_type,
  coalesce(b.status,'')                AS n2_status,
  c.unique_id                          AS n3_id,
  c.type                               AS n3_type,
  coalesce(c.status,'')                AS n3_status,
  r1.direction_4                       AS r1_dir4,
  r1.direction_8                       AS r1_dir8,
  coalesce(r1.predicates[1],'')        AS r1_dist,
  r1.distance                          AS r1_actual_dist,
  r2.direction_4                       AS r2_dir4,
  r2.direction_8                       AS r2_dir8,
  coalesce(r2.predicates[1],'')        AS r2_dist,
  r2.distance                          AS r2_actual_dist,
  [s IN siblings | s.id]               AS sibling_ids,
  [s IN siblings | s.type]             AS sibling_types,
  [s IN siblings | s.status]           AS sibling_statuses,
  [s IN siblings | s.dir8]             AS sibling_dir8s,
  [s IN siblings | s.dist]             AS sibling_dists
LIMIT 1
""".strip()

    @staticmethod
    def build_l2b_fallback_cypher(cell: Dict) -> str:
        """Hardcoded L2B context Cypher (ego→X 和 ego→Y 双臂)."""
        a_id  = cell.get("a_id",  "")
        b_id  = cell.get("b_id",  "")
        ego   = cell.get("ego_id", "ego")
        return f"""
MATCH (ego:Object {{unique_id: '{ego}'}})-[r1:RELATES_TO]->(a:Object {{unique_id: '{a_id}'}}),
      (ego)-[r2:RELATES_TO]->(b:Object {{unique_id: '{b_id}'}})
OPTIONAL MATCH (ego)-[r3:RELATES_TO]->(ctx:Object)
  WHERE ctx.unique_id <> '{a_id}' AND ctx.unique_id <> '{b_id}'
WITH a, b, r1, r2, collect(ctx) AS ctx_nodes
RETURN
  a.unique_id                          AS a_id,
  a.type                               AS a_type,
  coalesce(a.status,'')                AS a_status,
  '{ego}'                              AS ego_id,
  b.unique_id                          AS b_id,
  b.type                               AS b_type,
  coalesce(b.status,'')                AS b_status,
  r1.direction_4                       AS r1_dir4,
  r1.direction_8                       AS r1_dir8,
  coalesce(r1.predicates[1],'')        AS r1_dist,
  r1.distance                          AS r1_actual_dist,
  r2.direction_4                       AS r2_dir4,
  r2.direction_8                       AS r2_dir8,
  coalesce(r2.predicates[1],'')        AS r2_dist,
  r2.distance                          AS r2_actual_dist,
  [n IN ctx_nodes | n.unique_id]       AS context_node_ids,
  [n IN ctx_nodes | n.type]            AS context_node_types
LIMIT 1
""".strip()
