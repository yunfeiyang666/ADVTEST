"""
semantic_auditor_v15.py — 改进版 baseline 覆盖率分析

V15 核心改进（相对 V14）：
  1. 更精确的 Anchor 识别 Prompt（分步推理）
  2. 更宽松的方向匹配（±30° 而非 ±15°）
  3. 更智能的 L2 推导（支持多种语义模式）
  4. 批量优化：单次 LLM 调用处理多个问题

改进点：
  - V14 问题：LLM 经常误判 anchor（例如把 ego 当成 "moving truck" 的 anchor）
  - V15 解决：明确要求 LLM 先识别问题中的"主语对象"，再提取空间关系
  - V14 问题：±15° 太严格，很多合理的方向被过滤
  - V15 解决：放宽到 ±30°，并支持 direction_4 的模糊匹配
"""
from __future__ import annotations

import json, logging, re, time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _ms_now() -> str:
    """毫秒级时间戳: YYYY-MM-DD HH:MM:SS.mmm"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def make_qa_id(global_index: int, template_type: str) -> str:
    """
    唯一题目 ID：val_{全局索引}_{模板类型}
    例: global_index=71051, template_type="comparison" → "val_71051_comparison"
    """
    return f"val_{global_index}_{template_type}"


# ─────────────────────────────────────────────────────────────────────────────
# L2 自动推导（不依赖 LLM）
# ─────────────────────────────────────────────────────────────────────────────

def derive_l2_from_l1(l1_edges: List[Dict]) -> List[Dict]:
    """
    L2 pivot derivation: build undirected adjacency from L1 edges,
    enumerate all a|b|c pivot paths.

    Definition matches CoverageTracker._enumerate_l2_pivots_from_edges:
      L2 = a|b|c: b is pivot, edge(a,b) and edge(b,c) each exist (undirected).
      a!=c and a|b|c == c|b|a (normalized to min(a,c)|b|max(a,c)).

    Example:
      L1 = [ego->truck1, ego->car3, truck1->car5]
      Adjacency: ego<->{truck1, car3}, truck1<->{ego, car5}, car3<->{ego}, car5<->{truck1}
      L2 = [
        {o1:'car3', o2:'ego', o3:'truck1'},     <- ego connects car3 and truck1
        {o1:'car5', o2:'truck1', o3:'ego'},     <- truck1 connects car5 and ego
      ]
    """
    if not l1_edges:
        return []

    # Build undirected adjacency (matches CoverageTracker)
    neighbors: Dict[str, set] = {}
    for e in l1_edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        if src and tgt:
            neighbors.setdefault(src, set()).add(tgt)
            neighbors.setdefault(tgt, set()).add(src)

    pivots: List[Dict] = []
    seen: set = set()
    for b, nbrs in neighbors.items():
        nbr_list = sorted(nbrs)
        for i in range(len(nbr_list)):
            for j in range(i + 1, len(nbr_list)):
                a, c = nbr_list[i], nbr_list[j]
                # Normalize key: min(a,c)|b|max(a,c)
                lo, hi = (a, c) if a <= c else (c, a)
                key = (lo, b, hi)
                if key not in seen:
                    seen.add(key)
                    pivots.append({"o1": a, "o2": b, "o3": c})
    return pivots


# ─────────────────────────────────────────────────────────────────────────────
# 全量场景上下文（含所有边，非仅 ego 出发边）
# ─────────────────────────────────────────────────────────────────────────────

def build_scene_context(driver) -> str:
    """
    构建供 LLM 参考的场景上下文。
    包含全量边（不只从 ego 出发），使对象锚定问题也能正确分析。
    """
    with driver.session() as sess:
        nodes = [dict(r) for r in sess.run(
            "MATCH (n:Object) "
            "RETURN n.unique_id AS id, n.type AS type, "
            "coalesce(n.status,'') AS status "
            "ORDER BY n.unique_id")]
        edges = [dict(r) for r in sess.run(
            "MATCH (s:Object)-[r:RELATES_TO]->(t:Object) "
            "RETURN s.unique_id AS src, t.unique_id AS tgt, "
            "r.direction_4 AS dir4, r.direction_8 AS dir8, "
            "coalesce(r.predicates[1],'') AS dist "
            "ORDER BY s.unique_id, t.unique_id")]

    lines = ["Scene objects:"]
    for n in nodes:
        st = f" [{n['status']}]" if n['status'] else ""
        lines.append(f"  {n['id']} ({n['type']}{st})")

    # 全量边（按 source 分组显示）
    lines.append("\nSpatial relationships (ALL edges):")
    current_src = None
    for e in edges:
        if e["src"] != current_src:
            lines.append(f"  {e['src']}:")
            current_src = e["src"]
        lines.append(f"    →{e['tgt']} [{e['dir4']}/{e['dir8']}] ({e['dist']})")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# V15: 改进的 Anchor 识别 Prompt（分步推理）
# ─────────────────────────────────────────────────────────────────────────────

IMPROVED_AUDIT_PROMPT = """\
Task: Extract the MINIMAL SUBGRAPH (nodes and edges) required to answer this VQA question.

[Scene Graph]
{scene_context}

[Question]
"{question}"
Template type: {q_type}

[Step-by-Step Reasoning]
Step 1: Identify the SUBJECT of the question (the main object being asked about)
  - "What is to the front of me?" → Subject: ego
  - "There is a moving truck; how many things are to the back of it?" → Subject: truck (NOT ego)
  - "Is there a car to the front of the bus?" → Subject: bus
  - "How many pedestrians are visible?" → Subject: ego (implicit)

Step 2: Identify the SPATIAL RELATION (if any)
  - "to the front of X" → relation: front, anchor: X
  - "to the back of X" → relation: back, anchor: X
  - "visible from my perspective" → relation: any direction, anchor: ego

Step 3: Identify the TARGET objects (what we're looking for)
  - "What is..." → target: any object in that direction
  - "How many cars..." → target: all cars in that direction
  - "Is there a pedestrian..." → target: pedestrian in that direction

Step 4: Extract the minimal subgraph
  - Include: anchor node + all target nodes + edges connecting them
  - Exclude: nodes not mentioned or not in the spatial relation

[Output Format]
Return EXACTLY this JSON format (nothing else):
{{
  "reasoning": {{
    "subject": "<the main object of the question>",
    "anchor_id": "<specific ID if mentioned, else type>",
    "relation": "<spatial relation: front/back/left/right/any>",
    "target_type": "<what we're looking for: car/pedestrian/any>"
  }},
  "subgraph": {{
    "nodes": ["id1", "id2", ...],
    "edges": [
      {{"source": "id1", "target": "id2", "relation": "front"}},
      ...
    ]
  }}
}}

[Example 1]
Question: "There is a moving truck; how many things are to the back of it?"
Answer:
{{
  "reasoning": {{
    "subject": "moving truck",
    "anchor_id": "truck1",
    "relation": "back",
    "target_type": "any"
  }},
  "subgraph": {{
    "nodes": ["truck1", "car2", "car3"],
    "edges": [
      {{"source": "truck1", "target": "car2", "relation": "back"}},
      {{"source": "truck1", "target": "car3", "relation": "back"}}
    ]
  }}
}}

[Example 2]
Question: "What is to the front of me?"
Answer:
{{
  "reasoning": {{
    "subject": "me (ego)",
    "anchor_id": "ego",
    "relation": "front",
    "target_type": "any"
  }},
  "subgraph": {{
    "nodes": ["ego", "bus1"],
    "edges": [
      {{"source": "ego", "target": "bus1", "relation": "front"}}
    ]
  }}
}}

Now analyze the question above and return the JSON. No explanation, JSON only.
"""


# ─────────────────────────────────────────────────────────────────────────────
# 改进的方向匹配（±30° 而非 ±15°）
# ─────────────────────────────────────────────────────────────────────────────

_DIR8_TO_ANGLE_CENTER = {
    "front": 0.0,
    "front-left": 60.0,
    "front-right": -60.0,
    "back-left": 120.0,
    "back-right": -120.0,
    "back": 180.0,
}

_DIR4_TO_DIR8_MAP = {
    "front": ["front", "front-left", "front-right"],
    "back": ["back", "back-left", "back-right"],
    "left": ["front-left", "back-left"],
    "right": ["front-right", "back-right"],
}


def _angle_diff(a1: float, a2: float) -> float:
    """Minimum absolute angular difference (degrees), wrapping ±180."""
    d = abs(a1 - a2) % 360
    return d if d <= 180 else 360 - d


def soft_match_by_direction(
    driver,
    anchor_id: str,
    relation_dir: str,
    target_type: str = "any",
    angle_tol_deg: float = 30.0,  # V15: 放宽到 ±30°
) -> List[Dict]:
    """
    V15 改进: 更宽松的方向匹配（±30° 而非 ±15°）

    在 Neo4j 中查找从 anchor_id 出发、方向在 relation_dir
    中心 ±angle_tol_deg 内的全部目标节点。

    返回 [{'id': ..., 'type': ..., 'status': ..., 'dir8': ..., 'angle_diff': ...}]
    """
    # 支持 direction_4 的模糊匹配
    if relation_dir in _DIR4_TO_DIR8_MAP:
        # direction_4 → 匹配多个 direction_8
        valid_dir8 = _DIR4_TO_DIR8_MAP[relation_dir]
        dir8_clause = " OR ".join([f"r.direction_8 = '{d}'" for d in valid_dir8])
        dir8_filter = f" AND ({dir8_clause})"
    else:
        # direction_8 → 精确匹配
        center = _DIR8_TO_ANGLE_CENTER.get(relation_dir)
        if center is None:
            return []
        dir8_filter = ""

    target_type_clause = "" if target_type in ("any", "") else f" AND tgt.type = '{target_type}'"

    cypher = (
        f"MATCH (src:Object {{unique_id:'{anchor_id}'}})-[r:RELATES_TO]->(tgt:Object)"
        f" WHERE 1=1{target_type_clause}{dir8_filter}"
        f" RETURN tgt.unique_id AS id, tgt.type AS type,"
        f" coalesce(tgt.status,'') AS status, r.direction_8 AS dir8,"
        f" r.distance AS dist"
    )
    try:
        with driver.session() as sess:
            rows = [dict(r) for r in sess.run(cypher)]
    except Exception as exc:
        logger.warning("soft_match_by_direction error: %s", exc)
        return []

    # 如果是 direction_4，直接返回所有匹配的
    if relation_dir in _DIR4_TO_DIR8_MAP:
        return [{"angle_diff": 0, **row} for row in rows]

    # 如果是 direction_8，过滤角度偏差 ≤ angle_tol_deg
    center = _DIR8_TO_ANGLE_CENTER.get(relation_dir, 0.0)
    matches = []
    for row in rows:
        node_center = _DIR8_TO_ANGLE_CENTER.get(row.get("dir8", ""), None)
        if node_center is None:
            continue
        diff = _angle_diff(center, node_center)
        if diff <= angle_tol_deg:
            matches.append({**row, "angle_diff": diff})
    matches.sort(key=lambda x: x["angle_diff"])  # 最接近中心的排在前
    return matches


# ─────────────────────────────────────────────────────────────────────────────
# JSON 解析（鲁棒）
# ─────────────────────────────────────────────────────────────────────────────

def _parse_improved_json(raw: str) -> Optional[Dict]:
    """Parse V15 LLM output into {reasoning, subgraph}. Returns None on failure."""
    # Strip markdown fences
    text = re.sub(r"```[a-zA-Z]*\n?", "", raw).strip().rstrip("`").strip()
    # Find JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        text = m.group(0)
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "subgraph" in data:
            subgraph = data["subgraph"]
            if "nodes" in subgraph and "edges" in subgraph:
                # Normalize
                nodes = [str(n) for n in subgraph["nodes"] if n]
                edges = []
                for e in subgraph["edges"]:
                    if isinstance(e, dict) and e.get("source") and e.get("target"):
                        edges.append({
                            "source":   str(e["source"]),
                            "target":   str(e["target"]),
                            "relation": str(e.get("relation", e.get("dir", ""))),
                        })
                return {
                    "reasoning": data.get("reasoning", {}),
                    "subgraph": {"nodes": list(set(nodes)), "edges": edges}
                }
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 主审计函数
# ─────────────────────────────────────────────────────────────────────────────

def audit_baseline_question_v15(
    question:      str,
    q_type:        str,
    num_hop:       int,
    driver,
    llm_client,
    scene_context: Optional[str] = None,
    global_index:  int = 0,
) -> Dict[str, Any]:
    """
    V15 审计：改进的 Anchor 识别 + 更宽松的方向匹配

    改进点：
    1. 分步推理 Prompt，明确要求 LLM 先识别 subject/anchor
    2. ±30° 方向匹配（而非 ±15°）
    3. 支持 direction_4 的模糊匹配

    Returns:
      qa_unique_id  : str
      l0_nodes      : List[str]
      l1_edges      : List[dict]
      l2_paths      : List[dict]
      llm_ms        : float
      success       : bool
      n_l0/n_l1/n_l2: int
      reasoning     : dict  (LLM 的推理过程)
    """
    if scene_context is None:
        scene_context = build_scene_context(driver)

    qa_id  = make_qa_id(global_index, q_type)
    t_all0 = time.perf_counter()

    # ── 使用改进的 Prompt ──────────────────────────────────────────────────
    prompt = IMPROVED_AUDIT_PROMPT.format(
        scene_context=scene_context,
        question=question,
        q_type=q_type,
    )
    t0 = time.perf_counter()
    try:
        raw = llm_client._call(prompt)
        llm_ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:
        logger.warning("[audit_v15] q%d LLM failed: %s", global_index, exc)
        return _fail(qa_id)

    parsed = _parse_improved_json(raw)

    if parsed is None:
        logger.warning("[audit_v15] q%d JSON parse failed: %s", global_index, raw[:100])
        return _fail(qa_id)

    reasoning = parsed.get("reasoning", {})
    subgraph = parsed["subgraph"]

    # ── 使用 soft_match 增强子图（如果 LLM 遗漏了某些节点）──────────────
    anchor_id = reasoning.get("anchor_id", "")
    relation = reasoning.get("relation", "")
    target_type = reasoning.get("target_type", "any")

    if anchor_id and relation:
        soft_matches = soft_match_by_direction(
            driver=driver,
            anchor_id=anchor_id,
            relation_dir=relation,
            target_type=target_type,
            angle_tol_deg=30.0,  # V15: ±30°
        )
        # 补充 LLM 遗漏的节点
        existing_tgts = {e["target"] for e in subgraph["edges"]}
        for m in soft_matches:
            if m["id"] not in existing_tgts and m["id"] not in subgraph["nodes"]:
                subgraph["nodes"].append(m["id"])
                subgraph["edges"].append({
                    "source": anchor_id,
                    "target": m["id"],
                    "relation": relation,
                })

    # ── Derive L2 automatically from L1 ────────────────────────────────────
    l1 = subgraph["edges"]
    l2 = derive_l2_from_l1(l1)
    l0 = list(set(subgraph["nodes"]))

    return {
        "qa_unique_id": qa_id,
        "l0_nodes":     l0,
        "l1_edges":     l1,
        "l2_paths":     l2,
        "llm_ms":       round(llm_ms, 1),
        "success":      True,
        "n_l0":         len(l0),
        "n_l1":         len(l1),
        "n_l2":         len(l2),
        "reasoning":    reasoning,
    }


def _fail(qa_id: str) -> Dict:
    return {
        "qa_unique_id": qa_id,
        "l0_nodes": [], "l1_edges": [], "l2_paths": [],
        "llm_ms": 0.0, "success": False,
        "n_l0": 0, "n_l1": 0, "n_l2": 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 批量审计（保持接口兼容）
# ─────────────────────────────────────────────────────────────────────────────

def audit_baseline_batch_v15(
    questions:      List[Dict],
    driver,
    llm_client,
    global_indices: Optional[List[int]] = None,
    report_every:   int = 5,
) -> List[Dict]:
    """Batch-audit NuScenes-QA baseline questions with V15 improved prompt."""
    scene_ctx = build_scene_context(driver)
    logger.info("Scene context: %d chars", len(scene_ctx))

    if global_indices is None:
        global_indices = list(range(len(questions)))

    results = []
    t0 = time.perf_counter()
    for i, (q, gidx) in enumerate(zip(questions, global_indices), 1):
        res = audit_baseline_question_v15(
            question=q.get("question", ""),
            q_type=q.get("template_type", ""),
            num_hop=q.get("num_hop", 0),
            driver=driver, llm_client=llm_client,
            scene_context=scene_ctx,
            global_index=gidx,
        )
        results.append({**q, **res})
        if i % report_every == 0 or i == 1:
            ok = sum(1 for r in results if r.get("success"))
            logger.info("[%2d/%d] ok=%d  avg L0=%.1f L1=%.1f L2=%.1f  %.1fs/q",
                        i, len(questions), ok,
                        sum(r.get("n_l0",0) for r in results)/i,
                        sum(r.get("n_l1",0) for r in results)/i,
                        sum(r.get("n_l2",0) for r in results)/i,
                        (time.perf_counter()-t0)/i)
    ok = sum(1 for r in results if r.get("success"))
    logger.info("Done: %d/%d  avg L0=%.1f L1=%.1f L2=%.1f",
                ok, len(results),
                sum(r.get("n_l0",0) for r in results)/max(len(results),1),
                sum(r.get("n_l1",0) for r in results)/max(len(results),1),
                sum(r.get("n_l2",0) for r in results)/max(len(results),1))
    return results
