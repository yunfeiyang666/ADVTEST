"""
semantic_auditor.py 鈥?V14.0 涓ら樁娈垫剰鍥惧尮閰嶅璁″紩鎿?

V14 鏍稿績鏀硅繘锛堢浉瀵?V9锛夛細
  Phase 1: LLM 浠呮彁鍙栨剰鍥句笁鍏冪粍 {anchor_type/id, relation_dir, target_type}
           涓嶈姹?LLM 鐚滃叿浣撹妭鐐?ID锛屽噺灏戝够瑙?
  Phase 2: Python 杞尮閰?(卤15掳 鍋忓樊瀹瑰樊)锛屽湪 Neo4j 涓槑纭畾浣?ID
           纭繚瀹屽叏瀵归綈璁烘枃绾х簿搴?
  derive_l2_from_l1: 浠?L1 鐗╃悊杈硅嚜鍔ㄦ帹瀵?L2锛堜笉渚濊禆 LLM锛?
  涓?V9 鍚戜笅鍏煎锛?audit_baseline_question 澶栨帴鍙ｄ笉鍙?
"""
from __future__ import annotations

import json, logging, re, time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# 宸ュ叿鍑芥暟
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def _ms_now() -> str:
    """姣绾ф椂闂存埑: YYYY-MM-DD HH:MM:SS.mmm"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def make_qa_id(global_index: int, template_type: str) -> str:
    """
    鍞竴棰樼洰 ID锛歷al_{鍏ㄥ眬绱㈠紩}_{妯℃澘绫诲瀷}
    渚? global_index=71051, template_type="comparison" 鈫?"val_71051_comparison"
    NuScenes-QA 鍚屽抚澶氶鍏变韩 sample_token锛屽洜姝ゅ繀椤荤敤鍏ㄥ眬绱㈠紩淇濊瘉鍞竴鎬с€?
    """
    return f"val_{global_index}_{template_type}"


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# L2 鑷姩鎺ㄥ锛堜笉渚濊禆 LLM锛?
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def derive_l2_from_l1(l1_edges: List[Dict]) -> List[Dict]:
    """
    瀹氫箟锛歀2 = L1 涓弧瓒?edge1.target == edge2.source 鐨勯灏剧浉杩炶竟瀵?A鈫払鈫扖銆?

    绠楁硶锛歄(n虏) 鎵弿锛坣 閫氬父 鈮?10锛屾瀬蹇級銆?

    绀轰緥锛?
      L1 = [ego鈫抰ruck1, truck1鈫抍ar5, ego鈫抍ar3]
      L2 = [{o1:'ego', o2:'truck1', o3:'car5'}]    鈫?鍙湁 truck1 杩炴帴浜嗕袱鏉¤竟
      ego鈫抍ar3 娌℃湁鍑鸿竟锛屼笉褰㈡垚閾?

    杩欐牱 L2 姘歌繙浠庣墿鐞嗗瓙鍥炬嫇鎵戜腑璇诲彇锛岃€屼笉鏄敱 LLM 鐚滄祴銆?
    """
    if not l1_edges:
        return []

    # 鏋勫缓鍑鸿竟瀛楀吀: source 鈫?[edge, ...]
    edges_from: Dict[str, List[Dict]] = {}
    for e in l1_edges:
        src = e.get("source", "")
        if src:
            edges_from.setdefault(src, []).append(e)

    chains: List[Dict] = []
    seen: set = set()
    for e1 in l1_edges:
        o1, o2 = e1.get("source", ""), e1.get("target", "")
        if not o1 or not o2:
            continue
        for e2 in edges_from.get(o2, []):
            o3 = e2.get("target", "")
            if not o3 or o3 == o1:      # 璺宠繃 A鈫払鈫扐 鑷幆
                continue
            key = (o1, o2, o3)
            if key not in seen:
                seen.add(key)
                chains.append({"o1": o1, "o2": o2, "o3": o3})
    return chains


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# 鍏ㄩ噺鍦烘櫙涓婁笅鏂囷紙鍚墍鏈夎竟锛岄潪鍙?ego 鍑哄彂杈癸級
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def build_scene_context(driver) -> str:
    """
    鏋勫缓渚?LLM 鍙傝€冪殑鍦烘櫙涓婁笅鏂囥€?
    鍖呭惈鍏ㄩ噺杈癸紙涓嶅彧浠?ego 鍑哄彂锛夛紝浣垮璞￠敋瀹氶棶棰樹篃鑳芥纭垎鏋愩€?
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

    # 鍏ㄩ噺杈癸紙鎸?source 鍒嗙粍鏄剧ず锛?
    lines.append("\nSpatial relationships (ALL edges):")
    current_src = None
    for e in edges:
        if e["src"] != current_src:
            lines.append(f"  {e['src']}:")
            current_src = e["src"]
        lines.append(f"    鈫?{e['tgt']} [{e['dir4']}/{e['dir8']}] ({e['dist']})")

    return "\n".join(lines)


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# V14: Phase 1 鎰忓浘鎻愬彇 Prompt
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

INTENT_EXTRACTION_PROMPT = """\
Extract the SPATIAL INTENT from this VQA question as a compact JSON triplet.
DO NOT guess specific object IDs. Return only the category/type and direction.

Question: "{question}"

Return ONLY this JSON (no explanation):
{{
  "anchor_type": "<type-of-reference-object, e.g. ego/truck/car/pedestrian>",
  "anchor_id_hint": "<partial ID hint if explicitly named, else null>",
  "relation_dir": "<one of: front/front-left/front-right/back-left/back-right/back>",
  "target_type": "<type-of-target-object, e.g. car/pedestrian/truck/any>",
  "query_type": "<one of: exist/count/status/object/comparison>"
}}

Examples:
  Q: "What is to the front-left of ego?"  鈫?{{anchor_type:"ego", anchor_id_hint:null, relation_dir:"front-left", target_type:"any", query_type:"object"}}
  Q: "Is there a car to the front of the moving truck?"  鈫?{{anchor_type:"truck", anchor_id_hint:null, relation_dir:"front", target_type:"car", query_type:"exist"}}
  Q: "How many pedestrians are to the back of truck1?"  鈫?{{anchor_type:"truck", anchor_id_hint:"truck1", relation_dir:"back", target_type:"pedestrian", query_type:"count"}}
"""


_DIR8_TO_ANGLE_CENTER = {
    "front": 0.0,
    "front-left": 60.0,
    "front-right": -60.0,
    "back-left": 120.0,
    "back-right": -120.0,
    "back": 180.0,
}


def _angle_diff(a1: float, a2: float) -> float:
    """Minimum absolute angular difference (degrees), wrapping 卤180."""
    d = abs(a1 - a2) % 360
    return d if d <= 180 else 360 - d


def soft_match_by_direction(
    driver,
    anchor_id: str,
    relation_dir: str,
    target_type: str = "any",
    angle_tol_deg: float = 15.0,
) -> List[Dict]:
    """
    V14 Phase 2: Python 杞尮閰嶃€?
    鍦?Neo4j 涓煡鎵句粠 anchor_id 鍑哄彂銆佹柟鍚戝湪 relation_dir
    涓績 卤angle_tol_deg 鍐呯殑鍏ㄩ儴鐩爣鑺傜偣銆?

    杩斿洖 [{'id': ..., 'type': ..., 'status': ..., 'dir8': ..., 'angle_diff': ...}]
    """
    center = _DIR8_TO_ANGLE_CENTER.get(relation_dir)
    if center is None:
        return []

    # 鏍规嵁涓績瑙掑害鎺ㄧ畻 dir8 鍊欓€夛紙涓績 卤15掳 鍙兘璺ㄨ秺涓€涓墖鍖猴級
    target_type_clause = "" if target_type in ("any", "") else f" AND tgt.type = '{target_type}'"

    cypher = (
        f"MATCH (src:Object {{unique_id:'{anchor_id}'}})-[r:RELATES_TO]->(tgt:Object)"
        f" WHERE 1=1{target_type_clause}"
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

    # 杩囨护瑙掑害鍋忓樊 鈮?angle_tol_deg
    matches = []
    for row in rows:
        node_center = _DIR8_TO_ANGLE_CENTER.get(row.get("dir8", ""), None)
        if node_center is None:
            continue
        diff = _angle_diff(center, node_center)
        if diff <= angle_tol_deg:
            matches.append({**row, "angle_diff": diff})
    matches.sort(key=lambda x: x["angle_diff"])  # 鏈€鎺ヨ繎涓績鐨勬帓鍦ㄥ墠
    return matches


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# V14.0 瀹¤ Prompt锛圠LM 杈撳嚭 JSON锛屼笉鐢熸垚 Cypher锛?
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

AUDIT_PROMPT_TEMPLATE = """\
Task: Extract the MINIMAL SUBGRAPH (nodes and edges) required to answer this VQA question.
You are given the complete scene graph. Return a JSON object only.

[Scene Graph]
{scene_context}

[Question]
"{question}"
Template type: {q_type}

[Rules 鈥?MUST FOLLOW]
1. Identify the ANCHOR object(s) of the question:
   - If the question says "to the back of the truck", the truck is the anchor, NOT ego
   - If the question says "visible from my perspective", ego is the anchor
   - If the question says "there is a moving X", X is the anchor
2. Include ONLY nodes and edges that are directly relevant to answering the question
3. Do NOT automatically include ego unless the question references ego/me/my/I
4. For spatial questions: include the anchor node AND the objects in the specified direction
5. For count questions: include anchor 鈫?all objects in that direction
6. Return EXACTLY this JSON format (nothing else):
{{
  "nodes": ["id1", "id2", ...],
  "edges": [
    {{"source": "id1", "target": "id2", "relation": "direction4_value"}},
    ...
  ]
}}

[Correct Example]
Question: "There is a moving truck; how many things are to the back of it?"
Anchor: truck1 (NOT ego)
Output:
{{
  "nodes": ["truck1", "car2", "car3"],
  "edges": [
    {{"source": "truck1", "target": "car2", "relation": "back"}},
    {{"source": "truck1", "target": "car3", "relation": "back"}}
  ]
}}

[Correct Example 2]
Question: "What is to the front of me?"
Anchor: ego
Output:
{{
  "nodes": ["ego", "bus1"],
  "edges": [
    {{"source": "ego", "target": "bus1", "relation": "front"}}
  ]
}}

Now return the JSON for the question above. No explanation, JSON only.
"""

AUDIT_RETRY_TEMPLATE = """\
Your previous response could not be parsed as valid JSON. Error: {error}

Please return ONLY valid JSON in this exact format:
{{
  "nodes": ["id1", "id2"],
  "edges": [{{"source": "id1", "target": "id2", "relation": "front"}}]
}}

Question: "{question}"
"""


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# JSON 瑙ｆ瀽锛堥瞾妫掞級
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def _parse_subgraph_json(raw: str) -> Optional[Dict]:
    """Parse LLM output into {nodes, edges}. Returns None on failure."""
    # Strip markdown fences
    text = re.sub(r"```[a-zA-Z]*\n?", "", raw).strip().rstrip("`").strip()
    # Find JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        text = m.group(0)
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "nodes" in data and "edges" in data:
            # Normalize
            nodes = [str(n) for n in data["nodes"] if n]
            edges = []
            for e in data["edges"]:
                if isinstance(e, dict) and e.get("source") and e.get("target"):
                    edges.append({
                        "source":   str(e["source"]),
                        "target":   str(e["target"]),
                        "relation": str(e.get("relation", e.get("dir", ""))),
                    })
            return {"nodes": list(set(nodes)), "edges": edges}
    except Exception:
        pass
    return None


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# 涓诲璁″嚱鏁?
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def audit_baseline_question(
    question:      str,
    q_type:        str,
    num_hop:       int,
    driver,
    llm_client,
    scene_context: Optional[str] = None,
    global_index:  int = 0,
) -> Dict[str, Any]:
    """
    V14.0 瀹¤锛氫袱闃舵鎰忓浘鍖归厤 鈫?JSON 瀛愬浘 鈫?L0/L1/L2

    Phase 1: LLM 浠呰緭鍑?{anchor_type, anchor_id_hint, relation_dir, target_type}
    Phase 2: Python soft_match_by_direction (卤15掳 瀹藉) 鍦?Neo4j 纭畾鍏蜂綋 ID
             濡傛灉杞尮閰嶆壘鍒拌妭鐐癸紝鐢ㄧ湡瀹?ID 澧炲己 LLM 杈撳嚭鐨勫瓙鍥?
    涓?V9 鍚戜笅鍏煎: 杩斿洖缁撴瀯涓嶅彉

    Returns:
      qa_unique_id  : str
      l0_nodes      : List[str]
      l1_edges      : List[dict]
      l2_paths      : List[dict]
      llm_ms        : float
      success       : bool
      n_l0/n_l1/n_l2: int
      intent        : dict  (Phase 1 鎻愬彇缁撴灉)
      soft_matches  : list  (Phase 2 杞尮閰嶇粨鏋?
    """
    if scene_context is None:
        scene_context = build_scene_context(driver)

    qa_id  = make_qa_id(global_index, q_type)
    t_all0 = time.perf_counter()
    intent: Dict = {}
    soft_matches: list = []

    # 鈹€鈹€ Phase 1: 鎰忓浘鎻愬彇 (LLM 鍙繑鍥炵被鍨?鏂瑰悜, 涓嶇寽 ID) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    intent_prompt = INTENT_EXTRACTION_PROMPT.format(question=question)
    try:
        raw_intent = llm_client._call(intent_prompt)
        m = re.search(r"\{.*\}", raw_intent, re.DOTALL)
        if m:
            intent = json.loads(m.group(0))
    except Exception as exc:
        logger.debug("[audit] q%d Phase-1 failed: %s", global_index, exc)

    # 鈹€鈹€ Phase 2: Python 杞尮閰?(卤15掳) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    if intent.get("anchor_type") and intent.get("relation_dir"):
        # 纭畾 anchor ID
        anchor_id = intent.get("anchor_id_hint") or ""
        if not anchor_id:
            # 濡傛灉娌℃湁 hint锛屽皾璇曞尮閰嶇被鍨嬶紙浠?ego 浼樺厛锛?
            a_type = intent["anchor_type"].lower()
            if a_type == "ego":
                anchor_id = "ego"
            else:
                try:
                    with driver.session() as sess:
                        row = sess.run(
                            "MATCH (n:Object) WHERE n.type=$t RETURN n.unique_id AS id LIMIT 1",
                            t=a_type
                        ).single()
                    if row:
                        anchor_id = row["id"]
                except Exception:
                    pass
        if anchor_id:
            soft_matches = soft_match_by_direction(
                driver=driver,
                anchor_id=anchor_id,
                relation_dir=intent["relation_dir"],
                target_type=intent.get("target_type", "any"),
                angle_tol_deg=15.0,
            )

    # 鈹€鈹€ Phase 3: 鍏ㄥ満鏅瓙鍥?(LLM + 瀹屾暣鍫存櫙涓婁笅鏂? 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    prompt = AUDIT_PROMPT_TEMPLATE.format(
        scene_context=scene_context,
        question=question,
        q_type=q_type,
    )
    t0 = time.perf_counter()
    try:
        raw = llm_client._call(prompt)
        llm_ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:
        logger.warning("[audit] q%d LLM failed: %s", global_index, exc)
        # 濡傛灉鍏ㄥ満鏅?LLM 澶辫触锛岀敤 Phase2 杞尮閰嶇粨鏋滄瀯寤哄瓙鍥?
        if soft_matches:
            l0 = ([intent.get("anchor_id_hint") or "ego"] +
                  [m["id"] for m in soft_matches[:3]])
            anchor = l0[0]
            l1 = [{"source": anchor, "target": m["id"],
                   "relation": intent.get("relation_dir", "")} for m in soft_matches[:3]]
            l2 = derive_l2_from_l1(l1)
            return {
                "qa_unique_id": qa_id, "l0_nodes": l0, "l1_edges": l1, "l2_paths": l2,
                "llm_ms": round((time.perf_counter()-t_all0)*1000, 1),
                "success": True, "n_l0": len(l0), "n_l1": len(l1), "n_l2": len(l2),
                "intent": intent, "soft_matches": soft_matches,
            }
        return _fail(qa_id)

    subgraph = _parse_subgraph_json(raw)

    # 鈹€鈹€ Retry once on parse failure 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    if subgraph is None:
        logger.debug("[audit] q%d parse failed, retrying", global_index)
        try:
            retry_prompt = AUDIT_RETRY_TEMPLATE.format(
                error="Could not parse JSON",
                question=question,
            )
            raw2 = llm_client._call(retry_prompt)
            llm_ms += (time.perf_counter() - t0) * 1000
            subgraph = _parse_subgraph_json(raw2)
        except Exception:
            pass

    if subgraph is None:
        logger.warning("[audit] q%d JSON parse failed after retry: %s", global_index, raw[:100])
        return _fail(qa_id)

    # 鈹€鈹€ 鐢?Phase2 杞尮閰嶇粨鏋滃寮哄瓙鍥撅紙琛ュ叆鏈 LLM 璇嗗埆鐨勮妭鐐癸級 鈹€鈹€鈹€
    if soft_matches and intent.get("anchor_id_hint"):
        anchor_id = intent["anchor_id_hint"]
        existing_tgts = {e["target"] for e in subgraph["edges"]}
        for m in soft_matches:
            if m["id"] not in existing_tgts and m["id"] not in subgraph["nodes"]:
                # 杞尮閰嶅埌鐨勮妭鐐瑰姞鍏ュ瓙鍥撅紙Phase2 琛ュ叆锛?
                subgraph["nodes"].append(m["id"])
                subgraph["edges"].append({
                    "source": anchor_id,
                    "target": m["id"],
                    "relation": intent.get("relation_dir", ""),
                })

    # 鈹€鈹€ Derive L2 automatically from L1 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
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
        "intent":       intent,
        "soft_matches": soft_matches,
    }


def _fail(qa_id: str) -> Dict:
    return {
        "qa_unique_id": qa_id,
        "l0_nodes": [], "l1_edges": [], "l2_paths": [],
        "llm_ms": 0.0, "success": False,
        "n_l0": 0, "n_l1": 0, "n_l2": 0,
    }


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# 鎵归噺瀹¤
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def audit_baseline_batch(
    questions:      List[Dict],
    driver,
    llm_client,
    global_indices: Optional[List[int]] = None,
    report_every:   int = 5,
) -> List[Dict]:
    """Batch-audit NuScenes-QA baseline questions with progress logging."""
    scene_ctx = build_scene_context(driver)
    logger.info("Scene context: %d chars", len(scene_ctx))

    if global_indices is None:
        global_indices = list(range(len(questions)))

    results = []
    t0 = time.perf_counter()
    for i, (q, gidx) in enumerate(zip(questions, global_indices), 1):
        res = audit_baseline_question(
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


