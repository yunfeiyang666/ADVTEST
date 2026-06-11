"""Neo4j-backed grounding for original NuScenesQA coverage."""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Tuple

from gap_pipeline.l2_question_graph import QuestionGraph


def _http_url() -> str:
    return os.environ.get("NEO4J_HTTP_URL") or "http://localhost:7474/db/neo4j/tx/commit"


def _auth_header() -> str:
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "87017563")
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def _post(statements: List[Dict[str, Any]]) -> Dict[str, Any]:
    req = urllib.request.Request(
        _http_url(),
        data=json.dumps({"statements": statements}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": _auth_header()},
    )
    with urllib.request.urlopen(req, timeout=int(os.environ.get("NEO4J_TIMEOUT_SECONDS") or 120)) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    for match in re.finditer(r"\{.*\}", text, flags=re.S):
        try:
            return json.loads(match.group())
        except Exception:
            continue
    return {}


def _question_text(record: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(record.get("question") or record.get("Question") or ""),
        str(record.get("answer") or record.get("Answer") or ""),
        str(record.get("template_type") or ""),
        str(record.get("num_hop") or ""),
    )


def make_coverage_cypher(record: Dict[str, Any], llm_client: Any) -> Dict[str, Any]:
    question, answer, template_type, num_hop = _question_text(record)
    prompt = f"""
You generate Neo4j Cypher for coverage grounding, not for final answer checking.
Schema:
(:Object {{unique_id,type,category,status,is_ego}})
(:Object)-[:RELATES_TO {{direction_6,distance,is_nearest,rank_by_distance}}]->(:Object)

Task: Given a NuScenesQA question, write one READ-ONLY Cypher query that returns graph elements touched when solving it on the current filtered graph.
Rules:
- Do NOT verify the provided answer. The answer is context only.
- Do NOT return count/boolean as the main result. Return touched object ids and edge endpoint pairs.
- Output JSON only with keys: cypher, query_type, notes.
- Cypher MUST return exactly two columns: nodes and edges.
- nodes: list of object unique_id strings.
- edges: list of [source_unique_id, target_unique_id] pairs for RELATES_TO relations directly used by the question.
- Use only MATCH/OPTIONAL MATCH/WHERE/WITH/RETURN, boolean logic, IN, CONTAINS, =~ if helpful.
- Never use CREATE, MERGE, DELETE, DETACH, SET, REMOVE, CALL, LOAD, APOC.
- Spatial relations use official 6-direction property r.direction_6 with underscore labels: front, front_left, front_right, back_left, back_right, back.
- NuScenes filtered graph aliases: traffic cone often appears as type='barrier' and category CONTAINS 'trafficcone'; car as type='car' or category CONTAINS 'vehicle.car'; pedestrian as type='pedestrian' or category CONTAINS 'pedestrian'.
- For answer='no' exist questions, if no target path exists, return the anchor node(s) only, e.g. ['ego'], with edges=[] when appropriate.

Examples:
Q: Are any cars visible?
Cypher: MATCH (c:Object) WHERE c.type='car' OR c.category CONTAINS 'vehicle.car' RETURN collect(DISTINCT c.unique_id) AS nodes, [] AS edges
Q: Are any traffic cones visible?
Cypher: MATCH (c:Object) WHERE c.type='traffic_cone' OR c.type='barrier' OR c.category CONTAINS 'trafficcone' RETURN collect(DISTINCT c.unique_id) AS nodes, [] AS edges
Q: Are there any moving cars to the back left of me? Answer: no
Cypher: MATCH (ego:Object {{unique_id:'ego'}}) OPTIONAL MATCH (ego)-[r:RELATES_TO]->(c:Object) WHERE (c.type='car' OR c.category CONTAINS 'vehicle.car') AND c.status='moving' AND r.direction_6='back_left' RETURN CASE WHEN count(c)=0 THEN ['ego'] ELSE collect(DISTINCT ego.unique_id)+collect(DISTINCT c.unique_id) END AS nodes, collect(DISTINCT [ego.unique_id,c.unique_id]) AS edges
Q: There is a not standing pedestrian; what number of things are to the front left of it?
Cypher: MATCH (p:Object)-[r:RELATES_TO]->(t:Object) WHERE (p.type='pedestrian' OR p.category CONTAINS 'pedestrian') AND NOT p.status='standing' AND r.direction_6='front_left' AND t.unique_id <> 'ego' RETURN collect(DISTINCT p.unique_id)+collect(DISTINCT t.unique_id) AS nodes, collect(DISTINCT [p.unique_id,t.unique_id]) AS edges

Question: {question}
Answer: {answer}
Template type: {template_type}
Num hop: {num_hop}
""".strip()
    data = llm_client._post_json("/chat/completions", {
        "model": llm_client.model,
        "messages": [{"role": "system", "content": "Return strict JSON only. Do not explain."}, {"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": int(os.environ.get("VQA_CYPHER_MAX_TOKENS") or os.environ.get("LLM_COVERAGE_MAX_TOKENS") or 512),
        "chat_template_kwargs": {"enable_thinking": False},
        "_timeout_seconds": int(os.environ.get("LLM_COVERAGE_TIMEOUT_SECONDS") or 45),
        "_retries": int(os.environ.get("LLM_COVERAGE_RETRIES") or 0),
    })

    msg = data.get("choices", [{}])[0].get("message", {})
    raw = msg.get("content") or msg.get("reasoning_content") or ""
    payload = _extract_json(str(raw))
    payload["_llm_raw"] = str(raw)[:4000]
    return payload


def validate_readonly_cypher(cypher: str) -> None:
    text = re.sub(r"//.*", "", cypher).strip()
    upper = re.sub(r"\s+", " ", text.upper())
    forbidden = ["CREATE", "MERGE", "DELETE", "DETACH", " SET ", "REMOVE", "CALL", "LOAD", "APOC", "DROP", "FOREACH"]
    if not upper.startswith(("MATCH", "OPTIONAL MATCH")):
        raise ValueError("cypher_must_start_with_match")
    hit = [word for word in forbidden if word in f" {upper} "]
    if hit:
        raise ValueError(f"forbidden_cypher_keyword:{hit[0]}")
    if " RETURN " not in f" {upper} ":
        raise ValueError("cypher_missing_return")


def execute_coverage_cypher(cypher: str) -> Tuple[List[str], List[Tuple[str, str]], Dict[str, Any]]:
    validate_readonly_cypher(cypher)
    result = _post([{"statement": cypher, "resultDataContents": ["row"]}])
    rows = result.get("results", [{}])[0].get("data", [])
    cols = result.get("results", [{}])[0].get("columns", [])
    nodes: set[str] = set()
    edges: set[Tuple[str, str]] = set()
    for entry in rows:
        row = entry.get("row", [])
        data = dict(zip(cols, row))
        for value in data.get("nodes", []) or []:
            if value is not None:
                nodes.add(str(value))
        for pair in data.get("edges", []) or []:
            if isinstance(pair, list) and len(pair) >= 2 and pair[0] and pair[1]:
                a, b = str(pair[0]), str(pair[1])
                edges.add((a, b)); nodes.update([a, b])
    meta = {"columns": cols, "row_count": len(rows)}
    return sorted(nodes), sorted(edges), meta


def footprint_from_cypher(record: Dict[str, Any], llm_client: Any) -> Dict[str, Any]:
    payload = make_coverage_cypher(record, llm_client)
    cypher = str(payload.get("cypher") or "")
    nodes, edges, meta = execute_coverage_cypher(cypher)
    graph = QuestionGraph(template_family="initial_coverage_cypher")
    for node in nodes:
        graph.add_node(node)
    for a, b in edges:
        graph.add_edge(a, b, source="original_qa_cypher")
    fp: Dict[str, Any] = graph.footprint().as_dict()
    fp["_grounding_status"] = "cypher_grounded"
    fp["_grounded_nodes"] = nodes
    fp["_grounded_edges"] = [[a, b] for a, b in edges]
    fp["_llm_payload"] = payload
    fp["_llm_raw"] = payload.get("_llm_raw", "")
    fp["_llm_cypher"] = cypher
    fp["_neo4j_meta"] = meta
    return fp

