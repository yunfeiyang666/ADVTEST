"""
Gap Pipeline — LLM Client
Thin wrapper around an OpenAI-compatible chat completion API.
Only used for Cypher generation — all QA answers come from Neo4j context.
"""
import logging
import re
from typing import Dict

from .config import LLM_CONFIG, SCENE_ANALYSIS_PROMPT, GAP_CONTEXT_PROMPT

_logger = logging.getLogger(__name__)

# LLM HTTP 超时配置（connect 10s，read 30s）
# 超时后 run_gap_pipeline 自动退回硬编码 Cypher，保证流程不卡住
_LLM_TIMEOUT_CONNECT = float(
    LLM_CONFIG.get("timeout_connect", 10.0)  # type: ignore[arg-type]
)
_LLM_TIMEOUT_READ = float(
    LLM_CONFIG.get("timeout_read", 30.0)  # type: ignore[arg-type]
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

        # 设置连接超时，防止 DeepSeek-R1 思考过长把流程挂起
        _timeout = httpx.Timeout(
            connect=_LLM_TIMEOUT_CONNECT,
            read=_LLM_TIMEOUT_READ,
            write=10.0,
            pool=5.0,
        )
        http_client = (
            httpx.Client(timeout=_timeout)  # verify_ssl=True 时不禁用 SSL
            if LLM_CONFIG["verify_ssl"]
            else httpx.Client(verify=False, timeout=_timeout)  # noqa: S501
        )
        self._client = openai.OpenAI(
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["api_base"],
            http_client=http_client,
            timeout=_LLM_TIMEOUT_READ,   # openai 客户端级超时保险
            max_retries=0,               # 禁止重试，超时直接退回硬编码 Cypher
        )
        self._model = LLM_CONFIG["model"]
        self._temperature = LLM_CONFIG["temperature"]
        self._max_tokens = LLM_CONFIG["max_tokens"]
        # 最近一次调用的 token 用量（用于 RQ1 成本分析）
        self.last_token_usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        _logger.info(
            "LLMClient 初始化  model=%s  timeout(connect/read)=%.0f/%.0fs",
            self._model, _LLM_TIMEOUT_CONNECT, _LLM_TIMEOUT_READ,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call(self, prompt: str) -> str:
        """Send a single-turn prompt and return the response text."""
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Neo4j Cypher expert for autonomous driving "
                        "scene graphs. Return only valid Cypher queries."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            stream=False,
        )
        # 记录 token 用量（部分接口可能无 usage 字段，安全取得）
        try:
            u = resp.usage
            if u:
                self.last_token_usage = {
                    "prompt_tokens":     getattr(u, "prompt_tokens",     0) or 0,
                    "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                    "total_tokens":      getattr(u, "total_tokens",      0) or 0,
                }
        except Exception:
            pass
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
        """Basic sanity check for generated Cypher."""
        if not text:
            return False
        s = text.strip()
        if "<think>" in s.lower():
            return False
        if not re.match(r"(?is)^(MATCH|OPTIONAL|WITH|UNWIND|CALL|CREATE|MERGE)\b", s):
            return False
        if "RETURN" not in s.upper():
            return False
        return True

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
        raw = self._call(SCENE_ANALYSIS_PROMPT)
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
        raw = self._call(prompt)
        logger.debug("LLM raw output (first 200 chars): %s", raw[:200])
        cleaned = self._strip_fences(raw)
        logger.debug("After _strip_fences (first 200 chars): %s", cleaned[:200])
        if not self._looks_like_cypher(cleaned):
            return self._gap_context_fallback_cypher(src_id, tgt_id)
        return cleaned
