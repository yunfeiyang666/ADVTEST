"""
LLM客户端 - 调用元景大模型API
兼容OpenAI接口格式
"""
import requests
import json
import time
import re
import logging
from typing import Optional, Tuple, List, Dict, Any

from . import config

logger = logging.getLogger(__name__)

# HTTP status codes that warrant retry
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class LLMClient:
    """元景大模型API客户端（兼容OpenAI格式）"""
    
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None, verify_ssl: bool = None):
        self.api_key = api_key or config.API_KEY
        self.base_url = base_url or config.API_BASE_URL
        self.model = model or config.MODEL_NAME
        self.timeout = config.REQUEST_TIMEOUT
        self.max_retries = config.MAX_RETRIES
        # 使用配置中的SSL验证设置，默认为False以支持本地调试
        self.verify_ssl = verify_ssl if verify_ssl is not None else config.VERIFY_SSL
        
        # Initialize attributes that are set by generation methods
        self.last_thinking: Optional[str] = None
        self.last_elapsed: Optional[float] = None
        
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表 [{"role": "user/assistant/system", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大生成token数
            
        Returns:
            模型生成的回复文本
            
        Raises:
            Exception: API请求失败且超出重试次数
        """
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                    verify=self.verify_ssl,  # Configurable SSL verification
                )
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        # Safely extract content with validation
                        if "choices" not in result or not result["choices"]:
                            raise ValueError("Invalid API response: missing 'choices'")
                        choice = result["choices"][0]
                        if "message" not in choice or "content" not in choice["message"]:
                            raise ValueError("Invalid API response: missing 'message.content'")
                        
                        # 检测是否被截断（finish_reason == 'length'）
                        finish_reason = choice.get("finish_reason", "stop")
                        # 以前这里会在 finish_reason == 'length' 时自动增大 max_tokens 并重试，
                        # 这会让错误题目卡非常久。现在只做日志提示，不再放大 max_tokens 或重试，
                        # 直接返回当前内容（即使是被截断的）。
                        if finish_reason == "length":
                            logger.warning(
                                f"⚠️ LLM响应被截断 (finish_reason=length, max_tokens={max_tokens})，" \
                                "已关闭自动增大max_tokens重试逻辑，直接返回当前结果。"
                            )
                        
                        return choice["message"]["content"]
                    except (ValueError, KeyError, IndexError) as e:
                        logger.error(f"Failed to parse API response: {e}")
                        logger.debug(f"Response content: {response.text}")
                        raise ValueError(f"Invalid API response format: {e}") from e
                else:
                    logger.warning(
                        f"API request failed (attempt {attempt+1}/{self.max_retries}): "
                        f"status={response.status_code}"
                    )
                    logger.debug(f"Response: {response.text}")
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    
                    # Special handling for rate limiting
                    if response.status_code == 429:
                        retry_after = int(response.headers.get('Retry-After', 5))
                        logger.info(f"Rate limited, waiting {retry_after}s before retry")
                        time.sleep(retry_after)
                        continue
                    
                    # Only retry on retryable status codes
                    if response.status_code not in RETRYABLE_STATUS_CODES:
                        raise Exception(f"Non-retryable error: {last_error}")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout (attempt {attempt+1}/{self.max_retries})")
                last_error = "Request timeout"
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request exception (attempt {attempt+1}/{self.max_retries}): {e}")
                last_error = str(e)
            
            # Exponential backoff (unless already handled by rate limit)
            if attempt < self.max_retries - 1:
                backoff = min(2 ** attempt, 32)  # Cap at 32 seconds
                logger.debug(f"Backing off for {backoff}s before retry")
                time.sleep(backoff)
        
        raise Exception(f"API请求失败，已达到最大重试次数。最后错误: {last_error}")
    
    def _fix_direction_syntax(self, cypher: str) -> str:
        """修复LLM生成的方位查询语法。
        
        问题：LLM经常忽略Prompt指令，使用 r.predicates[0]='direction' 而不是 'direction' IN r.angle_matches_source
        解决：自动将 predicates[0] 替换为正确的 angle_matches_source 语法
        
        示例：
        输入: WHERE r.predicates[0]='back-right'
        输出: WHERE 'back-right' IN r.angle_matches_source
        
        输入: WHERE r1.predicates[0]='left'
        输出: WHERE 'left' IN r1.angle_matches_source
        """
        # Pattern 1: <var>.predicates[0] = 'direction' → 'direction' IN <var>.angle_matches_source
        # 支持任意关系变量名（r, r1, r2, rel, 等）
        pattern1 = r"(\w+)\.predicates\[0\]\s*=\s*'([^']+)'"
        replacement1 = r"'\2' IN \1.angle_matches_source"
        cypher = re.sub(pattern1, replacement1, cypher)
        
        # Pattern 2: <var>.predicates[0] = "direction" → 'direction' IN <var>.angle_matches_source
        pattern2 = r'(\w+)\.predicates\[0\]\s*=\s*"([^"]+)"'
        replacement2 = r"'\2' IN \1.angle_matches_source"
        cypher = re.sub(pattern2, replacement2, cypher)
        
        return cypher
    
    def _fix_status_syntax(self, cypher: str) -> str:
        """修复 status 等价语义问题。
        
        问题：题目可能用 'parked'，但数据中是 'stopped'，两者等价
        解决：自动将 status='parked' 替换为 status IN ['parked', 'stopped']
        
        示例：
        输入: WHERE car.status='parked'
        输出: WHERE car.status IN ['parked', 'stopped']
        """
        # Pattern: <var>.status = 'parked' → <var>.status IN ['parked', 'stopped']
        pattern = r"(\w+)\.status\s*=\s*['\"]parked['\"]"
        replacement = r"\1.status IN ['parked', 'stopped']"
        cypher = re.sub(pattern, replacement, cypher)
        
        return cypher
    
    def generate_cypher(self, question: str, question_type: str = 'general', mode: str = 'strict',
                        feedback: Optional[str] = None, scene_context: Optional[str] = None) -> str:
        """将自然语言问题转换为 **单条可执行的** Cypher 查询。

        约束：
        - 只能返回一条查询，且只能有一个最终的 RETURN 子句；
        - 不允许在一个字符串中拼接多条查询（例如多个 MATCH...RETURN；或 RETURN 之后再跟新的 MATCH）。

        mode 参数说明：
        - "strict": 生产/评测模式，尽量减少复杂抽取逻辑，只做轻量清洗和基础语法检查；
        - "debug" : 调试模式，保留更多抽取/分块逻辑，方便分析模型输出和思考过程。
        
        scene_context: 当前场景的摘要信息，包含对象列表和方位关系
        """
        prompt = config.QUESTION_TO_CYPHER_PROMPT.format(
            question=question,
            prev_error=feedback or "无",
        )

        # System Prompt - 强引导思考流程，快速决策
        system_content = (
            "【思考流程-按此执行】\n"
            "1. 问什么? type/status/count/yes-no\n"
            "2. 哪个对象? 确定目标和参照物\n"
            "3. 有方位吗? 用'DIR' IN r.angle_matches_source\n"
            "4. 写Cypher\n\n"
            "【输出】\n"
            "```cypher\n"
            "MATCH ...查询语句...\n"
            "```\n\n"
            "【规则】\n"
            "对象类型统一用type字段: car/truck/bus/motorcycle/trailer/bicycle/pedestrian/barrier\n"
            "方位: 'DIR' IN r.angle_matches_source\n"
            "'X to DIR of Y': MATCH (Y)-[r]->(X)\n"
            "status值: stopped/moving/with_rider/without_rider/standing\n"
            "parked=stopped: 这两个等价，查parked时用status IN ['parked','stopped']\n"
            "'the X': LIMIT 1\n"
            "other things: type<>'barrier'\n\n"
            "【禁止】predicates[0]/velocity/category CONTAINS/注释"
        )
        
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        start_time = time.time()
        # 低temperature + 足够的max_tokens确保inference完成
        temp = 0.1
        max_tok = 4096  # 给足够空间，避克截断
        response = self.chat(messages, temperature=temp, max_tokens=max_tok)
        elapsed = time.time() - start_time
        
        # 提取思维过程（用于日志）
        think_match = re.search(r"<think>(.*?)</think>", response, flags=re.DOTALL)
        thinking = think_match.group(1).strip() if think_match else None

        # ---------- 提取Cypher查询：优先级顺序 ----------
        # 记录是否从代码块提取（用于strict模式决策）
        extracted_from_code_block = False
        
        # 1. 优先提取 ```cypher ... ``` 块（标准代码块）
        cypher_block_match = re.search(r"```cypher\s*(.*?)```", response, flags=re.DOTALL | re.IGNORECASE)
        if cypher_block_match:
            candidate_text = cypher_block_match.group(1).strip()
            extracted_from_code_block = True
        else:
            # 2. 备用：通用代码块 ``` ... ```
            generic_block_match = re.search(r"```\s*(.*?)```", response, flags=re.DOTALL)
            if generic_block_match:
                candidate_text = generic_block_match.group(1).strip()
                extracted_from_code_block = True
            else:
                # 3. 备用：旧版【CYPHER】...【/CYPHER】格式
                legacy_block_match = re.search(r"【CYPHER】(.*?)【/CYPHER】", response, flags=re.DOTALL)
                if legacy_block_match:
                    candidate_text = legacy_block_match.group(1).strip()
                    extracted_from_code_block = True
                else:
                    # 4. 最后备用：移除<think>块后的全部内容
                    cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
                    candidate_text = cleaned if cleaned else response
        
        # 基本清理
        candidate_text = candidate_text.strip().rstrip(";")
        
        # 后处理：修夏LLM不遵守Prompt的问题
        candidate_text = self._fix_direction_syntax(candidate_text)  # predicates[0] -> angle_matches_source
        candidate_text = self._fix_status_syntax(candidate_text)     # parked -> IN ['parked', 'stopped']

        def _strip_comment_and_explanation_lines(text: str) -> str:
            """移除明显是解释/注释的行，保留更像Cypher的行（strict模式使用）。

            策略（尽量保守，只保留“看起来像Cypher语句”的行）：
            - 丢弃：
              * 以 //、#、-- 开头的注释行；
              * 只包含 ... / .. 的占位行；
              * 带有明显中文说明/自然语言的行（"表示"、"意思是"、"例如"、"比如"、"注意"等）；
              * 以大小写英文开头、且不以任何Cypher关键字开头且不含括号/方括号的行（通常是英文解释）。
            - 保留：
              * 以 Cypher 关键字开头的行：MATCH / WHERE / WITH / RETURN / CREATE / MERGE / OPTIONAL / UNWIND / CALL / SET / DELETE / DETACH / REMOVE / FOREACH / UNION / SKIP / LIMIT / ORDER BY 等；
              * 其余行中，如果包含 () 或 [] 或 {} 且包含关系/节点模式的典型标记（:Object、RELATES_TO 等），也保留。
            """
            lines: list[str] = []
            cypher_starts = (
                "MATCH",
                "WHERE",
                "WITH",
                "RETURN",
                "CREATE",
                "MERGE",
                "OPTIONAL",
                "UNWIND",
                "CALL",
                "SET",
                "DELETE",
                "DETACH",
                "REMOVE",
                "FOREACH",
                "UNION",
                "SKIP",
                "LIMIT",
                "ORDER BY",
            )
            for raw in text.splitlines():
                # 先去掉行尾内联注释（//、#、-- 之后的部分），避免语法错误和中文说明残留
                ln = raw.rstrip()
                if not ln:
                    continue
                # 按第一个注释分隔符截断（不包含分隔符本身）
                parts = re.split(r"//|#|--", ln, maxsplit=1)
                ln = parts[0].rstrip()
                if not ln:
                    continue
                # 移除括号内的解释文本（例如 "RETURN x.type   (or maybe x.id?)" → "RETURN x.type"）
                ln = re.sub(r'\s*\([^()]*\?[^()]*\)', '', ln)  # 移除包含问号的括号注释
                ln = re.sub(r'\s*\([^()]*(?:or|alternatively|meaning|i\.e\.|e\.g\.|note)[^()]*\)', '', ln, flags=re.IGNORECASE)  # 移除包含解释性词汇的括号
                ln = ln.rstrip()
                if not ln:
                    continue
                up = ln.upper()
                # 跳过纯注释或省略号
                if ln.startswith("//") or ln.startswith("#") or ln.startswith("--"):
                    continue
                if ln.startswith("💭") or "思维过程" in ln or "AI思维" in ln:
                    continue
                if ln in ("...", ".."):
                    continue
                # 明显中文说明行
                if any(tok in ln for tok in ["表示", "意思是", "例如", "比如", "注意：", "注意:", "例如：", "说明", "解释", "含义"]):
                    continue
                # 以自然语言开头但不是Cypher关键字的英文/中文句子，大概率是说明
                first_token = ln.split()[0].upper() if ln.split() else ""
                if not any(first_token.startswith(kw) for kw in cypher_starts):
                    # 如果这一行既不包含典型模式符号，也没有明显的Cypher关键词，则丢弃
                    if not any(ch in ln for ch in "()[]{}"):
                        continue
                    # 允许包含关系/节点模式的行
                    if not any(marker in ln for marker in [":Object", "RELATES_TO", "=", "<-"]):
                        continue
                lines.append(ln)
            return "\n".join(lines).strip()

        def _extract_single_query_debug(text: str) -> str:
            """原有的较复杂抽取逻辑（保留为debug模式）。"""
            # 按空行分块，尝试从最后一个包含 MATCH 和 RETURN 的块中选取查询
            chunks = [ch.strip() for ch in re.split(r"\n\s*\n", text) if ch.strip()]
            query_block = None
            for ch in reversed(chunks):
                up = ch.upper()
                if "MATCH" in up and "RETURN" in up:
                    query_block = ch.strip()
                    break

            # 如果没有找到合格块，则退回到按行过滤 Cypher 关键字的策略
            if query_block is None:
                lines = [ln.rstrip() for ln in text.split("\n")]
                filtered: list[str] = []
                for ln in lines:
                    up = ln.lstrip().upper()
                    if any(
                        up.startswith(kw)
                        for kw in [
                            "MATCH",
                            "MERGE",
                            "CREATE",
                            "WITH",
                            "WHERE",
                            "RETURN",
                            "ORDER BY",
                            "LIMIT",
                            "UNWIND",
                            "CALL",
                        ]
                    ):
                        filtered.append(ln.strip())
                if filtered:
                    query_block = "\n".join(filtered).strip()

            cypher_text = (query_block or "").strip()

            def extract_single_query(text2: str) -> str:
                lines2 = [ln for ln in text2.splitlines() if ln.strip()]
                if not lines2:
                    return ""

                collected: list[str] = []
                started = False
                seen_return = False

                for ln2 in lines2:
                    stripped2 = ln2.strip()
                    upper_ln2 = stripped2.upper()

                    is_start = upper_ln2.startswith(("MATCH ", "MATCH(", "MERGE ", "CREATE ", "CALL ", "WITH ", "UNWIND ", "OPTIONAL ", "RETURN "))
                    if not started:
                        if is_start:
                            started = True
                            collected.append(stripped2)
                            if upper_ln2.startswith("RETURN") and "}" in stripped2:
                                seen_return = True
                                break
                            if " RETURN " in upper_ln2:
                                seen_return = True
                                break
                        continue

                    if not seen_return:
                        collected.append(stripped2)
                        if " RETURN " in upper_ln2 or upper_ln2.startswith("RETURN"):
                            seen_return = True
                            break
                    else:
                        break

                upper_lines2 = [ln.upper() for ln in collected]
                if not collected or not any("RETURN" in ln for ln in upper_lines2):
                    return ""
                has_match = any("MATCH" in ln for ln in upper_lines2)
                has_exists_subquery = any("EXISTS" in ln and "{" in ln for ln in upper_lines2)
                if not has_match and not has_exists_subquery:
                    return ""

                return "\n".join(collected).strip().rstrip(";")

            return extract_single_query(cypher_text)

        # 根据mode选择抽取策略
        if mode == "debug":
            # 调试模式：对完整文本做复杂抽取，保留更多信息便于分析
            single_query = _extract_single_query_debug(candidate_text)
        else:
            # strict模式：如果成功从代码块提取，直接使用，避免过度清洗
            if extracted_from_code_block:
                # 已绋从代码块中提取，只做基本验证
                single_query = candidate_text.strip().rstrip(";")
            else:
                # 没有代码块标记，使用复杂清洗逻辑
                stripped = _strip_comment_and_explanation_lines(candidate_text)
                if not stripped:
                    single_query = _extract_single_query_debug(candidate_text)
                else:
                    single_query = _extract_single_query_debug(stripped)

        cypher = (single_query or "").strip()

        if not cypher:
            raise Exception(f"LLM 未能生成有效的Cypher查询，原始响应: {response!r}")
        
        # 检测无效的模板占位符（如 <查询> 或 <query>）
        if cypher.startswith('<') and cypher.endswith('>'):
            raise Exception(f"LLM 返回了模板占位符而非实际Cypher: {cypher!r}，原始响应: {response[:500]!r}")
        
        # 基本有效性检查：Cypher 必须包含关键字
        cypher_upper = cypher.upper()
        if not any(kw in cypher_upper for kw in ['MATCH', 'RETURN', 'CREATE', 'MERGE']):
            raise Exception(f"LLM 生成的内容不像有效Cypher: {cypher!r}")

        # 保存元信息
        self.last_thinking = thinking
        self.last_elapsed = elapsed

        return cypher

    def generate_query_plan(self, question: str, question_type: str) -> str:
        """使用IR_GENERATION_PROMPT生成QueryPlan JSON字符串（尽量只返回纯JSON）。"""
        prompt = config.IR_GENERATION_PROMPT + f"\n\nQuestion_type: \"{question_type}\"\nQuestion: \"{question}\"\n\nOutput:\n"
        messages = [
            {"role": "system", "content": "You are a precise information extraction engine. Only output valid JSON, nothing else."},
            {"role": "user", "content": prompt}
        ]
        start_time = time.time()
        response = self.chat(messages, temperature=0.1)
        elapsed = time.time() - start_time

        # 清理 <think> 块以及可能的额外文字，只保留最外层 JSON
        text = response.strip()
        # 1) 移除闭合的 <think>...</think>
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # 2) 移除可能残留的 <think> 开头片段
        text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
        # 3) 移除孤立的 </think>
        text = re.sub(r'</think>', '', text, flags=re.DOTALL)
        text = text.strip()

        # 4) 从清理后的文本中截取第一个 '{' 到最后一个 '}' 作为 JSON 片段
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end + 1]
        else:
            # 如果没有找到明显的JSON结构，就退回原始清理后的文本
            json_str = text

        self.last_thinking = None  # IR生成不使用<think>模式
        self.last_elapsed = elapsed
        return json_str.strip()
    
    def generate_cypher_from_ir(self, query_plan: dict, question: str, feedback: str | None = None) -> str:
        """
        根据IR (QueryPlan) 生成Cypher查询
        
        Args:
            query_plan: QueryPlan JSON对象
            question: 原始问题（提供上下文）
            feedback: 额外重试反馈（用于修正查询）
            
        Returns:
            Cypher查询语句
        """
        import json as _json
        
        prompt = config.IR_TO_LLM_CYPHER_PROMPT.format(
            query_plan=_json.dumps(query_plan, ensure_ascii=False, indent=2),
            question=question
        )
        if feedback:
            prompt += f"\n\nRetry feedback (apply strictly):\n{feedback}\n\nPlease revise the Cypher accordingly."
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的Neo4j Cypher查询专家。请直接输出一条可执行的Cypher查询语句，不要包含任何思考过程或解释。"
            },
            {"role": "user", "content": prompt}
        ]
        
        start_time = time.time()
        response = self.chat(messages, temperature=0.1)  # 低温度确保准确性
        elapsed = time.time() - start_time
        
        # 提取思维过程（用于日志）
        think_match = re.search(r"<think>(.*?)</think>", response, flags=re.DOTALL)
        thinking = think_match.group(1).strip() if think_match else None
        
        # 清理响应
        cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
        
        # 提取代码块
        code_block_match = re.search(r"```(?:cypher)?\s*(.*?)```", cleaned, flags=re.DOTALL)
        if code_block_match:
            cleaned = code_block_match.group(1).strip()
        
        # 移除多余的标记
        cleaned = cleaned.strip().rstrip(";")
        if "<" in cleaned or "`" in cleaned:
            cleaned = re.sub(r"<[^>]+>", "", cleaned)
            cleaned = cleaned.replace("`", "").strip()
        
        # 提取第一条完整的查询（包括 ORDER BY/LIMIT）
        lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip()]
        cypher_lines = []
        started = False
        seen_return = False
        
        for ln in lines:
            up = ln.upper()
            if not started:
                if up.startswith(("MATCH", "RETURN", "WITH", "OPTIONAL")):
                    started = True
                    cypher_lines.append(ln)
                    if up.startswith("RETURN"):
                        seen_return = True
            else:
                # Once started, continue collecting lines
                if not seen_return:
                    cypher_lines.append(ln)
                    if "RETURN" in up:
                        seen_return = True
                else:
                    # After RETURN, only include ORDER BY, LIMIT, SKIP
                    if up.startswith(("ORDER BY", "LIMIT", "SKIP")):
                        cypher_lines.append(ln)
                    else:
                        # Stop at any other statement (likely a new query)
                        if up.startswith(("MATCH", "WITH", "CREATE", "MERGE")):
                            break
                        # Otherwise, might be continuation of previous line
                        # (e.g., multi-line ORDER BY), include it
                        cypher_lines.append(ln)
        
        cypher = "\n".join(cypher_lines).strip()
        
        if not cypher:
            raise Exception(f"LLM 未能生成有效的Cypher查询，原始响应: {response!r}")
        
        self.last_thinking = thinking
        self.last_elapsed = elapsed
        
        return cypher
    
    def generate_answer(self, question: str, query_result: str, question_type: str = 'general', format_requirement: str = '') -> str:
        """
        将查询结果转换为自然语言答案
        
        Args:
            question: 原始问题
            query_result: Neo4j查询结果（JSON字符串）
            question_type: 问题类型
            format_requirement: 答案格式要求
            
        Returns:
            自然语言答案
        """
        prompt = config.RESULT_TO_ANSWER_PROMPT.format(
            question=question,
            result=query_result,
            question_type=question_type,
            format_requirement=format_requirement
        )
        
        messages = [
            {"role": "system", "content": "你是一个专业的问答助手。"},
            {"role": "user", "content": prompt}
        ]
        
        start_time = time.time()
        response = self.chat(messages, temperature=0.5)
        elapsed = time.time() - start_time
        
        # 提取思维过程
        think_match = re.search(r'<think>(.*?)</think>', response, flags=re.DOTALL)
        thinking = think_match.group(1).strip() if think_match else None
        
        # 去除<think>标签
        answer = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
        
        # 保存元信息
        self.last_thinking = thinking
        self.last_elapsed = elapsed
        
        return answer
    
    def call_llm_raw(self, prompt: str, max_tokens: int = 256, temperature: float = 0.1) -> str:
        """
        直接调用LLM（不加工），用于答案判定等简单任务
        
        Args:
            prompt: 完整的prompt
            max_tokens: 最大生成token数
            temperature: 温度参数
            
        Returns:
            LLM原始响应
        """
        messages = [
            {"role": "user", "content": prompt}
        ]
        response = self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        # 去除<think>标签
        cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
        return cleaned
    
    def analyze_query_error(self, question: str, question_type: str, 
                           cypher_query: str, query_result: dict,
                           expected_answer: str = None) -> Tuple[str, str]:
        """
        分析查询错误并提供修复建议
        
        Args:
            question: 原始问题
            question_type: 问题类型
            cypher_query: 生成的Cypher查询
            query_result: 查询结果
            expected_answer: 预期答案（可选，用于更精确的分析）
            
        Returns:
            (error_analysis, fix_suggestion): 错误分析和修复建议
        """
        prompt = f"""You are a Neo4j Cypher query debugging expert.

Original Question: {question}
Question Type: {question_type}

Generated Cypher Query:
```cypher
{cypher_query}
```

Query Result: {json.dumps(query_result, ensure_ascii=False)}
"""
        if expected_answer:
            prompt += f"\nExpected Answer: {expected_answer}\n"
        
        prompt += """
Analyze the issue and provide:
1. Error Analysis: What went wrong? (e.g., wrong direction, missing filter, logic error)
2. Fix Suggestion: How should the query be modified?

Format your response as:
ERROR: <brief error description>
FIX: <specific fix suggestion>

Be concise (max 3 lines each).
"""
        
        try:
            response = self.call_llm_raw(prompt, max_tokens=2048, temperature=0.2)
            
            # 解析响应
            error_analysis = ""
            fix_suggestion = ""
            
            for line in response.split('\n'):
                line = line.strip()
                if line.upper().startswith('ERROR:'):
                    error_analysis = line[6:].strip()
                elif line.upper().startswith('FIX:'):
                    fix_suggestion = line[4:].strip()
            
            if not error_analysis:
                error_analysis = response[:200]
            if not fix_suggestion:
                fix_suggestion = "Review query logic and constraints"
            
            return error_analysis, fix_suggestion
            
        except Exception as e:
            return f"Analysis failed: {e}", "Retry with simplified query"


def test_connection(verify_ssl: bool = False) -> bool:
    """测试API连接
    
    Args:
        verify_ssl: Whether to verify SSL certificates (default False for local testing)
    
    Returns:
        True if connection successful, False otherwise
    """
    client = LLMClient(verify_ssl=verify_ssl)
    try:
        response = client.chat([{"role": "user", "content": "你好，请简短回复。"}])
        print(f"✓ API连接成功！")
        print(f"  回复: {response}")
        return True
    except Exception as e:
        print(f"✗ API连接失败: {e}")
        logger.exception("API connection test failed")
        return False


if __name__ == "__main__":
    # Setup basic logging for standalone test
    logging.basicConfig(level=logging.INFO)
    test_connection()
