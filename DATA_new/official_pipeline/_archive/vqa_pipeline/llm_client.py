"""
LLM客户端 - 调用元景大模型API
兼容OpenAI接口格式
"""
import requests
import json
import time
import re
from typing import Optional, Tuple

from . import config


class LLMClient:
    """元景大模型API客户端（兼容OpenAI格式）"""
    
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self.api_key = api_key or config.API_KEY
        self.base_url = base_url or config.API_BASE_URL
        self.model = model or config.MODEL_NAME
        self.timeout = config.REQUEST_TIMEOUT
        self.max_retries = config.MAX_RETRIES
        
    def chat(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表 [{"role": "user/assistant/system", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大生成token数
            
        Returns:
            模型生成的回复文本
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
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
                verify=False,  # 本地调试环境临时关闭证书校验
            )
                
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    print(f"API请求失败 (尝试 {attempt+1}/{self.max_retries}): {response.status_code}")
                    print(f"响应: {response.text}")
                    
            except requests.exceptions.Timeout:
                print(f"请求超时 (尝试 {attempt+1}/{self.max_retries})")
            except requests.exceptions.RequestException as e:
                print(f"请求异常 (尝试 {attempt+1}/{self.max_retries}): {e}")
            
            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
        
        raise Exception("API请求失败，已达到最大重试次数")
    
    def generate_cypher(self, question: str, question_type: str = 'general', mode: str = 'strict', feedback: Optional[str] = None) -> str:
        """将自然语言问题转换为 **单条可执行的** Cypher 查询。

        约束：
        - 只能返回一条查询，且只能有一个最终的 RETURN 子句；
        - 不允许在一个字符串中拼接多条查询（例如多个 MATCH...RETURN；或 RETURN 之后再跟新的 MATCH）。

        mode 参数说明：
        - "strict": 生产/评测模式，尽量减少复杂抽取逻辑，只做轻量清洗和基础语法检查；
        - "debug" : 调试模式，保留更多抽取/分块逻辑，方便分析模型输出和思考过程。
        """
        prompt = config.QUESTION_TO_CYPHER_PROMPT.format(
            schema=config.SCENE_GRAPH_SCHEMA,
            question=question,
            question_type=question_type,
            prev_error=feedback or "无",
        )

        # 根据是否有feedback调整system message的简洁性要求
        if feedback:
            system_content = (
                "你是一个专业的Neo4j Cypher查询专家。\n"
                "**重要**: 这是一次重试，你之前的查询有误。请简洁输出修正后的Cypher查询。\n"
                "**禁止**: 不要输出冗长的思考过程、解释或分析。如需思考，请控制在3行以内。\n"
                "**要求**: 直接在【CYPHER】...【/CYPHER】块中输出一条完整的、可执行的Cypher查询。\n"
                "只生成一条查询，且只有一个最终 RETURN；可以包含多个 MATCH/WHERE/WITH 等子句，但不要在 RETURN 之后继续追加新的查询。\n"
                "对于方位：单一方位词（front/back/left/right）使用 r.direction_4；复合方位（如 'front-left'/'back-right'）使用 r.predicates[0] 或 r.direction_8，直接使用完整8方位值，不要简化为其它方位。"
            )
        else:
            system_content = (
                "你是一个专业的Neo4j Cypher查询专家。请直接输出一条可执行的Cypher查询语句，不要在 <think> 之外添加任何解释或自然语言说明。\n"
                "只生成一条查询，且只有一个最终 RETURN；可以包含多个 MATCH/WHERE/WITH 等子句，但不要在 RETURN 之后继续追加新的查询。\n"
                "❗❗ 极其重要：如果你在WITH子句中定义了变量（如 refStatus, refId），必须在后续的WHERE子句中使用它们！\n"
                "  错误示例: WITH refStatus, refId ... MATCH (o:Object) WHERE o.type='car' RETURN count(o)  // refStatus和refId未使用\n"
                "  正确示例: WITH refStatus, refId ... MATCH (o:Object) WHERE o.type='car' AND o.status=refStatus AND o.unique_id<>refId RETURN count(o)\n"
                "对于方位：单一方位词（front/back/left/right）使用 r.direction_4；复合方位（如 'front-left'/'back-right'）使用 r.predicates[0] 或 r.direction_8，直接使用完整八方位值，不要简化为其它方位。"
            )
        
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        start_time = time.time()
        # retry时使用更低的temperature和更小的max_tokens，减少冗余输出
        temp = 0.1 if feedback else 0.2
        max_tok = 1024 if feedback else 2048
        response = self.chat(messages, temperature=temp, max_tokens=max_tok)
        elapsed = time.time() - start_time

        # 提取思维过程（用于日志）
        think_match = re.search(r"<think>(.*?)</think>", response, flags=re.DOTALL)
        thinking = think_match.group(1).strip() if think_match else None

        # ---------- 通用清理：去掉<think>和代码块包装 ----------
        cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()

        code_block_match = re.search(r"```(?:cypher)?\s*(.*?)```", cleaned, flags=re.DOTALL)
        if code_block_match:
            cleaned = code_block_match.group(1).strip()

        cleaned = cleaned.strip().rstrip(";")
        if "<" in cleaned or "`" in cleaned:
            cleaned = re.sub(r"<[^>]+>", "", cleaned)
            cleaned = cleaned.replace("`", "").strip()

        # 优先从【CYPHER】...【/CYPHER】块中提取主体查询文本
        block_match = re.search(r"【CYPHER】(.*?)【/CYPHER】", cleaned, flags=re.DOTALL)
        if block_match:
            candidate_text = block_match.group(1).strip()
        else:
            candidate_text = cleaned if cleaned else response

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
            # strict模式：如果成功从【CYPHER】块提取，直接使用，避免过度清洗
            if block_match:
                # 已经从【CYPHER】块中提取，只做基本验证
                single_query = candidate_text.strip().rstrip(";")
            else:
                # 没有【CYPHER】块标记，使用复杂清洗逻辑
                stripped = _strip_comment_and_explanation_lines(candidate_text)
                if not stripped:
                    single_query = _extract_single_query_debug(candidate_text)
                else:
                    single_query = _extract_single_query_debug(stripped)

        cypher = (single_query or "").strip()

        if not cypher:
            raise Exception(f"LLM 未能生成有效的Cypher查询，原始响应: {response!r}")

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
    
    def generate_cypher_from_ir(self, query_plan: dict, question: str) -> str:
        """
        根据IR (QueryPlan) 生成Cypher查询
        
        Args:
            query_plan: QueryPlan JSON对象
            question: 原始问题（提供上下文）
            
        Returns:
            Cypher查询语句
        """
        import json as _json
        
        prompt = config.IR_TO_CYPHER_PROMPT.format(
            query_plan=_json.dumps(query_plan, ensure_ascii=False, indent=2),
            question=question
        )
        
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
        
        # 提取第一条完整的查询
        lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip()]
        cypher_lines = []
        started = False
        for ln in lines:
            up = ln.upper()
            if not started:
                if up.startswith(("MATCH", "RETURN", "WITH", "OPTIONAL")):
                    started = True
                    cypher_lines.append(ln)
            else:
                cypher_lines.append(ln)
                if "RETURN" in up and not up.startswith("RETURN"):
                    break
                if up.startswith("RETURN"):
                    break
        
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
    
    def generate_gap_context_cypher(self, gap_cell: dict) -> str:
        """给定一个缺口边（ID模式），生成按 unique_id 精确匹配并获取上下文的 Cypher。

        输入 gap_cell 字段:
          src_id, src_type, src_status,
          tgt_id, tgt_type, tgt_status,
          dir4, dir8, dist_level
        返回可直接在 Neo4j 中执行的 Cypher 字符串（含 OPTIONAL MATCH L2 链）。
        """
        src_id     = gap_cell.get("src_id", "")
        src_type   = gap_cell.get("src_type", "")
        src_status = gap_cell.get("src_status", "")
        tgt_id     = gap_cell.get("tgt_id", "")
        tgt_type   = gap_cell.get("tgt_type", "")
        tgt_status = gap_cell.get("tgt_status", "")
        dir4       = gap_cell.get("dir4", "")
        dir8       = gap_cell.get("dir8", "")
        dist_level = gap_cell.get("dist_level", "")

        prompt = config.GAP_CONTEXT_PROMPT.format(
            schema=config.SCENE_GRAPH_SCHEMA,
            src_id=src_id,
            src_type=src_type,
            src_status=src_status,
            tgt_id=tgt_id,
            tgt_type=tgt_type,
            tgt_status=tgt_status,
            dir4=dir4,
            dir8=dir8,
            dist_level=dist_level,
        )

        system_content = (
            "你是一个Neo4j Cypher专家。"
            "将Cypher包裹在【CYPHER】...【/CYPHER】标签中输出。"
            "只输出一条查询，不要任何解释。"
        )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user",   "content": prompt},
        ]

        start_time = time.time()
        response = self.chat(messages, temperature=0.1, max_tokens=1024)
        elapsed  = time.time() - start_time

        # 清洗 <think>
        cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()

        # 优先从【CYPHER】块提取
        block_match = re.search(r"【CYPHER】(.*?)【/CYPHER】", cleaned, flags=re.DOTALL)
        if block_match:
            cypher = block_match.group(1).strip().rstrip(";")
        else:
            # 备选：提取```代码块
            code_match = re.search(r"```(?:cypher)?\s*(.*?)```", cleaned, flags=re.DOTALL)
            cypher = (code_match.group(1).strip() if code_match else cleaned).rstrip(";")

        if not cypher or "RETURN" not in cypher.upper():
            raise RuntimeError(
                f"LLM未能生成有效的缺口上下文Cypher，原始响应: {response!r}"
            )

        self.last_thinking = None
        self.last_elapsed  = elapsed
        return cypher

    def generate_scene_analysis_cypher(self) -> str:
        """生成枚举场景图所有边实例（ID模式）的初始分析 Cypher。

        返回的 Cypher 查询结果字段：
          src_id, src_type, src_status, tgt_id, tgt_type, tgt_status, dir4, dir8, dist_level
        """
        prompt = config.SCENE_ANALYSIS_PROMPT.format(
            schema=config.SCENE_GRAPH_SCHEMA,
        )
        system_content = (
            "你是一个Neo4j Cypher专家。"
            "将Cypher包裹在【CYPHER】...【/CYPHER】标签中输出。"
            "只输出一条查询，不要任何解释。"
        )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user",   "content": prompt},
        ]

        start_time = time.time()
        response   = self.chat(messages, temperature=0.1, max_tokens=512)
        elapsed    = time.time() - start_time

        cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()

        block_match = re.search(r"【CYPHER】(.*?)【/CYPHER】", cleaned, flags=re.DOTALL)
        if block_match:
            cypher = block_match.group(1).strip().rstrip(";")
        else:
            code_match = re.search(r"```(?:cypher)?\s*(.*?)```", cleaned, flags=re.DOTALL)
            cypher = (code_match.group(1).strip() if code_match else cleaned).rstrip(";")

        if not cypher or "RETURN" not in cypher.upper():
            raise RuntimeError(
                f"LLM未能生成有效的场景分析Cypher，原始响应: {response!r}"
            )

        self.last_thinking = None
        self.last_elapsed  = elapsed
        return cypher

    def call_llm_raw(self, prompt: str, max_tokens: int = 2048, temperature: float = 0.7) -> str:
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
            response = self.call_llm_raw(prompt, max_tokens=512, temperature=0.2)
            
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


def test_connection():
    """测试API连接"""
    client = LLMClient()
    try:
        response = client.chat([{"role": "user", "content": "你好，请简短回复。"}])
        print(f"✓ API连接成功！")
        print(f"  回复: {response}")
        return True
    except Exception as e:
        print(f"✗ API连接失败: {e}")
        return False


if __name__ == "__main__":
    test_connection()
